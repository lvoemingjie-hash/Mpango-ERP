# DC-12R1-MVP-L1-PW1-R4-A-R3-V1 — Kilo Final Bounded Cumulative Adversarial Source Review

## Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_A_R3_V1_KILO_FINAL_REVIEW**

This is **source / test-authenticity / committed-evidence approval only**. It is **not** browser acceptance or merge approval.

---

## Phase 1 — Proof gate

### Candidate / lineage
- Frozen candidate: `5e91e97326134805cc29b75492b187aae7c17985`
- Direct parent: `aba791d281b812f96d89ccfcd1bed5f5ec955386`
- Aggregate base: `2b7b959815a8f2454811303ca1bd13c64c413bb4`
- Source branch `origin/zcode/dc12r1-mvp-l1-pw1-r4-a-tenant-statement-cache-closure-2026-08-15` resolves to **exactly** `5e91e97…`
- Detached exact-SHA worktree created and kept clean.

### Exact aggregate scope
`git diff --name-only 2b7b959..5e91e97` contains **exactly 4 files**, and exactly the 4 required files:
1. `backend/database/session.py`
2. `backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py`
3. `backend/tests/test_pw1r4_cross_tenant_statement_cache.py`
4. `ai-ledger/product-ai/2026-08-15_dc12r1_mvp_l1_pw1_r4_a_tenant_statement_cache.md`

No extra files. No evidence artifacts are on the branch.

### Exact R3 delta
`git diff --name-only aba791d..5e91e97` contains **exactly 3 files**:
- `backend/database/session.py`
- `backend/tests/test_pw1r4_cross_tenant_statement_cache.py`
- `ai-ledger/product-ai/2026-08-15_dc12r1_mvp_l1_pw1_r4_a_tenant_statement_cache.md`

That matches the requested “session comment + R4-A test + ledger” delta.

### `session.py` AST identity
I parsed `backend/database/session.py` from `aba791d` and the candidate with Python `ast.parse()` + `ast.dump(include_attributes=False)`.
Result: **AST identical**.

Therefore the R3 delta in `session.py` is **comment-only**.

---

## Phase 2 — Production causality

### Only behavioral repair
Across the full aggregate span, the only behavioral production change in `backend/database/session.py` is:
- `connect_args["prepared_statement_cache_size"] = 0`

The aggregate diff adds this one runtime setting plus explanatory comments.

### Broad/non-minimal repairs rejected
I found **no** evidence of any of the following in production code:
- retry loops
- swallowed exceptions
- per-request `engine.dispose()`
- per-tenant engines
- alternative behavior-changing fixes beyond `prepared_statement_cache_size=0`

The ledger also explicitly rejects:
- `statement_cache_size=0` as the adopted runtime repair
- per-request disposal
- per-tenant engines
- route retries / swallowed exceptions

### Exact-route GREEN is genuinely production-shaped
`backend/tests/test_pw1r4_cross_tenant_statement_cache.py` drives the precise route:
- `GET /api/v1/client/orders?page=1&size=100`

It uses the **real stack**:
- `configure_app(app, get_settings())`
- production `JwtAuthStrategy`
- real middleware chain
- `resolve_client_identity`
- `RequirePermission("client:orders:read")`
- real `get_orders_for_retailer`
- real tenant DB sessions via production dependencies

The test seeds public and tenant-scoped rows needed for the real dependency chain:
- public `retailers`
- public `wholesalers`
- public `wholesaler_retailer_bindings`
- tenant user / role / permission rows
- tenant `orders` row

The GREEN path asserts **200**, exactly **one** order, and the correct tenant marker across A→B→DDL→A and B→A cycles.

### Exact-route RED is genuinely causal
The RED leg rewires only the tenant-context session factory onto a **legacy engine** (production config minus the fix), keeps the same exact production route, and expects an `InvalidCachedStatementError` chain after the same DDL storm.

This is genuine causal proof of the repair, not a synthetic engine-only toy.

### Tenant A/B rows and permission path are real dependencies
The exact-route test exercises:
- token.tenant_id → public `wholesaler_retailer_bindings.wholesaler_id`
- token.user_id → `tenant_user_id`
- role membership and permission rows in tenant schema
- real `resolve_client_identity` dual-key binding logic
- real `RequirePermission("client:orders:read")`
- real retailer order listing repository path

This is production-shaped dependency exercise, not mocked identity resolution.

---

## Phase 3 — Cleanup authenticity

### Synthetic bypass absent
The prior `cleanup_drop` synthetic bypass branch is **absent**.
No `cleanup_drop` parameter remains in the candidate.

### Original exception / cleanup exception truth
The candidate now proves the exact required properties:
- `original_error` is pre-created and raised through the **real** seed/setup path
- `cleanup_error` is pre-created and raised by the **actual** `_drop_owned_schemas(...)` invocation via its `forced_error` parameter
- cleanup-success path re-raises the **same original object** (`ei.value is original_error`)
- cleanup-failure path raises a `BaseExceptionGroup` whose members are checked by **object identity**:
  - `members[0] is original_error`
  - `members[1] is cleanup_error`
- member count asserted exactly **2**

This closes the R2 weakness where only type/message, not object identity, was proven.

### Finally cleanup and residue proof
The dual-error test wraps the failure in a `finally` block that:
- calls the real saved drop helper with the exact owned schemas
- runs an independent fresh-engine `pg_namespace` check (`count == 0`) afterward

This is a genuine out-of-band residue proof.

### Fixture teardown audit
`two_tenants` fixture teardown:
- wraps `yield` in `try/finally`
- drops **exactly** the owned schema names
- asserts zero schema residue
- disposes the fixture DDL engine
- collects teardown failures and raises `BaseExceptionGroup` if needed

I found no teardown swallowing.

### Public-table residue audit
Important boundary of proof:
- `_seed_tenant_readiness()` inserts into:
  - `public.retailers`
  - `public.wholesalers`
  - `public.wholesaler_retailer_bindings`
- teardown / helper cleanup drops **schemas only** via `_drop_owned_schemas()`
- I found **no** DELETE / TRUNCATE cleanup for those public tables in the candidate test file

Therefore:
- the suite **does prove zero schema residue**
- the suite **does not prove zero database residue overall**
- by source inspection, it appears to **leave public-table residue** unless the surrounding database is disposable

I do **not** broaden “zero schema residue” into “zero database residue”.

This is not a STOP blocker because the ledger/test language in the candidate is careful about schema residue, and the task explicitly asked for honest reporting rather than over-claiming.

---

## Phase 4 — H5 and evidence truth

### RED/GREEN/POLICY boundaries are correct
`backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py` now states and implements:
- **RED** on a **dedicated cache-enabled engine**
- **GREEN** on a **dedicated cache-enabled engine** with `dispose()` proving the mechanism
- **POLICY** as the **only** production-global-engine leg

This matches the requested truth model.

### No stale cache wording
I verified:
- `session.py` R3 delta corrects the stale “per-pool LRU” wording to the accurate “per DBAPI connection retained/reused by the shared pool” wording
- ledger R3 section states that correction explicitly

### No historical evidence represented as current
The ledger explicitly marks historical `pw1r4a-evidence/*` artifacts as **off-branch / referable by SHA only** and keeps current branch scope to the exact 4 files.

### 9 + 5 node reconciliation
Actual test-node counts by source:
- `test_pw1r4_cross_tenant_statement_cache.py` → **9** `async def test_*`
- `test_dc12r1_h5_prepared_statement_cache_isolation.py` → **5** `async def test_*`
- total = **14**

The final ledger sections consistently state:
- `R4-A (9) + H5 (5): natural order 14/14; reverse order 14/14`

Counts reconcile.

---

## Phase 5 — Runtime if host permits

I probed local host support:
- candidate worktree had no ready backend pytest environment
- global Python lacked `pytest`
- PostgreSQL was reachable, but I did not have a clean local test environment in the candidate worktree
- I did **not** independently provision the two 23-minute full gates

Therefore:
- I **did not claim** local execution of the focused natural/reverse `14/14` suite
- I relied on the committed ledger evidence only for that runtime claim

This is compliant with the instruction to disclose unavailable runtime rather than over-claim execution.

---

## Phase 6 — Quality

### `git diff --check`
- `git diff --check 2b7b959..5e91e97` → **clean**

### `py_compile`
- `backend/database/session.py`
- `backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py`
- `backend/tests/test_pw1r4_cross_tenant_statement_cache.py`

All compiled successfully.

### scoped `detect-secrets`
Scoped scan on the 4 changed files was **clean**.

### strict UTF-8 / mojibake
Changed-file scan found **0** replacement-character (`U+FFFD`) hits.

### GitNexus
- `npx gitnexus analyze` completed successfully in the detached candidate worktree
- `npx gitnexus status` reports:
  - indexed commit = `5e91e97`
  - current commit = `5e91e97`
  - status = **up-to-date**

### Findings accounting gap
Review findings accounting gap = **0**.
No unresolved P0/P1/P2 defect or evidence contradiction remains.

---

## Final conclusion

This bounded cumulative review closes the required points:
- exact candidate identity and lineage
- exact 4-file aggregate scope
- exact 3-file R3 delta
- `session.py` AST identity across `aba791d..candidate`
- only behavioral repair = `prepared_statement_cache_size=0`
- no broad workaround fixes
- exact-route GREEN/RED are production-shaped and causal
- cleanup proof is genuine and object-identity based
- public-table residue is **not** falsely claimed clean
- H5 boundaries and wording are current and accurate
- 9 R4-A + 5 H5 nodes reconcile
- bounded quality gates pass

**Final verdict: `PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_A_R3_V1_KILO_FINAL_REVIEW`**
