"""FastAPI routes for P18 Controlled Platform Actions (request skeleton, P18-B).

SAFE skeleton. These endpoints validate, deduplicate, redact, audit, and RECORD
controlled-action requests only. No action is ever executed; every response
carries executed == False. The skeleton never mutates the P17 registry, tenant
lifecycle, operational flags, provisioning, backup, or tenant business data.

Endpoints (all behind the identity-only P10 platform guard):
  GET  /api/v1/platform/p18/actions/catalog
  POST /api/v1/platform/p18/actions/validate
  POST /api/v1/platform/p18/actions/request
  GET  /api/v1/platform/p18/actions/requests/{action_id}

Responses align to docs/ai/PLATFORM_PRODUCT_P18_CONTROLLED_ACTIONS_CONTRACT.md.

Role granularity deferral: the reused P10 guard enforces identity-only
super_admin at runtime; the support_operator / engineering_operator distinction
is not wired yet. Per the P18-A contract and the P18-B task, this skeleton
defaults to conservative super_admin-only access and defers narrower role
delegation to a future phase when runtime role granularity exists.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID as PyUUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.v1.platform.p10.guard import require_platform_operator

from . import services
from .schemas import (
    ActionCatalogResponse,
    ActionRequest,
    ActionRequestResponse,
)

router = APIRouter(prefix="/api/v1/platform/p18", tags=["platform-p18"])


# -- Guard + best-effort access-denied audit (mirrors P13/P15/P17) ----------


async def _write_access_denied_audit(
    db: AsyncSession, request: Request, exc: HTTPException
) -> None:
    """Best-effort audit for a denied P18 access attempt. Never blocks the response."""
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
                "scope": "platform_p18",
            },
        )
        await db.commit()
    except Exception:
        pass


async def require_platform_operator_with_p18_audit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_platform_operator: Optional[str] = Header(
        None, alias="X-Platform-Operator", description="Platform operator shared secret"
    ),
    x_platform_test_override: Optional[str] = Header(
        None, alias="X-Platform-Test-Override", description="Test override (test env only)"
    ),
) -> None:
    """P10 identity-only guard with a best-effort access-denied audit on denial."""
    try:
        require_platform_operator(request, x_platform_operator, x_platform_test_override)
    except HTTPException as exc:
        if exc.status_code in (401, 403):
            await _write_access_denied_audit(db, request, exc)
        raise


# -- Best-effort request audit ---------------------------------------------


async def _write_request_audit(
    db: AsyncSession,
    request: Request,
    response: ActionRequestResponse,
    endpoint: str,
) -> None:
    """Best-effort audit for a P18 validate / request / lookup. Never blocks."""
    try:
        actor_id = None
        try:
            from api.context.auth import get_auth_context

            auth_ctx = get_auth_context(request)
            token = auth_ctx.token
            actor_id = token.user_id
        except Exception:
            pass

        from services.platform_audit_service import append_audit_entry

        await append_audit_entry(
            db,
            actor_type="api",
            action=f"p18_action_{endpoint}",
            resource="ops/platform/p18/actions",
            actor_id=PyUUID(actor_id) if actor_id else None,
            wholesaler_id=None,
            audit_metadata={
                "scope": "platform_p18",
                "action_type": response.action_type,
                "result": response.result,
                "executed": False,
                "dry_run": response.dry_run,
                "idempotency_key": response.idempotency_key,
                "source_status": response.source_status,
            },
        )
        await db.commit()
    except Exception:
        pass  # Audit failure must never block the (non-executing) response


# -- Routes -----------------------------------------------------------------


@router.get("/actions/catalog", response_model=ActionCatalogResponse)
async def get_catalog(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p18_audit),
) -> ActionCatalogResponse:
    """Read-only controlled-action catalog (P18-A section 3).

    Returns the closed set of action types with their classification, allowed
    actors, confirmation requirement, and degraded allowance. Nothing is executed.
    """
    return services.get_catalog()


@router.post("/actions/validate", response_model=ActionRequestResponse)
async def validate_action(
    payload: ActionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p18_audit),
) -> ActionRequestResponse:
    """Dry-run validation of a controlled-action request (P18-B).

    Validates the request against the catalog, reason, idempotency_key,
    confirmation, and registry source rules, and returns the projected result
    WITHOUT persisting and WITHOUT executing. dry_run == True on the response.
    """
    response = await services.evaluate_request(
        db=db,
        persist=False,
        **payload.model_dump(),
    )
    await _write_request_audit(db, request, response, "validate")
    return response


@router.post("/actions/request", response_model=ActionRequestResponse)
async def submit_action(
    payload: ActionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p18_audit),
) -> ActionRequestResponse:
    """Record a controlled-action request (P18-B). The request is NOT executed.

    Validates, deduplicates (duplicate / conflict on idempotency_key), redacts,
    audits, and records the request in ephemeral in-memory storage. The response
    always carries executed == False; no registry, lifecycle, flag, provisioning,
    or backup state is changed.
    """
    response = await services.evaluate_request(
        db=db,
        persist=True,
        **payload.model_dump(),
    )
    await _write_request_audit(db, request, response, "request")
    return response


@router.get("/actions/requests/{action_id}", response_model=ActionRequestResponse)
async def get_recorded_request(
    action_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p18_audit),
) -> ActionRequestResponse:
    """Read a previously recorded controlled-action request by action_id.

    Returns 404 when the request is not in the ephemeral in-memory store. The
    returned record always carries executed == False; nothing is executed.
    """
    response = services.get_stored_request(action_id)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "P18_REQUEST_NOT_FOUND",
                "message": "Recorded request not found (ephemeral in-memory store).",
            },
        )
    await _write_request_audit(db, request, response, "lookup")
    return response
