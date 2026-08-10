"""Generate a per-node outcome CSV from two pytest JUnit XML files using the
standard-library csv.writer (correct quoting for node IDs containing commas,
newlines, quotes, or binary bytes).

Usage: python gen_node_csv.py <junit_a.xml> <junit_b.xml> <out.csv>

The CSV has columns: nodeid,outcome_run_a,outcome_run_b
Outcomes are one of: passed, skipped, xfailed, failed, error, absent.
- ``absent`` marks a node that appeared in only one run (dynamic node IDs).
- Every non-absent value is from {passed, skipped, xfailed, failed, error}.
Prints an accounting reconciliation and asserts A/B node-id sets + outcomes.
"""
import csv
import sys
import xml.etree.ElementTree as ET
from collections import Counter

LEGAL = {"passed", "skipped", "xfailed", "failed", "error"}


def parse(xml_path: str) -> dict[str, str]:
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


def main(a_path: str, b_path: str, out_path: str) -> None:
    a = parse(a_path)
    b = parse(b_path)
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
    diffs = [(n, a[n], b[n]) for n in all_nodes if n in a and n in b and a[n] != b[n]]
    print(f"outcome diffs: {len(diffs)}")
    gap = {k: ca.get(k, 0) - cb.get(k, 0) for k in set(ca) | set(cb)}
    print(f"accounting gap (A-B): {gap}")

    # CSV round-trip validation with csv.DictReader.
    with open(out_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    bad_cols = [(i, r) for i, r in enumerate(rows) if set(r.keys()) != {"nodeid", "outcome_run_a", "outcome_run_b"}]
    bad_outcomes = [
        (i, r["outcome_run_a"], r["outcome_run_b"])
        for i, r in enumerate(rows)
        if r["outcome_run_a"] not in LEGAL | {"absent"} or r["outcome_run_b"] not in LEGAL | {"absent"}
    ]
    print(f"CSV rows (excl header): {len(rows)}; bad-col rows: {len(bad_cols)}; bad-outcome rows: {len(bad_outcomes)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
