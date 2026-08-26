# DC-12R1-MVP-L1-J1-H2-C-R1-R1-V1 — Kilo Bounded Test-Infrastructure Delta Review

**VERIFICATION_TIER:** V1_SOURCE_AND_TEST_AUTHENTICITY_REVIEW  
**CLAIM_CEILING:** TEST_INFRASTRUCTURE_DELTA_APPROVAL_ONLY  
**BASE:** `8ad346e52ff812638a6ac35205b3aade68e20005`  
**IMPLEMENTATION:** `ff6fc4f3d64bed9a4a5bb6ea1b948f7e44f3dc2b`  
**CANDIDATE:** `d1198f3ba30b39016299fe449087980310ff5df1`  
**PRIOR_KILO_E2:** `acd836bb1cc8d229088f8041cea86230f60609e7`  
**PROTECTED_BASELINE:** `2c20d58c88a0a8f5175f4d11041d03b6ca785e06`  
**REPORT_DATE:** 2026-08-27 (+08:00)  
**REVIEWER:** Kilo (static source audit; no runtime execution)

---

## Phase 1 — Proof Gate

| Check | Result | Evidence |
|-------|--------|----------|
| `fetch --all --prune` | PASS | Executed in main worktree; remotes refreshed. |
| Detached clean worktree at CANDIDATE | PASS | Created `_dc12r1_j1h2b_r3r2_residue_zero_red_2026-08-26_wt_candidate` at `d1198f3ba30b39016299fe449087980310ff5df1`. |
| Remote source tip == CANDIDATE | PASS | `origin/zcode/dc12r1-mvp-l1-j1-h2-c-r1-r1-canonical-neutrality-residue-closure-2026-08-27` points to `d1198f3b...`. |
| `CANDIDATE^ == ff6fc4f3` | PASS | Verified via `git rev-parse`. |
| `ff6fc4f3^ == BASE` | PASS | Verified via `git rev-parse`. |
| `BASE..CANDIDATE` exactly 2 files | PASS | `ai-ledger/product-ai/2026-08-27_dc12r1_mvp_l1_j1_h2_c_r1_r1_canonical_neutrality_residue.md` and `backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py`. |
| Protected files unchanged | PASS | `product/`, `frontend/`, `shared/s1_db/`, `migrations/`, `requirements`, `pyproject.toml`, `tests/harness/`, and protected ref `2c20d58c...` show zero diff. |

**Phase 1 verdict: PASS**

---

## Phase 2 — Cleanup Source Review

### 2.1 Registry precision
The `_Registry` class records exact IDs per test:
- `setup_token_ids`, `reset_token_ids`, `binding_ids`, `invitation_ids`, `retailer_ids`, `wholesaler_ids`, `schemas`
- `_MODULE_REGISTRY` mirrors per-test registries at fixture teardown.

PASS: Registry records only exact IDs/schemas created by this module.

### 2.2 Fresh connection + FK-safe order
`_fresh_session()` creates a new `create_async_engine` per call and sets `session.info["tenant_schema"] = "public"`.  
`_cleanup_exact()` deletes in FK order: tokens → bindings → invitations → retailers → wholesalers → schemas.

PASS: Fresh connections used; FK-safe order respected.

### 2.3 No wildcard/global destruction
All deletions use `WHERE id = :exact`. Schema drops use exact name with `DROP SCHEMA IF EXISTS "<schema>" CASCADE`. No `LIKE`, no wildcard, no full-table delete, no `DROP DATABASE`, no global reset.

PASS: No prohibited patterns found.

### 2.4 Second fresh connection zero-proof
`_prove_zero()` opens a second fresh connection and verifies every exact ID and schema is absent.

PASS: Second-connection zero-proof implemented.

### 2.5 DROP SCHEMA IF EXISTS evaluation
`DROP SCHEMA IF EXISTS` is used for exact schema names only. It does not mask lifecycle errors because:
- The schema name comes from the registry (exact, deterministic `t_<ws_id.hex>`).
- The preceding `_prove_zero` on public rows ensures no orphaned FK references remain.
- If a schema were unexpectedly missing, `DROP SCHEMA IF EXISTS` is idempotent and does not hide the fact that public rows were already cleaned.

PASS: `DROP SCHEMA IF EXISTS` does not mask lifecycle errors.

### 2.6 Test-body failure vs teardown failure preservation
The `h2c_registry` fixture is a `yield` fixture. Teardown runs `_cleanup_exact` then `_prove_zero`. Pytest reports teardown errors alongside (not instead of) test-body failures.

PASS: Both failure modes are preserved.

**Phase 2 verdict: PASS**

---

## Phase 3 — Mandatory Failure-Cut Review

### Cut Point 1: wholesaler/schema committed, invitation not registered
- **Finalizer discovery:** YES. `_register_ws_and_schema()` appends `wholesaler_ids` and `schemas` immediately. Even if invitation registration fails later, the wholesaler and schema are in the registry.
- **FK cleanup failure:** NO. No invitation/retailer/binding/token exists yet; deleting the wholesaler and schema has no FK dependents.
- **DB residue after teardown:** NO.
- **Original test failure preserved:** YES. Fixture teardown runs; if cleanup succeeds, only the test failure is reported.

### Cut Point 2: invitation committed, retailer/binding not registered
- **Finalizer discovery:** YES. `_register_invitation()` appends `invitation_ids` immediately.
- **FK cleanup failure:** NO. No retailer/binding/token references the invitation.
- **DB residue after teardown:** NO.
- **Original test failure preserved:** YES.

### Cut Point 3: setup token created, `_sweep_tokens` not executed
- **Finalizer discovery:** NO. `_sweep_tokens()` is called AFTER `consume_setup_token()`. If `consume_setup_token()` raises (e.g., token already used/expired), the setup token row remains in the DB but is **not** appended to `setup_token_ids`.
- **FK cleanup failure:** YES. The unregistered setup token still holds a FK to `retailer_id`. When `_cleanup_exact` later tries `DELETE FROM retailers WHERE id = :exact`, PostgreSQL will raise a FK violation because the orphaned token row still references the retailer.
- **DB residue after teardown:** YES. The cleanup transaction rolls back on FK violation, leaving both the retailer and the setup token in the DB.
- **Original test failure preserved:** YES. Pytest reports the test-body failure and the teardown FK error. However, the DB residue persists silently after the test run.

**STOP CONDITION TRIGGERED: P1 TEST_HYGIENE_DEFECT**

### Cut Point 4: forgot-password POST creates reset token/email, token ID not written to registry
- **Finalizer discovery:** NO. In `test_hc07_hc10_canonical_neutrality_real_http`, reset tokens are created by the real HTTP endpoint. Their IDs are queried and appended to `h2c_registry.reset_token_ids` **after** the HTTP block. If any assertion between the HTTP calls and the sweep fails, the reset token is not registered.
- **FK cleanup failure:** YES. Same as Cut Point 3 — unregistered reset tokens FK-reference `retailer_id`. Deleting the retailer fails.
- **DB residue after teardown:** YES.
- **Original test failure preserved:** YES.

**STOP CONDITION TRIGGERED: P1 TEST_HYGIENE_DEFECT (continued)**

### Cut Point 5: canonical response assertion fails before token ID registration
- **Finalizer discovery:** NO. Identical to Cut Point 4 — the token exists in DB but is not in the registry.
- **FK cleanup failure:** YES.
- **DB residue after teardown:** YES.
- **Original test failure preserved:** YES.

**STOP CONDITION TRIGGERED: P1 TEST_HYGIENE_DEFECT (continued)**

### Summary
The finalizer operates **only** on exact IDs already present in the registry. It does **not** re-discover intermediate objects by `retailer_id` or any other predicate. Any test failure occurring between object creation and the explicit `_sweep_tokens()` / manual ID query leaves an unregistered object in the DB. When that object holds a FK to a registered parent, the parent-deletion step fails with a FK violation, the cleanup transaction rolls back, and **committed residue remains**.

**Phase 3 verdict: STOP — P1 TEST_HYGIENE_DEFECT**

---

## Phase 4 — Global-State Review

### 4.1 `app.dependency_overrides` restoration
`_real_client()` sets `app.dependency_overrides[get_db_session] = _override`.  
`test_hc07_hc10_canonical_neutrality_real_http` wraps the client usage in `try: ... finally: app.dependency_overrides.pop(get_db_session, None)`.

PASS: Override is restored in success and exception paths.

### 4.2 Dev email sink restoration per test
`clear_dev_email_deliveries()` is called at the **start** of tests that need a clean sink:
- `test_forgot_password_email_carries_db_canonical_uppercase_code` (line 341)
- `test_forgot_password_email_w_matches_case_insensitive_lookup` (line 367)
- `test_hc07_hc10_canonical_neutrality_real_http` (line 445)

There is **no** corresponding `clear_dev_email_deliveries()` call at test end or module teardown. The `s1_db` fixture (from `test_dc12r1_s1_retailer_identity.py`) clears at setup only.

**STOP CONDITION TRIGGERED: P1 GLOBAL_TEST_STATE_RESIDUE**

### 4.3 `clear_dev_email_deliveries` not called after test
Confirmed: the sink is cleared only before tests, never after. `test_hc07_hc10_canonical_neutrality_real_http` creates exactly one HC07 email delivery. Because `test_module_residue_zero` (the final test in the module) does **not** clear the sink, the module terminates with at least one residual `RetailerCredentialEmailDelivery` in `_DEV_RETAILER_EMAIL_DELIVERIES`.

**STOP CONDITION TRIGGERED: P1 GLOBAL_TEST_STATE_RESIDUE (continued)**

### 4.4 `_MODULE_REGISTRY` cross-test/order state leakage
`_MODULE_REGISTRY` is a module-level singleton. Each test's registry is mirrored into it at fixture teardown. Because IDs are UUID-based and tests use `uuid.uuid4()`, reverse-order execution does not replay the same IDs. No state from one test influences another's assertions.

PASS: No cross-test state leakage detected.

### 4.5 Engine/session/connection closure
`_fresh_session()` uses `create_async_engine` in an `async with` block and calls `engine.dispose()` in `finally`. All test-level sessions are either fixture-managed or context-managed.

PASS: Connections are closed.

### 4.6 Mutation DB + memory state zeroed
`test_module_residue_zero()` calls `_prove_zero(_MODULE_REGISTRY)` to assert DB residue is zero. However, as noted in Phase 3, unregistered objects bypass this proof. In-memory email sink is **not** zeroed at module end.

**Phase 4 verdict: STOP — P1 GLOBAL_TEST_STATE_RESIDUE**

---

## Phase 5 — Canonical Neutrality Authenticity

### 5.1 Real ASGI endpoint
`test_hc07_hc10_canonical_neutrality_real_http` uses `AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")` with a real `get_db_session` override. This is a live HTTP round-trip through FastAPI, not a service直调 or mock response.

PASS: Real ASGI endpoint exercised.

### 5.2 HC07–HC10 four states real
- **HC07:** Established retailer (verified email + password) + correct wholesaler code → token + email issued.
- **HC08:** Ghost email + correct wholesaler code → neutral 200, zero token, zero email.
- **HC09:** Verified retailer + wrong wholesaler code → neutral 200, zero token, zero email.
- **HC10:** Unverified retailer (setup token NOT consumed) + correct wholesaler code → neutral 200, zero token, zero email.

All four are exercised through real HTTP POST to `/api/v1/client/auth/forgot-password`.

PASS: Four states are real and verified.

### 5.3 Exact key set + success + data + fixed message + parseable timestamp
`_assert_canonical_neutral_body()` asserts:
- `set(body.keys()) == {"success", "data", "message", "timestamp"}`
- `body["success"] is True`
- `body["data"] == {}`
- `body["message"] == NEUTRAL_RETAILER_CREDENTIAL_MESSAGE`
- `timestamp` is non-empty string and `datetime.fromisoformat` parses it.

PASS: Strong assertions on exact key set and values.

### 5.4 Timestamp sentinel comparison
`_sentinel()` replaces ONLY the `timestamp` value with `"<SENTINEL>"` and compares the four dicts key-for-key.

PASS: Sentinel comparison implemented correctly.

### 5.5 No raw-byte / duration / timing-side-channel equality
The docstring and code explicitly state: "No raw-byte equality, no response-duration equality, and no timing side-channel closure is claimed."

PASS: No forbidden equality claims.

### 5.6 HC07 exactly one token/email; HC08–HC10 zero side effects
The test asserts:
- `len(tokens7) == 1`
- `len(tokens10) == 0`
- One delivery to `email7`, zero deliveries to `email10`.

PASS: Side-effect accounting exact.

### 5.7 C4 temporary product message mutation hits HTTP assertion
Mutation anchor C4: "changing the neutral message or adding a response key -> the canonical equality assertion RED."  
The test asserts exact `NEUTRAL_RETAILER_CREDENTIAL_MESSAGE` and exact key set. Any mutation to the message or addition of a key causes assertion failure.

PASS: C4 would go RED.

**Phase 5 verdict: PASS**

---

## Phase 6 — Test Authenticity

### 6.1 C1–C4 hit real fix points
- **C1** (remove finalizer) → `test_module_residue_zero` RED because unregistered objects survive.
- **C2** (clean rows but keep schema) → schema zero-proof RED.
- **C3** (drop schema but keep rows) → public-row zero-proof RED.
- **C4** (change neutral message / add key) → canonical equality RED.

All anchors target the exact regression points described in the docstring.

PASS: Anchors are well-placed.

### 6.2 Kilo-not-executed mutations labeled
Kilo did not execute C1–C4. They are documented as **CANDIDATE_PROVIDED_EVIDENCE** (mutation anchors in the test docstring and assertions). No claim is made that Kilo independently runtime-verified them.

PASS: Properly labeled.

### 6.3 Runtime execution claims
The review is **static source-only** (`VERIFICATION_TIER: V1_SOURCE_AND_TEST_AUTHENTICITY_REVIEW`). No PG16/Redis7 runtime was launched. The candidate evidence (zcode branch `dc12r1-mvp-l1-j1-h2-c-r1-r1-canonical-neutrality-residue-closure-2026-08-27` and its ledger) claims runtime execution, but this review does not re-run or validate those runtime claims.

PASS: No fabricated runtime PASS; HOST_LIMITATION disclosed by scope.

### 6.4 Scope compliance
The review covers only the 2-file delta and its immediate source dependencies. It does not re-run the full backend suite, Playwright, or Lubuntu.

PASS: Scope respected.

**Phase 6 verdict: PASS (with CANDIDATE_PROVIDED_EVIDENCE for mutations)**

---

## Phase 7 — Quality

| Check | Result | Evidence |
|-------|--------|----------|
| `py_compile` | PASS | `python -m py_compile backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py` returned no errors. |
| `git diff --check` | PASS | No whitespace or conflict markers detected. |
| `detect-secrets` | PASS | Scan of the modified test file returned zero results. |
| UTF-8 / no-BOM / no-NUL / LF | PASS | Binary inspection: BOM=False, NUL=False, CR=False, size=21224 bytes. |
| Worktree clean | PASS | `git status --short` empty. |
| GitNexus analyze/status | N/A | `gn` CLI not available in this environment. |

**Phase 7 verdict: PASS (with GitNexus N/A)**

---

## STOP Conditions Evaluation

| STOP Condition | Triggered? | Detail |
|----------------|------------|--------|
| Two-file scope or commit chain inconsistent | NO | Exactly 2 files; chain BASE→IMPLEMENTATION→CANDIDATE verified. |
| Any failure cut point leaves committed residue | **YES** | Cut Points 3–5: unregistered tokens survive teardown, causing FK cleanup failure and DB residue. |
| Dev email sink or dependency override not restored | **YES** | Module ends with non-zero `_DEV_RETAILER_EMAIL_DELIVERIES` (HC07 email not cleared after test). |
| Canonical neutrality still mock-only | NO | Real ASGI endpoint exercised. |
| Mutation false-red or recovery byte inconsistency | NO | Not evaluated (static review only). |
| Report writes candidate evidence as Kilo independent runtime evidence | NO | Review explicitly labels mutations as CANDIDATE_PROVIDED_EVIDENCE. |

---

## Final Verdict

**STOP**

### P1 Findings

1. **P1 TEST_HYGIENE_DEFECT** — Finalizer is registry-bound and cannot re-discover mid-test objects by `retailer_id`. Any test failure between object creation and `_sweep_tokens()` leaves unregistered tokens in the DB. When those tokens reference a registered parent, FK deletion fails, the cleanup transaction rolls back, and committed residue persists.

2. **P1 GLOBAL_TEST_STATE_RESIDUE** — `clear_dev_email_deliveries()` is invoked only at the start of tests, never at test end or module teardown. The module terminates with at least one `RetailerCredentialEmailDelivery` (HC07) remaining in `_DEV_RETAILER_EMAIL_DELIVERIES`.

### Required Remediation Before PASS

- **For P1 TEST_HYGIENE_DEFECT:** The finalizer must either (a) re-sweep all tokens/bindings/retailers for every registered `retailer_id` before deletion, or (b) guarantee zero-window registration by sweeping immediately after every creation step inside a try/finally that still preserves original test failures.
- **For P1 GLOBAL_TEST_STATE_RESIDUE:** Add `clear_dev_email_deliveries()` to the `h2c_registry` fixture teardown (or an `autouse` module-level fixture) so the sink is empty after every test and at module end.

### Claim Ceiling
This review is bounded to **TEST_INFRASTRUCTURE_DELTA_APPROVAL_ONLY**. No product, frontend, migration, dependency, or protected baseline changes were evaluated beyond confirming zero diff.
