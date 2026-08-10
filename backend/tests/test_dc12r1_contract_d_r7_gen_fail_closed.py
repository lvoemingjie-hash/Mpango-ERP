"""R1-R1-R7 — generator fail-closed + atomic-publish unit tests.

Pure unit tests (no DB) for ``tests/tools/gen_node_csv.py``. Three minimal
fixtures cover the CTO requirements:

  * duplicate XML  -> exit 1, NO output file produced;
  * shared-outcome-diff XML -> exit 1, NO output file produced (and an
    existing target is left byte-unchanged);
  * legal dynamic A-only/B-only XML -> exit 0, output file published.

These run the generator as a subprocess to exercise its real exit code and
file-publish behavior.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

_GEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "gen_node_csv.py")

# Minimal valid JUnit XML skeleton.
_XML_HEAD = '<?xml version="1.0" encoding="utf-8"?>\n<testsuite name="s" tests="{n}">\n'
_XML_TAIL = "</testsuite>\n"


def _tc(classname: str, name: str, *, skipped: bool = False, xfail: bool = False) -> str:
    if xfail:
        return f'  <testcase classname="{classname}" name="{name}"><skipped type="xfail" message="xfailed"/></testcase>\n'
    if skipped:
        return f'  <testcase classname="{classname}" name="{name}"><skipped/></testcase>\n'
    return f'  <testcase classname="{classname}" name="{name}"/>\n'


def _write_xml(path: str, cases: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(_XML_HEAD.format(n=len(cases)))
        for c in cases:
            f.write(c)
        f.write(_XML_TAIL)


def _run_gen(a: str, b: str, out: str) -> int:
    """Run the generator as a subprocess; return its exit code."""
    return subprocess.call(
        [sys.executable, _GEN, a, b, out],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_duplicate_node_id_fails_and_produces_no_output(tmp_path):
    """Two identical testcase entries -> exit 1 and NO output file."""
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    out = tmp_path / "out.csv"
    cases = [
        _tc("tests.test_x.TestA", "test_one"),
        _tc("tests.test_x.TestA", "test_one"),  # duplicate
    ]
    _write_xml(str(a), cases)
    _write_xml(str(b), [_tc("tests.test_x.TestA", "test_one")])
    rc = _run_gen(str(a), str(b), str(out))
    assert rc != 0, f"expected non-zero exit on duplicate, got {rc}"
    assert not out.exists(), "output file must NOT be produced on duplicate failure"


def test_shared_outcome_diff_fails_and_leaves_existing_target_unchanged(tmp_path):
    """Same node, different outcome -> exit 1. An EXISTING target file must be
    left byte-for-byte unchanged (atomic publish: no partial write)."""
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    out = tmp_path / "out.csv"
    # Pre-create a target with known content.
    out.write_text("PRE-EXISTING-CONTENT\n", encoding="utf-8")
    before = out.read_bytes()
    _write_xml(str(a), [_tc("tests.test_x.TestA", "test_one")])  # passed
    _write_xml(str(b), [_tc("tests.test_x.TestA", "test_one", skipped=True)])  # skipped
    rc = _run_gen(str(a), str(b), str(out))
    assert rc != 0, f"expected non-zero exit on outcome diff, got {rc}"
    assert out.read_bytes() == before, "existing target must be byte-unchanged on failure"


def test_shared_outcome_diff_fails_and_produces_no_output_when_target_absent(tmp_path):
    """Outcome diff, target does NOT exist beforehand -> exit 1 and target
    must NOT be created."""
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    out = tmp_path / "out.csv"
    _write_xml(str(a), [_tc("tests.test_x.TestA", "test_one")])
    _write_xml(str(b), [_tc("tests.test_x.TestA", "test_one", xfail=True)])
    rc = _run_gen(str(a), str(b), str(out))
    assert rc != 0
    assert not out.exists(), "target must not be created on failure"


def test_legal_dynamic_a_only_b_only_publishes_exit0(tmp_path):
    """Legal: A has one node, B has a DIFFERENT node (dynamic A-only/B-only).
    -> exit 0, output published, round-trips as 3-column, absent markers
    present."""
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    out = tmp_path / "out.csv"
    _write_xml(str(a), [_tc("tests.test_x.TestA", "test_only_in_a")])
    _write_xml(str(b), [_tc("tests.test_x.TestA", "test_only_in_b")])
    rc = _run_gen(str(a), str(b), str(out))
    assert rc == 0, f"expected exit 0 on legal dynamic, got {rc}"
    assert out.exists(), "output must be published on success"
    import csv
    with open(out, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    by_node = {r["nodeid"]: r for r in rows}
    a_node = "tests/test_x.py::TestA::test_only_in_a"
    b_node = "tests/test_x.py::TestA::test_only_in_b"
    assert by_node[a_node]["outcome_run_a"] == "passed"
    assert by_node[a_node]["outcome_run_b"] == "absent"
    assert by_node[b_node]["outcome_run_a"] == "absent"
    assert by_node[b_node]["outcome_run_b"] == "passed"
