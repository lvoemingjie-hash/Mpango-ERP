# SKU-M1 Browser Harness — Execution Runbook (B1)

Frozen nodes: `CATALOG-ID-001`, `CATALOG-HIST-001` (each under desktop and
mobile-390 Chromium). This runbook is the handoff for the independent
verifier. This harness is NOT independent final authority; it is the frozen
instrument that task B2 (or the CTO's designated verifier) runs.

## 0. Prerequisites

- Repository checkout at the frozen candidate (see `manifest/frozen-candidate.sha`).
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
npx playwright test --list          # exactly 4 executions (2 nodes x 2 viewports)
python3 validator/static_validator.py --allow-missing-reconciliation   # GREEN
npx tsc -p tsconfig.json --noEmit   # clean
python3 validator/mutations.py      # all 10 mutations RED, restores byte-identical
```

## 6. Browser run (the harness reads everything else from env)

```bash
export B1_CANDIDATE_SHA="$(git rev-parse HEAD)"
export B1_BACKEND_BASE_URL=http://127.0.0.1:<backend-port>
export B1_FRONTEND_BASE_URL=http://127.0.0.1:<frontend-port>
export B1_SMTP_PORT=<smtp-port>
export B1_REDIS_PORT=<redis-port>
export B1_ALEMBIC_VERSIONS_DIR="$PWD/backend/alembic/versions"
export B1_CHROMIUM_EXECUTABLE=/usr/bin/chromium-browser   # or leave unset
npx playwright test                                        # 4 executions
python3 validator/static_validator.py                      # GREEN (reconciliation gap = 0)
python3 tools/scan_artifacts.py                            # GREEN
```

## 7. Fail-closed behavior (what the verifier must observe)

- provisioning data missing/incomplete → `PRECONDITION_FAIL`, 0 browser launches,
  nodes NOT_RUN;
- wrong `B1_CANDIDATE_SHA` → `VOID`, 0 launches;
- alembic head != `038_catalog_identity_vertical_slice` (or parent != 037) → VOID;
- Redis unavailable / DB15 nonempty / wrong DB / sentinel reachable → VOID;
- backend or frontend health red → VOID;
- manifest node missing/extra/duplicated/reordered → static validator RED
  (and STOP before any browser run);
- static gates RED on: skip/fixme/only/retry, API mocking/route fulfillment,
  direct DB seeding, unsupported URL navigation.

## 8. Evidence produced by a run

- `results/playwright-report.json` — per-execution outcomes
- `results/reconciliation.json` — node x viewport accounting (gap must be 0)
- `results/preflight-verdict.json` — preflight classification
- `results/maildir/` — captured local emails (inputs to provisioning)

## 9. Handoff statement

B1 delivers the frozen harness only. The browser verdicts for CATALOG-ID-001 /
CATALOG-HIST-001 become authoritative exclusively through an INDEPENDENT
execution of this runbook by the verifier; B1's own run (if any) is labeled
AUTHOR_DIAGNOSTIC_ONLY.
