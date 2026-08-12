# DC-12R1-MVP-R0-R1-R1-V2 — Lubuntu Independent Runtime Final Gate

**Date:** 2026-08-12
**Verdict:** `PASS_DC12R1_MVP_R0_R1_R1_V2_LUBUNTU_INDEPENDENT_FINAL`

**Verifying agent:** Independent runtime gate (opencode, glm-5.2) on a clean Lubuntu host.
**Scope:** Independent validation of the real runtime behavior of WPR-001..004 freeze
candidate `872250ba`. The candidate, the kilo-review ref, protected refs, and all source
were **not** modified, merged, deployed, Playwright-launched, or H7-fixed during this task.

---

## 0. References under review

| Role | Branch | Commit |
|------|--------|--------|
| Baseline | `origin/main` ancestor | `d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f` |
| R0 | parent of candidate | `033797305bcd8407538a89eda9abe621282a8860` |
| **Freeze candidate** | `zcode/dc12r1-mvp-r0-r1-readiness-debt-closure-2026-08-12` | **`872250ba139bdf71404b8415431f8b46bbc8025f`** |
| Kilo review (input) | `reports/dc12r1-mvp-r0-r1-r1-v1-kilo-review-2026-08-12` | `58acb9233556a142f3191094e4e7428a2341fa61` |
| This report | `reports/dc12r1-mvp-r0-r1-r1-v2-lubuntu-independent-final-2026-08-12` | (this commit) |

Isolated full clone under `/home/ivy/dc12r1-v2-gate/repo`; verification performed on a
detached `872250ba` worktree. Host: 4 vCPU / 11 GiB RAM / Docker 29.1.3;
`postgres:16` + `redis:7` images served from the local image cache.

---

## 1. Pre-checks — PASS

- `git fetch --all --prune` on the fresh clone: clean (already complete).
- Remote candidate == `872250ba139bdf71404b8415431f8b46bbc8025f` ✓
- Candidate^ (R0) == `033797305bcd8407538a89eda9abe621282a8860` ✓
- Baseline `d796dcb0` is an ancestor of the candidate (`merge-base --is-ancestor` → yes) ✓
- **R1 increment (R0..candidate) == exactly 3 files, all docs:**
  - `ai-ledger/product-ai/2026-08-12_dc12r1_mvp_r0_r1_readiness_debt_closure.md`
  - `docs/ai/CTO_CURRENT_OPS.md`
  - `docs/ai/PROJECT.md`
- **Baseline→candidate == exactly 16 files** (4 backend src/test, 8 frontend src/test,
  1 new ai-ledger doc, 2 modified docs, 1 new backend module) ✓
- **Forbidden-change scan (deps/lockfile/migration/deploy/path) == 0**:
  no `requirements.txt`, `pyproject.toml`, `poetry.lock`, `setup.sh`, `Dockerfile`,
  `docker-compose*`, `k8s/*`, `alembic/versions/*`, `package.json`, or `pnpm-lock.yaml`
  in the delta; no renames/copies (`-M -C`) ✓
- Protected refs snapshot before vs after: **identical** (§7).

## 2. Python environment — PASS

- Environment built **only** from `backend/pyproject.toml` + `backend/poetry.lock`
  (`poetry install --no-root`, exit 0). Isolated venv outside the repo tree
  (`/home/ivy/dc12r1-v2-gate/artifacts/venvs/...`) so the candidate tree stays clean.
- **Runtime bcrypt == 4.0.1** proven (`import bcrypt; bcrypt.__version__ == '4.0.1'`)
  and `passlib` bcrypt round-trip (hash/verify/reject) succeeds → passlib⇄bcrypt-4.0.1
  interop intact.
- `requirements.txt` (the drifted file) pins `bcrypt==5.0.0` and was **not** used to
  build the env — this is the deferred **H7** drift, intentionally left unfixed per task.
- `requirements.txt`, `pyproject.toml`, `poetry.lock`, `setup.sh` were not modified
  (working-tree diff vs `872250ba` empty throughout).
- `pytest-randomly` is **not** a locked dependency; it was installed into the venv solely
  as a verification-only harness for the Contract D seeded run and fully removed
  (uninstalled + residue directory purged) immediately afterward, leaving the venv
  lock-faithful.

## 3. Backend focus gates — PASS

Run from `backend/`, each a single `pytest` process, no `-k/--ignore/deselect/rerun`,
no skip/xfail increases, no assertion weakening.

| Bundle | Result | Wall |
|--------|--------|------|
| Contract D — natural order (`test_dc12r1_contract_d_statement_print.py`) | **75 passed**, 0 skip/0 xfail | 268.1 s |
| Contract D — `pytest-randomly` seed **3304940527** | **75 passed** (`Using --randomly-seed=3304940527`), 0 skip/0 xfail | 270.7 s |
| Route-authorization + RBAC + auth-regression + S2-login bundle (4 files: `test_route_authorization_policy.py`, `test_rbac_enforcement.py`, `test_auth_regressions.py`, `test_dc12r1_s2_supplier_scoped_retailer_login.py`) | **110 passed**, 0 skip/0 xfail | 76.4 s |

Order-independence of Contract D is proven (natural order and fixed-seed random order
both 75/75 green).

## 4. Two independent full backend gates — PASS

Two mutually independent fresh stacks (each `postgres:16` + `redis:7`,
`max_connections=300`, dedicated ports/volumes/networks, bound to `127.0.0.1`).

- Each DB freshly DROP+CREATE'd; `alembic upgrade head` → **sole head
  `037_payment_declarations_schema`**; `reporting_user`/`reporting_role` created by
  migration `011`.
- **Temp-DB gate correctly configured** (required by the suite's disposable-DB evidence
  tests in `tests/async_test_utils.py`): `MPANGO_ENV=test`,
  `MPANGO_ALLOW_TEMP_DB_CREATE=1`, `TEST_DATABASE_URL` pointing at a `test_*`-named DB
  (matches `^(?:test|pytest|ci)[_-]…$`), and `MPANGO_TEMP_DB_ALLOWED_PORTS` set per stack.
  Test-safe superuser used; the host guard (`127.0.0.1`) and `MPANGO_ENV=test` gate are
  satisfied.
- Each stack ran exactly **one** `pytest` process: `poetry run pytest tests/ -q`
  (a JUnit XML artifact was attached as a report-only output; it does not filter,
  reorder, deselect, or retry any test).

| Stack | Port | Result | failed | errors | Wall | exit |
|-------|------|--------|--------|--------|------|------|
| 1 | pg 54321 / redis 63801 | **3303 passed / 48 skipped / 15 xfailed** | 0 | 0 | 1599.2 s | 0 |
| 2 | pg 54322 / redis 63802 | **3303 passed / 48 skipped / 15 xfailed** | 0 | 0 | 1564.3 s | 0 |

- **Node-set identity (run 1 vs run 2):** the 48 skipped nodeid set, the 15 xfailed
  nodeid set, and the (empty) failure/error nodeid set are **byte-identical** across the
  two runs (`diff` of parsed JUnit sets → no differences).
- **Accounting gap = 0** for both runs: 3303 + 48 + 15 = 3366 = collected total;
  JUnit root `tests=3366, failures=0, errors=0`.
- No splitting, `-k`, `--ignore`, deselect, or failure re-run was used.

> Note: an initial exploratory full run that had NOT yet configured the temp-DB gate
> surfaced 7 failed / 29 errors (all `KeyError: 'TEST_DATABASE_URL'` or
> `MPANGO_ALLOW_TEMP_DB_CREATE=1` assertion) plus 21 extra skips. Root-caused (single
> cause: unconfigured disposable-DB gate, not a candidate defect), the gate env was set,
> and both official runs then returned the exact 3303/48/15. The 4 affected files were
> also re-run in isolation with the corrected env → 79 passed (diagnostic only; the
> official result is the two full `tests/ -q` runs above).

## 5. Frontend gates — PASS

From `frontend/`, using the existing `pnpm-lock.yaml` (`pnpm install --frozen-lockfile`,
exit 0; lockfile not modified).

- **5 named tests — all pass (real collection):**
  | Test | Collected via | Result |
  |------|---------------|--------|
  | `src/tests/permissions.test.ts` | default glob | **23 passed** |
  | `src/tests/DeclarePaymentPage.test.tsx` | default glob | **10 passed** |
  | `src/tests/PrintableWorkspace.test.tsx` | default glob | **78 passed** |
  | `src/tests/StatementPrintWorkspace.test.tsx` | default glob | **45 passed** |
  | `src/router/__tests__/guards.test.tsx` | **explicit config** `--config vite.config.ts` (it lives outside `vitest.config.ts`'s `src/tests/**` glob) | **15 passed** |
- **Full `pnpm vitest run`: 20 files / 291 passed / 0 failed** (69.8 s, exit 0).
- **`pnpm build`: exit 0** (1294 modules transformed, 11.85 s; `dist/` produced;
  `dist/` and `node_modules/` are gitignored → candidate tree unaffected).

**Special proofs (all evidenced by the green tests above, and dynamically by §6):**
- *Missing `client:*` permission → page does not mount + zero protected request:*
  `guards.test.tsx` → "fails closed (redirects to /client) when the permission is
  missing", "denies a retailer holding a DIFFERENT client permission (precision)",
  "denies an unauthenticated (null) user"; `permissions.test.ts` →
  "can() admits a retailer_operator holding `client:payments:declare` and denies one
  without it". `DeclarePaymentPage` is reachable only through `RetailerPermissionRoute`,
  so without permission the page never mounts → zero requests.
- *Missing `client:payments:declare` → zero POST:* enforced by the guard + the
  `can()` precision tests; `DeclarePaymentPage` idempotency tests start from an
  authenticated, permissioned state and assert exact POST counts.
- *Malicious backend body / `Error.message` kept out of the DOM:* `DeclarePaymentPage`
  → "never renders the backend body message / code / schema / internal id on a 409",
  "shows the fixed neutral 409 copy (status-derived), not the backend message",
  "never renders the raw `Error.message` on a network/timeout failure".
- *Idempotency key reused on failure, rotated only after success:* `DeclarePaymentPage`
  → "reuses the same idempotency key when the first request fails and the user retries",
  "rotates the idempotency key only after a successful submission",
  "prevents duplicate in-flight submissions on rapid double-submit".
- *Supplier/client statement mapper parity (state, code, message identical):* backend
  Contract D `test_supplier_and_client_mapping_are_identical[…]` (code+message
  byte-for-byte) and `test_end_to_end_parity_invalid_date_range_both_routes`
  (identical 400 `INVALID_DATE_RANGE` on both routes); frontend
  `StatementPrintWorkspace.test.tsx` (45) mirrors the same contract.

## 6. Mutation authenticity — PASS (RED→restore→GREEN, all restored)

Three minimal, fully-reversed mutations. After each restore the relevant suite returned
to GREEN; the final working tree is byte-identical to `872250ba`.

| # | Mutation (temporary) | Test that went RED | RED result | After restore |
|---|----------------------|--------------------|-----------|---------------|
| 1 | `frontend/src/router/guards.tsx` `RetailerPermissionRoute` guard neutered (`if (!can(...))` → `if (false)`) | `guards.test.tsx` "fails closed … permission missing", "denies DIFFERENT permission", "denies unauthenticated" | **3 failed / 12 passed** (exit 1) | 15 passed |
| 2 | `frontend/src/pages/client/DeclarePaymentPage.tsx` error set to backend `data.message` instead of `neutralDeclarationError(err)` | `DeclarePaymentPage.test.tsx` "never renders the backend body message … on a 409", "shows the fixed neutral 409 copy …" | **2 failed / 8 passed** (exit 1) | 10 passed |
| 3 | `backend/api/v1/statements.py` (supplier) rebound `map_statement_result` to a drifted wrapper (range→409 `DRIFTED`) — one-sided | Contract D `test_supplier_and_client_mapping_are_identical[range]` (+ supplier detail assertion) | **2 failed / 16 passed** (exit 1) | 18 passed |

**Final tree integrity:** `git diff --stat HEAD` empty; `HEAD^{tree}` ==
`09ef7ebf481280b56be11e215f6a2a135c7692ce` (the candidate's tree) — working tree
byte-identical to `872250ba`. (One transient change observed earlier was a generated
Hypothesis cache file `backend/.hypothesis/.../codec-utf-8.json.gz`, restored via
`git checkout` — not a source file.)

## 7. Quality & ref integrity — PASS

- `python3 -m compileall` over backend source/tests → exit 0.
- `git diff --check d796dcb0 872250ba` → clean (no whitespace/conflict-marker issues).
- Scoped `pre-commit run --files <16 delta files>` → trailing-whitespace, end-of-file,
  large-files, detect-secrets all **Passed** (check-yaml N/A — no YAML in delta); exit 0;
  no files modified.
- `detect-secrets scan` over the 16 delta files → **0 findings**.
- UTF-8/mojibake: all 16 files valid UTF-8, no BOM, no U+FFFD replacement chars.
- GitNexus analyze/status: **N/A** — no runnable `gitnexus` CLI is installed on this host
  (only the `GitNexus/` docs checkout and `~/.gitnexus/registry.json` exist).
- **Protected refs unchanged:** `refs_before.txt` == `refs_after.txt` (candidate, kilo,
  and `origin/main` object names identical before and after the task).

## 8. Accounting summary

| Gate | Expected | Observed | Gap |
|------|----------|----------|-----|
| Contract D natural | 75 passed | 75 passed | 0 |
| Contract D seeded 3304940527 | 75 passed | 75 passed | 0 |
| Route/RBAC/auth/S2 bundle | 110 passed | 110 passed | 0 |
| Full backend ×2 | 3303/48/15, 0 fail/err | 3303/48/15, 0 fail/err (both) | 0 |
| Full vitest | 291 passed / 0 failed | 291 passed / 0 failed | 0 |
| pnpm build | exit 0 | exit 0 | 0 |
| delta files | 16 (3 docs in R1) | 16 (3 docs in R1) | 0 |
| forbidden changes | 0 | 0 | 0 |

Accounting gap = 0 across every gate.

## 9. Cleanup

At task end all verification harness is purged: both docker-compose projects
(`dc12r1v2s1`, `dc12r1v2s2`) brought `down -v` (containers, volumes, networks removed),
the `test_mpango` databases and any disposable `test_*` DBs dropped, the isolated clone
and poetry venv removed, and `/tmp/opencode/dc12r1-v2-gate/` logs/artifacts cleared. No
worktree, mutation, container, volume, network, or log residue remains on the host. The
only artifact retained is this report on its dedicated report branch.

## 10. Deferred / non-blocking observations (not part of the verdict)

- **H7 (deferred, per task):** `backend/requirements.txt` drifts to `bcrypt==5.0.0`
  (incompatible with `passlib` 1.7.4) while `poetry.lock` correctly pins `4.0.1`. Left
  unfixed; the verification environment was built exclusively from the lockfile.
- `pytest-randomly` is not a locked dev dependency; the seeded Contract D order-proof
  used it as a verification-only plugin (added then removed). No candidate file changed.
- `backend/test_s2_*.py` and several modules emit `datetime.utcnow()` /
  `pytest.mark.asyncio`-on-sync deprecation warnings; none affect outcomes (0 fail/err).

---

**Verdict:** `PASS_DC12R1_MVP_R0_R1_R1_V2_LUBUNTU_INDEPENDENT_FINAL`
