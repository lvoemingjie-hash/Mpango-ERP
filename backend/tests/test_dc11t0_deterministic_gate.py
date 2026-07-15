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


def test_compare_summaries_ignores_volatile_passed_node_ids_with_equal_totals():
    left = _summary()
    right = _summary(
        normalized_node_ledger_sha256="all-node-ledger-b",
    )

    result = gate.compare_summaries(left, right)

    assert result["match"] is True
    assert result["mismatches"] == []
    assert (
        result["left_failed_error_ledger_sha256"]
        == result["right_failed_error_ledger_sha256"]
    )
    assert "normalized_node_ledger_sha256 differs" in result["diagnostic_mismatches"]


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
    assert "failed node set differs" in result["mismatches"]
    assert "failed_error_ledger_sha256 differs" in result["mismatches"]
    assert (
        result["left_failed_error_ledger_sha256"]
        != result["right_failed_error_ledger_sha256"]
    )


def test_compare_summaries_fails_on_error_node_id_drift():
    left = _summary()
    right = _summary(
        error_nodes=["tests/test_exports.py::test_different_error"],
    )

    result = gate.compare_summaries(left, right)

    assert result["match"] is False
    assert "error node set differs" in result["mismatches"]
    assert "failed_error_ledger_sha256 differs" in result["mismatches"]


def test_compare_summaries_fails_on_status_total_drift():
    left = _summary()
    right = _summary(
        passed=4,
        failed=1,
        failed_nodes=["tests/test_payments.py::test_replay_rejected"],
    )

    result = gate.compare_summaries(left, right)

    assert result["match"] is False
    assert "passed: 3 != 4" in result["mismatches"]
    assert "failed: 2 != 1" in result["mismatches"]
    assert "failed node set differs" in result["mismatches"]


def test_failed_error_ledger_hash_is_order_independent():
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

    assert gate.failed_error_ledger_sha256(left) == gate.failed_error_ledger_sha256(right)
