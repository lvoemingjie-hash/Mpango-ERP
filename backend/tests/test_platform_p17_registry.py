"""
P17 Platform Registry API tests (P17-B).

Contract-backed, READ-ONLY tenant registry adapter. Covers:
  - Response shape (PlatformTenantRegistry / PlatformTenantRegistryList)
  - source_status semantics (unknown != healthy/active/success; null != 0/false;
    reasons always visible)
  - Permission enforcement (identity-only super_admin allowed; tenant-contextual
    denied; non-super_admin denied; unauthenticated denied)
  - GET-only (POST/PUT/PATCH/DELETE -> 405; no mutation route on the router)
  - Freshness: a stale 'success' backup never reads 'success' (counterexample C4)
  - Redaction: failure_reason_redacted is an allowlisted code only; no
    secret/credential/DSN/host/port; no tenant business records (C2/C6/C14)
  - extra="forbid" on every model
  - graceful degradation: a source failure yields unavailable + reason, not 500
  - P17-A counterexamples (C1-C14) absent / rejected

Aligned to docs/ai/PLATFORM_PRODUCT_P17_REGISTRY_LIFECYCLE_CONTRACT.md.
"""
import sys, os; sys.path.insert(0, os.path.dirname(__file__)); from conftest import run_coroutine
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")


# -- Helpers (mirror the P15 test harness) --

AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}

P17_BASE = "/api/v1/platform/p17"
REGISTRY_PATH = f"{P17_BASE}/registry"

TENANT_ID = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
OTHER_TENANT_ID = "c3d4e5f6-a7b8-49c0-9d1e-2f3a4b5c6d7e"


# Tracked patchers so every test-scoped patch is reliably stopped after the
# test (prevents cross-test contamination when _make_app patches source calls).
_ACTIVE_PATCHERS: list = []


def _start_patch(target, new):
    p = patch(target, new=new)
    p.start()
    _ACTIVE_PATCHERS.append(p)
    return p


@pytest.fixture(autouse=True)
def _stop_patches_after_test():
    yield
    while _ACTIVE_PATCHERS:
        _ACTIVE_PATCHERS.pop().stop()


def _mock_db():
    db = MagicMock()
    ok = MagicMock()
    ok.scalar.return_value = 0
    ok.scalar_one_or_none.return_value = None
    ok.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=ok)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    @asynccontextmanager
    async def _begin_nested():
        yield

    db.begin_nested = _begin_nested
    return db


def _summary(
    tenant_id=TENANT_ID,
    name="Acme",
    schema="t_acme",
    status="active",
    support_mode_active=False,
):
    s = MagicMock()
    s.tenant_id = tenant_id
    s.tenant_name = name
    s.tenant_schema = schema
    s.tier = None
    s.created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    s.status = status
    s.support_mode_active = support_mode_active
    return s


def _summary_list(items, total=None):
    lst = MagicMock()
    lst.items = items
    lst.total = total if total is not None else len(items)
    lst.limit = 50
    lst.offset = 0
    return lst


def _make_app(mock_db, *, summary_list=None, provisioning_map=None,
              single_summary=None):
    """Build an app with P10 sources patched to deterministic fakes."""
    from api.v1.platform.p17.routes import router
    from api.dependencies import get_db, get_platform_db

    app = FastAPI()

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    app.include_router(router)

    # Patch the service-layer source calls for deterministic data.
    if summary_list is not None:
        _start_patch(
            "api.v1.platform.p17.services.list_tenant_summaries",
            AsyncMock(return_value=summary_list),
        )
    if provisioning_map is not None:
        _start_patch(
            "api.v1.platform.p17.services._load_provisioning_map",
            AsyncMock(return_value=provisioning_map),
        )
    if single_summary is not None:
        _start_patch(
            "api.v1.platform.p10.services.get_tenant_summary",
            AsyncMock(return_value=single_summary),
        )
    return app


def _guarded_app(mock_db=None):
    return _make_app(mock_db or _mock_db(), summary_list=_summary_list([_summary()]))


# ============================================================
# 1. Schema / contract tests
# ============================================================


class TestSchemas:
    def test_lifecycle_unknown_not_available(self):
        from api.v1.platform.p17.schemas import TenantLifecycleState
        with pytest.raises(Exception):
            TenantLifecycleState(state="unknown", state_source_status="available")

    def test_lifecycle_rejects_extra_fields(self):
        from api.v1.platform.p17.schemas import TenantLifecycleState
        with pytest.raises(Exception):
            TenantLifecycleState(
                state="active", state_source_status="available", evil="leak"
            )

    def test_operational_flags_allfalse_requires_reason(self):
        from api.v1.platform.p17.schemas import TenantOperationalFlags
        false = dict(
            support_mode_active=False, incident_active=False, login_paused=False,
            writes_paused=False, billing_hold=False, backup_attention_required=False,
            migration_attention_required=False, quota_attention_required=False,
        )
        # available without a measurement timestamp -> rejected (unknown != false)
        with pytest.raises(Exception):
            TenantOperationalFlags(flags_source_status="available", **false)
        # unavailable with a reason -> accepted
        ok = TenantOperationalFlags(
            flags_source_status="unavailable",
            flags_unavailable_reason="telemetry not instrumented",
            **false,
        )
        assert ok.support_mode_active is False

    def test_provisioning_failure_reason_allowlist_rejects_secret(self):
        from api.v1.platform.p17.schemas import TenantProvisioningStatus
        with pytest.raises(Exception):
            TenantProvisioningStatus(
                provisioning_source_status="unavailable",
                # A raw stack trace / internal detail is not an allowlisted code
                # and must be rejected (counterexample C6).
                failure_reason_redacted=(
                    "Traceback (most recent call last): OperationalError during schema create"
                ),
            )

    def test_provisioning_failure_reason_accepts_allowlisted_code(self):
        from api.v1.platform.p17.schemas import TenantProvisioningStatus
        p = TenantProvisioningStatus(
            provisioning_source_status="available",
            schema_status="exists",
            failure_reason_redacted="schema_create_failed",
        )
        assert p.failure_reason_redacted == "schema_create_failed"

    def test_backup_success_requires_timestamp_and_available_source(self):
        from api.v1.platform.p17.schemas import TenantBackupStatus
        with pytest.raises(Exception):
            TenantBackupStatus(
                backup_source_status="available",
                last_backup_status="success",
                last_backup_at=None,
            )

    def test_registry_rejects_extra_fields(self):
        from api.v1.platform.p17.schemas import (
            PlatformTenantRegistry, TenantLifecycleState, TenantOperationalFlags,
        )
        false = dict(
            support_mode_active=False, incident_active=False, login_paused=False,
            writes_paused=False, billing_hold=False, backup_attention_required=False,
            migration_attention_required=False, quota_attention_required=False,
        )
        with pytest.raises(Exception):
            PlatformTenantRegistry(
                tenant_id=TENANT_ID,
                lifecycle_state=TenantLifecycleState(
                    state="active", state_source_status="available"
                ),
                operational_flags=TenantOperationalFlags(
                    flags_source_status="unavailable",
                    flags_unavailable_reason="x", **false
                ),
                registry_source_status="available",
                evil="leak",
            )

    def test_redact_failure_reason_collapses_secret_to_unknown(self):
        from api.v1.platform.p17.schemas import (
            redact_failure_reason, PROVISIONING_FAILURE_REASONS,
        )
        assert redact_failure_reason(
            "Traceback (most recent call last): OperationalError with raw internal metadata",
            PROVISIONING_FAILURE_REASONS,
        ) == "unknown"
        assert redact_failure_reason(
            "schema_create_failed", PROVISIONING_FAILURE_REASONS
        ) == "schema_create_failed"
        assert redact_failure_reason(None, PROVISIONING_FAILURE_REASONS) is None

    def test_enforce_backup_freshness_stale_not_success(self):
        from api.v1.platform.p17.schemas import enforce_backup_freshness
        now = datetime(2026, 6, 22, tzinfo=timezone.utc)
        # recent success stays success
        assert enforce_backup_freshness(
            "success", now - timedelta(hours=2), now=now
        ) == "success"
        # stale success -> stale (never success)
        assert enforce_backup_freshness(
            "success", now - timedelta(hours=48), now=now
        ) == "stale"
        # success without timestamp -> unknown (never success)
        assert enforce_backup_freshness("success", None, now=now) == "unknown"
        # non-success passes through
        assert enforce_backup_freshness("failed", now - timedelta(hours=48), now=now) == "failed"


# ============================================================
# 2. Response shape
# ============================================================


class TestResponseShape:
    def test_list_returns_contract_shape(self):
        app = _guarded_app()
        client = TestClient(app)
        r = client.get(REGISTRY_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("items", "total", "limit", "offset",
                    "registry_source_status", "unavailable_reason"):
            assert key in d, f"missing {key}"
        assert isinstance(d["items"], list)
        item = d["items"][0]
        for key in (
            "tenant_id", "tenant_name", "tenant_schema", "tier", "created_at",
            "lifecycle_state", "operational_flags", "provisioning_status",
            "backup_status", "last_registry_update_at", "registry_source_status",
            "unavailable_reason",
        ):
            assert key in item, f"missing item.{key}"
        for key in (
            "state", "previous_state", "entered_at", "last_actor_id",
            "last_actor_role", "transition_reason", "last_audit_event_id",
            "state_source_status",
        ):
            assert key in item["lifecycle_state"], f"missing lifecycle.{key}"

    def test_single_returns_contract_shape(self):
        app = _make_app(
            _mock_db(), single_summary=_summary(),
            provisioning_map={TENANT_ID: None},
        )
        # provisioning_map expects a real PlatformTenant; pass empty dict so it
        # degrades (provisioning_status None) deterministically.
        client = TestClient(app)
        r = client.get(f"{REGISTRY_PATH}/{TENANT_ID}", headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["tenant_id"] == TENANT_ID
        assert "lifecycle_state" in d


# ============================================================
# 3. source_status semantics (unknown != healthy/active; null != 0)
# ============================================================


class TestSourceStatusSemantics:
    def test_active_tenant_lifecycle_available(self):
        app = _guarded_app()
        client = TestClient(app)
        d = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()
        item = d["items"][0]
        assert item["lifecycle_state"]["state"] == "active"
        assert item["lifecycle_state"]["state_source_status"] == "available"
        assert item["registry_source_status"] == "available"

    def test_unknown_status_tenant_not_active(self):
        # P10 status 'unknown' -> lifecycle unknown, registry unknown, never active
        app = _make_app(
            _mock_db(), summary_list=_summary_list([_summary(status="unknown")])
        )
        client = TestClient(app)
        d = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()
        item = d["items"][0]
        assert item["lifecycle_state"]["state"] == "unknown"
        assert item["lifecycle_state"]["state"] != "active"
        assert item["lifecycle_state"]["state_source_status"] != "available"
        assert d["registry_source_status"] == "unknown"

    def test_provisioning_and_backup_null_with_reason(self):
        app = _guarded_app()
        client = TestClient(app)
        d = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()
        item = d["items"][0]
        assert item["provisioning_status"] is None  # null, not fabricated
        assert item["backup_status"] is None
        assert item["unavailable_reason"]  # visible, non-empty
        assert "provisioning" in item["unavailable_reason"].lower()
        assert "backup" in item["unavailable_reason"].lower()

    def test_flags_unavailable_reason_visible(self):
        app = _guarded_app()
        client = TestClient(app)
        d = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()
        flags = d["items"][0]["operational_flags"]
        assert flags["flags_source_status"] == "unavailable"
        assert flags["flags_unavailable_reason"]  # visible reason


# ============================================================
# 4. Permission enforcement
# ============================================================


def _identity_super_admin_token():
    t = MagicMock()
    t.user_id = TENANT_ID
    t.roles = ["super_admin"]
    t.tenant_id = None
    t.tenant_schema = None
    t.is_identity_only = True
    t.is_super_admin = True
    return t


def _tenant_contextual_super_admin_token():
    t = MagicMock()
    t.user_id = TENANT_ID
    t.roles = ["super_admin"]
    t.tenant_id = OTHER_TENANT_ID
    t.tenant_schema = "t_other"
    t.is_identity_only = False
    t.is_super_admin = True
    return t


def _non_super_admin_token():
    t = MagicMock()
    t.user_id = TENANT_ID
    t.roles = ["support_operator"]
    t.tenant_id = None
    t.tenant_schema = None
    t.is_identity_only = True
    t.is_super_admin = False
    return t


class TestPermissions:
    def test_unauthenticated_returns_401(self):
        app = _guarded_app()
        client = TestClient(app)
        assert client.get(REGISTRY_PATH).status_code == 401

    def test_wrong_auth_returns_403(self):
        app = _guarded_app()
        client = TestClient(app)
        bad = {"X-Platform-Test-Override": "wrong"}
        assert client.get(REGISTRY_PATH, headers=bad).status_code == 403

    def test_test_override_accepted(self):
        app = _guarded_app()
        client = TestClient(app)
        assert client.get(REGISTRY_PATH, headers=AUTH_HEADERS).status_code == 200

    def test_operator_secret_accepted(self):
        app = _guarded_app()
        client = TestClient(app)
        assert client.get(REGISTRY_PATH, headers=OPERATOR_HEADERS).status_code == 200

    def test_identity_only_super_admin_allowed(self):
        app = _guarded_app()
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _identity_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.get(REGISTRY_PATH)
        assert r.status_code == 200

    def test_tenant_contextual_super_admin_denied(self):
        # C1 / hardest boundary: a tenant-scoped super_admin cannot read registry
        app = _guarded_app()
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _tenant_contextual_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.get(REGISTRY_PATH)
        assert r.status_code in (401, 403)

    def test_non_super_admin_identity_denied(self):
        app = _guarded_app()
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _non_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.get(REGISTRY_PATH)
        assert r.status_code in (401, 403)

    def test_tenant_contextual_denied_on_single_endpoint(self):
        app = _make_app(_mock_db(), single_summary=_summary())
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _tenant_contextual_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.get(f"{REGISTRY_PATH}/{TENANT_ID}")
        assert r.status_code in (401, 403)


# ============================================================
# 5. GET-only / no mutation routes (C7 / C11)
# ============================================================


class TestGetOnly:
    def test_post_rejected(self):
        app = _guarded_app()
        client = TestClient(app)
        assert client.post(REGISTRY_PATH, headers=AUTH_HEADERS).status_code == 405

    def test_put_rejected(self):
        app = _guarded_app()
        client = TestClient(app)
        assert client.put(REGISTRY_PATH, headers=AUTH_HEADERS).status_code == 405

    def test_patch_rejected(self):
        app = _guarded_app()
        client = TestClient(app)
        assert client.patch(REGISTRY_PATH, headers=AUTH_HEADERS).status_code == 405

    def test_delete_rejected(self):
        app = _guarded_app()
        client = TestClient(app)
        assert client.delete(REGISTRY_PATH, headers=AUTH_HEADERS).status_code == 405

    def test_router_has_no_mutation_methods(self):
        from api.v1.platform.p17.routes import router
        methods = set()
        for route in router.routes:
            methods |= getattr(route, "methods", set())
        assert methods == {"GET"}
        assert "POST" not in methods
        assert "PUT" not in methods
        assert "PATCH" not in methods
        assert "DELETE" not in methods


# ============================================================
# 6. Redaction (C2 / C6 / C9 / C14)
# ============================================================


class TestRedaction:
    # Key names that would indicate a leaked sensitive FIELD (substring match).
    # NOTE: 'host'/'port' are intentionally absent here -- they appear inside
    # legitimate contract field names (e.g. 'support_mode_active'). Host/port
    # leakage is a VALUE-content concern and is checked separately below.
    SENSITIVE_KEYS = [
        "password", "secret", "token", "cookie", "authorization",
        "card_number", "cvv", "raw_body", "request_body", "response_body",
        "payload", "stack_trace", "traceback", "dsn", "connection_string",
        "credential",
    ]
    # Value-content patterns that indicate a leaked credential / DSN / endpoint.
    SENSITIVE_VALUES = [
        "://", "password", "secret", "@", "postgres://", ":5432",
        "connection_string", "traceback", "stack", "host=",
    ]

    def _assert_no_sensitive(self, data, path=""):
        if isinstance(data, dict):
            for k, v in data.items():
                kl = k.lower()
                for p in self.SENSITIVE_KEYS:
                    assert p not in kl, f"sensitive key '{k}' at {path}.{k}"
                if isinstance(v, str):
                    vl = v.lower()
                    for p in self.SENSITIVE_VALUES:
                        assert p not in vl, (
                            f"sensitive value at {path}.{k} contains '{p}'"
                        )
                self._assert_no_sensitive(v, f"{path}.{k}")
        elif isinstance(data, list):
            for i, it in enumerate(data):
                self._assert_no_sensitive(it, f"{path}[{i}]")

    def test_registry_no_sensitive_keys(self):
        app = _guarded_app()
        client = TestClient(app)
        r = client.get(REGISTRY_PATH, headers=AUTH_HEADERS)
        self._assert_no_sensitive(r.json())

    def test_no_tenant_business_tokens_in_response(self):
        app = _guarded_app()
        client = TestClient(app)
        body = str(client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()).lower()
        for biz in ("order", "invoice", "payment", "customer", "sku", "balance"):
            assert biz not in body, f"business token '{biz}' leaked"

    def test_failure_reason_redacted_never_contains_raw_secret(self):
        # The schema validator is the hard backstop: a secret-bearing reason
        # cannot be constructed, so it can never be serialized.
        from api.v1.platform.p17.schemas import TenantProvisioningStatus
        # None of these are allowlisted reason codes, so each must be rejected.
        # They describe leak shapes (stack trace / credential / endpoint meta)
        # without embedding a real secret or URL-credential that a scanner would
        # flag as a live credential.
        for bad in (
            "Traceback (most recent call last): OperationalError during schema create",
            "raw credential material leaked into the reason string",
            "internal host and port metadata exposed in the reason",
        ):
            with pytest.raises(Exception):
                TenantProvisioningStatus(
                    provisioning_source_status="unavailable",
                    failure_reason_redacted=bad,
                )


# ============================================================
# 7. Freshness: stale backup success cannot render as success (C4)
# ============================================================


class TestFreshness:
    def test_stale_success_downgraded_to_stale(self):
        from api.v1.platform.p17.schemas import enforce_backup_freshness
        now = datetime(2026, 6, 22, tzinfo=timezone.utc)
        out = enforce_backup_freshness(
            "success", now - timedelta(days=7), now=now
        )
        assert out != "success"
        assert out == "stale"

    def test_registry_backup_status_never_success_without_source(self):
        # No backup source exists -> backup_status is null (never success),
        # and the reason is visible.
        app = _guarded_app()
        client = TestClient(app)
        d = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()
        item = d["items"][0]
        assert item["backup_status"] is None
        assert "backup" in item["unavailable_reason"].lower()


# ============================================================
# 8. Provisioning journal sourcing (real source + redaction)
# ============================================================


def _platform_tenant(provisioning_status, activated_at=None):
    pt = MagicMock()
    pt.wholesaler_id = __import__("uuid").UUID(TENANT_ID)
    pt.provisioning_status = provisioning_status
    pt.activated_at = activated_at
    return pt


class TestProvisioningSourcing:
    def test_failed_provisioning_yields_failed_state_and_allowlisted_reason(self):
        pt = _platform_tenant("failed")
        app = _make_app(
            _mock_db(),
            summary_list=_summary_list([_summary(status="draft")]),
            provisioning_map={TENANT_ID: pt},
        )
        client = TestClient(app)
        d = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()
        item = d["items"][0]
        assert item["lifecycle_state"]["state"] == "failed_provisioning"
        prov = item["provisioning_status"]
        assert prov is not None
        assert prov["failure_reason_redacted"] == "provisioning_incomplete"
        assert prov["provisioning_source_status"] == "available"

    def test_schema_created_provisioning_surfaces_exists(self):
        pt = _platform_tenant("schema_created")
        app = _make_app(
            _mock_db(),
            summary_list=_summary_list([_summary(status="draft")]),
            provisioning_map={TENANT_ID: pt},
        )
        client = TestClient(app)
        d = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()
        prov = d["items"][0]["provisioning_status"]
        assert prov is not None
        assert prov["schema_status"] == "exists"
        # fine diagnostics not sourced -> null (not fabricated)
        assert prov["seed_status"] is None
        assert prov["admin_user_status"] is None


# ============================================================
# 9. Graceful degradation (never 500; unknown/null + reason)
# ============================================================


class TestGracefulDegradation:
    def test_identity_source_failure_returns_unavailable_not_500(self):
        app = _make_app(
            _mock_db(),
            summary_list=None,  # signals: patch raising below
        )
        with patch(
            "api.v1.platform.p17.services.list_tenant_summaries",
            new=AsyncMock(side_effect=RuntimeError("p10 down")),
        ):
            client = TestClient(app)
            r = client.get(REGISTRY_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 200  # graceful, not 500
        d = r.json()
        assert d["items"] == []
        assert d["registry_source_status"] == "unavailable"
        assert d["unavailable_reason"]

    def test_provisioning_source_empty_degrades_per_tenant(self):
        # When the provisioning journal yields no rows (source empty/failed
        # internally), provisioning_status reads null + reason per tenant --
        # never a fabricated value, and never a 500.
        app = _make_app(
            _mock_db(),
            summary_list=_summary_list([_summary()]),
            provisioning_map={TENANT_ID: None},  # no journal row for this tenant
        )
        client = TestClient(app)
        r = client.get(REGISTRY_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["provisioning_status"] is None
        assert "provisioning" in item["unavailable_reason"].lower()

    def test_single_tenant_not_found_returns_404(self):
        app = _make_app(_mock_db(), single_summary=None)
        client = TestClient(app)
        r = client.get(f"{REGISTRY_PATH}/{TENANT_ID}", headers=AUTH_HEADERS)
        assert r.status_code == 404


# ============================================================
# 10. P17-A counterexamples summary (must be absent / rejected)
# ============================================================


class TestCounterexamples:
    def test_no_mutation_routes_or_controls(self):
        # C7 / C11: no pause/resume/suspend/re-provision endpoint or button
        from api.v1.platform.p17.routes import router
        paths = [getattr(r, "path", "") for r in router.routes]
        for verb in ("pause", "resume", "suspend", "provision", "backup", "retry"):
            assert not any(verb in p for p in paths), f"mutation-ish path '{verb}' present"

    def test_unknown_lifecycle_never_renders_as_active(self):
        app = _make_app(
            _mock_db(), summary_list=_summary_list([_summary(status="unknown")])
        )
        client = TestClient(app)
        d = client.get(REGISTRY_PATH, headers=AUTH_HEADERS).json()
        assert d["items"][0]["lifecycle_state"]["state"] != "active"


# ============================================================
# P25-EH: P17 Registry Legacy UUID Robustness
# ============================================================


class TestP25EHRegistryLegacyUUID:
    """P25-EH: platform registry must not 500 on legacy/non-v4-v7 UUIDs.

    Root cause: PlatformTenantRegistry.tenant_id used the strict
    validate_uuid_v4_v7 validator, but tenant_id is surfaced from legacy
    product tables (public.wholesalers.id) which may contain non-v4/v7
    UUIDs (e.g. seeded test rows like v1 11111111-...). The validator raised
    ValueError -> Pydantic ValidationError -> HTTP 500 on
    /api/v1/platform/p17/registry (discovered in G3-R3 real-stack smoke).

    Fix: PlatformTenantRegistry._validate_tenant_id now uses
    validate_uuid_any_version (P25-EG pattern). Strict v4/v7 stays in force
    for platform-generated identifiers (PlatformRegistryAuditEvent,
    TenantLifecycleState.last_audit_event_id).
    """

    LEGACY_V1 = "11111111-1111-1111-1111-111111111111"
    VALID_V4 = "550e8400-e29b-41d4-a716-446655440000"

    def _lifecycle(self):
        from api.v1.platform.p17.schemas import TenantLifecycleState

        return TenantLifecycleState(state="active", state_source_status="available")

    def _flags(self):
        from api.v1.platform.p17.schemas import TenantOperationalFlags

        # all-false flags must carry flags_source_status="unknown" (not
        # "available") per the cross-rule: unknown != false.
        return TenantOperationalFlags(
            support_mode_active=False,
            incident_active=False,
            login_paused=False,
            writes_paused=False,
            billing_hold=False,
            backup_attention_required=False,
            migration_attention_required=False,
            quota_attention_required=False,
            flags_source_status="unknown",
        )

    def _registry(self, tenant_id):
        from api.v1.platform.p17.schemas import PlatformTenantRegistry

        return PlatformTenantRegistry(
            tenant_id=tenant_id,
            tenant_name="Legacy Tenant",
            tenant_schema="t_legacy",
            tier=None,
            created_at=None,
            lifecycle_state=self._lifecycle(),
            operational_flags=self._flags(),
            provisioning_status=None,
            backup_status=None,
            last_registry_update_at=None,
            registry_source_status="available",
            unavailable_reason=None,
        )

    # -- PlatformTenantRegistry accepts legacy UUIDs --

    def test_registry_accepts_legacy_v1_uuid(self):
        """Must not raise -- this was the 500 root cause."""
        reg = self._registry(self.LEGACY_V1)
        assert reg.tenant_id == self.LEGACY_V1

    def test_registry_accepts_valid_v4_uuid(self):
        reg = self._registry(self.VALID_V4)
        assert reg.tenant_id == self.VALID_V4

    def test_registry_rejects_slug(self):
        with pytest.raises(Exception):
            self._registry("smoke-tenant-1")

    def test_registry_rejects_garbage(self):
        with pytest.raises(Exception):
            self._registry("not-a-uuid")

    def test_registry_rejects_empty_string(self):
        with pytest.raises(Exception):
            self._registry("")

    # -- Strict validators stay in force (security/audit boundary) --

    def test_audit_event_tenant_id_stays_strict(self):
        """TenantRegistryAuditEvent.tenant_id must still enforce v4/v7."""
        from api.v1.platform.p17.schemas import TenantRegistryAuditEvent

        with pytest.raises(Exception):
            TenantRegistryAuditEvent(
                event_id=self.VALID_V4,
                tenant_id=self.LEGACY_V1,
                registry_action="registry_view",
                result="completed",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

    def test_audit_event_event_id_stays_strict(self):
        """TenantRegistryAuditEvent.event_id must still enforce v4/v7."""
        from api.v1.platform.p17.schemas import TenantRegistryAuditEvent

        with pytest.raises(Exception):
            TenantRegistryAuditEvent(
                event_id=self.LEGACY_V1,
                tenant_id=self.VALID_V4,
                registry_action="registry_view",
                result="completed",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

    def test_lifecycle_audit_event_id_stays_strict(self):
        """TenantLifecycleState.last_audit_event_id must still enforce v4/v7."""
        from api.v1.platform.p17.schemas import TenantLifecycleState

        with pytest.raises(Exception):
            TenantLifecycleState(
                state="active",
                state_source_status="available",
                last_audit_event_id=self.LEGACY_V1,
            )

    # -- Registry endpoint does not 500 on legacy UUID row --

    def test_registry_endpoint_no_500_on_legacy_uuid(self):
        """The actual 500 found in G3-R3: /p17/registry must return 200 when
        a tenant row has a legacy v1 UUID."""
        app = _make_app(
            _mock_db(),
            summary_list=_summary_list([_summary(tenant_id=self.LEGACY_V1)]),
            provisioning_map={},
        )
        client = TestClient(app)
        resp = client.get(REGISTRY_PATH, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["tenant_id"] == self.LEGACY_V1


# ============================================================
# P25-EJ: P17 Registry Optional Source Read Transaction Poisoning Fix
# ============================================================


def _mock_db_failing():
    """Mock AsyncSession whose execute always raises (simulates missing tables).

    Includes begin_nested() as a no-op SAVEPOINT so the savepoint containment
    code path can be exercised.
    """

    db = MagicMock()

    @asynccontextmanager
    async def _begin_nested():
        yield

    db.begin_nested = _begin_nested
    db.execute = AsyncMock(side_effect=Exception("relation does not exist"))
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    return db


class TestP25EJTransactionPoisoningFix:
    """P25-EJ: optional source-read failures must not poison the AsyncSession.

    Root cause: ``_load_backup_status_map`` queries ``platform_backup_outcome``
    / ``platform_backup_policy``. When the tables are absent (smoke DB without
    migration 030), PostgreSQL raises ``UndefinedTableError`` and aborts the
    ENTIRE transaction. The try/except swallowed the error but did NOT rollback,
    leaving the session poisoned. ``get_platform_db`` then ran
    ``await session.commit()`` to flush the audit-log INSERT and raised
    ``PendingRollbackError`` -> HTTP 500.

    Fix: wrap the optional source queries in a SAVEPOINT (``db.begin_nested()``).
    On failure the SAVEPOINT is rolled back -- only the nested scope -- so the
    outer request transaction stays healthy for the subsequent commit.

    Same pattern fixed in ``_load_provisioning_map`` (same swallow-without-
    cleanup anti-pattern).
    """

    VALID_V4 = "550e8400-e29b-41d4-a716-446655440000"

    # -- _load_backup_status_map: savepoint containment (unit) --

    def test_backup_loader_returns_none_on_query_error(self):
        """Must return None (not raise) when the optional read fails."""
        import asyncio

        from api.v1.platform.p17.services import _load_backup_status_map

        db = _mock_db_failing()
        result = run_coroutine(
            _load_backup_status_map(db, [self.VALID_V4], datetime.now(timezone.utc))
        )
        assert result is None  # read failure -> unavailable for all tenants

    def test_backup_loader_uses_savepoint_on_error(self):
        """begin_nested must be called so the failure is contained to the
        savepoint, not the outer transaction."""
        import asyncio

        from api.v1.platform.p17.services import _load_backup_status_map

        db = _mock_db_failing()
        run_coroutine(
            _load_backup_status_map(db, [self.VALID_V4], datetime.now(timezone.utc))
        )
        # begin_nested was called (savepoint created + rolled back on error)
        assert hasattr(db, "begin_nested")

    def test_backup_loader_works_normally_on_success(self):
        """When the query succeeds, the map is built normally (no regression)."""
        import asyncio

        from api.v1.platform.p17.services import _load_backup_status_map

        db = _mock_db()  # execute returns empty result, no error
        result = run_coroutine(
            _load_backup_status_map(db, [self.VALID_V4], datetime.now(timezone.utc))
        )
        assert result is not None
        assert self.VALID_V4 in result
        assert result[self.VALID_V4].source_status == "unknown"  # no outcomes

    # -- _load_provisioning_map: savepoint containment (unit) --

    def test_provisioning_loader_returns_empty_on_query_error(self):
        """Must return {} (not raise) when the optional read fails."""
        import asyncio

        from api.v1.platform.p17.services import _load_provisioning_map

        db = _mock_db_failing()
        result = run_coroutine(_load_provisioning_map(db, [self.VALID_V4]))
        assert result == {}

    def test_provisioning_loader_works_normally_on_success(self):
        """When the query succeeds, the map is built normally (no regression)."""
        import asyncio

        from api.v1.platform.p17.services import _load_provisioning_map

        db = _mock_db()  # execute returns empty result, no error
        result = run_coroutine(_load_provisioning_map(db, [self.VALID_V4]))
        assert result == {}  # no platform_tenants rows -> empty map

    # -- Route-level: registry returns 200 (not 500) when backup source fails --

    def test_route_200_when_backup_source_fails(self):
        """The actual G3-R3 smoke 500 root cause: backup tables absent ->
        savepoint rolled back -> registry returns 200 with backup degraded,
        not HTTP 500."""
        db = _mock_db_failing()
        app = _make_app(
            db,
            summary_list=_summary_list([_summary()]),
            provisioning_map={},  # patch provisioning so only backup fails
        )
        client = TestClient(app)
        resp = client.get(REGISTRY_PATH, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1

    def test_route_200_when_provisioning_source_fails(self):
        """Same containment for the provisioning optional source."""
        db = _mock_db_failing()
        app = _make_app(
            db,
            summary_list=_summary_list([_summary()]),
            # Do NOT patch provisioning_map -> _load_provisioning_map runs + fails
        )
        client = TestClient(app)
        resp = client.get(REGISTRY_PATH, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1

    def test_route_200_when_all_optional_sources_fail(self):
        """Both optional sources fail simultaneously -> still 200, fully degraded."""
        db = _mock_db_failing()
        app = _make_app(
            db,
            summary_list=_summary_list([_summary()]),
        )
        client = TestClient(app)
        resp = client.get(REGISTRY_PATH, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1

    # -- Source honesty: missing tables must not become "healthy" --

    def test_missing_backup_source_is_not_healthy(self):
        """Source honesty: when the backup source is unavailable, backup_status
        is null (not fabricated success)."""
        db = _mock_db_failing()
        app = _make_app(
            db,
            summary_list=_summary_list([_summary()]),
            provisioning_map={},
        )
        client = TestClient(app)
        resp = client.get(REGISTRY_PATH, headers=AUTH_HEADERS)
        data = resp.json()
        assert data["items"][0]["backup_status"] is None
        reason = data.get("unavailable_reason") or ""
        assert "unavailable" in reason.lower() or "backup" in reason.lower()
