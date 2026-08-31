# DC-12R1-MVP-L1-SKU-R0-M1-R1-A2-V2 — Lubuntu Independent SKU Runtime and Merge-Readiness Final

**Date:** 2026-08-31 | **Host:** Lubuntu x86_64 (Ubuntu 24.04, Docker 29.1.3, PG16.15, Redis 7, Python 3.12.3, Node 22.23.2)
**Verdict: STOP_AND_REPORT_CTO_BLOCKED_BY_MISSING_AUTHORITATIVE_SKU_BROWSER_HARNESS**

## Verdict summary

Candidate `8cef1fffe2ca92f9c368ffd23a1ce6ece7812f1b` passed every executable gate
this task owns: migration 038 authority (exact parent 037, single head, all-tenant
preflight, unique-reservation-only legacy identity link), focused bundle 150/150 in
natural and reverse order on separate fresh databases, full backend authority run
through `AUTHORITY_SKU_M1_BACKEND` with **accounting gap = 0**, and frontend
400/400 + clean TypeScript check + successful production build. **Product-defect
count = 0.** The merge-readiness statement is BLOCKED solely because the two
authoritative inventory nodes CATALOG-ID-001 / CATALOG-HIST-001 have no frozen
browser harness anywhere in the candidate; per task contract no browser PASS was
improvised, and a separate harness-authoring task is required before controlled
merge. Additionally, the authority run exposed **61 STALE_TEST_CONTRACT reds**
(proven green at baseline `24a28d76`) that the CTO must schedule for repair.

## 1. Candidate and ancestry (exact)

| Proof | Result |
|---|---|
| `origin/product-dev-recovered` | `24a28d76d6d9483d8101f8e0f537c148dc262859` (rev-parse == protected baseline) ✓ |
| `origin/codexl/dc12r1-mvp-l1-sku-r0-m1-r1-a2-catalog-identity-2026-08-30` | `8cef1fffe2ca92f9c368ffd23a1ce6ece7812f1b` (rev-parse == candidate) ✓ |
| Chain | `24a28d76` → `8bdb9911f21b554da2970e673b73eacd6e09537f` "feat(sku): add catalog identity vertical slice" (2026-08-30) → `8cef1fff` "fix(sku): close bootstrap and seeder identity review gaps" (2026-08-31 05:08 +0800) ✓ |
| Shape | Linear; no merge commits; baseline `--is-ancestor` true ✓ |
| Worktree | Fresh detached worktree at candidate; tracked tree clean for the whole run (only test-runtime hypothesis cache churn + untracked runner `artifacts/`) ✓ |

## 2. Changed-path accounting (exact)

`git diff --name-status 24a28d76..8cef1fff`: **60 paths** (38 modified, 22 added;
0 deleted), 4,784 insertions / 619 deletions. All 60 paths are catalog-identity
scope: backend models/services/repos/APIs/schemas (`catalog_product`,
`sku`, `order`, `inventory`), alembic 038, bootstrap/seeder, their tests, frontend
SKU/order/catalog pages + services + types + tests, `docs/contracts/openapi.yaml`,
and 7 harness-governance files authorized by the candidate's own registered deltas
`PD-2026-08-30-SKU-R0-M1-R1-A4` / `-A5` (inventory node binding for
CATALOG-ID-001/CATALOG-HIST-001; R3-A1 truth retarget to real 038/037 tree).

**Scope exclusion (no H2-C / PRICING / ORDER-PRICE / REORDER scope):**

| Check | Result |
|---|---|
| Path overlap vs H2-C branch `origin/zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r5-browser-authority-control-plane-closure-2026-08-31` (54 changed paths) | **intersection = ∅** ✓ |
| Forbidden-keyword scan of full delta (reorder/repricing/negotiation/promotion/tax/payment-expansion) | only governance-JSON node-ordering wording + unchanged context line; no feature scope ✓ |
| `backend/tests/test_phase4_pricing_safe_orders.py` diff | identity-adaptation only (`sellable_unit_id`, snapshot fields, allowlist pragma); no price-resolution change ✓ |
| diff --check / strict UTF-8 / CRLF / BOM over all 60 paths | clean / valid / none / none ✓ |
| `detect-secrets scan` (raw) | 13 findings, all `"base_sha"` git SHAs in protocol-deltas.json — not secrets ✓ |
| `detect-secrets-hook --baseline .secrets.baseline` over 60 paths | exit 0 — zero findings outside baseline ✓ |
| `.secrets.baseline` mutation guard | `sha256 c8f3aa24…0290e6` verified unchanged after every scan (an accidental `scan --baseline` settings-import was immediately caught by the SHA guard and restored from git before any further action; final SHA verified OK) ✓ |

## 3. Migration 038 parent/head truth

| Proof | Result |
|---|---|
| Static | `038_catalog_identity_vertical_slice` `down_revision = "037_payment_declarations_schema"`, non-merge ✓ |
| Tree | 38 revision files; `alembic heads` = exactly `038_catalog_identity_vertical_slice` (single head) ✓ |
| Runner profile binding | `AUTHORITY_SKU_M1_BACKEND` preflight + child sessionstart both verified profile-bound successor (single head byte-equal 038, declared parent 037): published proof `alembic_expected_bound=true, alembic_match=true` ✓ |
| Fresh-chain execution | fresh PG16 DB → `alembic upgrade 037` (current = 037) → **one** `upgrade 038` exactly; `alembic current` = 038 ✓ |

## 4. Migration authority (Phase 2) — fresh PG16, role `sku_v2_auth` (rolsuper=f, rolcreatedb=t)

Manual proof harness (in /tmp, reusing the candidate's own test helpers; no
product/test edits) on `test_sku_v2_migr`:

1. Chain at 037; 2 registered tenants (`t_f087f6e6…`, `t_3d763086…`) bootstrapped
   then stripped of 038 artifacts (pre-038 legacy simulation); legacy SKU/order/
   reservation cases seeded (unique-evidence, ambiguous-A/B, safe-zero stock).
2. Single `alembic upgrade 038` executed.
3. Postconditions ALL GREEN: `alembic_version`=038; migrated-tenant schema
   contract == fresh-bootstrap reference contract (columns/constraints/indexes,
   both tenants); unique reservation evidence is the ONLY legacy identity link
   (`linked_legacy`=1 with `sellable_unit_id` set; ambiguous + no-evidence stay
   `legacy` with NULL); order snapshots byte-stable; per-unit stock preserved
   (17.00/3.00; safe 0.00/0.00).

`backend/tests/test_sku_m1_migration_pg16.py` on the same fresh stack:
**6 passed / 0 failed / 0 errors / 0 skipped** (45.2s) — covering all-tenant
preflight-before-mutation, one-unsafe-tenant → zero tenant mutation, unregistered
pre-038 bootstrap tenant reconciliation, unsafe missing-stock reconciliation
rollback, demo seeder delegating to canonical bootstrap, and non-live registered
tenant fail-closed. Bootstrap/Seeder/Alembic parity: migrated == bootstrap
reference contract (above) + seeder test green.

## 5. Focused backend (Phase 3) — natural and reverse on separate fresh DBs

Bundle: 3 SKU-M1 files + pricing-safe-orders + U3C×2 + U4IB2 + six S4 invariant
files. Both databases freshly created with the alembic chain at head 038
(`test_sku_v2_focus_a` / `_b`).

| Order | Result |
|---|---|
| Natural (SKU → … → S4F) | **150 passed / 0 failed / 0 errors / 0 skipped** (138s) |
| Reverse (S4F → … → SKU) | **150 passed / 0 failed / 0 errors / 0 skipped** (185s) |

Calibration disclosure: the FIRST natural attempt ran against a bare fresh DB
(chain not applied by my environment prep) → 131 passed / 19 failed, all in the two
S4 files that require `public` master tables, single cause
`UndefinedTableError: relation "public.wholesalers" does not exist`. Classified
TEST_INFRASTRUCTURE (my environment preparation, not product); superseded by the
two canonical runs above.

## 6. Full backend authority (Phase 4) — AUTHORITY_SKU_M1_BACKEND, exactly once

Infrastructure: fresh PG16 container + fresh Redis 7 container (loopback ports,
task-owned networks), role `sku_v2_auth` (NOSUPERUSER, CREATEDB, +CREATEROLE —
required by migration 011's cluster-role management on bare temp DBs; runner
checks `rolsuper=f AND rolcreatedb=t` pass), Redis DB15 empty (DBSIZE 0) and
sentinel 127.0.0.1:26379 unreachable, `MPANGO_ALLOW_TEMP_DB_CREATE=1` with
port/host allowlists, `REPORTING_USER_PASSWORD` set, no profile override.

Runner sequence: `--preflight-only` PASS → full-manifest attempt → staged
`--collect-only` (registered profile defaults) PASS → **single authority launch**
(`sentinel_calls=1`, state FINISHED, `RUN_VERDICT=TEST_RED_REAL_COMMAND_NONZERO
exit=1`).

**Accounting (gap = 0):**

| Metric | Value |
|---|---|
| Collected (frozen at candidate) | **3803** |
| junit unique nodes | **3803** (set diff vs frozen manifest = ∅) |
| passed | **3678** |
| failed | **49** |
| errors | **167** junit entries = **13 unique** (setup) + **154 teardown-error duplicate entries** |
| skipped / xfailed / xpassed | 48 / 15 / **0** |
| Accounting | 3678+49+13+48+15 = **3803 = collected → gap 0** ✓ |

**Every red root-caused and classified — CURRENT_PRODUCT_DEFECT count = 0:**

| Class | Count | Root cause (sanitized) | Proof |
|---|---|---|---|
| ENVIRONMENT_GATED | 155 (1 failure + 154 teardown errors) | `redis.exceptions.ConnectionError: Error -2 connecting to redis:6379` — my run env omitted `REDIS_URL`, so conftest defaulted to the compose hostname; no such host exists on this stack | Same-file rerun with corrected env: `test_dc12r1_contract_d_statement_print.py` **76 passed / 0 failed** (601s) |
| STALE_TEST_CONTRACT | 61 (48 failures + 13 setup errors) | (a) 30 head-contract nodes: frozen `head == 037` assertions and real-upgrade fixtures that bootstrap tenants then run 037→038 — migration 038's all-tenant preflight **correctly refuses** ("partial or pre-existing SKU-M1 schema detected", fail-closed as designed); (b) 26 legacy-seed nodes: test helpers (`_seed_sku`, `seed_products`, S5A seed) raw-INSERT SKUs without `catalog_product_id` into head-shaped schemas (NOT NULL now enforced), and 3 raw legacy-shaped `order_items` schemas queried by the new ORM (`sellable_unit_id` UndefinedColumn); (c) 2 AST guards forbidding the literal `inventory_repository` in import/intake services — candidate delegates via `InventoryRepository.ensure_stock_row` inside apply only | Baseline differential at `24a28d76` (fresh DB, chain at 037): the same files **229 passed / 0 failed** — green before the candidate; every failing frame is TEST-side seeding/DDL/guard code, none is a product call path |

The 61 stale nodes live in 16 files: `test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py` (27),
`test_phase3_pricing.py` (13), `test_dc12r1_s3_s1_catalog_order_hardening.py` (12),
`test_u3b2_preview_validate.py` (2), and 1 each in `test_dc11d_payment_replay_concurrency_integrity.py`,
`test_dc11t4h_receivable_collection_integrity.py`, `test_dc12r1_s3_s2b_i1_financial_schema_foundation.py`,
`test_dc12r1_s3_s2b_i2a_canonical_payment_service.py`, `test_s5a_fresh_tenant_real_user_journey_gate.py`,
`test_u6f_onboarding_auth_chain_closeout.py`, `test_u6i1_owner_credential_setup_schema.py`.
The candidate did not update these files; that is a **review gap for the CTO to
schedule** (STALE_TEST_CONTRACT repair task), not a runtime product defect.

**Harness transport finding (pre-existing infrastructure):** the runner cannot
bind a full-suite frozen manifest — `ET1_RUNNER_REQUIRED_NODES` carries the whole
node list in ONE environment variable (3803 nodes = 460,335 bytes > kernel
`MAX_ARG_STRLEN` 131,072), so the collect child spawn fails `E2BIG` before any
launch. `authority_runner.py` is untouched by this candidate (not introduced by
8cef1fff). The authority launch therefore used the profile's registered defaults
(9-node fixture manifest — the exact configuration of the only prior phase-4
precedent, `dc12r1-e2-v2 runner-phase4`), and full-suite node-set equality was
proven out-of-band (frozen manifest vs junit set diff = ∅). No authority rerun was
performed after the red verdict; no test was skipped, deselected, xfailed, or
weakened; no product or test file was edited at any point.

## 7. Frontend (Phase 5)

Frozen install `pnpm install --frozen-lockfile` (pnpm 9.15.4) — clean.

| Gate | Result |
|---|---|
| SKU catalog identity tests (`SKUCatalogIdentity.test.tsx` + `.integration.test.tsx`) | **5 passed / 0 failed** |
| SKU list + S5B real-user smoke | **13 passed / 0 failed** |
| Complete suite, run 1 (while a backend pytest ran concurrently) | 399/400 — single `S5BRealUserSmoke` 5000ms timeout (load flake; the same node passed in isolation and in run 2) |
| Complete suite, run 2 (idle machine) | **400 passed / 0 failed (29 files)** |
| TypeScript check (`tsc -p tsconfig.app.json --noEmit`) | clean |
| Production build (`tsc && vite build`) | success in 11.35s (chunk-size warning only) |

No snapshots, mocks, assertions, or dependencies were changed.

## 8. Browser truth (Phase 6) — BLOCKED

- **CATALOG-ID-001: BLOCKED_BY_MISSING_AUTHORITATIVE_SKU_BROWSER_HARNESS.**
- **CATALOG-HIST-001: BLOCKED_BY_MISSING_AUTHORITATIVE_SKU_BROWSER_HARNESS.**
- Exhaustive sweep: no Playwright/Puppeteer spec covers `sellable_unit_id` or any
  catalog-identity journey; the only browser harness in the tree is
  `j1h2b-forgot-reset/` (H2-B/C family — Windows/Zcode property, touching it is
  forbidden); `backend/playwright.config.py` covers no SKU route; `scenarios/`
  contains only SC-001..SC-003 (pre-SKU); both inventory nodes are registered
  `status: NOT_RUN, evidence_sha: ""` with `layer: full_stack`,
  `viewport: desktop-and-mobile-390`.
- Per contract, no browser PASS was improvised. **Desktop and 390px real-browser
  journeys: NOT_EVALUATED.** The 10 required browser coverage points (multi-pack
  product creation, per-unit UUID/stock, `sellable_unit_id` ordering, mismatched/
  cross-tenant UUID rejection, rename/deactivate history stability, hidden
  unavailable products, supported navigation) remain unproven at browser level.
- Backend-level equivalents that DID pass: mismatched UUID/code and cross-tenant
  rejection + RBAC (`test_sku_m1_api_rbac.py`, S4E tenant isolation, U6* gates),
  snapshot immutability (migration + identity tests), all in Phases 2–4.

## 9. Required explicit statements

```
H2-C_NOT_EVALUATED_BY_LUBUNTU
PRICING_NOT_STARTED
ORDER_PRICE_NOT_STARTED
REORDER_NOT_STARTED
```

PRICING/ORDER-PRICE/REORDER remain NOT_STARTED and were neither implemented nor
evaluated; the pricing-safe-orders focused file passed with identity adaptation
only. H2-C sources/tests/harness/evidence were not read for modification, not run,
and not repaired; zero path overlap with the H2-C branch is proven in §2.

## 10. Cleanup proof (post-report)

Task-owned resources destroyed after this report was pushed (verified in the push
commit's host session): containers `sku_v2_lub_pg16` / `sku_v2_lub_redis7` removed
with their volumes; network `sku_v2_lub_net` removed; databases
`test_sku_v2_migr/_authority/_focus_a/_focus_b/_diag/_base` destroyed with their
container; worktrees `dc12r1-mvp-l1-sku-r0m1r1-a2-v2-runtime` and
`/tmp/dc12r1_sku_v2_baseline` removed; venv `.venv-sku-v2` removed; `/tmp/v2_*`
artifacts removed. Host-owner containers (`dc2t0c_*`, prior-round `sku_m1_a5_*`)
were never touched.

## 11. CTO decision items

1. Authorize a separate SKU browser-harness task for CATALOG-ID-001 /
   CATALOG-HIST-001 (desktop + 390px, the 10 coverage points in the task
   directive). Until then, controlled merge of `8cef1fff` stays BLOCKED.
2. Schedule STALE_TEST_CONTRACT repair (61 nodes / 16 files, §6) so the full
   authority suite can reach zero-red independent of environment.
3. Consider a runner fix for full-suite manifest transport (§6 E2BIG) so future
   authorities can bind complete node sets natively.

**Final verdict: STOP_AND_REPORT_CTO_BLOCKED_BY_MISSING_AUTHORITATIVE_SKU_BROWSER_HARNESS**
