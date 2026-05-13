# Stabilization Cycle 1C Revision — Search Path Production Seam Hardening

Date: 2026-05-09
Branch: ops/integration-rehearsal-clean-2026-05-08
Worktree: C:\Users\Jeff0\MPANGO ERP\product-dev-recovered-review
Agent: Goose
Status: FIX VERIFIED — all 3 test suites green, awaiting CTO commit approval

---

## Scope

Single file: `backend/database/session.py` (+38 lines, -6 lines, net +32)

## GitNexus Impact

| Symbol | d=1 Callers (prod) | Risk |
|--------|---------------------|------|
| `get_db` | 2 | LOW — additive defensive code |
| `get_tenant_db` | 1 | LOW — additive defensive code |
| `_reset_search_path_before_close` | NEW private helper | NONE |

No HIGH/CRITICAL risk.

## Changes

### 1. New helper: `_reset_search_path_before_close(session)`

```python
async def _reset_search_path_before_close(session: AsyncSession) -> None:
    await session.execute(text("SET search_path TO public"))
    await session.commit()          # <-- 关键：提交 RESET，不留隐式事务
```

### 2. `get_db()` — defensive open + reliable cleanup

- **Open**: `SET search_path TO public` — 无论连接池状态如何，确保干净起点
- **Cleanup**: 调用 helper → `SET + COMMIT` → `session.close()`
- **Exception handling**: `original_exc` 模式 — 仅在原始异常飞行时抑制清理失败

### 3. `get_tenant_db()` — rollback + defensive reset

- **Exception path**: rollback（清除 SET LOCAL）→ helper（defensive reset + commit）
- **Normal path**: commit → helper（defensive reset + commit）
- **Cleanup**: 与 get_db() 共用 helper，确保一致性

## Revision Highlights vs Cycle 1C v1

| Issue | v1 | v2 (this) |
|-------|----|-----------|
| RESET opens implicit tx | `RESET search_path` (no commit) | `SET search_path TO public` + **COMMIT** |
| Silent failure swallowing | `except Exception: pass` | `original_exc` pattern — only suppress when original in flight |
| Duplicated cleanup | inline in both functions | extracted `_reset_search_path_before_close()` |
| Exception type | `except Exception` | `except BaseException` (catches CancelledError etc.) |

## Unified PostgreSQL Environment Verification

### Environment
- POSTGRES_HOST=localhost (Docker container mpango_postgres, port 5432)
- POSTGRES_USER=mpango / POSTGRES_DB=mpango_erp
- REPORTING_USER_PASSWORD=ReportingPass_ci_2026
- reporting_user role: confirmed exists, can login, password matches

### Test Suite 1: Tenant Isolation
```
tests/test_tenant_isolation.py — 4 passed, 0 failed
```

### Test Suite 2: DB Critical Subset (143 tests)
```
tests/test_global_tenant_filter.py ......
tests/test_search_path.py .
tests/test_schema_security.py ......
tests/test_tenant_isolation.py ....
tests/test_platform_audit.py ..................
tests/test_platform_audit_api.py ...............................
tests/test_platform_p0.py .............
tests/test_platform_stats_api.py ..........
tests/test_phase5_order_payment.py ..............................x......
tests/test_payment_atomicity.py ..
tests/test_payments_api.py .....

142 passed, 1 xfailed, 0 failed
```

### Test Suite 3: Reporting Suites (13 tests)
```
tests/test_s6_p_reporting_constraints.py ........
tests/test_s6_2_materialized_views.py .....

13 passed, 0 failed
```
(Run with `POSTGRES_HOST=localhost REPORTING_USER_PASSWORD=ReportingPass_ci_2026`)

## CTO Required Result Checklist

| Requirement | Result |
|-------------|--------|
| tenant isolation: all pass | ✅ 4/4 |
| DB critical subset: all pass except known xfail | ✅ 142 passed, 1 xfailed |
| reporting_user suites: all pass | ✅ 13/13 |
| no new failures introduced by session.py | ✅ confirmed |

## Runtime Verification

- [x] search_path leak eliminated at runtime
- [x] `test_public_session_has_no_tenant_schema` passes in full suite
- [x] All 142 critical DB tests green
- [x] All 13 reporting_user tests green
- [x] No business logic touched
- [x] No payment/order code touched

## Confirmations

- [x] No commit
- [x] No push
- [x] Only `session.py` modified
- [x] No merge into product-dev-recovered
- [x] No `git reset --hard`
- [x] `resolve_conflict.py` not staged

## Next Step

Awaiting CTO commit approval.
