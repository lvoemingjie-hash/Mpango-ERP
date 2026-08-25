#!/usr/bin/env python3
"""Deterministic RED mutation gate for the HE2 harness governance validator.

Every mutation tampers with a pristine copy of the real governance tree and
MUST turn the validator RED with the intended rule code. This proves the gate
is sensitive to the regressions it exists to catch (standard section 11):
a gate that stays green when its own detection logic is attacked is not
evidence. Two GREEN controls prove the harness can still pass.

Standard library only. Exit code 0 iff all mutations go RED with the expected
codes and all controls stay GREEN.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
GOV_DIR = REPO_ROOT / "harness-governance"
VALIDATOR = GOV_DIR / "validator" / "harness_governance_validator.py"

TODAY = "2026-08-25"
EXPIRED_DATE = "2026-08-24"
ACTIVE_DATE = "2026-08-26"


def _load(root, relpath):
    with open(os.path.join(root, relpath), encoding="utf-8") as fh:
        return json.load(fh)


def _save(root, relpath, doc):
    path = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _nodes(root):
    doc = _load(root, "harness-governance/inventory/inventory.json")
    return doc, doc["nodes"]


def _node(root, node_id):
    doc, nodes = _nodes(root)
    return doc, next(node for node in nodes if node["id"] == node_id)


def make_workspace():
    head = tempfile.mkdtemp(prefix="he2-mut-head-")
    baseline = tempfile.mkdtemp(prefix="he2-mut-base-")
    shutil.copytree(GOV_DIR, os.path.join(head, "harness-governance"))
    shutil.copytree(GOV_DIR, os.path.join(baseline, "harness-governance"))
    return head, baseline


def run_validator(head, baseline):
    report_path = os.path.join(head, "_mutation_report.json")
    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--root",
            head,
            "--baseline-dir",
            baseline,
            "--today",
            TODAY,
            "--report-json",
            report_path,
            "--quiet",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    report = None
    if os.path.isfile(report_path):
        with open(report_path, encoding="utf-8") as fh:
            report = json.load(fh)
        os.remove(report_path)
    return proc.returncode, report


# ---------------------------------------------------------------------------
# Mutations: each returns (head_root, baseline_root) with the tamper applied.
# ---------------------------------------------------------------------------


def mut_duplicate_node_id():
    head, base = make_workspace()
    doc, nodes = _nodes(head)
    nodes[1]["id"] = nodes[0]["id"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_blank_oracle():
    head, base = make_workspace()
    doc, nodes = _nodes(head)
    nodes[0]["ui_oracle"] = "   "
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_unknown_status():
    head, base = make_workspace()
    doc, nodes = _nodes(head)
    nodes[0]["status"] = "PASSED"
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_p0_mutation_removed():
    head, base = make_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["mutation_id"] = ""
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_blocked_owner_removed():
    head, base = make_workspace()
    doc, node = _node(head, "MOBILE-DEV-001")
    node["blocked_owner"] = ""
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_silent_node_deletion():
    head, base = make_workspace()
    doc, nodes = _nodes(head)
    doc["nodes"] = [node for node in nodes if node["id"] != "TOKEN-INV-001"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_node_reorder():
    head, base = make_workspace()
    doc, nodes = _nodes(head)
    doc["nodes"] = nodes[1:] + nodes[:1]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_expired_waiver_on_unsynced_change():
    head, base = make_workspace()
    probe = os.path.join(head, "backend", "api", "_mutation_probe.py")
    os.makedirs(os.path.dirname(probe), exist_ok=True)
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write("# governed-path change without inventory update\n")
    _save(
        head,
        "harness-governance/inventory/waivers.json",
        [
            {
                "waiver_id": "WVR-MUT-001",
                "scope": "inventory-sync",
                "reason": "expired waiver must not cover the change",
                "owner": "cto",
                "risk": "mutation proof",
                "expires": EXPIRED_DATE,
            }
        ],
    )
    return head, base


def mut_pass_without_evidence():
    head, base = make_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["status"] = "PASS"
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_pass_with_bogus_evidence():
    head, base = make_workspace()
    doc, node = _node(head, "TENANT-ISO-001")
    node["status"] = "PASS"
    node["evidence_sha"] = "deadbeef"
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


def mut_debt_owner_blank():
    head, base = make_workspace()
    doc = _load(head, "harness-governance/inventory/coverage-debt.json")
    doc["debts"][0]["owner"] = "   "
    _save(head, "harness-governance/inventory/coverage-debt.json", doc)
    return head, base


def mut_required_interaction_removed():
    head, base = make_workspace()
    doc = _load(head, "harness-governance/inventory/critical-interactions.json")
    doc["interactions"] = [
        item for item in doc["interactions"] if item.get("category") != "tenant"
    ]
    _save(head, "harness-governance/inventory/critical-interactions.json", doc)
    return head, base


def mut_blocked_node_orphaned_from_debt():
    head, base = make_workspace()
    doc = _load(head, "harness-governance/inventory/coverage-debt.json")
    for debt in doc["debts"]:
        if debt["debt_id"] == "DEBT-MOBILE-REAL-DEVICE":
            debt["node_ids"] = []
    _save(head, "harness-governance/inventory/coverage-debt.json", doc)
    return head, base


def mut_unknown_interaction_reference():
    head, base = make_workspace()
    doc, node = _node(head, "AUTH-INT-001")
    node["interaction_ids"] = ["CI-DOES-NOT-EXIST"]
    _save(head, "harness-governance/inventory/inventory.json", doc)
    return head, base


# GREEN controls -------------------------------------------------------------


def control_pristine_green():
    return make_workspace()


def control_active_waiver_covers_change():
    head, base = make_workspace()
    probe = os.path.join(head, "backend", "api", "_mutation_probe.py")
    os.makedirs(os.path.dirname(probe), exist_ok=True)
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write("# governed-path change covered by an active waiver\n")
    _save(
        head,
        "harness-governance/inventory/waivers.json",
        [
            {
                "waiver_id": "WVR-MUT-002",
                "scope": "inventory-sync",
                "reason": "active waiver must cover the change",
                "owner": "cto",
                "risk": "mutation proof",
                "expires": ACTIVE_DATE,
            }
        ],
    )
    return head, base


RED_MUTATIONS = [
    ("M01-duplicate-node-id", mut_duplicate_node_id, ["INV-DUP-ID"]),
    ("M02-blank-oracle", mut_blank_oracle, ["INV-ORACLE-EMPTY"]),
    ("M03-unknown-status", mut_unknown_status, ["SCHEMA-ENUM"]),
    ("M04-p0-mutation-removed", mut_p0_mutation_removed, ["INV-MUTATION-MISSING"]),
    ("M05-blocked-owner-removed", mut_blocked_owner_removed, ["INV-BLOCKED-OWNER"]),
    ("M06-silent-node-deletion", mut_silent_node_deletion, ["DRIFT-SILENT-DELETE"]),
    ("M07-node-reorder", mut_node_reorder, ["DRIFT-REORDER"]),
    (
        "M08-expired-waiver-on-unsynced-change",
        mut_expired_waiver_on_unsynced_change,
        ["WVR-EXPIRED", "SYNC-INVENTORY-MISSING"],
    ),
    ("M09-pass-without-evidence", mut_pass_without_evidence, ["INV-PASS-EVIDENCE"]),
    ("M10-pass-with-bogus-evidence", mut_pass_with_bogus_evidence, ["INV-PASS-EVIDENCE"]),
    ("M11-debt-owner-blank", mut_debt_owner_blank, ["DEBT-INCOMPLETE"]),
    ("M12-required-interaction-removed", mut_required_interaction_removed, ["REG-CATEGORY-MISSING"]),
    (
        "M13-blocked-node-orphaned-from-debt",
        mut_blocked_node_orphaned_from_debt,
        ["INV-BLOCKED-DEBT"],
    ),
    ("M14-unknown-interaction-reference", mut_unknown_interaction_reference, ["REG-REF-UNKNOWN"]),
]

GREEN_CONTROLS = [
    ("C01-pristine-tree-green", control_pristine_green),
    ("C02-active-waiver-covers-change", control_active_waiver_covers_change),
]


def main() -> int:
    failures = []

    print(f"HE2 RED mutation gate: {len(RED_MUTATIONS)} mutations, {len(GREEN_CONTROLS)} controls")
    print("-" * 78)

    for name, factory, expected_codes in RED_MUTATIONS:
        head, base = factory()
        try:
            code, report = run_validator(head, base)
            codes = {v["code"] for v in (report or {}).get("violations", [])}
            missing = [c for c in expected_codes if c not in codes]
            if code != 1:
                failures.append(f"{name}: validator stayed GREEN (exit {code})")
                status = "ESCAPED (green)"
            elif missing:
                failures.append(f"{name}: missing expected codes {missing}, got {sorted(codes)}")
                status = f"RED but wrong codes {sorted(codes)}"
            else:
                status = f"RED as intended ({', '.join(expected_codes)})"
            print(f"  {name:<40} {status}")
        finally:
            shutil.rmtree(head, ignore_errors=True)
            shutil.rmtree(base, ignore_errors=True)

    for name, factory in GREEN_CONTROLS:
        head, base = factory()
        try:
            code, report = run_validator(head, base)
            if code == 0:
                print(f"  {name:<40} GREEN as intended")
            else:
                violations = [v["code"] for v in (report or {}).get("violations", [])]
                failures.append(f"{name}: control went RED: {violations}")
                print(f"  {name:<40} UNEXPECTED RED {violations}")
        finally:
            shutil.rmtree(head, ignore_errors=True)
            shutil.rmtree(base, ignore_errors=True)

    print("-" * 78)
    if failures:
        print(f"FAIL: {len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        f"PASS: all {len(RED_MUTATIONS)} mutations produced the intended RED "
        f"and {len(GREEN_CONTROLS)} controls stayed GREEN"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
