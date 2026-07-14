# DC-11P1 Platform Operator Schema Foundation

| Field | Value |
|---|---|
| Date | 2026-07-14 |
| Task ID | DC-11P1 (Platform Operator Schema Foundation) |
| Revision | R1 (portability, schema qualification, email normalization, index parity) |
| Base | `origin/product-dev-recovered @ cb1b1fffc63ed19e320701043eed38b8f2bea0c7` |
| Branch | `opencode/dc11p1-platform-operator-schema-2026-07-14` |
| R0 commit | `62f1340c` |
| Verdict | `PASS_FOR_CTO_DC11P1_MERGE_REVIEW` |

## 1. Scope

Schema/model foundation only. No authentication, service, guard, login, or
runtime behavior changes. Four additive public-schema tables created.

## 2. Changed Files

### R0 commit (62f1340c): 6 files

| File | Change |
|---|---|
| `backend/alembic/versions/034_platform_operators.py` | New migration (4 tables) |
| `backend/models/platform_operator.py` | 4 ORM models |
| `backend/models/__init__.py` | Export 4 new models |
| `backend/tests/test_dc11p1_platform_operator_schema.py` | 24 DB-backed tests |
| `backend/tests/test_dc11p0_platform_operator_identity_contract.py` | Updated: absent -> present |
| `ai-ledger/product-ai/2026-07-14_dc11p1_platform_operator_schema.md` | This ledger |

### Full branch diff from product baseline (cb1b1fff): 7 files

| File | From |
|---|---|
| `ai-ledger/product-ai/2026-07-14_dc11p0_platform_operator_identity_credential_contract.md` | DC-11P0 contract |
| `ai-ledger/product-ai/2026-07-14_dc11p1_platform_operator_schema.md` | This ledger |
| `backend/alembic/versions/034_platform_operators.py` | New migration |
| `backend/models/__init__.py` | Modified (exports) |
| `backend/models/platform_operator.py` | New models |
| `backend/tests/test_dc11p0_platform_operator_identity_contract.py` | Modified |
| `backend/tests/test_dc11p1_platform_operator_schema.py` | New tests |

## 3. R1 Corrections

### 3.1 Explicit public schema
- Migration: every `create_table`, `create_index`, `drop_table` uses `schema="public"`.
- FKs reference `public.platform_operators.id`.
- ORM: every model `__table_args__` includes `{"schema": "public"}`.
- Tests: all `information_schema`/`pg_catalog` queries filter `table_schema='public'`.
- Test proves no same-named table exists in any tenant schema.

### 3.2 Email normalization
- Migration + ORM CHECK: `email = lower(btrim(email)) AND length(btrim(email)) > 0`.
- One UNIQUE constraint on email (the normalization CHECK enforces stored form).
- Removed the redundant unique index on `lower(trim(email))`.
- Tests: mixed-case, whitespace-padded, empty, whitespace-only all rejected.

### 3.3 ORM/DDL index parity
- ORM `Index()` definitions added for `ux_setup_tokens_operator_active`,
  `ux_reset_tokens_operator_active`, `ux_recovery_credentials_operator_active`.
- Test verifies expected index names exist in both ORM metadata and pg_catalog.

### 3.4 Portable DB gate
- Removed hardcoded DB URL from tests.
- Uses `TEST_DATABASE_URL` then `DATABASE_URL`.
- Refuses known production DB names (`mpango_erp`, `mpango`, `mpango_prod`).
- Skips with clear reason when no disposable DB is available.
- Never prints the URL or credentials.

### 3.5 Security column tests strengthened
- Setup/reset tables: asserts absence of forbidden token-like column names
  and presence of `token_hash`.
- Recovery table: asserts absence of forbidden credential-like column names
  and presence of `credential_hash`.
- Token hash uniqueness within each table verified.
- Expired-token lifecycle-active behavior preserved.

### 3.6 Migration-history evidence
- Replaced the misleading byte-integrity test with static checks:
  - `revision` is `034_platform_operators`.
  - `down_revision` is `033_order_status_enum_reconciliation`.
  - Migration imports no runtime model/service/api modules.
- Actual proof of unmodified historical migrations:
  `git diff --name-only cb1b1fff..HEAD -- backend/alembic/versions`
  outputs only: `backend/alembic/versions/034_platform_operators.py`.

### 3.7 Ledger accuracy
- R0 commit changed 6 files.
- Full branch diff from baseline: 7 files (including DC-11P0 contract).
- No claim of byte-identity proof via tests; the proof is `git diff`.

## 4. Migration

- Revision: `034_platform_operators`
- Down revision: `033_order_status_enum_reconciliation`
- Single Alembic head after upgrade: `034_platform_operators`
- Additive only: no existing tables modified
- Downgrade drops all 4 tables cleanly (verified: 0 tables remain)
- Re-upgrade succeeds

## 5. Test Results

| Suite | Count |
|---|---|
| `test_dc11p1_platform_operator_schema.py` | 36 passed |
| `test_dc11p0_platform_operator_identity_contract.py` | 16 passed |

## 6. Verdict

**PASS_FOR_CTO_DC11P1_MERGE_REVIEW**
