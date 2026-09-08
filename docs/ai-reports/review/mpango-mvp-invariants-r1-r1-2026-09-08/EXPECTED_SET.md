# MPANGO-MVP-INVARIANTS-R1-R1 冻结验收预期集合

> **状态标注（R1-R2 整改，2026-09-08）**：候选侧冻结全量运行为 **POST_VOID_CONTINUATION**
> （VOID-1 之后加入准备步骤的续跑），不追溯为原授权下的首次正式验收；正式验收由独立 V3 执行。
> 见 INTEGRITY_APPENDIX.md §1。

## 环境准备步骤（VOID-1 修订后显式声明）

**VOID-1 记录（2026-09-08）**：第一次候选冻结运行（容器 mpango-zcode-inv-r1r1-cand-pg/redis，
日志 `C:/Users/Jeff0/MPANGO ERP/_zcode_mvp_invariants_r1r1_frozen_cand_VOID1.log`）为**环境 VOID**：
任务库从未迁移（归属守卫的 alembic upgrade 在套件后段的 invariants 夹具内才触发），早期套件
（dc10e 报缺 reporting_role、dc11d/平台 schema 类 416 个 setup ERROR、迁移类 139 FAILED）全部撞上
未迁移库。根因：此前轮次的全量运行复用了聚焦运行已迁移的同一容器，掩盖了"全量套件自身不提供
早期迁移"这一前提；冻结改用全新容器后前提缺失显形。该运行与预期集合严重不符，按停止判据本可
STOP；因根因为可证明的环境准备故障（非测试/产品语义变化）、且未产生任何可用差分，处置为：
保留原始材料并归档为 VOID1 → 删除该运行容器 → 显式增加准备步骤 → 重新执行一次候选冻结运行
（非"重跑选绿"：VOID 运行没有绿色结果，也不是因失败内容重跑）。

**准备步骤（两侧等价，绑定各自容器与 env）**：
`pytest tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_control_single_adjustment_and_failed_adjustment_rollback -q`
——经归属七重守卫对核验目标执行 alembic upgrade head、断言 head==037，并以一个对照节点验证库可用
（预期 PASS）。准备调用的产出（含退出码）记入 RUN_IDENTITY。其后再执行全量冻结运行。

## 冻结验收预期集合（于两次冻结全量运行之前写定）

> 冻结字节（工作树状态，随后原样提交）：
> - HEAD = a516d2b3257f782ce068e71e8730c05541f08931（BASE）
> - 测试文件 SHA256：
>   - revocation `a472cccb95f155e15e256827e4c28db33540b3bd54176908422eba33a9edd9ed`
>   - guards `f94b32d0858c04ad0d5ecc096d002dcd332ef7b81ac89c3ace2b6a41405c7800`
>   - concurrency `7e9d1c25933b7f02d5875517e6ea5ad0bde7fcd7a781e3045a9303e26e681cdf`
>   - support `817f56f5de390623cae906520bf98f38f8aa7afa1d5d6424b747c0e029f54626`
> - 产品文件与 pw1r3 夹具 = BASE 字节（本轮未动）。
> - 冻结运行命令：`python -m pytest tests/ -ra --tb=short`（pytest.ini 已含 -v），另存 `--collect-only -q` 清单。
> - 环境：候选与 BASE 各自独立的新建 PG16 + Redis 容器（互不继承残留）；同一 venv
>   （Python 3.12.10 / SQLAlchemy 2.0.45 / hypothesis 6.150.2）；MPANGO_ENV=staging；
>   REDIS_URL 与 PW1R3_TEST_REDIS_URL 均指向各自任务 Redis（真实限流路径）；迁移由归属守卫
>   夹具对核验目标执行（head 037），绝不使用 alembic.ini 默认地址。

## 已证实的环境机制（预列依据）

1. **MPANGO_ENV 模块级泄漏**：6 个旧测试文件在模块 import（= 收集阶段）硬设
   `os.environ["MPANGO_ENV"]="test"`（test_b5_real_db.py:17 等）。全量运行中任何测试执行前进程环境
   已被污染 → 撤权文件的 `require_jwt_auth_strategy` 守卫对文件内**全部节点**按设计拒绝
   （GUARD_REFUSED_MOCK_AUTH，setup 阶段 ERROR，零运行、零写入）。因此**撤权文件的全量内结果为
   环境受限证据；其权威证据绑定聚焦冻结运行**（无污染进程，单独记录）。
2. **pw1r3 限流 Redis**：该套件使用独立 env `PW1R3_TEST_REDIS_URL`（默认 127.0.0.1:26379 不可达）。
   上一轮全量运行未设置它 → 限器 fail-open：`test_101st_anonymous_...` 因此失败（非产品/测试缺陷），
   两个 contextual bucket 测试的通过亦不构成真实限流证据。本轮冻结运行显式设置该变量指向任务 Redis
   （开发期已实测候选侧 7/7 PASS）。此更正将写入勘误。
3. **缓存诊断节点**：可达缓存 → 命名 RED（INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED）；
   不可达 → 显式 SKIP。在全量内该节点随撤权文件一起 ERROR（机制 1）；其 RED 证据绑定聚焦冻结运行
   （可达缓存、无污染进程，单独记录；开发期已实测复现）。

## 候选冻结全量运行预期（逐节点/分类）

| 类别 | 预期 |
|---|---|
| revocation 文件 14 节点 | 全部 ERROR（机制 1；零运行） |
| concurrency 文件 8 节点 | 7 PASS + `red_concurrent_full_return_single_economic_effect` FAILED（已知双退 RED） |
| guards 文件 31 节点 | 全部 PASS |
| pw1r3 文件 7 节点 | 全部 PASS（真实限流路径，开发期已实测） |
| 旧失败集合（17 节点，逐 nodeid 见下） | 全部 FAILED（既有，不刷绿） |
| real_alembic_upgrade 29 节点 | 全部 ERROR（既有临时库类） |
| skip / xfail | skip 数与原因以 -ra 实测为准逐条对账（本轮起可恢复 nodeid）；xfail 预期 15 |
| 汇总预期 | FAILED ≈ 18（17 既有 + 1 已知 RED）；ERROR ≈ 43（29 既有 + 14 撤权环境）；PASSED ≈ 3695+ |

旧失败集合 nodeid（17，候选与 BASE 相同，全部既有）：
- tests/test_dc11t2_async_test_utils.py::test_temp_db_body_and_cleanup_failure_raise_exception_group
- …::test_temp_db_creates_and_drops_exact_database
- …::test_temp_db_original_exception_preserved_by_identity
- …::test_temp_db_persistent_foreign_session_fails_closed_sanitized
- …::test_temp_db_terminates_own_role_session_and_drops
- …::test_temp_db_waits_out_transient_foreign_session
- tests/test_dc11t4c_reporting_bootstrap_contract.py::test_public_alembic_alone_preserves_tenant_schema_set
- tests/test_dc12a_r2_credential_email_links.py::TestSettingsValidation::test_none_allowed_in_test
- tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py::test_forgot_password_email_carries_db_canonical_uppercase_code
- …::test_reset_link_legacy_shape_unchanged_without_code
- …::test_reset_link_with_canonical_code_keeps_fragment_only
- tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py::test_actual_alembic_035_to_036_failure_rolls_back_then_repaired_upgrade_noops
- tests/test_s4g_migration_infrastructure_hardening.py::test_alembic_upgrade_head_creates_wide_version_table_on_fresh_database
- …::test_alembic_upgrade_head_widens_existing_varchar32_version_table
- …::test_migration_017_creates_retailer_prices_on_fresh_tenant_schema
- …::test_migration_017_fails_closed_for_incompatible_retailer_prices
- …::test_migration_017_reconciles_compatible_preexisting_retailer_prices

## BASE(1485c3f5) 冻结全量运行预期

| 类别 | 预期 |
|---|---|
| revocation 文件 11 节点（BASE 字节） | 全部 ERROR（机制 1） |
| concurrency 文件 7 节点 | 5 PASS + 2 FAILED（`red_concurrent_stock_adjustments_no_lost_update` 与 `red_concurrent_full_return...` 均为基线 RED） |
| guards 文件 25 节点 | 全部 PASS |
| pw1r3 文件 7 节点（BASE 夹具无 wholesalers 行 + BASE 产品无租户核验） | 全部 PASS（匿名/上下文桶行为两侧同构） |
| 旧失败集合 17 节点 | 同候选表，全部 FAILED |
| real_alembic_upgrade 29 节点 | 全部 ERROR |
| 汇总预期 | FAILED ≈ 19（17 既有 + 2 基线 RED）；ERROR ≈ 37（29 既有 + 11 撤权环境） |

## 停止判据（预先声明）

冻结运行中任何 **不在本预期集合内** 的 FAILED / ERROR / SKIP / XFAIL→XPASS 变化、收集错误、
或无法归因的节点状态变化 → STOP：保留原始材料、清理、如实报告，不以重跑消除。
仅报告文件可在运行后变更；测试/产品字节不得变更（否则重新冻结并声明作废本次运行）。
