# DC-2T1-R2 Independent Evidence Verification

**Baseline:** e022f21 | **Date:** 2026-07-08 | **Executor:** Leo (manual, subagent failed 2x gateway restart)

---

## D1: STALE_TEST_CONTRACT

**Test:** `test_contract_locks_public_endpoint_disclosure_boundary` in `tests/test_u6i0_owner_credential_setup_contract.py:130`

**Test logic:** This is a **source-level static check**, NOT a runtime HTTP test. It iterates over `PUBLIC_BOUNDARY_PATHS` (auth.py, onboarding_service.py, tenant_provisioning_service.py) and asserts that the literal strings `"owner credential setup"`, `"setup token"`, and `"raw setup token"` do NOT appear in the source files.

**Source evidence:**
- `api/v1/auth.py:603` — `# POST /auth/onboarding/setup-credential  (U6-I5 owner credential setup)` ← comment contains "owner credential setup"
- `api/v1/auth.py` — no literal `"setup token"` or `"raw setup token"` found in source (only `setup_token` as variable name, no spaces)
- `services/onboarding_service.py:367` — `"""Build the owner credential setup link for email delivery only."""` ← docstring contains "owner credential setup"

**Verdict:** The comment on line 603 of `auth.py` and the docstring in `onboarding_service.py` contain `"owner credential setup"`, which the test's case-insensitive grep catches. This is a **comment/docstring** — not an HTTP response leak. The test is a **static contract guard** checking that public-facing source files don't reveal implementation details in their text content. The presence of a code comment like `(U6-I5 owner credential setup)` is a minor information disclosure in source (not runtime), but the test's strictness makes it a STALE_TEST_CONTRACT issue — the test expects zero mentions, but the source has benign comments. **Not a runtime PRODUCT_DEFECT.**

---

## D2: NEEDS_EVIDENCE (no matching test function exists)

**Expected test:** `test_setup_credential_route_disclosure_boundary` — **this function does NOT exist** in `tests/test_u6i5_owner_credential_setup_endpoint.py`.

**Available related test:** `test_response_never_exposes_sensitive_data` (line 431) — checks that HTTP response body does NOT contain sensitive fields (setup_token, token_hash, password_hash, tenant_schema, wholesaler, user_id, role_id, permission_id). This is a **runtime HTTP response** check, not a source path exposure check.

**No test exists** that checks for source code path exposure in HTTP responses or OpenAPI schema. The original D2 finding may refer to a test that was planned but not yet written, or the test name was misremembered.

**Source check:** `api/v1/auth.py` — no `__file__`, no debug traceback exposure, no source path in error handlers found. The route registration is standard FastAPI.

**Verdict:** The referenced test function does not exist. Cannot verify D2 as described. The actual HTTP response data exposure test (`test_response_never_exposes_sensitive_data`) is well-written and tests the right thing. **NEEDS_EVIDENCE** — D2 as originally described cannot be reproduced because no test with that name exists.

---

## D3: BLOCKED_BY_BCRYPT_INCOMPATIBILITY (not a duplicate-email bug)

**Test:** `test_duplicate_live_email_in_production_is_neutral_and_sends_no_extra_smtp`

**Actual pytest result:** FAILED — but NOT because of duplicate email handling.

**Root cause:** `bcrypt 5.0.0` is incompatible with `passlib 1.7.4`. The error chain:
```
passlib.handlers.bcrypt → _load_backend_mixin → detect_wrap_bug → _bcrypt.hashpw
ValueError: password cannot be longer than 72 bytes, truncate manually if necessary
```
Also: `AttributeError: module 'bcrypt' has no attribute '__about__'`

This causes the FIRST signup request to fail with an unhandled `ValueError` (500 Internal Server Error), so the test never even reaches the duplicate-email scenario.

**Source code analysis (duplicate email handling):**
In `services/onboarding_service.py:280-283`:
```python
existing_live = await _live_registration_for_email(db, owner_email)
if existing_live is not None:
    return SignupResult(registration_id=None, status="pending_email_verification")
```
And at line 339-340 (IntegrityError handler):
```python
except IntegrityError:
    await db.rollback()
    return SignupResult(registration_id=None, status="pending_email_verification")
```

The product code has **correct neutral handling** for duplicate emails — it returns the same `SignupResult` without creating new rows. The 500 is caused entirely by the bcrypt/passlib version mismatch, not by a duplicate-email code bug.

**Verdict:** D3's claimed "duplicate email returns 500" is **NOT reproducible as a product code bug**. The test fails because bcrypt 5.0.0 broke passlib 1.7.4, causing ALL password hashing to crash before any signup logic runs. The duplicate email path in the source code is correct (neutral 202 response). **BLOCKED_BY_DEPENDENCY_BUG**.

---

## D4: STALE_TEST_CONTRACT

**Test:** `test_public_auth_routes_do_not_call_tenant_provisioning` in `tests/test_u6h1_tenant_provisioning_service_skeleton.py:264`

**Test logic:** Static source check — asserts that `api/v1/auth.py` and `services/onboarding_service.py` do NOT contain `TenantProvisioningService`, `tenant_provisioning_service`, or `claim_registration_for_provisioning`.

**Source evidence:**
- `api/v1/auth.py` — grep returns EMPTY (no matches for any of the three terms) ✅
- `services/onboarding_service.py:37` — `from services.tenant_provisioning_service import TenantProvisioningService` ← **FOUND** ❌
- `services/onboarding_service.py:177` — `TenantProvisioningService(session,` ← **FOUND** ❌  
- `services/onboarding_service.py:181` — `.claim_registration_for_provisioning(registration_id)` ← **FOUND** ❌

**Verdict:** `onboarding_service.py` DOES import and use `TenantProvisioningService` and `claim_registration_for_provisioning`. The test checks `ONBOARDING_SERVICE_PATH` (onboarding_service.py) and asserts these terms must NOT appear. The test would **FAIL**.

This is a genuine coupling — the onboarding service directly depends on the provisioning service. However, looking at the e2e test (D5), the provisioning flow is: signup → verify_email → onboarding orchestrator calls `TenantProvisioningService.claim_registration_for_provisioning()` → `provision_wholesaler_and_schema()`. This is the **intended architecture** — the onboarding service orchestrates provisioning.

**The test expects an architecture where onboarding_service doesn't know about provisioning, but the actual code has evolved to couple them.** This is either:
1. A STALE_TEST_CONTRACT (test written for an earlier decoupled design)
2. A real PRODUCT_DEFECT (unwanted coupling)

Given the e2e test explicitly uses this coupling, the test contract is stale. **STALE_TEST_CONTRACT**.

---

## D5: VERIFIED_CORRECT (test matches product code)

**Test:** `test_full_owner_onboarding_backend_chain_proves_hash_only_tokens_and_admin_rbac` in `tests/test_u6i6_onboarding_e2e_closeout.py:288`

**State machine in the test:**
1. Signup → `pending_email_verification` (asserted)
2. Verify email → `email_verified` (asserted at line ~340)
3. Claim for provisioning → `provisioning` (asserted)
4. Provision → `active` (asserted)

**Source code analysis:**
- `services/onboarding_service.py` — signup creates registration with `status="pending_email_verification"`
- `verify_email_token` — updates to `email_verified`
- `TenantProvisioningService.claim_registration_for_provisioning()` — updates to `provisioning`
- `TenantProvisioningService.provision_wholesaler_and_schema()` — updates to `active`

**The test asserts BOTH `email_verified` (line ~340) AND `active` (line ~355) at the appropriate stages.** The final state is `active`, which is correct.

**Verdict:** The test correctly models the state machine. Both `email_verified` (intermediate) and `active` (final) are asserted at the right points. **VERIFIED_CORRECT** — no mismatch between test expectations and product code.

---

## G1: FRESH_FAIL (retailer_prices does NOT exist in t_dev)

**Migration 017:** `alembic/versions/017_retailer_prices.py` — creates `retailer_prices` table with columns: id (uuid), retailer_id (uuid), sku_id (uuid), price (numeric 12,2), created_at, updated_at, is_deleted, deleted_at, created_by, updated_by. Uses `_current_schema(bind)` to determine which schema to create in.

**Fresh tenant path (t_dev):**
```sql
SELECT column_name FROM information_schema.columns 
WHERE table_schema='t_dev' AND table_name='retailer_prices';
→ (0 rows)
```

**t_dev schema exists** but has NO `retailer_prices` table.

**Existing tenant path:**
```sql
\dt t_dev.* → Did not find any relation named "t_dev.*"
```
(t_dev is empty — no tables at all)

**Verdict:** `t_dev` schema exists but `retailer_prices` has NOT been created. Migration 017 exists in code but has NOT been applied to t_dev. **FRESH_FAIL** — a fresh tenant provisioning would not have the `retailer_prices` table until migration 017 is explicitly run.

---

## G2: EXISTING_PASS (mv_sales_daily exists in test schemas, NOT in t_dev)

**Migration:** `alembic/versions/013_s6_2_materialize_sales.py` — creates `MATERIALIZED VIEW mv_sales_daily` per tenant schema.

**t_dev check:**
```sql
SELECT matviewname FROM pg_matviews WHERE schemaname='t_dev';
→ (0 rows)
```

**All matviews:**
```
 schemaname    | matviewname
 t_s3c_205b01bc | mv_sales_daily
 t_s3c_8bf98dce | mv_sales_daily
 t_u1r1_test    | mv_sales_daily
 t_u4ib1_proof  | mv_sales_daily
```

**Verdict:** `mv_sales_daily` exists in 4 test schemas but NOT in `t_dev`. This is expected — t_dev was likely created for testing but migration 013 wasn't applied to it. The materialized view IS being created correctly in schemas where the migration runs. **EXISTING_PASS** (for schemas where migration ran) / **FRESH_FAIL** (for t_dev specifically).

---

## bcrypt/passlib: CRITICAL_INCOMPATIBILITY

**Installed versions:**
- `bcrypt` 5.0.0
- `passlib` 1.7.4

**Problem:** bcrypt 5.0.0 removed `bcrypt.__about__.__version__` and changed the `hashpw()` API to reject passwords >72 bytes without explicit truncation. passlib 1.7.4 expects the old API.

**Test results (test_password_utils.py):**
```
FAILED test_hash_password_produces_different_hash_each_time - ValueError
FAILED test_verify_password_returns_true_for_correct_password - ValueError
FAILED test_verify_password_returns_false_for_wrong_password - ValueError
FAILED test_password_hash_roundtrip - ValueError
```
All 4 tests fail with the same bcrypt incompatibility.

**Impact:** This is a **BLOCKER** — it prevents ALL password-dependent operations (signup, login, credential setup) from functioning. Every endpoint that calls `hash_password()` or `verify_password()` will crash with ValueError.

**Fix options:**
1. Pin `bcrypt<4.1.0` (e.g., `bcrypt==4.0.1`) — restores compatibility with passlib 1.7.4
2. Migrate from passlib to direct bcrypt usage
3. Use `passlib[bcrypt]` with a compatible bcrypt version

---

## Summary Table

| Item | Verdict | Key Evidence |
|------|---------|-------------|
| D1 | STALE_TEST_CONTRACT | Test checks source for "owner credential setup"; auth.py has it in a comment (line 603). Static check, not runtime leak. |
| D2 | NEEDS_EVIDENCE | Referenced test function does not exist. Closest test (response_never_exposes_sensitive_data) is correct. |
| D3 | BLOCKED_BY_BCRYPT | Can't test duplicate email — bcrypt 5.0.0 crashes all password hashing. Source code has correct neutral handling. |
| D4 | STALE_TEST_CONTRACT | onboarding_service.py imports TenantProvisioningService (lines 37, 177, 181). Test expects decoupled architecture; code evolved to couple them. |
| D5 | VERIFIED_CORRECT | Test correctly asserts email_verified → active state progression matching product code. |
| G1 | FRESH_FAIL | retailer_prices not in t_dev. Migration 017 exists but not applied. |
| G2 | MIXED | mv_sales_daily in 4 test schemas (PASS), not in t_dev (FAIL). Migration 013 works when applied. |
| bcrypt/passlib | CRITICAL_BLOCKER | bcrypt 5.0.0 + passlib 1.7.4 = ValueError on all hash/verify operations. |
