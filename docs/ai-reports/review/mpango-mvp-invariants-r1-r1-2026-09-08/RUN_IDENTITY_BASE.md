# 冻结运行身份：PRODUCT_FIX_COMPARISON_BASE（1485c3f5）

## 绑定字节

- 运行树：detached worktree `C:/Users/Jeff0/MPANGO ERP/worktrees/zcode_mpango_mvp_invariants_r1r1_base_ref`
  于 `1485c3f5b59e45357462e40975537cbf3932d3b0`（树哈希 = 该提交树，未做任何修改，`git status` 干净）
- 该字节 = R0-R2 已接受候选：产品**无**本轮三处修复；pw1r3 夹具**无** wholesalers 行；
  撤权/并发/guards 测试为 R0-R2 版本（11/7/25 节点）

## 运行环境（与候选运行相互独立、配置等价）

- 容器：`mpango-zcode-inv-r1r1-base-pg`（ID b4ea538433f1，postgres:16-alpine，127.0.0.1:52804，任务标签）
  `mpango-zcode-inv-r1r1-base-redis`（ID 62d790117d8c，redis:7-alpine，127.0.0.1:52807，任务标签）
- env（`_zcode_mvp_invariants_r1r1_env_base.sh`）：DATABASE_URL=TEST_DATABASE_URL=postgresql://
  inv_r1r1_base:***@127.0.0.1:52804/inv_r1r1_base；MPANGO_ENV=staging；
  REDIS_URL=…/15；PW1R3_TEST_REDIS_URL=…/14；SECRET_KEY/PUBLIC_FRONTEND_URL/REPORTING_USER_PASSWORD 与候选同源合成值
- venv：与候选同一实例（版本清单见候选身份文件）
- 初始数据状态：全新容器，互不继承候选运行任何残留（两容器均为本任务新建、独立端口与凭据）

## 执行序列与退出码

| 步骤 | 命令 | 结果 |
|---|---|---|
| 收集清单 | `pytest tests/ --collect-only -q` | 结果存 `_zcode_mvp_invariants_r1r1_frozen_base_collect.txt`，exit 0 |
| 准备步骤（与候选同一步骤、同一节点） | `pytest tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_control_single_adjustment_and_failed_adjustment_rollback -q` | 1 passed（7.49s）；库内核验 `alembic_version=037_payment_declarations_schema` |
| 冻结全量 | `pytest tests/ -ra --tb=short` | **19 failed, 3684 passed, 69 skipped, 15 xfailed, 37 errors，1378.69s，FROZEN_BASE_EXIT=1** |

## 结果与预期集合比对

与 `EXPECTED_SET.md` BASE 侧预列**完全一致**：
- 19 FAILED = 17 既有（逐 nodeid 同候选表）+ 2 基线 RED（`red_concurrent_stock_adjustments_no_lost_update`、
  `red_concurrent_full_return_single_economic_effect`）
- 37 ERROR = 29 real_alembic + 8 撤权文件（同一收集期 MPANGO_ENV 泄漏机制）
- 69 SKIPPED（与候选逐 nodeid 集合一致）；15 XFAIL
- 无任何未在预期集合内的状态
