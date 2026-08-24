# Provisioning / Runtime Preflight — DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R2-V2

Date: 2026-08-24 (task-local). Operator: OpenCode (ZCode) authorized browser
final run. All commands executed read-only or task-scoped; no product source
modified; no secrets recorded.

## Phase 1 — Proof gates (all PASS)

| Gate | Result | Evidence |
|---|---|---|
| `git fetch --all --prune` | PASS | fetched origin (GitHub lvoemingjie-hash/Mpango-ERP) |
| HARNESS is remote candidate tip | PASS | `cb35207969fc1b0c8d8488ac65d75e47fedc3f23` == tip of `origin/zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r2-app-settle-eol-portability-2026-08-24` |
| `HARNESS^ == e65e9a7f` | PASS | `git rev-parse HARNESS^` → `e65e9a7f61c78906c2c5874d6589d4bada23942c` |
| PRODUCT_SOURCE is HARNESS ancestor | PASS | `git merge-base --is-ancestor 8c462170 cb352079` → 0 |
| Detached worktree at HARNESS | PASS | fresh worktree `_dc12r1_j1h2b_v2_browser_final_2026-08-24`, HEAD == cb352079, `git status --porcelain` empty |
| Product paths byte-identical to PRODUCT_SOURCE | PASS | `git diff --name-only 8c462170 cb352079` lists 22 files, ALL under `j1h2b-forgot-reset/`; 0 files elsewhere (tree-level byte identity for backend/**, frontend/** and all other product paths) |
| Harness exactly 22 files, worktree clean | PASS | `git ls-files j1h2b-forgot-reset` → 22; porcelain 0 |

Frozen refs recorded at start (re-verified at cleanup):
- PRODUCT_SOURCE `8c462170804322d3f73803d8991c00879582e232`
- HARNESS `cb35207969fc1b0c8d8488ac65d75e47fedc3f23`
- KILO_REVIEW `1082f6177af69ce57c1951e07009d0a13f0e2400`
- LUBUNTU_REVIEW_BRANCH_TIP `9066e117`
- BACKEND_ZERO_RED `5570093e`
- PROTECTED_BASELINE `6e9470a1`

## Phase 2 — Fresh exclusive runtime (all PASS)

| Item | Value / Proof |
|---|---|
| Containers | `j1h2b-v2-pg16` postgres:16-alpine, `j1h2b-v2-redis7` redis:7-alpine — task-exclusive names, created fresh this task |
| Volumes | `j1h2b-v2-pgdata`, `j1h2b-v2-redisdata` — fresh, task-exclusive |
| Network | `j1h2b-v2-net` — task-exclusive |
| Bindings | PG published 127.0.0.1:55432, Redis 127.0.0.1:56379, backend 127.0.0.1:8000, frontend 127.0.0.1:5173 — loopback only |
| Ports pre-confirmed free | 8000/5173/55432/56379 checked via netstat before start (all FREE) |
| Empty database | `mpango_erp` — `\dt` returned "Did not find any relations" before migration; 29 public tables after |
| Alembic | empty DB → `alembic upgrade head`; `alembic current` = `037_payment_declarations_schema (head)`; single head (28 revisions, 1 head) |
| Backend | production entry `backend/main.py` (`main:app`) served by uvicorn 127.0.0.1:8000; launcher task-private, adds no HTTP surface; `MPANGO_ENV=staging`; real JWT (random task SECRET_KEY, 64 chars, value never printed/committed/echoed) |
| Frontend | Vite dev host `http://127.0.0.1:5173` (`vite --host 127.0.0.1 --port 5173 --strictPort`), HMR-capable dev runtime per B1-R2; `/api` proxy verified reaching backend (login probe → 422 validation from backend) |
| Maildir | task-private `_dc12r1_j1h2b_v2_browser_final_2026-08-24/maildir`, created empty; launcher dumper mirrors the backend non-production in-memory email sink to maildir text files (README-documented launcher duty; no debug endpoint, no SQL, no ORM) |
| No reuse | fresh DB/identities/maildir/tokens/containers/volumes; no old runtime touched (existing host containers left running untouched) |

## Phase 3 — Frozen harness preflight gates (all PASS, harness dir `j1h2b-forgot-reset/`)

| Gate | Result |
|---|---|
| `pnpm install --frozen-lockfile` | PASS — @playwright/test 1.49.1, @types/node 22.10.5, typescript 5.7.3 exact pins |
| `pnpm exec playwright test --list` | PASS — exactly 24 tests in 1 spec, order == CSV browser rows (F1-D…M1) |
| `node tools/validate-static.mjs` | PASS — 6/6 steps (CSV 29x15 + 24/5; registry; ordered list equality; serial/maxFailures:1/no-sleep/app-settle/no-networkidle + config invariants; .gitattributes LF; UTF-8/no-BOM/no-CR over 22 files) |
| `pnpm exec tsc --noEmit` | PASS — zero diagnostics |
| `git diff --check` (worktree) | PASS — clean |
| detect-secrets (harness source, 21 tracked files excl lockfile) | PASS — 0 findings; pnpm-lock.yaml 7 sha512 integrity-hash false positives only; node_modules findings are third-party content, untracked |
| workers=1 / retries=0 / maxFailures=1 / single serial describe | enforced by frozen playwright.config.ts and re-verified by validator step 4 |
| 24 browser + 5 non-browser = 29 | validator steps 1–2 |

## Runtime health (three checks, protocol §5.4)

- `GET /health` → 200
- `GET /health/ready` → 200
- `GET /health/live` → 200
- frontend `/` and `/login` → 200 (Vite dev host)

## PB-1 recheck (read-only; RT0 remains BLOCKED_BY_H2_C)

- `frontend/src/router/AppRouter.tsx` contains 0 occurrences of
  `retailer/forgot-password` (route still absent)
- `retailerForgotPassword` has 0 call sites in any .tsx
- → RT0 stays `BLOCKED_BY_H2_C`; NO API bypass attempted or permitted.

## Phase 4 — Provisioning boundary contract (how identities enter the run)

- ALL provisioning is performed INSIDE the single authoritative run by the
  frozen harness at point of need, exclusively through official lifecycle/API:
  - A1: `POST /api/v1/auth/signup` → maildir verify link (browser-external
    private read) → `POST /auth/verify-email` → maildir setup link →
    `POST /auth/onboarding/setup-credential` → `POST /auth/login` →
    `POST /auth/select-tenant` (api-client.ts provisionOwner).
  - X (ineligible fixture): `POST /api/v1/users` then soft-delete
    `DELETE /api/v1/users/{id}` as tenant admin (official create + official
    soft-delete; temp password never authenticates).
  - M1: W1/W2 owners via official lifecycle with DIFFERENT emails; shared M
    created in BOTH tenants via `POST /api/v1/users` with the SAME normalized
    email and the SAME initial password P1; formal admin role both sides via
    `PUT /api/v1/users/{id}/roles`; pre-gate asserts M login exposes EXACTLY
    the two expected workspaces (count and names; values withheld).
- No SQL, no direct ORM, no hand-written hashes, no debug endpoints, no DB
  patching, no reuse of old identities is possible: the harness performs none,
  and the launcher adds no HTTP surface beyond the production app.
- API provisioning replaces NO forgot/reset journey action: F1–F2 discovery,
  forgot submit, reset open/submit, logins, replay and M1 dual-context login
  checks are rendered-UI browser actions in the spec.
- Credentials exist ONLY in the task process environment at run time
  (`J1H2B_*` per the frozen README contract); generated per-task, never
  printed, never written to any artifact, maildir, or repo file.

## R6 / M2 references

- R6 (natural expiry) and M2 (partial-copy rollback) remain
  `PRE_GATE_ONLY`: reference accepted backend pre-gate evidence
  `5570093ec7f9e3dc2b4083ac8c091aae75a62d1d` (Lubuntu dual fresh-stack
  literal zero-red final, PASS) — backend-level contracts; NOT browser PASS.
