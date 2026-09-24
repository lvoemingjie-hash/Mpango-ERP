# DC-12R1-MVP-L1-SKU-R0-M1-R1-B3 Browser Harness Closure

Date: 2026-09-01

Branch: `codexl/dc12r1-mvp-l1-sku-r0-m1-r1-b3-browser-harness-closure-2026-09-01`

Base: `97170e4cba48a3d8cc1e49f383e0cba8131cf08f`

Frozen B3 harness candidate SHA: `13fd597131befc3aaea672f79a5f684f9e818ad6`

## Candidate Scope

Final changed paths from base:

```text
M    sku-m1-browser/README.md
M    sku-m1-browser/inventory/source-path-accounting.md
R100 sku-m1-browser/manifest/frozen-candidate.sha -> sku-m1-browser/manifest/product-base.sha
M    sku-m1-browser/playwright.config.ts
M    sku-m1-browser/provisioning/official.json
A    sku-m1-browser/src/diagnostic-reporter.ts
A    sku-m1-browser/src/fixtures.ts
M    sku-m1-browser/src/global-setup.ts
M    sku-m1-browser/src/preflight.ts
M    sku-m1-browser/src/provision.ts
M    sku-m1-browser/src/reconcile.ts
A    sku-m1-browser/src/runtime.ts
M    sku-m1-browser/tests/catalog-hist-001.spec.ts
M    sku-m1-browser/tests/catalog-id-001.spec.ts
M    sku-m1-browser/validator/mutations.py
A    sku-m1-browser/validator/reconciliation_truth_tests.py
M    sku-m1-browser/validator/static_validator.py
```

Product-byte identity proof:

```text
git diff --name-only 97170e4cba48a3d8cc1e49f383e0cba8131cf08f..13fd597131befc3aaea672f79a5f684f9e818ad6 -- backend frontend backend/alembic | wc -l
0
```

`sku-m1-browser/manifest/product-base.sha` is documented as the historical B1 product base binding (`5c5a9a82a3a2f7f0d5471c38b204e76bac91745e`), not the B3 harness self-identity. Runtime candidate binding came from external execution env `B1_CANDIDATE_SHA` and was compared with live HEAD.

## Static And Mutation Evidence

Typecheck:

```text
pnpm --dir sku-m1-browser typecheck
$ tsc -p tsconfig.json --noEmit
```

Strict validator:

```text
python3 sku-m1-browser/validator/static_validator.py
STATIC VALIDATOR: GREEN
```

Artifact secret scan:

```text
python3 sku-m1-browser/tools/scan_artifacts.py
ARTIFACT SCANNER: GREEN (7 files scanned, 0 findings)
```

Mutation suite:

```text
python3 sku-m1-browser/validator/mutations.py
MUTATION SUITE: all 26 mutations RED as intended, pristine and restored states GREEN
```

Reconciliation truth tests:

```text
python3 sku-m1-browser/validator/reconciliation_truth_tests.py
RECONCILIATION TRUTH TESTS: PASS
```

Truth coverage includes assertion failure recorded as FAIL, duplicate stale record rejection, `--list` read-only behavior, stale runtime cleanup ordering, report/reconciliation disagreement rejection, and second author-diagnostic invocation refusal.

## Fresh Runtime Evidence

Fresh stack:

```text
PostgreSQL 16: sku_b3_pg16 on 127.0.0.1:17760
Redis 7: sku_b3_redis7 on 127.0.0.1:17761, DB15 size 0 before run
Sentinel: 127.0.0.1:26379 unreachable
Backend: real production-mode backend on 127.0.0.1:17743
Frontend: production build served by vite preview on 127.0.0.1:17744
SMTP: local fake SMTP/Maildir on 127.0.0.1:17742
Browser: real Chromium via /usr/bin/chromium-browser
```

Alembic:

```text
alembic current
038_catalog_identity_vertical_slice (head)

revision = "038_catalog_identity_vertical_slice"
down_revision = "037_payment_declarations_schema"
```

Preflight:

```json
{
  "outcome": {
    "kind": "OK"
  },
  "sharedIdentitiesOnly": true
}
```

Single author diagnostic invocation:

```json
{"schema":"sku-m1-browser/invocation-ledger/1","event":"start","mode":"AUTHOR_DIAGNOSTIC","candidate_sha":"13fd597131befc3aaea672f79a5f684f9e818ad6","invocation_count":1,"status":"started","workers":1,"retries":0,"expected_node_count":4,"observed_node_count":0}
{"schema":"sku-m1-browser/invocation-ledger/1","event":"end","mode":"AUTHOR_DIAGNOSTIC","candidate_sha":"13fd597131befc3aaea672f79a5f684f9e818ad6","invocation_count":1,"status":"passed","workers":1,"retries":0,"expected_node_count":4,"observed_node_count":4}
```

Playwright:

```text
B3_AUTHOR_DIAGNOSTIC=1
B1_CANDIDATE_SHA=13fd597131befc3aaea672f79a5f684f9e818ad6
workers=1
retries=0
no grep
no shard
no rerun

4 passed (34.4s)
```

Playwright JSON stats:

```json
{"duration":34436.388,"expected":4,"flaky":0,"skipped":0,"startTime":"2026-09-01T07:29:04.284Z","unexpected":0}
```

Reconciliation accounting:

```json
{"duplicates":0,"fail":0,"gap":0,"not_run":0,"pass":4,"playwright_without_reconciliation":0,"reconciliation_without_playwright":0,"recorded_combinations":4,"report_disagreements":0,"required_combinations":4,"skipped":0,"unknown_nodes":0,"unknown_viewports":0}
```

Recorded combinations:

```text
CATALOG-HIST-001 / desktop      passed
CATALOG-HIST-001 / mobile-390   passed
CATALOG-ID-001 / desktop        passed
CATALOG-ID-001 / mobile-390     passed
```

Functional proof:

```text
CATALOG-ID-001 desktop namespace: CATID-DESKTOP
CATALOG-ID-001 mobile namespace: CATID-MOBILE-390
CATALOG-HIST-001 desktop namespace: CATHIST-DESKTOP
CATALOG-HIST-001 mobile namespace: CATHIST-MOBILE-390
No cross-node namespace collision was observed.
No 401 was observed in backend runtime output.
Only expected negative-path 409 was observed for retired SKU-code reuse rejection.
Every direct Playwright API request is statically guarded for explicit Authorization bearer headers.
Mobile navigation is explicitly opened through the `Toggle navigation menu` button.
Back navigation uses the product's actual accessible button roles.
Unavailable unit absence is asserted through unit-level catalog truth.
Historical order snapshot assertions passed after product rename and package deactivation.
```

Cleanup proof:

```text
docker ps -a filtered for sku_b3/sku-b3: empty
docker network ls filtered for sku-b3-net: empty
ss filtered for 17742/17743/17744/17760/17761: empty
```

## Required Statements

```text
H2-C_NOT_EVALUATED
B2_PRODUCT_BYTES_UNCHANGED
BROWSER_RESULT_AUTHOR_DIAGNOSTIC_ONLY
PRICING_NOT_STARTED
ORDER_PRICE_NOT_STARTED
REORDER_NOT_STARTED
```

Verdict:

```text
PASS_FOR_CTO_DC12R1_MVP_L1_SKU_R0_M1_R1_B3_BROWSER_HARNESS_READY_FOR_INDEPENDENT_AUTHORITY
```
