"""Generate a per-node outcome CSV from two pytest JUnit XML files using the
standard-library csv.writer (correct quoting for node IDs containing commas,
newlines, quotes, or binary bytes).

Usage: python tests/tools/gen_node_csv.py <junit_a.xml> <junit_b.xml> <out.csv>

The CSV has columns: nodeid,outcome_run_a,outcome_run_b
Outcomes are one of: passed, skipped, xfailed, failed, error, absent.
- ``absent`` marks a node that appeared in only one run (dynamic node IDs).
- Every non-absent value is from {passed, skipped, xfailed, failed, error}.

FAIL-CLOSED (R1-R1-R7): the generator exits NON-ZERO (SystemExit) if it detects
any of: a duplicate node ID (checked at PARSE time, before any dict overwrite),
an illegal outcome value, a shared-node outcome difference (same node, different
outcome), a bad column count on round-trip, or a non-zero accounting gap.

ATOMIC PUBLISH (R1-R1-R7): all validation runs BEFORE the target CSV is
touched. The CSV is written to a task-owned temp file, round-trip-validated,
and only then atomically published via ``os.replace()``. On any failure the
temp file is removed and the target file is left byte-unchanged (or, if it did
not previously exist, left non-existent).
"""
import csv
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter

LEGAL = {"passed", "skipped", "xfailed", "failed", "error"}


def _parse(xml_path: str) -> dict[str, str]:
    """Parse a JUnit XML into a nodeid -> outcome dict.

    R1-R1-R7: duplicate node IDs are detected at INSERT time (before any dict
    overwrite) and raise immediately — a later len() comparison would always
    be equal because dict keys are unique."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    outcomes: dict[str, str] = {}
    for tc in root.iter("testcase"):
        cls = tc.get("classname") or ""
        name = tc.get("name") or ""
        parts = cls.split(".")
        module_parts: list[str] = []
        class_parts: list[str] = []
        split_done = False
        for p in parts:
            if not split_done and p.startswith("Test"):
                split_done = True
            if split_done:
                class_parts.append(p)
            else:
                module_parts.append(p)
        module_path = "/".join(module_parts) + ".py"
        class_seg = ".".join(class_parts)
        nodeid = f"{module_path}::{class_seg}::{name}" if class_seg else f"{module_path}::{name}"
        # Duplicate detection at parse time (R1-R1-R7) — before insertion.
        if nodeid in outcomes:
            raise ValueError(f"duplicate node ID in {xml_path}: {nodeid}")
        children = {c.tag for c in tc}
        if "failure" in children:
            outcome = "failed"
        elif "error" in children:
            outcome = "error"
        elif "skipped" in children:
            skip_el = tc.find("skipped")
            stype = skip_el.get("type") or "" if skip_el is not None else ""
            msg = skip_el.get("message") or "" if skip_el is not None else ""
            if "xfail" in stype or "expected failure" in msg.lower() or "xfailed" in msg.lower():
                outcome = "xfailed"
            else:
                outcome = "skipped"
        else:
            outcome = "passed"
        outcomes[nodeid] = outcome
    return outcomes


def _build_rows(a: dict[str, str], b: dict[str, str]) -> list[list[str]]:
    """Build the CSV data rows (without header) from the two outcome dicts.
    Pure — no file I/O — so it can be fully validated before publishing."""
    all_nodes = sorted(set(a) | set(b))
    rows: list[list[str]] = []
    for n in all_nodes:
        rows.append([n, a.get(n, "absent"), b.get(n, "absent")])
    return rows


def _validate(a: dict[str, str], b: dict[str, str]) -> int:
    """Run all A/B validations. Returns 0 on success, non-zero on failure
    (with a diagnostic printed to stderr). Pure — no file I/O."""
    ca = Counter(a.values())
    cb = Counter(b.values())

    # Illegal outcome values.
    for label, d in (("A", a), ("B", b)):
        for n, o in d.items():
            if o not in LEGAL:
                print(f"FAIL: illegal outcome in {label}: {n} -> {o}", file=sys.stderr)
                return 1

    # Shared-node outcome difference.
    shared = set(a) & set(b)
    diffs = [(n, a[n], b[n]) for n in shared if a[n] != b[n]]
    print(f"shared-node outcome diffs: {len(diffs)}")
    if diffs:
        print(f"FAIL: shared-node outcome differences: {diffs[:5]}", file=sys.stderr)
        return 1

    # Accounting gap.
    gap = {k: ca.get(k, 0) - cb.get(k, 0) for k in set(ca) | set(cb)}
    print(f"accounting gap (A-B): {gap}")
    if any(v != 0 for v in gap.values()):
        print(f"FAIL: non-zero accounting gap: {gap}", file=sys.stderr)
        return 1

    return 0


def main(a_path: str, b_path: str, out_path: str) -> int:
    # Parse (duplicate detection happens here, at parse time).
    try:
        a = _parse(a_path)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    try:
        b = _parse(b_path)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    ca = Counter(a.values())
    cb = Counter(b.values())
    a_only = sorted(set(a) - set(b))
    b_only = sorted(set(b) - set(a))
    print(f"nodes A={len(a)} B={len(b)} union={len(set(a) | set(b))}")
    print(f"A-only={len(a_only)} B-only={len(b_only)}")
    print(f"outcomes A: {dict(ca)}")
    print(f"outcomes B: {dict(cb)}")

    # All A/B validation BEFORE touching the target CSV (R1-R1-R7).
    rc = _validate(a, b)
    if rc != 0:
        return rc

    rows = _build_rows(a, b)

    # Write to a task-owned temp file in the SAME directory as the target (so
    # os.replace is atomic on the same filesystem), round-trip-validate, then
    # atomically publish. On any failure the temp file is removed and the
    # target is left byte-unchanged (or non-existent).
    target_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".gen_node_csv_", suffix=".tmp", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["nodeid", "outcome_run_a", "outcome_run_b"])
            for r in rows:
                w.writerow(r)

        # Round-trip validation on the temp file.
        with open(tmp_path, encoding="utf-8", newline="") as f:
            raw_rows = list(csv.reader(f))
        col_counts = Counter(len(r) for r in raw_rows)
        bad = {k: v for k, v in col_counts.items() if k != 3}
        print(f"CSV rows (incl header): {len(raw_rows)}; col-count dist: {dict(col_counts)}")
        if bad:
            print(f"FAIL: non-3-col rows: {bad}", file=sys.stderr)
            return 1
        with open(tmp_path, encoding="utf-8", newline="") as f:
            drows = list(csv.DictReader(f))
        bad_outcomes = [
            (i, r["outcome_run_a"], r["outcome_run_b"])
            for i, r in enumerate(drows)
            if r["outcome_run_a"] not in LEGAL | {"absent"}
            or r["outcome_run_b"] not in LEGAL | {"absent"}
        ]
        print(f"bad-outcome rows: {len(bad_outcomes)}")
        if bad_outcomes:
            print(f"FAIL: illegal outcomes in round-trip: {bad_outcomes[:5]}", file=sys.stderr)
            return 1

        # Atomic publish (R1-R1-R7).
        os.replace(tmp_path, out_path)
    except BaseException:
        # Failure: remove the temp file; target is untouched.
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
        raise

    print("OK: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
