"""FastAPI routes for P20 Durable Approval Governance.

These endpoints open durable approval requests, list and read them, and record
per-checker approve / reject DECISIONS under a maker-checker, quorum-based
dual-control policy. No action is ever executed; every record and queue item
carries execution_allowed == False and executed == False. The routes never
mutate the P17 registry, tenant lifecycle, operational flags, provisioning,
backup, or any tenant business data. Approval is not execution and durability
is not execution: a quorum-met approval resolves to approved_execution_blocked.

P21-D-D: each endpoint runs the storage gate (durable default; explicit memory
test/dev backend). When the durable store is not ready the handler returns 503
(``storage_not_ready`` / ``unavailable`` / ``degraded``) and never silently
falls back to memory.

Endpoints (all behind the identity-only P10 platform guard):
  POST /api/v1/platform/p20/durable-approvals                            create
  GET  /api/v1/platform/p20/durable-approvals                            list (filters)
  GET  /api/v1/platform/p20/durable-approvals/{approval_id}              read
  POST /api/v1/platform/p20/durable-approvals/{approval_id}/decisions    checker decision

Responses align to docs/ai/PLATFORM_PRODUCT_P20_DURABLE_APPROVAL_GOVERNANCE_CONTRACT.md.

Role granularity deferral: the reused P10 guard enforces identity-only
super_admin at runtime, which denies tenant-contextual super_admin,
tenant-scoped tokens, and non-super_admin roles (support_operator /
engineering_operator) at the boundary -- strictly stronger than the contract's
read-only allowance for those roles and satisfying cannot-create /
cannot-approve. Narrower runtime role delegation is deferred to a future phase
(mirrors P18 / P19); this skeleton performs no auth / RBAC rewrite.
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
    DurableApprovalDecisionRequest,
    DurableApprovalQueue,
    DurableApprovalRecord,
    DurableApprovalCreateRequest,
)

router = APIRouter(prefix="/api/v1/platform/p20", tags=["platform-p20"])


# -- Guard + best-effort access-denied audit (mirrors P13/P15/P17/P18/P19) ---


async def _write_access_denied_audit(
    db: AsyncSession, request: Request, exc: HTTPException
) -> None:
    """Best-effort audit for a denied P20 access attempt. Never blocks the response."""
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
                "scope": "platform_p20",
            },
        )
        await db.commit()
    except Exception:
        pass


async def require_platform_operator_with_p20_audit(
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


def _actor_context_and_role(request: Request) -> tuple[Optional[str], str, str]:
    """Best-effort (actor_id, identity_context, actor_role) read from the auth
    context attached by the middleware.

    The actor is the authenticated identity (read from the token). The system /
    operator-secret / test-override fallback has NO actor (it returns
    (None, 'system', 'system')); in that case the create and decision services
    deny the request, because the maker / checker must bind to a real
    authenticated actor. Maker-checker separation and quorum are enforced in
    services.py against this authenticated actor (never the client payload).
    Never raises.
    """
    try:
        from api.context.auth import get_auth_context

        auth_ctx = get_auth_context(request)
        token = auth_ctx.token
        actor = getattr(token, "user_id", None)
        is_super = bool(getattr(token, "is_super_admin", False))
        is_identity = bool(getattr(token, "is_identity_only", True))
        roles = list(getattr(token, "roles", []) or [])
        if is_super and is_identity:
            return actor, "identity_only", "super_admin"
        if is_super and not is_identity:
            return actor, "tenant_contextual", "super_admin"
        if "support_operator" in roles:
            return actor, ("identity_only" if is_identity else "tenant_contextual"), "support_operator"
        if "engineering_operator" in roles:
            return actor, ("identity_only" if is_identity else "tenant_contextual"), "engineering_operator"
        if getattr(token, "tenant_id", None):
            return actor, "tenant_admin", "unknown"
        return actor, "unknown", "unknown"
    except Exception:
        return None, "system", "system"


async def _write_outcome_audit(
    db: AsyncSession, request: Request, record: DurableApprovalRecord, endpoint: str
) -> None:
    """Best-effort audit of a P20 create / decision / read / queue outcome. Never blocks."""
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
            action=f"p20_durable_approval_{endpoint}",
            resource="ops/platform/p20/durable-approvals",
            actor_id=PyUUID(actor_id) if actor_id else None,
            wholesaler_id=None,
            audit_metadata={
                "scope": "platform_p20",
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


def _raise_storage_not_ready(exc: Exception) -> None:
    """Translate a P21-D-D DurableStoreNotReady gate failure into a 503 response.

    The durable store was not ready (DB unreachable, P21-C1 schema / tables
    missing, or adapter init / operation failure). The request was NOT recorded
    or read and nothing was executed; the service did not silently fall back to
    the in-memory store. The closed-vocabulary ``code`` (storage_not_ready /
    unavailable / degraded) is echoed so the caller can tell the modes apart.
    """
    code = getattr(exc, "code", "storage_not_ready")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": code,
            "message": (
                "Durable approval store is not ready; the request was not "
                "recorded / read and nothing was executed."
            ),
            "storage": "durable",
            "unavailable_reason": code,
        },
    )


# -- Routes ------------------------------------------------------------------


@router.post("/durable-approvals", response_model=DurableApprovalRecord)
async def create_durable_approval_route(
    payload: DurableApprovalCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p20_audit),
) -> DurableApprovalRecord:
    """Open (record) a durable approval request (P20-B). Nothing is executed.

    Validates reason / idempotency_key / maker / confirmation / future
    expires_at, resolves the P18 action reference and class honestly,
    deduplicates (digest-only key), and records the approval at pending_review in
    ephemeral in-memory storage with the action-class quorum floor. The response
    always carries execution_allowed == False and executed == False.
    """
    actor, identity_context, actor_role = _actor_context_and_role(request)
    try:
        record = await services.create_durable_approval(
            db=db,
            actor=actor,
            actor_role=actor_role,
            identity_context=identity_context,
            **payload.model_dump(),
        )
    except services.DurableStoreNotReady as exc:
        _raise_storage_not_ready(exc)
    await _write_outcome_audit(db, request, record, "create")
    return record


@router.get("/durable-approvals", response_model=DurableApprovalQueue)
async def list_durable_approvals_route(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by lifecycle state."),
    action_type: Optional[str] = Query(None, description="Filter by P18 action_type."),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant_id."),
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p20_audit),
) -> DurableApprovalQueue:
    """List the operator queue of durable approvals (with filters).

    P21-D-D: the queue is served by the durable adapter in production (default)
    and by the in-memory backend only in explicit test / dev memory mode.
    """
    try:
        queue = await services.list_durable_approvals(
            limit=limit, offset=offset, status=status, action_type=action_type,
            tenant_id=tenant_id, db=db,
        )
    except services.DurableStoreNotReady as exc:
        _raise_storage_not_ready(exc)
    summary = DurableApprovalRecord(
        reason="", source_status="unknown", result="recorded",
        message="queue_list", executed=False, execution_allowed=False,
    )
    await _write_outcome_audit(db, request, summary, "queue_list")
    return queue


@router.get("/durable-approvals/{approval_id}", response_model=DurableApprovalRecord)
async def read_durable_approval_route(
    approval_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p20_audit),
) -> DurableApprovalRecord:
    """Read a previously recorded durable approval by approval_id.

    Returns 404 when the approval is not found. P21-D-D: the record is served by
    the durable adapter in production (default) and by the in-memory backend only
    in explicit test / dev memory mode. The returned record always carries
    executed == False; nothing is executed.
    """
    try:
        record = await services.read_durable_approval(approval_id, db=db)
    except services.DurableStoreNotReady as exc:
        _raise_storage_not_ready(exc)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "P20_APPROVAL_NOT_FOUND",
                "message": "Durable approval record not found.",
            },
        )
    await _write_outcome_audit(db, request, record, "read")
    return record


@router.post(
    "/durable-approvals/{approval_id}/decisions", response_model=DurableApprovalRecord
)
async def submit_decision_route(
    approval_id: str,
    payload: DurableApprovalDecisionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p20_audit),
) -> DurableApprovalRecord:
    """Record one checker's approve / reject decision for a durable approval (P20-B).

    Maker-checker separation is enforced (approver_id must differ from maker).
    Each checker records at most one decision; reject is final; approve
    accumulates until the quorum floor of distinct checkers is met, then resolves
    to approved_execution_blocked. An approve against an unknown / unavailable
    P18 source is denied. The action is NOT executed and execution_allowed stays
    false.
    """
    actor, identity_context, actor_role = _actor_context_and_role(request)
    try:
        record = await services.submit_decision(
            approval_id,
            actor=actor,
            actor_role=actor_role,
            identity_context=identity_context,
            db=db,
            **payload.model_dump(),
        )
    except services.DurableStoreNotReady as exc:
        _raise_storage_not_ready(exc)
    await _write_outcome_audit(db, request, record, "decision")
    return record
