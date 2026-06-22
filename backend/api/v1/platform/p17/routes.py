"""
FastAPI routes for P17 Platform Registry (read-only tenant registry API).

All endpoints are GET-only (read-only). No mutations. There is intentionally no
POST / PUT / PATCH / DELETE route: lifecycle transitions, flag changes,
provisioning re-runs, and backup triggers are reserved for a separately
approved controlled-action phase (contract §9 / counterexample C7 / C11).

Responses match docs/ai/PLATFORM_PRODUCT_P17_REGISTRY_LIFECYCLE_CONTRACT.md.

Endpoints:
  GET /api/v1/platform/p17/registry               -- paginated tenant registry
  GET /api/v1/platform/p17/registry/{tenant_id}   -- single tenant registry

Both require identity-only super_admin (reused P10 guard). Tenant-contextual
super_admin and non-super_admin roles are denied. The adapter reads only
existing P10/provisioning-journal sources; it performs no writes (other than
best-effort access audit) and no tenant business-data reads.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID as PyUUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.v1.platform.p10.guard import require_platform_operator

from . import services
from .schemas import PlatformTenantRegistry, PlatformTenantRegistryList

router = APIRouter(prefix="/api/v1/platform/p17", tags=["platform-p17"])


# -- Access-denied audit helper (best-effort, mirrors P13/P15) --


async def _write_access_denied_audit(
    db: AsyncSession,
    request: Request,
    exc: HTTPException,
) -> None:
    """Write an ops_access_denied / registry_view_denied audit event. Best-effort."""
    try:
        actor_id = None
        actor_role = None
        has_tenant_context = False
        try:
            from api.context.auth import get_auth_context

            auth_ctx = get_auth_context(request)
            token = auth_ctx.token
            actor_id = token.user_id
            has_tenant_context = not getattr(token, "is_identity_only", True)
            if getattr(token, "is_super_admin", False):
                actor_role = "super_admin"
        except Exception:
            pass

        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}

        from services.platform_audit_service import append_audit_entry

        await append_audit_entry(
            db,
            actor_type="api",
            action="ops_access_denied",
            resource=f"ops{request.url.path}",
            actor_id=PyUUID(actor_id) if actor_id else None,
            wholesaler_id=None,
            audit_metadata={
                "code": detail.get("code", "UNKNOWN"),
                "reason": detail.get("message", ""),
                "path": str(request.url.path),
                "actor_id": actor_id,
                "actor_role": actor_role,
                "has_tenant_context": has_tenant_context,
                "scope": "platform_registry",
                "registry_action": "registry_view_denied",
            },
        )
        await db.commit()
    except Exception:
        pass


async def require_platform_operator_with_registry_audit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_platform_operator: Optional[str] = Header(
        None, alias="X-Platform-Operator",
        description="Platform operator shared secret",
    ),
    x_platform_test_override: Optional[str] = Header(
        None, alias="X-Platform-Test-Override",
        description="Test override (MPANGO_ENV=test|testing only)",
    ),
) -> None:
    """Platform operator guard with an access-denied audit on denial."""
    try:
        require_platform_operator(request, x_platform_operator, x_platform_test_override)
    except HTTPException as exc:
        if exc.status_code in (401, 403):
            await _write_access_denied_audit(db, request, exc)
        raise


# -- Best-effort view audit --


async def _write_registry_view_audit(
    db: AsyncSession,
    request: Request,
    tenant_id: Optional[str],
) -> None:
    """Best-effort audit for a successful registry view. Never blocks the read."""
    try:
        actor_id = None
        actor_role = None
        try:
            from api.context.auth import get_auth_context

            auth_ctx = get_auth_context(request)
            token = auth_ctx.token
            actor_id = token.user_id
            if getattr(token, "is_super_admin", False):
                actor_role = "super_admin"
        except Exception:
            pass

        from services.platform_audit_service import append_audit_entry

        await append_audit_entry(
            db,
            actor_type="api",
            action="ops_registry_view",
            resource="ops/platform/p17/registry",
            actor_id=PyUUID(actor_id) if actor_id else None,
            wholesaler_id=None,
            audit_metadata={
                "view_type": "platform_registry",
                "actor_role": actor_role,
                "scope": "platform_registry",
                "registry_action": "registry_view",
                "tenant_scoped": tenant_id is not None,
            },
        )
        await db.commit()
    except Exception:
        pass  # Audit failure must not prevent the read-only response


# -- GET /registry (list) --


@router.get("/registry", response_model=PlatformTenantRegistryList)
async def list_tenant_registries(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_registry_audit),
) -> PlatformTenantRegistryList:
    """Read-only paginated platform tenant registry (P17-B).

    Aggregates existing P10 tenant-identity sources + the provisioning journal
    into a single read-consistent registry view. Degrades gracefully: a source
    failure yields registry_source_status 'unavailable'/'unknown' with a reason,
    never a 500 and never a fabricated healthy record. No writes (besides
    best-effort access audit), no tenant business records, no credentials.
    """
    result = await services.list_tenant_registries(db, limit=limit, offset=offset)
    await _write_registry_view_audit(db, request, tenant_id=None)
    return result


# -- GET /registry/{tenant_id} (single) --


@router.get("/registry/{tenant_id}", response_model=PlatformTenantRegistry)
async def get_tenant_registry(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_registry_audit),
) -> PlatformTenantRegistry:
    """Read-only single-tenant platform registry (P17-B).

    Returns 404 when the tenant identity does not exist. When the tenant exists
    but sub-sources are unavailable, returns a record with unknown / null fields
    and reasons -- never a fabricated healthy one.
    """
    registry = await services.get_tenant_registry(db, tenant_id)
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "REGISTRY_TENANT_NOT_FOUND",
                "message": "Tenant identity not found in the platform registry",
            },
        )
    await _write_registry_view_audit(db, request, tenant_id=tenant_id)
    return registry
