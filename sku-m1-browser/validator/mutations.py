#!/usr/bin/env python3
"""Mutation suite for the SKU browser harness (B1). Stdlib only.

Each mutation independently removes or weakens ONE required harness property;
the static validator must turn RED under the mutation and GREEN again after
the byte-exact restore. Mutations:

  M01  sellable_unit_id payload assertion removed
  M02  mismatched UUID/code rejection removed
  M03  cross-tenant UUID rejection removed
  M04  independent stock assertion removed
  M05  immutable historical snapshot assertion removed
  M06  unavailable-item assertion removed
  M07  mobile-390 viewport coverage removed (project deleted)
  M08  no-mock guard violated (API route fulfillment introduced)
  M09  supported-navigation guard violated (deep-URL goto introduced)
  M10  exact node manifest broken (node dropped + reorder + duplicate)

GREEN controls: pristine candidate must pass the validator before and after
every mutation (byte-identical restore is enforced by SHA-256).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
VALIDATOR = HARNESS / "validator" / "static_validator.py"

ID_SPEC = HARNESS / "tests" / "catalog-id-001.spec.ts"
HIST_SPEC = HARNESS / "tests" / "catalog-hist-001.spec.ts"
CONFIG = HARNESS / "playwright.config.ts"
MANIFEST = HARNESS / "manifest" / "nodes.manifest.txt"


def run_validator(allow_missing_reconciliation: bool = True) -> int:
    import subprocess
    cmd = [sys.executable, str(VALIDATOR)]
    if allow_missing_reconciliation:
        cmd.append("--allow-missing-reconciliation")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode


def mutate_and_check(name: str, target: Path, find: str, replace: str) -> bool:
    """Apply patch, require validator RED, restore byte-identically, require GREEN."""
    original = target.read_bytes()
    original_sha = hashlib.sha256(original).hexdigest()
    mutated = original.decode("utf-8").replace(find, replace, 1)
    if mutated == original.decode("utf-8"):
        print(f"  {name:<52} FAIL (anchor not found)")
        return False
    red_ok = False
    try:
        target.write_bytes(mutated.encode("utf-8"))
        red_ok = run_validator() != 0
    finally:
        target.write_bytes(original)
    restored_sha = hashlib.sha256(target.read_bytes()).hexdigest()
    if restored_sha != original_sha:
        print(f"  {name:<52} FAIL (restore not byte-identical)")
        return False
    green_after = run_validator() == 0
    ok = red_ok and green_after
    print(f"  {name:<52} {'RED as intended (byte-identical restore)' if ok else 'FAIL'}")
    return ok


def main() -> int:
    failures: list[str] = []

    pristine = run_validator() == 0
    print(f"  {'M00-pristine-validator-green':<52} {'GREEN as intended' if pristine else 'FAIL (pristine already RED)'}")
    if not pristine:
        failures.append("pristine validator not green")

    mutations = [
        ("M01-payload-assertion-removed", ID_SPEC,
         "  expect(payloadUnitIds).toContain(bottleUuid);",
         "  // payload assertion removed by M01"),
        ("M02-mismatch-rejection-removed", ID_SPEC,
         "  expect([400, 404, 409, 422]).toContain(mismatch.status());",
         "  // mismatch rejection removed by M02"),
        ("M03-cross-tenant-rejection-removed", ID_SPEC,
         "  expect([400, 403, 404, 409, 422]).toContain(foreign.status());",
         "  // cross-tenant rejection removed by M03"),
        ("M04-independent-stock-assertion-removed", ID_SPEC,
         '  expect(String(bottleStock.skuId ?? bottleStock.sku_id ?? \'\')).not.toBe(\n    String(caseStock.skuId ?? caseStock.sku_id ?? \'\'),\n  );',
         "  // independent stock assertion removed by M04"),
        ("M05-immutable-snapshot-assertion-removed", HIST_SPEC,
         "  expect(afterName).toBe(before.productName);",
         "  // immutable snapshot assertion removed by M05"),
        ("M06-unavailable-item-assertion-removed", HIST_SPEC,
         "  expect(addCount === 0 || !addVisible || addDisabled).toBeTruthy();",
         "  // unavailable-item assertion removed by M06"),
        ("M07-mobile-390-coverage-removed", CONFIG,
         """    {
      name: 'mobile-390',""",
         """    {
      name: 'desktop-shadow',"""),
        ("M08-no-mock-guard-violated", ID_SPEC,
         "  const state = loadProvisionedState();",
         "  const state = loadProvisionedState();\n"
         "  await page.route('**/api/v1/client/orders', (route) => route.fulfill({ status: 201, body: '{}' }));"),
        ("M09-supported-navigation-guard-violated", ID_SPEC,
         "  await page.goto(ENTRY_WHOLESALER_LOGIN);",
         "  await page.goto(ENTRY_WHOLESALER_LOGIN);\n"
         "  await page.goto('/skus');"),
        ("M10-manifest-node-dropped-and-reordered", MANIFEST,
         None,  # special-cased below
         None),
    ]

    for name, target, find, replace in mutations:
        if name.startswith("M10"):
            original = MANIFEST.read_bytes()
            original_sha = hashlib.sha256(original).hexdigest()
            lines = original.decode("utf-8").split("\n")
            mutated_manifest = "\n".join([lines[1], lines[0], lines[1]])  # drop one, reorder, duplicate
            red_ok = False
            try:
                MANIFEST.write_bytes(mutated_manifest.encode("utf-8"))
                red_ok = run_validator() != 0
            finally:
                MANIFEST.write_bytes(original)
            restored_sha = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
            if restored_sha != original_sha:
                failures.append(f"{name}: restore not byte-identical")
                print(f"  {name:<52} FAIL (restore not byte-identical)")
                continue
            green_after = run_validator() == 0
            ok = red_ok and green_after
            print(f"  {name:<52} {'RED as intended (byte-identical restore)' if ok else 'FAIL'}")
            if not ok:
                failures.append(name)
            continue
        if not mutate_and_check(name, target, find, replace):
            failures.append(name)

    if failures:
        print(f"MUTATION SUITE: RED-FAILED ({len(failures)}): {failures}")
        return 1
    print("MUTATION SUITE: all 10 mutations RED as intended, pristine and restored states GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
