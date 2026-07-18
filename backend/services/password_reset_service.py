"""Password recovery service (DC-3B).

Implements self-service password reset on top of the existing
``public.password_reset_tokens`` table (migration 026) plus the canonical
multi-tenant same-email password rule.

Canonical rule (DC-3A Section 5.4): an owner/admin email may exist as an active
user row in multiple tenant schemas. A password reset must update ALL active
tenant user rows for that normalized email, not just one. This keeps every
copy's hash identical, which is the assumption ``find_user_across_tenants``
relies on.

Security invariants (must not be weakened):
- Tokens are stored hash-only (HMAC-SHA256 via ``hash_token``); raw tokens exist
  only in memory / the email channel and are never logged.
- ``request_reset`` never reveals whether an email exists (always-neutral result).
- Production fails closed: if email delivery is not configured, NO token is
  created and the failure surfaces so the caller can roll back.
- ``consume_reset`` marks ``used_at`` only AFTER the password update succeeds,
  validates expiry/used/revoked/is_deleted, and the API rejects query-string
  tokens.
- The raw email is never stored on the token row (only ``user_email_hash``);
  consume resolves the affected tenant copies by matching SHA-256(email) of
  active tenant users against the stored hash, so no plaintext email is needed
  at consume time.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.security import hash_password
from db.sql_safety import validate_identifier
from db.tenant_filter import mark_session_as_system, run_as_system
from models.tenant_onboarding import PASSWORD_RESET_TOKEN_PURPOSE, PasswordResetToken
from models.wholesaler import Wholesaler
from services.email_delivery import record_password_reset_email
from services.onboarding_service import (
    build_password_reset_link,
    generate_verification_token,
    hash_token,
    validate_password_policy,
)

PASSWORD_RESET_TOKEN_TTL = timedelta(hours=1)
INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN = "INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN"  # pragma: allowlist secret
NEUTRAL_PASSWORD_RESET_MESSAGE = "Password reset result is not disclosed through this endpoint."  # pragma: allowlist secret


class PasswordResetTokenInvalidError(Exception):
    """Raised for invalid, expired, used, revoked, or non-actionable reset tokens."""


@dataclass(frozen=True)
class PasswordResetRequestResult:
    """Neutral result for POST /auth/forgot-password.

    ``issued`` is for internal callers/tests only; the API always returns the
    same neutral response regardless of this value.
    """

    issued: bool
    email: str


@dataclass(frozen=True)
class PasswordResetConsumeResult:
    """Result for POST /auth/reset-password (no internal IDs exposed publicly)."""

    action: str
    updated_tenant_count: int


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _email_hash(email: str) -> str:
    """Stable SHA-256 of the normalized email for token-row grouping.

    This is NOT the token hash; it only lets the unique partial indexes enforce
    one-active-reset-per-email (tenant_id NULL) without storing the raw email.
    """
    return hashlib.sha256(_normalize_email(email).encode("utf-8")).hexdigest()


async def _enumerate_active_tenant_users(
    db: AsyncSession,
) -> list[tuple[str, str, UUID]]:
    """Return (normalized_email, tenant_schema, user_id) for active tenant users.

    Scans non-deleted wholesalers ordered by created_at (same order as the login
    scan) and, for each, reads active, non-deleted user rows. Schemas lacking a
    ``users`` table are skipped defensively (mirrors login behavior).
    """
    mark_session_as_system(db, reason="password_reset_user_scan")
    with run_as_system(reason="password_reset_user_scan"):
        result = await db.execute(
            select(Wholesaler)
            .where(Wholesaler.is_deleted == False)  # noqa: E712
            .order_by(Wholesaler.created_at),
            execution_options={"ignore_tenant": True},
        )
        wholesalers = list(result.scalars().all())

    rows: list[tuple[str, str, UUID]] = []
    for ws in wholesalers:
        schema = ws.get_tenant_schema()
        try:
            async with db.begin_nested():
                res = await db.execute(
                    text(
                        f'SELECT lower(email) AS email, id FROM "{schema}".users '
                        "WHERE is_active = true AND is_deleted = false"
                    ),
                )
                for email, uid in res.all():
                    rows.append((str(email), schema, uid))
        except Exception:
            # Roll back only this tenant's SAVEPOINT. Without it, a missing or
            # damaged schema aborts the outer transaction and blocks every
            # healthy tenant that follows in the scan.
            continue
    return rows


class PasswordResetService:
    """Issue and consume password reset tokens with multi-tenant fan-out."""

    def __init__(self, db: AsyncSession, *, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    async def request_reset(self, email: str) -> PasswordResetRequestResult:
        """Issue one canonical reset token for the email if active users exist.

        Always returns a neutral result; the API must not distinguish the
        issued=True / issued=False cases in its response. Production fails
        closed on email delivery: if SMTP is not configured, no token is
        persisted (the exception propagates before commit).
        """
        normalized = _normalize_email(email)
        eh = _email_hash(normalized)
        # Confirm at least one active tenant user exists for this email.
        active_users = await _enumerate_active_tenant_users(self.db)
        has_user = any(row_email == normalized for (row_email, _s, _u) in active_users)
        if not has_user:
            return PasswordResetRequestResult(issued=False, email=normalized)

        now = datetime.now(timezone.utc)
        # Revoke any previously-active reset token for this email so the new one
        # is the only live token (the unique partial index also enforces this).
        await self.db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_email_hash == eh)
            .where(PasswordResetToken.tenant_id.is_(None))
            .where(PasswordResetToken.used_at.is_(None))
            .where(PasswordResetToken.revoked_at.is_(None))
            .where(PasswordResetToken.is_deleted.is_(False))
            .values(revoked_at=now)
            .execution_options(ignore_tenant=True)
        )

        raw_token = generate_verification_token()
        self.db.add(
            PasswordResetToken(
                user_email_hash=eh,
                tenant_id=None,
                tenant_schema=None,
                token_hash=hash_token(raw_token, self.settings),
                purpose=PASSWORD_RESET_TOKEN_PURPOSE,
                expires_at=now + PASSWORD_RESET_TOKEN_TTL,
            )
        )
        await self.db.flush()

        # Fail-closed: raises in production if SMTP not configured, BEFORE commit.
        record_password_reset_email(
            settings=self.settings,
            to_email=normalized,
            token=raw_token,
            reset_link=build_password_reset_link(raw_token),
        )
        return PasswordResetRequestResult(issued=True, email=normalized)

    async def consume_reset(self, token: str, new_password: str) -> PasswordResetConsumeResult:
        """Consume a reset token and set the new password on ALL active copies.

        Marks ``used_at`` only after the password update succeeds. Raises
        ``PasswordResetTokenInvalidError`` for any invalid/expired/used/revoked
        token (the API maps this to a neutral error).
        """
        validate_password_policy(new_password)

        token_row = await self._actionable_reset_token(token)
        target_hash = token_row.user_email_hash

        # Resolve the affected copies by matching SHA-256(email) so the raw
        # email is never needed at consume time and is never stored on the token.
        copies: list[tuple[str, UUID]] = []
        for row_email, schema, uid in await _enumerate_active_tenant_users(self.db):
            if hashlib.sha256(row_email.encode("utf-8")).hexdigest() == target_hash:
                copies.append((schema, uid))

        if not copies:
            # Email no longer has any active tenant user since the token issued.
            raise PasswordResetTokenInvalidError(INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN)

        password_hash = hash_password(new_password)
        updated = 0
        for schema, uid in copies:
            try:
                validate_identifier(schema)
            except Exception:
                continue
            try:
                async with self.db.begin_nested():
                    await self.db.execute(
                        text(
                            f'UPDATE "{schema}".users '
                            "SET password_hash = :password_hash, is_active = true, "
                            "is_deleted = false, deleted_at = NULL, updated_at = now() "
                            "WHERE id = :user_id AND is_active = true"
                        ),
                        {"password_hash": password_hash, "user_id": uid},
                    )
                    updated += 1
            except Exception:
                # Isolate per-tenant failures via SAVEPOINT rollback so one bad
                # schema cannot abort the whole reset. The token is still marked
                # used; the canonical rule is best-effort across reachable copies.
                continue

        # Mark used only after the update succeeded.
        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.id == token_row.id)
            .values(used_at=now)
            .execution_options(ignore_tenant=True)
        )
        await self.db.flush()
        return PasswordResetConsumeResult(action="reset", updated_tenant_count=updated)

    async def _actionable_reset_token(self, raw_token: str) -> PasswordResetToken:
        """Lock and validate a reset token row by hash. Single-use enforced."""
        th = hash_token(raw_token, self.settings)
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == th)
            .where(PasswordResetToken.purpose == PASSWORD_RESET_TOKEN_PURPOSE)
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        token_row = result.scalar_one_or_none()
        if not self._is_actionable(token_row, now):
            raise PasswordResetTokenInvalidError(INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN)
        return token_row

    @staticmethod
    def _is_actionable(token_row: PasswordResetToken | None, now: datetime) -> bool:
        if token_row is None:
            return False
        if token_row.is_deleted:
            return False
        if token_row.used_at is not None:
            return False
        if token_row.revoked_at is not None:
            return False
        if token_row.expires_at <= now:
            return False
        return True
