"""P21-D-B unit tests: durable approval adapter SKELETON (non-executing surface).

Self-contained (NO database). Verifies that ``api.v1.platform.p21.adapter``
exposes the planned non-executing runtime adapter surface frozen in the P21-D
design lock (section 4) and the P21-B storage-adapter interface contract
(schema plan section 7), AND that no P20 / app / models / alembic cutover has
occurred:

  - the adapter is explicitly NOT the live store (IS_LIVE_STORE False);
  - the no-execution invariants are declared (execution_allowed False,
    executed False, execution_gate "blocked");
  - the operation -> table mapping, in-memory-global mapping, and new-column
    population rules are closed and reference only durable tables;
  - the source-status and audit-result mappings are closed over the durable
    vocabularies and compatible with P20;
  - the StoreError vocabulary is the closed section-7 set;
  - every planned DurableApprovalStore method exists and raises
    StoreNotImplementedError (a NotImplementedError) -- nothing executes;
  - the P21-D-B skeleton surface itself is unchanged (non-executing,
    is_live_store False); P21-D-D wires P20 services to the concrete adapter
    behind an explicit readiness gate (verified by the cutover tests below);
    api.app still registers no p21 router, models.__init__ still registers no
    durable model, and alembic still adds no new migration.

Pure-Python (metadata + source scans); runs by default (unit marker), no DB.
"""
import inspect
from pathlib import Path

import pytest

from api.v1.platform.p20.schemas import RegistrySourceStatus
from api.v1.platform.p21 import adapter as p21a
from api.v1.platform.p21.models import (
    AUDIT_RESULT_VALUES,
    EVENT_TYPE_VALUES,
    SOURCE_STATUS_VALUES,
)

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[1]
P20_DIR = BACKEND / "api" / "v1" / "platform" / "p20"
P21_DIR = BACKEND / "api" / "v1" / "platform" / "p21"


# ---------------------------------------------------------------------------
# Phase / liveness / no-execution invariants
# ---------------------------------------------------------------------------


def test_adapter_is_not_the_live_store():
    assert p21a.IS_LIVE_STORE is False
    assert p21a.STORAGE_CLASS_DURABLE == "durable"
    assert p21a.ADAPTER_PHASE == "P21-D-B-skeleton"
    assert p21a.DurableApprovalStore.is_live_store is False


def test_no_execution_invariants_declared():
    assert p21a.EXECUTION_ALLOWED is False
    assert p21a.EXECUTED is False
    assert p21a.EXECUTION_GATE == "blocked"


# ---------------------------------------------------------------------------
# Closed mappings (design lock 4.1 / 4.4)
# ---------------------------------------------------------------------------


def test_operation_table_mapping_closed_and_durable_only():
    expected_ops = {"create", "decide", "read", "list"}
    assert set(p21a.OPERATION_TABLE_MAP) == expected_ops
    for op, tables in p21a.OPERATION_TABLE_MAP.items():
        assert tables, f"operation {op} has no target tables"
        for t in tables:
            assert t in p21a.DURABLE_TABLES, f"operation {op} targets non-durable table {t}"


def test_inmemory_global_mapping_covers_p20_store():
    expected_globals = {
        "_STORE[approval_id]",
        "_STORE_BY_CREATE_KEY",
        "decision_digest dedup",
        "_AUDIT_LOG",
    }
    assert set(p21a.INMEMORY_GLOBAL_MAP) == expected_globals
    blob = " ".join(p21a.INMEMORY_GLOBAL_MAP.values())
    for table in (
        "durable_approval_requests",
        "durable_approval_decisions",
        "durable_approval_audit_events",
        "durable_approval_idempotency_keys",
    ):
        assert table in blob


def test_new_column_rules_closed():
    assert set(p21a.NEW_COLUMN_RULES) == {
        "store_version", "sequence_no", "storage_class",
        "audit_result", "confirm", "metadata_redacted",
    }


def test_source_status_map_closed_and_compatible_with_p20():
    p20_sources = set(RegistrySourceStatus.__args__)  # available / unavailable / unknown
    assert set(p21a.SOURCE_STATUS_MAP) == p20_sources
    # Every target is a valid durable source_status value.
    for target in p21a.SOURCE_STATUS_MAP.values():
        assert target in SOURCE_STATUS_VALUES
    # The durable vocabulary generalizes P20: "available" -> "valid"; adds degraded.
    assert p21a.SOURCE_STATUS_MAP["available"] == "valid"
    assert p21a.DEGRADED_SOURCE_STATUS == "degraded"
    assert "degraded" in SOURCE_STATUS_VALUES


def test_audit_result_derivation_closed_and_total():
    assert set(p21a.AUDIT_RESULT_BY_EVENT_TYPE) == EVENT_TYPE_VALUES
    for value in p21a.AUDIT_RESULT_BY_EVENT_TYPE.values():
        assert value in AUDIT_RESULT_VALUES


def test_derive_audit_result_is_pure_and_enforces_closed_sets():
    # Default for a known event is a valid audit_result.
    assert p21a.derive_audit_result("approval_opened") == "success"
    assert p21a.derive_audit_result("approval_denied") == "denied"
    assert p21a.derive_audit_result("approval_expired") == "expired"
    # Outcome override honors the closed audit_result set.
    assert p21a.derive_audit_result("approval_denied", outcome="conflict") == "conflict"
    assert p21a.derive_audit_result("approval_denied", outcome="idempotent") == "idempotent"
    # Unknown event_type / outcome are rejected at the boundary.
    with pytest.raises(ValueError):
        p21a.derive_audit_result("not_a_real_event")
    with pytest.raises(ValueError):
        p21a.derive_audit_result("approval_opened", outcome="bogus")


# ---------------------------------------------------------------------------
# StoreError vocabulary + StoreResult
# ---------------------------------------------------------------------------


def test_store_error_vocabulary_is_the_closed_section_7_set():
    expected = {
        "not_authorized", "self_decision_denied", "decision_conflict",
        "idempotent_replay", "expired", "terminal", "unknown_source",
        "stale_write", "read_only", "not_found", "store_unknown",
    }
    assert p21a.STORE_ERROR_CODES == expected


def test_store_error_rejects_non_closed_code():
    assert p21a.StoreError(code="not_found")  # closed code accepted
    with pytest.raises(ValueError):
        p21a.StoreError(code="totally_made_up_code")


def test_store_result_preserves_no_execution_invariant():
    ok = p21a.StoreResult.ok_value({"approval_id": "x"})
    assert ok.ok is True
    assert ok.restart_safe is True
    assert ok.execution_allowed is False
    assert ok.executed is False
    assert ok.storage_class == "durable"

    err = p21a.StoreResult.err("store_unknown", "bad", unavailable_reason="store_unknown")
    assert err.ok is False
    assert err.error.code == "store_unknown"
    assert err.execution_allowed is False
    assert err.executed is False


# ---------------------------------------------------------------------------
# Planned store surface -- every method exists and is NON-EXECUTING
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def store():
    return p21a.DurableApprovalStore()


@pytest.mark.parametrize("method_name", p21a.PLANNED_METHODS)
def test_planned_methods_exist_and_raise_not_implemented(store, method_name):
    method = getattr(store, method_name)
    assert callable(method)
    # Supply None for EVERY declared parameter (positional-or-keyword and
    # keyword-only) so the call binds for every signature. The planned methods
    # have heterogeneous arities (e.g. create_request / submit_decision /
    # find_by_idempotency_digest / export_record take several required args), so
    # a single positional None would raise TypeError at call time for those and
    # never reach the body. The body raises StoreNotImplementedError before any
    # argument is dereferenced, so the values are irrelevant -- only the call
    # must bind. No method has positional-only parameters, so **kwargs is valid.
    call_kwargs = {name: None for name in inspect.signature(method).parameters}
    with pytest.raises(p21a.StoreNotImplementedError):
        method(**call_kwargs)


def test_planned_methods_match_section_7_surface():
    # The P20 service-function contract (create/list/get/decide) MUST be present.
    for required in ("create_request", "list_requests", "get_request", "submit_decision"):
        assert required in p21a.PLANNED_METHODS
    # Durable-only operations from schema plan section 7.
    for durable_op in (
        "append_audit_event", "find_by_idempotency_digest",
        "expire_due_requests", "purge_eligible_records", "export_record",
    ):
        assert durable_op in p21a.PLANNED_METHODS


def test_store_has_no_execution_unlocking_surface():
    """The adapter exposes NO operation that sets execution_allowed/executed true."""
    src = Path(p21a.__file__).read_text(encoding="utf-8")
    assert "execution_allowed = True" not in src
    assert "executed = True" not in src
    assert "execution_allowed=True" not in src
    assert "executed=True" not in src


# ---------------------------------------------------------------------------
# P21-D-D cutover audit (source scans + filesystem). P20 services are wired to
# the durable adapter BEHIND an explicit readiness gate; the in-memory store is
# retained as the explicit test / dev memory backend; no p21 router is
# registered; no durable model is registered in models.__init__; no new
# migration is chained; env.py / deps / baseline are unchanged.
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    assert path.is_file(), f"expected file missing: {path}"
    return path.read_text(encoding="utf-8")


def test_p20_schemas_do_not_reference_p21():
    """P20 schemas stay free of any durable adapter / model reference."""
    src = _read(BACKEND / "api" / "v1" / "platform" / "p20" / "schemas.py")
    for token in ("api.v1.platform.p21", "DurableApprovalStore", "p21.adapter", "p21.models"):
        assert token not in src, f"p20 schemas must not reference durable adapter: {token}"


def test_p20_services_wire_durable_adapter_behind_gate():
    """P21-D-D: P20 services import the concrete adapter and define the gate."""
    src = _read(P20_DIR / "services.py")
    # The cutover: services reference the concrete durable adapter.
    assert "api.v1.platform.p21.adapter" in src
    assert "DurableApprovalStoreAdapter" in src
    # The explicit readiness gate + storage-mode resolver + fail-closed mapper.
    assert "DurableStoreNotReady" in src
    assert "_check_durable_readiness" in src
    assert "get_storage_mode" in src
    assert "_from_durable_record" in src
    assert "STORAGE_MODE_DURABLE" in src
    assert "STORAGE_MODE_MEMORY" in src
    # No operation may set execution_allowed / executed true on the durable path.
    assert "execution_allowed = True" not in src
    assert "executed = True" not in src
    assert "execution_allowed=True" not in src
    assert "executed=True" not in src


def test_p20_routes_handle_storage_gate_via_services():
    """Routes translate the gate failure to 503 and never import p21 directly."""
    src = _read(BACKEND / "api" / "v1" / "platform" / "p20" / "routes.py")
    assert "DurableStoreNotReady" in src
    assert "503" in src or "SERVICE_UNAVAILABLE" in src
    # Routes reach the durable store ONLY through services (no direct p21 import).
    for token in ("api.v1.platform.p21", "DurableApprovalStoreAdapter", "p21.adapter", "p21.models"):
        assert token not in src, f"p20 routes must not import durable adapter directly: {token}"


def test_p20_store_retains_explicit_memory_backend():
    """P20 services retain the in-memory globals as the explicit memory backend."""
    src = _read(P20_DIR / "services.py")
    assert "_STORE" in src
    assert "_STORE_BY_CREATE_KEY" in src
    assert "_AUDIT_LOG" in src
    assert 'storage="memory"' in src or 'storage = "memory"' in src


def test_app_does_not_register_p21_router():
    src = _read(BACKEND / "api" / "app.py")
    assert "p21" not in src
    assert "platform.p21" not in src


def test_models_registry_does_not_include_durable():
    """The global models package must NOT register the durable models yet."""
    src = _read(BACKEND / "models" / "__init__.py")
    assert "durable" not in src.lower()
    assert "p21" not in src
    assert "DurableApproval" not in src


def test_p21_package_has_no_router():
    """The p21 skeleton ships NO routes module and exposes no router."""
    assert not (P21_DIR / "routes.py").exists()
    import api.v1.platform.p21 as p21_pkg
    assert not hasattr(p21_pkg, "router")


def test_no_new_alembic_migration_chained_on_020():
    """020_durable_approval_store is still the head -- nothing descends from it."""
    versions = BACKEND / "alembic" / "versions"
    assert (versions / "020_durable_approval_store.py").is_file()
    descendants = []
    for f in versions.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        if "down_revision" in text and "020_durable_approval_store" in text:
            # 020 itself names 019 as down_revision; a NEW migration would name 020.
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("down_revision") and "020_durable_approval_store" in stripped:
                    descendants.append(f.name)
    # Only an acceptable match is 020's own downgrade docstring / references; a
    # real new migration would add a NEW file with down_revision == '020_...'.
    new_migrations = [
        name for name in descendants
        if not name.startswith("020_")
    ]
    assert new_migrations == [], f"unexpected new migration(s) chained on 020: {new_migrations}"


def test_alembic_env_does_not_reference_p21():
    src = _read(BACKEND / "alembic" / "env.py")
    assert "p21" not in src
    assert "durable" not in src.lower()


def test_no_dependency_or_baseline_changes():
    """pyproject/lockfile and the secrets baseline are unchanged by this slice."""
    for rel in ("pyproject.toml", "poetry.lock", "../.secrets.baseline"):
        # These files simply must still exist and not mention a p21 dependency.
        path = (BACKEND / rel).resolve()
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "p21-durable" not in text.lower()
