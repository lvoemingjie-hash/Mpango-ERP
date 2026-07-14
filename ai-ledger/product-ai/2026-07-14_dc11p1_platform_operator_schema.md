# DC-11P1 Platform Operator Schema Foundation

| Field | Value |
|---|---|
| Date | 2026-07-14 |
| Task ID | DC-11P1 (Platform Operator Schema Foundation) |
| Base | `origin/product-dev-recovered @ cb1b1fffc63ed19e320701043eed38b8f2bea0c7` |
| Branch | `opencode/dc11p1-platform-operator-schema-2026-07-14` |
| Predecessor | DC-11P0-R2 contract (`087848f2`) |
| Verdict | `PASS_FOR_CTO_DC11P1_MERGE_REVIEW` |

## 1. Scope

Schema/model foundation only. No authentication, service, guard, login, or
runtime behavior changes. Four additive public-schema tables created.

## 2. Changed Files

| File | Change |
|---|---|
| `backend/alembic/versions/034_platform_operators.py` | New migration (4 tables, constraints, indexes) |
| `backend/models/platform_operator.py` | 4 ORM models (PlatformOperator, SetupToken, ResetToken, RecoveryCredential) |
| `backend/models/__init__.py` | Export 4 new models |
| `backend/tests/test_dc11p1_platform_operator_schema.py` | 24 DB-backed schema tests |
| `backend/tests/test_dc11p0_platform_operator_identity_contract.py` | Updated: absent assertions -> present assertions |

## 3. Migration

- Revision: `034_platform_operators`
- Down revision: `033_order_status_enum_reconciliation`
- Single Alembic head after upgrade: `034_platform_operators`
- Additive only: no existing tables modified
- Downgrade drops all 4 tables cleanly

## 4. Schema Summary

### platform_operators
- UUID PK, email (unique, normalized), password_hash, status, role,
  failed_login_attempts, locked_until, auth_version, last_login_at,
  revoked_at, invited_by (self-FK SET NULL), AuditMixin.
- CHECK constraints: status, role, failed_login_attempts >= 0,
  auth_version >= 1, active requires password_hash, active not revoked.
- Unique index on lower(trim(email)).

### platform_operator_setup_tokens
- UUID PK, operator_id (FK CASCADE), token_hash (unique), purpose='setup',
  expires_at, used_at, revoked_at, AuditMixin.
- CHECK: purpose='setup', used_at and revoked_at not both set.
- Partial unique index: one lifecycle-active token per operator.

### platform_operator_reset_tokens
- Same structure as setup_tokens with purpose='reset'.

### platform_operator_recovery_credentials
- UUID PK, operator_id (FK CASCADE), credential_hash (unique), status,
  used_at, revoked_at, AuditMixin.
- CHECK: status in (active, used, revoked), state-consistency constraint.
- Partial unique index: one active credential per operator.

## 5. No Plaintext Token Columns

Verified by test: no column named `token`, `raw_token`, or any token-like
column other than `token_hash` exists in any of the three token tables.

## 6. Migration Byte-Unchanged Proof

Migrations 001-033 are unmodified. The only new migration file is
`034_platform_operators.py`. No existing migration file was edited.

## 7. Test Results

| Suite | Count |
|---|---|
| `test_dc11p1_platform_operator_schema.py` | 24 passed |
| `test_dc11p0_platform_operator_identity_contract.py` | 16 passed |

## 8. GitNexus Impact

PublicBaseModel impact: CRITICAL (109 nodes) -- expected, as it is the base
class for all models. DC-11P1 is ADDITIVE only (new models, no base-class
modification). The CRITICAL rating confirms we must not modify PublicBaseModel.

## 9. Stop Conditions

- Baseline drift: no (cb1b1fff confirmed).
- Alembic head: 033 before, 034 after (single head).
- 034 unused before: confirmed.

## 10. Verdict

**PASS_FOR_CTO_DC11P1_MERGE_REVIEW**
