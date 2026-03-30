# Track E1 Backend Ledger Record

- **Time (UTC+08)**: 2026-02-15 18:53
- **Topic**: Tenant Guardrail Hardening (v0.2.0)

---

## PLAN

1. Harden backend tenant isolation so ORM queries fail closed when tenant context is missing.
2. Enforce tenant-key predicates for tenant-keyed models (`tenant_id` / `wholesaler_id`).
3. Add explicit, auditable system-scope bypass for public flows that are legitimately cross-tenant.
4. Provide architecture documentation and red-test proof of protection.

---

## EXECUTION

### Files Updated

- `backend/db/tenant_filter.py`
- `backend/services/invitation_service.py`
- `backend/services/retailer_service.py`
- `backend/tests/test_global_tenant_filter.py`
- `backend/tests/b6_hardening/test_b6_global_tenant_filter.py`
- `docs/arch/tenant-isolation.md`

### Key Changes Delivered

1. Added strict guardrail exception type and fail-safe checks:
   - `TenantContextMissingError`
   - missing `tenant_schema` => hard error
   - missing `tenant_id` for tenant-keyed queries => hard error
   - invalid UUID tenant_id for `wholesaler_id` filter => hard error
2. Added/used explicit bypass wrapper:
   - `run_as_system(reason="...")`
   - applied in public invitation lookup and retailer registration flows
3. Strengthened ORM tenant criteria:
   - automatic filter for `tenant_id`
   - automatic UUID-validated filter for `wholesaler_id`
4. Added red tests:
   - Orders-like (`wholesaler_id`) query with `tenant_schema` present but missing `tenant_id` now asserts `TenantContextMissingError`
5. Added architecture note:
   - request-scoped context lifecycle
   - ORM interception and fail-safe behavior
   - bypass policy and approved public-flow usage

### Commands Executed

```bash
pytest tests/test_global_tenant_filter.py tests/b6_hardening/test_b6_global_tenant_filter.py -q
```

Additional environment checks attempted:

```bash
pytest backend/tests/test_global_tenant_filter.py backend/tests/b6_hardening/test_b6_global_tenant_filter.py -q
pytest tests/test_s5_order_state_machine.py -q
```

---

## EVIDENCE

### Guardrail Test Suite Pass (backend cwd)

```text
collected 12 items

tests\test_global_tenant_filter.py ......                       [ 50%]
tests\b6_hardening\test_b6_global_tenant_filter.py ......      [100%]

12 passed, 1 warning in 0.33s
```

### Root-level pytest import/config failure (captured)

```text
pydantic_core._pydantic_core.ValidationError: 5 validation errors for Settings
VITE_V0_API_KEY ... Extra inputs are not permitted
VITE_API_URL ... Extra inputs are not permitted
POSTGRES_USER ... Extra inputs are not permitted
POSTGRES_PASSWORD ... Extra inputs are not permitted
ENVIRONMENT ... Extra inputs are not permitted
```

### Full S5 state-machine suite DB credential failure (captured)

```text
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "mpango"
...
3 passed, 1 warning, 10 errors in 6.44s
```

---

## Session 2: 2026-02-15 19:23–19:55 — Troubleshooting & Final Fix

### Root Cause Analysis

**Issue**: When `test_global_tenant_filter.py` (sync, SQLite) ran before `test_s5_order_state_machine.py` (async, PostgreSQL), every `OrderService.transition()` call failed with `ValueError: Order ... not found`.

**SQL evidence** (DATABASE_ECHO):
```sql
SELECT ... FROM orders
WHERE orders.id = $1::UUID AND orders.is_deleted = false
  AND orders.wholesaler_id = $2::UUID FOR UPDATE
-- params: (UUID('...'), None)   ← wholesaler_id bound to None!
```

**Mechanism**: `_maybe_apply_tenant_id_criteria()` used `with_loader_criteria(DeclarativeBase, lambda, track_closure_variables=False)`. SQLAlchemy cached the generated SQL fragment keyed on the entity class. When the sync guardrail test ran first with `tenant_id="t1"` (not a valid UUID), the cached fragment carried a `bindparam("mpango_tenant_uuid")` whose value resolved to `None` on subsequent async queries — even though the async session had a valid UUID in `session.info["tenant_id"]`.

### Fixes Applied

| # | File | Change |
|---|------|--------|
| 1 | `backend/db/tenant_filter.py` | Replaced `with_loader_criteria(DeclarativeBase, ...)` with direct `stmt.where()` injection per mapper. Eliminates SQLAlchemy's internal lambda caching — each execution evaluates fresh. |
| 2 | `backend/pytest.ini` | Added `asyncio_default_fixture_loop_scope = session` and `asyncio_default_test_loop_scope = session` so `-o` flags are no longer needed. |
| 3 | `backend/core/config.py` | Verified `extra="ignore"` already present (fixed in earlier session). |

### Verification

```text
pytest tests/test_global_tenant_filter.py tests/b6_hardening/test_b6_global_tenant_filter.py \
      tests/test_s5_order_state_machine.py tests/test_s5_ledger.py tests/test_s5_5_ledger_hardening.py -q

collected 48 items

tests\test_global_tenant_filter.py ......                      [ 12%]
tests\b6_hardening\test_b6_global_tenant_filter.py ......      [ 25%]
tests\test_s5_order_state_machine.py .............             [ 52%]
tests\test_s5_ledger.py ............                           [ 77%]
tests\test_s5_5_ledger_hardening.py ...........                [100%]

48 passed, 1 warning in 10.72s
```

Extended scope (orders API, order creation, search_path, security):
```text
89 passed, 1 warning in 11.88s
(1 unrelated failure: ModuleNotFoundError: No module named 'redis' — pre-existing, not Track E1)
```

---

## Outcome

Track E1 tenant guardrail hardening is **COMPLETE**:
- Architecture doc ✅
- Enforcement code (fail-closed guardrail + explicit bypass) ✅
- Red tests (12 guardrail + 36 S5 order/ledger) ✅
- Cross-test contamination bug fixed ✅
- Pydantic `extra="ignore"` verified ✅
- pytest.ini asyncio loop scope baked in ✅
