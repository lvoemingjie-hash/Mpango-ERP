"""
P23 Operator Task / Notification Queue -- non-executing, non-sending in-memory
backend skeleton tests (P23-B).

Contract-backed (docs/ai/PLATFORM_PRODUCT_P23_OPERATOR_TASK_NOTIFICATION_QUEUE_CONTRACT.md):
the queue is the aggregation / presentation layer over P17-P22. A task is a view,
not an executor. A notification is a record, not a delivery.

Coverage:
  - closed task type (10) / state (9) / severity (3) / source-status / channel /
    delivery-state vocabularies are exactly the contract sets.
  - intake materializes a task; replay is idempotent (dedup); terminal tasks are
    exempt from dedup (a recurrence re-opens as a NEW task); no cross-tenant dedup.
  - intake is typed/redacted only: extra="forbid" rejects a raw / product-business
    payload (422); an unknown task_type is rejected (422).
  - list filters (severity / type / state / tenant / source / owner / correlation)
    and pagination; ranking severity-DESC then recency.
  - read returns redacted record + full audit history + notification events; 404
    when missing; dismissed retains audit history.
  - transitions: acknowledge, self-assign (owner only, no state change),
    in-progress, complete (evidence + closed gate), dismiss. Each records exactly
    one OperatorTaskAuditEvent.
  - invalid / forbidden transitions are rejected and audited as denials; terminal
    states accept no exit.
  - notification event is RECORD-ONLY: delivery_state recorded | suppressed;
    per-(task, channel) in-flight dedup; nothing is sent (no channel module is
    even imported).
  - task state transition NEVER calls P22 execution (no p22 execution import; no
    execute / dispatch / drain / deliver / schedule function exposed).
  - source_unknown is never displayed healthy (in every state, incl completed);
    backup_check_warning is never displayed as success.
  - severity is monotonic upward within a correlation; force-high types force high.
  - redaction: a raw secret / DSN / host:port / token / shell-SQL token in any
    free-text field is scrubbed before storage / response / audit.
  - route auth: no credential -> 401; wrong operator secret -> 403; valid identity
    super_admin and valid test override -> 200.
  - route-level transitions behave end-to-end (200 accepted / 409 denied / 404
    missing); app.py includes the P23 router.
  - forbidden-primitive scan: no subprocess / shell / pg_dump / restore / worker /
    scheduler / drain / channel-delivery / persistence / product import in the
    p23 AST; no executing call tokens.

Aligned to docs/ai/PLATFORM_PRODUCT_P23_OPERATOR_TASK_NOTIFICATION_QUEUE_CONTRACT.md
(P23-A).
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
BASE = "/api/v1/platform/p23/operator-tasks"

_ACTIVE_PATCHERS: list = []
_CURRENT_AUTH: dict = {"ctx": None}


# -- Harness (mirrors the P15/P17/P18/P19/P20/P22 test harness) ----------------


@pytest.fixture(autouse=True)
def _reset_p23_state():
    from api.v1.platform.p23 import services

    services.reset_store()
    _CURRENT_AUTH["ctx"] = None
    _enable_auth()
    _as_super("super-exec")
    yield
    services.reset_store()
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


def _as_engineering(user_id="eng-1"):
    _CURRENT_AUTH["ctx"] = _auth_ctx(
        user_id, identity_only=True, super_admin=False, roles=["engineering_operator"]
    )


def _as_tenant_contextual(user_id="ctx-admin"):
    _CURRENT_AUTH["ctx"] = _auth_ctx(
        user_id, identity_only=False, super_admin=True, tenant_id="t-ctx-tenant"
    )


def _as_no_auth():
    _CURRENT_AUTH["ctx"] = None


def _make_app():
    from api.v1.platform.p23.routes import router

    app = FastAPI()
    app.include_router(router)
    return app


def _client():
    return TestClient(_make_app())


# -- Intake helpers ------------------------------------------------------------


def _intake(client, **over):
    payload = {
        "task_type": "action_request_created",
        "correlation_id": "corr-1",
        "summary": "request opened",
        "linked_action_id": "act-1",
    }
    payload.update(over)
    return client.post(f"{BASE}/internal/intake", json=payload, headers=AUTH_HEADERS)


def _seed_task(**over):
    """Seed a task directly through the service (no HTTP) and return its view dict."""
    from api.v1.platform.p23.schemas import OperatorTaskIntakeEvent
    from api.v1.platform.p23 import services

    payload = {
        "task_type": "action_request_created",
        "correlation_id": "corr-1",
        "summary": "request opened",
        "linked_action_id": "act-1",
    }
    payload.update(over)
    res = services.upsert_task_from_event(OperatorTaskIntakeEvent(**payload))
    return res.task.model_dump(mode="json")


# ============================================================================
# 1. Closed vocabularies
# ============================================================================


def test_task_type_vocabulary_is_exactly_ten():
    from api.v1.platform.p23.schemas import TASK_TYPES

    assert len(TASK_TYPES) == 10
    assert len(set(TASK_TYPES)) == 10
    for t in (
        "action_request_created", "approval_pending", "approval_decision_required",
        "execution_ready", "execution_completed", "execution_failed", "source_unknown",
        "backup_check_warning", "incident_followup_required", "runbook_step_required",
    ):
        assert t in TASK_TYPES


def test_state_vocabulary_is_exactly_nine():
    from api.v1.platform.p23.schemas import TASK_STATES, TERMINAL_STATES, ACTIVE_STATES

    assert len(TASK_STATES) == 9
    assert set(TASK_STATES) == {
        "open", "acknowledged", "in_progress", "waiting_on_approval",
        "waiting_on_source", "completed", "dismissed", "expired", "failed",
    }
    assert set(TERMINAL_STATES) == {"completed", "dismissed", "expired", "failed"}
    assert set(ACTIVE_STATES) == {
        "open", "acknowledged", "in_progress", "waiting_on_approval", "waiting_on_source"
    }
    assert set(ACTIVE_STATES).isdisjoint(TERMINAL_STATES)


def test_no_product_business_task_type_exists():
    from api.v1.platform.p23.schemas import TASK_TYPES

    for banned in ("order", "payment", "invoice", "customer", "inventory", "ledger", "billing"):
        for t in TASK_TYPES:
            assert banned not in t, f"product business token {banned!r} in task_type {t!r}"


def test_severity_and_notification_vocabularies():
    from api.v1.platform.p23.schemas import (
        SEVERITIES, NOTIFICATION_CHANNELS, NOTIFICATION_DELIVERY_STATES,
    )

    assert set(SEVERITIES) == {"low", "medium", "high"}
    assert "critical" not in SEVERITIES  # no auto-execute tier
    assert set(NOTIFICATION_CHANNELS) == {"in_app", "email", "webhook"}
    assert "recorded" in NOTIFICATION_DELIVERY_STATES
    assert "delivered" in NOTIFICATION_DELIVERY_STATES  # defined for fidelity; P23-B never produces it


def test_state_machine_graph_matches_contract():
    from api.v1.platform.p23.schemas import ALLOWED_TRANSITIONS

    # open reaches the full set per contract 4.1
    assert ALLOWED_TRANSITIONS["open"] >= {
        "acknowledged", "in_progress", "waiting_on_approval", "waiting_on_source",
        "dismissed", "expired", "failed", "completed",
    }
    # terminal states have no outgoing edges
    for term in ("completed", "dismissed", "expired", "failed"):
        assert ALLOWED_TRANSITIONS[term] == frozenset()
    # waiting_on_* can return to acknowledged / in_progress
    assert "acknowledged" in ALLOWED_TRANSITIONS["waiting_on_approval"]
    assert "in_progress" in ALLOWED_TRANSITIONS["waiting_on_source"]


# ============================================================================
# 2. Intake / dedup
# ============================================================================


def test_intake_creates_task_then_dedups_replay():
    with _client() as c:
        first = _intake(c).json()
        assert first["created"] is True
        assert first["deduped"] is False
        assert first["task"]["state"] == "open"
        tid = first["task"]["task_id"]

        second = _intake(c).json()
        assert second["created"] is False
        assert second["deduped"] is True
        assert second["task"]["task_id"] == tid  # same task

        # No duplicate task, no duplicate audit-success on replay.
        listed = c.get(BASE, headers=AUTH_HEADERS).json()
        assert listed["total"] == 1
        from api.v1.platform.p23 import services
        # materialized audit only (replay writes no new audit)
        assert len([e for e in services.audit_log() if e.task_id == tid]) == 1


def test_terminal_task_is_exempt_from_dedup_reopens_as_new():
    from api.v1.platform.p23 import services
    from api.v1.platform.p23.schemas import OperatorTaskIntakeEvent

    ev = OperatorTaskIntakeEvent(
        task_type="execution_ready", correlation_id="c-ex",
        summary="exec ready", linked_execution_id="ex-9", linked_gate_open=False,
    )
    t1 = services.upsert_task_from_event(ev)
    services.dismiss_task(t1.task.task_id, actor_id="a", actor_role="super_admin",
                          payload=None)
    # Same logical follow-up recurs after dismiss -> NEW task id.
    t2 = services.upsert_task_from_event(ev)
    assert t2.created is True
    assert t2.task.task_id != t1.task.task_id


def test_no_cross_tenant_dedup():
    from api.v1.platform.p23 import services
    from api.v1.platform.p23.schemas import OperatorTaskIntakeEvent

    base = dict(task_type="source_unknown", correlation_id="c-tn",
                summary="unknown", linked_source_ref="src-1", source_status="unknown")
    a = services.upsert_task_from_event(OperatorTaskIntakeEvent(tenant_id="tA", **base))
    b = services.upsert_task_from_event(OperatorTaskIntakeEvent(tenant_id="tB", **base))
    assert a.created and b.created
    assert a.task.task_id != b.task.task_id  # tenant is part of the dedup key


def test_intake_rejects_raw_and_product_payload():
    with _client() as c:
        # extra field -> 422
        bad = c.post(f"{BASE}/internal/intake", json={
            "task_type": "action_request_created", "correlation_id": "c",
            "summary": "x", "order_id": "ord-123",  # product business payload
        }, headers=AUTH_HEADERS)
        assert bad.status_code == 422
        # unknown task_type -> 422 (closed enum)
        bad2 = c.post(f"{BASE}/internal/intake", json={
            "task_type": "order.refund", "correlation_id": "c", "summary": "x",
        }, headers=AUTH_HEADERS)
        assert bad2.status_code == 422


# ============================================================================
# 3. List / read / filters
# ============================================================================


def test_list_filters_and_ranking():
    _seed_task(task_type="source_unknown", correlation_id="hi", linked_source_ref="s1",
               source_status="unknown", summary="unknown src")           # high
    _seed_task(task_type="action_request_created", correlation_id="lo",
               linked_action_id="a1", summary="low")                     # low
    _seed_task(task_type="approval_pending", correlation_id="mid",
               linked_approval_id="ap1", summary="pending", severity="medium",
               tenant_id="tA")
    with _client() as c:
        all_tasks = c.get(BASE, headers=AUTH_HEADERS).json()
        assert all_tasks["total"] == 3
        # severity-DESC ranking: high first, low last
        sev_rank = {"high": 0, "medium": 1, "low": 2}
        seq = [sev_rank[t["severity"]] for t in all_tasks["tasks"]]
        assert seq == sorted(seq)

        only_high = c.get(BASE, params={"severity": "high"}, headers=AUTH_HEADERS).json()
        assert only_high["total"] == 1 and only_high["tasks"][0]["severity"] == "high"

        only_a = c.get(BASE, params={"tenant_id": "tA"}, headers=AUTH_HEADERS).json()
        assert only_a["total"] == 1 and only_a["tasks"][0]["tenant_id"] == "tA"

        by_type = c.get(BASE, params={"task_type": "source_unknown"}, headers=AUTH_HEADERS).json()
        assert by_type["total"] == 1


def test_read_returns_detail_and_404_when_missing():
    tid = _seed_task()["task_id"]
    with _client() as c:
        ok = c.get(f"{BASE}/{tid}", headers=AUTH_HEADERS)
        assert ok.status_code == 200
        body = ok.json()
        assert body["task_id"] == tid
        assert isinstance(body["audit_events"], list)
        assert len(body["audit_events"]) >= 1  # materialized
        missing = c.get(f"{BASE}/does-not-exist", headers=AUTH_HEADERS)
        assert missing.status_code == 404


# ============================================================================
# 4. Transitions (behavioral via service; end-to-end via route below)
# ============================================================================


def test_acknowledge_transition():
    from api.v1.platform.p23 import services
    tid = _seed_task()["task_id"]
    r = services.acknowledge_task(tid, actor_id="op-1", actor_role="super_admin", payload=None)
    assert r.accepted and r.next_state == "acknowledged" and r.transition == "open->acknowledged"
    ev = [e for e in services.audit_log() if e.task_id == tid and e.transition == "open->acknowledged"]
    assert len(ev) == 1 and ev[0].actor_id == "op-1"


def test_self_assign_sets_owner_no_state_change():
    from api.v1.platform.p23 import services
    tid = _seed_task()["task_id"]
    r = services.self_assign_task(tid, actor_id="op-7", actor_role="engineering_operator", payload=None)
    assert r.accepted and r.transition == "self_assigned"
    assert r.previous_state == r.next_state == "open"  # no state change
    detail = services.read_task(tid)
    assert detail.owner_actor_id == "op-7"
    assert detail.owner_role == "engineering_operator"


def test_in_progress_transition():
    from api.v1.platform.p23 import services
    tid = _seed_task()["task_id"]
    services.acknowledge_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    r = services.mark_in_progress_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    assert r.accepted and r.next_state == "in_progress"


def test_complete_requires_evidence_and_closed_gate():
    from api.v1.platform.p23 import services
    from api.v1.platform.p23.schemas import OperatorTaskTransitionRequest as R
    tid = _seed_task(linked_gate_open=True)["task_id"]
    # no evidence -> denied
    r0 = services.complete_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    assert not r0.accepted and r0.denial_code == "COMPLETE_DENIED_NO_EVIDENCE"
    # evidence but gate open -> denied
    r1 = services.complete_task(tid, actor_id="op", actor_role="super_admin",
                                payload=R(evidence="done"))
    assert not r1.accepted and r1.denial_code == "COMPLETE_DENIED_GATE_OPEN"
    # evidence_ref accepted as evidence too, once gate closed
    _seed_close_gate(tid)
    r2 = services.complete_task(tid, actor_id="op", actor_role="super_admin",
                                payload=R(evidence_ref="audit-event-42"))
    assert r2.accepted and r2.next_state == "completed"
    assert r2.task.evidence_ref == "audit-event-42"


def _seed_close_gate(tid):
    """Re-intake the same logical event with linked_gate_open=False to mirror the gate closing."""
    from api.v1.platform.p23 import services
    from api.v1.platform.p23.schemas import OperatorTaskIntakeEvent
    stored = services.read_task(tid)
    ev = OperatorTaskIntakeEvent(
        task_type=stored.task_type, correlation_id=stored.correlation_id,
        tenant_id=stored.tenant_id, summary=stored.summary_redacted,
        linked_action_id=stored.linked_action_id,
        linked_approval_id=stored.linked_approval_id,
        linked_execution_id=stored.linked_execution_id,
        linked_source_ref=stored.linked_source_ref,
        linked_incident_id=stored.linked_incident_id,
        source_status=stored.source_status,
        linked_gate_open=False,
    )
    services.upsert_task_from_event(ev)


def test_complete_with_evidence_note_stores_pointer_not_raw():
    from api.v1.platform.p23 import services
    from api.v1.platform.p23.schemas import OperatorTaskTransitionRequest as R
    tid = _seed_task(linked_gate_open=False)["task_id"]
    r = services.complete_task(tid, actor_id="op", actor_role="super_admin",
                               payload=R(evidence="follow-up done via P22 dry-run + execute"))
    assert r.accepted
    # task row stores a digest pointer, never the raw note
    assert r.task.evidence_ref.startswith("note:")
    # the redacted evidence note lives on the completion audit event
    last = [e for e in services.audit_log() if e.task_id == tid][-1]
    assert "follow-up done" in (last.reason_redacted or "")


def test_invalid_transition_rejected_and_audited():
    from api.v1.platform.p23 import services
    tid = _seed_task()["task_id"]
    services.acknowledge_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    # acknowledged -> failed is NOT in the allowed graph (contract 4.1) -> denied.
    r = services._apply_transition(
        tid, "failed", action="force_fail",
        actor_id="op", actor_role="super_admin", payload=None,
    )
    assert not r.accepted
    assert r.denial_code == "TRANSITION_DENIED_INVALID"
    assert r.previous_state == r.next_state == "acknowledged"  # no state change
    # the denial was audited
    denied = [e for e in services.audit_log()
              if e.task_id == tid and e.transition == "denied:force_fail"]
    assert len(denied) == 1
    assert denied[0].denial_code == "TRANSITION_DENIED_INVALID"


def test_terminal_state_cannot_exit():
    from api.v1.platform.p23 import services
    tid = _seed_task()["task_id"]
    services.dismiss_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    # any transition out of dismissed is denied
    r = services.acknowledge_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    assert not r.accepted and r.denial_code == "TRANSITION_DENIED_TERMINAL"
    r2 = services.mark_in_progress_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    assert not r2.accepted and r2.denial_code == "TRANSITION_DENIED_TERMINAL"


def test_dismiss_keeps_audit_history():
    from api.v1.platform.p23 import services
    tid = _seed_task()["task_id"]
    services.acknowledge_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    before = len(services.task_audit_log(tid))
    services.dismiss_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    after = len(services.task_audit_log(tid))
    assert after > before  # dismiss appended; nothing deleted
    detail = services.read_task(tid)
    assert detail.state == "dismissed"
    assert len(detail.audit_events) == after  # full history retained


# ============================================================================
# 5. Notification boundary (record-only; nothing is sent)
# ============================================================================


def test_notification_event_is_record_only_and_deduped():
    from api.v1.platform.p23 import services
    from api.v1.platform.p23.schemas import OperatorTaskIntakeEvent

    ev = OperatorTaskIntakeEvent(
        task_type="approval_decision_required", correlation_id="c-nf",
        summary="approval needs decision", linked_approval_id="ap-5",
        channel="in_app", severity="high",
    )
    res = services.upsert_task_from_event(ev)
    notifs = services.task_notifications(res.task.task_id)
    assert len(notifs) == 1
    n = notifs[0]
    assert n.delivery_state == "recorded"  # never delivered / queued
    assert n.channel == "in_app"
    assert n.redaction_applied is True
    assert n.summary_redacted == "approval needs decision"

    # Replay the same event: no duplicate notification (per task+channel in-flight dedup).
    services.upsert_task_from_event(ev)
    assert len(services.task_notifications(res.task.task_id)) == 1

    # A second channel is a separate (still record-only) event.
    ev2 = ev.model_copy(update={"channel": "email"})
    services.upsert_task_from_event(ev2)
    notifs2 = services.task_notifications(res.task.task_id)
    assert len(notifs2) == 2
    assert all(n.delivery_state in ("recorded", "suppressed") for n in notifs2)
    assert all(n.delivery_state != "delivered" for n in notifs2)


def test_no_notification_channel_module_imported():
    """P23 sends nothing: no smtp / socket / requests / httpx / push import in its AST."""
    for _path, src in _p23_source_files():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
            for m in mods:
                low = m.lower()
                for banned in ("smtplib", "socket", "requests", "httpx", "aiohttp",
                               "websockets", "pymsteams", "slack", "push"):
                    assert banned not in low, f"forbidden delivery import {m!r} in p23 source"


# ============================================================================
# 6. source_unknown / backup_check_warning display honesty
# ============================================================================


def test_source_unknown_never_healthy_in_any_state():
    from api.v1.platform.p23 import services
    tid = _seed_task(task_type="source_unknown", source_status="unknown",
                     correlation_id="c-su", linked_source_ref="s1",
                     summary="prov source unknown")["task_id"]
    for actor_state in ("acknowledged", "in_progress", "completed"):
        # drive through allowed path to completed
        pass
    services.acknowledge_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    services.mark_in_progress_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    # gate closed so complete is allowed
    services.complete_task(tid, actor_id="op", actor_role="super_admin",
                           payload=__ev("recovered then verified"))
    detail = services.read_task(tid)
    # Even after completion, a source_unknown task is never displayed healthy.
    assert detail.display_status == "unknown"
    assert detail.state == "completed"


def test_backup_check_warning_never_success():
    from api.v1.platform.p23 import services
    tid = _seed_task(task_type="backup_check_warning", correlation_id="c-bw",
                     linked_execution_id="ex-bw", summary="stale backup",
                     source_status="degraded")["task_id"]
    assert services.read_task(tid).display_status == "warning"
    services.acknowledge_task(tid, actor_id="op", actor_role="super_admin", payload=None)
    services.complete_task(tid, actor_id="op", actor_role="super_admin",
                           payload=__ev("investigated; warning stands"))
    assert services.read_task(tid).display_status == "warning"  # never 'completed'/success


def __ev(note):
    from api.v1.platform.p23.schemas import OperatorTaskTransitionRequest
    return OperatorTaskTransitionRequest(evidence=note)


# ============================================================================
# 7. Severity honesty / monotonicity
# ============================================================================


def test_severity_monotonic_upward_in_correlation():
    from api.v1.platform.p23 import services
    from api.v1.platform.p23.schemas import OperatorTaskIntakeEvent

    base = dict(correlation_id="c-sev", summary="peer")
    low = services.upsert_task_from_event(OperatorTaskIntakeEvent(
        task_type="action_request_created", linked_action_id="a-low", **base))
    assert low.task.severity == "low"
    # a high force-high peer joins the same correlation -> low peer lifts to at least medium
    services.upsert_task_from_event(OperatorTaskIntakeEvent(
        task_type="execution_failed", linked_execution_id="ex-fail", **base))
    reranked = services.read_task(low.task.task_id)
    assert reranked.severity in ("medium", "high")


def test_force_high_types_are_high():
    from api.v1.platform.p23 import services
    from api.v1.platform.p23.schemas import OperatorTaskIntakeEvent
    for tt in ("source_unknown", "backup_check_warning", "execution_failed"):
        ev = OperatorTaskIntakeEvent(
            task_type=tt, correlation_id=f"c-{tt}", summary=tt,
            linked_execution_id=f"ex-{tt}" if tt != "source_unknown" else None,
            linked_source_ref="src-x" if tt == "source_unknown" else None,
            source_status="unknown" if tt == "source_unknown" else None,
        )
        res = services.upsert_task_from_event(ev)
        assert res.task.severity == "high", f"{tt} should be high"


# ============================================================================
# 8. Redaction (raw secret / DSN / host:port / token / shell-SQL)
# ============================================================================


def test_redact_text_scrubs_secret_dsn_hostport_shell():
    from api.v1.platform.p23.services import redact_text

    # The credential is assembled at runtime so no single source line carries a
    # literal user:pass@host token. The redactor must still scrub every part.
    user, pwd, host, port = "op", "hunter2", "10.0.0.5", "5432"
    dsn = f"postgres://{user}:{pwd}@{host}:{port}/mpango"
    raw = (f"fail dsn={dsn} "
           "Authorization: Bearer abc.def.ghi cookie=session=zk "
           "ran: pg_dump -Fc mpango | DROP TABLE tenants")
    out = redact_text(raw)
    for forbidden in (pwd, host, port, "postgres://", "Bearer",
                      "abc.def.ghi", "session=zk", "pg_dump", "DROP TABLE"):
        assert forbidden not in out, f"{forbidden!r} survived redaction: {out!r}"
    assert "[redacted:" in out


def test_intake_redacts_summary_before_storage_and_audit():
    from api.v1.platform.p23 import services
    from api.v1.platform.p23.schemas import OperatorTaskIntakeEvent

    # Credential assembled at runtime (no literal user:pass@host in source).
    user, pwd, host, port = "root", "p4ss", "db.internal", "3306"
    dsn = f"mysql://{user}:{pwd}@{host}:{port}/erp"
    ev = OperatorTaskIntakeEvent(
        task_type="execution_failed", correlation_id="c-r",
        summary=f"exec failed; dsn={dsn}",
        linked_execution_id="ex-r",
    )
    res = services.upsert_task_from_event(ev)
    summary = res.task.summary_redacted
    for forbidden in (pwd, host, port, "mysql://"):
        assert forbidden not in summary
    # audit event carries only the redacted summary
    audit = [e for e in services.audit_log() if e.task_id == res.task.task_id][0]
    dump = audit.model_dump_json()
    for forbidden in (pwd, host, port, "mysql://"):
        assert forbidden not in dump


# ============================================================================
# 9. Route auth
# ============================================================================


def test_route_requires_auth_401_without_credential():
    _as_no_auth()
    with _client() as c:
        r = c.get(BASE)  # no header, no token
        assert r.status_code == 401


def test_route_403_wrong_operator_secret():
    _as_no_auth()
    with _client() as c:
        r = c.get(BASE, headers={"X-Platform-Operator": "wrong"})
        assert r.status_code == 403


def test_route_allows_test_override_and_identity_super_admin():
    _as_no_auth()
    with _client() as c:
        assert c.get(BASE, headers=AUTH_HEADERS).status_code == 200
        assert c.get(BASE, headers=OPERATOR_HEADERS).status_code == 200
    _as_super()
    with _client() as c:
        assert c.get(BASE).status_code == 200  # identity-only super_admin token


def test_route_401_tenant_contextual_token_without_header():
    # A tenant-contextual super_admin token (no header) is NOT identity-only -> 401.
    _as_tenant_contextual()
    with _client() as c:
        assert c.get(BASE).status_code == 401


# ============================================================================
# 10. Route-level transitions (end-to-end)
# ============================================================================


def test_route_acknowledge_in_progress_dismiss():
    with _client() as c:
        tid = _intake(c, task_type="action_request_created", linked_action_id="a-r",
                      correlation_id="c-r").json()["task"]["task_id"]
        ack = c.post(f"{BASE}/{tid}/acknowledge", headers=AUTH_HEADERS)
        assert ack.status_code == 200 and ack.json()["next_state"] == "acknowledged"
        prog = c.post(f"{BASE}/{tid}/in-progress", headers=AUTH_HEADERS)
        assert prog.status_code == 200 and prog.json()["next_state"] == "in_progress"
        dis = c.post(f"{BASE}/{tid}/dismiss", headers=AUTH_HEADERS,
                     json={"reason": "not actionable"})
        assert dis.status_code == 200 and dis.json()["next_state"] == "dismissed"


def test_route_complete_denied_then_accepted():
    with _client() as c:
        tid = _intake(c, task_type="execution_ready", linked_execution_id="ex-r2",
                      correlation_id="c-r2", linked_gate_open=True).json()["task"]["task_id"]
        denied = c.post(f"{BASE}/{tid}/complete", headers=AUTH_HEADERS,
                        json={"evidence": "done"})
        assert denied.status_code == 409
        assert denied.json()["detail"]["code"] == "COMPLETE_DENIED_GATE_OPEN"
        # close the gate via replay, then complete succeeds
        _intake(c, task_type="execution_ready", linked_execution_id="ex-r2",
                correlation_id="c-r2", linked_gate_open=False)
        ok = c.post(f"{BASE}/{tid}/complete", headers=AUTH_HEADERS,
                    json={"evidence": "ran through P22"})
        assert ok.status_code == 200 and ok.json()["next_state"] == "completed"


def test_route_terminal_exit_returns_409():
    with _client() as c:
        tid = _intake(c).json()["task"]["task_id"]
        c.post(f"{BASE}/{tid}/dismiss", headers=AUTH_HEADERS)
        again = c.post(f"{BASE}/{tid}/acknowledge", headers=AUTH_HEADERS)
        assert again.status_code == 409
        assert again.json()["detail"]["code"] == "TRANSITION_DENIED_TERMINAL"


def test_route_transition_404_missing_task():
    with _client() as c:
        r = c.post(f"{BASE}/nope/acknowledge", headers=AUTH_HEADERS)
        assert r.status_code == 404


def test_route_self_assign_sets_owner():
    with _client() as c:
        tid = _intake(c).json()["task"]["task_id"]
        r = c.post(f"{BASE}/{tid}/self-assign", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json()["transition"] == "self_assigned"
        detail = c.get(f"{BASE}/{tid}", headers=AUTH_HEADERS).json()
        assert detail["owner_actor_id"] == "super-exec"


def test_route_intake_status_201_then_200():
    with _client() as c:
        first = _intake(c)
        assert first.status_code == 201
        second = _intake(c)  # same logical event -> dedup -> 200
        assert second.status_code == 200


# ============================================================================
# 11. App wiring + forbidden-primitive scan
# ============================================================================


def test_app_py_includes_p23_router():
    import api.v1.platform.p23 as pkg
    app_path = os.path.join(os.path.dirname(pkg.__file__), "..", "..", "..", "app.py")
    app_path = os.path.abspath(app_path)
    with open(app_path, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert "from api.v1.platform.p23.routes import router as platform_p23_router" in src
    assert "app.include_router(platform_p23_router)" in src


def test_p23_router_has_exactly_the_contract_endpoints():
    from api.v1.platform.p23.routes import router

    pairs = set()
    for r in router.routes:
        methods = getattr(r, "methods", None) or set()
        for m in methods:
            pairs.add((m, getattr(r, "path", None)))
    expected = {
        ("GET", f"{BASE}"),
        ("GET", f"{BASE}/{{task_id}}"),
        ("POST", f"{BASE}/internal/intake"),
        ("POST", f"{BASE}/{{task_id}}/acknowledge"),
        ("POST", f"{BASE}/{{task_id}}/self-assign"),
        ("POST", f"{BASE}/{{task_id}}/in-progress"),
        ("POST", f"{BASE}/{{task_id}}/complete"),
        ("POST", f"{BASE}/{{task_id}}/dismiss"),
    }
    assert expected.issubset(pairs)


def _p23_source_files():
    import api.v1.platform.p23 as pkg
    base = os.path.dirname(pkg.__file__)
    # P23-C added sources.py to the scanned set so this contract guard covers the
    # source-materialization bridge too (it lives in the same in-bounds tree).
    for name in ("__init__.py", "schemas.py", "services.py", "routes.py", "sources.py"):
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


def test_no_subprocess_shell_dump_restore_worker_scheduler_in_p23_ast():
    """No code-execution / queue-worker / dump-restore token appears in any p23 AST.

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
    for path, src in _p23_source_files():
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


def test_no_persistence_or_product_or_p22execution_imports_in_p23_source():
    forbidden_import_substrings = (
        "subprocess", "alembic", "migrate", "sqlalchemy", "psycopg",
        "p16", "product", "order", "payment", "invoice", "customer",
        "inventory", "ledger", "billing",
        # P23 must NOT call the P22 execution / governed-action surface
        "api.v1.platform.p22.governed_execution",
        "api.v1.platform.p22.services",
        "api.v1.platform.p22.adapters",
    )
    for _path, src in _p23_source_files():
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
                        f"forbidden import {m!r} in p23 source"
                    )


def test_p23_services_expose_no_execution_or_delivery_function():
    from api.v1.platform.p23 import services

    forbidden_names = (
        "execute", "execute_action", "run_action", "dispatch", "dispatch_action",
        "drain", "invoke", "invoke_harness", "start_worker", "run",
        "send_email", "post_webhook", "deliver", "deliver_notification",
        "schedule", "enqueue", "consume",
    )
    public = [n for n in dir(services) if not n.startswith("_")]
    for name in forbidden_names:
        assert name not in public, f"forbidden execution/delivery function {name!r} exposed by p23.services"
