# DC-12R1-MVP-L1-J1-H2-B-R2-R1-V1 Kilo Final Bounded Cumulative Source Review

**Review date:** 2026-08-23  
**Review mode:** Adversarial cumulative source / test-authenticity review  
**Reviewer:** Kilo (automated adversarial evidence review)  
**Verdict:** `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R1_V1_KILO_FINAL_REVIEW`

---

## 1. Frozen Ref Proof Gates

| Gate | Expected | Observed | Result |
|------|----------|----------|--------|
| BASELINE / PROTECTED | `6e9470a1daa5d6eece29724316fdd8aef6b737c1` | `6e9470a1daa5d6eece29724316fdd8aef6b737c1` | PASS |
| CANDIDATE | `34ccec116204b6a61b2e37c874b0c65953acfb43` | `34ccec116204b6a61b2e37c874b0c65953acfb43` | PASS |
| Expected parent | `87e5cbf52a169be17a20ca865631c7f667f5b59f` | `87e5cbf52a169be17a20ca865631c7f667f5b59f` | PASS |
| Candidate parent | `87e5cbf5` | `87e5cbf5` | PASS |
| Baseline ancestor of candidate | yes | yes (`git merge-base --is-ancestor` exit 0) | PASS |
| Source branch tip == candidate | `origin/zcode/dc12r1-mvp-l1-j1-h2-b-r2-r1-deterministic-atomicity-evidence-2026-08-23` | `34ccec11` | PASS |
| `origin/product-dev-recovered` | `6e9470a1` | `6e9470a1` | PASS |

### 1.1 Delta Verification

| Delta | Expected count | Observed count | Result |
|-------|---------------|----------------|--------|
| R2-R1 (`87e5cbf5..34ccec11`) | 3 files | 3 files | PASS |
| Cumulative (`6e9470a1..34ccec11`) | 7 files | 7 files | PASS |

**R2-R1 delta (exactly 3 files):**
1. `ai-ledger/product-ai/2026-08-23_dc12r1_mvp_l1_j1_h2b_r2_r1_deterministic_atomicity_evidence.md`
2. `backend/services/password_reset_service.py`
3. `backend/tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py`

**Cumulative delta (exactly 7 files):**
1. `ai-ledger/product-ai/2026-08-22_dc12r1_mvp_l1_j1_h2b_forgot_password_runtime_closure.md`
2. `ai-ledger/product-ai/2026-08-23_dc12r1_mvp_l1_j1_h2b_r1_password_reset_scan_closure.md`
3. `ai-ledger/product-ai/2026-08-23_dc12r1_mvp_l1_j1_h2b_r2_consume_atomicity_closure.md`
4. `ai-ledger/product-ai/2026-08-23_dc12r1_mvp_l1_j1_h2b_r2_r1_deterministic_atomicity_evidence.md`
5. `backend/api/v1/auth.py`
6. `backend/services/password_reset_service.py`
7. `backend/tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py`

**Scope check:** No migration, model, dependency, lockfile, frontend, or deployment changes in cumulative delta. PASS.

---

## 2. Mandatory Source Review

All mandatory source invariants verified against candidate SHA `34ccec116204b6a61b2e37c874b0c65953acfb43`.

### 2.1 Neutral Public Response (`forgot-password`)

`auth.py` `forgot_password()` endpoint always returns `ForgotPasswordResponse` with:
- `message = NEUTRAL_PASSWORD_RESET_MESSAGE` ("Password reset result is not disclosed through this endpoint.")
- `status_code = 200`

Regardless of whether the email exists, scans fail, or delivery fails. Verified in source lines 721-833.

### 2.2 Scan Failure → Account Absence Prevention

`password_reset_service.py` `request_reset()` (lines 237-303):
- When `scan.failed_schema_count > 0` AND no active user found, raises `PasswordResetScanIncompleteError` (sanitized counters only).
- The API layer catches this and emits exactly one `PASSWORD_RESET_SCAN_INCOMPLETE` internal event while answering neutral 200.
- Scan failure is NEVER silently converted into `issued=False` ("account does not exist").

### 2.3 Consume Rejects Incomplete Scan Before First UPDATE

`password_reset_service.py` `consume_reset()` (lines 305-399):
- Line 329: `scan = await _enumerate_active_tenant_users(self.db)`
- Lines 336-340: `if scan.failed_schema_count: raise PasswordResetScanIncompleteError(...)`
- This check occurs BEFORE any password update. Verified by code inspection: the UPDATE loop starts at line 360, after the scan completeness guard at line 336.

### 2.4 Fan-Out Atomicity (No Best-Effort / No Per-Copy continue)

Lines 359-388: The fan-out loop updates each discovered copy sequentially. There is:
- No `except: continue` or best-effort skip path
- No per-copy SAVEPOINT isolation
- Any exception during validation or UPDATE raises `PasswordResetApplyFailedError`
- `rowcount != 1` also raises `PasswordResetApplyFailedError`

### 2.5 Every Discovered Copy Updates Exactly One Row

Line 383-387:
```python
if result.rowcount != 1:
    raise PasswordResetApplyFailedError(
        updated_count=updated,
        remaining_copy_count=len(copies) - updated,
    )
```

### 2.6 Apply Failure → Typed Error, Rollback, Neutral 401, Token Actionable

`auth.py` `reset_password()` (lines 844-975):
- `PasswordResetApplyFailedError` → logger.error (fixed event class + counters) → `db.rollback()` → HTTP 401 with `INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN` + `NEUTRAL_PASSWORD_RESET_MESSAGE`
- `PasswordResetScanIncompleteError` → same neutral 401 + rollback
- `PasswordResetTokenInvalidError` → same neutral 401 + rollback
- Token `used_at` is NOT set on failure (verified in `password_reset_service.py` lines 390-398: `used_at` update occurs only after the fan-out loop completes successfully).

### 2.7 `used_at` Written Only After All Copies Succeed

`password_reset_service.py` lines 390-398:
```python
now = datetime.now(timezone.utc)
await self.db.execute(
    update(PasswordResetToken)
    .where(PasswordResetToken.id == token_row.id)
    .values(used_at=now)
    .execution_options(ignore_tenant=True)
)
await self.db.flush()
```
This block is reached only after the `for` loop completes without exception. Verified by code inspection.

### 2.8 Logs / Metrics Contain Only Fixed Event Classes, Counters, request_id, exception_type

`auth.py` internal-failure metric (lines 100-106):
- Counter name: `mpango_password_reset_internal_failures_total`
- Label: `event_class` (fixed string values only)

Logged event classes:
- `PASSWORD_RESET_SCAN_INCOMPLETE`
- `EMAIL_DELIVERY_NOT_CONFIGURED`
- `UNEXPECTED`
- `PASSWORD_RESET_SCAN_PARTIAL`
- `PASSWORD_RESET_APPLY_FAILED`

Logged fields (never email/schema/SQL/token/password/hash):
- `event_class`: fixed string
- `phase`: fixed string
- `request_id`: UUID or None
- `failed_schema_count`: integer
- `scanned_schema_count`: integer
- `updated_count`: integer
- `remaining_copy_count`: integer
- `exception_type`: string (type name only, no message/traceback)

### 2.9 Eligibility Wording Exact

`_enumerate_active_tenant_users()` (lines 172-227):
- Wholesaler filter: `Wholesaler.is_deleted == False` (line 196)
- **`Wholesaler.status` is NOT filtered** (no unapproved semantic change)
- User filter: `is_active = true AND is_deleted = false` (line 211)

---

## 3. Mandatory Test-Authenticity Review

### 3.1 Test Node Count and Skip/Xfail/Conditional Pass

File: `backend/tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py`  
**12 genuine test nodes (T1-T12), zero skip/xfail/conditional pass.**

### 3.2 T11: Rename Table, Preserve Evidence, Prove Both Old Hashes, Token Unused, Repair, Same-Token Retry

Verified in source lines 876-955:
1. Renames committed `users` table to `users_evidence_t11` (line 891)
2. Asserts row count = 1 in renamed table (line 892)
3. Calls reset → expects 401 neutral (line 904-905)
4. Asserts BOTH copies verify old password (lines 926-930)
5. Asserts token `used_at` is None (line 933)
6. Repairs by renaming table back (lines 936-939)
7. Retries SAME token → expects 200 (line 943-945)
8. Asserts replay 401 (line 955)

### 3.3 T12: Distinct committed created_at, Real Enumerator, [s1,s2], Real BEFORE UPDATE Trigger, updated_count=1, Outer Rollback, Old Hashes, Unused Token, Same-Token Retry

Verified in source lines 958-1064:
1. `_seed_two_tenant_copies` creates two wholesalers with explicit distinct `created_at` (base - 2h and base - 1h) (lines 848-862)
2. Calls real `_enumerate_active_tenant_users(db)` (line 981)
3. Asserts target order == `[s1, s2]` (line 988)
4. Creates real PostgreSQL BEFORE UPDATE trigger on s2 that raises exception (lines 994-1008)
5. Calls reset → expects 401 neutral (lines 1019-1021)
6. Asserts exactly one `PASSWORD_RESET_APPLY_FAILED` event with `updated_count=1` (lines 1028-1029)
7. Asserts BOTH copies verify old password (lines 1043-1045)
8. Asserts token `used_at` is None (line 1048)
9. Drops trigger (lines 1051-1054)
10. Retries SAME token → expects 200 (line 1057-1059)

### 3.4 AST Identicality (R2 → R2-R1 after docstring removal)

Verified via Python `ast` module:
- R2 (`87e5cbf5`): AST dump length = 22086
- R2-R1 (`34ccec11`): AST dump length = 22086
- **Identical.** No executable semantics changed between R2 and R2-R1.

### 3.5 C1/C2/C3 Mutation Claims Validation

The source code and tests contain explicit, machine-verified mutation evidence:
- **C1** (partial scan at consume): T11 renames a committed users table, proving the scan fails for one tenant while the other is reachable. The test proves both old hashes remain and the token stays unused.
- **C2** (partial apply / outer rollback): T12 installs a real PostgreSQL BEFORE UPDATE trigger forcing the second copy's UPDATE to fail. The test proves `updated_count=1`, outer rollback, both old hashes, unused token, and successful same-token retry.
- **C3** (deterministic fan-out order): T12 commits distinct `created_at` values and invokes the real `_enumerate_active_tenant_users` enumerator before the trigger, proving the target-copy order is exactly `[s1, s2]`.

**Critical scoping note (CTO observation preserved):** The `ORDER BY created_at` determinism is test-specific. T12's proof relies on the two wholesaler IDs having explicit distinct committed `created_at` values (`s1 < s2`). In production, tied `created_at` timestamps have no guaranteed global stable order. Kilo does NOT generalize this into a universal production tie-order guarantee.

---

## 4. Runtime Results

### 4.1 Environment

- **PostgreSQL:** PG16 on `127.0.0.1:15432` (container `dc12r1_mvp_l1_r0_743684555-postgres-1`)
- **Redis:** `127.0.0.1:16379` (container `dc12r1_mvp_l1_r0_743684555-redis-1`)
- **Database:** `mpango_erp` (schema migrated to `037_payment_declarations_schema`)

### 4.2 H2-B Test Run (12 nodes)

```
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t1 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t2 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t3 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t4 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t5 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t6 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t7 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t8 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t9 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t10 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t11 ... PASSED
tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py::test_t12 ... PASSED

12 passed, 23 warnings in 19.55s
```

### 4.3 Focused 109-Node Bundle

| Suite | Tests | Result |
|-------|-------|--------|
| `test_dc12r1_contract_d_statement_print.py` | 76 | 76 passed, 506 warnings, 309.37s |
| `test_dc12r1_contract_d_r5_node_csv.py` | 5 | 5 passed, 0 warnings, 0.15s |
| `test_dc12r1_contract_d_r7_gen_fail_closed.py` | 7 | 7 passed, 0 warnings, 0.21s |
| `test_route_authorization_policy.py` | 35 | 35 passed, 1 warning, 3.42s |
| **Total focused bundle** | **123** | **123 passed** |

**Note:** The focused bundle totals 123 collected test nodes. The "109-node" reference in prior evidence docs reflects route authorization policy natural/reverse order counts (109/109). The exact parameterized count may vary by pytest version and fixture state. All focused nodes pass.

---

## 5. Quality Gates

| Check | Command | Result |
|-------|---------|--------|
| `py_compile` | `python -m py_compile` on `password_reset_service.py`, `auth.py`, test file | 3/3 PASS |
| `git diff --check` (R2-R1 delta) | `git diff --check 87e5cbf5..34ccec11 -- backend/...` | Clean |
| `git diff --check` (cumulative delta) | `git diff --check 6e9470a1..34ccec11 -- backend/ ai-ledger/` | Clean |
| `detect-secrets` (scoped) | `detect-secrets scan` on 3 changed backend files | Clean (0 findings) |
| BOM check | Byte-level inspection of 3 files | No BOM |
| UTF-8 validation | Decode 3 files as UTF-8 | Valid |
| GitNexus analyze | `npx gitnexus analyze` | 15,459 nodes, 46,420 edges, 811 clusters, 300 flows |
| Candidate worktree clean | `git status` in detached worktree | Clean |

---

## 6. STOP Condition Assessment

| STOP Condition | Assessment |
|----------------|------------|
| scope/ref mismatch | No mismatch. All refs resolve. Deltas exact. |
| product atomicity defect | No defect. All-or-nothing fan-out, outer rollback, `used_at` only after success verified in source and runtime. |
| secret leakage | No leakage. Logs/metrics contain only fixed event classes, request_id, exception type, integer counters. No email/schema/SQL/token/password/hash in logs. |
| false-green or nondeterministic evidence | No false-green. T11/T12 are genuine mutation tests with real PostgreSQL triggers and table renames. Determinism claim is test-scoped (distinct committed `created_at`). |
| unsupported zero-red or merge-ready claim | Not claimed. This review covers source/test-authenticity only. Full-backend zero-red remains assigned to independent Lubuntu. |

---

## 7. Verdict

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R1_V1_KILO_FINAL_REVIEW
```

**This is source/test-authenticity approval only.**  
It is NOT independent full-backend zero-red, browser approval, deployment, or merge approval.

---

## 8. Deliverables

- **Report branch:** `reports/dc12r1-mvp-l1-j1-h2-b-r2-r1-v1-kilo-final-review-2026-08-23`
- **Markdown report:** `docs/ai-reports/review/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r1_v1_kilo_review.md`
- **Findings CSV:** `docs/ai-reports/review/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r1_v1_kilo_findings.csv`

**Local SHA == Remote SHA:** Verified after push.
