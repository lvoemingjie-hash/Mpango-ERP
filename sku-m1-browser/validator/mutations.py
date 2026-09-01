#!/usr/bin/env python3
"""SKU browser harness mutation suite — B1 (M01-M10) + B3 (M11-M26).

Each mutation independently removes or weakens ONE required harness property;
the static validator must turn RED under the mutation and GREEN again after
the byte-exact restore. Detection is static (fast, deterministic, and runtime
401s are terminal by contract).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
VALIDATOR = HARNESS / "validator" / "static_validator.py"
ID_SPEC = HARNESS / "tests" / "catalog-id-001.spec.ts"
HIST_SPEC = HARNESS / "tests" / "catalog-hist-001.spec.ts"
CONFIG = HARNESS / "playwright.config.ts"
MANIFEST = HARNESS / "manifest" / "nodes.manifest.txt"
PROVISION = HARNESS / "src" / "provision.ts"
FIXTURES = HARNESS / "src" / "fixtures.ts"
GLOBAL_SETUP = HARNESS / "src" / "global-setup.ts"
RUNTIME = HARNESS / "src" / "runtime.ts"
RECONCILE = HARNESS / "src" / "reconcile.ts"


def run_validator(allow_missing_reconciliation: bool = True) -> int:
    cmd = [sys.executable, str(VALIDATOR)]
    if allow_missing_reconciliation:
        cmd.append("--allow-missing-reconciliation")
    return subprocess.run(cmd, capture_output=True, text=True).returncode


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mutate_and_check(name: str, patches: list[tuple[Path, str, str]]) -> bool:
    """Apply all patches, require validator RED, restore byte-identically,
    require GREEN. patches: [(file, find, replace)]."""
    originals = [(p, p.read_bytes()) for p, _, _ in patches]
    originals_sha = {p: sha(d) for p, d in originals}
    red = False
    try:
        texts = {p: d.decode("utf-8") for p, d in originals}
        ok_anchors = True
        mutated: dict[Path, str] = {}
        for p, find, replace in patches:
            if find not in texts[p]:
                print(f"  {name:<58} FAIL (anchor not found: {find[:50]!r})")
                ok_anchors = False
                continue
            mutated[p] = texts[p].replace(find, replace, 1)
        if not ok_anchors:
            return False
        for p in mutated:
            p.write_bytes(mutated[p].encode("utf-8"))
        red = run_validator() != 0
        if not red:
            print("    [debug] mutated run stayed green")
    finally:
        for p, data in originals:
            p.write_bytes(data)
    restored = all(sha(p.read_bytes()) == originals_sha[p] for p in originals_sha)
    green_after = run_validator() == 0
    ok = red and restored and green_after
    print(f"  {name:<58} {'RED as intended (byte-identical restore)' if ok else 'FAIL'}")
    if not restored:
        print("    restore was NOT byte-identical")
    return ok


def m10_manifest() -> bool:
    original = MANIFEST.read_bytes()
    original_sha = sha(original)
    lines = original.decode("utf-8").split("\n")
    mutated_manifest = "\n".join([lines[1], lines[0], lines[1]])  # drop one, reorder, duplicate
    red = False
    try:
        MANIFEST.write_bytes(mutated_manifest.encode("utf-8"))
        red = run_validator() != 0
    finally:
        MANIFEST.write_bytes(original)
    restored = sha(MANIFEST.read_bytes()) == original_sha
    green_after = run_validator() == 0
    ok = red and restored and green_after
    print(f"  {'M10-manifest-node-dropped-and-reordered':<58} {'RED as intended (byte-identical restore)' if ok else 'FAIL'}")
    return ok


def main() -> int:
    failures: list[str] = []

    pristine = run_validator() == 0
    print(f"  {'M00-pristine-validator-green':<58} {'GREEN as intended' if pristine else 'FAIL (pristine red)'}")
    if not pristine:
        failures.append("pristine")

    mutations: list[tuple[str, list[tuple[Path, str, str]]]] = [
        ("M01-payload-assertion-removed", [
            (ID_SPEC, "expect(payloadUnitIds).toContain(bottleUuid);", "// payload assertion removed"),
        ]),
        ("M02-mismatch-rejection-removed", [
            (ID_SPEC, "expect([400, 404, 409, 422]).toContain(mismatch.status());", "// mismatch rejection removed"),
        ]),
        ("M03-cross-tenant-rejection-removed", [
            (ID_SPEC, "expect([400, 403, 404, 409, 422]).toContain(foreign.status());", "// cross-tenant rejection removed"),
        ]),
        ("M04-independent-stock-assertion-removed", [
            (ID_SPEC,
             "expect(String(bottleStock.skuId ?? bottleStock.sku_id ?? '')).not.toBe(\n    String(caseStock.skuId ?? caseStock.sku_id ?? ''),\n  );",
             "// independent stock assertion removed"),
        ]),
        ("M05-immutable-snapshot-assertion-removed", [
            (HIST_SPEC, "expect(afterName).toBe(before.productName);", "// immutable snapshot assertion removed"),
        ]),
        ("M06-unavailable-item-assertion-removed", [
            (HIST_SPEC, "await expect(unavailableUnitLink).toHaveCount(0);", "// unavailable-item assertion removed"),
        ]),
        ("M07-mobile-390-coverage-removed", [
            (CONFIG, "name: 'mobile-390',", "name: 'desktop-shadow',"),
        ]),
        ("M08-no-mock-guard-violated", [
            (ID_SPEC, "attachObserver(page, observed);",
             "attachObserver(page, observed);\n  await page.route('**/api/v1/client/orders', (route) => route.fulfill({ status: 201, body: '{}' }));"),
        ]),
        ("M09-supported-navigation-guard-violated", [
            (ID_SPEC, "await page.goto(ENTRY_WHOLESALER_LOGIN);",
             "await page.goto(ENTRY_WHOLESALER_LOGIN);\n  await page.goto('/skus');"),
        ]),
        ("M10-manifest-node-dropped-and-reordered", [
            (MANIFEST, "__M10_SPECIAL__", "__M10_SPECIAL__"),
        ]),
        ("M11-shared-fixed-sku-code-restored", [
            (PROVISION,
             "codes: [`${nodeShort}-${vp}-UNIT`, `${nodeShort}-${vp}-PACK`],",
             "codes: ['B1-JUICE-BOTTLE', 'B1-JUICE-CASE'] as [string, string],"),
        ]),
        ("M12-per-node-namespace-removed", [
            (PROVISION,
             "const vp: ViewportId = viewport === 'mobile-390' ? 'MOBILE-390' : 'DESKTOP';",
             "const vp: ViewportId = 'DESKTOP';"),
        ]),
        ("M13-inventory-authorization-removed", [
            (ID_SPEC,
             "      `${API}/api/v1/inventory/stocks/${encodeURIComponent(bottleCode)}`,\n      { headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` } },",
             "      `${API}/api/v1/inventory/stocks/${encodeURIComponent(bottleCode)}`,"),
        ]),
        ("M14-catalog-mutation-authorization-removed", [
            (ID_SPEC,
             "      headers: { Authorization: `Bearer ${shared.tenantA.accessToken}` },\n      data: { is_active: false },",
             "      data: { is_active: false },"),
        ]),
        ("M15-client-order-authorization-removed", [
            (HIST_SPEC,
             "    headers: { Authorization: `Bearer ${shared.retailer.accessToken}` },\n    data: { items: [{ sellable_unit_id: unit.sellableUnitId, sku_code: unit.skuCode, quantity: 2 }] },",
             "    data: { items: [{ sellable_unit_id: unit.sellableUnitId, sku_code: unit.skuCode, quantity: 2 }] },"),
        ]),
        ("M16-401-replay-introduced", [
            (HIST_SPEC,
             "  const historical = await page.request.get(`${API}/api/v1/client/orders/${orderId}`, {\n    headers: { Authorization: `Bearer ${shared.retailer.accessToken}` },\n  });",
             "  let historical;\n  for (let attempt = 0; attempt < 3; attempt++) {\n    historical = await page.request.get(`${API}/api/v1/client/orders/${orderId}`, {\n      headers: { Authorization: `Bearer ${shared.retailer.accessToken}` },\n    });\n    if (historical.status() === 401) continue; // replay after 401\n    break;\n  }"),
        ]),
        ("M17-back-control-role-changed-to-broad-link", [
            (HIST_SPEC, "await page.getByRole('button', { name: 'Back to orders' }).click();",
             "await page.getByRole('link', { name: 'Back to orders' }).click();"),
        ]),
        ("M18-mobile-menu-opening-removed", [
            (ID_SPEC, "  await expect(menuButton).toBeVisible();\n  await menuButton.click();",
             "  // mobile menu opening removed by M18"),
        ]),
        ("M19-wildcard-first-selector-introduced", [
            (HIST_SPEC, "await page.getByRole('link', { name: 'Products' }).click();",
             "await page.getByRole('link', { name: /.*/ }).first().click();"),
        ]),
        ("M20-one-node-mutates-another-nodes-resource", [
            (HIST_SPEC, "const ns = executionNamespace('CATHIST', viewport);",
             "const ns = executionNamespace('CATID', viewport);"),
        ]),
        ("M21-central-fixture-removed-from-spec", [
            (ID_SPEC, "import { test, expect } from '../src/fixtures';",
             "import { test, expect } from '@playwright/test';"),
        ]),
        ("M22-failure-recorded-as-not-run", [
            (FIXTURES, "const status = testInfo.status === 'passed' ? 'passed' : 'failed';",
             "const status = testInfo.status === 'passed' ? 'passed' : 'not_run' as any;"),
        ]),
        ("M23-author-diagnostic-mode-guard-removed", [
            (GLOBAL_SETUP, "  requireAuthorDiagnosticMode();",
             "  // requireAuthorDiagnosticMode removed by M23"),
        ]),
        ("M24-stale-runtime-cleanup-removed", [
            (GLOBAL_SETUP, "  clearGeneratedRuntimeOutputs();",
             "  // clearGeneratedRuntimeOutputs removed by M24"),
        ]),
        ("M25-second-author-invocation-guard-removed", [
            (RUNTIME, "second_author_diagnostic_invocation_refused",
             "second_invocation_allowed_by_M25"),
        ]),
        ("M26-report-disagreement-accounting-removed", [
            (RECONCILE, "reportDisagreements += 1;",
             "// report disagreement increment removed by M26"),
        ]),
    ]

    for name, patches in mutations:
        if name.startswith("M10"):
            if not m10_manifest():
                failures.append("M10-manifest-node-dropped-and-reordered")
            continue
        if not mutate_and_check(name, patches):
            failures.append(name)

    if failures:
        print(f"MUTATION SUITE: RED-FAILED ({len(failures)}): {failures}")
        return 1
    print("MUTATION SUITE: all 26 mutations RED as intended, pristine and restored states GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
