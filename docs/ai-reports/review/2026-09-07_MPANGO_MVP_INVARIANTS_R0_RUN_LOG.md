# MPANGO-MVP-INVARIANTS-R0 运行记录（2026-09-07）

任务独占环境：docker 容器 `mpango-zcode-inv-r0-20260907-pg`（postgres:16-alpine，127.0.0.1:61310，标签 mpango.owner=zcode-mvp-invariants-r0）；公共迁移至 `037_payment_declarations_schema`；MPANGO_ENV=staging；REDIS_URL 指向不可达地址；Python 3.12.10 / SQLAlchemy 2.0.45 / asyncpg 0.31.0 / FastAPI 0.128.0 / pytest 8.4.2 / pytest-asyncio 0.26.0。

多次运行（≥3 次，含逐项调试运行与两次完整运行）结果确定一致。以下为完整运行的逐项结果：

```
tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_control_single_adjustment_and_failed_adjustment_rollback PASSED
tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_red_concurrent_stock_adjustments_no_lost_update FAILED
tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_control_single_full_return_single_economic_effect PASSED
tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_red_concurrent_full_return_single_economic_effect FAILED
tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_control_active_user_active_tenant_can_access PASSED
tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_control_deactivated_user_denied PASSED
tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_soft_deleted_user_in_active_tenant_denied FAILED
tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_active_user_in_suspended_tenant_denied FAILED
tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_refresh_nonexistent_principal_no_session FAILED
tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_refresh_soft_deleted_user_no_session FAILED
tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_refresh_suspended_tenant_no_session FAILED
tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_control_refresh_live_subject_issues_usable_session PASSED

====== 7 failed, 5 passed in ~50s ======
```

全部 7 个 FAILED 均为预期命名 RED（目标缺陷复现），断言消息以 `INVARIANT_R0_` 开头；全部 5 个 PASSED 为正常对照。无未知失败，无 skip/xfail。

## 命名 RED 实测值

| 命名 | 实测 | 预期（不变量） | 外部对照值 |
|---|---|---|---|
| INVARIANT_R0_STOCK_LOST_UPDATE | 10+7+5 → 15.00 | 22.00 | 外部 15 一致 |
| INVARIANT_R0_DOUBLE_RETURN_CASH | refund cash −200.0000（revenue +200） | −100.0000 | 外部 −200 一致 |
| INVARIANT_R0_SOFT_DELETED_USER_ACCESS | GET /api/v1/skus → 200 | 401 | 外部 200 一致 |
| INVARIANT_R0_SUSPENDED_TENANT_ACCESS | GET /api/v1/skus → 200 | 401 | 外部 200 一致 |
| INVARIANT_R0_REFRESH_NONEXISTENT_PRINCIPAL | 返回新 token 对 | 401 拒绝 | 外部 issued=true 一致 |
| INVARIANT_R0_REFRESH_DELETED_USER | 返回新 token 对 | 401 拒绝 | 本轮扩展场景 |
| INVARIANT_R0_REFRESH_SUSPENDED_TENANT | 返回新 token 对 | 401 拒绝 | 本轮扩展场景 |

## 开发期调试记录（夹具修正，未改任何预期）

1. `mpango_invariants_r0_support.adjustment_movements`：SELECT 列 `created_at/id` 未限定表名导致 ambiguous column（asyncpg AmbiguousColumnError）→ 限定 `m.` 前缀。属夹具 SQL 错误，非产品缺陷，非预期修改。
2. 并发退货屏障判断初版用 tenant_schema 匹配（A/B 两会话同 schema 均会暂停）→ 改为 `db is db_a` 会话同一性判断。
3. refresh RED 断言初版按"返回错误响应"设计 → 端点实际抛 HTTPException，改为 try/except + 命名 fail 助手，保证基线上 RED 消息携带不变量名。

## 环境守卫验证

- 非本机 DATABASE_URL → 测试在 setup 阶段失败（MPANGO_INVARIANTS_R0_ENV_GUARD）。
- MPANGO_ENV=test（会选 MockAuthStrategy）→ 撤权文件 setup 阶段失败。
- 任务库残留核查：运行后 `t_%` schema=0、public.wholesalers/retailers=0（各测试 finally 自清理）。
