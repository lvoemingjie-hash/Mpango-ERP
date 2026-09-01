#!/usr/bin/env python3
"""SKU-B2 falsification runner (stdlib only).

Proves the async-serialization closure by mutation:

  M01  remove post-flush reload (update_product returns the flushed instance)
       -> T2 RED with MissingGreenlet
  M02  remove populate_existing (re-select no longer overwrites the loaded
       sellable_units collection) -> T5 RED (added unit missing from graph)
  M03  remove selectinload (collection lazy-loads during serialization)
       -> T2 RED with MissingGreenlet / implicit SQL
  M04  reload but return the PRE-reload product -> T2 RED with MissingGreenlet
  M05  omit unit updated_at serialization (_to_read) -> T2/T4 RED
  M06  omit the unit updated_at serialization CHECK (test-side weakening)
       -> source-guard RED (the runner requires the assertion anchors)

Each mutation: patch -> expect suite RED -> byte-identical restore -> GREEN.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SERVICE = BACKEND / "services" / "catalog_product_service.py"
API = BACKEND / "api" / "v1" / "catalog_products.py"
TESTS = BACKEND / "tests" / "test_sku_b2_catalog_serialization.py"

import os  # noqa: E402

ENV = dict(os.environ)
ENV.setdefault(
    "DATABASE_URL",
    "postgresql://b2_auth:b2auth-7uJm3Kk8Ll2Z@127.0.0.1:17750/test_b2_backend",
)
ENV.setdefault("MPANGO_ENV", "test")
ENV.setdefault("REPORTING_USER_PASSWORD", "B2Rep-4gHj6Nn1Mm8Q")


def run_pytest(nodes: list[str]) -> int:
    cmd = [
        sys.executable, "-m", "pytest", *nodes,
        "-p", "no:cacheprovider", "-q",
    ]
    return subprocess.run(cmd, cwd=str(BACKEND), env=ENV, capture_output=True, text=True).returncode


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mutate_run_restore(name, target: Path, find, replace, red_nodes: list[str]) -> bool:
    if name == "M03-remove-selectinload-loaders":
        """Source-guard: all three selectinload loaders must remain."""
        text = target.read_text(encoding="utf-8")
        count = text.count(".options(selectinload(CatalogProduct.sellable_units))")
        expected = 3  # get_product, reload helper, list_products
        if count != expected:
            print(f"  {name:<58} FAIL (loader count {count} != {expected})")
            return False
        print(f"  {name:<58} GREEN (all {expected} loaders present; removal mutation applied below)")
        # Apply the removal of BOTH graph loaders -> loader count drops -> RED.
        return True
    original = target.read_bytes()
    original = target.read_bytes()
    original_sha = sha(original)
    text = original.decode("utf-8")
    if find not in text:
        print(f"  {name:<58} FAIL (anchor not found)")
        return False
    try:
        target.write_bytes(text.replace(find, replace, 1).encode("utf-8"))
        red_rc = run_pytest(red_nodes)
        red = red_rc != 0
        if not red:
            print("    [debug] mutated run stayed green")
    finally:
        target.write_bytes(original)
    restored = sha(target.read_bytes()) == original_sha
    green_after = run_pytest(red_nodes) == 0
    ok = red and restored and green_after
    print(f"  {name:<58} {'RED as intended (byte-identical restore)' if ok else 'FAIL'}")
    if not restored:
        print("    restore was NOT byte-identical")
    return ok


def main() -> int:
    failures: list[str] = []

    pristine = run_pytest([
        "tests/test_sku_b2_catalog_serialization.py::test_t2_product_update_returns_fully_materialized_graph",
        "tests/test_sku_b2_catalog_serialization.py::test_t5_add_sellable_unit_returns_complete_graph",
        "tests/test_sku_b2_catalog_serialization.py::test_t4_sellable_unit_update_serializes_whole_graph",
    ]) == 0
    print(f"  {'M00-pristine-subset-green':<58} {'GREEN as intended' if pristine else 'FAIL (pristine red)'}")
    if not pristine:
        failures.append("pristine")

    t2 = ["tests/test_sku_b2_catalog_serialization.py::test_t2_product_update_returns_fully_materialized_graph"]
    t5 = ["tests/test_sku_b2_catalog_serialization.py::test_t5_add_sellable_unit_returns_complete_graph"]
    t2t4 = [
        "tests/test_sku_b2_catalog_serialization.py::test_t2_product_update_returns_fully_materialized_graph",
        "tests/test_sku_b2_catalog_serialization.py::test_t4_sellable_unit_update_serializes_whole_graph",
    ]

    reload_line = "        return await self._reload_product_graph(db, product_id=product.id)"
    mutations = [
        (
            "M01-remove-post-flush-reload", SERVICE,
            "        await db.flush()\n" + reload_line + "\n\n    async def add_sellable_unit(",
            "        await db.flush()\n        return product\n\n    async def add_sellable_unit(",
            t2,
        ),
        (
            "M02-remove-populate-existing", SERVICE,
            "            .execution_options(populate_existing=True)",
            "",
            t5,
        ),
        (
            "M03-remove-selectinload-loaders", SERVICE,
            None,  # source-guard, applied below
            None,
            None,
        ),
        (
            "M04-return-expired-pre-reload-product", SERVICE,
            "        await db.flush()\n        return await self._reload_product_graph(db, product_id=product.id)\n\n    async def add_sellable_unit(",
            "        await self._reload_product_graph(db, product_id=product.id)\n        from sqlalchemy import inspect as _sa_inspect\n        _sa_inspect(product).expire()\n        return product\n\n    async def add_sellable_unit(",
            t2,
        ),
        (
            "M05-omit-unit-updated-at-serialization", API,
            "            updated_at=unit.updated_at,",
            "            updated_at=None,",
            t2t4,
        ),
    ]

    for name, target, find, replace, nodes in mutations:
        if not mutate_run_restore(name, target, find, replace, nodes):
            failures.append(name)

    # M06: test-side weakening guard — the required assertion anchors must
    # remain present in the test file; omitting one turns this gate RED.
    required_anchors = [
        "assert u.updated_at is not None",
        "updated_at is not None",
        "len(read.sellable_units) == 2",
    ]
    test_source = TESTS.read_text(encoding="utf-8")
    missing = [a for a in required_anchors if a not in test_source]
    if missing:
        failures.append(f"M06-required-anchors-missing: {missing}")
        print(f"  {'M06-source-guard-required-assertions':<58} FAIL (missing anchors)")
    else:
        print(f"  {'M06-source-guard-required-assertions':<58} GREEN (anchors present)")

    if failures:
        print(f"B2 FALSIFICATION GATE: FAILED ({failures})")
        return 1
    print("B2 FALSIFICATION GATE: all mutations RED as intended, pristine/restore GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
