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
- H2-B-R1: a per-tenant scan failure is never silently converted into a
  definitive "account does not exist" (or "token invalid") outcome. Scan
  health travels through sanitized, counter-only types
  (``TenantUserScanResult`` / ``PasswordResetScanIncompleteError``) so the
  API can emit exactly one internal event while the public envelope stays
  neutral; no email/schema/SQL/token/credential ever reaches a log.
- Production fails closed: if email delivery is not configured, NO token is
  created and the failure surfaces so the caller can roll back.
- ``consume_reset`` marks ``used_at`` only AFTER every discovered active copy
  updated exactly one row; the fan-out is all-or-nothing (H2-B-R2): any scan
  failure fails closed before the first update, and any apply failure rolls
  back the whole outer transaction via the sanitized
  ``PasswordResetApplyFailedError`` — no best-effort partial resets;
  the API rejects query-string
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


class PasswordResetScanIncompleteError(Exception):
    """The cross-tenant user scan could not complete AND no active user for the
    requested email was found in any reachable tenant.

    H2-B-R1: without this, a per-tenant schema/query failure was silently
    converted into a definitive ``issued=False`` ("account does not exist")
    answer with zero observability. The error is sanitized by construction:
    it carries only integer counters and never embeds the email, tenant
    schema names, SQL text, tokens, or credentials (raw driver errors can
    leak the schema name, so the triggering exception is not chained).
    """

    def __init__(self, *, failed_schema_count: int, scanned_schema_count: int) -> None:
        self.failed_schema_count = failed_schema_count
        self.scanned_schema_count = scanned_schema_count
        super().__init__(
            "password reset tenant scan incomplete: "
            f"{failed_schema_count} of {scanned_schema_count} tenant scans failed"
        )


class PasswordResetApplyFailedError(Exception):
    """The all-or-nothing password fan-out failed for at least one copy.

    H2-B-R2: partial application is forbidden — tenant copies of the same
    email must never end up with divergent password hashes, so ANY
    validation/update failure during the fan-out aborts the whole consume
    (the caller rolls back the outer transaction, so no copy retains the
    new password, and the token is never marked used). Sanitized by
    construction: integer counters only, never schema names, SQL text,
    emails, tokens, or credentials; the triggering exception is not chained.
    """

    def __init__(self, *, updated_count: int, remaining_copy_count: int) -> None:
        self.updated_count = updated_count
        self.remaining_copy_count = remaining_copy_count
        super().__init__(
            "password reset all-or-nothing apply aborted: "
            f"{updated_count} copy update(s) staged, {remaining_copy_count} remaining"
        )


@dataclass(frozen=True)
class TenantUserScanResult:
    """Rows reachable from active tenant schemas plus sanitized scan health.

    ``failed_schema_count`` counts per-tenant scans whose SAVEPOINT rolled
    back. It deliberately contains no schema names / SQL / emails so it is
    safe to log and to expose through metrics.
    """

    rows: list[tuple[str, str, UUID]]
    scanned_schema_count: int
    failed_schema_count: int


@dataclass(frozen=True)
class PasswordResetRequestResult:
    """Neutral result for POST /auth/forgot-password.

    ``issued`` is for internal callers/tests only; the API always returns the
    same neutral response regardless of this value. ``scan_failed_schema_count``
    is likewise internal-only telemetry (0 = the scan completed for every
    non-deleted wholesaler schema); it never changes the public response.
    """

    issued: bool
    email: str
    scan_failed_schema_count: int = 0


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
) -> TenantUserScanResult:
    """Scan active tenant schemas for (normalized_email, schema, user_id) rows.

    Scans non-deleted wholesalers ordered by created_at (same order as the login
    scan) and, for each, reads active, non-deleted user rows. Each tenant query
    runs inside its own SAVEPOINT: a schema lacking a ``users`` table (or any
    per-tenant query failure) rolls back only that savepoint and MUST NOT abort
    the outer transaction, which would block every healthy tenant that follows.

    H2-B-R1: the failure is no longer silent. Failed savepoints are counted in
    the returned result so callers can distinguish "scanned everything, the
    account does not exist" from "could not scan every tenant, absence is NOT
    proven". The count is aggregate-only — never which schema or why.
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
    failed_schema_count = 0
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
            # Roll back only this tenant's SAVEPOINT (isolation retained) and
            # record the failure in the aggregate count. The caller decides
            # how to surface it; this function never converts the failure
            # into "the account does not exist".
            failed_schema_count += 1
            continue
    return TenantUserScanResult(
        rows=rows,
        scanned_schema_count=len(wholesalers),
        failed_schema_count=failed_schema_count,
    )


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
        scan = await _enumerate_active_tenant_users(self.db)
        has_user = any(row_email == normalized for (row_email, _s, _u) in scan.rows)
        if not has_user:
            if scan.failed_schema_count:
                # H2-B-R1: absence is NOT proven when tenant scans failed.
                # Surface a sanitized typed error instead of silently
                # converting the scan failure into "account does not exist";
                # the API layer emits exactly one internal event and still
                # answers with the neutral envelope.
                raise PasswordResetScanIncompleteError(
                    failed_schema_count=scan.failed_schema_count,
                    scanned_schema_count=scan.scanned_schema_count,
                )
            return PasswordResetRequestResult(
                issued=False, email=normalized, scan_failed_schema_count=0
            )

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
            reset_link=build_password_reset_link(raw_token, self.settings),
        )
        return PasswordResetRequestResult(
            issued=True,
            email=normalized,
            scan_failed_schema_count=scan.failed_schema_count,
        )

    async def consume_reset(self, token: str, new_password: str) -> PasswordResetConsumeResult:
        """Consume a reset token and set the new password on ALL active copies.

        H2-B-R2 atomicity contract:
        - fails closed BEFORE any password update when any tenant scan failed
          (``PasswordResetScanIncompleteError``), even if reachable copies
          were found;
        - the fan-out is all-or-nothing: every discovered active copy must
          update exactly one row (affected-row count verified); any failure
          raises the sanitized ``PasswordResetApplyFailedError`` and the API
          rolls back the outer transaction so NO copy keeps the new password;
        - ``used_at`` is set only after every copy succeeded, so a failed
          consume leaves the token actionable for a retry after repair.

        Raises ``PasswordResetTokenInvalidError`` for any invalid/expired/
        used/revoked token (the API maps this to a neutral error).
        """
        validate_password_policy(new_password)

        token_row = await self._actionable_reset_token(token)
        target_hash = token_row.user_email_hash

        # Resolve the affected copies by matching SHA-256(email) so the raw
        # email is never needed at consume time and is never stored on the token.
        scan = await _enumerate_active_tenant_users(self.db)

        # H2-B-R2: fail closed BEFORE any password update whenever ANY tenant
        # scan failed — regardless of whether reachable copies were found. On
        # an incomplete scan the full copy set is unknowable, and a partial
        # fan-out would leave tenant copies with divergent password hashes,
        # the exact invariant the canonical multi-tenant rule protects.
        if scan.failed_schema_count:
            raise PasswordResetScanIncompleteError(
                failed_schema_count=scan.failed_schema_count,
                scanned_schema_count=scan.scanned_schema_count,
            )

        copies: list[tuple[str, UUID]] = []
        for row_email, schema, uid in scan.rows:
            if hashlib.sha256(row_email.encode("utf-8")).hexdigest() == target_hash:
                copies.append((schema, uid))

        if not copies:
            # Email no longer has any active tenant user since the token issued.
            raise PasswordResetTokenInvalidError(INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN)

        password_hash = hash_password(new_password)
        # All-or-nothing fan-out (H2-B-R2): every discovered active copy must
        # update exactly one row. Any validation/update failure raises the
        # sanitized typed error; the API layer then rolls back the OUTER
        # transaction (undoing every prior copy update) and the token is
        # never marked used. There is deliberately NO best-effort path and
        # NO per-copy SAVEPOINT isolation here — failure must abort the
        # whole consume, not be skipped past.
        updated = 0
        for schema, uid in copies:
            try:
                validate_identifier(schema)
            except Exception:
                raise PasswordResetApplyFailedError(
                    updated_count=updated,
                    remaining_copy_count=len(copies) - updated,
                ) from None
            try:
                result = await self.db.execute(
                    text(
                        f'UPDATE "{schema}".users '
                        "SET password_hash = :password_hash, is_active = true, "
                        "is_deleted = false, deleted_at = NULL, updated_at = now() "
                        "WHERE id = :user_id AND is_active = true"
                    ),
                    {"password_hash": password_hash, "user_id": uid},
                )
            except Exception:
                raise PasswordResetApplyFailedError(
                    updated_count=updated,
                    remaining_copy_count=len(copies) - updated,
                ) from None
            if result.rowcount != 1:
                raise PasswordResetApplyFailedError(
                    updated_count=updated,
                    remaining_copy_count=len(copies) - updated,
                )
            updated += 1

        # Mark used only after EVERY copy updated exactly one row.
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
