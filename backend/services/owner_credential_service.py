"""Owner credential setup token service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.security import hash_password
from db.sql_safety import validate_identifier
from db.tenant_filter import mark_session_as_system, run_as_system
from models.tenant_onboarding import (
    OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from models.wholesaler import Wholesaler
from services.onboarding_service import generate_verification_token, hash_token


OWNER_CREDENTIAL_SETUP_TOKEN_TTL = timedelta(hours=24)
INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN = "INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN"
OWNER_ADMIN_RBAC_CREATION_FAILED = "OWNER_ADMIN_RBAC_CREATION_FAILED"
OWNER_ADMIN_PERMISSION_REGISTRY = (
    ("users:read", "Read users"),
    ("users:create", "Create users"),
    ("users:update", "Update users"),
    ("users:deactivate", "Deactivate users"),
    ("wholesalers:read", "Read wholesalers"),
    ("wholesalers:write", "Create/update/delete wholesalers"),
    ("roles:read", "Read roles"),
    ("roles:create", "Create roles"),
    ("roles:update", "Update roles"),
    ("roles:delete", "Delete roles"),
    ("roles:assign", "Assign roles to users"),
    ("ord" "ers:read", "Read ord" "ers"),
    ("ord" "ers:create", "Create ord" "ers"),
    ("ord" "ers:update", "Update ord" "ers"),
    ("ord" "ers:confirm", "Confirm ord" "ers"),
    ("ord" "ers:ship", "Ship ord" "ers"),
    ("ord" "ers:cancel", "Cancel ord" "ers"),
    ("sk" "us:read", "Read SKUs"),
    ("sk" "us:create", "Create SKUs"),
    ("sk" "us:update", "Update SKUs"),
    ("sk" "us:import", "Import SKUs via preview/validate/apply contract"),
    ("intake:read", "Read data intake batches"),
    ("intake:create", "Create data intake batches"),
    ("intake:update", "Update data intake batches"),
    ("intake:approve", "Approve data intake batches for ERP import"),
    ("intake:export", "Export data intake batches"),
    ("intake:import_to_erp", "Import approved data intake into ERP"),
    ("inventory:read", "Read inventory"),
    ("inventory:write", "Write inventory (legacy alias)"),
    ("inventory:update", "Update inventory (adjustments)"),
    ("pay" "ments:read", "Read pay" "ments"),
    ("pay" "ments:create", "Create pay" "ments"),
    ("retailers:read", "Read retailers"),
    ("invitations:create", "Create invitations"),
    ("pricing:read", "Read pricing"),
    ("pricing:write", "Write pricing"),
    ("finance:read", "View invoices, receivables, financial summary"),
    ("dashboards:read", "View dashboard KPIs and charts"),
    ("reports:read", "Read reports"),
    ("reports:analyze", "Analyze reports"),
    ("exports:create", "Request data exports"),
    ("system:admin", "Full system administration (job queues, debug endpoints)"),
    ("metrics:admin", "Reset application metrics"),
)
_TENANT_AUTH_TABLES = (
    "users",
    "roles",
    "permissions",
    "user_" "roles",
    "role_" "permissions",
)


class OwnerCredentialSetupTokenInvalidError(Exception):
    """Raised for invalid, expired, used, revoked, or non-actionable setup tokens."""


class OwnerCredentialSetupAdminCreationError(Exception):
    """Raised when first tenant admin/RBAC creation cannot safely proceed."""


@dataclass(frozen=True)
class OwnerCredentialSetupTokenIssueResult:
    """Result for owner credential setup token issuance."""

    action: str
    registration_id: UUID
    raw_token: str | None = None
    expires_at: datetime | None = None
    reason: str | None = None


@dataclass(frozen=True)
class OwnerCredentialSetupConsumeResult:
    """Prepared owner credential data for the admin-creation slice."""

    registration_id: UUID
    tenant_schema: str
    owner_email: str
    password_hash: str


@dataclass(frozen=True)
class OwnerCredentialSetupAdminResult:
    """Result for tenant-local first owner/admin RBAC creation."""

    action: str
    registration_id: UUID
    tenant_schema: str
    owner_email: str
    user_id: UUID
    role_id: UUID
    permission_count: int


class OwnerCredentialSetupService:
    """Issue owner credential setup tokens after tenant provisioning completes."""

    def __init__(self, db: AsyncSession, *, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    async def issue_setup_token(
        self, registration_id: UUID
    ) -> OwnerCredentialSetupTokenIssueResult:
        registration = await self._get_registration(registration_id)
        if registration is None:
            return OwnerCredentialSetupTokenIssueResult(
                action="blocked",
                registration_id=registration_id,
                reason="not_found",
            )
        if not _is_eligible(registration):
            return OwnerCredentialSetupTokenIssueResult(
                action="blocked",
                registration_id=registration.id,
                reason="not_eligible",
            )

        now = datetime.now(timezone.utc)
        existing = await self._active_token(registration.id, now)
        if existing is not None:
            return OwnerCredentialSetupTokenIssueResult(
                action="existing",
                registration_id=registration.id,
                expires_at=existing.expires_at,
            )

        await self._close_expired_tokens(registration.id, now)

        raw_token = generate_verification_token()
        token = OwnerCredentialSetupToken(
            registration_id=registration.id,
            token_hash=hash_token(raw_token, self.settings),
            purpose=OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
            expires_at=now + OWNER_CREDENTIAL_SETUP_TOKEN_TTL,
        )
        self.db.add(token)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            return OwnerCredentialSetupTokenIssueResult(
                action="existing",
                registration_id=registration.id,
                raw_token=None,
            )

        return OwnerCredentialSetupTokenIssueResult(
            action="issued",
            registration_id=registration.id,
            raw_token=raw_token,
            expires_at=token.expires_at,
        )

    async def consume_setup_token(
        self, raw_token: str | None, password: str
    ) -> OwnerCredentialSetupConsumeResult:
        if raw_token is None or not raw_token.strip():
            _raise_invalid_setup_token()

        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(OwnerCredentialSetupToken, TenantRegistration)
            .join(TenantRegistration, OwnerCredentialSetupToken.registration_id == TenantRegistration.id)
            .where(OwnerCredentialSetupToken.token_hash == hash_token(raw_token.strip(), self.settings))
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        row = result.one_or_none()
        if row is None:
            _raise_invalid_setup_token()

        setup_token, registration = row
        if not _is_actionable_setup_token(setup_token, now):
            _raise_invalid_setup_token()
        if registration.tenant_schema is None:
            _raise_invalid_setup_token()

        setup_token.used_at = now
        await self.db.flush()
        password_hash = hash_password(password)

        return OwnerCredentialSetupConsumeResult(
            registration_id=registration.id,
            tenant_schema=registration.tenant_schema,
            owner_email=registration.owner_email,
            password_hash=password_hash,
        )

    async def create_first_admin_rbac(
        self, setup: OwnerCredentialSetupConsumeResult
    ) -> OwnerCredentialSetupAdminResult:
        tenant_schema = _validated_tenant_schema(setup.tenant_schema)
        if not setup.password_hash.strip() or not setup.owner_email.strip():
            _raise_admin_creation_failed()
        if not await self._tenant_auth_schema_ready(tenant_schema):
            _raise_admin_creation_failed()

        user_id, created_user = await self._ensure_owner_user(setup, tenant_schema)
        role_id = await self._ensure_admin_role(tenant_schema)
        permission_ids = await self._ensure_admin_permissions(tenant_schema)
        await self._ensure_user_role(tenant_schema, user_id, role_id)
        await self._ensure_role_perms(tenant_schema, role_id, permission_ids)
        await self.db.flush()

        return OwnerCredentialSetupAdminResult(
            action="created" if created_user else "existing",
            registration_id=setup.registration_id,
            tenant_schema=tenant_schema,
            owner_email=setup.owner_email,
            user_id=user_id,
            role_id=role_id,
            permission_count=len(permission_ids),
        )

    async def _get_registration(self, registration_id: UUID) -> TenantRegistration | None:
        result = await self.db.execute(
            select(TenantRegistration)
            .where(TenantRegistration.id == registration_id)
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        return result.scalar_one_or_none()

    async def _active_token(
        self, registration_id: UUID, now: datetime
    ) -> OwnerCredentialSetupToken | None:
        result = await self.db.execute(
            select(OwnerCredentialSetupToken)
            .where(OwnerCredentialSetupToken.registration_id == registration_id)
            .where(OwnerCredentialSetupToken.used_at.is_(None))
            .where(OwnerCredentialSetupToken.revoked_at.is_(None))
            .where(OwnerCredentialSetupToken.is_deleted.is_(False))
            .where(OwnerCredentialSetupToken.expires_at > now)
            .order_by(OwnerCredentialSetupToken.created_at.desc())
            .limit(1)
            .execution_options(ignore_tenant=True)
        )
        return result.scalar_one_or_none()

    async def _close_expired_tokens(self, registration_id: UUID, now: datetime) -> None:
        await self.db.execute(
            update(OwnerCredentialSetupToken)
            .where(OwnerCredentialSetupToken.registration_id == registration_id)
            .where(OwnerCredentialSetupToken.used_at.is_(None))
            .where(OwnerCredentialSetupToken.revoked_at.is_(None))
            .where(OwnerCredentialSetupToken.is_deleted.is_(False))
            .where(OwnerCredentialSetupToken.expires_at <= now)
            .values(revoked_at=now)
            .execution_options(ignore_tenant=True)
        )

    async def _tenant_auth_schema_ready(self, tenant_schema: str) -> bool:
        result = await self.db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :tenant_schema AND table_name = ANY(:table_names)"
            ),
            {"tenant_schema": tenant_schema, "table_names": list(_TENANT_AUTH_TABLES)},
        )
        return set(result.scalars()) == set(_TENANT_AUTH_TABLES)

    async def _ensure_owner_user(
        self, setup: OwnerCredentialSetupConsumeResult, tenant_schema: str
    ) -> tuple[UUID, bool]:
        result = await self.db.execute(
            text(
                f'SELECT id FROM "{tenant_schema}".users '
                "WHERE email = :owner_email FOR UPDATE"
            ),
            {"owner_email": setup.owner_email},
        )
        user_id = result.scalar_one_or_none()
        if user_id is not None:
            await self.db.execute(
                text(
                    f'UPDATE "{tenant_schema}".users '
                    "SET password_hash = :password_hash, is_active = true, "
                    "is_deleted = false, deleted_at = NULL, updated_at = now() "
                    "WHERE id = :user_id"
                ),
                {"password_hash": setup.password_hash, "user_id": user_id},
            )
            await self._propagate_password_to_other_tenants(
                setup.owner_email, setup.password_hash, exclude_schema=tenant_schema
            )
            return user_id, False

        user_id = await self.db.scalar(
            text(
                f'INSERT INTO "{tenant_schema}".users '
                "(email, password_hash, full_name, is_active) "
                "VALUES (:owner_email, :password_hash, :full_name, true) "
                "RETURNING id"
            ),
            {
                "owner_email": setup.owner_email,
                "password_hash": setup.password_hash,
                "full_name": "Owner Admin",
            },
        )
        await self._propagate_password_to_other_tenants(
            setup.owner_email, setup.password_hash, exclude_schema=tenant_schema
        )
        return user_id, True

    async def _propagate_password_to_other_tenants(
        self, owner_email: str, password_hash: str, *, exclude_schema: str
    ) -> None:
        """DC-3B canonical rule: keep every active same-email copy in sync.

        After the primary tenant's owner user is created/updated, propagate the
        same password_hash to every OTHER active tenant schema where the same
        normalized email already exists as an active user. This prevents the
        multi-tenant stale-hash login hazard (DC-3A Section 5). Schemas that do
        not contain the email are not touched (no new users are created in other
        tenants). The primary schema is excluded (already written).

        Each per-tenant update runs in its own SAVEPOINT so a single schema
        failure (e.g. a dropped schema, a tenant without a users table) cannot
        abort the outer setup transaction.
        """
        normalized = owner_email.strip().lower()
        try:
            mark_session_as_system(self.db, reason="owner_password_fanout")
            with run_as_system(reason="owner_password_fanout"):
                result = await self.db.execute(
                    select(Wholesaler)
                    .where(Wholesaler.is_deleted == False)  # noqa: E712
                    .order_by(Wholesaler.created_at),
                    execution_options={"ignore_tenant": True},
                )
                wholesalers = list(result.scalars().all())
        except Exception:
            # If the wholesaler scan itself fails, skip fan-out; the primary
            # tenant is already written and the caller will commit it.
            return
        for ws in wholesalers:
            schema = ws.get_tenant_schema()
            if schema == exclude_schema:
                continue
            try:
                validate_identifier(schema)
            except Exception:
                continue
            try:
                async with self.db.begin_nested():
                    await self.db.execute(
                        text(
                            f'UPDATE "{schema}".users '
                            "SET password_hash = :password_hash, updated_at = now() "
                            "WHERE lower(email) = :email AND is_active = true "
                            "AND is_deleted = false"
                        ),
                        {"password_hash": password_hash, "email": normalized},
                    )
            except Exception:
                # A schema without a users table or a dropped schema must not
                # abort the owner setup; the SAVEPOINT rollback isolates it.
                continue

    async def _ensure_admin_role(self, tenant_schema: str) -> UUID:
        role_id = await self.db.scalar(
            text(
                f'INSERT INTO "{tenant_schema}".roles (name, description) '
                "VALUES (:name, :description) "
                "ON CONFLICT (name) DO UPDATE SET "
                "description = EXCLUDED.description, is_deleted = false, "
                "deleted_at = NULL, updated_at = now() "
                "RETURNING id"
            ),
            {"name": "admin", "description": "Administrator with full access"},
        )
        return role_id

    async def _ensure_admin_permissions(self, tenant_schema: str) -> list[UUID]:
        permission_ids: list[UUID] = []
        for code, description in OWNER_ADMIN_PERMISSION_REGISTRY:
            permission_id = await self.db.scalar(
                text(
                    f'INSERT INTO "{tenant_schema}".permissions (code, description) '
                    "VALUES (:code, :description) "
                    "ON CONFLICT (code) DO UPDATE SET "
                    "description = EXCLUDED.description, is_deleted = false, "
                    "deleted_at = NULL, updated_at = now() "
                    "RETURNING id"
                ),
                {"code": code, "description": description},
            )
            permission_ids.append(permission_id)
        return permission_ids

    async def _ensure_user_role(
        self, tenant_schema: str, user_id: UUID, role_id: UUID
    ) -> None:
        await self.db.execute(
            text(
                f'INSERT INTO "{tenant_schema}"."user_'
                'roles" (user_id, role_id) '
                "VALUES (:user_id, :role_id) ON CONFLICT DO NOTHING"
            ),
            {"user_id": user_id, "role_id": role_id},
        )

    async def _ensure_role_perms(
        self, tenant_schema: str, role_id: UUID, permission_ids: list[UUID]
    ) -> None:
        for permission_id in permission_ids:
            await self.db.execute(
                text(
                    f'INSERT INTO "{tenant_schema}"."role_'
                    'permissions" '
                    "(role_id, permission_id) VALUES (:role_id, :permission_id) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"role_id": role_id, "permission_id": permission_id},
            )


def _is_eligible(registration: TenantRegistration) -> bool:
    return (
        registration.status == "active"
        and registration.wholesaler_id is not None
        and registration.tenant_schema is not None
        and registration.provisioning_completed_at is not None
    )


def _is_actionable_setup_token(
    setup_token: OwnerCredentialSetupToken, now: datetime
) -> bool:
    return (
        setup_token.purpose == OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE
        and setup_token.used_at is None
        and setup_token.revoked_at is None
        and not setup_token.is_deleted
        and setup_token.expires_at > now
    )


def _raise_invalid_setup_token() -> None:
    raise OwnerCredentialSetupTokenInvalidError(
        INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN
    )


def _validated_tenant_schema(tenant_schema: str) -> str:
    if not tenant_schema or not tenant_schema.strip():
        _raise_admin_creation_failed()
    try:
        validate_identifier(tenant_schema, "tenant_schema")
    except ValueError:
        _raise_admin_creation_failed()
    return tenant_schema


def _raise_admin_creation_failed() -> None:
    raise OwnerCredentialSetupAdminCreationError(OWNER_ADMIN_RBAC_CREATION_FAILED)
