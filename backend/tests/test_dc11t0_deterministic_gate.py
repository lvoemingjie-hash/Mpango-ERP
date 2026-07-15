from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_gate_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dc11t0_deterministic_gate.py"
    spec = importlib.util.spec_from_file_location("dc11t0_deterministic_gate", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate_module()


def _summary(**overrides):
    base = {
        "collected": 6,
        "passed": 3,
        "failed": 2,
        "errors": 1,
        "skipped": 0,
        "xfailed": 0,
        "accounting_gap": 0,
        "failed_nodes": [
            "tests/test_payments.py::test_replay_rejected",
            "tests/test_orders.py::test_cross_tenant_blocked",
        ],
        "error_nodes": [
            "tests/test_exports.py::test_worker_context",
        ],
        "normalized_node_ledger_sha256": "all-node-ledger-a",
    }
    base.update(overrides)
    return base


def test_compare_summaries_ignores_passed_node_diagnostics():
    left = _summary()
    right = _summary(
        collected=8,
        passed=5,
        normalized_node_ledger_sha256="all-node-ledger-b",
    )

    result = gate.compare_summaries(left, right)

    assert result["match"] is True
    assert result["mismatches"] == []
    assert result["left_failure_ledger_sha256"] == result["right_failure_ledger_sha256"]
    assert "normalized_node_ledger_sha256 differs" in result["diagnostic_mismatches"]
    assert "collected: 6 != 8" in result["diagnostic_mismatches"]
    assert "passed: 3 != 5" in result["diagnostic_mismatches"]


def test_compare_summaries_fails_on_failed_node_id_drift():
    left = _summary()
    right = _summary(
        failed_nodes=[
            "tests/test_payments.py::test_replay_rejected",
            "tests/test_orders.py::test_different_failure",
        ],
    )

    result = gate.compare_summaries(left, right)

    assert result["match"] is False
    assert result["mismatches"] == ["failure_ledger_sha256 differs"]
    assert result["left_failure_ledger_sha256"] != result["right_failure_ledger_sha256"]


def test_compare_summaries_fails_when_error_and_failure_status_swap():
    left = _summary(
        failed_nodes=["tests/test_platform.py::test_boundary"],
        error_nodes=[],
    )
    right = _summary(
        failed_nodes=[],
        error_nodes=["tests/test_platform.py::test_boundary"],
    )

    result = gate.compare_summaries(left, right)

    assert result["match"] is False
    assert result["mismatches"] == ["failure_ledger_sha256 differs"]


def test_failure_ledger_hash_is_order_independent():
    left = _summary(
        failed_nodes=[
            "tests/test_b.py::test_two",
            "tests/test_a.py::test_one",
        ],
        error_nodes=[
            "tests/test_c.py::test_three",
        ],
    )
    right = _summary(
        failed_nodes=[
            "tests/test_a.py::test_one",
            "tests/test_b.py::test_two",
        ],
        error_nodes=[
            "tests/test_c.py::test_three",
        ],
    )

    assert gate.failure_ledger_sha256(left) == gate.failure_ledger_sha256(right)
