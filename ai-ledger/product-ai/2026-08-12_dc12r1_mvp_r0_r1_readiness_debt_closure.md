# DC-12R1-MVP-R0-R1 — P2/P3 Readiness Debt Closure (KILO-WPR-001..004)

> Isolated branch: `zcode/dc12r1-mvp-r0-r1-readiness-debt-closure-2026-08-12`
> Base: `origin/product-dev-recovered@d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f`
> Objective: close four readiness-debt items **without** changing backend
> authorization, financial semantics, migrations, or deployment.

## 0 Verdict Summary

| Dimension | Result |
|---|---|
| Base / lineage | ✅ branch created from `d796dcb0`; `adcc7f28` verified as an ancestor (descends-from confirmed); clean isolated worktree |
| Scope discipline | ✅ Exactly 14 modified + 1 new (`statement_http.py`) + this ledger = **16 files**, all on the allowed list; zero migration/seed/permission-registry/backend-RBAC/financial/lockfile/deployment changes |
| WPR-001 baseline truth | ✅ `d796dcb0` (current protected tip) distinguished from `adcc7f28` (accepted merge/ancestor); zero remaining `@adcc7f28` implies-tip wording; historical merge records preserved; post-merge SHA-sync note added |
| WPR-002 permission-aligned client routes | ✅ canonical `CLIENT_PERMISSIONS` (six `client:*` codes, 036 seed + 037 rename); reusable `RetailerPermissionRoute` reusing `can()`; 5 client print/declare routes admission-checked; `RetailerRoute` stays role-only; fail-closed before render + before any protected GET |
| WPR-003 declaration route + neutral error | ✅ `client:payments:declare` gate on the declare route; idempotency contract unchanged (same key on failure / rotate on success); `response.data.message`/`Error.message` rendering replaced with fixed status-derived public copy; malicious backend payload proven to never reach the UI; zero declaration POSTs when permission missing |
| WPR-004 Contract D mapper de-dup | ✅ ONE shared `backend/api/v1/statement_http.map_statement_result`; supplier + retailer routes call it; every status/code/message preserved exactly; supplier/client parity tests + mutation evidence (one-sided drift → RED) |
| Backend gates | ✅ Contract D focused 75/75 natural + 75/75 randomized (seed 3304940527); RBAC/route-auth regression 110/110; full `pytest tests/` on two independent fresh PG16+Redis7 stacks: **identical totals, 0 failed / 0 errors** (see §6) |
| Frontend gates | ✅ focused suites green (permissions 23, guards 15, DeclarePaymentPage 10, PrintableWorkspace 78, StatementPrintWorkspace 45); full `pnpm vitest run` **291/0**; `pnpm build` exit 0 |
| Static / integrity | ✅ `py_compile` clean (4 backend files); `git diff --check` clean; detect-secrets 0 new (baseline-scoped); mojibake/encoding clean; no skip/xfail/deselect/assert-weakening |
| Verdict | **PASS_FOR_CTO_DC12R1_MVP_R0_R1_MERGE_REVIEW** |

---

## 1 Objective

Close four Kilo-raised P2/P3 readiness-debt items on the protected baseline
without touching backend authorization, financial semantics, migrations, or
deployment:

- **KILO-WPR-001** — baseline truth: distinguish current protected SHA `d796dcb0`
  from accepted product-code merge `adcc7f28`; remove wording claiming the
  protected branch currently points at `adcc7f28`; update agent/task baselines to
  `d796dcb0`; note CTO post-merge final-SHA sync.
- **KILO-WPR-002** — permission-aligned client route admission: reuse
  `frontend/src/utils/permissions.ts` `can()`; add canonical `CLIENT_PERMISSIONS`
  matching the six backend `retailer_operator` permissions; add a reusable
  `RetailerPermissionRoute`; keep `RetailerRoute` role/boundary-only.
- **KILO-WPR-003** — declaration route + neutral error contract: require
  `client:payments:declare` before the declaration page; preserve the idempotency
  contract; replace backend-body rendering with fixed status-derived public copy;
  prove missing permission → zero declaration POSTs.
- **KILO-WPR-004** — Contract D mapper duplication: extract ONE shared API-layer
  `StatementResult→HTTP` mapper; supplier and retailer routes both call it;
  preserve every status/code/message; add parity tests + mutation evidence.

## 2 Lineage / baseline truth

- `origin/product-dev-recovered` == `d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f`
  (the documented current protected tip; the SHA this branch was created from).
- `adcc7f281c661897ad050a8278686375b611edb5` resolves as the accepted Contract D
  product-code merge.
- Ancestry verified: `git merge-base --is-ancestor adcc7f28 d796dcb0` → **YES**
  (`d796dcb0` descends from `adcc7f28`; exactly 2 commits ahead). The accepted
  merge is contained in the current tip history; it is **not** the tip itself.
- The branch was created clean from `d796dcb0`; no protected refs were pushed or
  merged.

## 3 What changed (WPR-001..004)

### WPR-001 — docs/ai baseline truth
- `docs/ai/PROJECT.md` + `docs/ai/CTO_CURRENT_OPS.md`: added an explicit
  **Current protected branch tip** (`d796dcb0`) header field distinct from the
  **Accepted product code merge** (`adcc7f28`); rewrote the only `@adcc7f28`
  implies-current-tip table/truth line to `@d796dcb0` with the descends-from
  note; updated the agent worktree baseline to `@d796dcb0`; rewrote the stale
  "does not descend from `adcc7f28`" stop condition to the reconciled, verified
  state; added the CTO post-merge final-SHA sync note.
- Verified: zero remaining `@adcc7f28` references; all historical "Merged as
  `adcc7f28`" records preserved untouched (they are factual merge records, not
  current-tip claims).

### WPR-002 — permission-aligned client routes (frontend)
- `frontend/src/utils/permissions.ts`: added canonical `CLIENT_PERMISSIONS`
  (`CATALOG_READ`, `ORDERS_READ`, `ORDERS_CREATE`, `PAYMENTS_READ`,
  `PAYMENTS_DECLARE`, `FINANCE_READ`) + `ALL_CLIENT_PERMISSIONS`; the stale
  `client:payments:create` is explicitly absent (037 rename).
- `frontend/src/router/guards.tsx`: added `RetailerPermissionRoute({permission})`
  reusing `can()` (no independent permission algorithm); fails closed to
  `/client` before the child page renders; `RetailerRoute` left role-only.
- `frontend/src/router/AppRouter.tsx`: wrapped the five guarded client routes in
  four permission groups matching their backend `RequirePermission` exactly:
  - `/client/orders/:orderId/print` → `client:orders:read`
  - `/client/declarations/:declarationId/print` + `.../receipt` → `client:payments:read`
  - `/client/statements/print` → `client:finance:read`
  - `/client/orders/:orderId/declare` → `client:payments:declare` (WPR-003)

### WPR-003 — declaration route + neutral error (frontend)
- `frontend/src/pages/client/DeclarePaymentPage.tsx`: replaced
  `response.data.message` / `Error.message` rendering with a local
  `neutralDeclarationError(err)` that consults **only** the coarse HTTP status
  (modelled on the existing `sanitizePrintError` contract); never reads the body,
  code, schema, internal id, or raw exception. Idempotency contract unchanged
  (same key on failure; rotate only on success — the catch block keeps the key).

### WPR-004 — shared Contract D mapper (backend)
- `backend/api/v1/statement_http.py` (NEW): one `map_statement_result(res)` that
  maps `StatementResult` → `StatementPrintView` or raises the precise
  `HTTPException` (status + `{code,message}` detail) for every variant.
- `backend/api/v1/statements.py` (supplier) and `backend/api/v1/client/statements.py`
  (retailer): both now `from api.v1.statement_http import map_statement_result` and
  call it; the two private `_map_statement_result` copies were removed. The route
  pre-validation (`StatementPeriodError`/`parse_statement_date_range`) and
  `RequirePermission` decorators are unchanged.

## 4 Impact analysis (before edit, every changed symbol)

GitNexus CLI was not on PATH in this worktree; an equivalent static dependant
search was performed instead and recorded:
- `_map_statement_result` — only self-referential in the two route files; **no**
  test or external module imported it → relocating to `statement_http.py` breaks
  nothing. Verified zero references in `backend/tests/`.
- `StatementResult` / `build_statement_print` — importers limited to the two
  route files + the Contract D test (which imports `build_statement_print` only,
  unaffected).
- `RetailerRoute` — AppRouter + one portal test (unchanged behavior).
- `can` — 3 import sites (reused, not modified).
- `DeclarePaymentPage` / `submitDeclaration` — AppRouter + the declaration test.
- No test imported the removed private mapper, so the rename is import-safe.

## 5 RED/GREEN evidence

- **permissions=[] admits before / denies after (WPR-002 RED→GREEN):** the
  existing retailer ALLOW matrices in `PrintableWorkspace` / `StatementPrintWorkspace`
  previously used `permissions:[]` and admitted; after the guard they would be
  denied, so the matrices now use a permitted fixture, and new
  `WPR-002 — ... denied for permissions=[]` blocks prove each client print route
  is denied (no document testid, zero print-data GET, zero writes).
- **Each missing `client:*` permission independently denies its exact route
  (precision):** a retailer holding all six client permissions except the one a
  route requires is denied that route only.
- **Missing `client:payments:declare` → zero declaration POSTs (WPR-003):**
  AppRouter-level test proves the declare form never mounts (button absent) and
  `api.post` is never called for a permission-empty retailer.
- **Malicious backend message never in the UI (WPR-003):** a 409 carrying
  `SQLSTATE … schema=public tenant_user_id=… raw: ERROR …` is rendered as the
  fixed neutral 409 copy; every fragment of the payload is asserted absent, and a
  network/timeout `Error.message` is likewise not leaked.
- **Permitted routes remain GREEN:** the ALLOW matrices (permitted retailer) and
  the existing idempotency tests stay green.
- **Mapper parity (WPR-004):** identity (both routes reference the same
  callable), byte-contract table (every variant → exact status/code/message),
  supplier/client parity (identical HTTPException for the same result), and
  mutation evidence (a drifted mapper provably disagrees with the shared one for
  `StatementRangeTooLarge`, so a one-sided drift turns the parity test RED).

## 6 Backend gate evidence

- **Contract D focused suite** (`tests/test_dc12r1_contract_d_statement_print.py`):
  - natural order (`-p no:randomly`): **75 passed**, 0 failed, 0 errors.
  - randomized order (`-p randomly`, seed `3304940527`): **75 passed**, 0 failed.
- **RBAC / route-authorization regression**
  (`test_route_authorization_policy.py`, `test_rbac_enforcement.py`,
  `test_auth_regressions.py`, `test_dc12r1_s2_supplier_scoped_retailer_login.py`):
  **110 passed**, 0 failed.
- **Two full `pytest tests/` runs on independent fresh PG16+Redis7 stacks**
  (stack1 `contractd_pg16:5433`/`contractd_redis7:6380`; stack2
  `contractd_pg16_run2:5434`/`contractd_redis7_run2:6381`; `-p no:randomly`):

  | Metric | Run 1 (stack1) | Run 2 (stack2) |
  |---|---:|---:|
  | Passed | 3303 | 3303 |
  | Skipped | 48 | 48 |
  | XFailed | 15 | 15 |
  | Failed | 0 | 0 |
  | Errors | 0 | 0 |

  Totals are identical across the two independent stacks with **0 failed / 0
  errors** (3285 prior baseline + 18 new WPR-004 tests = 3303).

### Test-environment note (disclosed, not a code change)
The full-suite gate was run with `bcrypt==4.0.1` (the version `pyproject.toml`
documents as compatible with `passlib 1.7.4` — its comment states passlib 1.7.4
is incompatible with bcrypt ≥ 4.1's strict 72-byte enforcement). The shipped
`requirements.txt` carries a pre-existing drifted `bcrypt==5.0.0` pin that breaks
password hashing; this drift predates this slice and is **out of scope** (no
dependency/lockfile changes are permitted). The disposable test DBs are named
`test_mpango` (matching the `tests/async_test_utils.py` `^(?:test|…)[_-]…`
temp-DB source contract) owned by the test-safe `mpango_test` superuser; the
main `mpango_test` user is rejected by the temp-DB guard (`user is not
test-safe`). None of these are repository changes.

## 7 Frontend gate evidence

- Focused suites (collected by `pnpm vitest run`): `permissions.test.ts` 23/23;
  `DeclarePaymentPage.test.tsx` 10/10; `PrintableWorkspace.test.tsx` 78/78
  (incl. 11 new WPR tests); `StatementPrintWorkspace.test.tsx` 45/45 (incl. 2 new
  WPR tests).
- `frontend/src/router/__tests__/guards.test.tsx` 15/15 (verified via a temporary
  collect-config; this file is outside the default `src/tests/**` include glob —
  a pre-existing condition affecting the whole file — so the collected
  RetailerPermissionRoute evidence is the AppRouter matrices above).
- Full `pnpm vitest run`: **20 files, 291 passed, 0 failed** (was 270; +21 new
  collected tests). `pnpm build` (tsc + vite): **exit 0**.

## 8 Static / integrity gates

- `python -m py_compile` clean: `statement_http.py`, `statements.py`,
  `client/statements.py`, `test_dc12r1_contract_d_statement_print.py`.
- `git diff --check`: clean (no whitespace errors).
- `detect-secrets-hook --baseline .secrets.baseline` on all 15 changed files:
  exit 0 (no new secrets).
- Mojibake / UTF-8 validity scan on all 15 changed text files: clean.
- No `skip`/`xfail`/deselect/timeout-increase/assertion-weakening introduced —
  only additive tests.

## 9 Scope / exclusions honored

No migration, schema, permission-registry, seed/bootstrap, or backend RBAC
change. No financial/payment/ledger/receivable/order mutation change. No
dependency, lockfile, Playwright, deployment, or VPS change. No S3-S3, I2C-I3,
SMS/WhatsApp, PDF/QR, or provider work. No protected push or merge. Only the
isolated source branch is pushed.

## 10 After push: STOP

After the isolated branch is pushed and the SHA frozen, **STOP**. Await Kilo
review, Lubuntu verification, and CTO merge. Do not begin Playwright or local
deployment.
