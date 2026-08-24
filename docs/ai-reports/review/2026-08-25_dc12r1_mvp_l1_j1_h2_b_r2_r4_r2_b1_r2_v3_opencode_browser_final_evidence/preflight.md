# Provisioning / Runtime Preflight — DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R2-V3

Date: 2026-08-25 (task-local; UTC run 2026-08-24T16:23Z). Operator: OpenCode.
V2 evidence preserved untouched at `3fb185be25b51ae4554c58e8c06c795673c058dd`.

## Phase 1 — Proof gates (all PASS)

- `git fetch --all --prune` done (only unrelated `reports/lubuntu-validation` moved).
- Detached worktree exactly at HARNESS `cb35207969fc1b0c8d8488ac65d75e47fedc3f23`; worktree clean (0).
- `git diff PRODUCT_SOURCE..HEAD`: 22 files, all under `j1h2b-forgot-reset/`; 0 outside → product paths byte-identical.
- Harness = exactly 22 tracked files.
- Frozen refs all resolve unchanged, INCLUDING V2 branch tip == `3fb185be` (remote verified).

## Phase 2 — Provisioning input preflight (all PASS; the V2 fix)

- Identity domain: non-special-use real-TLD subdomain (domain recorded as
  `mail.j1h2b-v3-task.dev`; local parts withheld). Offline probe with the
  candidate backend venv (pydantic 2.12.5, backend
  `schemas.auth_signup.SignupRequest`) accepted it and correctly REJECTED
  `.invalid` / `.test` / `.local` / `localhost` probes (V2 root-cause model
  reproduced and closed).
- All 6 identities (A1 / U / X / W1-owner / W2-owner / M) validated OFFLINE
  through the actual backend schema BEFORE Playwright:
  - `validated_email_count: 6`
  - `all_valid: true`
  - `special_use_domain_count: 0`
  (identity-summary.json; no full email recorded anywhere.)
- Env file properly quoted (V2 invocation-1 defect fixed at generation);
  bash-source → node round-trip proven. All 22 J1H2B_* vars proven non-empty
  with VARIABLE NAMES + booleans only (env-preflight-variables.txt:
  TOTAL=22 MISSING=0; MAILDIR_ROOT_READABLE=true).
- 8 passwords ≥8 chars, distinctness rules (initial≠new≠replay; M
  initial≠new), 6 distinct emails — asserted at generation, values withheld.

## Phase 3 — Fresh exclusive runtime (all PASS)

- New task-owned objects only: containers `j1h2b-v3-pg16` (postgres:16-alpine,
  published 127.0.0.1:55433→5432) and `j1h2b-v3-redis7`
  (redis:7-alpine, published 127.0.0.1:56380→6379), volumes `j1h2b-v3-pgdata` /
  `j1h2b-v3-redisdata`, network `j1h2b-v3-net`; ports 8000/5173/55433/56380
  pre-confirmed FREE; no j1h2b docker residue existed before creation.
- Empty DB `mpango_erp` (0 public tables) → `alembic upgrade head` →
  `037_payment_declarations_schema (head)`; single head.
- Backend: production entry `backend/main.py` (`main:app`) via uvicorn
  127.0.0.1:8000; `MPANGO_ENV=staging`; real JWT with fresh task-random
  SECRET_KEY (64 chars, value never printed/committed); fresh
  REPORTING_USER_PASSWORD (48 chars, withheld); task-private launcher also
  mirrors the non-production email sink into the fresh task maildir
  (README-documented launcher duty; no HTTP surface added, no SQL/ORM).
- Frontend: Vite dev host `http://127.0.0.1:5173` (HMR runtime retained);
  `/api` proxy verified against backend (login probe → 422 backend validation).
- Fresh maildir (0 files at start); no reuse of any V2 data, identity,
  maildir, container, or task directory.

## Phase 4 — Frozen harness gates (all PASS)

| Gate | Result |
|---|---|
| `pnpm install --frozen-lockfile` | PASS (exact pins) |
| `pnpm exec playwright test --list` | PASS — 24 tests / 1 spec, CSV order |
| `node tools/validate-static.mjs` | PASS — 6/6 |
| `pnpm exec tsc --noEmit` | PASS — zero diagnostics |
| `git diff --check` | PASS |
| detect-secrets (21 tracked harness source files) | PASS — 0 findings |
| Health | /health, /health/ready, /health/live all 200; frontend 200 |

Browser binaries: playwright-pinned chromium build v1148 (full + headless
shell) already present on host from V2 infrastructure setup — host-level
browser cache, not V2 task runtime reuse.

PB-1 recheck: retailer forgot-password route still absent, zero
retailerForgotPassword call sites → RT0 stays `BLOCKED_BY_H2_C` (no API bypass).
