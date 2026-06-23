# P18-D real registry source status integration tests.
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from tests.test_platform_p18_controlled_actions import (
    AUTH_HEADERS,
    REQUEST_PATH,
    _ACTIVE_PATCHERS,
    _make_app,
    _payload,
    _start_patch,
)


@pytest.fixture(autouse=True)
def _stop_patches_after_test():
    yield
    while _ACTIVE_PATCHERS:
        _ACTIVE_PATCHERS.pop().stop()


def _registry(
    *,
    lifecycle_source="available",
    flags_source="unavailable",
    provisioning_source=None,
    backup_source=None,
):
    reg = MagicMock()
    reg.lifecycle_state.state_source_status = lifecycle_source
    reg.operational_flags.flags_source_status = flags_source
    if provisioning_source is None:
        reg.provisioning_status = None
    else:
        reg.provisioning_status.provisioning_source_status = provisioning_source
    if backup_source is None:
        reg.backup_status = None
    else:
        reg.backup_status.backup_source_status = backup_source
    return reg


def test_lifecycle_accepted_when_lifecycle_available():
    app = _make_app(registry=_registry(lifecycle_source="available"))
    client = TestClient(app)
    body = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=_payload()).json()
    assert body["result"] == "accepted"
    assert body["source_status"] == "available"
    assert body["executed"] is False


def test_lifecycle_denied_when_lifecycle_unknown():
    reg = _registry()
    reg.lifecycle_state.state_source_status = "unknown"
    app = _make_app(registry=reg)
    client = TestClient(app)
    body = client.post(
        REQUEST_PATH, headers=AUTH_HEADERS, json=_payload(action_type="tenant.pause")
    ).json()
    assert body["result"] == "denied"
    assert body["source_status"] == "unknown"


def test_lifecycle_transition_maps_to_lifecycle_source():
    app = _make_app(registry=_registry(lifecycle_source="available"))
    client = TestClient(app)
    body = client.post(
        REQUEST_PATH,
        headers=AUTH_HEADERS,
        json=_payload(action_type="lifecycle.transition", requested_state="paused"),
    ).json()
    assert body["source_status"] == "available"
    assert body["result"] == "accepted"


def test_flag_actions_denied_when_flags_unavailable():
    app = _make_app(registry=_registry(flags_source="unavailable", lifecycle_source="available"))
    client = TestClient(app)
    for idx, action_type in enumerate(("support_mode.on", "incident.flag_set")):
        body = client.post(
            REQUEST_PATH,
            headers=AUTH_HEADERS,
            json=_payload(action_type=action_type, idempotency_key="flag-%d" % idx),
        ).json()
        assert body["result"] == "denied"
        assert body["source_status"] == "unavailable"


def test_provisioning_recheck_accepted_when_provisioning_available():
    app = _make_app(registry=_registry(provisioning_source="available"))
    client = TestClient(app)
    body = client.post(
        REQUEST_PATH,
        headers=AUTH_HEADERS,
        json=_payload(action_type="provisioning.recheck", confirm=False, idempotency_key="pr-ok"),
    ).json()
    assert body["result"] == "accepted"
    assert body["source_status"] == "available"


def test_provisioning_recheck_degraded_when_provisioning_null():
    app = _make_app(registry=_registry(provisioning_source=None))
    client = TestClient(app)
    body = client.post(
        REQUEST_PATH,
        headers=AUTH_HEADERS,
        json=_payload(action_type="provisioning.recheck", confirm=False, idempotency_key="pr-deg"),
    ).json()
    assert body["result"] == "degraded"
    assert body["source_status"] == "unavailable"
    assert body["degraded_reason"] is not None


def test_backup_check_degraded_when_backup_null():
    app = _make_app(registry=_registry(backup_source=None))
    client = TestClient(app)
    body = client.post(
        REQUEST_PATH,
        headers=AUTH_HEADERS,
        json=_payload(action_type="backup.check", confirm=False, idempotency_key="bk-deg"),
    ).json()
    assert body["result"] == "degraded"
    assert body["source_status"] == "unavailable"


def test_backup_restore_test_denied_when_backup_null():
    app = _make_app(registry=_registry(backup_source=None))
    client = TestClient(app)
    body = client.post(
        REQUEST_PATH,
        headers=AUTH_HEADERS,
        json=_payload(
            action_type="backup.restore_test_request", confirm=True, idempotency_key="brt-deny"
        ),
    ).json()
    assert body["result"] == "denied"
    assert body["source_status"] == "unavailable"


def test_tenant_not_found_resolves_unknown():
    app = _make_app(registry=None)
    client = TestClient(app)
    body = client.post(
        REQUEST_PATH, headers=AUTH_HEADERS, json=_payload(action_type="tenant.pause")
    ).json()
    assert body["result"] == "denied"
    assert body["source_status"] == "unknown"


def test_registry_read_error_resolves_unknown():
    app = _make_app()
    _start_patch(
        "api.v1.platform.p18.services.get_tenant_registry",
        AsyncMock(side_effect=RuntimeError("p17 read failed")),
    )
    client = TestClient(app)
    body = client.post(
        REQUEST_PATH,
        headers=AUTH_HEADERS,
        json=_payload(action_type="provisioning.recheck", confirm=False, idempotency_key="err"),
    ).json()
    assert body["result"] == "degraded"
    assert body["source_status"] == "unknown"


def test_null_tenant_id_resolves_unknown():
    app = _make_app(registry=_registry())
    client = TestClient(app)
    body = client.post(
        REQUEST_PATH,
        headers=AUTH_HEADERS,
        json=_payload(action_type="incident.flag_set", tenant_id=None),
    ).json()
    assert body["result"] == "denied"
    assert body["source_status"] == "unknown"


def test_real_mapping_results_remain_not_executed():
    app = _make_app(
        registry=_registry(lifecycle_source="available", provisioning_source="available")
    )
    client = TestClient(app)
    for payload in (
        _payload(action_type="tenant.pause"),
        _payload(action_type="provisioning.recheck", confirm=False, idempotency_key="nx"),
    ):
        body = client.post(REQUEST_PATH, headers=AUTH_HEADERS, json=payload).json()
        assert body["executed"] is False
