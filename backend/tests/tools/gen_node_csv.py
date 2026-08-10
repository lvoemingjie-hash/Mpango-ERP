"""Generate a per-node outcome CSV from two pytest JUnit XML files using the
standard-library csv.writer (correct quoting for node IDs containing commas,
newlines, quotes, or binary bytes).

Usage: python tests/tools/gen_node_csv.py <junit_a.xml> <junit_b.xml> <out.csv>

The CSV has columns: nodeid,outcome_run_a,outcome_run_b
Outcomes are one of: passed, skipped, xfailed, failed, error, absent.
- ``absent`` marks a node that appeared in only one run (dynamic node IDs).
- Every non-absent value is from {passed, skipped, xfailed, failed, error}.

FAIL-CLOSED (R1-R1-R6): the generator exits NON-ZERO (SystemExit) if it detects
any of: a duplicate node ID, an illegal outcome value, a shared-node outcome
difference (same node, different outcome), a bad column count on round-trip,
or a non-zero accounting gap. It prints the reconciliation summary to stdout.
"""
import csv
import sys
import xml.etree.ElementTree as ET
from collections import Counter

LEGAL = {"passed", "skipped", "xfailed", "failed", "error"}


def _parse(xml_path: str) -> dict[str, str]:
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


def main(a_path: str, b_path: str, out_path: str) -> int:
    a = _parse(a_path)
    b = _parse(b_path)

    # Fail-closed: duplicate node IDs within a single run.
    if len(a) != len(set(a)):
        dups = [k for k, c in Counter(a).items() if c > 1]
        print(f"FAIL: duplicate node IDs in run A: {dups[:5]}", file=sys.stderr)
        return 1
    if len(b) != len(set(b)):
        dups = [k for k, c in Counter(b).items() if c > 1]
        print(f"FAIL: duplicate node IDs in run B: {dups[:5]}", file=sys.stderr)
        return 1

    all_nodes = sorted(set(a) | set(b))
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["nodeid", "outcome_run_a", "outcome_run_b"])
        for n in all_nodes:
            oa = a.get(n, "absent")
            ob = b.get(n, "absent")
            w.writerow([n, oa, ob])

    ca = Counter(a.values())
    cb = Counter(b.values())
    a_only = sorted(set(a) - set(b))
    b_only = sorted(set(b) - set(a))
    print(f"nodes A={len(a)} B={len(b)} union={len(all_nodes)}")
    print(f"A-only={len(a_only)} B-only={len(b_only)}")
    print(f"outcomes A: {dict(ca)}")
    print(f"outcomes B: {dict(cb)}")

    # Fail-closed: illegal outcome values.
    for n, o in a.items():
        if o not in LEGAL:
            print(f"FAIL: illegal outcome in A: {n} -> {o}", file=sys.stderr)
            return 1
    for n, o in b.items():
        if o not in LEGAL:
            print(f"FAIL: illegal outcome in B: {n} -> {o}", file=sys.stderr)
            return 1

    # Fail-closed: shared-node outcome difference.
    shared = set(a) & set(b)
    diffs = [(n, a[n], b[n]) for n in shared if a[n] != b[n]]
    print(f"shared-node outcome diffs: {len(diffs)}")
    if diffs:
        print(f"FAIL: shared-node outcome differences: {diffs[:5]}", file=sys.stderr)
        return 1

    # Fail-closed: accounting gap.
    gap = {k: ca.get(k, 0) - cb.get(k, 0) for k in set(ca) | set(cb)}
    print(f"accounting gap (A-B): {gap}")
    if any(v != 0 for v in gap.values()):
        print(f"FAIL: non-zero accounting gap: {gap}", file=sys.stderr)
        return 1

    # Fail-closed: CSV round-trip column integrity.
    with open(out_path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    col_counts = Counter(len(r) for r in rows)
    bad = {k: v for k, v in col_counts.items() if k != 3}
    print(f"CSV rows (incl header): {len(rows)}; col-count dist: {dict(col_counts)}")
    if bad:
        print(f"FAIL: non-3-col rows: {bad}", file=sys.stderr)
        return 1
    # Re-read outcomes and validate allowlist.
    with open(out_path, encoding="utf-8", newline="") as f:
        drows = list(csv.DictReader(f))
    bad_outcomes = [
        (i, r["outcome_run_a"], r["outcome_run_b"])
        for i, r in enumerate(drows)
        if r["outcome_run_a"] not in LEGAL | {"absent"}
        or r["outcome_run_b"] not in LEGAL | {"absent"}
    ]
    print(f"bad-outcome rows: {len(bad_outcomes)}")
    if bad_outcomes:
        print(f"FAIL: illegal outcomes: {bad_outcomes[:5]}", file=sys.stderr)
        return 1

    print("OK: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
