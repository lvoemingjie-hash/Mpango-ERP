#!/usr/bin/env python3
"""Static harness validator for the SKU browser harness (B1). Stdlib only.

Enforces, fail-closed:
  - exact two-node manifest (sorted, unique, LF-terminated, no duplicates,
    no reordering, deterministic identities);
  - deterministic node titles present in the specs;
  - desktop + mobile-390 viewport coverage (exact two projects, exact
    viewports, retries 0);
  - required assertion anchors (payload binding, mismatch rejection,
    cross-tenant rejection, independent stock, immutable snapshot,
    unavailable item);
  - no response mocking / route fulfillment / network interception;
  - no skip/fixme/only/retry;
  - no H2-C / j1h2b-forgot-reset imports;
  - no direct database drivers or DB seeding;
  - page.goto restricted to the whitelisted entry points (supported
    navigation guard);
  - reconciliation accounting: every node x viewport combination recorded
    exactly once (checked against a results dir when present, else skipped
    with --allow-missing-reconciliation).

Exit 0 = GREEN, 1 = RED (findings listed on stdout).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS.parents[1]

EXPECTED_NODES = [
    "sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001",
    "sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001",
]

# Required assertion anchors: the EXACT assertion code that must remain
# present. The mutation suite removes each one independently; the validator
# must turn RED when any is missing.
REQUIRED_ANCHORS = {
    "tests/catalog-id-001.spec.ts": [
        "expect(payloadUnitIds).toContain(bottleUuid);",
        "expect([400, 404, 409, 422]).toContain(mismatch.status());",
        "expect([400, 403, 404, 409, 422]).toContain(foreign.status());",
        "expect(String(bottleStock.skuId ?? bottleStock.sku_id ?? '')).not.toBe(",
        "expect(bottleUuid).toMatch(uuidRe);",
    ],
    "tests/catalog-hist-001.spec.ts": [
        "expect(afterName).toBe(before.productName);",
        "expect(addCount === 0 || !addVisible || addDisabled).toBeTruthy();",
    ],
}

FORBIDDEN_PATTERNS = [
    (r"page\.route\s*\(", "api_mocking:page.route"),
    (r"context\.route\s*\(", "api_mocking:context.route"),
    (r"\.fulfill\s*\(", "api_mocking:fulfill"),
    (r"from\s+['\"]nock['\"]|require\(['\"]nock['\"]\)", "api_mocking:nock"),
    (r"msw", "api_mocking:msw"),
    (r"test\.skip|test\.only|\.fixme\s*\(|\.slow\s*\(", "skip_or_focus"),
    (r"retries\s*:\s*[1-9]", "retry_configured"),
    (r"j1h2b|forgot-reset|h2-c|h2c", "h2c_reference"),
    (r"from\s+['\"](pg|pg-promise|mysql|mysql2|mongodb)['\"]", "db_driver_import"),
    (r"from\s+['\"](psycopg|asyncpg|sqlalchemy)", "db_driver_import"),
    (r"INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM", "direct_db_seeding"),
]

ALLOWED_GOTO = [
    r"^'/login'$", r"^'/client/login'$", r"^`/login`$", r"^`/client/login`$",
    r"^ENTRY_WHOLESALER_LOGIN$", r"^ENTRY_RETAILER_LOGIN$",
    r"^retailerEntry$",  # supported portal handoff entry (defined as `/client/login?w=<code>`)
]


def read(rel: str) -> str:
    return (HARNESS / rel).read_text(encoding="utf-8")


def check_manifest(findings: list[str]) -> None:
    raw = (HARNESS / "manifest" / "nodes.manifest.txt").read_bytes()
    if not raw.endswith(b"\n"):
        findings.append("manifest:missing_trailing_newline")
    text = raw.decode("utf-8")
    lines = text.split("\n")[:-1]
    if any(not line.strip() for line in lines):
        findings.append("manifest:blank_line")
    if len(lines) != 2:
        findings.append(f"manifest:expected_2_nodes_got_{len(lines)}")
    if len(lines) != len(set(lines)):
        findings.append("manifest:duplicate_nodes")
    if lines != sorted(lines):
        findings.append("manifest:reordered_nodes")
    if sorted(lines) != EXPECTED_NODES:
        findings.append("manifest:node_set_mismatch")


def check_config(findings: list[str]) -> None:
    cfg = read("playwright.config.ts")
    if "retries: 0" not in cfg:
        findings.append("config:retries_not_zero")
    for project, viewport in (("desktop", "1280"), ("mobile-390", "390")):
        name_idx = cfg.find(f"name: '{project}'")
        if name_idx < 0:
            findings.append(f"config:missing_project_{project}")
            continue
        window = cfg[name_idx : name_idx + 600]
        if f"width: {viewport}" not in window:
            findings.append(f"config:project_{project}_viewport_wrong")
    if "workers: 1" not in cfg:
        findings.append("config:workers_not_serialized")


def check_specs(findings: list[str]) -> None:
    id_spec = read("tests/catalog-id-001.spec.ts")
    hist_spec = read("tests/catalog-hist-001.spec.ts")
    if "test('CATALOG-ID-001'" not in id_spec:
        findings.append("spec:catalog_id_title_missing_or_nondeterministic")
    if "test('CATALOG-HIST-001'" not in hist_spec:
        findings.append("spec:catalog_hist_title_missing_or_nondeterministic")
    bodies = {"tests/catalog-id-001.spec.ts": id_spec, "tests/catalog-hist-001.spec.ts": hist_spec}
    for rel, anchors in REQUIRED_ANCHORS.items():
        body = bodies[rel]
        for anchor in anchors:
            if anchor not in body:
                findings.append(f"anchor:missing_in_{Path(rel).name}: {anchor[:60]}")

    for rel, body in (
        ("tests/catalog-id-001.spec.ts", id_spec),
        ("tests/catalog-hist-001.spec.ts", hist_spec),
        ("src/provision.ts", read("src/provision.ts")),
        ("src/observe.ts", read("src/observe.ts")),
        ("src/global-setup.ts", read("src/global-setup.ts")),
        ("src/preflight.ts", read("src/preflight.ts")),
        ("src/reconcile.ts", read("src/reconcile.ts")),
    ):
        for pattern, label in FORBIDDEN_PATTERNS:
            for match in re.finditer(pattern, body, re.IGNORECASE):
                findings.append(f"forbidden:{label}:{rel}:{match.group(0)[:30]}")
        if rel.startswith("tests/"):
            for match in re.finditer(r"page\.goto\(([^)]*)\)", body):
                target = match.group(1).strip()
                if not any(re.search(allowed, target) for allowed in ALLOWED_GOTO):
                    findings.append(f"navigation:unsupported_goto:{rel}:{target[:40]}")
    # uuid4 / Date.now() must never enter node identities (titles are the
    # constants asserted above; guard against dynamic test titles).
    for rel, body in (("tests/catalog-id-001.spec.ts", id_spec), ("tests/catalog-hist-001.spec.ts", hist_spec)):
        for match in re.finditer(r"(?<![\w.])test\(\s*([^'\)][^,)]*)", body):
            first_arg = match.group(1).strip()
            if not (first_arg.startswith("'") or first_arg.startswith('"')):
                findings.append(f"spec:dynamic_title:{rel}:{first_arg[:30]}")


def check_no_h2c_imports(findings: list[str]) -> None:
    for path in HARNESS.rglob("*.ts"):
        rel = path.relative_to(HARNESS)
        if "node_modules" in str(rel) or "results" in str(rel):
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        for pattern in ("j1h2b", "forgot-reset", "h2-c/", "h2c"):
            if pattern in body.lower() and "h2c_reference" not in pattern:
                findings.append(f"h2c_import:{rel}:{pattern}")


def check_reconciliation(findings: list[str], allow_missing: bool) -> None:
    results = HARNESS / "results" / "reconciliation.json"
    if not results.exists():
        if allow_missing:
            return
        findings.append("reconciliation:results_absent")
        return
    data = json.loads(results.read_text(encoding="utf-8"))
    accounting = data.get("accounting", {})
    if accounting.get("gap") != 0:
        findings.append(f"reconciliation:gap_nonzero({json.dumps(accounting)})")
    expected = {(n, v) for n in (
        "sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001",
        "sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001",
    ) for v in ("desktop", "mobile-390")}
    seen = set()
    for node, records in (data.get("nodes") or {}).items():
        for rec in records or []:
            seen.add((node, rec.get("viewport")))
    if seen != expected:
        findings.append(f"reconciliation:combination_mismatch(missing={sorted(expected - seen)})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-missing-reconciliation", action="store_true",
                        help="author validation mode: reconciliation.json may be absent")
    args = parser.parse_args()

    findings: list[str] = []
    check_manifest(findings)
    check_config(findings)
    check_specs(findings)
    check_no_h2c_imports(findings)
    check_reconciliation(findings, args.allow_missing_reconciliation)

    if findings:
        print("STATIC VALIDATOR: RED")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("STATIC VALIDATOR: GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
