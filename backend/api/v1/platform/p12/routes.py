"""
FastAPI routes for P12 Support Console API.

Endpoints:
  POST /api/v1/platform/p12/sessions                        -- Create support session
  GET  /api/v1/platform/p12/sessions/{session_id}/diagnostics -- Get redacted diagnostics
  POST /api/v1/platform/p12/sessions/{session_id}/bundles     -- Generate support bundle
  POST /api/v1/platform/p12/sessions/{session_id}/close       -- Close support session

All endpoints require platform operator credentials via the P10 guard.
Tenant-contextual super_admin tokens are denied.
Denied access triggers a support_access_denied audit event (best-effort).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID as PyUUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.v1.platform.p10.guard import require_platform_operator

from .schemas import (
    CreateBundleRequest,
    CreateSessionRequest,
    SupportBundle,
    SupportDiagnosticItem,
    SupportSession,
)
from . import services

router = APIRouter(prefix="/api/v1/platform/p12", tags=["platform-p12"])


# -- Access-denied audit helper --


async def _write_access_denied_audit(
    db: AsyncSession,
    request: Request,
    exc: HTTPException,
) -> None:
    """Write support_access_denied audit event. Best-effort --
    failure here must not prevent access denial."""
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
            action="support_access_denied",
            resource=f"support{request.url.path}",
            actor_id=PyUUID(actor_id) if actor_id else None,
            wholesaler_id=None,
            audit_metadata={
                "code": detail.get("code", "UNKNOWN"),
                "reason": detail.get("message", ""),
                "path": str(request.url.path),
                "actor_id": actor_id,
                "actor_role": actor_role,
                "has_tenant_context": has_tenant_context,
            },
        )
        await db.commit()
    except Exception:
        pass  # Audit failure must not prevent access denial


async def require_platform_operator_with_audit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_platform_operator: Optional[str] = Header(
        None,
        alias="X-Platform-Operator",
        description="Platform operator shared secret",
    ),
    x_platform_test_override: Optional[str] = Header(
        None,
        alias="X-Platform-Test-Override",
        description="Test override (MPANGO_ENV=test|testing only)",
    ),
) -> None:
    """Platform operator guard with support_access_denied audit on denial.

    Wraps the P10 guard. If access is denied (401/403), writes a
    support_access_denied audit event before re-raising. Actor_id
    is null when no auth context is available.
    """
    try:
        require_platform_operator(request, x_platform_operator, x_platform_test_override)
    except HTTPException as exc:
        if exc.status_code in (401, 403):
            await _write_access_denied_audit(db, request, exc)
        raise


# -- POST /sessions --


@router.post(
    "/sessions",
    response_model=SupportSession,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    request: Request,
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_audit),
):
    """
    Create a new support session.

    Requires a support reason (minimum 10 characters).
    Creates a support_session_start audit event.
    """
    try:
        session = await services.create_support_session(
            db,
            request,
            reason=body.reason,
            category=body.category,
            tenant_id=body.tenant_id,
        )
        return session
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SESSION_CREATE_FAILED", "message": str(exc)},
        )


# -- GET /sessions/{session_id}/diagnostics --


@router.get(
    "/sessions/{session_id}/diagnostics",
    response_model=list[SupportDiagnosticItem],
)
async def get_diagnostics(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_audit),
):
    """
    Get redacted diagnostics for an active support session.

    Returns diagnostic items from P10 services with redaction applied.
    Unknown/unavailable metrics stay unknown/null.
    """
    try:
        items = await services.get_diagnostics(db, session_id)
        return items
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg or "expired" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SESSION_NOT_FOUND", "message": msg},
            )
        if "not active" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "SESSION_NOT_ACTIVE", "message": msg},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "DIAGNOSTICS_ERROR", "message": msg},
        )


# -- POST /sessions/{session_id}/bundles --


@router.post(
    "/sessions/{session_id}/bundles",
    response_model=SupportBundle,
    status_code=status.HTTP_201_CREATED,
)
async def create_bundle(
    request: Request,
    session_id: str,
    body: CreateBundleRequest = CreateBundleRequest(),
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_audit),
):
    """
    Generate a support bundle from an active session.

    Bundle types: full, technical, summary.
    Creates a support_bundle_generated audit event.
    redaction_applied is always true.
    """
    try:
        bundle = await services.generate_bundle(
            db, request, session_id, body.bundle_type
        )
        return bundle
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg or "expired" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SESSION_NOT_FOUND", "message": msg},
            )
        if "cannot generate" in msg or "not active" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "SESSION_NOT_ACTIVE", "message": msg},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "BUNDLE_ERROR", "message": msg},
        )


# -- POST /sessions/{session_id}/close --


@router.post(
    "/sessions/{session_id}/close",
    response_model=SupportSession,
)
async def close_session(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_audit),
):
    """
    Close an active support session.

    Creates a support_session_end audit event.
    """
    try:
        session = await services.close_support_session(db, session_id)
        return session
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg or "expired" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SESSION_NOT_FOUND", "message": msg},
            )
        if "already" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "SESSION_ALREADY_CLOSED", "message": msg},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CLOSE_ERROR", "message": msg},
        )
