"""R1-R1-R5 — machine-verifiable node-outcomes CSV validity.

Pure file-parsing tests (no DB, no async fixtures). Kept in a separate module
so the Contract D suite's module-level ``pytest.mark.asyncio`` does not pull
an event loop / DB fixture into these synchronous checks.
"""
from __future__ import annotations

import csv
import os
from collections import Counter

_CSV = (
    "ai-ledger/product-ai/"
    "2026-08-10_dc12r1_s3_s2b_i2c_i2b_r4_node_outcomes.csv"
)
_LEGAL = {"passed", "skipped", "xfailed", "failed", "error", "absent"}


def _rows():
    # __file__ = backend/tests/test_dc12r1_contract_d_r5_node_csv.py
    # repo_root = two dirnames up from backend/ → the worktree root.
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(tests_dir)
    repo_root = os.path.dirname(backend_dir)
    path = os.path.join(repo_root, _CSV)
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_every_row_has_exactly_three_columns():
    rows = _rows()
    assert rows, "CSV is empty"
    expected_cols = {"nodeid", "outcome_run_a", "outcome_run_b"}
    for i, r in enumerate(rows):
        assert set(r.keys()) == expected_cols, (
            f"row {i} has columns {set(r.keys())}, expected {expected_cols}"
        )


def test_outcomes_are_in_allowlist():
    for i, r in enumerate(_rows()):
        assert r["outcome_run_a"] in _LEGAL, (i, r["outcome_run_a"])
        assert r["outcome_run_b"] in _LEGAL, (i, r["outcome_run_b"])


def test_union_rows_per_run_counts_and_accounting_gap():
    rows = _rows()
    union = len(rows)
    a_nonabsent = sum(1 for r in rows if r["outcome_run_a"] != "absent")
    b_nonabsent = sum(1 for r in rows if r["outcome_run_b"] != "absent")
    a_only = sum(1 for r in rows if r["outcome_run_a"] != "absent" and r["outcome_run_b"] == "absent")
    b_only = sum(1 for r in rows if r["outcome_run_b"] != "absent" and r["outcome_run_a"] == "absent")
    assert union == 3345, f"union rows = {union}"
    assert a_nonabsent == 3341, f"A non-absent = {a_nonabsent}"
    assert b_nonabsent == 3341, f"B non-absent = {b_nonabsent}"
    assert a_only == 4, f"A-only = {a_only}"
    assert b_only == 4, f"B-only = {b_only}"
    ca = Counter(r["outcome_run_a"] for r in rows if r["outcome_run_a"] != "absent")
    cb = Counter(r["outcome_run_b"] for r in rows if r["outcome_run_b"] != "absent")
    assert ca == {"passed": 3278, "skipped": 48, "xfailed": 15}, dict(ca)
    assert cb == {"passed": 3278, "skipped": 48, "xfailed": 15}, dict(cb)
    for k in set(ca) | set(cb):
        assert ca.get(k, 0) == cb.get(k, 0), (k, ca.get(k), cb.get(k))


def test_no_outcome_diff_between_runs():
    rows = _rows()
    diffs = [
        (r["nodeid"], r["outcome_run_a"], r["outcome_run_b"])
        for r in rows
        if r["outcome_run_a"] != "absent"
        and r["outcome_run_b"] != "absent"
        and r["outcome_run_a"] != r["outcome_run_b"]
    ]
    assert diffs == [], f"outcome diffs: {diffs[:5]}"


def test_csv_round_trips_with_stdlib_reader():
    """The exact CTO check: csv.reader on every line yields exactly 3 fields."""
    tests_dir = os.path.dirname(os.path.abspath(__file__)); backend_dir = os.path.dirname(tests_dir); repo_root = os.path.dirname(backend_dir)
    path = os.path.join(repo_root, _CSV)
    with open(path, encoding="utf-8", newline="") as f:
        raw_rows = list(csv.reader(f))
    from collections import Counter
    col_counts = Counter(len(r) for r in raw_rows)
    assert set(col_counts) == {3}, f"non-3-col rows present: {dict(col_counts)}"
    assert len(raw_rows) == 3346, len(raw_rows)  # 1 header + 3345 data
