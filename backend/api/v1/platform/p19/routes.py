"""FastAPI routes for P19 Controlled Action Approval Workflow (P19-B skeleton).

SAFE skeleton. These endpoints record approval requests, list the approval
queue, read a single approval, and record approve / reject DECISIONS only. No
action is ever executed; every record and queue item carries
execution_allowed == False and executed == False. The skeleton never mutates
the P17 registry, tenant lifecycle, operational flags, provisioning, backup, or
tenant business data. Approval is not execution: approved resolves to
execution_blocked.

Endpoints (all behind the identity-only P10 platform guard):
  POST /api/v1/platform/p19/approvals                      create approval request
  GET  /api/v1/platform/p19/approvals                      list approval queue
  GET  /api/v1/platform/p19/approvals/{approval_id}        read approval record
  POST /api/v1/platform/p19/approvals/{approval_id}/decision  approve / reject

Responses align to docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md.

Role granularity deferral: the reused P10 guard enforces identity-only
super_admin at runtime; the support_operator / engineering_operator distinction
is not wired yet (mirrors P18). This skeleton defaults to conservative
platform-operator access and defers narrower role delegation to a future phase.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID as PyUUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.v1.platform.p10.guard import require_platform_operator

from . import services
from .schemas import (
    ControlledActionApprovalDecision,
    ControlledActionApprovalQueue,
    ControlledActionApprovalRecord,
    ControlledActionApprovalRequest,
)

router = APIRouter(prefix="/api/v1/platform/p19", tags=["platform-p19"])


# -- Guard + best-effort access-denied audit (mirrors P13/P15/P17/P18) -------


async def _write_access_denied_audit(
    db: AsyncSession, request: Request, exc: HTTPException
) -> None:
    """Best-effort audit for a denied P19 access attempt. Never blocks the response."""
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
                "scope": "platform_p19",
            },
        )
        await db.commit()
    except Exception:
        pass


async def require_platform_operator_with_p19_audit(
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


# -- Identity helpers --------------------------------------------------------


def _actor_and_context(request: Request) -> tuple[Optional[str], str]:
    """Best-effort actor id + identity_context from the auth context.

    Falls back to (None, 'system') for the test-override / operator-header path
    where no auth context is attached. Never raises.
    """
    try:
        from api.context.auth import get_auth_context

        auth_ctx = get_auth_context(request)
        token = auth_ctx.token
        actor = getattr(token, "user_id", None)
        is_super = bool(getattr(token, "is_super_admin", False))
        is_identity = bool(getattr(token, "is_identity_only", True))
        if is_super and is_identity:
            return actor, "identity_only"
        if is_super and not is_identity:
            return actor, "tenant_contextual"
        if getattr(token, "tenant_id", None):
            return actor, "tenant_admin"
        return actor, "unknown"
    except Exception:
        return None, "system"


async def _write_outcome_audit(
    db: AsyncSession, request: Request, record: ControlledActionApprovalRecord, endpoint: str
) -> None:
    """Best-effort audit of a P19 create / decision / read / queue outcome. Never blocks."""
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
            action=f"p19_approval_{endpoint}",
            resource="ops/platform/p19/approvals",
            actor_id=PyUUID(actor_id) if actor_id else None,
            wholesaler_id=None,
            audit_metadata={
                "scope": "platform_p19",
                "approval_id": record.approval_id,
                "action_type": record.action_type,
                "state": record.state,
                "decision": record.decision,
                "result": record.result,
                "executed": False,
                "execution_allowed": False,
                "source_status": record.source_status,
            },
        )
        await db.commit()
    except Exception:
        pass  # Audit failure must never block the (non-executing) response


# -- Routes ------------------------------------------------------------------


@router.post("/approvals", response_model=ControlledActionApprovalRecord)
async def create_approval_route(
    payload: ControlledActionApprovalRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p19_audit),
) -> ControlledActionApprovalRecord:
    """Create (record) an approval request (P19-B). Nothing is executed.

    Validates reason / idempotency_key / requested_by / confirmation / future
    expires_at, resolves the P18 action reference honestly, deduplicates, and
    records the approval at pending_review in ephemeral in-memory storage. The
    response always carries execution_allowed == False and executed == False.
    """
    actor, identity_context = _actor_and_context(request)
    record = await services.create_approval(
        db=db,
        actor=actor,
        identity_context=identity_context,
        **payload.model_dump(),
    )
    await _write_outcome_audit(db, request, record, "create")
    return record


@router.get("/approvals", response_model=ControlledActionApprovalQueue)
async def list_approvals_route(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p19_audit),
) -> ControlledActionApprovalQueue:
    """List the current ephemeral operator queue of recorded approvals."""
    queue = services.list_approvals(limit=limit, offset=offset)
    # Best-effort read audit (one summary event for the queue listing).
    summary = ControlledActionApprovalRecord(
        reason="", source_status="unknown", result="recorded",
        message="queue_list", executed=False, execution_allowed=False,
    )
    await _write_outcome_audit(db, request, summary, "queue_list")
    return queue


@router.get("/approvals/{approval_id}", response_model=ControlledActionApprovalRecord)
async def read_approval_route(
    approval_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p19_audit),
) -> ControlledActionApprovalRecord:
    """Read a previously recorded approval by approval_id.

    Returns 404 when the approval is not in the ephemeral in-memory store. The
    returned record always carries executed == False; nothing is executed.
    """
    record = services.read_approval(approval_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "P19_APPROVAL_NOT_FOUND",
                "message": "Approval record not found (ephemeral in-memory store).",
            },
        )
    await _write_outcome_audit(db, request, record, "read")
    return record


@router.post(
    "/approvals/{approval_id}/decision", response_model=ControlledActionApprovalRecord
)
async def submit_decision_route(
    approval_id: str,
    payload: ControlledActionApprovalDecision,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p19_audit),
) -> ControlledActionApprovalRecord:
    """Submit an approve / reject decision for a recorded approval (P19-B).

    reject is final; an expired / cancelled approval cannot be decided; a
    duplicate decision is idempotent; a conflicting decision fails; an approve
    against an unknown / unavailable P18 source is denied. An approve resolves to
    execution_blocked -- the action is NOT executed and execution_allowed stays
    false.
    """
    actor, identity_context = _actor_and_context(request)
    record = services.submit_decision(
        approval_id,
        actor=actor,
        identity_context=identity_context,
        **payload.model_dump(),
    )
    await _write_outcome_audit(db, request, record, "decision")
    return record
