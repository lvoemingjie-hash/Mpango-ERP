"""
FastAPI routes for P12 Support Console API.

Endoints:
  POST /api/v1/platform/p12/sessions                        -- Create support session
  GET  /api/v1/platform/p12/sessions/{session_id}/diagnostics -- Get redacted diagnostics
  POST /api/v1/platform/p12/sessions/{session_id}/bundles     -- Generate support bundle
  POST /api/v1/platform/p12/sessions/{session_id}/close       -- Close support session

All endpoints require platform operator credentials via the P10 guard.
Tenant-contextual super_admin tokens are denied.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
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


# ── POST /sessions ──


@router.post(
    "/sessions",
    response_model=SupportSession,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    request: Request,
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator),
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


# ── GET /sessions/{session_id}/diagnostics ──


@router.get(
    "/sessions/{session_id}/diagnostics",
    response_model=list[SupportDiagnosticItem],
)
async def get_diagnostics(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator),
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


# ── POST /sessions/{session_id}/bundles ──


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
    _platform_auth: None = Depends(require_platform_operator),
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


# ── POST /sessions/{session_id}/close ──


@router.post(
    "/sessions/{session_id}/close",
    response_model=SupportSession,
)
async def close_session(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator),
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
