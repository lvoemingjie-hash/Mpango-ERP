# DC-12R1-MVP-R0-R1-R1-V1 Kilo adversarial final review

**Verdict:** `PASS_FOR_CTO_DC12R1_MVP_R0_R1_R1_V1_KILO_FINAL_REVIEW`

## 0. Scope and evidence mode

- Review mode: independent adversarial source, test-authenticity, and evidence-consistency review.
- Candidate branch reviewed: `origin/zcode/dc12r1-mvp-r0-r1-readiness-debt-closure-2026-08-12`
- Baseline: `d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f`
- Frozen R0: `033797305bcd8407538a89eda9abe621282a8860`
- Frozen candidate: `872250ba139bdf71404b8415431f8b46bbc8025f`
- No candidate source was modified during this review.

Evidence labels used below:

- **EXECUTED** — run independently on this host.
- **STATIC** — verified from source.
- **GITNEXUS** — verified from `analyze/status/context/impact/query`.
- **HISTORICAL-AUTH** — reconciled against current source/diff.
- **ENV-GATED** — not available on this host; not fabricated.

## 1. SHA, lineage, and scope

### 1.1 Exact SHA proof — EXECUTED

- `git rev-parse origin/zcode/dc12r1-mvp-r0-r1-readiness-debt-closure-2026-08-12` -> `872250ba139bdf71404b8415431f8b46bbc8025f`
- `git rev-parse 872250ba139bdf71404b8415431f8b46bbc8025f` -> exact
- `git rev-parse 033797305bcd8407538a89eda9abe621282a8860` -> exact
- `git rev-list --parents -n 1 872250ba139bdf71404b8415431f8b46bbc8025f` -> candidate parent is exactly `033797305bcd8407538a89eda9abe621282a8860`
- `git merge-base --is-ancestor d796dcb0d8ecc4ddffc2f82a67e90170c9cdb60f 872250ba139bdf71404b8415431f8b46bbc8025f` -> exit `0`

### 1.2 R1 incremental scope — EXECUTED

`git diff --name-only 03379730..872250ba` returned exactly three files:

1. `ai-ledger/product-ai/2026-08-12_dc12r1_mvp_r0_r1_readiness_debt_closure.md`
2. `docs/ai/CTO_CURRENT_OPS.md`
3. `docs/ai/PROJECT.md`

This satisfies the required R1 doc-only scope.

### 1.3 Baseline-to-candidate cumulative scope — EXECUTED

`git diff --name-only d796dcb0..872250ba` returned exactly 16 files:

1. `ai-ledger/product-ai/2026-08-12_dc12r1_mvp_r0_r1_readiness_debt_closure.md`
2. `backend/api/v1/client/statements.py`
3. `backend/api/v1/statement_http.py`
4. `backend/api/v1/statements.py`
5. `backend/tests/test_dc12r1_contract_d_statement_print.py`
6. `docs/ai/CTO_CURRENT_OPS.md`
7. `docs/ai/PROJECT.md`
8. `frontend/src/pages/client/DeclarePaymentPage.tsx`
9. `frontend/src/router/AppRouter.tsx`
10. `frontend/src/router/__tests__/guards.test.tsx`
11. `frontend/src/router/guards.tsx`
12. `frontend/src/tests/DeclarePaymentPage.test.tsx`
13. `frontend/src/tests/PrintableWorkspace.test.tsx`
14. `frontend/src/tests/StatementPrintWorkspace.test.tsx`
15. `frontend/src/tests/permissions.test.ts`
16. `frontend/src/utils/permissions.ts`

### 1.4 Forbidden-path audit — EXECUTED

I found no cumulative diff in:

- migrations / `backend/alembic/**`
- runtime permission registry / `backend/core/permission_registry.py`
- dependencies / lockfiles
- deploy files

Conclusion: scope discipline passes.

## 2. GitNexus

### 2.1 Candidate indexing — EXECUTED

- `npx gitnexus analyze` completed successfully on candidate SHA.
- `npx gitnexus status` then reported:
  - indexed commit: `872250b`
  - current commit: `872250b`
  - status: up to date

### 2.2 Required detect_changes compare baseline — ENV-GATED / verified limitation

This GitNexus CLI build does **not** expose `detect_changes`.

Independent proof:

- `npx gitnexus --help` lists `analyze`, `status`, `query`, `context`, `impact`, `cypher`, etc., but no `detect_changes` command.
- `npx gitnexus detect_changes --repo _dc12r1_review --help` falls back to top-level help, confirming the subcommand is unavailable on this host.

Therefore I could not independently execute the requested `detect_changes compare baseline` gate. I did **not** fabricate it.

### 2.3 Context / impact results — GITNEXUS

#### `map_statement_result`

- Context resolved to `backend/api/v1/statement_http.py:48-105`
- Direct incoming callers:
  - `backend/api/v1/statements.py:print_supplier_statement`
  - `backend/api/v1/client/statements.py:print_client_statement`
  - mapper parity/mutation tests in `backend/tests/test_dc12r1_contract_d_statement_print.py`
- Impact: **LOW**
  - direct callers: 2
  - affected processes: 2
  - no HIGH/CRITICAL result

#### `RetailerPermissionRoute`

- Context resolved to `frontend/src/router/guards.tsx:114-122`
- Outgoing call: `can`
- Impact: **LOW**
  - upstream impacted count: 0 reported by graph
  - no HIGH/CRITICAL result

#### `can`

- Context resolved to `frontend/src/utils/permissions.ts:35-38`
- Incoming callers include:
  - `RetailerPermissionRoute`
  - `SKUListPage`
  - `DataIntakePage`
- Impact: **LOW**
  - direct callers: 3
  - affected module: frontend `Skus`
  - no HIGH/CRITICAL result

#### `neutralDeclarationError`

- Context resolved to `frontend/src/pages/client/DeclarePaymentPage.tsx:16-26`
- Direct caller: `handleSubmit`
- Impact: **LOW**
  - direct callers: 1
  - no HIGH/CRITICAL result

#### `AppRouter`

- Context resolved to `frontend/src/router/AppRouter.tsx:270-272`
- Impact: **LOW**
  - direct callers: 0 reported by graph
  - no HIGH/CRITICAL result

### 2.4 Author-ledger GitNexus disclosure review — STATIC + HISTORICAL-AUTH

The candidate ledger explicitly says the author did **not** run mandatory GitNexus gates and that CTO-supplied `detect_changes` evidence was supplementary. That disclosure is internally consistent with the CLI limitation observed on this host.

I could not independently prove the ledger’s quoted supplementary `detect_changes = 84 symbols / 16 files / 6 affected flows / HIGH` numbers because the command is unavailable here and no standalone artifact was committed for replay. I therefore treat that specific numeric claim as **unreproduced supplementary evidence**, not as independently executed proof.

## 3. WPR-001 document-fact review

### 3.1 Protected-tip truth — STATIC + EXECUTED

`docs/ai/PROJECT.md` and `docs/ai/CTO_CURRENT_OPS.md` now correctly distinguish:

- current protected tip: `d796dcb0...`
- accepted merge ancestor: `adcc7f28...`

Exact examples:

- `docs/ai/PROJECT.md:6-8`
- `docs/ai/PROJECT.md:80-81`
- `docs/ai/CTO_CURRENT_OPS.md:6-8`
- `docs/ai/CTO_CURRENT_OPS.md:17-22`

This matches the independently executed ancestry proof.

### 3.2 R1 date consistency — STATIC

- `docs/ai/PROJECT.md:3` -> `2026-08-12`
- `docs/ai/CTO_CURRENT_OPS.md:3` -> `2026-08-12`
- ledger R1 section is also explicitly dated `2026-08-12`

Consistent.

### 3.3 16-file detect-secrets disclosure — STATIC + EXECUTED

- Candidate ledger §8 says final scan covered **all 16 changed files**.
- Executed cumulative diff confirms exactly 16 files changed from baseline to candidate.

Consistent.

### 3.4 H7 record consistency — STATIC

The ledger’s H7 note matches current source:

- `backend/pyproject.toml:59-60` -> `passlib 1.7.4` and `bcrypt >=4.0,<4.1`
- `backend/poetry.lock:200-201` -> `bcrypt 4.0.1`
- `backend/Dockerfile:36` -> `poetry install --no-root --only main`
- `backend/requirements.txt:8` -> `bcrypt==5.0.0`
- `backend/scripts/setup.sh:44` -> `pip install -r requirements.txt`

This is accurately recorded as a pre-existing post-merge prerequisite, not a change in this candidate.

## 4. WPR-002 permission-guard review

### 4.1 Guard implementation — STATIC + GITNEXUS

`frontend/src/router/guards.tsx:114-122` defines `RetailerPermissionRoute` and it reuses `can(user, permission)` exactly as required.

No independent permission algorithm was introduced.

### 4.2 Exact client-route to backend-permission mapping — STATIC

I verified all five guarded client routes in `frontend/src/router/AppRouter.tsx:158-190` against backend `RequirePermission(...)`:

| Client route | Frontend guard | Backend route / permission | Result |
|---|---|---|---|
| `/client/orders/:orderId/declare` | `CLIENT_PERMISSIONS.PAYMENTS_DECLARE` | `backend/api/v1/client/orders.py:527-539` -> `client:payments:declare` | exact |
| `/client/orders/:orderId/print` | `CLIENT_PERMISSIONS.ORDERS_READ` | `backend/api/v1/client/orders.py:325-335` -> `client:orders:read` | exact |
| `/client/declarations/:declarationId/print` | `CLIENT_PERMISSIONS.PAYMENTS_READ` | `backend/api/v1/client/declarations.py:114-123` -> `client:payments:read` | exact |
| `/client/declarations/:declarationId/receipt` | `CLIENT_PERMISSIONS.PAYMENTS_READ` | `backend/api/v1/client/declarations.py:178-187` -> `client:payments:read` | exact |
| `/client/statements/print` | `CLIENT_PERMISSIONS.FINANCE_READ` | `backend/api/v1/client/statements.py:151-162` -> `client:finance:read` | exact |

### 4.3 Real AppRouter evidence — STATIC

The candidate contains real AppRouter tests rather than only local reconstructed-route evidence:

- `frontend/src/tests/PrintableWorkspace.test.tsx:975-1178`
- `frontend/src/tests/StatementPrintWorkspace.test.tsx:664-827`

These tests render the real `AppRouter`, manipulate the actual browser history, and assert:

- admitted routes issue only the expected endpoint call
- denied routes do not mount the protected document/form
- denied routes produce zero protected GETs and zero writes

This satisfies the “not only local reconstructed route” requirement.

## 5. WPR-003 declaration-submit review

### 5.1 Permission requirement — STATIC

Frontend routing now requires `client:payments:declare` before the page mounts:

- `frontend/src/router/AppRouter.tsx:158-165`
- `frontend/src/router/guards.tsx:114-122`

Backend still requires the same permission:

- `backend/api/v1/client/orders.py:527-539`

Exact match.

### 5.2 Idempotency-key contract — STATIC + test-authenticity review

Implementation:

- one stable ref created on mount: `DeclarePaymentPage.tsx:43`
- success rotates key: `DeclarePaymentPage.tsx:63-66`
- failure preserves key: `DeclarePaymentPage.tsx:67-71`

Tests:

- failure retry uses same key: `frontend/src/tests/DeclarePaymentPage.test.tsx:93-120`
- success rotates only after success: `...:122-140`
- neutral-copy failure still preserves same key: `...:279-295`

I found no false-green hole in the reviewed idempotency assertions.

### 5.3 Neutral public copy only — STATIC + test-authenticity review

Implementation `neutralDeclarationError()` only consults coarse HTTP status:

- `DeclarePaymentPage.tsx:16-26`

The DOM write path uses only `setError(neutralDeclarationError(err))`:

- `DeclarePaymentPage.tsx:67-71`

It does **not** read:

- backend `data.message`
- backend `data.code`
- schema names
- internal ids
- raw `Error.message`

Tests explicitly assert leakage does not reach DOM:

- malicious 409 payload redaction: `frontend/src/tests/DeclarePaymentPage.test.tsx:233-255`
- fixed 409 copy: `...:257-265`
- raw network `Error.message` does not render: `...:267-277`

### 5.4 Missing-permission zero POST — STATIC

Real AppRouter deny tests prove no declaration POST when permission is absent:

- `frontend/src/tests/PrintableWorkspace.test.tsx:1188-1228`

The denied path asserts:

- form never mounts
- `api.post` never called

This satisfies the zero-POST requirement.

## 6. WPR-004 shared-mapper review

### 6.1 Single shared mapper — STATIC + GITNEXUS

Shared helper exists at:

- `backend/api/v1/statement_http.py:48-105`

Both Contract D routes import and call it:

- supplier: `backend/api/v1/statements.py:19,116`
- retailer: `backend/api/v1/client/statements.py:25,132`

No private `_map_statement_result` copy remains in either route module.

### 6.2 Exact status/code/message parity — STATIC

Shared mapper contract is:

- `not_found` -> `404 STATEMENT_NOT_AVAILABLE`
- `StatementPeriodError` -> `400 INVALID_DATE_RANGE`
- `StatementRangeTooLarge` -> `400 STATEMENT_RANGE_TOO_LARGE`
- `StatementLedgerScopeIncomplete` -> `409 STATEMENT_LEDGER_SCOPE_INCOMPLETE`
- `StatementInternalInconsistent` -> `409 STATEMENT_INTERNAL_INCONSISTENT`
- `StatementReconciliationFailed` -> `409 STATEMENT_RECONCILIATION_FAILED`
- unknown fallback -> `404 STATEMENT_NOT_AVAILABLE`

This is implemented exactly in `backend/api/v1/statement_http.py:54-105`.

### 6.3 Parity and mutation-test sensitivity — STATIC

Relevant tests:

- shared import / no private copy: `backend/tests/test_dc12r1_contract_d_statement_print.py:2925-2931`
- byte-contract table: `...:2993-3006`
- supplier/client identical mapping: `...:3023-3036`
- one-sided drift mutation evidence: `...:3040-3074`

The mutation test is meaningful: it explicitly creates a drifted mapper where `StatementRangeTooLarge` becomes `409 DRIFTED` instead of the contract `400 STATEMENT_RANGE_TOO_LARGE`, then proves the outputs diverge. That is sufficient to catch one-sided drift.

## 7. Test-authenticity review

### 7.1 What I independently verified

- AppRouter-based route guard tests are present for the protected client print/declaration routes.
- Component-level declaration tests explicitly check idempotency and DOM redaction.
- Backend mapper tests verify shared-callable identity, byte contract, parity, and mutation sensitivity.

### 7.2 What I did not independently execute

I did **not** independently run:

- full backend PG16/Redis7 runtime suites
- frontend vitest suites
- full candidate author gates from the ledger

Reason: this review host was used for source/evidence audit only, and I did not manufacture runtime proof beyond available local static/GitNexus/git evidence.

### 7.3 Authenticity conclusion

I found no source-level sign that the reviewed WPR-002/003/004 tests are relying on skip/xfail weakening, swallowed assertions, or reconstructed-route-only evidence. The deny-path AppRouter tests are materially stronger than the R0 issues they claim to close.

## 8. Overall conclusion

All mandatory source checks passed:

- candidate SHA exact
- R0 direct parent exact
- baseline ancestor exact
- R1 doc-only delta exact (3 files)
- cumulative approved delta exact (16 files)
- no forbidden migration/permission/dependency/deploy changes
- WPR-001 document facts reconciled
- WPR-002 five guarded routes match backend permissions exactly
- WPR-003 declaration permission/idempotency/neutral-copy/zero-POST conditions satisfied
- WPR-004 shared mapper and parity/mutation coverage satisfied

Residual limitation:

- GitNexus `detect_changes compare baseline` could not be independently executed because this CLI build does not expose that command. I disclosed this explicitly and did not treat unavailable runtime/tooling as a source defect.

## 9. Finding accounting

- P0: 0
- P1: 0
- P2: 0
- P3: 0
- INFO: 3
- NEEDS_PROOF: 0
- Accounting gap: 0
