"""
P18 Controlled Platform Actions API tests (P18-B request skeleton).

Contract-backed, NON-EXECUTING request skeleton. Covers:
  - catalog GET (closed set of 10 actions; executed == False)
  - valid request accepted but NOT executed (executed == False; recorded)
  - missing reason / missing idempotency_key / unsupported action_type -> denied
  - tenant-contextual admin denied; unauthenticated denied; non-super_admin denied
  - duplicate idempotency (same payload -> duplicate; different payload -> conflict)
  - write / write_request against unknown registry source -> denied
  - degraded read allowed ONLY for provisioning.recheck / backup.check
  - confirmation required for write / write_request actions
  - no mutation endpoints to P17 registry / tenant state (executed == False; route set)
  - no tenant business data in any response
  - metadata redaction (no raw secret / DSN / host / port)
  - validate is a dry run (does not persist; not executed)

Aligned to docs/ai/PLATFORM_PRODUCT_P18_CONTROLLED_ACTIONS_CONTRACT.md (P18-A).
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")


# -- Helpers (mirror the P15/P17 test harness) --

AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}

P18_BASE = "/api/v1/platform/p18"
CATALOG_PATH = f"{P18_BASE}/actions/catalog"
VALIDATE_PATH = f"{P18_BASE}/actions/validate"
REQUEST_PATH = f"{P18_BASE}/actions/request"


def recorded_path(action_id: str) -> str:
    return f"{P18_BASE}/actions/requests/{action_id}"


TENANT_ID = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
OTHER_TENANT_ID = "c3d4e5f6-a7b8-49c0-9d1e-2f3a4b5c6d7e"

EXPECTED_ACTION_TYPES = {
    "support_mode.on",
    "support_mode.off",
    "tenant.pause",
    "tenant.resume",
    "incident.flag_set",
    "incident.flag_clear",
    "provisioning.recheck",
    "backup.check",
    "backup.restore_test_request",
    "lifecycle.transition",
}

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
    return db


def _make_app(mock_db=None, *, source_status=None, registry=None):
    """Build an app with the P18 router; reset the store; optionally fix source status."""
    from api.v1.platform.p18 import services
    from api.v1.platform.p18.routes import router
    from api.dependencies import get_db, get_platform_db

    services.reset_store()
    app = FastAPI()

    async def override():
        yield mock_db or _mock_db()

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    app.include_router(router)

    if source_status is not None:
        _start_patch(
            "api.v1.platform.p18.services._resolve_action_source_status",
            AsyncMock(return_value=source_status),
        )
    else:
        _start_patch(
            "api.v1.platform.p18.services.get_tenant_registry",
            AsyncMock(return_value=registry),
        )
    return app


def _payload(**overrides):
    base = {
        "action_type": "tenant.pause",
        "tenant_id": TENANT_ID,
        "reason": "routine ops review",
        "idempotency_key": "idem-1",
        "confirm": True,
    }
    base.update(overrides)
    return base


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


# ============================================================
# 1. Catalog
# ============================================================


class TestCatalog:
    def test_catalog_returns_closed_set_of_ten_actions(self):
        app = _make_app()
        client = TestClient(app)
        r = client.get(CATALOG_PATH, headers=AUTH_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 10
        assert body["executed"] is False
        assert body["contract"] == "P18-A"
        types = {item["action_type"] for item in body["items"]}
        assert types == EXPECTED_ACTION_TYPES

    def test_catalog_marks_only_recheck_and_backup_check_degradable(self):
        app = _make_app()
        client = TestClient(app)
        body = client.get(CATALOG_PATH, headers=AUTH_HEADERS).json()
        by_type = {item["action_type"]: item for item in body["items"]}
        assert by_type["provisioning.recheck"]["degraded_allowed"] is True
        assert by_type["backup.check"]["degraded_allowed"] is True
        for action_type, item in by_type.items():
            if action_type not in ("provisioning.recheck", "backup.check"):
                assert item["degraded_allowed"] is False

    def test_catalog_descriptions_state_not_executed(self):
        app = _make_app()
        client = TestClient(app)
        body = client.get(CATALOG_PATH, headers=AUTH_HEADERS).json()
        for item in body["items"]:
            assert "not executed" in item["description"].lower()


# ============================================================
# 2. Valid request accepted but not executed
# ============================================================


class TestRequestAcceptance:
    def test_valid_request_accepted_but_not_executed(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=_payload())
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "accepted"
        assert body["executed"] is False
        assert body["action_id"] is not None
        assert "not executed" in body["message"].lower() or "not" in body["message"].lower()
        # previous_state never populated (nothing read/mutated)
        assert body["previous_state"] is None

    def test_recorded_request_retrievable_and_still_not_executed(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        action_id = client.post(
            REQUEST_PATH, headers=AUTH_HEADERS, json=_payload()
        ).json()["action_id"]
        r = client.get(recorded_path(action_id), headers=AUTH_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["executed"] is False
        assert body["action_id"] == action_id

    def test_get_unknown_request_returns_404(self):
        app = _make_app()
        client = TestClient(app)
        r = client.get(recorded_path("does-not-exist"), headers=AUTH_HEADERS)
        assert r.status_code == 404


# ============================================================
# 3. Validation denials
# ============================================================


class TestValidationDenials:
    def test_missing_reason_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(reason=None),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "denied"
        assert "reason" in body["message"].lower()

    def test_empty_reason_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(
            REQUEST_PATH, headers=AUTH_HEADERS, json=_payload(reason="   ")
        )
        assert r.status_code == 200
        assert r.json()["result"] == "denied"

    def test_missing_idempotency_key_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(idempotency_key=None),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "denied"
        assert "idempotency" in body["message"].lower()

    def test_unsupported_action_type_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(action_type="evil.mutate"),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "denied"
        assert body["action_type"] == "evil.mutate"

    def test_confirmation_required_for_write_action(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(
            REQUEST_PATH, headers=AUTH_HEADERS, json=_payload(confirm=False)
        )
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "denied"
        assert "confirmation" in body["message"].lower()


# ============================================================
# 4. Permissions
# ============================================================


class TestPermissions:
    def test_unauthenticated_denied_401(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        # Valid body, no credentials -> 401
        r = client.post(REQUEST_PATH, json=_payload())
        assert r.status_code == 401

    def test_wrong_test_override_denied_403(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(REQUEST_PATH, json=_payload(),
                        headers={"X-Platform-Test-Override": "wrong"})
        assert r.status_code == 403

    def test_test_override_accepted(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=_payload())
        assert r.status_code == 200

    def test_operator_secret_accepted(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(REQUEST_PATH, headers=OPERATOR_HEADERS, json=_payload())
        assert r.status_code == 200

    def test_identity_only_super_admin_allowed(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _identity_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(REQUEST_PATH, json=_payload())
        assert r.status_code == 200

    def test_tenant_contextual_super_admin_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _tenant_contextual_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(REQUEST_PATH, json=_payload())
        assert r.status_code in (401, 403)

    def test_non_super_admin_identity_denied(self):
        # Role granularity is deferred -> non-super_admin identity tokens are denied.
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _non_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(REQUEST_PATH, json=_payload())
        assert r.status_code in (401, 403)


# ============================================================
# 5. Idempotency
# ============================================================


class TestIdempotency:
    def test_duplicate_same_payload_returns_duplicate(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        first = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=_payload()).json()
        assert first["result"] == "accepted"
        second = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=_payload()).json()
        assert second["result"] == "duplicate"
        assert second["executed"] is False
        assert second["action_id"] == first["action_id"]

    def test_duplicate_different_payload_returns_conflict(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        first = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=_payload()).json()
        assert first["result"] == "accepted"
        second = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(reason="a different stated reason"),
        ).json()
        assert second["result"] == "conflict"
        assert second["executed"] is False


# ============================================================
# 6. Source status semantics (unknown source)
# ============================================================


class TestSourceStatus:
    def test_write_against_unknown_source_denied(self):
        # Default resolver returns "unknown" -> write denied.
        app = _make_app()
        client = TestClient(app)
        r = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=_payload())
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "denied"
        assert body["source_status"] == "unknown"
        assert "source" in body["message"].lower()

    def test_write_request_against_unknown_source_denied(self):
        app = _make_app()
        client = TestClient(app)
        r = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(action_type="backup.restore_test_request", confirm=True),
        )
        assert r.json()["result"] == "denied"

    def test_degraded_read_allowed_for_provisioning_recheck(self):
        app = _make_app()  # unknown source
        client = TestClient(app)
        r = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(
                action_type="provisioning.recheck",
                idempotency_key="idem-recheck",
                confirm=False,
            ),
        )
        body = r.json()
        assert body["result"] == "degraded"
        assert body["executed"] is False
        assert body["source_status"] == "unknown"
        assert body["degraded_reason"] is not None

    def test_degraded_read_allowed_for_backup_check(self):
        app = _make_app()  # unknown source
        client = TestClient(app)
        r = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(
                action_type="backup.check",
                idempotency_key="idem-backup",
                confirm=False,
            ),
        )
        assert r.json()["result"] == "degraded"

    def test_read_accepted_when_source_available(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(
                action_type="provisioning.recheck",
                idempotency_key="idem-recheck-ok",
                confirm=False,
            ),
        )
        body = r.json()
        assert body["result"] == "accepted"
        assert body["executed"] is False


# ============================================================
# 7. No mutation / no tenant business data / redaction
# ============================================================


class TestSafetyBoundaries:
    _RESPONSE_FIELDS = {
        "action_id",
        "action_type",
        "result",
        "executed",
        "dry_run",
        "message",
        "reason",
        "idempotency_key",
        "requested_state",
        "previous_state",
        "source_status",
        "degraded_reason",
        "metadata_redacted",
        "correlation_id",
        "created_at",
    }

    def test_no_mutation_route_to_p17_registry_or_tenant_state(self):
        from api.v1.platform.p18.routes import router

        paths = sorted({route.path for route in router.routes})
        assert paths == [
            f"{P18_BASE}/actions/catalog",
            f"{P18_BASE}/actions/request",
            f"{P18_BASE}/actions/requests",
            f"{P18_BASE}/actions/requests/{{action_id}}",
            f"{P18_BASE}/actions/validate",
        ]
        for route in router.routes:
            for method in route.methods:
                assert method in {"GET", "POST"}
                assert method not in {"PUT", "PATCH", "DELETE"}

    def test_response_never_claims_execution(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        for payload in [
            _payload(),
            _payload(action_type="provisioning.recheck", confirm=False, idempotency_key="r1"),
        ]:
            body = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=payload).json()
            assert body["executed"] is False

    def test_no_tenant_business_data_in_response(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=_payload()).json()
        # Response carries only the controlled-action envelope fields.
        assert set(body.keys()) <= self._RESPONSE_FIELDS
        for forbidden in ("orders", "payments", "invoices", "customers", "inventory", "ledger"):
            assert forbidden not in body

    def test_metadata_redaction_strips_secrets(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(
                idempotency_key="idem-redact",
                metadata={
                    "note": "ok to keep",
                    "password": "hunter2",  # pragma: allowlist secret
                    "api_key": "sk-abcdef",  # pragma: allowlist secret
                    "dsn": "postgres://u:p@10.0.0.5:5432/db",  # pragma: allowlist secret
                    "nested": {"token": "abc", "safe": "plain"},  # pragma: allowlist secret
                },
            ),
        ).json()
        redacted = body["metadata_redacted"]
        assert redacted is not None
        assert redacted["note"] == "ok to keep"
        assert redacted["password"] == "[redacted]"
        assert redacted["api_key"] == "[redacted]"
        assert redacted["dsn"] == "[redacted]"
        assert redacted["nested"]["token"] == "[redacted]"
        assert redacted["nested"]["safe"] == "plain"
        # No raw secret / host / port leaks anywhere in the payload.
        serialized = str(body)
        assert "hunter2" not in serialized
        assert "10.0.0.5" not in serialized
        assert "5432" not in serialized
        assert "sk-abcdef" not in serialized


# ============================================================
# 8. Validate is a dry run (no persistence, no execution)
# ============================================================


class TestValidateDryRun:
    def test_validate_returns_dry_run_accepted_not_executed(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(VALIDATE_PATH, headers=AUTH_HEADERS, json=_payload())
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "accepted"
        assert body["dry_run"] is True
        assert body["executed"] is False
        assert body["action_id"] is None

    def test_validate_does_not_persist_so_request_is_not_duplicate(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        # Two validates with the same key never conflict/duplicate (no persistence).
        first = client.post(VALIDATE_PATH, headers=AUTH_HEADERS, json=_payload()).json()
        second = client.post(VALIDATE_PATH, headers=AUTH_HEADERS, json=_payload()).json()
        assert first["result"] == "accepted"
        assert second["result"] == "accepted"
        # A subsequent real request with the same key is accepted (validate did not store).
        third = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=_payload()).json()
        assert third["result"] == "accepted"

    def test_validate_denies_missing_reason(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            VALIDATE_PATH, headers=AUTH_HEADERS, json=_payload(reason=None)
        ).json()
        assert body["result"] == "denied"
        assert body["dry_run"] is True


# ============================================================
# 9. Reason redaction (P18-B/C-R1: no secret value leaks)
# ============================================================


class TestReasonRedaction:
    """R1: a sensitive reason is wholesale-redacted so no secret VALUE remains in
    any response, stored request, or duplicate echo. A clean reason is preserved.
    """

    def test_reason_password_value_not_leaked(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(reason="password=abc123"),  # pragma: allowlist secret
        ).json()
        assert body["reason"] == "[redacted]"
        assert "abc123" not in str(body)

    def test_reason_token_value_not_leaked(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(reason="token abc123"),  # pragma: allowlist secret
        ).json()
        assert body["reason"] == "[redacted]"
        assert "abc123" not in str(body)

    def test_reason_dsn_connection_string_not_leaked(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(reason="postgres://u:p@10.0.0.5:5432/db"),  # pragma: allowlist secret
        ).json()
        assert body["reason"] == "[redacted]"
        serialized = str(body)
        for leak in ("postgres://", "u:p", "10.0.0.5", "5432", "/db"):
            assert leak not in serialized

    def test_reason_host_port_not_leaked(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(reason="connect to db.internal:5432 now"),  # pragma: allowlist secret
        ).json()
        assert body["reason"] == "[redacted]"
        assert "5432" not in str(body)
        assert "db.internal" not in str(body)

    def test_accepted_request_get_by_id_does_not_leak_raw_reason(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        action_id = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(reason="password=secret_value", idempotency_key="k-id"),  # pragma: allowlist secret
        ).json()["action_id"]
        got = client.get(recorded_path(action_id), headers=AUTH_HEADERS).json()
        assert got["reason"] == "[redacted]"
        assert "secret_value" not in str(got)

    def test_duplicate_response_does_not_leak_raw_reason(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        first = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(reason="api_key=sk_987654321", idempotency_key="k-dup"),  # pragma: allowlist secret
        ).json()
        assert first["result"] == "accepted"
        dup = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(reason="api_key=sk_987654321", idempotency_key="k-dup"),  # pragma: allowlist secret
        ).json()
        assert dup["result"] == "duplicate"
        assert dup["reason"] == "[redacted]"
        assert "sk_987654321" not in str(dup)

    def test_clean_reason_is_preserved(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(reason="routine ops review", idempotency_key="k-clean"),
        ).json()
        assert body["reason"] == "routine ops review"
        assert body["result"] == "accepted"

    def test_metadata_redaction_still_passes(self):
        # Regression guard: structured metadata redaction is unchanged by R1.
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(
                idempotency_key="k-md",
                metadata={
                    "note": "ok to keep",
                    "password": "hunter2",  # pragma: allowlist secret
                    "dsn": "postgres://u:p@10.0.0.5:5432/db",  # pragma: allowlist secret
                },
            ),
        ).json()
        redacted = body["metadata_redacted"]
        assert redacted["note"] == "ok to keep"
        assert redacted["password"] == "[redacted]"
        assert redacted["dsn"] == "[redacted]"
        assert "hunter2" not in str(body)


# ============================================================
# 10. Generalized sensitive-input boundary (P18-B/C-R2)
# ============================================================


class TestGeneralizedSensitiveBoundary:
    """R2: every client-supplied echo field is sanitized -- action_type (unsupported
    + sensitive), idempotency_key, requested_state, correlation_id -- so no raw
    sensitive value appears in any response or audit. Clean values are preserved.
    Duplicate / conflict semantics are unchanged (raw values still drive the internal
    store key and one-way fingerprint).
    """

    def test_sensitive_idempotency_key_not_leaked_in_response_or_audit(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        with patch(
            "services.platform_audit_service.append_audit_entry", new=AsyncMock()
        ) as mock_audit:
            body = client.post(
                REQUEST_PATH,
                headers=AUTH_HEADERS,
                json=_payload(idempotency_key="password=abc123"),  # pragma: allowlist secret
            ).json()
        assert body["idempotency_key"] == "[redacted]"
        assert "abc123" not in str(body)
        # Audit metadata must not carry the raw key either.
        assert mock_audit.called
        meta = mock_audit.call_args.kwargs.get("audit_metadata", {}) or {}
        assert meta.get("idempotency_key") == "[redacted]"
        assert "abc123" not in str(meta)

    def test_unsupported_sensitive_action_type_not_leaked(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(action_type="postgres://u:p@10.0.0.5:5432/db"),  # pragma: allowlist secret
        ).json()
        assert body["result"] == "denied"
        assert body["action_type"] == "[redacted]"
        serialized = str(body)
        for leak in ("postgres://", "u:p", "10.0.0.5", "5432", "/db"):
            assert leak not in serialized

    def test_benign_unsupported_action_type_still_echoed(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(action_type="evil.mutate"),
        ).json()
        assert body["result"] == "denied"
        assert body["action_type"] == "evil.mutate"

    def test_sensitive_requested_state_not_leaked(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(
                idempotency_key="k-state",
                requested_state="host=db.internal:5432",  # pragma: allowlist secret
            ),
        ).json()
        assert body["result"] == "accepted"
        assert body["requested_state"] == "[redacted]"
        assert "5432" not in str(body)
        assert "db.internal" not in str(body)

    def test_sensitive_correlation_id_not_leaked(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(
                idempotency_key="k-corr",
                correlation_id="token abc123",  # pragma: allowlist secret
            ),
        ).json()
        assert body["result"] == "accepted"
        assert body["correlation_id"] == "[redacted]"
        assert "abc123" not in str(body)

    def test_duplicate_with_sensitive_key_does_not_leak(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        first = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(idempotency_key="password=abc123"),  # pragma: allowlist secret
        ).json()
        assert first["result"] == "accepted"
        dup = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(idempotency_key="password=abc123"),  # pragma: allowlist secret
        ).json()
        assert dup["result"] == "duplicate"
        assert dup["idempotency_key"] == "[redacted]"
        assert "abc123" not in str(dup)

    def test_conflict_with_sensitive_key_does_not_leak(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(idempotency_key="password=abc123", reason="reason one"),  # pragma: allowlist secret
        ).json()
        conflict = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(idempotency_key="password=abc123", reason="reason two"),  # pragma: allowlist secret
        ).json()
        assert conflict["result"] == "conflict"
        assert conflict["idempotency_key"] == "[redacted]"
        assert "abc123" not in str(conflict)

    def test_get_by_id_does_not_leak_sensitive_echo_fields(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        action_id = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(
                idempotency_key="token xyz999",  # pragma: allowlist secret
                requested_state="postgres://u:p@10.0.0.5:5432/db",  # pragma: allowlist secret
                correlation_id="api_key=sk_123",  # pragma: allowlist secret
            ),
        ).json()["action_id"]
        got = client.get(recorded_path(action_id), headers=AUTH_HEADERS).json()
        assert got["idempotency_key"] == "[redacted]"
        assert got["requested_state"] == "[redacted]"
        assert got["correlation_id"] == "[redacted]"
        serialized = str(got)
        for leak in ("xyz999", "postgres://", "10.0.0.5", "5432", "sk_123"):
            assert leak not in serialized

    def test_clean_echo_fields_preserved(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(
                idempotency_key="clean-key-1",
                requested_state="paused",
                correlation_id="req-abc-123",
            ),
        ).json()
        assert body["result"] == "accepted"
        assert body["idempotency_key"] == "clean-key-1"
        assert body["requested_state"] == "paused"
        assert body["correlation_id"] == "req-abc-123"


# ============================================================
# 11. Operator queue (P18-E)
# ============================================================


class TestOperatorQueue:
    def test_queue_lists_recorded_requests_newest_first(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        first = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(idempotency_key="queue-1"),
        ).json()
        second = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(idempotency_key="queue-2"),
        ).json()

        body = client.get(f"{P18_BASE}/actions/requests", headers=AUTH_HEADERS).json()

        assert body["storage"] == "memory"
        assert body["executed"] is False
        assert body["total"] == 2
        assert [item["action_id"] for item in body["items"]] == [
            second["action_id"],
            first["action_id"],
        ]
        assert all(item["executed"] is False for item in body["items"])

    def test_queue_paginates_and_never_leaks_sensitive_echo_fields(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(
                idempotency_key="password=abc123",  # pragma: allowlist secret
                requested_state="host=db.internal:5432",  # pragma: allowlist secret
                correlation_id="token xyz999",  # pragma: allowlist secret
            ),
        ).json()
        client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(idempotency_key="queue-clean"),
        ).json()

        body = client.get(
            f"{P18_BASE}/actions/requests?limit=1&offset=1",
            headers=AUTH_HEADERS,
        ).json()

        assert body["total"] == 2
        assert body["limit"] == 1
        assert body["offset"] == 1
        assert len(body["items"]) == 1
        serialized = str(body)
        for leak in ("abc123", "db.internal", "5432", "xyz999"):
            assert leak not in serialized
        assert body["items"][0]["idempotency_key"] == "[redacted]"

    def test_queue_requires_platform_auth(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.get(f"{P18_BASE}/actions/requests")
        assert r.status_code in (401, 403)
