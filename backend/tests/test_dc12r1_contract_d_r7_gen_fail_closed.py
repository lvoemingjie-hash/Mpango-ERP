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


# -- R1-R1-R8: post-temp round-trip validation failures ---------------------
# These inject a failure AFTER the temp file is created (the R7 defect leaked
# the temp file here). They call the generator's main() directly (not as a
# subprocess) and monkeypatch the csv round-trip readers to return bad data.


def _load_gen_module():
    """Import the generator as a module so its main() is callable directly
    (lets us monkeypatch csv.reader/csv.DictReader on the module's view)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_gen_r8", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_valid_pair(a_path: str, b_path: str) -> None:
    """Two simple passed testcases — legal, so the failure is injected only
    by the monkeypatched round-trip reader."""
    _write_xml(a_path, [_tc("tests.test_x.TestA", "test_one")])
    _write_xml(b_path, [_tc("tests.test_x.TestA", "test_one")])


def test_round_trip_non3col_failure_cleans_temp_and_preserves_target(tmp_path, monkeypatch):
    """R1-R1-R8: inject a round-trip non-3-column failure AFTER temp creation.
    Assert nonzero result, target byte-unchanged, and zero surviving temp
    files in the target directory."""
    import csv as _csv

    mod = _load_gen_module()
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    out = tmp_path / "out.csv"
    out.write_text("PRE-EXISTING\n", encoding="utf-8")
    before = out.read_bytes()
    _write_valid_pair(str(a), str(b))

    # Monkeypatch csv.reader on the generator module's csv to return a 4-col
    # row (simulating a corrupt round-trip read).
    real_reader = mod.csv.reader

    def _bad_reader(f, *a_, **kw):
        rows = list(real_reader(f, *a_, **kw))
        # Corrupt one row to 4 columns.
        if rows:
            rows[0] = rows[0] + ["extra"]
        return iter(rows)

    monkeypatch.setattr(mod.csv, "reader", _bad_reader)

    rc = mod.main(str(a), str(b), str(out))
    assert rc != 0, f"expected nonzero exit on non-3-col round-trip, got {rc}"
    assert out.read_bytes() == before, "existing target must be byte-unchanged"
    # Zero surviving task-owned temp files.
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".gen_node_csv_")]
    assert leftovers == [], f"temp file survived: {leftovers}"


def test_round_trip_illegal_outcome_failure_cleans_temp_and_preserves_target(tmp_path, monkeypatch):
    """R1-R1-R8: inject a round-trip illegal-outcome failure AFTER temp
    creation (after the column check passes). Assert nonzero result, target
    byte-unchanged, and zero surviving temp files."""
    import csv as _csv

    mod = _load_gen_module()
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    out = tmp_path / "out.csv"
    out.write_text("PRE-EXISTING\n", encoding="utf-8")
    before = out.read_bytes()
    _write_valid_pair(str(a), str(b))

    # Monkeypatch csv.DictReader to return an illegal outcome. The column
    # check (csv.reader) must still pass (3 cols) so the outcome check runs.
    real_reader = mod.csv.reader
    real_dictreader = mod.csv.DictReader

    class _BadDictReader:
        def __init__(self, f, *a_, **kw):
            self._real = real_dictreader(f, *a_, **kw)

        def __iter__(self):
            return self

        def __next__(self):
            row = next(self._real)
            # Inject an illegal outcome value.
            if "outcome_run_a" in row:
                row["outcome_run_a"] = "bogus"
            return row

    monkeypatch.setattr(mod.csv, "DictReader", _BadDictReader)

    rc = mod.main(str(a), str(b), str(out))
    assert rc != 0, f"expected nonzero exit on illegal-outcome round-trip, got {rc}"
    assert out.read_bytes() == before, "existing target must be byte-unchanged"
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".gen_node_csv_")]
    assert leftovers == [], f"temp file survived: {leftovers}"


def test_round_trip_failure_when_target_absent_leaves_no_target_no_temp(tmp_path, monkeypatch):
    """R1-R1-R8: a post-temp failure when the target does NOT exist must
    leave the target absent AND zero surviving temp files."""
    mod = _load_gen_module()
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    out = tmp_path / "out.csv"
    _write_valid_pair(str(a), str(b))

    real_reader = mod.csv.reader

    def _bad_reader(f, *a_, **kw):
        rows = list(real_reader(f, *a_, **kw))
        if rows:
            rows[0] = rows[0] + ["extra"]
        return iter(rows)

    monkeypatch.setattr(mod.csv, "reader", _bad_reader)

    rc = mod.main(str(a), str(b), str(out))
    assert rc != 0
    assert not out.exists(), "target must not be created on failure"
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".gen_node_csv_")]
    assert leftovers == [], f"temp file survived: {leftovers}"
