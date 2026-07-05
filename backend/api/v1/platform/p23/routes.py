"""FastAPI routes for P23 Operator Task / Notification Queue (P23-B skeleton).

NON-EXECUTING, NON-SENDING endpoints. Every route is behind the reused P10
identity-only platform-operator guard; P23 defines no new auth, token, session,
or role (no auth / RBAC rewrite). No route executes a P22 action, approves a
P19/P20/P21 approval, mutates a P17 registry field, delivers a notification,
dispatches a worker, drains a queue, runs shell / SQL / script, or reads / writes
any tenant business / payment / billing / product record.

The actor for every state-management transition is the authenticated identity
(read from the token via the reused P10 guard); it is NEVER read from the request
body (no identity spoof), mirroring the P20-B-R1 / P22 binding. Owner is
presentation only; it grants no new privilege.

Endpoints (all behind require_platform_operator):
  GET  /api/v1/platform/p23/operator-tasks                              list (filters)
  GET  /api/v1/platform/p23/operator-tasks/{task_id}                    read detail
  POST /api/v1/platform/p23/operator-tasks/{task_id}/acknowledge        open|waiting->ack
  POST /api/v1/platform/p23/operator-tasks/{task_id}/self-assign        set owner
  POST /api/v1/platform/p23/operator-tasks/{task_id}/in-progress        ->in_progress
  POST /api/v1/platform/p23/operator-tasks/{task_id}/complete           ->completed (+ev)
  POST /api/v1/platform/p23/operator-tasks/{task_id}/dismiss            ->dismissed
  POST /api/v1/platform/p23/operator-tasks/internal/intake              typed intake only
  POST /api/v1/platform/p23/operator-tasks/internal/materialize         P23-C read/materialize

Responses align to docs/ai/PLATFORM_PRODUCT_P23_OPERATOR_TASK_NOTIFICATION_QUEUE_CONTRACT.md
(P23-A, section 7).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from api.dependencies import get_db
from api.v1.platform.p10.guard import require_platform_operator

from . import services, sources
from .schemas import (
    OperatorTaskDetail,
    OperatorTaskIntakeEvent,
    OperatorTaskIntakeResponse,
    OperatorTaskQueue,
    OperatorTaskTransitionRequest,
    OperatorTaskTransitionResponse,
)

router = APIRouter(
    prefix="/api/v1/platform/p23/operator-tasks", tags=["platform-p23"]
)


# -- Identity helper (mirrors P20 / P22; the actor is the authenticated token) --


def _actor_context_and_role(request: Request) -> tuple[Optional[str], str]:
    """Best-effort (actor_id, actor_role) from the auth context. Never raises.

    The operator is the authenticated identity. The system / operator-secret /
    test-override fallback has NO actor and returns (None, 'system'); that path
    may still perform read / triage, but owner_actor_id will be None. Owner is
    presentation only and grants no new privilege.
    """
    try:
        from api.context.auth import get_auth_context

        auth_ctx = get_auth_context(request)
        token = auth_ctx.token
        actor = getattr(token, "user_id", None)
        is_super = bool(getattr(token, "is_super_admin", False))
        roles = list(getattr(token, "roles", []) or [])
        if is_super:
            return actor, "super_admin"
        if "support_operator" in roles:
            return actor, "support_operator"
        if "engineering_operator" in roles:
            return actor, "engineering_operator"
        return actor, "system"
    except Exception:
        return None, "system"


# -- Read / list ---------------------------------------------------------------


@router.get("", response_model=OperatorTaskQueue)
def list_tasks_route(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    severity: Optional[str] = Query(None, description="Filter by severity."),
    task_type: Optional[str] = Query(None, description="Filter by task_type."),
    state: Optional[str] = Query(None, description="Filter by state."),
    tenant_id: Optional[str] = Query(None, description="Filter by scoped tenant_id."),
    source_status: Optional[str] = Query(None, description="Filter by source_status."),
    owner_actor_id: Optional[str] = Query(None, description="Filter by owner."),
    correlation_id: Optional[str] = Query(None, description="Filter by correlation_id."),
    _platform_auth: None = Depends(require_platform_operator),
) -> OperatorTaskQueue:
    """List operator tasks with filters, ranked by severity then recency. Read-only.

    Executes, approves, mutates, and sends nothing.
    """
    return services.list_tasks(
        limit=limit,
        offset=offset,
        severity=severity,
        task_type=task_type,
        state=state,
        tenant_id=tenant_id,
        source_status=source_status,
        owner_actor_id=owner_actor_id,
        correlation_id=correlation_id,
    )


@router.get("/{task_id}", response_model=OperatorTaskDetail)
def read_task_route(
    task_id: str,
    request: Request,
    _platform_auth: None = Depends(require_platform_operator),
) -> OperatorTaskDetail:
    """Read one task's redacted record, full audit history, and notification events.

    Read-only; executes nothing. dismissed / expired tasks retain their full audit
    history. Returns 404 when the task is not found.
    """
    detail = services.read_task(task_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "P23_TASK_NOT_FOUND",
                "message": "Operator task not found.",
            },
        )
    return detail


# -- State management (presentation-only) --------------------------------------


def _resolve_optional_payload(
    payload: Optional[OperatorTaskTransitionRequest],
) -> OperatorTaskTransitionRequest:
    return payload if payload is not None else OperatorTaskTransitionRequest()


def _transition_response_status(response: OperatorTaskTransitionResponse) -> int:
    """200 when the transition changed state; 409 when it was denied."""
    return (
        status.HTTP_200_OK
        if response.accepted
        else status.HTTP_409_CONFLICT
    )


@router.post(
    "/{task_id}/acknowledge",
    response_model=OperatorTaskTransitionResponse,
)
def acknowledge_route(
    task_id: str,
    request: Request,
    payload: Optional[OperatorTaskTransitionRequest] = None,
    _platform_auth: None = Depends(require_platform_operator),
) -> OperatorTaskTransitionResponse:
    """open|waiting_on_* -> acknowledged. State management only; executes nothing."""
    actor_id, actor_role = _actor_context_and_role(request)
    response = services.acknowledge_task(
        task_id, actor_id=actor_id, actor_role=actor_role,
        payload=_resolve_optional_payload(payload),
    )
    if not response.accepted and response.denial_code == "TASK_NOT_FOUND":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "P23_TASK_NOT_FOUND", "message": "Operator task not found."
        })
    status_code = _transition_response_status(response)
    if status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=status_code, detail={
            "code": response.denial_code,
            "message": response.transition,
            "task": response.task.model_dump(mode="json"),
        })
    return response


@router.post(
    "/{task_id}/self-assign",
    response_model=OperatorTaskTransitionResponse,
)
def self_assign_route(
    task_id: str,
    request: Request,
    payload: Optional[OperatorTaskTransitionRequest] = None,
    _platform_auth: None = Depends(require_platform_operator),
) -> OperatorTaskTransitionResponse:
    """Set the owner to the authenticated operator. Presentation only; runs nothing.

    Does not change the task state and grants no new privilege.
    """
    actor_id, actor_role = _actor_context_and_role(request)
    response = services.self_assign_task(
        task_id, actor_id=actor_id, actor_role=actor_role,
        payload=_resolve_optional_payload(payload),
    )
    if not response.accepted and response.denial_code == "TASK_NOT_FOUND":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "P23_TASK_NOT_FOUND", "message": "Operator task not found."
        })
    return response


@router.post(
    "/{task_id}/in-progress",
    response_model=OperatorTaskTransitionResponse,
)
def in_progress_route(
    task_id: str,
    request: Request,
    payload: Optional[OperatorTaskTransitionRequest] = None,
    _platform_auth: None = Depends(require_platform_operator),
) -> OperatorTaskTransitionResponse:
    """-> in_progress. For an execution_ready task this records operator attention
    only; the action still runs through P22. The task itself runs nothing."""
    actor_id, actor_role = _actor_context_and_role(request)
    response = services.mark_in_progress_task(
        task_id, actor_id=actor_id, actor_role=actor_role,
        payload=_resolve_optional_payload(payload),
    )
    if not response.accepted and response.denial_code == "TASK_NOT_FOUND":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "P23_TASK_NOT_FOUND", "message": "Operator task not found."
        })
    status_code = _transition_response_status(response)
    if status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=status_code, detail={
            "code": response.denial_code,
            "message": response.transition,
            "task": response.task.model_dump(mode="json"),
        })
    return response


@router.post(
    "/{task_id}/complete",
    response_model=OperatorTaskTransitionResponse,
)
def complete_route(
    task_id: str,
    request: Request,
    payload: Optional[OperatorTaskTransitionRequest] = None,
    _platform_auth: None = Depends(require_platform_operator),
) -> OperatorTaskTransitionResponse:
    """-> completed. Requires a redacted evidence note or linked completed id, AND
    a closed linked gate. Rejects (409) otherwise. Executes nothing; completing an
    execution_ready task does not run the action and does not make the completer
    the P22 executor."""
    actor_id, actor_role = _actor_context_and_role(request)
    response = services.complete_task(
        task_id, actor_id=actor_id, actor_role=actor_role,
        payload=_resolve_optional_payload(payload),
    )
    if not response.accepted and response.denial_code == "TASK_NOT_FOUND":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "P23_TASK_NOT_FOUND", "message": "Operator task not found."
        })
    status_code = _transition_response_status(response)
    if status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=status_code, detail={
            "code": response.denial_code,
            "message": response.transition,
            "task": response.task.model_dump(mode="json"),
        })
    return response


@router.post(
    "/{task_id}/dismiss",
    response_model=OperatorTaskTransitionResponse,
)
def dismiss_route(
    task_id: str,
    request: Request,
    payload: Optional[OperatorTaskTransitionRequest] = None,
    _platform_auth: None = Depends(require_platform_operator),
) -> OperatorTaskTransitionResponse:
    """-> dismissed. Removes from the active queue; the audit history is RETAINED.
    Nothing is deleted; the queue is a view, not the system of record."""
    actor_id, actor_role = _actor_context_and_role(request)
    response = services.dismiss_task(
        task_id, actor_id=actor_id, actor_role=actor_role,
        payload=_resolve_optional_payload(payload),
    )
    if not response.accepted and response.denial_code == "TASK_NOT_FOUND":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "P23_TASK_NOT_FOUND", "message": "Operator task not found."
        })
    status_code = _transition_response_status(response)
    if status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=status_code, detail={
            "code": response.denial_code,
            "message": response.transition,
            "task": response.task.model_dump(mode="json"),
        })
    return response


# -- Internal intake (typed / redacted only; no raw payload) -------------------


@router.post(
    "/internal/intake",
    response_model=OperatorTaskIntakeResponse,
    status_code=status.HTTP_201_CREATED,
)
def intake_route(
    event: OperatorTaskIntakeEvent,
    request: Request,
    response: Response,
    _platform_auth: None = Depends(require_platform_operator),
) -> OperatorTaskIntakeResponse:
    """Internal intake: materialize (or dedup-bump) a task from a typed source event.

    Accepts ONLY the closed OperatorTaskIntakeEvent shape (extra="forbid" rejects
    any raw payload, order / payment / invoice / customer / inventory / ledger
    field, or undeclared key). Materializing a task executes nothing, approves
    nothing, and sends nothing. Returns 201 when a new task was created, 200 when
    an existing ACTIVE task absorbed the event (idempotent replay).
    """
    result = services.upsert_task_from_event(event)
    if not result.created:
        # Idempotent replay against an existing active task: not a new resource.
        response.status_code = status.HTTP_200_OK
    return result


# -- P23-C source materialization (manual read/materialize; NOT a scheduler) ---


@router.post(
    "/internal/materialize",
    response_model=sources.MaterializeSummary,
)
async def materialize_route(
    request: Request,
    db: Any = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator),
) -> sources.MaterializeSummary:
    """P23-C: manually read the safe platform source surfaces and materialize
    operator tasks through the P23 service layer. READ-ONLY.

    Reads P19 in-memory approvals and the P22-E3 read-only backup.check source
    probe, maps them to typed, redacted intake events, and feeds them -- and only
    them -- through ``upsert_task_from_event``. The response summarizes per-source
    read / created / deduped / skipped / unavailable counts and the task ids
    touched. This is a manual read/materialize operation: it is NOT a scheduler,
    NOT a worker, executes nothing, approves nothing, delivers nothing, and
    mutates no product / tenant business data.

    ``db`` is the async session the backup.check probe reads through; it is typed
    ``Any`` so the P23 source tree stays free of a direct sqlalchemy import (a
    static AST guard requires that).
    """
    return await sources.materialize_all(db)
