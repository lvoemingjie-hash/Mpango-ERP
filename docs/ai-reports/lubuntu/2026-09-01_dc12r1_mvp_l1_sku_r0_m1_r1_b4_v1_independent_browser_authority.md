# DC-12R1-MVP-L1-SKU-R0-M1-R1-B4-V1 Lubuntu Independent Browser Authority Final

Date: 2026-09-01

Executor: independent verifier (fresh task-private worktree, infrastructure,
runtime and evidence; no reuse of any B1/B3/B4 author container, database,
Redis data, Maildir, result artifact, browser state or provisioning output).

Source branch:
`codexl/dc12r1-mvp-l1-sku-r0-m1-r1-b4-independent-browser-authority-mode-2026-09-01`

Exact target SHA executed:
`a45fe99eaab73f4949cf4c3e4797626ec5f571cd`

Report branch:
`reports/dc12r1-mvp-l1-sku-r0-m1-r1-b4-v1-lubuntu-independent-browser-authority-2026-09-01`

## Scope Compliance

This was an execution-and-classification task, not a repair task:

- no product, frontend, backend/test or sku-m1-browser edits;
- the only added file is this report;
- H2-C was not evaluated;
- PRICING, ORDER_PRICE and REORDER were not started.

## Pre-Execution Verification (before any execution)

Isolated worktree created detached at the exact target SHA:

```text
git worktree add --detach <task-private-dir> a45fe99eaab73f4949cf4c3e4797626ec5f571cd
HEAD = a45fe99eaab73f4949cf4c3e4797626ec5f571cd   (verified with git rev-parse)
```

Report-only range:

```text
git log --oneline c5215df8..a45fe99e
a45fe99e docs(report): DC-12R1-MVP-L1-SKU-R0-M1-R1-B4 independent browser authority mode
git diff --stat c5215df8..a45fe99e
 ..._m1_r1_b4_independent_browser_authority_mode.md | 457 +++++++++++++++++++++
 1 file changed, 457 insertions(+)   [single docs/ai-reports markdown file]
```

Product-byte identity (B2 authority reuse proof):

```text
git diff 97170e4c..a45fe99e -- backend frontend backend/alembic | wc -l
0
```

Frozen functional browser-byte identity:

```text
git diff 13fd5971..a45fe99e -- \
  sku-m1-browser/tests sku-m1-browser/src/provision.ts sku-m1-browser/provisioning/official.json | wc -l
0
```

All three reference SHAs (`97170e4c`, `13fd5971`, `c5215df8`) resolved as
commits in the candidate repository before execution.

## Fresh Task-Private Infrastructure (loopback only, nothing reused)

```text
PostgreSQL 16: docker dc12r1_b4v1_pg16 (postgres:16-alpine) on 127.0.0.1:17951
               fresh database sku_b4v1_db, fresh non-superuser OWNER role
               (CREATEDB+CREATEROLE required by the real chain: tenant schema
               creation and migration 011 reporting-role creation)
Redis 7:       docker dc12r1_b4v1_redis7 (redis:7-alpine) on 127.0.0.1:17952
               --save "" --appendonly no; DB15 dbsize 0 before the run;
               sentinel 127.0.0.1:26379 verified unreachable
SMTP:          local fake SMTP/Maildir sink (sku-m1-browser/tools/smtp_sink.py)
               on 127.0.0.1:17953, Maildir inside the task results dir
Backend:       fresh uvicorn api.app:app process on 127.0.0.1:17954,
               MPANGO_ENV=production, real SMTP delivery into the local sink
               (EMAIL_PROVIDER=smtp, EMAIL_DELIVERY_MODE=smtp,
               SMTP_STARTTLS=false for the non-TLS local sink);
               fresh venv, pip install -r requirements.txt (fully pinned);
               .env.prod never read; no real SMTP server or mailbox contacted
Frontend:      fresh production build (pnpm install --frozen-lockfile;
               VITE_API_URL=http://127.0.0.1:17954/api/v1 set at build time
               and verified present in the built bundle), served over local
               HTTPS (self-signed loopback certificate) on 127.0.0.1:17955
Browser:       real Chromium via /usr/bin/chromium-browser, fresh profile
Alembic:       the real chain applied from empty through head:
               038_catalog_identity_vertical_slice (parent 037_payment_declarations_schema)
               No manual DDL, create_all, bootstrap repair or schema
               reconciliation was run at any point before assertions.
```

Backend runtime settings were independently confirmed before the run:
`MPANGO_ENV=production`, `EMAIL_PROVIDER=smtp`, `EMAIL_DELIVERY_MODE=smtp`,
`SMTP=127.0.0.1:17953`, `SMTP_STARTTLS=False`, SMTP config complete
(production mode enforces HTTPS `PUBLIC_FRONTEND_URL` and non-default
`DATABASE_URL`/`REDIS_URL`/`SECRET_KEY` at startup).

## Preflight Gates (all GREEN before any browser launch)

```text
Frozen dependency installation:
  frontend  pnpm install --frozen-lockfile       OK
  harness   pnpm install --frozen-lockfile       OK
  backend   fresh venv + pinned requirements.txt OK

TypeScript typecheck:
  npx tsc -p tsconfig.json --noEmit             CLEAN (exit 0)

Read-only list gate (no mode variables set):
  npx playwright test --list
  Total: 4 tests in 2 files  (exactly the four expected executions)
  results/ tree snapshot before == after  (ZERO evidence written)

Static validator (permitted pre-run mode):
  python3 sku-m1-browser/validator/static_validator.py --allow-missing-reconciliation
  STATIC VALIDATOR: GREEN

Reconciliation truth tests:
  python3 sku-m1-browser/validator/reconciliation_truth_tests.py
  RECONCILIATION TRUTH TESTS: PASS  (T01..T21b, incl. both mode directions,
  list read-only in all four mode configurations, zero-runtime-write probes)

Mutation suite:
  python3 sku-m1-browser/validator/mutations.py
  MUTATION SUITE: all 36 mutations RED as intended, pristine and restored
  states GREEN (M01..M36, byte-identical restoration verified per mutation)

Candidate worktree clean after mutation restoration:
  git status --porcelain  -> empty; HEAD still a45fe99e

Secret/artifact scan:
  python3 sku-m1-browser/tools/scan_artifacts.py
  ARTIFACT SCANNER: GREEN (0 findings)
```

No preflight failed, so `VOID_ENVIRONMENT_PRECHECK` did not apply and zero
browser launches happened before the authority invocation.

## Authority Environment

```text
B4_INDEPENDENT_AUTHORITY=1            (exactly one mode variable, literal '1')
B3_AUTHOR_DIAGNOSTIC                  unset (env -u at invocation)
second runtime-mode variable          none present
B1_CANDIDATE_SHA=a45fe99eaab73f4949cf4c3e4797626ec5f571cd
workers=1  retries=0                  (frozen harness config; "Running 4 tests using 1 worker")
no grep, no shard, no repeat-each, no only/skip/xfail, no deselection
```

## Authority Execution — exactly ONE invocation

```text
npx playwright test
Running 4 tests using 1 worker
  ✓  1 [desktop]    › catalog-hist-001.spec.ts:32:5 › CATALOG-HIST-001 (5.2s)
  ✓  2 [desktop]    › catalog-id-001.spec.ts:31:5  › CATALOG-ID-001   (6.8s)
  ✓  3 [mobile-390] › catalog-hist-001.spec.ts:32:5 › CATALOG-HIST-001 (5.1s)
  ✓  4 [mobile-390] › catalog-id-001.spec.ts:31:5  › CATALOG-ID-001   (5.9s)
  4 passed (38.1s)   exit code 0
```

No rerun, no diagnostic replay, no 401 replay, no selector/namespace/data/
wait/assertion change occurred. No browser failure occurred, so no STOP
classification was required.

## PASS Accounting

```text
collected = 4      (authority report observed_execution_count = 4;
                    Playwright JSON stats expected = 4)
passed    = 4      (reconciliation pass = 4)
failed    = 0      (reconciliation fail = 0; Playwright unexpected = 0)
skipped   = 0      (Playwright stats skipped = 0)
flaky     = 0      (Playwright stats flaky = 0)
not_run   = 0      (reconciliation not_run = 0)
duplicates= 0      (reconciliation duplicates = 0)
gap       = 0      (reconciliation gap = 0, errors = [])
authority invocation count = 1
                    (ledger: exactly one start + one end, zero refused)
```

Recorded combinations (all passed, failure_class NO_FAILURE):

```text
CATALOG-ID-001   / desktop     passed
CATALOG-ID-001   / mobile-390  passed
CATALOG-HIST-001 / desktop     passed
CATALOG-HIST-001 / mobile-390  passed
```

Preflight verdict written by the run:

```json
{"outcome": {"kind": "OK"}, "sharedIdentitiesOnly": true}
```

## Required Evidence Binding (all sources independently record)

`execution_mode = INDEPENDENT_AUTHORITY`,
`candidate_sha = a45fe99eaab73f4949cf4c3e4797626ec5f571cd`,
`workers = 1`, `retries = 0`:

```text
live-execution-contract.json  INDEPENDENT_AUTHORITY / a45fe99e… / 1 / 0 /
                              frozen_at_invocation_start=true
invocation-ledger.jsonl       start + end, INDEPENDENT_AUTHORITY / a45fe99e… /
                              workers 1 / retries 0 / expected 4 / observed 4
Playwright report metadata    config.metadata and both project metadata:
                              {"execution_mode":"INDEPENDENT_AUTHORITY",
                               "candidate_sha":"a45fe99e…","workers":1,
                               "retries":0,"actualWorkers":1}
authority-report.json         INDEPENDENT_AUTHORITY / a45fe99e… / 1 / 0 /
                              expected 4 / observed 4 / status passed
reconciliation records        4/4 records stamped INDEPENDENT_AUTHORITY /
                              a45fe99e…; accounting mode_mismatches=0,
                              candidate_sha_mismatches=0
```

The strict validator cross-checks all five sources and exits GREEN:

```text
python3 sku-m1-browser/validator/static_validator.py
STATIC VALIDATOR: GREEN
python3 sku-m1-browser/validator/static_validator.py --require-mode INDEPENDENT_AUTHORITY
STATIC VALIDATOR: GREEN
python3 sku-m1-browser/tools/scan_artifacts.py
ARTIFACT SCANNER: GREEN (9 files scanned, 0 findings)
```

## Functional Observations (no repair performed)

```text
Provisioning flowed exclusively through public API flows; all 5 local sink
emails (2 owner verify + 2 owner setup + 1 retailer setup) were delivered to
the Maildir and consumed by the harness — proof of real production-mode SMTP
delivery into the local fake sink only.
Backend HTTP status census for the whole authority window:
  0 × 401 (no authentication failure of any kind)
  4 × 400 (expected negative paths: mismatched sellable_unit_id/SKU code and
           cross-tenant sellable_unit_id rejections, desktop+mobile)
  2 × 409 (expected negative path: retired SKU-code reuse rejection,
           desktop+mobile)
Zero 5xx responses.
Per-execution namespaces CATID-DESKTOP, CATID-MOBILE-390, CATHIST-DESKTOP,
CATHIST-MOBILE-390 were isolated; no cross-node collision was observed.
```

## Classification

No failure occurred at any gate or during execution:

```text
CURRENT_PRODUCT_DEFECT : none observed
HARNESS_DEFECT         : none observed
ENVIRONMENT_GATED      : none observed
STOP_AND_REPORT_CTO    : not applicable
```

## Backend Authority Reuse

The full backend suite was NOT rerun. B2 backend authority is reused under
the exact product-byte identity proof above
(`git diff 97170e4c..a45fe99e -- backend frontend backend/alembic` = empty),
and independently re-proven in this worktree before execution.

## Required Statements

```text
H2-C_NOT_EVALUATED
B2_BACKEND_AUTHORITY_REUSED_BY_EXACT_PRODUCT_BYTE_IDENTITY
B4_INDEPENDENT_AUTHORITY_EXECUTED
PRICING_NOT_STARTED
ORDER_PRICE_NOT_STARTED
REORDER_NOT_STARTED
```

## Cleanup

After PASS, all task-private infrastructure was removed:

```text
docker containers dc12r1_b4v1_pg16 / dc12r1_b4v1_redis7: removed
docker network dc12r1-b4v1-net: removed
SMTP sink, backend uvicorn and HTTPS frontend processes: stopped
fresh backend venv, node_modules (frontend + harness), frontend dist:
  removed
task results (evidence + Maildir + browser artifacts), task worktree and
temporary task files: removed
loopback ports 17951/17952/17953/17954/17955 released
Evidence is preserved verbatim inside this report.
```

## Verdict

```text
PASS_FOR_CTO_DC12R1_MVP_L1_SKU_R0_M1_R1_B4_V1_LUBUNTU_INDEPENDENT_BROWSER_AUTHORITY_FINAL_READY_FOR_CONTROLLED_MERGE
```
