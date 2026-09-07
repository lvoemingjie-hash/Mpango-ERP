# MPANGO-MVP-INVARIANTS-R0-R1 运行记录（2026-09-07）

> R1 修订版：按 CTO 修订指令补充开发运行分类、安全演练与最终完整运行的脱敏结果。
> R0 运行记录保留于 git 历史（R0：容器 mpango-zcode-inv-r0-20260907-pg，12 节点，5 PASS + 7 RED）。

## R1 任务独占环境

- 容器：`mpango-zcode-inv-r0r1-20260907-pg`，镜像 postgres:16-alpine，`127.0.0.1:52639`，标签 `mpango.owner=zcode-mvp-invariants-r0-r1`（任务归属证明在每次运行的会话夹具中核验）。
- 运行时：Python 3.12.10、SQLAlchemy 2.0.45、asyncpg 0.31.0、FastAPI 0.128.0、pytest 8.4.2、pytest-asyncio 0.26.0；MPANGO_ENV=staging；REDIS_URL=redis://127.0.0.1:1/15（不可达）；SECRET_KEY 为合成 64 位十六进制。
- 迁移：由会话夹具在归属证明通过后对核验目标执行 `alembic upgrade head`，并核对 head == `037_payment_declarations_schema`。全程无手工 alembic 调用，无 alembic.ini 默认地址路径。

## 开发期运行（夹具迭代，逐次记录原因）

| # | 范围 | 结果 | 原因/处置 |
|---|---|---|---|
| 1 | guards 文件 | 11 PASS / 1 FAILED | 守卫检查顺序缺陷：owner 标签前缀检查位于 docker inspect 之后，负控（声明不存在容器+错误标签）先触发"容器不存在"。处置：前缀检查移到 docker 探测之前（错误配置不该触发基础设施查询）。重跑 12/12 PASS。属夹具缺陷修正，非预期修改。 |
| 2 | concurrency 第一个对照 | ERROR（setup） | 实况探针误用 `current_setting('port')`（容器内端口 5432）对比宿主映射端口 52639。处置：端口一致性由 docker 映射+引擎 URL 核验；库内核验改为 current_database()+PostgreSQL 16 版本。重跑 PASS。属夹具缺陷修正。 |
| 3 | concurrency 清理路径对照 ×2 | 2 PASS | 新增节点首跑通过。 |
| 4 | concurrency 两个 RED | 2 FAILED（命名 RED，值 15.00 / −200.0000） | 预期产品 RED，与 R0/外部证据一致。 |
| 5 | revocation 全文件 | 8 FAILED | 开发缺陷：重写时漏导入 `tenant_session`（NameError）。处置：补导入。属夹具缺陷修正。 |
| 6 | revocation 全文件 | 5 命名 RED + 3 对照 PASS | 预期形态恢复。 |
| 7 | guards + 断言逻辑 | 17 PASS / 1 FAILED | 断言逻辑反例自身写错：流水总和 10+12=22 与实测终值无关，判别在 starts/ends 形状与"初始+总增量=实测终值"。处置：反例改为同时验证两条判别。重跑 18/18 PASS。属测试级对照修正，非产品预期修改。 |

## 最终完整运行（三文件一次运行）

命令：`pytest tests/test_mpango_invariants_r0_r1_guards.py tests/test_mpango_mvp_invariants_r0_concurrency.py tests/test_mpango_mvp_invariants_r0_revocation.py --no-header -rA`
**退出码：1**（存在产品命名 RED 时的预期退出码）；耗时 60.19s。

逐节点结果（32 节点；脱敏——输出不含凭据，URL/口令仅存在于运行环境）：

产品命名 RED（7，全部预期，断言名以 INVARIANT_R0_ 开头）：
```
FAILED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_red_concurrent_stock_adjustments_no_lost_update        (INVARIANT_R0_STOCK_LOST_UPDATE: got 15.00)
FAILED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_red_concurrent_full_return_single_economic_effect      (INVARIANT_R0_DOUBLE_RETURN: refund cash -200.0000)
FAILED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_soft_deleted_user_in_active_tenant_denied           (INVARIANT_R0_SOFT_DELETED_USER_ACCESS: 200)
FAILED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_active_user_in_suspended_tenant_denied              (INVARIANT_R0_SUSPENDED_TENANT_ACCESS: 200)
FAILED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_refresh_nonexistent_principal_no_session            (INVARIANT_R0_REFRESH_NONEXISTENT_PRINCIPAL)
FAILED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_refresh_soft_deleted_user_no_session                 (INVARIANT_R0_REFRESH_DELETED_USER)
FAILED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_red_refresh_suspended_tenant_no_session                  (INVARIANT_R0_REFRESH_SUSPENDED_TENANT)
```

生命周期/焦点对照（5 PASS）：
```
PASSED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_control_single_adjustment_and_failed_adjustment_rollback
PASSED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_control_single_full_return_single_economic_effect
PASSED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_control_active_user_active_tenant_can_access
PASSED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_control_deactivated_user_denied
PASSED tests/test_mpango_mvp_invariants_r0_revocation.py::test_r0_control_refresh_live_subject_issues_usable_session
```

清理路径对照（2 PASS）：
```
PASSED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_harness_control_barrier_timeout_cancels_and_rolls_back
PASSED tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_harness_control_task_exception_rolls_back_and_cleans
```

守卫与断言逻辑单测（18 PASS；归属负控 3、JWT 工厂正反例 9、断言逻辑正反例 6）：
```
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_refuses_missing_ownership_config
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_refuses_disagreeing_targets
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_refuses_non_task_owner_label
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_mock_for_every_test_variant[test]
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_mock_for_every_test_variant[TEST]
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_mock_for_every_test_variant[ test ]
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_mock_for_every_test_variant[\tTest]
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_mock_for_every_test_variant[TeSt ]
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_jwt_for_non_test_variants[staging]
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_jwt_for_non_test_variants[ STAGING ]
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_jwt_for_non_test_variants[production]
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_guard_factory_jwt_for_non_test_variants[Production]
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_logic_accepts_serialized_duplicate_return
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_logic_accepts_rejected_duplicate_return
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_logic_rejects_arbitrary_error_outcome
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_logic_rejects_double_economic_effect
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_logic_accepts_correct_adjustment_algebra
PASSED tests/test_mpango_invariants_r0_r1_guards.py::test_r0_assertion_logic_rejects_lost_update_algebra
```

汇总：**25 PASSED + 7 FAILED（全部为产品命名 RED）**。无 skip/xfail，无未知失败。

## 安全演练（记录于本轮，不入库提交，演练后核查零写入）

1. **声明错误容器**（`MPANGO_INVARIANTS_R0_PG_CONTAINER=not-our-container`）：setup 阶段 `GUARD_REFUSED_DATABASE_OWNERSHIP: declared task container 'not-our-container' does not exist`，零写入。
2. **MPANGO_ENV 大小写/空白变体**（`"  TEST  "`）：产品 `core.config.Settings` Literal 校验直接拒绝启动（pydantic ValidationError: Input should be 'production', 'staging' or 'test'）——应用不可启动即不可产生证据。产品两层（Settings 与 auth.factory）对变体处理不一致为源码观察，已记录于任务报告 §5。
3. **MPANGO_ENV=test（精确）**：`GUARD_REFUSED_MOCK_AUTH: MPANGO_ENV='test' normalizes to 'test' and selects MockAuthStrategy`，零写入。
4. 演练后核查：任务库 `t_%` schema 数 = 0。

## 环境守卫验证

- 归属七重核验（env 齐备 / 双 URL 一致 / loopback / 标签命名空间 / docker 标签-镜像-端口-库名-用户 / 引擎一致 / 实况探针）全部在写入前执行，任一不符即 GuardRefused。
- JWT 实证：归一判断 + 应用中间件实际绑定实例类型核对（JwtAuthStrategy）。
- 清理：最终运行后 `t_%` schema = 0、public.wholesalers/retailers = 0；RED 测试同样完成清理。
