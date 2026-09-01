# SKU-M1 Browser Harness — Execution Runbook (B3 + B4 authority modes)

Frozen nodes: `CATALOG-ID-001`, `CATALOG-HIST-001` (each under desktop and
mobile-390 Chromium). This runbook is the handoff for the independent verifier.

The harness supports EXACTLY two mutually exclusive runtime modes. Both run the
identical frozen journey bodies; only the recorded authority label differs.

| mode                  | select with                  | meaning                                    |
| --------------------- | ---------------------------- | ------------------------------------------ |
| `AUTHOR_DIAGNOSTIC`   | `B3_AUTHOR_DIAGNOSTIC=1`     | author evidence; never independent         |
| `INDEPENDENT_AUTHORITY` | `B4_INDEPENDENT_AUTHORITY=1` | independent verifier authority evidence    |

Mode rules (all fail closed **before** any browser launch):

- exactly one mode variable must equal the literal string `1`;
- neither set -> fail closed;
- both set -> fail closed;
- any other value (for example `B4_INDEPENDENT_AUTHORITY=YES`) -> unknown mode,
  fail closed;
- an unknown mode label inside any evidence file -> fail closed;
- `--list` ignores BOTH mode variables, writes nothing, and stays read-only;
- after an invocation starts the mode is FROZEN in
  `results/live-execution-contract.json`; no environment variable can relabel or
  override it.

Invocation accounting (append-only `results/invocation-ledger.jsonl`):

- one fresh task worktree / results directory permits exactly ONE runtime
  invocation for its selected mode;
- a second start in the same mode -> refused;
- `AUTHOR_DIAGNOSTIC` -> `INDEPENDENT_AUTHORITY` (or the reverse) in one
  worktree/results directory -> refused;
- a ledger holding evidence for another candidate SHA -> VOID before launch.

## 0. Prerequisites

- Repository checkout at the committed B3 harness candidate SHA supplied by
  the external execution contract through `B1_CANDIDATE_SHA`.
- `manifest/product-base.sha` is the historical product-code base used for
  product-byte identity proof. It is not a B3 harness self-binding and must not
  be treated as the final B3 candidate SHA.
- Docker (for PG16 + Redis 7) or equivalent fresh instances.
- Node 22+, pnpm 9 (frozen installs), Python 3.12 (stdlib-only tools).
- System Chromium, or set `B1_CHROMIUM_EXECUTABLE` (e.g. `/usr/bin/chromium-browser`).

## 1. Infrastructure (fresh, loopback-only)

```bash
docker network create sku-b1-net
docker run -d --name sku_b1_pg16 --network sku-b1-net \
  -e POSTGRES_PASSWORD='<pg-password>' -e POSTGRES_USER=postgres -e POSTGRES_DB=postgres \
  -p 127.0.0.1:<pg-port>:5432 postgres:16-alpine
docker run -d --name sku_b1_redis7 --network sku-b1-net \
  -p 127.0.0.1:<redis-port>:6379 redis:7-alpine --save "" --appendonly no
# non-superuser CREATEDB role; create the backend database; apply alembic to head:
cd backend && DATABASE_URL=... alembic upgrade head   # must reach 038_catalog_identity_vertical_slice
```

## 2. Local SMTP sink (maildir — no production email)

```bash
python3 sku-m1-browser/tools/smtp_sink.py --port <smtp-port> \
  --maildir sku-m1-browser/results/maildir
```

## 3. Backend (real process, dev_sink-free SMTP)

```bash
cd backend
DATABASE_URL=... REDIS_URL=redis://127.0.0.1:<redis-port>/15 \
SMTP_HOST=127.0.0.1 SMTP_PORT=<smtp-port> EMAIL_PROVIDER=smtp EMAIL_DELIVERY_MODE=smtp \
EMAIL_FROM='b1@skum1browser.invalid' PUBLIC_FRONTEND_URL=http://127.0.0.1:<frontend-port> \
MPANGO_ENV=test REPORTING_USER_PASSWORD=... \
<venv>/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port <backend-port>
```

## 4. Production-built frontend (real process)

```bash
cd frontend && pnpm install --frozen-lockfile && pnpm build
# serve dist/ on <frontend-port> (vite preview --port <frontend-port> --strictPort)
```

## 5. Harness frozen install + author gates

```bash
cd sku-m1-browser
pnpm install --frozen-lockfile
npx playwright test --list          # read-only; exactly 4 executions listed
python3 validator/static_validator.py --allow-missing-reconciliation   # GREEN
npx tsc -p tsconfig.json --noEmit   # clean
python3 validator/mutations.py      # all 36 mutations RED, restores byte-identical
python3 validator/reconciliation_truth_tests.py
```

`python3 validator/static_validator.py --require-mode INDEPENDENT_AUTHORITY`
additionally requires every evidence source (invocation ledger, live execution
contract, authority report, Playwright report metadata, reconciliation records)
to carry `INDEPENDENT_AUTHORITY`; author evidence is RED under it, and vice
versa with `--require-mode AUTHOR_DIAGNOSTIC`.

## 6. Browser run (the harness reads everything else from env)

Select EXACTLY ONE mode. For independent authority evidence use
`B4_INDEPENDENT_AUTHORITY=1` in a FRESH worktree (the invocation ledger permits
one invocation per worktree/results directory).

```bash
export B1_CANDIDATE_SHA="$(git rev-parse HEAD)"
# author diagnostic evidence (author only):
export B3_AUTHOR_DIAGNOSTIC=1
# OR independent authority evidence (verifier): export B4_INDEPENDENT_AUTHORITY=1
export B1_BACKEND_BASE_URL=http://127.0.0.1:<backend-port>
export B1_FRONTEND_BASE_URL=http://127.0.0.1:<frontend-port>
export B1_SMTP_PORT=<smtp-port>
export B1_REDIS_PORT=<redis-port>
export B1_ALEMBIC_VERSIONS_DIR="$PWD/backend/alembic/versions"
export B1_CHROMIUM_EXECUTABLE=/usr/bin/chromium-browser   # or leave unset
npx playwright test                                        # exactly one invocation; 4 executions
python3 validator/static_validator.py                      # GREEN (reconciliation gap = 0)
python3 validator/static_validator.py --require-mode <MODE_USED>   # GREEN
python3 tools/scan_artifacts.py                            # GREEN
```

## 7. Fail-closed behavior (what the verifier must observe)

- provisioning data missing/incomplete → `PRECONDITION_FAIL`, 0 browser launches,
  nodes NOT_RUN;
- wrong `B1_CANDIDATE_SHA` → `VOID`, 0 launches;
- alembic head != `038_catalog_identity_vertical_slice` (or parent != 037) → VOID;
- Redis unavailable / DB15 nonempty / wrong DB / sentinel reachable → VOID;
- backend or frontend health red → VOID;
- no mode variable, both mode variables, or a non-`1` mode value → fail-closed
  before runtime writes (config load, zero browser launches);
- second invocation in the same mode → refused in the append-only ledger;
- mode switch inside one worktree/results directory → refused
  (`cross_mode_invocation_refused`);
- ledger evidence for another candidate SHA → `candidate_sha_mismatch_void`;
- mode or candidate SHA disagreement between the invocation ledger, the live
  execution contract, the authority report, the Playwright report metadata and
  the reconciliation records → reconciliation gap/error and nonzero exit;
- manifest node missing/extra/duplicated/reordered → static validator RED
  (and STOP before any browser run);
- static gates RED on: skip/fixme/only/retry, API mocking/route fulfillment,
  direct DB seeding, unsupported URL navigation.

## 8. Evidence produced by a run

- `results/playwright-report.json` — per-execution outcomes; `config.projects[*].metadata`
  carries the execution mode and candidate SHA actually launched
- `results/reconciliation-in.jsonl` — centralized fixture records, one per execution
  (each stamped with the recorded mode and candidate SHA)
- `results/reconciliation.json` — node x viewport accounting (gap must be 0)
- `results/invocation-ledger.jsonl` — append-only invocation ledger
- `results/live-execution-contract.json` — the frozen mode/candidate SHA/workers/retries
  binding written at invocation start
- `results/authority-report.json` — mode-neutral authority report: execution mode,
  candidate SHA, workers=1, retries=0, expected/observed counts, and per-execution
  node / viewport / status / sanitized failure class
- `results/preflight-verdict.json` — preflight classification
- `results/maildir/` — captured local emails (inputs to provisioning)

All five evidence sources must agree on ONE execution mode and ONE candidate
SHA; any disagreement is a gap/error and exits nonzero.

## 9. Handoff statement

B3 delivered the repaired browser harness. B4 adds the real, fail-closed
`INDEPENDENT_AUTHORITY` runtime mode to the same frozen journeys.

Report correction: B3's functional author-diagnostic result 4/4 remains valid
and its evidence is untouched, but its
`READY_FOR_INDEPENDENT_AUTHORITY` claim was premature — under B3 no independent
runtime mode existed, so an independent verifier could not have produced
independently labeled authority evidence. Historical B3 evidence is not
rewritten.

The browser verdicts for CATALOG-ID-001 / CATALOG-HIST-001 become authoritative
exclusively through an `INDEPENDENT_AUTHORITY` execution of this runbook by the
verifier. Author evidence can never be relabeled independent; independent
evidence requires `B4_INDEPENDENT_AUTHORITY=1`.
