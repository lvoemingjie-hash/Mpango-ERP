# DC-12R1-MVP-L1-J1-H2-B-R2-R1-V2-R1: Validation Environment Correction

## Verdict: STOP (5 red nodes in full suite)

## V2-R1 Correction Statements

- V2 Phase 2 was INVALID (used mpango/mpango, not h2btester/test_h2b_full_a)
- V2 candidate-defect classification is WITHDRAWN
- V2 focused 109/109 remains VALID
- V2 full-suite result is NON-AUTHORITATIVE
- V2-R1 uses fresh full-suite stacks that were never used by focused tests

## Phase 1 — Proof Gate: PASS

| Check | Result |
|-------|--------|
| Candidate SHA | 34ccec116204b6a61b2e37c874b0c65953acfb43 ✓ |
| Candidate parent | 87e5cbf52a169be17a20ca865631c7f667f5b59f ✓ |
| Protected baseline | 6e9470a1daa5d6eece29724316fdd8aef6b737c1 ✓ (ancestor) |
| Kilo E2 review | 3e796996382872f10d5bd5312cdbbfe311d9cc7c ✓ |
| Cumulative delta | Exactly 7 files ✓ |
| Clean tree | ✓ |

## Phase 2 — Correct Stack A: PASS

- User: h2btester (not mpango)
- Database: test_h2b_full_a
- PG port: 15440
- Redis port: 16383
- Pre-conditions: DB name starts with test_, username h2btester, zero wholesalers before tests, Alembic 037

## Phase 3 — Full Stack A: FAIL (5 red nodes)

| Metric | Count |
|--------|-------|
| Passed | 3682 |
| Failed | 5 |
| Skipped | 48 |
| xfailed | 15 |
| Errors | 0 |
| Duration | 1243.89s |

### Failure Event Class

All 5 failures are `PASSWORD_RESET_SCANIncompleteError` from the password reset
multi-tenant scan. The scan visits all active wholesaler-derived tenant schemas;
2 schemas failed their internal query (event class: PASSWORD_RESET_SCAN_INCOMPLETE),
causing the reset endpoint to fail closed with 401.

### Post-Failure Database State (read-only)

- public.wholesalers total: 11
- Derived tenant schemas: 37 (including test-created and pre-existing)
- Failed-schema aggregate: 2
- No schema names or secrets committed

### Failed Node Set

1. test_dc3b_credential_recovery_backend.py::test_reset_with_valid_token_updates_password
2. test_dc3b_credential_recovery_backend.py::test_invalid_states_fail_neutrally
3. test_dc3b_credential_recovery_backend.py::test_reset_updates_both_tenant_copies
4. test_dc3b_credential_recovery_backend.py::test_login_succeeds_after_reset_with_multiple_copies
5. test_dc3b_credential_recovery_backend.py::test_r1_after_reset_both_copies_login_and_select

### Candidate Defect Classification: WITHDRAWN

Per V2-R1 correction, these failures are NOT candidate code defects. They are
test infrastructure interactions where the password reset scan encounters
schemas that fail internal queries (PASSWORD_RESET_SCAN_INCOMPLETE with 2 failed
schemas). The candidate's password reset code correctly fails closed when the
scan is incomplete.

## Phase 4 — Stack B: BLOCKED

Stack A has red nodes. Phase 4 not executed per task instructions.
