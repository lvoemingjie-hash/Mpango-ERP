# MPANGO-MVP-INVARIANTS-R0-R2 运行记录（2026-09-07）

> R2 修订版：闭合 CTO 对 R1 候选（a511369e）裁决的 F1（409 被捕获后误 commit）与
> F2（按 reason 建字典掩盖重复流水）两处测试缺口。R1 运行记录保留于 git 历史
> （R1：容器 mpango-zcode-inv-r0r1-20260907-pg，32 节点，25 PASS + 7 RED）。

## R2 任务独占环境

- 容器：`mpango-zcode-inv-r0r2-20260907-pg`，镜像 postgres:16-alpine，`127.0.0.1:57435`，标签 `mpango.owner=zcode-mvp-invariants-r0-r2`（任务归属证明在每次运行的会话夹具中核验）。
- 运行时：Python 3.12.10、SQLAlchemy 2.0.45、asyncpg 0.31.0、FastAPI 0.128.0、pytest 8.4.2、pytest-asyncio 0.26.0；MPANGO_ENV=staging；REDIS_URL=redis://127.0.0.1:1/15（不可达）；SECRET_KEY 为合成 64 位十六进制。
- 迁移：由会话夹具在归属证明通过后对核验目标执行 `alembic upgrade head`，并核对 head == `037_payment_declarations_schema`。全程无手工 alembic 调用，无 alembic.ini 默认地址路径。

## R2 开发期运行（逐次记录原因）

| # | 范围 | 结果 | 原因/处置 |
|---|---|---|---|
| 1 | guards 文件 | 25 PASS | 共享 `assert_adjustment_chain` 的 9 个正反例首跑即通过（R2 自造链式重复坏快照：折叠快照经 ALGEBRA 拒绝、原始三行经 SET 拒绝。**2026-09-08 R1 轮按 CTO O1 更正**：该组行并非 CTO 原反例；CTO 精确原反例 A(17→22)×2、B(10→17) 的折叠形态与合法 B→A 链不可区分、必须接受，已另立对照补入）。 |
| 2 | concurrency 全文件 | 4 FAILED / 3 PASSED | 两个夹具缺陷：① 单次调整对照残留旧 dict API（`.values()` 对 list 失效）→ 改列表索引；② **新对照阶段 3 自身犯了 F1 同型错误**——`pytest.raises` 放在会话上下文内部捕获 RuntimeError，上下文正常退出走了 commit，探针行存活。处置：raises 移到事务上下文之外（异常逃逸→回滚→再捕获），并在测试 docstring 记录该教训。两个 RED 保持原命名原值。 |
| 3 | concurrency 全文件重跑 | 5 PASSED / 2 FAILED（预期 RED） | F1 回归对照（拒绝请求暂存写入零残留 + 后续请求可提交 + 未知异常传播回滚）通过。 |
| 4 | revocation 全文件 | 5 命名 RED + 3 对照 PASS | 与 R1 一致（本轮未改该文件）。 |

## R2 最终完整运行（三文件一次运行）

命令：`pytest tests/test_mpango_invariants_r0_r1_guards.py tests/test_mpango_mvp_invariants_r0_concurrency.py tests/test_mpango_mvp_invariants_r0_revocation.py --no-header -rA`
**退出码：1**（存在产品命名 RED 时的预期退出码）；耗时 59.12s。脱敏输出不含凭据。

逐节点结果（40 节点）：

产品命名 RED（7，全部预期）：
```
FAILED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_red_concurrent_stock_adjustments_no_lost_update        (INVARIANT_R0_STOCK_LOST_UPDATE: got 15.00)
FAILED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_red_concurrent_full_return_single_economic_effect      (INVARIANT_R0_DOUBLE_RETURN: refund cash -200.0000)
FAILED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_soft_deleted_user_in_active_tenant_denied           (INVARIANT_R0_SOFT_DELETED_USER_ACCESS: 200)
FAILED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_active_user_in_suspended_tenant_denied              (INVARIANT_R0_SUSPENDED_TENANT_ACCESS: 200)
FAILED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_refresh_nonexistent_principal_no_session            (INVARIANT_R0_REFRESH_NONEXISTENT_PRINCIPAL)
FAILED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_refresh_soft_deleted_user_no_session                 (INVARIANT_R0_REFRESH_DELETED_USER)
FAILED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_refresh_suspended_tenant_no_session                  (INVARIANT_R0_REFRESH_SUSPENDED_TENANT)
```

生命周期/焦点/事务对照（8 PASS）：
```
PASSED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_control_single_adjustment_and_failed_adjustment_rollback
PASSED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_control_single_full_return_single_economic_effect
PASSED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_control_rejected_return_rolls_back_staging_write   (R2/F1 回归)
PASSED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_harness_control_barrier_timeout_cancels_and_rolls_back
PASSED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_harness_control_task_exception_rolls_back_and_cleans
PASSED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_control_active_user_active_tenant_can_access
PASSED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_control_deactivated_user_denied
PASSED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_control_refresh_live_subject_issues_usable_session
```

守卫与断言逻辑单测（25 PASS；归属负控 3、JWT 工厂 9、退货结果契约 4、调整链共享助手正反例 9——R2/F2）：
```
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_refuses_missing_ownership_config
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_refuses_disagreeing_targets
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_refuses_non_task_owner_label
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_mock_for_every_test_variant[test / TEST / " test " / \tTest / "TeSt "]   (5 参数化)
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_jwt_for_non_test_variants[staging / " STAGING " / production / Production]  (4 参数化)
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_logic_accepts_serialized_duplicate_return
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_logic_accepts_rejected_duplicate_return
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_logic_rejects_arbitrary_error_outcome
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_logic_rejects_double_economic_effect
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_chain_accepts_b_then_a_serial_order          (10→17→22)
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_chain_accepts_a_then_b_serial_order          (10→15→22)
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_chain_rejects_duplicate_reason_rows          (CTO F2 三行原始形态)
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_chain_rejects_duplicate_collapsed_to_two     (R2 自造链式重复坏快照；R1 轮按 CTO O1 更名并更正措辞)
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_chain_rejects_unknown_reason
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_chain_rejects_missing_movement
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_chain_rejects_wrong_final_value
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_chain_rejects_wrong_single_row_algebra
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_chain_rejects_lost_update_journal
```

汇总：**33 PASSED + 7 FAILED（全部为产品命名 RED）**。无 skip/xfail，无未知失败。

## R2 安全演练与残留核查

- 归属拒绝演练（错误容器声明）：`GUARD_REFUSED_DATABASE_OWNERSHIP`，演练后 `t_%` schema = 0（零写入）。
- 最终运行后核查：`t_%` schema = 0、public.wholesalers = 0、retailers = 0。F1 探针行（reference_type='r0-harness-probe'）位于各租户 schema 内，schema 全部级联删除即为失败请求零残留的库级证明；控制测试内部另在 schema 存活时直接断言探针行数为 0。
- 未触碰既有容器/库/卷；容器删除经标签核验。

## 新增/修改节点与真实 helper 对应（CTO F1/F2 要求）

| 节点 | 调用的真实 helper |
|---|---|
| control_rejected_return_rolls_back_staging_write（新增） | `_return_outcome`（F1 修订后的事务对齐实现）+ `_insert_probe_write`/`_probe_movement_count`（夹具探针）+ `_assert_single_economic_effect` |
| red_concurrent_full_return_single_economic_effect（修订） | 同上 `_return_outcome`（A、B 两请求均走修订后事务路径） |
| red_concurrent_stock_adjustments_no_lost_update（修订） | `adjustment_movements`（list）+ `assert_adjustment_chain`（共享助手） |
| guards 9 个调整链对照（2 正例改写 + 7 反例新增） | `assert_adjustment_chain`（同一共享助手，无平行实现） |
| guards 4 个退货契约对照（保留） | `_assert_outcomes_contractual` / `_assert_single_economic_effect`（真实测试同款） |

---
R1 轮的完整开发运行记录、安全演练明细与 32 节点逐项结果保留于 git 历史（a511369e 的本文件）。
