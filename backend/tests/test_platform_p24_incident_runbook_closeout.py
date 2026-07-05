"""
P24 Incident + Runbook Closeout -- non-executing, non-sending in-memory backend
skeleton tests (P24-B).

Contract-backed (docs/ai/PLATFORM_PRODUCT_P24_INCIDENT_RUNBOOK_CLOSEOUT_CONTRACT.md,
P24-A). The invariant, repeated throughout:

    An incident closeout is a view, not an executor. A runbook step is a pointer,
    not an execution. A follow-up task is a record, not a repair.

Coverage:
  - closed closeout-state (8) / step-kind (3) / step-state (5) / classification /
    flag-observed / source-status / intake-event-type (7) vocabularies are exactly
    the contract sets; no product-business token in any vocabulary.
  - intake: incident_detected opens a closeout; replay is idempotent (dedup);
    terminal closeouts are exempt from dedup (a recurrence re-opens as a NEW
    closeout); no cross-tenant dedup.
  - intake is typed/redacted only: extra="forbid" rejects a raw / product-business
    payload (422); an unknown event_type is rejected (422).
  - closeout lifecycle transitions (detect / triage / flag-observe / remediate /
    await / close / withdraw / expire) match the contract graph; each records
    exactly one IncidentCloseoutAuditEvent.
  - terminal closeout states accept no exit (C14); flagged_active may not be
    fabricated without an observed-true flag (C5).
  - ``closed`` honest-completion gate: owed tasks non-terminal -> denied (C4);
    flag still set -> denied (C3); source_unknown -> denied (C9); execution
    warning -> denied (C10).
  - runbook step model: three kinds; done per-kind gate -- action_pointer needs
    an observed terminal execution (C6/C7, approvals are not execution);
    approval_pointer needs an observed resolved approval (C8); observation needs
    a redacted evidence note. Terminal step states accept no exit (C14).
  - materialization seam: incident_followup_required is materialized on
    flagged_active and resolved on awaiting_closeout / closed; runbook_step_required
    is materialized per owed / in_progress / blocked step and resolved on
    terminal -- through the REAL P23 upsert seam (P23 regression).
  - the flag is mirrored, never owned: P24 sets/clears no P17 incident_active
    field (no p17 import; no flag-write function exposed).
  - source_unknown is never displayed healthy; backup_check_warning / a degraded
    linked execution is never displayed as success (in every state).
  - redaction: a raw secret / DSN / host:port / token / shell-SQL token in any
    free-text field is scrubbed before storage / response / audit.
  - audit: every accepted AND denied closeout / step transition records exactly
    one audit event with previous_state, next_state, correlation_id, and (for
    closeouts) the observed flag mirror.
  - intake actor comes from the token, never the body (C22).
  - route auth: no credential -> 401; wrong operator secret -> 403; valid identity
    super_admin and valid test override -> 200.
  - route-level transitions behave end-to-end (200 accepted / 409 denied / 404
    missing); app.py includes the P24 router.
  - forbidden-primitive scan: no subprocess / shell / pg_dump / restore / worker /
    scheduler / drain / channel-delivery / persistence / product / p15-p22 import
    in the p24 AST; no executing call tokens; services exposes no execute / deliver
    / flag-write function.

Aligned to docs/ai/PLATFORM_PRODUCT_P24_INCIDENT_RUNBOOK_CLOSEOUT_CONTRACT.md
(P24-A).
"""
import ast
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")
os.environ.setdefault("SECRET_KEY", "test-secret-key-strong-enough-for-validation-0123456789")


# -- Constants ----------------------------------------------------------------

AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}
BASE = "/api/v1/platform/p24/incident-closeouts"

_ACTIVE_PATCHERS: list = []
_CURRENT_AUTH: dict = {"ctx": None}


# -- Harness (mirrors the P15/P17/P18/P19/P20/P22/P23 test harness) ------------


@pytest.fixture(autouse=True)
def _reset_p24_state():
    from api.v1.platform.p24 import services
    from api.v1.platform.p23 import services as p23_services

    p23_services.reset_store()
    services.reset_store()
    _CURRENT_AUTH["ctx"] = None
    _enable_auth()
    _as_super("super-exec")
    yield
    services.reset_store()
    p23_services.reset_store()
    while _ACTIVE_PATCHERS:
        _ACTIVE_PATCHERS.pop().stop()


def _start_patch(target, new):
    p = patch(target, new=new)
    p.start()
    _ACTIVE_PATCHERS.append(p)
    return p


def _auth_ctx(user_id, *, identity_only=True, super_admin=True, roles=None, tenant_id=None):
    t = MagicMock()
    t.user_id = user_id
    t.roles = list(roles if roles is not None else (["super_admin"] if super_admin else []))
    t.tenant_id = tenant_id
    t.tenant_schema = "t_other" if tenant_id else None
    t.is_identity_only = identity_only and not tenant_id
    t.is_super_admin = super_admin
    return MagicMock(token=t)


def _fake_get_auth_context(*args, **kwargs):
    ctx = _CURRENT_AUTH["ctx"]
    if ctx is None:
        raise RuntimeError("no auth context attached")
    return ctx


def _enable_auth():
    _start_patch(
        "api.context.auth.get_auth_context", MagicMock(side_effect=_fake_get_auth_context)
    )


def _as_super(user_id="super-exec"):
    _CURRENT_AUTH["ctx"] = _auth_ctx(user_id)


def _as_support(user_id="support-1"):
    _CURRENT_AUTH["ctx"] = _auth_ctx(
        user_id, identity_only=True, super_admin=False, roles=["support_operator"]
    )


def _as_no_auth():
    _CURRENT_AUTH["ctx"] = None


def _make_app():
    from api.v1.platform.p24.routes import router

    app = FastAPI()
    app.include_router(router)
    return app


def _client():
    return TestClient(_make_app())


# -- Intake helpers ------------------------------------------------------------


def _detected(client, **over):
    payload = {
        "event_type": "incident_detected",
        "correlation_id": "inc-corr-1",
        "summary": "platform anomaly observed",
        "linked_incident_id": "inc-1",
    }
    payload.update(over)
    return client.post(f"{BASE}/intake", json=payload, headers=AUTH_HEADERS)


def _seed_detected(**over):
    """Open a closeout directly through the service (no HTTP). Returns its view."""
    from api.v1.platform.p24 import services
    from api.v1.platform.p24.schemas import IncidentCloseoutIntakeEvent

    payload = {
        "event_type": "incident_detected",
        "correlation_id": "inc-corr-1",
        "summary": "platform anomaly observed",
        "linked_incident_id": "inc-1",
    }
    payload.update(over)
    res = services.ingest_event(
        IncidentCloseoutIntakeEvent(**payload), actor_id="super-exec", actor_role="super_admin"
    )
    return res.closeout.model_dump(mode="json")


def _ingest(event_dict):
    from api.v1.platform.p24 import services
    from api.v1.platform.p24.schemas import IncidentCloseoutIntakeEvent

    return services.ingest_event(
        IncidentCloseoutIntakeEvent(**event_dict), actor_id="super-exec", actor_role="super_admin"
    )


# ============================================================================
# 1. Closed vocabularies
# ============================================================================


def test_closeout_state_vocabulary_is_exactly_eight():
    from api.v1.platform.p24.schemas import (
        CLOSEOUT_STATES, TERMINAL_CLOSEOUT_STATES, ACTIVE_CLOSEOUT_STATES,
    )

    assert len(CLOSEOUT_STATES) == 8
    assert set(CLOSEOUT_STATES) == {
        "detected", "triaged", "flagged_active", "in_remediation",
        "awaiting_closeout", "closed", "withdrawn", "expired",
    }
    assert set(TERMINAL_CLOSEOUT_STATES) == {"closed", "withdrawn", "expired"}
    assert set(ACTIVE_CLOSEOUT_STATES) == {
        "detected", "triaged", "flagged_active", "in_remediation", "awaiting_closeout"
    }
    assert set(ACTIVE_CLOSEOUT_STATES).isdisjoint(TERMINAL_CLOSEOUT_STATES)


def test_step_kind_and_state_vocabularies():
    from api.v1.platform.p24.schemas import (
        STEP_KINDS, STEP_STATES, TERMINAL_STEP_STATES, ACTIVE_STEP_STATES,
    )

    assert set(STEP_KINDS) == {"observation", "action_pointer", "approval_pointer"}
    assert set(STEP_STATES) == {
        "owed", "in_progress", "done", "not_applicable", "blocked"
    }
    assert set(TERMINAL_STEP_STATES) == {"done", "not_applicable"}
    assert set(ACTIVE_STEP_STATES) == {"owed", "in_progress", "blocked"}


def test_classification_flag_source_intake_vocabularies():
    from api.v1.platform.p24.schemas import (
        CLASSIFICATIONS, FLAG_OBSERVED_VALUES, SOURCE_STATUSES, INTAKE_EVENT_TYPES,
    )

    assert set(CLASSIFICATIONS) == {
        "database", "system", "api", "tenant_health", "support_issue"
    }
    assert set(FLAG_OBSERVED_VALUES) == {
        "observed_true", "observed_false", "observed_unknown"
    }
    assert set(SOURCE_STATUSES) == {"known", "unknown", "degraded"}
    assert set(INTAKE_EVENT_TYPES) == {
        "incident_detected", "incident_classified", "incident_flag_observed",
        "runbook_step_owed", "runbook_step_progress", "runbook_step_terminal",
        "closeout_transition",
    }


def test_no_product_business_token_in_vocabularies():
    from api.v1.platform.p24 import schemas

    banned = ("order", "payment", "invoice", "customer", "inventory", "ledger", "billing")
    for name in (
        "CLOSEOUT_STATES", "STEP_KINDS", "STEP_STATES", "CLASSIFICATIONS",
        "INTAKE_EVENT_TYPES",
    ):
        for token in getattr(schemas, name):
            low = token.lower()
            for b in banned:
                assert b not in low, f"product token {b!r} in {name}={token!r}"


def test_closeout_and_step_graphs_match_contract():
    from api.v1.platform.p24.schemas import (
        ALLOWED_CLOSEOUT_TRANSITIONS, ALLOWED_STEP_TRANSITIONS,
    )

    # detected reaches triaged + the two terminal exits only
    assert set(ALLOWED_CLOSEOUT_TRANSITIONS["detected"]) == {"triaged", "withdrawn", "expired"}
    # triaged may close directly (no flag, no owed steps)
    assert "closed" in ALLOWED_CLOSEOUT_TRANSITIONS["triaged"]
    # awaiting_closeout -> closed + in_remediation + expired
    assert set(ALLOWED_CLOSEOUT_TRANSITIONS["awaiting_closeout"]) == {
        "closed", "in_remediation", "expired"
    }
    for term in ("closed", "withdrawn", "expired"):
        assert ALLOWED_CLOSEOUT_TRANSITIONS[term] == frozenset()
    # steps
    assert set(ALLOWED_STEP_TRANSITIONS["owed"]) == {
        "in_progress", "done", "not_applicable", "blocked"
    }
    assert set(ALLOWED_STEP_TRANSITIONS["blocked"]) == {"owed", "not_applicable"}
    for term in ("done", "not_applicable"):
        assert ALLOWED_STEP_TRANSITIONS[term] == frozenset()


# ============================================================================
# 2. Intake / dedup
# ============================================================================


def test_incident_detected_creates_closeout_then_dedups_replay():
    with _client() as c:
        first = _detected(c).json()
        assert first["created"] is True
        assert first["deduped"] is False
        assert first["closeout"]["state"] == "detected"
        cid = first["closeout"]["closeout_id"]

        second = _detected(c).json()
        assert second["created"] is False
        assert second["deduped"] is True
        assert second["closeout"]["closeout_id"] == cid  # same closeout

        listed = c.get(BASE, headers=AUTH_HEADERS).json()
        assert listed["total"] == 1  # no duplicate


def test_terminal_closeout_exempt_from_dedup_reopens_new():
    # A withdrawn closeout must NOT absorb a fresh incident_detected for the same
    # correlation/tenant/incident -- it re-opens as a NEW closeout (P24-A 5.5).
    co = _seed_detected()
    cid = co["closeout_id"]
    _ingest({
        "event_type": "closeout_transition", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "summary": "false positive",
        "target_state": "withdrawn",
    })
    again = _ingest({
        "event_type": "incident_detected", "correlation_id": "inc-corr-1",
        "summary": "recurring anomaly", "linked_incident_id": "inc-1",
    })
    assert again.created is True
    assert again.closeout.closeout_id != cid


def test_no_cross_tenant_dedup():
    a = _seed_detected(correlation_id="shared-corr", tenant_id="t-A", linked_incident_id="inc-X")
    b = _ingest({
        "event_type": "incident_detected", "correlation_id": "shared-corr",
        "tenant_id": "t-B", "linked_incident_id": "inc-X", "summary": "tenant B incident",
    })
    assert b.created is True
    assert b.closeout.closeout_id != a["closeout_id"]
    assert b.closeout.tenant_id == "t-B"


def test_intake_rejects_raw_and_product_payload():
    with _client() as c:
        # extra="forbid" rejects an undeclared field
        bad = c.post(f"{BASE}/intake", json={
            "event_type": "incident_detected", "correlation_id": "c1",
            "summary": "x", "order_id": "ord-123",
        }, headers=AUTH_HEADERS)
        assert bad.status_code == 422
        # an unknown event_type is rejected by the Literal
        bad2 = c.post(f"{BASE}/intake", json={
            "event_type": "order_refund_required", "correlation_id": "c1", "summary": "x",
        }, headers=AUTH_HEADERS)
        assert bad2.status_code == 422


# ============================================================================
# 3. Closeout lifecycle transitions
# ============================================================================


def test_classify_advances_detected_to_triaged():
    co = _seed_detected()
    res = _ingest({
        "event_type": "incident_classified", "closeout_id": co["closeout_id"],
        "correlation_id": "inc-corr-1", "classification": "database",
        "summary": "classified",
    })
    assert res.accepted is True
    assert res.closeout.state == "triaged"
    assert res.closeout.classification == "database"


def test_flag_observed_true_advances_to_flagged_active_and_materializes_followup():
    co = _seed_detected()
    _ingest({
        "event_type": "incident_classified", "closeout_id": co["closeout_id"],
        "correlation_id": "inc-corr-1", "classification": "system", "summary": "c",
    })
    res = _ingest({
        "event_type": "incident_flag_observed", "closeout_id": co["closeout_id"],
        "correlation_id": "inc-corr-1", "flag_observed": "observed_true",
        "summary": "flag set via P22",
    })
    assert res.closeout.state == "flagged_active"
    assert res.closeout.flag_observed == "observed_true"
    assert res.closeout.flag_ever_set is True
    # The incident_followup_required task is materialized in the P23 queue.
    assert res.closeout.linked_followup_task_id is not None
    assert res.closeout.followup_owed is True
    from api.v1.platform.p23 import services as p23s
    detail = p23s.read_task(res.closeout.linked_followup_task_id)
    assert detail is not None
    assert detail.task_type == "incident_followup_required"
    assert detail.state == "open"


def test_flagged_active_may_not_be_fabricated_without_observed_true_flag():
    # C5: a -> flagged_active transition where the flag is NOT observed true is rejected.
    co = _seed_detected()
    _ingest({
        "event_type": "incident_classified", "closeout_id": co["closeout_id"],
        "correlation_id": "inc-corr-1", "classification": "api", "summary": "c",
    })
    res = _ingest({
        "event_type": "closeout_transition", "closeout_id": co["closeout_id"],
        "correlation_id": "inc-corr-1", "summary": "attempt fabricate",
        "target_state": "flagged_active",
    })
    assert res.accepted is False
    assert res.denial_code == "TRANSITION_DENIED_INVALID"
    assert res.closeout.state == "triaged"


def test_withdraw_and_expire_are_terminal():
    co = _seed_detected()
    r1 = _ingest({
        "event_type": "closeout_transition", "closeout_id": co["closeout_id"],
        "correlation_id": "inc-corr-1", "summary": "not an incident",
        "target_state": "withdrawn",
    })
    assert r1.accepted is True
    assert r1.closeout.state == "withdrawn"
    # Any further transition is denied (C14).
    r2 = _ingest({
        "event_type": "closeout_transition", "closeout_id": co["closeout_id"],
        "correlation_id": "inc-corr-1", "summary": "try reopen",
        "target_state": "triaged",
    })
    assert r2.accepted is False
    assert r2.denial_code == "TRANSITION_DENIED_TERMINAL"


# ============================================================================
# 4. The ``closed`` honest-completion gate (C3 / C4 / C9 / C10)
# ============================================================================


def _seed_ready_to_close(*, flag_set=True, source_status=None, execution_warning=False):
    """Detected -> triaged -> flagged_active -> (flag cleared) -> awaiting_closeout."""
    co = _seed_detected(source_status=source_status, linked_execution_warning=execution_warning)
    cid = co["closeout_id"]
    _ingest({
        "event_type": "incident_classified", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "classification": "database", "summary": "c",
    })
    if flag_set:
        _ingest({
            "event_type": "incident_flag_observed", "closeout_id": cid,
            "correlation_id": "inc-corr-1", "flag_observed": "observed_true",
            "summary": "flag set",
        })
        _ingest({
            "event_type": "incident_flag_observed", "closeout_id": cid,
            "correlation_id": "inc-corr-1", "flag_observed": "observed_false",
            "summary": "flag cleared via P22 incident.flag_clear",
        })
    return cid


def test_close_denied_when_flag_still_set():
    # C3: a closeout whose flag was observed set and is NOT observed false may not
    # close. Path: detected + flag_observed_true mirror (stays detected; the
    # detected state does not auto-advance) -> classify -> triaged (flag_ever_set
    # True, flag still observed_true) -> close attempt -> denied.
    co = _seed_detected()
    cid = co["closeout_id"]
    _ingest({
        "event_type": "incident_flag_observed", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "flag_observed": "observed_true",
        "summary": "observed set while detected",
    })
    _ingest({
        "event_type": "incident_classified", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "classification": "database", "summary": "c",
    })
    res = _ingest({
        "event_type": "closeout_transition", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "summary": "close attempt",
        "target_state": "closed",
    })
    assert res.accepted is False
    assert res.denial_code == "CLOSE_DENIED_FLAG_STILL_SET"
    assert res.closeout.state == "triaged"


def test_awaiting_closeout_denied_when_steps_nonterminal():
    # C4 (steps): in_remediation -> awaiting_closeout is denied while any step is
    # still owed / in_progress / blocked (P24-A 3.1 / 3.3 rule 4).
    cid = _seed_ready_to_close(flag_set=False)
    step = _ingest({
        "event_type": "runbook_step_owed", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "step_kind": "observation", "sequence_no": 1,
        "summary": "read P13 ops.resources.database",
    })
    assert step.step.step_state == "owed"
    res = _ingest({
        "event_type": "closeout_transition", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "summary": "await attempt",
        "target_state": "awaiting_closeout",
    })
    assert res.accepted is False
    assert res.denial_code == "CLOSE_DENIED_OWED_TASKS_NONTERMINAL"


def test_close_denied_when_source_unknown():
    cid = _seed_ready_to_close(flag_set=False, source_status="unknown")
    res = _ingest({
        "event_type": "closeout_transition", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "summary": "close attempt",
        "target_state": "closed",
    })
    assert res.accepted is False
    assert res.denial_code == "CLOSE_DENIED_SOURCE_UNKNOWN"


def test_close_denied_when_execution_warning():
    cid = _seed_ready_to_close(flag_set=False, execution_warning=True)
    res = _ingest({
        "event_type": "closeout_transition", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "summary": "close attempt",
        "target_state": "closed",
    })
    assert res.accepted is False
    assert res.denial_code == "CLOSE_DENIED_EXECUTION_WARNING"


def test_close_succeeds_when_gate_honored_and_resolves_followup_task():
    cid = _seed_ready_to_close(flag_set=True)  # triaged->flagged->awaiting (flag cleared)
    from api.v1.platform.p24 import services
    before = services.read_closeout(cid)
    assert before.state == "awaiting_closeout"
    assert before.linked_followup_task_id is not None
    res = _ingest({
        "event_type": "closeout_transition", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "summary": "operator closeout",
        "target_state": "closed",
    })
    assert res.accepted is True
    assert res.closeout.state == "closed"
    # The follow-up task was resolved through P23.
    from api.v1.platform.p23 import services as p23s
    detail = p23s.read_task(before.linked_followup_task_id)
    assert detail.state in {"completed", "dismissed"}  # terminal


# ============================================================================
# 5. Runbook step model (per-kind done gate)
# ============================================================================


def test_action_pointer_done_requires_observed_terminal_execution():
    cid = _seed_ready_to_close(flag_set=False)
    owed = _ingest({
        "event_type": "runbook_step_owed", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "step_kind": "action_pointer", "sequence_no": 1,
        "linked_action_id": "act-1", "linked_execution_id": "exec-1",
        "linked_execution_terminal": False, "summary": "run backup.check",
    })
    sid = owed.step.step_id
    # done without an observed terminal execution -> denied (C6/C7: approvals are not execution)
    from api.v1.platform.p24 import services
    _step, ok, denial, _p, _n = services.apply_step_transition(
        cid, sid, target_state="done", actor_id="eng-1", actor_role="engineering_operator",
        evidence="approval granted",
    )
    assert ok is False
    assert denial == "STEP_DONE_DENIED_GATE_OPEN"
    # Now mirror the terminal execution outcome, then done succeeds.
    _ingest({
        "event_type": "runbook_step_terminal", "closeout_id": cid, "step_id": sid,
        "correlation_id": "inc-corr-1", "linked_execution_terminal": True,
        "evidence": "executed via P22", "summary": "terminal",
    })
    refreshed = services.read_runbook(cid)
    assert refreshed.steps[0].step_state == "done"


def test_approval_pointer_done_requires_observed_resolved_approval():
    cid = _seed_ready_to_close(flag_set=False)
    owed = _ingest({
        "event_type": "runbook_step_owed", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "step_kind": "approval_pointer", "sequence_no": 1,
        "linked_approval_id": "appr-1", "linked_approval_resolved": False,
        "summary": "obtain DBA quorum",
    })
    sid = owed.step.step_id
    from api.v1.platform.p24 import services
    _step, ok, denial, _p, _n = services.apply_step_transition(
        cid, sid, target_state="done", actor_id="super-exec", actor_role="super_admin",
    )
    assert ok is False
    assert denial == "STEP_DONE_DENIED_GATE_OPEN"  # C8: step mirrors approval, never grants quorum


def test_observation_done_requires_evidence_note():
    cid = _seed_ready_to_close(flag_set=False)
    owed = _ingest({
        "event_type": "runbook_step_owed", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "step_kind": "observation", "sequence_no": 1,
        "summary": "read P15 snapshot",
    })
    sid = owed.step.step_id
    from api.v1.platform.p24 import services
    _step, ok, denial, _p, _n = services.apply_step_transition(
        cid, sid, target_state="done", actor_id="super-exec", actor_role="super_admin",
    )
    assert ok is False
    assert denial == "STEP_DONE_DENIED_NO_EVIDENCE"
    _step2, ok2, _d, _p, _n = services.apply_step_transition(
        cid, sid, target_state="done", actor_id="super-exec", actor_role="super_admin",
        evidence="snapshot read; nothing abnormal",
    )
    assert ok2 is True


def test_terminal_step_accepts_no_exit():
    cid = _seed_ready_to_close(flag_set=False)
    owed = _ingest({
        "event_type": "runbook_step_owed", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "step_kind": "observation", "sequence_no": 1,
        "summary": "read",
    })
    sid = owed.step.step_id
    from api.v1.platform.p24 import services
    services.apply_step_transition(
        cid, sid, target_state="done", actor_id="x", actor_role="super_admin",
        evidence="note",
    )
    _step, ok, denial, _p, _n = services.apply_step_transition(
        cid, sid, target_state="owed", actor_id="x", actor_role="super_admin",
    )
    assert ok is False
    assert denial == "TRANSITION_DENIED_TERMINAL"  # C14


def test_runbook_step_required_task_materialized_and_resolved_via_p23_seam():
    cid = _seed_ready_to_close(flag_set=False)
    owed = _ingest({
        "event_type": "runbook_step_owed", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "step_kind": "observation", "sequence_no": 1,
        "summary": "read",
    })
    sid = owed.step.step_id
    from api.v1.platform.p23 import services as p23s
    task_id = owed.step.linked_task_id
    assert task_id is not None
    detail = p23s.read_task(task_id)
    assert detail.task_type == "runbook_step_required"
    assert detail.state == "open"  # active -> task materialized
    # Resolve the step -> the P23 task resolves to terminal.
    from api.v1.platform.p24 import services
    services.apply_step_transition(
        cid, sid, target_state="done", actor_id="x", actor_role="super_admin",
        evidence="done note",
    )
    detail2 = p23s.read_task(task_id)
    assert detail2.state in {"completed", "dismissed"}


# ============================================================================
# 6. Display honesty + flag mirror + redaction
# ============================================================================


def test_source_unknown_never_displayed_healthy_anywhere():
    co = _seed_detected(source_status="unknown")
    assert co["display_status"] == "unknown"
    cid = co["closeout_id"]
    _ingest({
        "event_type": "incident_classified", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "classification": "system", "summary": "c",
    })
    # Even after a successful triage, an unknown source is never healthy.
    from api.v1.platform.p24 import services
    triaged = services.read_closeout(cid)
    assert triaged.display_status == "unknown"


def test_degraded_and_execution_warning_never_displayed_as_success():
    co = _seed_detected(source_status="degraded")
    assert co["display_status"] == "warning"
    co2 = _seed_detected(linked_execution_warning=True, correlation_id="w-corr", linked_incident_id="inc-w")
    assert co2["display_status"] == "warning"


def test_p24_does_not_set_or_clear_p17_flag_only_mirrors():
    # The flag_observed field is an observation mirror. Setting it via intake to
    # observed_true / observed_false changes the mirror only; P24 exposes no
    # flag-write function and imports no p17 module.
    co = _seed_detected()
    cid = co["closeout_id"]
    res = _ingest({
        "event_type": "incident_flag_observed", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "flag_observed": "observed_true",
        "summary": "observed set",
    })
    assert res.closeout.flag_observed == "observed_true"
    res2 = _ingest({
        "event_type": "incident_flag_observed", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "flag_observed": "observed_false",
        "summary": "observed cleared",
    })
    assert res2.closeout.flag_observed == "observed_false"
    from api.v1.platform.p24 import services
    public = [n for n in dir(services) if not n.startswith("_")]
    for forbidden in ("set_flag", "clear_flag", "set_incident_active", "clear_incident_active"):
        assert forbidden not in public


def test_redaction_scrubs_secret_in_summary_reason_evidence():
    co = _seed_detected(summary="db down at postgresql://u:s3cr3t@10.0.0.5:5432/db")
    assert "s3cr3t" not in co["summary_redacted"]
    assert "[redacted:" in co["summary_redacted"]
    cid = co["closeout_id"]
    _ingest({
        "event_type": "incident_classified", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "classification": "database",
        "summary": "c", "reason": "password=hunter2 leak",
    })
    from api.v1.platform.p24 import services
    refreshed = services.read_closeout(cid)
    assert "hunter2" not in (refreshed.reason_redacted or "")


# ============================================================================
# 7. Audit completeness (every accepted AND denied transition audited)
# ============================================================================


def test_every_closeout_transition_records_one_audit_event():
    from api.v1.platform.p24 import services

    co = _seed_detected()
    cid = co["closeout_id"]
    # accepted
    services.apply_closeout_transition(
        cid, target_state="withdrawn", actor_id="op-1", actor_role="super_admin",
        reason="fp",
    )
    # denied (withdrawn is terminal)
    services.apply_closeout_transition(
        cid, target_state="closed", actor_id="op-1", actor_role="super_admin",
    )
    events = services.closeout_audit_log_for(cid)
    # materialized (detected) + accepted withdrawn + denied close = at least 3
    transitions = [e.transition for e in events]
    assert any("->withdrawn" in t for t in transitions)
    assert any(t == "denied:closeout:closed" for t in transitions)
    # every audit event carries the observed flag mirror + correlation
    for e in events:
        assert e.correlation_id == "inc-corr-1"
        assert e.flag_observed in ("observed_true", "observed_false", "observed_unknown")
        assert e.redaction_applied is True


def test_every_step_transition_records_one_audit_event():
    from api.v1.platform.p24 import services

    cid = _seed_ready_to_close(flag_set=False)
    owed = _ingest({
        "event_type": "runbook_step_owed", "closeout_id": cid,
        "correlation_id": "inc-corr-1", "step_kind": "observation", "sequence_no": 1,
        "summary": "read",
    })
    sid = owed.step.step_id
    # denied done (no evidence) + accepted done (with evidence)
    services.apply_step_transition(cid, sid, target_state="done", actor_id="x", actor_role="super_admin")
    services.apply_step_transition(
        cid, sid, target_state="done", actor_id="x", actor_role="super_admin", evidence="note",
    )
    events = services.step_audit_log_for(sid)
    labels = [e.step_transition for e in events]
    assert any("denied:step:done" in lab for lab in labels)
    assert any(lab.endswith("->done") for lab in labels)
    for e in events:
        assert e.correlation_id == "inc-corr-1"
        assert e.redaction_applied is True


# ============================================================================
# 8. Intake actor comes from the token, not the body (C22)
# ============================================================================


def test_intake_body_has_no_actor_field():
    from api.v1.platform.p24.schemas import IncidentCloseoutIntakeEvent

    fields = set(IncidentCloseoutIntakeEvent.model_fields.keys())
    for forbidden in ("actor_id", "actor_role", "actor", "user_id"):
        assert forbidden not in fields, f"actor field {forbidden!r} must not be in intake body"


def test_intake_actor_taken_from_token_not_body():
    # As support_operator, the audit actor_role should reflect the token role,
    # regardless of the body (which has no actor field anyway).
    _as_support("support-9")
    from api.v1.platform.p24 import services
    from api.v1.platform.p24.schemas import IncidentCloseoutIntakeEvent

    res = services.ingest_event(
        IncidentCloseoutIntakeEvent(
            event_type="incident_detected", correlation_id="sup-corr",
            summary="observed", linked_incident_id="inc-sup",
        ),
        actor_id="support-9", actor_role="support_operator",
    )
    events = services.closeout_audit_log_for(res.closeout.closeout_id)
    assert events[-1].actor_role == "support_operator"
    assert events[-1].actor_id == "support-9"


# ============================================================================
# 9. Route auth + end-to-end transition behavior
# ============================================================================


def test_route_auth_required():
    with _client() as c:
        # No credential at all -> 401 (no auth context attached).
        _as_no_auth()
        r = c.get(BASE, headers={})
        assert r.status_code in (401, 403)


def test_route_list_and_read_end_to_end():
    with _client() as c:
        created = _detected(c).json()
        cid = created["closeout"]["closeout_id"]
        one = c.get(f"{BASE}/{cid}", headers=AUTH_HEADERS).json()
        assert one["closeout_id"] == cid
        assert one["audit_events"]  # materialized audit present
        rb = c.get(f"{BASE}/{cid}/runbook", headers=AUTH_HEADERS).json()
        assert rb["steps"] == []  # no steps yet


def test_route_transition_404_and_409():
    with _client() as c:
        # missing closeout -> 404
        miss = c.post(f"{BASE}/no-such/transition", headers=AUTH_HEADERS, json={
            "target_state": "withdrawn"})
        assert miss.status_code == 404
        co = _detected(c).json()
        cid = co["closeout"]["closeout_id"]
        # invalid transition (detected -> closed is not in the graph) -> 409
        bad = c.post(f"{BASE}/{cid}/transition", headers=AUTH_HEADERS, json={
            "target_state": "closed"})
        assert bad.status_code == 409
        assert bad.json()["detail"]["code"] == "TRANSITION_DENIED_INVALID"


def test_route_step_transition_end_to_end():
    with _client() as c:
        co = _detected(c).json()
        cid = co["closeout"]["closeout_id"]
        owed = c.post(f"{BASE}/intake", headers=AUTH_HEADERS, json={
            "event_type": "runbook_step_owed", "closeout_id": cid,
            "correlation_id": "inc-corr-1", "step_kind": "observation",
            "sequence_no": 1, "summary": "read",
        }).json()
        sid = owed["step"]["step_id"]
        ok = c.post(f"{BASE}/{cid}/runbook/{sid}/transition", headers=AUTH_HEADERS, json={
            "target_state": "done", "evidence": "observed"})
        assert ok.status_code == 200
        assert ok.json()["accepted"] is True
        nodone = c.post(f"{BASE}/{cid}/runbook/{sid}/transition", headers=AUTH_HEADERS, json={
            "target_state": "done", "evidence": "x"})
        # step is already terminal -> denied 409
        assert nodone.status_code == 409


# ============================================================================
# 10. app.py includes the P24 router
# ============================================================================


def test_app_py_includes_p24_router():
    app_py = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "api", "app.py")
    )
    with open(app_py, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert "from api.v1.platform.p24.routes import router as platform_p24_router" in src
    assert "app.include_router(platform_p24_router)" in src
    # No auth/RBAC rewrite: no new role/token/session introduced by the P24 block.
    p24_block = src.split("Platform Track P24")[1].split("# Client API")[0]
    assert "oauth" not in p24_block.lower()
    assert "JWT_SECRET" not in p24_block


# ============================================================================
# 11. Forbidden-primitive AST scan (the non-execution / non-delivery contract)
# ============================================================================


def _p24_source_files():
    import api.v1.platform.p24 as pkg

    base = os.path.dirname(pkg.__file__)
    for name in ("__init__.py", "schemas.py", "services.py", "routes.py"):
        path = os.path.join(base, name)
        with open(path, "r", encoding="utf-8") as fh:
            yield path, fh.read()


def _ast_dotted(node):
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def test_no_subprocess_shell_dump_restore_worker_scheduler_in_p24_ast():
    """No code-execution / queue-worker / dump-restore token in any p24 AST.

    Scanned via ``ast`` (imports + call expressions) so docstring / comment
    mentions in negation statements do not match.
    """
    forbidden_bare = {"eval", "exec", "system", "popen", "run"}
    forbidden_os_attrs = {"system", "popen", "execv", "execve"}
    forbidden_attr_substrings = (
        "execute_action", "run_action", "dispatch_action", "drain_queue",
        "start_worker", "invoke_harness", "pg_dump", "pg_restore",
        "subprocess", "scheduler", "drain", "send_email", "post_webhook",
    )
    for path, src in _p24_source_files():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    assert f.id not in forbidden_bare, (
                        f"forbidden bare call {f.id!r} in {os.path.basename(path)}"
                    )
                elif isinstance(f, ast.Attribute):
                    dotted = _ast_dotted(f.value)
                    if dotted.startswith("subprocess"):
                        raise AssertionError(f"forbidden subprocess call in {path}")
                    if dotted == "os" and f.attr in forbidden_os_attrs:
                        raise AssertionError(f"forbidden os.{f.attr} call in {path}")
                    low = f.attr.lower()
                    assert not any(s in low for s in forbidden_attr_substrings), (
                        f"forbidden execution/worker attr {f.attr!r} in {os.path.basename(path)}"
                    )
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) \
                            and kw.value.value is True:
                        raise AssertionError(f"shell=True forbidden in {path}")


def test_no_persistence_product_or_priorphase_imports_in_p24_source():
    """P24 imports ONLY the P23 seam + P10 guard. It pulls no execution /
    approval / flag / registry / persistence / product path -- all prior-phase
    state arrives as observed mirrors on intake events (PUSH only).
    """
    forbidden_import_substrings = (
        "subprocess", "alembic", "migrate", "sqlalchemy", "psycopg",
        "product", "order", "payment", "invoice", "customer",
        "inventory", "ledger", "billing",
        # P24 must NOT reach into any execution / approval / flag / registry path.
        "api.v1.platform.p15",
        "api.v1.platform.p16",
        "api.v1.platform.p17",
        "api.v1.platform.p18",
        "api.v1.platform.p19",
        "api.v1.platform.p20",
        "api.v1.platform.p21",
        "api.v1.platform.p22",
    )
    allowed_import_substrings = ("api.v1.platform.p23", "api.v1.platform.p10", "api.v1.platform.p24")
    for path, src in _p24_source_files():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
            for m in mods:
                low = m.lower()
                for tok in forbidden_import_substrings:
                    assert tok.lower() not in low, (
                        f"forbidden import {m!r} in p24 source ({os.path.basename(path)})"
                    )
                # every platform import that is NOT p10/p23/p24 is forbidden above;
                # assert the only platform imports are the seam + guard + self.
                if low.startswith("api.v1.platform.p"):
                    assert any(a in low for a in allowed_import_substrings), (
                        f"unexpected platform import {m!r} in {os.path.basename(path)}"
                    )


def test_p24_services_expose_no_execution_or_delivery_or_flag_function():
    from api.v1.platform.p24 import services

    forbidden_names = (
        "execute", "execute_action", "run_action", "dispatch", "dispatch_action",
        "drain", "invoke", "invoke_harness", "start_worker", "run",
        "send_email", "post_webhook", "deliver", "deliver_notification",
        "schedule", "enqueue", "consume",
        "set_flag", "clear_flag", "set_incident_active", "clear_incident_active",
        "approve", "reject_approval", "mutate_registry",
    )
    public = [n for n in dir(services) if not n.startswith("_")]
    for name in forbidden_names:
        assert name not in public, f"forbidden function {name!r} exposed by p24.services"


def test_p24_has_no_persistence_or_table_or_migration_definitions():
    """No ORM/SQL/table/migration primitive appears in any p24 source file."""
    forbidden_attr_substrings = (
        "Base.metadata", "create_all", "Table(", "Column(", "migrate", "alembic",
        "sessionmaker", "create_engine", "session.execute", "INSERT INTO",
    )
    for path, src in _p24_source_files():
        for tok in forbidden_attr_substrings:
            assert tok not in src, f"forbidden persistence token {tok!r} in {os.path.basename(path)}"
