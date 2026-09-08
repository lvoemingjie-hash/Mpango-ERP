# 冻结运行身份：最终候选（zcode 分支 HEAD + 冻结测试字节）

## 绑定字节

- 分支：`zcode/mpango-mvp-invariants-r1-r1-test-evidence-closure-2026-09-08`
- BASE（HEAD，实现字节）：`a516d2b3257f782ce068e71e8730c05541f08931`（树 `6a412568cd2c50fcf1d92103d989603a5b819e60`）
- 运行时测试文件字节（工作树，随后原样提交；提交后以 blob 哈希复核一致）：
  - `backend/tests/test_mpango_mvp_invariants_r0_revocation.py` = `a472cccb95f155e15e256827e4c28db33540b3bd54176908422eba33a9edd9ed`
  - `backend/tests/test_mpango_invariants_r0_r1_guards.py` = `f94b32d0858c04ad0d5ecc096d002dcd332ef7b81ac89c3ace2b6a41405c7800`
  - `backend/tests/test_mpango_mvp_invariants_r0_concurrency.py` = `7e9d1c25933b7f02d5875517e6ea5ad0bde7fcd7a781e3045a9303e26e681cdf`
  - `backend/tests/mpango_invariants_r0_support.py` = `817f56f5de390623cae906520bf98f38f8aa7afa1d5d6424b747c0e029f54626`
  - 产品文件与 pw1r3 = BASE 字节（本轮未改）
- 运行目录：`C:/Users/Jeff0/MPANGO ERP/worktrees/zcode_mpango_mvp_invariants_r1_r1_2026-09-08/backend`

## 运行环境（任务独占，与 BASE 运行相互独立）

- 容器：`mpango-zcode-inv-r1r1-cand-pg`（ID 282a516fc4da，postgres:16-alpine，127.0.0.1:60171，
  标签 mpango.owner=zcode-mvp-invariants-r1-r1）
  `mpango-zcode-inv-r1r1-cand-redis`（ID a83f017bbdf3，redis:7-alpine，127.0.0.1:60172，同标签）
- env（脚本 `_zcode_mvp_invariants_r1r1_env_cand.sh`，口令为合成 disposable 值，不入库）：
  DATABASE_URL=TEST_DATABASE_URL=postgresql://inv_r1r1_cand:***@127.0.0.1:60171/inv_r1r1_cand；
  MPANGO_ENV=staging；REDIS_URL=redis://127.0.0.1:60172/15；PW1R3_TEST_REDIS_URL=…/14（真实限流路径）；
  SECRET_KEY=合成64hex；PUBLIC_FRONTEND_URL=http://127.0.0.1:1
- venv（与 BASE 运行同一实例）：`_zcode_mvp_invariants_r0_venv`：Python 3.12.10、pytest 8.4.2、
  pytest-asyncio 0.26.0、SQLAlchemy 2.0.45、asyncpg 0.31.0、hypothesis 6.150.2、redis、jose
- 真实 JWT 策略：聚焦运行经 `require_jwt_auth_strategy` 守卫核验（staging 归一 + 中间件绑定实例断言）；
  全量内该守卫因既有 MPANGO_ENV 泄漏对撤权文件拒绝（GUARD_REFUSED_MOCK_AUTH，见对账）
- 迁移：无任何 alembic.ini 默认地址路径；见下准备步骤

## 执行序列与退出码（原始日志均在仓库外，不可覆盖）

| 步骤 | 命令 | 结果 |
|---|---|---|
| 收集清单 | `pytest tests/ --collect-only -q` | 3837 collected，exit 0（`_zcode_mvp_invariants_r1r1_frozen_cand_collect.txt`） |
| 准备步骤（预期集合§环境准备） | `pytest tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_control_single_adjustment_and_failed_adjustment_rollback -q` | 1 passed（6.64s）；随后库内核验 `alembic_version=037_payment_declarations_schema`、public 表 29 张 |
| 冻结全量 | `pytest tests/ -ra --tb=short` | **18 failed, 3692 passed, 69 skipped, 15 xfailed, 43 errors，1427.26s，FROZEN_CAND_EXIT=1** |
| 聚焦冻结（不可达缓存前提） | `pytest <guards> <concurrency> <revocation> -ra --tb=short`（REDIS_URL=redis://127.0.0.1:1/15） | **1 failed（已知双退 RED）, 51 passed, 1 skipped（缓存诊断：前提缺失显式跳过）**，115.20s，exit 1 |
| 聚焦冻结（可达任务缓存前提） | 同上（REDIS_URL=redis://127.0.0.1:60172/15） | **2 failed（已知双退 RED + INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED 命名 RED）, 51 passed**，57.39s，exit 1 |
| 残留核查 | psql 计数 | 聚焦运行自清理；全量后残留为既有失败文件临时 schema（随容器销毁） |

## 结果与预期集合比对

全量汇总、FAILED/ERROR/SKIP/XFAIL 逐节点集合与 `EXPECTED_SET.md` 预列**完全一致**：
- 18 FAILED = 17 既有（逐 nodeid 见预期集合）+ `red_concurrent_full_return_single_economic_effect`（已知 RED）
- 43 ERROR = 29 real_alembic（既有临时库类）+ 14 撤权文件（既有 MPANGO_ENV 收集期泄漏，按设计拒绝，零运行）
- 69 SKIPPED（nodeid 集合与 BASE 完全一致，原因已捕获）；15 XFAIL
- 无任何未在预期集合内的状态
