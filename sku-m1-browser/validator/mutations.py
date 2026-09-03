#!/usr/bin/env python3
"""SKU browser harness mutation suite — B1 (M01-M10) + B3 (M11-M26) + B4 (M27-M36).

Each mutation independently removes or weakens ONE required harness property;
the static validator must turn RED under the mutation and GREEN again after
the byte-exact restore. Detection is static (fast, deterministic, and runtime
401s are terminal by contract).

B4 (M27-M36) covers the independent-browser-authority mode contract.

R1 (M37-M42) covers the product-level multipackaging oracle: containment
(exactly one product container), packaging inside that same container,
selection switching the selected sellable_unit_id, stock following the
selected unit, and the returned identity equaling the chosen unit:
  M27 remove mode exclusivity
  M28 map independent mode to AUTHOR_DIAGNOSTIC
  M29 allow no-mode execution
  M30 delete ledger mode comparison
  M31 delete reconciliation mode comparison
  M32 permit cross-mode second invocation
  M33 permit candidate-SHA ledger drift
  M34 enable reporter only for author mode
  M35 let --list write evidence
  M36 relabel author evidence independent

R5 (M43) covers the runbook run contract: restoring the old test-mode +
SMTP/maildir backend documentation in the README must turn the static
validator RED (L4 VOID_ENVIRONMENT_PRECHECK__TEST_MODE_CANNOT_FEED_MAILDIR_
SMTP_HARNESS), and the byte-exact restore must be GREEN again.

R5-R1 (M44-M46) covers the command-block-bound runbook oracle:
  M44 weaken the marked command's SMTP/TLS contract (STARTTLS back on)
  M45 downgrade the marked command's HTTPS origin to http
  M46 move a required anchor outside the marked block so global prose
      presence cannot hide its absence inside the executable block
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
VALIDATOR = HARNESS / "validator" / "static_validator.py"
README = HARNESS / "README.md"
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
        ("M23-runtime-mode-guard-removed", [
            (GLOBAL_SETUP, "  requireRuntimeMode();",
             "  // requireRuntimeMode removed by M23"),
        ]),
        ("M24-stale-runtime-cleanup-removed", [
            (GLOBAL_SETUP, "  clearGeneratedRuntimeOutputs();",
             "  // clearGeneratedRuntimeOutputs removed by M24"),
        ]),
        ("M25-second-invocation-guard-removed", [
            (RUNTIME, "  if (starts.length >= 1) {",
             "  if (false) {  // second-invocation guard removed by M25"),
        ]),
        ("M26-report-disagreement-accounting-removed", [
            (RECONCILE, "reportDisagreements += 1;",
             "// report disagreement increment removed by M26"),
        ]),
        # ---- B4: independent browser authority mode contract -----------------
        ("M27-mode-exclusivity-removed", [
            (RUNTIME, "  if (authorSet && independentSet) {",
             "  if (false) {  // mode exclusivity removed by M27"),
        ]),
        ("M28-independent-mode-mapped-to-author-diagnostic", [
            (RUNTIME, "  if (independentSet) return INDEPENDENT_AUTHORITY;",
             "  if (independentSet) return AUTHOR_DIAGNOSTIC;  // relabelled by M28"),
        ]),
        ("M29-no-mode-execution-allowed", [
            (RUNTIME,
             "  if (authorSet) return AUTHOR_DIAGNOSTIC;\n"
             "  if (independentSet) return INDEPENDENT_AUTHORITY;\n"
             "  throw new ModeResolutionError(\n"
             "    CODE_MODE_UNSET,\n"
             "    `exactly one of ${AUTHOR_DIAGNOSTIC_ENV}=1 / ${INDEPENDENT_AUTHORITY_ENV}=1 is required for browser runtime execution`,\n"
             "  );",
             "  if (independentSet) return INDEPENDENT_AUTHORITY;\n"
             "  return AUTHOR_DIAGNOSTIC;  // no-mode execution allowed by M29"),
        ]),
        ("M30-ledger-mode-comparison-deleted", [
            (RECONCILE,
             "    checkBinding(`invocation_ledger:${record.event}`, record.mode, record.candidate_sha,\n"
             "      expectedMode, expectedSha, errors, bindingTally);",
             "    // ledger mode comparison deleted by M30"),
        ]),
        ("M31-reconciliation-mode-comparison-deleted", [
            (RECONCILE,
             "    checkBinding(`reconciliation_record:${key(rec.node, rec.viewport)}`, rec.mode, rec.candidate_sha,\n"
             "      expectedMode, expectedSha, errors, bindingTally);",
             "    // reconciliation mode comparison deleted by M31"),
        ]),
        ("M32-cross-mode-second-invocation-permitted", [
            (RUNTIME, "  const foreignMode = starts.filter((record) => record.mode !== mode);",
             "  const foreignMode = starts.filter((record) => false);  // cross-mode permitted by M32"),
        ]),
        ("M33-candidate-sha-ledger-drift-permitted", [
            (RUNTIME,
             "  const foreignSha = prior.filter((record) => record.candidate_sha !== candidateSha);",
             "  const foreignSha = prior.filter((record) => false);  // SHA drift permitted by M33"),
        ]),
        ("M34-reporter-enabled-only-for-author-mode", [
            (CONFIG, "= runtimeMode ? [",
             "= runtimeMode === AUTHOR_DIAGNOSTIC ? [  // independent mode silenced by M34"),
        ]),
        ("M35-list-writes-runtime-evidence", [
            (CONFIG, "isListMode ? null : resolveRuntimeMode()",
             "resolveRuntimeMode()  // --list no longer exempt by M35"),
        ]),
        ("M36-author-evidence-relabelled-independent", [
            (RUNTIME,
             "  if (contract) return assertKnownMode(contract.execution_mode, LIVE_EXECUTION_CONTRACT);",
             "  if (contract) return INDEPENDENT_AUTHORITY;  // relabelled by M36"),
        ]),
        # ---- R1: product-level multipackaging oracle -------------------------
        ("M37-product-container-uniqueness-removed", [
            (ID_SPEC,
             "  await expect(productContainer).toHaveCount(1, { timeout: 30_000 });",
             "  // product-container uniqueness removed by M37"),
        ]),
        ("M38-in-container-packaging-assertion-removed", [
            (ID_SPEC,
             "  await expect(containerUnits).toContainText(caseCode, { timeout: 30_000 });",
             "  // in-container packaging assertion removed by M38"),
        ]),
        ("M39-selected-unit-switch-assertion-removed", [
            (ID_SPEC,
             "  await expect(orderSection).toHaveAttribute('data-selected-sellable-unit-id', caseUuid, {",
             "  // selected-unit switch assertion removed by M39"),
        ]),
        ("M40-selected-stock-update-assertion-removed", [
            (ID_SPEC,
             "  await expect(page.getByTestId('selected-unit-stock')).toHaveText('Low Stock', {",
             "  // selected-stock update assertion removed by M40"),
        ]),
        ("M41-returned-identity-check-removed", [
            (ID_SPEC,
             "  expect(orderItems[0].sellable_unit_id ?? orderItems[0].sellableUnitId).toBe(bottleUuid);",
             "  // returned-identity check removed by M41"),
        ]),
        ("M42-hist-product-container-anchor-removed", [
            (HIST_SPEC,
             "  await expect(productContainer).toBeVisible({ timeout: 30_000 });",
             "  // hist product-container anchor removed by M42"),
        ]),
        # ---- R5: runbook run contract ---------------------------------------
        ("M43-runbook-test-mode-smtp-combo-restored", [
            (README,
             "MPANGO_ENV=production \\",
             "MPANGO_ENV=test \\  # old VOID test-mode combo restored by M43"),
        ]),
        # ---- R5-R1: command-block-bound runbook oracle ----------------------
        ("M44-marked-command-starttls-re-enabled", [
            (README,
             "SMTP_USE_TLS=0 SMTP_STARTTLS=0 \\",
             "SMTP_USE_TLS=0 SMTP_STARTTLS=1 \\  # STARTTLS re-enabled by M44"),
        ]),
        ("M45-marked-command-https-origin-downgraded", [
            (README,
             "PUBLIC_FRONTEND_URL=https://skum1browser.email-links.invalid \\",
             "PUBLIC_FRONTEND_URL=http://skum1browser.email-links.invalid \\  # HTTPS downgraded by M45"),
        ]),
        ("M46-required-anchor-moved-outside-command-block", [
            # pristine README deliberately carries a prose duplicate of the
            # SMTP_HOST anchor; removing ONLY the in-block occurrence leaves
            # global substring presence intact while the executable block
            # loses the anchor — the command-block oracle must be RED.
            (README,
             "SMTP_HOST=127.0.0.1 SMTP_PORT=<smtp-port> \\",
             "SMTP_PORT=<smtp-port> \\"),
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
    print(f"MUTATION SUITE: all {len(mutations)} mutations RED as intended, pristine and restored states GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
