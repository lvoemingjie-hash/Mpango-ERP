"""Platform operator credential lifecycle service (DC-11P2).

This service owns platform operator setup/reset/invite/disable/revoke and
break-glass recovery without integrating login/JWT guard behavior. P3 will wire
the dedicated identity into auth.py/security.py/guard.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.security import hash_password, verify_password
from db.tenant_filter import mark_session_as_system
from models.platform_operator import (
    PlatformOperator,
    PlatformOperatorRecoveryCredential,
    PlatformOperatorResetToken,
    PlatformOperatorSetupToken,
)
from services.email_delivery import (
    EmailDeliveryNotConfiguredError,
    record_platform_operator_reset_email,
    record_platform_operator_setup_email,
)
from services.onboarding_service import (
    generate_verification_token,
    hash_token,
    validate_password_policy,
)
from services.platform_audit_service import append_audit_entry


SETUP_TOKEN_TTL = timedelta(hours=24)
RESET_TOKEN_TTL = timedelta(hours=1)
LOCKOUT_AFTER_ATTEMPTS = 5
LOCKOUT_TTL = timedelta(minutes=15)
INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN = "INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN"
NEUTRAL_PLATFORM_OPERATOR_SETUP_MESSAGE = "If this platform credential link is valid, credentials will be updated."
NEUTRAL_PLATFORM_OPERATOR_RESET_MESSAGE = "If this email can be used, platform password instructions will be sent."


class PlatformOperatorLifecycleError(Exception):
    """Base exception for platform operator lifecycle failures."""


class PlatformOperatorExistsError(PlatformOperatorLifecycleError):
    """Raised when an operator email already exists."""


class PlatformOperatorNotFoundError(PlatformOperatorLifecycleError):
    """Raised when an operator row is not found."""


class PlatformOperatorInvalidStateError(PlatformOperatorLifecycleError):
    """Raised when an operator state cannot perform the requested action."""


class PlatformOperatorTokenInvalidError(PlatformOperatorLifecycleError):
    """Raised for invalid, expired, used, or revoked setup/reset tokens."""


class PlatformOperatorRecoveryInvalidError(PlatformOperatorLifecycleError):
    """Raised for invalid break-glass recovery credentials."""


@dataclass(frozen=True)
class PlatformOperatorLifecycleResult:
    operator_id: UUID
    email: str
    status: str
    role: str
    auth_version: int
    expires_at: datetime | None = None


@dataclass(frozen=True)
class PlatformOperatorResetRequestResult:
    issued: bool
    email: str


def normalize_operator_email(email: str) -> str:
    return (email or "").strip().lower()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bump_auth_version(operator: PlatformOperator) -> None:
    operator.auth_version = int(operator.auth_version or 1) + 1


def _is_token_actionable(token, now: datetime) -> bool:
    return bool(
        token
        and not token.is_deleted
        and token.used_at is None
        and token.revoked_at is None
        and token.expires_at > now
    )


def _operator_result(
    operator: PlatformOperator,
    *,
    expires_at: datetime | None = None,
) -> PlatformOperatorLifecycleResult:
    return PlatformOperatorLifecycleResult(
        operator_id=operator.id,
        email=operator.email,
        status=operator.status,
        role=operator.role,
        auth_version=int(operator.auth_version),
        expires_at=expires_at,
    )


class PlatformOperatorService:
    """Hash-only platform operator credential lifecycle operations."""

    def __init__(self, db: AsyncSession, *, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        mark_session_as_system(db, reason="platform_operator_lifecycle")

    async def bootstrap_first_operator(
        self,
        *,
        email: str,
    ) -> PlatformOperatorLifecycleResult:
        """Create the first pending platform admin and email a setup token.

        The raw setup token is returned only through the email delivery channel.
        CLI callers must not print it or persist it.
        """
        normalized = normalize_operator_email(email)
        await self.db.execute(text("LOCK TABLE public.platform_operators IN SHARE ROW EXCLUSIVE MODE"))
        count = await self.db.scalar(
            select(func.count(PlatformOperator.id)).where(PlatformOperator.is_deleted.is_(False))
        )
        if int(count or 0) > 0:
            raise PlatformOperatorInvalidStateError("FIRST_OPERATOR_ALREADY_EXISTS")

        operator = PlatformOperator(
            email=normalized,
            role="platform_admin",
            status="pending_setup",
            password_hash=None,
        )
        self.db.add(operator)
        await self.db.flush()
        raw_token, expires_at = await self._issue_setup_token(operator, _now())
        record_platform_operator_setup_email(
            settings=self.settings,
            to_email=operator.email,
            token=raw_token,
        )
        await self._audit(
            actor_type="system",
            action="platform_operator.bootstrap",
            operator=operator,
        )
        return _operator_result(operator, expires_at=expires_at)

    async def invite_operator(
        self,
        *,
        email: str,
        role: str = "platform_operator",
        invited_by: UUID | None = None,
    ) -> PlatformOperatorLifecycleResult:
        normalized = normalize_operator_email(email)
        if role not in {"platform_admin", "platform_operator"}:
            raise PlatformOperatorInvalidStateError("INVALID_PLATFORM_ROLE")
        if await self._operator_by_email(normalized) is not None:
            raise PlatformOperatorExistsError("PLATFORM_OPERATOR_EXISTS")

        operator = PlatformOperator(
            email=normalized,
            role=role,
            status="pending_setup",
            password_hash=None,
            invited_by=invited_by,
        )
        self.db.add(operator)
        await self.db.flush()
        raw_token, expires_at = await self._issue_setup_token(operator, _now())
        record_platform_operator_setup_email(
            settings=self.settings,
            to_email=operator.email,
            token=raw_token,
        )
        await self._audit(
            actor_type="platform_operator" if invited_by else "system",
            actor_id=invited_by,
            action="platform_operator.invite",
            operator=operator,
        )
        return _operator_result(operator, expires_at=expires_at)

    async def setup_credential(self, *, setup_token: str | None, password: str) -> PlatformOperatorLifecycleResult:
        validate_password_policy(password)
        token_row, operator = await self._setup_token_with_operator(setup_token)
        now = _now()
        if not _is_token_actionable(token_row, now) or operator.revoked_at is not None:
            raise PlatformOperatorTokenInvalidError(INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN)

        operator.password_hash = hash_password(password)
        operator.status = "active"
        operator.failed_login_attempts = 0
        operator.locked_until = None
        _bump_auth_version(operator)
        token_row.used_at = now
        await self.db.flush()
        await self._audit(
            actor_type="platform_operator",
            actor_id=operator.id,
            action="platform_operator.setup_credential",
            operator=operator,
        )
        return _operator_result(operator)

    async def request_password_reset(self, *, email: str) -> PlatformOperatorResetRequestResult:
        normalized = normalize_operator_email(email)
        operator = await self._operator_by_email(normalized, for_update=True)
        if operator is None or not self._can_issue_reset(operator):
            return PlatformOperatorResetRequestResult(issued=False, email=normalized)

        now = _now()
        raw_token, _expires_at = await self._issue_reset_token(operator, now)
        record_platform_operator_reset_email(
            settings=self.settings,
            to_email=operator.email,
            token=raw_token,
        )
        await self._audit(
            actor_type="system",
            action="platform_operator.forgot_password",
            operator=operator,
        )
        return PlatformOperatorResetRequestResult(issued=True, email=normalized)

    async def reset_password(self, *, reset_token: str | None, new_password: str) -> PlatformOperatorLifecycleResult:
        validate_password_policy(new_password)
        token_row, operator = await self._reset_token_with_operator(reset_token)
        now = _now()
        if not _is_token_actionable(token_row, now) or not self._can_issue_reset(operator):
            raise PlatformOperatorTokenInvalidError(INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN)

        operator.password_hash = hash_password(new_password)
        operator.failed_login_attempts = 0
        operator.locked_until = None
        _bump_auth_version(operator)
        token_row.used_at = now
        await self.db.flush()
        await self._audit(
            actor_type="platform_operator",
            actor_id=operator.id,
            action="platform_operator.reset_password",
            operator=operator,
        )
        return _operator_result(operator)

    async def disable_operator(self, operator_id: UUID, *, actor_id: UUID | None = None) -> PlatformOperatorLifecycleResult:
        operator = await self._operator_by_id(operator_id, for_update=True)
        if operator is None:
            raise PlatformOperatorNotFoundError("PLATFORM_OPERATOR_NOT_FOUND")
        operator.status = "disabled"
        _bump_auth_version(operator)
        await self._revoke_active_tokens(operator.id, _now())
        await self.db.flush()
        await self._audit(
            actor_type="platform_operator" if actor_id else "system",
            actor_id=actor_id,
            action="platform_operator.disable",
            operator=operator,
        )
        return _operator_result(operator)

    async def enable_operator(self, operator_id: UUID, *, actor_id: UUID | None = None) -> PlatformOperatorLifecycleResult:
        operator = await self._operator_by_id(operator_id, for_update=True)
        if operator is None:
            raise PlatformOperatorNotFoundError("PLATFORM_OPERATOR_NOT_FOUND")
        if not operator.password_hash:
            raise PlatformOperatorInvalidStateError("PLATFORM_OPERATOR_PASSWORD_REQUIRED")
        operator.status = "active"
        operator.revoked_at = None
        operator.failed_login_attempts = 0
        operator.locked_until = None
        _bump_auth_version(operator)
        await self.db.flush()
        await self._audit(
            actor_type="platform_operator" if actor_id else "system",
            actor_id=actor_id,
            action="platform_operator.enable",
            operator=operator,
        )
        return _operator_result(operator)

    async def revoke_operator(self, operator_id: UUID, *, actor_id: UUID | None = None) -> PlatformOperatorLifecycleResult:
        operator = await self._operator_by_id(operator_id, for_update=True)
        if operator is None:
            raise PlatformOperatorNotFoundError("PLATFORM_OPERATOR_NOT_FOUND")
        operator.status = "disabled"
        operator.revoked_at = _now()
        _bump_auth_version(operator)
        await self._revoke_active_tokens(operator.id, operator.revoked_at)
        await self.db.flush()
        await self._audit(
            actor_type="platform_operator" if actor_id else "system",
            actor_id=actor_id,
            action="platform_operator.revoke",
            operator=operator,
        )
        return _operator_result(operator)

    async def verify_platform_password(self, *, email: str, password: str) -> PlatformOperator | None:
        """P2 helper for future P3 login wiring; not integrated into auth.py yet."""
        normalized = normalize_operator_email(email)
        operator = await self._operator_by_email(normalized, for_update=True)
        now = _now()
        if operator is None or operator.is_deleted or operator.revoked_at is not None:
            return None
        if operator.status != "active" or not operator.password_hash:
            return None
        if operator.locked_until is not None and operator.locked_until > now:
            return None
        if not verify_password(password, operator.password_hash):
            await self._record_failed_login(operator, now)
            return None

        operator.failed_login_attempts = 0
        operator.locked_until = None
        operator.last_login_at = now
        await self.db.flush()
        return operator

    async def store_recovery_credential(self, *, operator_id: UUID, raw_credential: str) -> None:
        """Pre-provision a recovery credential supplied from an external vault."""
        operator = await self._operator_by_id(operator_id, for_update=True)
        if operator is None:
            raise PlatformOperatorNotFoundError("PLATFORM_OPERATOR_NOT_FOUND")
        now = _now()
        await self.db.execute(
            update(PlatformOperatorRecoveryCredential)
            .where(PlatformOperatorRecoveryCredential.operator_id == operator.id)
            .where(PlatformOperatorRecoveryCredential.status == "active")
            .where(PlatformOperatorRecoveryCredential.is_deleted.is_(False))
            .values(status="revoked", revoked_at=now)
            .execution_options(ignore_tenant=True)
        )
        self.db.add(
            PlatformOperatorRecoveryCredential(
                operator_id=operator.id,
                credential_hash=hash_token(raw_credential.strip(), self.settings),
                status="active",
            )
        )
        await self.db.flush()

    async def break_glass_recover(
        self,
        *,
        raw_credential: str,
        operator_email: str | None = None,
    ) -> PlatformOperatorLifecycleResult:
        if not raw_credential or not raw_credential.strip():
            raise PlatformOperatorRecoveryInvalidError("INVALID_RECOVERY_CREDENTIAL")
        credential_hash = hash_token(raw_credential.strip(), self.settings)
        result = await self.db.execute(
            select(PlatformOperatorRecoveryCredential, PlatformOperator)
            .join(PlatformOperator, PlatformOperatorRecoveryCredential.operator_id == PlatformOperator.id)
            .where(PlatformOperatorRecoveryCredential.credential_hash == credential_hash)
            .where(PlatformOperatorRecoveryCredential.status == "active")
            .where(PlatformOperatorRecoveryCredential.is_deleted.is_(False))
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        row = result.one_or_none()
        if row is None:
            raise PlatformOperatorRecoveryInvalidError("INVALID_RECOVERY_CREDENTIAL")
        credential, operator = row
        if operator_email and operator.email != normalize_operator_email(operator_email):
            raise PlatformOperatorRecoveryInvalidError("INVALID_RECOVERY_CREDENTIAL")
        if not operator.password_hash:
            raise PlatformOperatorRecoveryInvalidError("INVALID_RECOVERY_CREDENTIAL")

        now = _now()
        original_hash = operator.password_hash
        operator.status = "active"
        operator.revoked_at = None
        operator.locked_until = None
        operator.failed_login_attempts = 0
        _bump_auth_version(operator)
        credential.status = "used"
        credential.used_at = now
        raw_reset, expires_at = await self._issue_reset_token(operator, now)
        record_platform_operator_reset_email(
            settings=self.settings,
            to_email=operator.email,
            token=raw_reset,
        )
        await self._audit(
            actor_type="system",
            action="platform_operator.break_glass_recovery",
            operator=operator,
            metadata={"recovery_credential_id": str(credential.id)},
        )
        await self.db.flush()
        if operator.password_hash != original_hash:
            raise RuntimeError("BREAK_GLASS_PASSWORD_MUTATION_REFUSED")
        return _operator_result(operator, expires_at=expires_at)

    async def list_operators(self) -> list[PlatformOperator]:
        result = await self.db.execute(
            select(PlatformOperator)
            .where(PlatformOperator.is_deleted.is_(False))
            .order_by(PlatformOperator.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_operator(self, operator_id: UUID) -> PlatformOperator:
        operator = await self._operator_by_id(operator_id)
        if operator is None:
            raise PlatformOperatorNotFoundError("PLATFORM_OPERATOR_NOT_FOUND")
        return operator

    async def _operator_by_email(self, email: str, *, for_update: bool = False) -> PlatformOperator | None:
        query = select(PlatformOperator).where(PlatformOperator.email == email).where(
            PlatformOperator.is_deleted.is_(False)
        )
        if for_update:
            query = query.with_for_update()
        result = await self.db.execute(query.execution_options(ignore_tenant=True))
        return result.scalar_one_or_none()

    async def _operator_by_id(self, operator_id: UUID, *, for_update: bool = False) -> PlatformOperator | None:
        query = select(PlatformOperator).where(PlatformOperator.id == operator_id).where(
            PlatformOperator.is_deleted.is_(False)
        )
        if for_update:
            query = query.with_for_update()
        result = await self.db.execute(query.execution_options(ignore_tenant=True))
        return result.scalar_one_or_none()

    async def _setup_token_with_operator(
        self, raw_token: str | None
    ) -> tuple[PlatformOperatorSetupToken, PlatformOperator]:
        if raw_token is None or not raw_token.strip():
            raise PlatformOperatorTokenInvalidError(INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN)
        result = await self.db.execute(
            select(PlatformOperatorSetupToken, PlatformOperator)
            .join(PlatformOperator, PlatformOperatorSetupToken.operator_id == PlatformOperator.id)
            .where(PlatformOperatorSetupToken.token_hash == hash_token(raw_token.strip(), self.settings))
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        row = result.one_or_none()
        if row is None:
            raise PlatformOperatorTokenInvalidError(INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN)
        return row

    async def _reset_token_with_operator(
        self, raw_token: str | None
    ) -> tuple[PlatformOperatorResetToken, PlatformOperator]:
        if raw_token is None or not raw_token.strip():
            raise PlatformOperatorTokenInvalidError(INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN)
        result = await self.db.execute(
            select(PlatformOperatorResetToken, PlatformOperator)
            .join(PlatformOperator, PlatformOperatorResetToken.operator_id == PlatformOperator.id)
            .where(PlatformOperatorResetToken.token_hash == hash_token(raw_token.strip(), self.settings))
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        row = result.one_or_none()
        if row is None:
            raise PlatformOperatorTokenInvalidError(INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN)
        return row

    async def _issue_setup_token(self, operator: PlatformOperator, now: datetime) -> tuple[str, datetime]:
        await self._revoke_active_setup_tokens(operator.id, now)
        raw_token = generate_verification_token()
        expires_at = now + SETUP_TOKEN_TTL
        self.db.add(
            PlatformOperatorSetupToken(
                operator_id=operator.id,
                token_hash=hash_token(raw_token, self.settings),
                purpose="setup",
                expires_at=expires_at,
            )
        )
        await self.db.flush()
        return raw_token, expires_at

    async def _issue_reset_token(self, operator: PlatformOperator, now: datetime) -> tuple[str, datetime]:
        await self._revoke_active_reset_tokens(operator.id, now)
        raw_token = generate_verification_token()
        expires_at = now + RESET_TOKEN_TTL
        self.db.add(
            PlatformOperatorResetToken(
                operator_id=operator.id,
                token_hash=hash_token(raw_token, self.settings),
                purpose="reset",
                expires_at=expires_at,
            )
        )
        await self.db.flush()
        return raw_token, expires_at

    async def _revoke_active_tokens(self, operator_id: UUID, now: datetime) -> None:
        await self._revoke_active_setup_tokens(operator_id, now)
        await self._revoke_active_reset_tokens(operator_id, now)

    async def _revoke_active_setup_tokens(self, operator_id: UUID, now: datetime) -> None:
        await self.db.execute(
            update(PlatformOperatorSetupToken)
            .where(PlatformOperatorSetupToken.operator_id == operator_id)
            .where(PlatformOperatorSetupToken.used_at.is_(None))
            .where(PlatformOperatorSetupToken.revoked_at.is_(None))
            .where(PlatformOperatorSetupToken.is_deleted.is_(False))
            .values(revoked_at=now)
            .execution_options(ignore_tenant=True)
        )

    async def _revoke_active_reset_tokens(self, operator_id: UUID, now: datetime) -> None:
        await self.db.execute(
            update(PlatformOperatorResetToken)
            .where(PlatformOperatorResetToken.operator_id == operator_id)
            .where(PlatformOperatorResetToken.used_at.is_(None))
            .where(PlatformOperatorResetToken.revoked_at.is_(None))
            .where(PlatformOperatorResetToken.is_deleted.is_(False))
            .values(revoked_at=now)
            .execution_options(ignore_tenant=True)
        )

    async def _record_failed_login(self, operator: PlatformOperator, now: datetime) -> None:
        operator.failed_login_attempts = int(operator.failed_login_attempts or 0) + 1
        if operator.failed_login_attempts >= LOCKOUT_AFTER_ATTEMPTS:
            operator.locked_until = now + LOCKOUT_TTL
        await self.db.flush()

    @staticmethod
    def _can_issue_reset(operator: PlatformOperator) -> bool:
        return bool(
            operator
            and not operator.is_deleted
            and operator.status == "active"
            and operator.revoked_at is None
            and operator.password_hash
        )

    async def _audit(
        self,
        *,
        actor_type: str,
        action: str,
        operator: PlatformOperator,
        actor_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> None:
        audit_metadata = {
            "operator_id": str(operator.id),
            "operator_email": operator.email,
            "operator_status": operator.status,
            "operator_role": operator.role,
            **(metadata or {}),
        }
        await append_audit_entry(
            self.db,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource=f"platform_operators/{operator.id}",
            audit_metadata=audit_metadata,
        )


__all__ = [
    "EmailDeliveryNotConfiguredError",
    "INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN",
    "NEUTRAL_PLATFORM_OPERATOR_RESET_MESSAGE",
    "NEUTRAL_PLATFORM_OPERATOR_SETUP_MESSAGE",
    "PlatformOperatorExistsError",
    "PlatformOperatorInvalidStateError",
    "PlatformOperatorLifecycleResult",
    "PlatformOperatorNotFoundError",
    "PlatformOperatorRecoveryInvalidError",
    "PlatformOperatorResetRequestResult",
    "PlatformOperatorService",
    "PlatformOperatorTokenInvalidError",
]
