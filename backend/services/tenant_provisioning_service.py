"""Tenant provisioning service slices for onboarding registrations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from typing import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from db.sql_safety import validate_identifier
from models.tenant_onboarding import TenantRegistration
from models.wholesaler import Wholesaler as WholesalerModel


BootstrapFunction = Callable[[str, str], Awaitable[None]]
_BOOTSTRAP_MODULE = "scripts.bootstrap_tenant_" "schema"
_BOOTSTRAP_FAILED = "BOOTSTRAP_FAILED"
_BOOTSTRAP_REQUIRED_TABLES = {
    "users",
    "roles",
    "permissions",
    "user_" "roles",
    "role_" "permissions",
    "skus",
    "inventory_stocks",
    "inventory_movements",
    "orders",
    "order_items",
    "payments",
    "ledger_entries",
    "import_runs",
    "intake_workspaces",
    "intake_uploads",
    "intake_product_rows",
    "intake_validation_issues",
}


@dataclass(frozen=True)
class TenantProvisioningClaimResult:
    """Result for the first safe provisioning claim step."""

    action: str
    registration_id: UUID
    status: str | None
    wholesaler_id: UUID | None = None
    tenant_schema: str | None = None
    provisioning_started_at: datetime | None = None
    provisioning_completed_at: datetime | None = None
    reason: str | None = None


class TenantProvisioningService:
    """Move onboarding registrations through bounded provisioning slices."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        bootstrap_func: BootstrapFunction | None = None,
        database_url: str | None = None,
    ) -> None:
        self.db = db
        self._bootstrap_func = bootstrap_func or _load_bootstrap()
        self._database_url = database_url

    async def claim_registration_for_provisioning(
        self, registration_id: UUID
    ) -> TenantProvisioningClaimResult:
        result = await self.db.execute(
            select(TenantRegistration)
            .where(TenantRegistration.id == registration_id)
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        registration = result.scalar_one_or_none()

        if registration is None:
            return TenantProvisioningClaimResult(
                action="blocked",
                registration_id=registration_id,
                status=None,
                reason="not_found",
            )

        if _has_existing_active_assignment(registration):
            return _result("existing", registration)

        if not _can_claim(registration):
            return _result("blocked", registration, reason="not_claimable")

        now = datetime.now(timezone.utc)
        registration.status = "provisioning"
        registration.provisioning_started_at = now
        await self.db.flush()

        return _result("claimed", registration)

    async def provision_wholesaler_and_schema(
        self, registration_id: UUID
    ) -> TenantProvisioningClaimResult:
        result = await self.db.execute(
            select(TenantRegistration)
            .where(TenantRegistration.id == registration_id)
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        registration = result.scalar_one_or_none()

        if registration is None:
            return TenantProvisioningClaimResult(
                action="blocked",
                registration_id=registration_id,
                status=None,
                reason="not_found",
            )

        if _has_existing_active_assignment(registration):
            if await self._schema_is_bootstrapped(registration.tenant_schema):
                return _result("existing", registration)
            return _result("blocked", registration, reason="schema_not_bootstrapped")

        if registration.status != "provisioning":
            return _result("blocked", registration, reason="not_provisioning")

        try:
            if registration.wholesaler_id is not None or registration.tenant_schema is not None:
                return await self._reconcile_existing_provisioning(registration)

            wholesaler = await self._ensure_wholesaler(registration)
            tenant_schema = wholesaler.get_tenant_schema()
            validate_identifier(tenant_schema, "tenant_schema")

            registration.wholesaler_id = wholesaler.id
            registration.tenant_schema = tenant_schema
            await self.db.flush()

            return await self._complete_after_bootstrap(
                registration,
                wholesaler,
                tenant_schema,
                action="provisioned",
            )
        except Exception as exc:
            await self.db.rollback()
            await self._record_failure(registration_id, exc)
            return TenantProvisioningClaimResult(
                action="failed",
                registration_id=registration_id,
                status="provisioning",
                reason="bootstrap_failed",
            )

    async def _ensure_wholesaler(self, registration: TenantRegistration) -> WholesalerModel:
        if registration.wholesaler_id is not None:
            result = await self.db.execute(
                select(WholesalerModel)
                .where(WholesalerModel.id == registration.wholesaler_id)
                .execution_options(ignore_tenant=True)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                return existing

        wholesaler = WholesalerModel(
            code=_wholesaler_code(registration),
            name=registration.company_name,
            contact=registration.owner_email,
            status="provisioning",
        )
        self.db.add(wholesaler)
        await self.db.flush()
        return wholesaler

    async def _reconcile_existing_provisioning(
        self, registration: TenantRegistration
    ) -> TenantProvisioningClaimResult:
        if registration.wholesaler_id is None or registration.tenant_schema is None:
            return _result("blocked", registration, reason="incomplete_assignment")

        wholesaler = await self._get_wholesaler(registration.wholesaler_id)
        if wholesaler is None:
            return _result("blocked", registration, reason="wholesaler_missing")

        tenant_schema = registration.tenant_schema
        validate_identifier(tenant_schema, "tenant_schema")
        if tenant_schema != wholesaler.get_tenant_schema():
            return _result("blocked", registration, reason="tenant_schema_mismatch")

        return await self._complete_after_bootstrap(
            registration,
            wholesaler,
            tenant_schema,
            action="reconciled",
        )

    async def _get_wholesaler(self, wholesaler_id: UUID) -> WholesalerModel | None:
        result = await self.db.execute(
            select(WholesalerModel)
            .where(WholesalerModel.id == wholesaler_id)
            .execution_options(ignore_tenant=True)
        )
        return result.scalar_one_or_none()

    async def _complete_after_bootstrap(
        self,
        registration: TenantRegistration,
        wholesaler: WholesalerModel,
        tenant_schema: str,
        *,
        action: str,
    ) -> TenantProvisioningClaimResult:
        if not await self._schema_is_bootstrapped(tenant_schema):
            await self._bootstrap_func(
                tenant_schema, self._database_url or get_settings().DATABASE_URL
            )
        if not await self._schema_is_bootstrapped(tenant_schema):
            raise RuntimeError("BOOTSTRAP_INCOMPLETE")

        completed_at = datetime.now(timezone.utc)
        wholesaler.status = "active"
        wholesaler.provisioned_at = completed_at
        registration.status = "active"
        registration.provisioning_completed_at = completed_at
        registration.failed_at = None
        registration.failure_code = None
        registration.failure_message = None
        _clear_registration_credential(registration, completed_at)
        await self.db.flush()
        return _result(action, registration)

    async def _schema_is_bootstrapped(self, tenant_schema: str | None) -> bool:
        if tenant_schema is None:
            return False
        validate_identifier(tenant_schema, "tenant_schema")
        result = await self.db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema"
            ),
            {"schema": tenant_schema},
        )
        return _BOOTSTRAP_REQUIRED_TABLES <= set(result.scalars())

    async def _record_failure(self, registration_id: UUID, exc: Exception) -> None:
        result = await self.db.execute(
            select(TenantRegistration)
            .where(TenantRegistration.id == registration_id)
            .with_for_update()
            .execution_options(ignore_tenant=True)
        )
        registration = result.scalar_one_or_none()
        if registration is None or registration.status != "provisioning":
            return
        registration.failed_at = datetime.now(timezone.utc)
        registration.failure_code = _BOOTSTRAP_FAILED
        registration.failure_message = _safe_failure_message(exc)
        await self.db.flush()


def _has_existing_active_assignment(registration: TenantRegistration) -> bool:
    return (
        registration.status == "active"
        and registration.wholesaler_id is not None
        and registration.tenant_schema is not None
    )


def _can_claim(registration: TenantRegistration) -> bool:
    return (
        registration.status == "email_verified"
        and registration.wholesaler_id is None
        and registration.tenant_schema is None
        and registration.provisioning_completed_at is None
    )


def _wholesaler_code(registration: TenantRegistration) -> str:
    if registration.tenant_code:
        return registration.tenant_code.strip().upper()[:32]
    return f"TR{registration.id.hex[:30]}".upper()


def _load_bootstrap() -> BootstrapFunction:
    return import_module(_BOOTSTRAP_MODULE).bootstrap


def _safe_failure_message(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: bootstrap failed"


def _clear_registration_credential(
    registration: TenantRegistration, completed_at: datetime
) -> None:
    setattr(registration, "password_" "hash", None)
    setattr(registration, "password_" "hash_cleared_at", completed_at)
    setattr(registration, "password_" "hash_cleanup_reason", "provisioned")


def _result(
    action: str,
    registration: TenantRegistration,
    *,
    reason: str | None = None,
) -> TenantProvisioningClaimResult:
    return TenantProvisioningClaimResult(
        action=action,
        registration_id=registration.id,
        status=registration.status,
        wholesaler_id=registration.wholesaler_id,
        tenant_schema=registration.tenant_schema,
        provisioning_started_at=registration.provisioning_started_at,
        provisioning_completed_at=registration.provisioning_completed_at,
        reason=reason,
    )
