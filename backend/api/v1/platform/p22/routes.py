"""FastAPI routes for P22 Controlled Execution v0 (P22-B non-executing skeleton).

These endpoints expose the v0 execution catalog, the no-mutation dry-run
validator, execution-request recording, and execution-result read. NO action is
ever executed; every response carries execution_allowed == False, executed ==
False, execution_started == False, and a result_state that is only ever
dry_run_passed | blocked. The routes never dispatch a worker, never drain a
queue, never invoke the P16 governed harness, and never mutate the P17 registry,
tenant lifecycle, operational flags, provisioning, backup, or any tenant business
/ payment / billing / product data. Approval is not execution and durability is
not execution.

The executor identity (actor_id / actor_role / identity_context) is derived from
the authenticated token via the reused P10 identity-only guard -- it is NEVER
read from the request body (no identity spoof), mirroring the P20-B-R1 binding.

Endpoints (all behind the identity-only P10 platform guard):
  GET  /api/v1/platform/p22/execution/catalog                       catalog (read-only)
  POST /api/v1/platform/p22/execution/dry-run                       dry-run (no mutation)
  POST /api/v1/platform/p22/execution/requests                      record request (no execution)
  GET  /api/v1/platform/p22/execution/requests                      list (filters)
  GET  /api/v1/platform/p22/execution/requests/{execution_request_id}  read

Responses align to docs/ai/PLATFORM_PRODUCT_P22_CONTROLLED_EXECUTION_V0_CONTRACT.md
(P22-A). Role granularity deferral mirrors P18 / P19 / P20: the reused P10 guard
enforces identity-only super_admin at runtime; the P22 service additionally
requires the executor (the authenticated actor) to be an identity-only
super_admin, denying support_operator / engineering_operator / tenant-contextual
super_admin / tenant-scoped tokens as v0 executors. No auth / RBAC rewrite.
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
    ExecutionCatalogResponse,
    ExecutionDryRunRequest,
    ExecutionDryRunResponse,
    ExecutionRequestCreate,
    ExecutionRequestQueue,
    ExecutionRequestResponse,
)

router = APIRouter(prefix="/api/v1/platform/p22", tags=["platform-p22"])


# -- Guard + best-effort access-denied audit (mirrors P20) --------------------


async def _write_access_denied_audit(
    db: AsyncSession, request: Request, exc: HTTPException
) -> None:
    """Best-effort audit for a denied P22 access attempt. Never blocks the response."""
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
                "scope": "platform_p22",
            },
        )
        await db.commit()
    except Exception:
        pass


async def require_platform_operator_with_p22_audit(
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


# -- Identity helpers (mirror P20; the actor is the authenticated token) -------


def _actor_context_and_role(request: Request) -> tuple[Optional[str], str, str]:
    """Best-effort (actor_id, identity_context, actor_role) from the auth context.

    The executor is the authenticated identity (read from the token). The system
    / operator-secret / test-override fallback has NO actor (it returns
    (None, 'system', 'system')); in that case the P22 service denies execution,
    because the v0 executor must be a real authenticated identity-only super_admin.
    Operator separation is enforced in services.py against this authenticated
    actor (never the client payload). Never raises.
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
    db: AsyncSession, request: Request, endpoint: str, **fields: object
) -> None:
    """Best-effort audit of a P22 outcome. Never blocks the (non-executing) response."""
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

        metadata = {
            "scope": "platform_p22",
            "executed": False,
            "execution_allowed": False,
            "execution_started": False,
        }
        metadata.update({k: v for k, v in fields.items() if v is not None})
        await append_audit_entry(
            db,
            actor_type="api",
            action=f"p22_execution_{endpoint}",
            resource="ops/platform/p22/execution",
            actor_id=PyUUID(actor_id) if actor_id else None,
            wholesaler_id=None,
            audit_metadata=metadata,
        )
        await db.commit()
    except Exception:
        pass  # Audit failure must never block the (non-executing) response.


# -- Routes -------------------------------------------------------------------


@router.get("/execution/catalog", response_model=ExecutionCatalogResponse)
async def execution_catalog_route(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p22_audit),
) -> ExecutionCatalogResponse:
    """Return the closed v0 execution catalog (allowlist + exclusions). Read-only.

    Never executes. The allowlist is exactly the seven v0 actions; every excluded
    action (tenant.pause / tenant.resume / lifecycle.transition / real restore /
    schema migration / data deletion / payment-billing / tenant-business-records /
    arbitrary shell-SQL-script) has no v0 execution path.
    """
    catalog = services.build_catalog()
    await _write_outcome_audit(
        db, request, "catalog", total=catalog.total, executed=False
    )
    return catalog


@router.post("/execution/dry-run", response_model=ExecutionDryRunResponse)
async def execution_dry_run_route(
    payload: ExecutionDryRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p22_audit),
) -> ExecutionDryRunResponse:
    """Validate an execution against the preconditions; return a no-mutation verdict.

    Mutates nothing; records dry-run audit events in memory. Returns executable /
    verdict / block_reasons / expected_audit_shape. A passed dry-run is a
    PRECONDITION, not an execution: execution_allowed is always false.
    """
    actor, identity_context, actor_role = _actor_context_and_role(request)
    response = services.evaluate_dry_run(
        payload, actor=actor, actor_role=actor_role, identity_context=identity_context
    )
    await _write_outcome_audit(
        db,
        request,
        "dry_run",
        durable_approval_id=response.durable_approval_id,
        action_type=response.action_type,
        executable=response.executable,
        verdict=response.verdict,
        executed=False,
        execution_allowed=False,
    )
    return response


@router.post("/execution/requests", response_model=ExecutionRequestResponse)
async def create_execution_request_route(
    payload: ExecutionRequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p22_audit),
) -> ExecutionRequestResponse:
    """Record an execution request after a passed dry-run and acknowledgement.

    Does NOT execute. result_state is only ever dry_run_passed (recorded) or
    blocked (a precondition failed / idempotency conflict). No worker is
    dispatched, no queue is drained, no P16 harness is invoked.
    """
    actor, identity_context, actor_role = _actor_context_and_role(request)
    response = services.record_execution_request(
        payload, actor=actor, actor_role=actor_role, identity_context=identity_context
    )
    await _write_outcome_audit(
        db,
        request,
        "request",
        execution_request_id=response.execution_request_id,
        durable_approval_id=response.durable_approval_id,
        action_type=response.action_type,
        result_state=response.result_state,
        result=response.result,
        executed=False,
        execution_allowed=False,
    )
    return response


@router.get("/execution/requests", response_model=ExecutionRequestQueue)
async def list_execution_requests_route(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    result_state: Optional[str] = Query(None, description="Filter by execution-record state."),
    action_type: Optional[str] = Query(None, description="Filter by v0 action_type."),
    durable_approval_id: Optional[str] = Query(None, description="Filter by durable_approval_id."),
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p22_audit),
) -> ExecutionRequestQueue:
    """List the recorded execution requests (with filters). Read-only; never executes."""
    queue = services.list_execution_requests(
        limit=limit,
        offset=offset,
        result_state=result_state,
        action_type=action_type,
        durable_approval_id=durable_approval_id,
    )
    await _write_outcome_audit(db, request, "queue_list", total=queue.total, executed=False)
    return queue


@router.get(
    "/execution/requests/{execution_request_id}", response_model=ExecutionRequestResponse
)
async def read_execution_request_route(
    execution_request_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_p22_audit),
) -> ExecutionRequestResponse:
    """Read one recorded execution request by id. Read-only; never executes.

    Returns 404 when the request is not found. The response always carries
    executed == False and a non-executing result_state.
    """
    response = services.read_execution_request(execution_request_id)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "P22_EXECUTION_REQUEST_NOT_FOUND",
                "message": "Execution request record not found.",
            },
        )
    await _write_outcome_audit(
        db,
        request,
        "read",
        execution_request_id=response.execution_request_id,
        result_state=response.result_state,
        executed=False,
    )
    return response
