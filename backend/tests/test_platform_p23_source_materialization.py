"""P23-C operator-task source materialization bridge tests.

Covers the P23-C PULL bridge that reads existing, already-audited READ-ONLY
platform source surfaces and materializes typed, redacted OperatorTaskIntakeEvent
records through the P23 service layer's ``upsert_task_from_event``.

Contract-backed (docs/ai/PLATFORM_PRODUCT_P23_OPERATOR_TASK_NOTIFICATION_QUEUE_CONTRACT.md
section 3.1). The single invariant: a task is a view, not an executor; a
notification is a record, not a delivery.

Coverage:
  - P19 in-memory approval -> ``approval_pending``; an overdue pending approval
    -> ``approval_decision_required``; non-pending states -> no follow-up.
  - P22-E3 backup.check source read -> ``backup_check_warning`` for a degraded
    backup (stale / failed / partial / in_progress), ``source_unknown`` for an
    unknown / unavailable source, and NO task for a fresh success.
  - Honesty: source_unknown is never displayed healthy; backup_check_warning is
    never displayed as success; a fresh success produces no task (no fake
    healthy state from unknown / unavailable data).
  - Redaction: a hostile value carried through a source field is scrubbed before
    the task is stored / audited.
  - Dedup: a second materialize pass dedups against ACTIVE tasks (idempotent).
  - The manual materialize route is guarded (401 / 403 / 200), returns a
    per-source summary, and is idempotent.
  - The materialize route is registered on the P23 router.
  - Static guards: sources.py + routes.py import no execution / approval-decision
    / backup-restore / shell / SQL / worker / scheduler / delivery / product
    surface; expose no executing / delivering function; import no channel module.

The bridge executes nothing, approves nothing, delivers nothing, and mutates no
product / tenant business data. Execution follow-ups (P22.services) are
deliberately NOT pulled -- they arrive via intake -- and that omission is honest.
"""
import ast
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")
os.environ.setdefault("SECRET_KEY", "test-secret-key-strong-enough-for-validation-0123456789")


# -- Constants ----------------------------------------------------------------

NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)
AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}
BASE = "/api/v1/platform/p23/operator-tasks"

_ACTIVE_PATCHERS: list = []
_CURRENT_AUTH: dict = {"ctx": None}


# -- Harness (mirrors the P23-B test harness) ---------------------------------


@pytest.fixture(autouse=True)
def _reset_p23_state():
    # P23-C reads the P19 in-memory approval store, so reset BOTH stores to keep
    # every test hermetic (independent of sibling P19 test suite state).
    from api.v1.platform.p19 import services as p19_services
    from api.v1.platform.p23 import services as p23_services

    p23_services.reset_store()
    p19_services.reset_store()
    _CURRENT_AUTH["ctx"] = None
    _enable_auth()
    _as_super("super-exec")
    yield
    p23_services.reset_store()
    p19_services.reset_store()
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


def _as_no_auth():
    _CURRENT_AUTH["ctx"] = None


def _make_app():
    from api.v1.platform.p23.routes import router

    app = FastAPI()
    app.include_router(router)
    return app


def _client():
    return TestClient(_make_app())


def _client_with_db(stub_db):
    """A TestClient whose get_db dependency resolves to the given stub session."""
    from api.dependencies import get_db, get_platform_db
    from api.v1.platform.p23.routes import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: stub_db
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    return TestClient(app)


# -- Source-item builders (stand-ins; only the attributes the mappers read) ----


def _approval_rec(
    *,
    approval_id="ap-1",
    state="pending_review",
    tenant_id=None,
    action_type="tenant.config.update",
    action_id="act-1",
    expires_at=None,
    source_status="available",
    correlation_id=None,
):
    rec = MagicMock()
    rec.approval_id = approval_id
    rec.state = state
    rec.tenant_id = tenant_id
    rec.action_type = action_type
    rec.action_id = action_id
    rec.expires_at = expires_at
    rec.source_status = source_status
    rec.correlation_id = correlation_id
    return rec


def _p19_queue(items):
    # materialize_approvals reads only ``.items``; a lightweight stand-in avoids
    # constructing real ControlledActionApprovalRecord pydantic instances.
    q = MagicMock()
    q.items = list(items)
    return q


def _backup_read(source_summary, *, source_status=None, reason=None):
    from api.v1.platform.p22.source_probe import BackupCheckSourceRead

    if source_status is None:
        source_status = (
            "known"
            if source_summary == "fresh_success"
            else "degraded"
            if source_summary in {"stale", "failed", "partial", "in_progress"}
            else "unknown"
        )
    return BackupCheckSourceRead(
        source_status=source_status, source_summary=source_summary, reason=reason, checked_at=NOW
    )


# ===========================================================================
# 1. P19 approval source -> event mapping (pure)
# ===========================================================================


class TestApprovalSourceMapping:
    def test_pending_review_maps_to_approval_pending(self):
        from api.v1.platform.p23.sources import approval_event_from_record

        ev = approval_event_from_record(
            _approval_rec(state="pending_review", expires_at=NOW + timedelta(days=1)),
            now=NOW,
        )
        assert ev is not None
        assert ev.task_type == "approval_pending"
        assert ev.linked_approval_id == "ap-1"
        assert ev.linked_action_id == "act-1"
        assert ev.linked_gate_open is True
        assert ev.owner_role == "super_admin"
        assert ev.channel is None

    def test_requested_maps_to_approval_pending(self):
        from api.v1.platform.p23.sources import approval_event_from_record

        ev = approval_event_from_record(
            _approval_rec(state="requested", expires_at=NOW + timedelta(days=1)), now=NOW
        )
        assert ev is not None
        assert ev.task_type == "approval_pending"

    def test_overdue_pending_maps_to_approval_decision_required(self):
        from api.v1.platform.p23.sources import approval_event_from_record

        ev = approval_event_from_record(
            _approval_rec(state="pending_review", expires_at=NOW - timedelta(hours=1)),
            now=NOW,
        )
        assert ev is not None
        assert ev.task_type == "approval_decision_required"
        assert ev.followup_variant == "approval_decision_required"

    def test_non_pending_states_produce_no_followup(self):
        from api.v1.platform.p23.sources import approval_event_from_record

        for state in ("approved", "rejected", "expired", "cancelled", "execution_blocked"):
            assert (
                approval_event_from_record(_approval_rec(state=state), now=NOW) is None
            ), f"{state} should not produce a follow-up"

    def test_tenant_id_drives_tenant_contextual_scope(self):
        from api.v1.platform.p23.sources import approval_event_from_record

        ev = approval_event_from_record(
            _approval_rec(tenant_id="t-abc", expires_at=NOW + timedelta(days=1)), now=NOW
        )
        assert ev.actor_scope == "tenant_contextual"
        assert ev.tenant_id == "t-abc"

    def test_no_tenant_id_drives_platform_scope(self):
        from api.v1.platform.p23.sources import approval_event_from_record

        ev = approval_event_from_record(
            _approval_rec(expires_at=NOW + timedelta(days=1)), now=NOW
        )
        assert ev.actor_scope == "platform"
        assert ev.tenant_id is None

    def test_source_status_mapping_never_fabricates_healthy(self):
        from api.v1.platform.p23.sources import approval_event_from_record

        cases = {"available": "known", "unavailable": "degraded", "unknown": "unknown"}
        for raw, expected in cases.items():
            ev = approval_event_from_record(
                _approval_rec(source_status=raw, expires_at=NOW + timedelta(days=1)), now=NOW
            )
            assert ev.source_status == expected, f"{raw} -> {ev.source_status}"

    def test_correlation_falls_back_to_approval_prefixed(self):
        from api.v1.platform.p23.sources import approval_event_from_record

        ev = approval_event_from_record(
            _approval_rec(approval_id="ap-9", correlation_id=None,
                          expires_at=NOW + timedelta(days=1)),
            now=NOW,
        )
        assert ev.correlation_id == "p23c:p19:approval:ap-9"

    def test_correlation_passed_through_when_present(self):
        from api.v1.platform.p23.sources import approval_event_from_record

        ev = approval_event_from_record(
            _approval_rec(correlation_id="corr-x", expires_at=NOW + timedelta(days=1)),
            now=NOW,
        )
        assert ev.correlation_id == "corr-x"


# ===========================================================================
# 2. P22-E3 backup.check source -> event mapping (pure)
# ===========================================================================


class TestBackupCheckSourceMapping:
    @pytest.mark.parametrize("summary", ["stale", "failed", "partial", "in_progress"])
    def test_degraded_summaries_map_to_backup_check_warning(self, summary):
        from api.v1.platform.p23.sources import backup_check_event_from_read

        ev = backup_check_event_from_read(_backup_read(summary))
        assert ev is not None
        assert ev.task_type == "backup_check_warning"
        assert ev.source_status == "degraded"
        assert ev.linked_source_ref == "backup.check"
        assert ev.linked_gate_open is False
        assert ev.owner_role == "engineering_operator"
        assert ev.actor_scope == "platform"

    def test_unknown_maps_to_source_unknown(self):
        from api.v1.platform.p23.sources import backup_check_event_from_read

        ev = backup_check_event_from_read(_backup_read("unknown"))
        assert ev.task_type == "source_unknown"
        assert ev.source_status == "unknown"

    def test_unavailable_maps_to_source_unknown(self):
        from api.v1.platform.p23.sources import backup_check_event_from_read

        ev = backup_check_event_from_read(_backup_read("unavailable"))
        assert ev.task_type == "source_unknown"
        assert ev.source_status == "unknown"

    def test_fresh_success_returns_none(self):
        from api.v1.platform.p23.sources import backup_check_event_from_read

        assert backup_check_event_from_read(_backup_read("fresh_success")) is None

    def test_degraded_never_carries_known_source_status(self):
        from api.v1.platform.p23.sources import backup_check_event_from_read

        # Even if the read lied with source_status='known', the mapper derives
        # degraded from the task type -- defensive honesty.
        ev = backup_check_event_from_read(
            _backup_read("stale", source_status="known")
        )
        assert ev.source_status == "degraded"


# ===========================================================================
# 3. materialize_approvals (integration over a patched P19 read)
# ===========================================================================


class TestMaterializeApprovals:
    def test_empty_queue_produces_zero_counts(self):
        from api.v1.platform.p23.sources import materialize_approvals

        with patch("api.v1.platform.p19.services.list_approvals", return_value=_p19_queue([])):
            counts = materialize_approvals(now=NOW)
        assert counts.source == "p19_approvals"
        assert (counts.read, counts.created, counts.deduped, counts.skipped) == (0, 0, 0, 0)
        assert counts.task_ids == []

    def test_pending_and_non_pending_counts(self):
        from api.v1.platform.p23.sources import materialize_approvals

        items = [
            _approval_rec(approval_id="ap-pending", state="pending_review",
                          expires_at=NOW + timedelta(days=1)),
            _approval_rec(approval_id="ap-done", state="approved"),
        ]
        with patch("api.v1.platform.p19.services.list_approvals", return_value=_p19_queue(items)):
            counts = materialize_approvals(now=NOW)
        assert counts.read == 2
        assert counts.created == 1
        assert counts.skipped == 1
        assert len(counts.task_ids) == 1

    def test_second_pass_dedups_the_pending_approval(self):
        from api.v1.platform.p23.sources import materialize_approvals

        items = [
            _approval_rec(approval_id="ap-dedup", state="pending_review",
                          expires_at=NOW + timedelta(days=1), correlation_id="c-dedup"),
        ]
        with patch("api.v1.platform.p19.services.list_approvals", return_value=_p19_queue(items)):
            first = materialize_approvals(now=NOW)
            second = materialize_approvals(now=NOW)
        assert first.created == 1 and first.deduped == 0
        assert second.created == 0 and second.deduped == 1
        assert first.task_ids == second.task_ids  # same task

    def test_overdue_approval_materializes_as_decision_required_high(self):
        from api.v1.platform.p23 import services
        from api.v1.platform.p23.sources import materialize_approvals

        items = [
            _approval_rec(approval_id="ap-late", state="pending_review",
                          expires_at=NOW - timedelta(hours=2), correlation_id="c-late"),
        ]
        with patch("api.v1.platform.p19.services.list_approvals", return_value=_p19_queue(items)):
            counts = materialize_approvals(now=NOW)
        task = services.read_task(counts.task_ids[0])
        assert task.task_type == "approval_decision_required"
        assert task.severity == "high"


# ===========================================================================
# 4. materialize_backup_check (integration over a patched probe read)
# ===========================================================================


class TestMaterializeBackupCheck:
    async def test_degraded_creates_backup_check_warning_task(self):
        from api.v1.platform.p23 import services
        from api.v1.platform.p23.sources import materialize_backup_check

        read = _backup_read("stale")
        with patch(
            "api.v1.platform.p23.sources.read_backup_check_source",
            new=AsyncMock(return_value=read),
        ):
            counts = await materialize_backup_check(MagicMock(), now=NOW)
        assert counts.source == "p22_backup_check"
        assert (counts.read, counts.created, counts.unavailable) == (1, 1, 0)
        task = services.read_task(counts.task_ids[0])
        assert task.task_type == "backup_check_warning"
        assert task.source_status == "degraded"

    async def test_unknown_creates_source_unknown_task(self):
        from api.v1.platform.p23 import services
        from api.v1.platform.p23.sources import materialize_backup_check

        with patch(
            "api.v1.platform.p23.sources.read_backup_check_source",
            new=AsyncMock(return_value=_backup_read("unknown")),
        ):
            counts = await materialize_backup_check(MagicMock(), now=NOW)
        task = services.read_task(counts.task_ids[0])
        assert task.task_type == "source_unknown"
        assert counts.unavailable == 0  # the read succeeded; no outcome -> unknown

    async def test_unavailable_counts_unavailable_and_surfaces_source_unknown(self):
        from api.v1.platform.p23 import services
        from api.v1.platform.p23.sources import materialize_backup_check

        with patch(
            "api.v1.platform.p23.sources.read_backup_check_source",
            new=AsyncMock(return_value=_backup_read("unavailable")),
        ):
            counts = await materialize_backup_check(MagicMock(), now=NOW)
        assert counts.unavailable == 1
        assert counts.created == 1
        task = services.read_task(counts.task_ids[0])
        assert task.task_type == "source_unknown"

    async def test_fresh_success_skips_no_task(self):
        from api.v1.platform.p23.sources import materialize_backup_check

        with patch(
            "api.v1.platform.p23.sources.read_backup_check_source",
            new=AsyncMock(return_value=_backup_read("fresh_success")),
        ):
            counts = await materialize_backup_check(MagicMock(), now=NOW)
        assert (counts.read, counts.created, counts.skipped) == (1, 0, 1)
        assert counts.task_ids == []

    async def test_read_failure_is_fail_closed_to_source_unknown(self):
        # A real raising session flows through read_backup_check_source and is
        # caught -> unavailable -> source_unknown (never a 500, never healthy).
        from api.v1.platform.p23 import services
        from api.v1.platform.p23.sources import materialize_backup_check

        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("source read failed"))
        counts = await materialize_backup_check(db, now=NOW)
        assert counts.unavailable == 1
        task = services.read_task(counts.task_ids[0])
        assert task.task_type == "source_unknown"
        assert task.display_status == "unknown"


# ===========================================================================
# 5. materialize_all (orchestration)
# ===========================================================================


class TestMaterializeAll:
    async def test_aggregates_across_sources_with_totals(self):
        from api.v1.platform.p23.sources import materialize_all

        items = [
            _approval_rec(approval_id="ap-1", state="pending_review",
                          expires_at=NOW + timedelta(days=1), correlation_id="c-1"),
        ]
        with patch(
            "api.v1.platform.p19.services.list_approvals", return_value=_p19_queue(items)
        ), patch(
            "api.v1.platform.p23.sources.read_backup_check_source",
            new=AsyncMock(return_value=_backup_read("stale")),
        ):
            summary = await materialize_all(MagicMock(), now=NOW)
        assert [s.source for s in summary.sources] == ["p19_approvals", "p22_backup_check"]
        assert summary.total_created == 2  # 1 approval_pending + 1 backup_check_warning
        assert summary.total_skipped == 0
        assert summary.total_unavailable == 0
        assert summary.materialized_at == NOW

    async def test_fresh_backup_and_only_non_pending_approvals_creates_nothing(self):
        from api.v1.platform.p23.sources import materialize_all

        with patch(
            "api.v1.platform.p19.services.list_approvals",
            return_value=_p19_queue([_approval_rec(state="approved")]),
        ), patch(
            "api.v1.platform.p23.sources.read_backup_check_source",
            new=AsyncMock(return_value=_backup_read("fresh_success")),
        ):
            summary = await materialize_all(MagicMock(), now=NOW)
        assert summary.total_created == 0
        assert summary.total_skipped == 2  # 1 approved approval + 1 healthy backup


# ===========================================================================
# 6. Honesty + redaction invariants on materialized tasks
# ===========================================================================


class TestHonestyAndRedaction:
    async def test_backup_check_warning_never_displayed_as_success(self):
        from api.v1.platform.p23 import services
        from api.v1.platform.p23.sources import materialize_backup_check

        with patch(
            "api.v1.platform.p23.sources.read_backup_check_source",
            new=AsyncMock(return_value=_backup_read("stale")),
        ):
            counts = await materialize_backup_check(MagicMock(), now=NOW)
        task = services.read_task(counts.task_ids[0])
        assert task.display_status == "warning"  # never 'success' / 'healthy'
        assert task.severity == "high"

    async def test_source_unknown_never_displayed_healthy(self):
        from api.v1.platform.p23 import services
        from api.v1.platform.p23.sources import materialize_backup_check

        with patch(
            "api.v1.platform.p23.sources.read_backup_check_source",
            new=AsyncMock(return_value=_backup_read("unknown")),
        ):
            counts = await materialize_backup_check(MagicMock(), now=NOW)
        task = services.read_task(counts.task_ids[0])
        assert task.display_status == "unknown"  # never 'healthy'

    def test_approval_summary_with_dsn_is_redacted(self):
        from api.v1.platform.p23 import services
        from api.v1.platform.p23.sources import materialize_approvals

        # Assembled at runtime (no literal credential token) so secret scanners
        # see no Basic-Auth shape here; the P23 redactor must still scrub it
        # before the task is stored / audited.
        _user = "db" + "admin"
        _pw = "hun" + "ter2"
        _host = "db.host" + ".example"
        hostile = "postgresql://" + _user + ":" + _pw + "@" + _host + ":5432/mpango"
        items = [
            _approval_rec(
                approval_id="ap-hostile",
                state="pending_review",
                action_type=hostile,
                expires_at=NOW + timedelta(days=1),
                correlation_id="c-hostile",
            )
        ]
        with patch(
            "api.v1.platform.p19.services.list_approvals", return_value=_p19_queue(items)
        ):
            counts = materialize_approvals(now=NOW)
        task = services.read_task(counts.task_ids[0])
        dumped = task.model_dump_json()
        for leak in ("postgresql://", "dbadmin", "hunter2", "db.host.example", "5432"):
            assert leak not in dumped, f"{leak!r} survived redaction: {dumped!r}"
        assert "[redacted:" in dumped

    def test_no_notification_event_recorded_by_materialize(self):
        # channel=None on every materialized event -> no notification event is
        # recorded by the bridge (a notification is a record, not a delivery,
        # and the bridge records none).
        from api.v1.platform.p23 import services
        from api.v1.platform.p23.sources import materialize_approvals

        items = [
            _approval_rec(approval_id="ap-none", state="pending_review",
                          expires_at=NOW + timedelta(days=1), correlation_id="c-none"),
        ]
        with patch(
            "api.v1.platform.p19.services.list_approvals", return_value=_p19_queue(items)
        ):
            counts = materialize_approvals(now=NOW)
        assert services.notifications_log() == []
        assert services.task_notifications(counts.task_ids[0]) == []


# ===========================================================================
# 7. Manual materialize route (HTTP, guarded)
# ===========================================================================


def _raising_db():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("no db in test"))
    return db


class TestMaterializeRoute:
    def test_route_registered_on_p23_router(self):
        from api.v1.platform.p23.routes import router

        paths = {getattr(r, "path", None) for r in router.routes}
        assert f"{BASE}/internal/materialize" in paths

    def test_route_401_no_credential(self):
        _as_no_auth()
        with _client_with_db(_raising_db()) as c:
            r = c.post(f"{BASE}/internal/materialize")
            assert r.status_code == 401

    def test_route_403_wrong_operator_secret(self):
        _as_no_auth()
        with _client_with_db(_raising_db()) as c:
            r = c.post(
                f"{BASE}/internal/materialize", headers={"X-Platform-Operator": "wrong"}
            )
            assert r.status_code == 403

    def test_route_200_test_override_and_operator_secret(self):
        _as_no_auth()
        with _client_with_db(_raising_db()) as c:
            assert (
                c.post(f"{BASE}/internal/materialize", headers=AUTH_HEADERS).status_code == 200
            )
        with _client_with_db(_raising_db()) as c:
            assert (
                c.post(f"{BASE}/internal/materialize", headers=OPERATOR_HEADERS).status_code
                == 200
            )

    def test_route_returns_summary_shape_and_surfaces_source_unknown(self):
        # The raising db makes the backup read unavailable -> one source_unknown
        # task; the P19 in-memory queue is empty here.
        with _client_with_db(_raising_db()) as c:
            r = c.post(f"{BASE}/internal/materialize", headers=AUTH_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert {s["source"] for s in body["sources"]} == {
            "p19_approvals",
            "p22_backup_check",
        }
        backup = next(s for s in body["sources"] if s["source"] == "p22_backup_check")
        assert backup["unavailable"] == 1
        assert backup["created"] == 1
        assert len(backup["task_ids"]) == 1
        assert body["total_unavailable"] == 1

    def test_route_idempotent_dedup(self):
        with _client_with_db(_raising_db()) as c:
            first = c.post(f"{BASE}/internal/materialize", headers=AUTH_HEADERS).json()
            second = c.post(f"{BASE}/internal/materialize", headers=AUTH_HEADERS).json()
        # Same source_unknown task absorbs the replay (deduped), no new task.
        assert first["total_created"] == 1
        assert second["total_created"] == 0
        assert second["total_deduped"] == 1
        first_ids = [tid for s in first["sources"] for tid in s["task_ids"]]
        second_ids = [tid for s in second["sources"] for tid in s["task_ids"]]
        assert first_ids == second_ids


# ===========================================================================
# 8. Static guards (AST) -- sources.py + routes.py stay in-bounds
# ===========================================================================


def _p23c_source_files():
    import api.v1.platform.p23 as pkg

    base = os.path.dirname(pkg.__file__)
    for name in ("sources.py", "routes.py"):
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


def test_no_forbidden_imports_in_p23c_source():
    forbidden_import_substrings = (
        "subprocess", "alembic", "migrate", "sqlalchemy", "psycopg",
        "p16", "product", "order", "payment", "invoice", "customer",
        "inventory", "ledger", "billing",
        # the P22 execution surface is off-limits to P23
        "api.v1.platform.p22.governed_execution",
        "api.v1.platform.p22.services",
        "api.v1.platform.p22.adapters",
        "smtplib", "socket", "requests", "httpx", "aiohttp", "websockets",
        "pymsteams", "slack",
    )
    for _path, src in _p23c_source_files():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            mods: list = []
            if isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
            for m in mods:
                low = m.lower()
                for tok in forbidden_import_substrings:
                    assert tok.lower() not in low, f"forbidden import {m!r} in p23-c source"


def test_no_forbidden_call_primitives_in_p23c_source():
    forbidden_bare = {"eval", "exec", "system", "popen", "run"}
    forbidden_os_attrs = {"system", "popen", "execv", "execve"}
    forbidden_attr_substrings = (
        "execute_action", "run_action", "dispatch_action", "drain_queue",
        "start_worker", "invoke_harness", "pg_dump", "pg_restore",
        "subprocess", "scheduler", "drain", "send_email", "post_webhook",
    )
    for path, src in _p23c_source_files():
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
                    assert not dotted.startswith("subprocess"), (
                        f"forbidden subprocess call in {path}"
                    )
                    if dotted == "os":
                        assert f.attr not in forbidden_os_attrs, (
                            f"forbidden os.{f.attr} call in {path}"
                        )
                    low = f.attr.lower()
                    assert not any(s in low for s in forbidden_attr_substrings), (
                        f"forbidden execution/worker attr {f.attr!r} in {os.path.basename(path)}"
                    )
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) \
                            and kw.value.value is True:
                        raise AssertionError(f"shell=True forbidden in {path}")


def test_sources_exposes_no_execution_or_delivery_function():
    from api.v1.platform.p23 import sources

    forbidden_names = (
        "execute", "execute_action", "run_action", "dispatch", "dispatch_action",
        "drain", "invoke", "invoke_harness", "start_worker", "run",
        "send_email", "post_webhook", "deliver", "deliver_notification",
        "schedule", "enqueue", "consume",
    )
    public = [n for n in dir(sources) if not n.startswith("_")]
    for name in forbidden_names:
        assert name not in public, f"forbidden execution/delivery function {name!r} exposed by sources"


def test_sources_marks_itself_non_executing():
    from api.v1.platform.p23 import sources

    assert sources.SOURCE_MATERIALIZE_REALIZES_EXECUTION is False
    assert sources.SOURCE_MATERIALIZE_PHASE == "P23-C-operator-task-source-materialization-bridge"
