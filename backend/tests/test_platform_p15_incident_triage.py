"""
P15 Incident Triage API tests (P15-B).

Contract-backed, read-only snapshot API. Covers:
  - Response shape (IncidentTriageSnapshot, IncidentHandoffSummary)
  - source_status semantics (unknown != healthy, null != 0, reasons visible)
  - Permission enforcement (identity-only super_admin allowed; tenant-contextual
    denied; non-super_admin denied)
  - graceful_degraded (single source failure still returns a snapshot)
  - Redaction (no credentials/DSN/host/port/raw pool.status()/tenant business)
  - GET-only (no mutation routes)
  - Counterexamples from PLATFORM_PRODUCT_P15_INCIDENT_TRIAGE_CONTRACT.md
"""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")


# -- Helpers --

AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}

P15_BASE = "/api/v1/platform/p15"
SNAPSHOT_PATH = f"{P15_BASE}/incidents/triage/snapshot"


def _mock_db():
    """Mock DB whose execute resolves (simulates a reachable DB for the ping)."""
    db = MagicMock()
    ok = MagicMock()
    ok.scalar.return_value = 0
    ok.scalar_one_or_none.return_value = None
    ok.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=ok)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _make_app(mock_db):
    from api.v1.platform.p15.routes import router
    from api.dependencies import get_db, get_platform_db
    from database.session import get_db as db_get_db

    app = FastAPI()

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    app.dependency_overrides[db_get_db] = override
    app.include_router(router)
    return app


def _guarded_app(mock_db=None):
    return _make_app(mock_db or _mock_db())


# ============================================================
# 1. Schema / contract tests
# ============================================================


class TestSchemas:
    def test_signal_unknown_severity_allowed(self):
        from api.v1.platform.p15.schemas import IncidentSignal
        s = IncidentSignal(
            signal_id="abc", kind="database", severity="unknown",
            source_ref="p14.ops.resources.database", source_status="unavailable",
            observed_at=datetime.now(timezone.utc),
        )
        assert s.severity == "unknown"  # unknown != healthy

    def test_signal_rejects_extra_fields(self):
        from api.v1.platform.p15.schemas import IncidentSignal
        with pytest.raises(Exception):
            IncidentSignal(
                signal_id="abc", kind="database", severity="info",
                source_ref="x", source_status="available",
                observed_at=datetime.now(timezone.utc),
                evil_field="leak",
            )

    def test_signal_accepts_integer_observed_value(self):
        """P15-R1 [P3]: observed_value accepts int (counts) per P15-A contract."""
        from api.v1.platform.p15.schemas import IncidentSignal
        s = IncidentSignal(
            signal_id="abc", kind="tenant_health", severity="warning",
            source_ref="p10.tenants.summary", observed_value=7,
            source_status="available", observed_at=datetime.now(timezone.utc),
        )
        assert s.observed_value == 7
        assert isinstance(s.observed_value, int)

    def test_signal_accepts_string_observed_value(self):
        """P15-R1 [P3]: observed_value still accepts str (status labels)."""
        from api.v1.platform.p15.schemas import IncidentSignal
        s = IncidentSignal(
            signal_id="abc", kind="system", severity="info",
            source_ref="p10.system.health", observed_value="healthy",
            source_status="available", observed_at=datetime.now(timezone.utc),
        )
        assert s.observed_value == "healthy"

    def test_snapshot_requires_graceful_degraded_and_overall_status(self):
        from api.v1.platform.p15.schemas import IncidentTriageSnapshot
        snap = IncidentTriageSnapshot(
            snapshot_id="x", generated_at=datetime.now(timezone.utc),
            overall_status="unknown", graceful_degraded=True,
        )
        assert snap.graceful_degraded is True
        assert snap.overall_status == "unknown"
        assert snap.tenant_health_sample_count is None  # null != 0

    def test_handoff_summary_always_redacted_flag(self):
        from api.v1.platform.p15.schemas import (
            IncidentHandoffSummary, IncidentClassification,
        )
        h = IncidentHandoffSummary(
            summary_id="x", created_at=datetime.now(timezone.utc),
            classification=IncidentClassification(
                category="database", confidence="high", suggested_owner="dba",
            ),
            redacted=True, sensitive_keys_dropped=0,
        )
        assert h.redacted is True


# ============================================================
# 2. Response shape
# ============================================================


class TestResponseShape:
    def test_snapshot_returns_contract_shape(self):
        app = _guarded_app()
        client = TestClient(app)
        r = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text
        d = r.json()
        for key in (
            "snapshot_id", "generated_at", "overall_status", "signals",
            "database_probe", "graceful_degraded",
        ):
            assert key in d, f"missing {key}"
        assert isinstance(d["signals"], list)


# ============================================================
# 3. source_status semantics (unknown != healthy, null != 0)
# ============================================================


class TestSourceStatusSemantics:
    def test_overall_status_not_fabricated_healthy_when_db_unknown(self):
        # A DB whose ping raises -> db probe unhealthy, overall must not be
        # fabricated 'healthy'.
        db = _mock_db()
        db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        app = _make_app(db)
        client = TestClient(app)
        r = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 200
        d = r.json()
        assert d["overall_status"] != "healthy"
        assert d["graceful_degraded"] is True

    def test_tenant_count_is_null_not_zero_when_unavailable(self):
        db = _mock_db()
        # Make tenant listing raise so the count is unavailable.
        with patch(
            "api.v1.platform.p15.services.list_tenant_summaries",
            new=AsyncMock(side_effect=RuntimeError("no tenants")),
        ):
            app = _make_app(db)
            client = TestClient(app)
            r = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        d = r.json()
        assert d["tenant_health_sample_count"] is None
        assert d["tenant_health_sample_count"] != 0
        assert d["graceful_degraded"] is True

    def test_unavailable_reason_visible_when_source_missing(self):
        db = _mock_db()
        db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        app = _make_app(db)
        client = TestClient(app)
        r = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        d = r.json()
        assert d.get("unavailable_reason")  # non-empty


# ============================================================
# 4. Permission enforcement
# ============================================================


class TestPermissions:
    def test_no_auth_returns_401(self):
        app = _guarded_app()
        client = TestClient(app)
        assert client.get(SNAPSHOT_PATH).status_code == 401

    def test_test_override_accepted(self):
        app = _guarded_app()
        client = TestClient(app)
        assert client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS).status_code == 200

    def test_operator_secret_accepted(self):
        app = _guarded_app()
        client = TestClient(app)
        assert client.get(SNAPSHOT_PATH, headers=OPERATOR_HEADERS).status_code == 200

    def test_invalid_override_returns_403(self):
        app = _guarded_app()
        client = TestClient(app)
        bad = {"X-Platform-Test-Override": "wrong"}
        assert client.get(SNAPSHOT_PATH, headers=bad).status_code == 403

    def test_tenant_contextual_super_admin_denied(self):
        app = _guarded_app()
        client = TestClient(app)
        token = MagicMock()
        token.user_id = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
        token.roles = ["super_admin"]
        token.tenant_id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
        token.tenant_schema = "t_test"
        token.is_identity_only = False
        token.is_super_admin = True
        auth_ctx = MagicMock()
        auth_ctx.token = token
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.get(SNAPSHOT_PATH)
        assert r.status_code in (401, 403)

    def test_non_super_admin_identity_denied(self):
        app = _guarded_app()
        client = TestClient(app)
        token = MagicMock()
        token.user_id = "e5f6a7b8-c9d0-4e1f-2a3b-4c5d6e7f8a9b"
        token.roles = ["support_operator"]
        token.tenant_id = None
        token.tenant_schema = None
        token.is_identity_only = True
        token.is_super_admin = False
        auth_ctx = MagicMock()
        auth_ctx.token = token
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.get(SNAPSHOT_PATH)
        assert r.status_code in (401, 403)

    def test_identity_only_super_admin_allowed(self):
        app = _guarded_app()
        client = TestClient(app)
        token = MagicMock()
        token.user_id = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
        token.roles = ["super_admin"]
        token.tenant_id = None
        token.tenant_schema = None
        token.is_identity_only = True
        token.is_super_admin = True
        auth_ctx = MagicMock()
        auth_ctx.token = token
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.get(SNAPSHOT_PATH)
        assert r.status_code == 200


# ============================================================
# 5. Redaction
# ============================================================


class TestRedaction:
    SENSITIVE = [
        "password", "secret", "token", "cookie", "authorization",
        "card_number", "cvv", "raw_body", "request_body", "response_body",
        "stack_trace", "traceback", "host", "port", "dsn", "connection_string",
    ]

    def _assert_no_sensitive(self, data, path=""):
        if isinstance(data, dict):
            for k, v in data.items():
                kl = k.lower()
                for p in self.SENSITIVE:
                    assert p not in kl, f"sensitive key '{k}' at {path}.{k}"
                self._assert_no_sensitive(v, f"{path}.{k}")
        elif isinstance(data, list):
            for i, it in enumerate(data):
                self._assert_no_sensitive(it, f"{path}[{i}]")

    def test_snapshot_no_sensitive_keys(self):
        app = _guarded_app()
        client = TestClient(app)
        r = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        self._assert_no_sensitive(r.json())

    def test_snapshot_no_raw_pool_status_string(self):
        app = _guarded_app()
        client = TestClient(app)
        r = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        body = str(r.json())
        assert "Pool size:" not in body  # raw pool.status() never serialized
        assert "Checked out connections" not in body

    def test_handoff_summary_no_sensitive(self):
        from api.v1.platform.p15.services import build_handoff_summary, build_triage_snapshot
        import asyncio
        db = _mock_db()
        snap = asyncio.run(build_triage_snapshot(db))
        from api.v1.platform.p15.schemas import IncidentClassification
        handoff = build_handoff_summary(
            snap,
            IncidentClassification(
                category="database", confidence="high", suggested_owner="dba",
            ),
        )
        dumped = handoff.model_dump()
        self._assert_no_sensitive(dumped)


# ============================================================
# 6. graceful degraded
# ============================================================


class TestGracefulDegraded:
    def test_snapshot_returns_200_with_reason_on_db_failure(self):
        db = _mock_db()
        db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        app = _make_app(db)
        client = TestClient(app)
        r = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 200  # graceful, not 500
        d = r.json()
        assert d["graceful_degraded"] is True
        assert d.get("unavailable_reason")

    def test_db_probe_null_when_ping_fails(self):
        db = _mock_db()
        db.execute = AsyncMock(side_effect=RuntimeError("db down"))
        app = _make_app(db)
        client = TestClient(app)
        d = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS).json()
        # database_probe may be null OR present-with-unhealthy; latency null either way
        probe = d.get("database_probe")
        if probe is not None:
            assert probe["latency_ms"] is None
            assert probe["status"] == "unhealthy"

    # -- P15-R1 [P1]: exact CTO counterexample --
    def test_db_source_failure_is_graceful_degraded_and_unavailable_unit(self):
        """P15-R1 [P1] unit: P10 sources succeed, only DB ping fails.

        P14 _database_health swallows the ping error and returns an
        unhealthy/null probe. P15 MUST treat that as a failed DB source.
        """
        import asyncio
        from api.v1.platform.p15.services import build_triage_snapshot

        db = _mock_db()
        db.execute = AsyncMock(side_effect=RuntimeError("db unreachable"))

        # P10 sources succeed (isolate the DB failure as the only failing source).
        ok_sys = MagicMock()
        ok_sys.overall_status = "healthy"
        ok_tenants = MagicMock()
        ok_tenants.total = 5
        ok_tenants.items = []
        with patch(
            "api.v1.platform.p15.services.get_system_health",
            new=AsyncMock(return_value=ok_sys),
        ), patch(
            "api.v1.platform.p15.services.list_tenant_summaries",
            new=AsyncMock(return_value=ok_tenants),
        ):
            snap = asyncio.run(build_triage_snapshot(db))

        assert snap.graceful_degraded is True
        assert snap.unavailable_reason and "database probe" in snap.unavailable_reason.lower()
        # database signal must NOT be marked available
        db_signals = [s for s in snap.signals if s.kind == "database"]
        assert db_signals, "expected a database signal"
        assert db_signals[0].source_status != "available"
        assert db_signals[0].source_status == "unavailable"
        assert db_signals[0].unavailable_reason  # visible, non-empty
        # database_probe is None OR its latency is None (null != 0; no fabrication)
        if snap.database_probe is not None:
            assert snap.database_probe.latency_ms is None

    def test_db_source_failure_is_graceful_degraded_route(self):
        """P15-R1 [P1] route: same counterexample through the GET endpoint."""
        db = _mock_db()
        db.execute = AsyncMock(side_effect=RuntimeError("db unreachable"))
        ok_sys = MagicMock()
        ok_sys.overall_status = "healthy"
        ok_tenants = MagicMock()
        ok_tenants.total = 5
        ok_tenants.items = []
        with patch(
            "api.v1.platform.p15.services.get_system_health",
            new=AsyncMock(return_value=ok_sys),
        ), patch(
            "api.v1.platform.p15.services.list_tenant_summaries",
            new=AsyncMock(return_value=ok_tenants),
        ):
            app = _make_app(db)
            client = TestClient(app)
            r = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 200  # graceful, no 500
        d = r.json()
        assert d["graceful_degraded"] is True
        assert d.get("unavailable_reason") and "database probe" in d["unavailable_reason"].lower()
        db_signals = [s for s in d["signals"] if s["kind"] == "database"]
        assert db_signals and db_signals[0]["source_status"] != "available"
        assert db_signals[0]["source_status"] == "unavailable"
        assert db_signals[0]["unavailable_reason"]

    def test_p10_source_failures_still_graceful_degraded(self):
        """P15-R1 [P1]: existing P10 tenant/system source failures still degrade gracefully."""
        db = _mock_db()
        with patch(
            "api.v1.platform.p15.services.get_system_health",
            new=AsyncMock(side_effect=RuntimeError("p10 system down")),
        ), patch(
            "api.v1.platform.p15.services.list_tenant_summaries",
            new=AsyncMock(side_effect=RuntimeError("p10 tenants down")),
        ):
            app = _make_app(db)
            client = TestClient(app)
            d = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS).json()
        assert d["graceful_degraded"] is True
        assert d.get("unavailable_reason")


# ============================================================
# 7. GET-only / no mutation routes
# ============================================================


class TestGetOnly:
    def test_post_rejected(self):
        app = _guarded_app()
        client = TestClient(app)
        r = client.post(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 405

    def test_put_rejected(self):
        app = _guarded_app()
        client = TestClient(app)
        r = client.put(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 405

    def test_delete_rejected(self):
        app = _guarded_app()
        client = TestClient(app)
        r = client.delete(SNAPSHOT_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 405


# ============================================================
# 8. P15-A counterexamples (must be absent / rejected)
# ============================================================


class TestCounterexamples:
    def test_no_repair_or_impersonate_endpoints(self):
        from api.v1.platform.p15.routes import router
        methods = []
        for route in router.routes:
            methods.extend(getattr(route, "methods", set()))
        assert "POST" not in methods
        assert "PUT" not in methods
        assert "PATCH" not in methods
        assert "DELETE" not in methods

    def test_no_tenant_business_fields_in_snapshot(self):
        app = _guarded_app()
        client = TestClient(app)
        d = client.get(SNAPSHOT_PATH, headers=AUTH_HEADERS).json()
        body = str(d).lower()
        for biz in ("order", "invoice", "payment", "customer", "sku", "balance"):
            assert biz not in body, f"business token '{biz}' leaked"

    def test_unknown_signal_severity_is_not_healthy(self):
        # unknown severity must be representable and distinct from a healthy state
        from api.v1.platform.p15.schemas import IncidentSignal
        s = IncidentSignal(
            signal_id="x", kind="system", severity="unknown",
            source_ref="p10", source_status="unknown",
            observed_at=datetime.now(timezone.utc),
        )
        assert s.severity != "healthy"  # no healthy severity exists for signals
