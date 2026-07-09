"""FastAPI routes for P24 Incident + Runbook Closeout (P24-B skeleton).

NON-EXECUTING, NON-SENDING endpoints. Every route is behind the reused P10
identity-only platform-operator guard; P24 defines no new auth, token, session,
or role (no auth / RBAC rewrite). No route executes a P22 action, approves a
P19/P20/P21 approval, sets or clears the P17 ``incident_active`` flag, mutates a
registry field, delivers a notification, dispatches a worker, drains a queue,
runs shell / SQL / script, or reads / writes any tenant business / payment /
billing / product record.

The actor for every state-management transition is the authenticated identity
(read from the token via the reused P10 guard); it is NEVER read from the request
body (no identity spoof), mirroring the P20-B-R1 / P22 / P23 binding. Owner is
presentation only; it grants no new privilege.

Endpoints (all behind require_platform_operator):
  POST /api/v1/platform/p24/incident-closeouts/intake                            PUSH intake
  GET  /api/v1/platform/p24/incident-closeouts                                   list (filters)
  GET  /api/v1/platform/p24/incident-closeouts/{closeout_id}                     read detail
  GET  /api/v1/platform/p24/incident-closeouts/{closeout_id}/runbook             read steps
  POST /api/v1/platform/p24/incident-closeouts/{closeout_id}/self-assign         set owner
  POST /api/v1/platform/p24/incident-closeouts/{closeout_id}/transition          closeout judgment
  POST /api/v1/platform/p24/incident-closeouts/{closeout_id}/runbook/{step_id}/transition  step

Responses align to docs/ai/PLATFORM_PRODUCT_P24_INCIDENT_RUNBOOK_CLOSEOUT_CONTRACT.md
(P24-A, section 9).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from api.v1.platform.p10.guard import require_platform_operator

from . import services
from .schemas import (
    CloseoutTransitionRequest,
    IncidentCloseout,
    IncidentCloseoutDetail,
    IncidentCloseoutIntakeEvent,
    IncidentCloseoutIntakeResponse,
    IncidentCloseoutList,
    RunbookView,
    StepTransitionRequest,
)

router = APIRouter(
    prefix="/api/v1/platform/p24/incident-closeouts", tags=["platform-p24"]
)


# -- Identity helper (mirrors P20 / P22 / P23; the actor is the authenticated token) --


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


# -- PUSH intake (typed / redacted only; no raw payload) -----------------------


@router.post(
    "/intake",
    response_model=IncidentCloseoutIntakeResponse,
    status_code=status.HTTP_201_CREATED,
)
def intake_route(
    event: IncidentCloseoutIntakeEvent,
    request: Request,
    response: Response,
    _platform_auth: None = Depends(require_platform_operator),
) -> IncidentCloseoutIntakeResponse:
    """PUSH intake of a recorded closeout event (P24-A 5.1). Non-executing.

    Accepts ONLY the closed IncidentCloseoutIntakeEvent shape (extra="forbid"
    rejects any raw payload, order / payment / invoice / customer / inventory /
    ledger field, or undeclared key). The actor is read from the token, never
    from the body. Processing the event advances the in-memory closeout / step
    view and upserts P23 tasks via the existing seam; it executes nothing,
    approves nothing, flags nothing, and sends nothing.

    Returns 201 when a new closeout was created, 200 otherwise (idempotent replay
    or an event addressing an existing closeout).
    """
    actor_id, actor_role = _actor_context_and_role(request)
    result = services.ingest_event(event, actor_id=actor_id, actor_role=actor_role)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result


# -- Read / list ---------------------------------------------------------------


@router.get("", response_model=IncidentCloseoutList)
def list_closeouts_route(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: Optional[str] = Query(None, description="Filter by closeout state."),
    classification: Optional[str] = Query(None, description="Filter by P15 classification."),
    severity: Optional[str] = Query(None, description="Filter by severity."),
    tenant_id: Optional[str] = Query(None, description="Filter by scoped tenant_id."),
    flag_observed: Optional[str] = Query(None, description="Filter by observed flag mirror."),
    owner_actor_id: Optional[str] = Query(None, description="Filter by owner."),
    correlation_id: Optional[str] = Query(None, description="Filter by correlation_id."),
    _platform_auth: None = Depends(require_platform_operator),
) -> IncidentCloseoutList:
    """List incident closeouts with filters, ranked by severity then recency.

    Read-only; executes, approves, flags, mutates, and sends nothing.
    """
    return services.list_closeouts(
        limit=limit,
        offset=offset,
        state=state,
        classification=classification,
        severity=severity,
        tenant_id=tenant_id,
        flag_observed=flag_observed,
        owner_actor_id=owner_actor_id,
        correlation_id=correlation_id,
    )


@router.get("/{closeout_id}", response_model=IncidentCloseoutDetail)
def read_closeout_route(
    closeout_id: str,
    request: Request,
    _platform_auth: None = Depends(require_platform_operator),
) -> IncidentCloseoutDetail:
    """Read one closeout's redacted record, full audit history, and runbook steps.

    Read-only; executes nothing. withdrawn / expired closeouts retain their full
    audit history. Returns 404 when the closeout is not found.
    """
    detail = services.read_closeout(closeout_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "P24_CLOSEOUT_NOT_FOUND", "message": "Incident closeout not found."},
        )
    return detail


@router.get("/{closeout_id}/runbook", response_model=RunbookView)
def read_runbook_route(
    closeout_id: str,
    request: Request,
    _platform_auth: None = Depends(require_platform_operator),
) -> RunbookView:
    """Read the ordered runbook steps for one closeout. Read-only; executes nothing."""
    view = services.read_runbook(closeout_id)
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "P24_CLOSEOUT_NOT_FOUND", "message": "Incident closeout not found."},
        )
    return view


# -- State management (presentation-only) --------------------------------------


def _transition_response_status(accepted: bool) -> int:
    """200 when the transition changed state; 409 when it was denied."""
    return status.HTTP_200_OK if accepted else status.HTTP_409_CONFLICT


def _denial_http(exc_code: str) -> int:
    return status.HTTP_404_NOT_FOUND if exc_code in ("CLOSEOUT_NOT_FOUND", "STEP_NOT_FOUND") else status.HTTP_409_CONFLICT


@router.post(
    "/{closeout_id}/self-assign",
    response_model=IncidentCloseoutIntakeResponse,
)
def self_assign_route(
    closeout_id: str,
    request: Request,
    _platform_auth: None = Depends(require_platform_operator),
) -> IncidentCloseoutIntakeResponse:
    """Set the owner to the authenticated operator. Presentation only; runs nothing.

    Does not change the closeout state and grants no new privilege.
    """
    actor_id, actor_role = _actor_context_and_role(request)
    closeout, accepted, denial = services.self_assign_closeout(
        closeout_id, actor_id=actor_id, actor_role=actor_role,
    )
    if closeout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "P24_CLOSEOUT_NOT_FOUND", "message": "Incident closeout not found."
        })
    return IncidentCloseoutIntakeResponse(
        closeout=closeout, step=None, created=False, deduped=False,
        accepted=accepted, denial_code=denial,
    )


@router.post(
    "/{closeout_id}/transition",
    response_model=IncidentCloseoutIntakeResponse,
)
def closeout_transition_route(
    closeout_id: str,
    request: Request,
    payload: CloseoutTransitionRequest,
    _platform_auth: None = Depends(require_platform_operator),
) -> IncidentCloseoutIntakeResponse:
    """Record an operator closeout judgment (advance to awaiting_closeout / closed /
    withdrawn), subject to the transition rules (P24-A 3.3).

    Rejects (409) if the gate is still open: flag still set, owed tasks still
    non-terminal, source still unknown, or linked execution at backup_check_warning.
    Executes nothing; flips no flag.
    """
    actor_id, actor_role = _actor_context_and_role(request)
    closeout, accepted, denial, prev, nxt = services.apply_closeout_transition(
        closeout_id, target_state=payload.target_state,
        actor_id=actor_id, actor_role=actor_role, reason=payload.reason,
    )
    if closeout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "P24_CLOSEOUT_NOT_FOUND", "message": "Incident closeout not found."
        })
    if not accepted:
        raise HTTPException(status_code=_denial_http(denial or ""), detail={
            "code": denial,
            "message": f"{prev}->{payload.target_state}",
            "closeout": closeout.model_dump(mode="json"),
        })
    return IncidentCloseoutIntakeResponse(
        closeout=closeout, step=None, created=False, deduped=False,
        accepted=True, denial_code=None,
    )


@router.post(
    "/{closeout_id}/runbook/{step_id}/transition",
    response_model=IncidentCloseoutIntakeResponse,
)
def step_transition_route(
    closeout_id: str,
    step_id: str,
    request: Request,
    payload: StepTransitionRequest,
    _platform_auth: None = Depends(require_platform_operator),
) -> IncidentCloseoutIntakeResponse:
    """Record a runbook step state change with a redacted evidence / observation
    note (P24-A 9). Rejects a ``done`` on an action_pointer whose execution is not
    observed terminal, on an approval_pointer whose approval is not observed
    resolved, or on an observation step without an evidence note. Executes nothing.
    """
    actor_id, actor_role = _actor_context_and_role(request)
    step, accepted, denial, prev, nxt = services.apply_step_transition(
        closeout_id, step_id, target_state=payload.target_state,
        actor_id=actor_id, actor_role=actor_role,
        evidence=payload.evidence, reason=payload.reason,
    )
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "code": "P24_STEP_NOT_FOUND", "message": "Runbook step not found for this closeout."
        })
    if not accepted:
        raise HTTPException(status_code=_denial_http(denial or ""), detail={
            "code": denial,
            "message": f"{prev}->{payload.target_state}",
            "step": step.model_dump(mode="json"),
        })
    closeout = services.read_closeout(closeout_id)
    closeout_view = IncidentCloseout(
        **{k: v for k, v in closeout.model_dump().items() if k in IncidentCloseout.model_fields}
    ) if closeout is not None else None
    return IncidentCloseoutIntakeResponse(
        closeout=closeout_view,  # type: ignore[arg-type]
        step=step, created=False, deduped=False, accepted=True, denial_code=None,
    )
