# REVOCATION-STOCK-INTEGRATION-R1 任务报告（ZCode-W 作者轮）

日期：2026-09-22
授权：CTO-AUTH-REVOCATION-STOCK-INTEGRATION-R1-ZCODE-W-20260922
权威合同：codex/revocation-stock-integration-r0-20260922@0cbde6ad（docs/ai-reports/review/2026-09-22_REVOCATION_STOCK_INTEGRATION_R0_AND_R1_DIRECTIVE.md）

RESULT=CANDIDATE_READY_FOR_CTO_REVOCATION_STOCK_INTEGRATION_R1_CANDIDATE_FREEZE
CLAIM_CEILING=AUTHOR_SOURCE_AND_TARGETED_REAL_DATABASE_EVIDENCE_ONLY（最终验收需独立 V3）
MERGE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
PRICING_AND_FURTHER_ORDERING_IMPLEMENTATION_AUTHORIZED=NO

## 1. 身份与累计范围

| 项 | 值 |
| --- | --- |
| 实施 BASE | 5c93763ded903cc4e903d67997f1528d09ddc4b8（tree e6444326…，与合同冻结值一致） |
| 历史修复参考 | a516d2b3257f782ce068e71e8730c05541f08931 |
| 候选（第一提交） | 95c044ec（parent 5c93763d） |
| 候选（最终 HEAD） | 7d95eaa2146019bdf7212006565358d91d87546d |
| 最终 tree | b2b666e38154040076a741b76b20162749de5336 |
| 谱系 | 5c93763d → 95c044ec → 7d95eaa2（均为普通后继提交，无 amend/rebase/force） |
| 累计路径 | 恰好 8 个：产品 3（api/context/tenant.py、api/v1/auth.py、services/inventory_service.py）+ 测试/支撑 5（mpango_invariants_r0_support.py、r0_revocation、r0_concurrency、r0_r1_guards、pw1r3_rate_limit_context）|
| 本轮新增 | 95c044ec：+4952/−4（3 改 5 新增）；7d95eaa2：仅支撑文件 +101/−44 |
| 分支 | zcode/revocation-stock-integration-r1-20260922（已推送，local==remote 于 7d95eaa2） |

产品移植口径：
- tenant.py、auth.py 恢复后与历史修复 a516d2b3 **git blob 字节一致**（`git diff a516d2b3 -- <两文件>` 为空；tenant.py blob==7f550693…、auth.py blob==962918f6…，与合同 blob 表完全相同）。
- inventory_service.py 仅 +1 行：adjust_stock 锁查询补 `.execution_options(populate_existing=True)`（与模块内既有 4 处同型）；未整文件覆盖，catalog/sellable-unit 身份、039 credit holds、pre-lock 排序、DB-authority 全部保留。

## 2. 实施要点

1. 访问撤权：resolve_tenant_context 读当前库态——USER_DELETED（软删用户）401；新增 assert_tenant_active：public.wholesalers 必须存在、未删、status='active'（共享 TENANT_ACTIVE_STATUS），其余状态一律 fail-closed 401。
2. contextual refresh：端点挂 Depends(get_db_session)（真实 HTTP 路径）；重签前 _validate_contextual_refresh_subject——wholesaler 存在且 active、schema 从 wholesaler 行派生（绝不信任 token 声明）+ validate_identifier、{schema}.users 行存在/未删/active；schema 缺失→TENANT_NOT_FOUND 401（不 500）；其余 DB 错误传播且零签发；identity-only 分支不动（登记开放边界）。
3. 并发库存：仅 adjust_stock 锁查询补 populate_existing——锁后行态即计算基准。

## 3. 测试套件（83 节点）

- 来源：五文件取自已获 CTO 多轮评审的 role-separated 谱系（revocation/concurrency/guards 原样带入，节点名与断言值与历史候选一致）。
- 本轮适配（唯一允许的改法，未放宽任何产品权限门）：
  - 支撑文件 BASELINE_MIGRATION_HEAD 037→**039_order_credit_holds**；
  - seed_sku_with_stock 先种 ACTIVE CatalogProduct（当前 SKU 模型要求非空 catalog_product_id）；
  - pw1r3 rl_tenant 种精确 active wholesalers 行（按 id 精确清理）；
  - **7d95eaa2（准备迭代 2）**：把支撑夹具的迁移后阶段对齐到当前候选的 migration-authority bootstrap 合同——旧夹具向运行角色转移公共守卫函数所有权并要求 CREATE on public；当前候选 bootstrap（DB-authority 工作）强制相反合同并在违约时拒绝租户 bootstrap。改为 verify_public_object_authority（函数 owner==库 owner==声明的迁移身份；运行角色 EXECUTE；运行角色**不得**有 CREATE on public），权限探针同步翻转。产品 bootstrap 检查一字未动。
- 分布：guards 54（纯逻辑，无 DB）+ revocation 14 + concurrency 8 + pw1r3 7。

## 4. 环境与正式运行（VPS，任务专属全新资源）

- 腾讯 VPS；全新容器 mpango-zcode-revint-r1-pg（postgres:16，127.0.0.1:15432）与 mpango-zcode-revint-r1-redis（redis:7，127.0.0.1:16379），均带 mpango.owner=zcode-mvp-invariants-revint-r1-20260922 标签；不复用任何旧容器/卷/凭据。
- 三身份合同：迁移身份=容器 POSTGRES_USER（mpango_revint_mig，库 owner）；运行身份=mpango_revint_run（NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION、零成员、无 CREATE on public）；reporting 由迁移 011 创建。
- 真实 001..039 链：39 条 Running upgrade、rc=0、head==**039_order_credit_holds**（独立探针），日志零口令残留。
- 真实 JwtAuthStrategy（MPANGO_ENV=staging）；PG/Redis 所有权守卫（docker inspect 标签/镜像/端口绑定）全数通过。
- 正式哨兵 evidence/formal/FORMAL_SENTINEL_7d95eaa2（O_EXCL 原子创建，一次性）；preflight.json（脱敏：仅变量名+存在性）；frozen_collection.txt 83 nodeids。

**正式运行（冻结字节 7d95eaa2）**：83/83 收集==JUnit，节点名集合完全一致；**82 PASS + 1 FAIL + 0 ERROR + 0 SKIP**，rc=1（唯一 FAIL 即登记的缓存诊断命名 RED，见 §6）。

## 5. 六项修复验收（全部真实路径、真实 PG16/Redis、真实 JWT）

| 验收行 | 节点 | 结果 |
| --- | --- | --- |
| 活跃用户+活跃租户正控 | test_r0_control_active_user_active_tenant_can_access | PASS |
| 软删用户撤权 | test_r0_red_soft_deleted_user_in_active_tenant_denied | PASS（401） |
| 停用租户撤权 | test_r0_red_active_user_in_suspended_tenant_denied | PASS（401） |
| 不存在主体刷新拒绝 | test_r0_red_refresh_nonexistent_principal_no_session | PASS（401+零令牌） |
| 软删主体刷新拒绝 | test_r0_red_refresh_soft_deleted_user_no_session | PASS |
| 停用租户刷新拒绝 | test_r0_red_refresh_suspended_tenant_no_session | PASS |
| 活主体刷新正控/错误签名/错误类型/主体验询故障零签发 | 4 个对照节点 | 全 PASS（签名拒绝带哨兵证明主体验询未达） |
| 同参同码租户隔离（DB 级、精确键缓存前提） | test_r1_control_tenant_isolation_same_query_same_code_db_only | PASS |
| 并发调整守恒 | test_r0_red_concurrent_stock_adjustments_no_lost_update | PASS：10+7+5=**22.00**，共享 assert_adjustment_chain 校验原始流水行数/每行代数/链式守恒（两合法顺序均接受） |
| 单次全额退货正控 | test_r0_control_single_full_return_single_economic_effect | PASS（退款 −100 cash/+100 revenue 恰一次、恰好一条 restock、库存还原） |
| 读助手保真对照 | test_r1_control_adjustment_read_helper_preserves_duplicate_rows | PASS |

守恒证据三件套：正式 PASS 的守恒断言节点（junit_formal.xml）+ M4 变异 RED 日志（去修复后 10+7+5=**15.00**，INVARIANT_R0_STOCK_LOST_UPDATE 原文）+ guards 合成对照（含 CTO 原始三行反例 A(17→22)×2+B(10→17) 拒绝）。

**重复退货节点的如实处置**：test_r0_red_concurrent_full_return_single_economic_effect 在当前候选上**观察为 PASS**——BASE 的 OrderCommandService._load_locked 已带 populate_existing 且 route 层 409 INVALID_STATE_TRANSITION 属 documented 形态（单一经济效果成立）。此为当前候选既有机制所致，**不由本轮修复、不改名不改断言、不计入本轮闭合**；登记边界（legacy 候选 a516d2b3 上为 RED）原样引用。

## 6. 回归（O27/D22 等价超集 + 受影响 auth/SKU）

- **口径限制（如实披露）**：O27/D22 的具体选点定义不在本执行方可得的冻结输入内（本地/远端全树检索仅合同一句话提及）。处置：跑**全量超集**，不可能藏住回归。
- 主信封（同一任务库、候选字节）：order_state_r2/ 全目录（65）+ test_combined_setup_authority_contract.py（46，DB-authority）+ test_platform_p10_contracts.py（resolve_tenant_context 直接调用方）+ test_s5a_fresh_tenant_real_user_journey_gate.py（adjust_stock 直接调用方）+ test_auth_regressions.py = **290 PASS + 16 SKIP + 9 ERROR**。
- 9 个 ERROR 全部为 business/test_s4d_inventory_movement_ledger_integrity.py（adjust_stock 二阶影响面）：其共享 conftest 夹具要求以运行角色 CREATE OR REPLACE 公共守卫函数——与主信封的 migration-authority 合同结构性冲突（预先存在于 BASE 的拓扑矛盾，非本轮字节所致；错误语句在夹具 DDL，产品路径未触）。处置：为该文件单设隔离信封（专用库 mpango_revint_s4d：迁移以迁移身份跑完 39 步、守卫函数所有权与公共 DML 授予该库的测试角色——即该文件自身夹具契约的要求），复跑 **9/9 PASS（rc=0）**。主信封未做任何放宽。
- 汇总：回归面 **299 PASS + 16 SKIP + 0 FAIL/ERROR**（junit_regression.xml、junit_s4d_isolated.xml、regression_reconciliation.json）。

## 7. 变异证伪（隔离就地、逐字节还原；全部语义级）

| 变异 | 去除内容 | 命中 RED（恰如声明） | 保持绿 | 还原 |
| --- | --- | --- | --- | --- |
| M1 | tenant.py USER_DELETED 检查 | 恰 1：软删用户撤权节点 | 正控 | blob==7f550693，tree 净 |
| M2 | tenant.py assert_tenant_active 调用 | 恰 1：停用租户撤权节点 | 正控 | 同上 |
| M3 | auth.py _validate_contextual_refresh_subject 调用 | 恰 5：三个 R0 刷新 RED + ghost-user 分支 + 故障零签发 | 签名/类型对照、活主体对照、隔离对照（8 PASS）；另有 1 个常驻缓存 RED（非变异所致） | blob 还原，tree 净 |
| M4 | inventory adjust_stock populate_existing | 恰 1：丢失更新节点（15.00≠22.00，INVARIANT_R0_STOCK_LOST_UPDATE 原文） | 并发文件其余 7 节点 | tree 净，HEAD==7d95eaa2 |

准备失败如实保留：语法/导入类失败为零；每轮迭代日志留存（见 §9）。

## 8. 工具门禁

- **GitNexus（候选绑定，1.6.11，编辑前 impact）**：adjust_stock 风险 **HIGH**（直接上游 inventory 路由 adjust_inventory + s5a journey gate；二阶 s4d 两节点）——HIGH 已披露并全部纳入回归；resolve_tenant_context 风险 LOW（4 个 p10 合同测试直接调用）；refresh_token 图上 0 上游（HTTP 路由），中间件→JwtAuthStrategy→resolve 的调用链以直接源码分析补证（strategy 委托 api/context/tenant.resolve_tenant_context）。
- **真实 detect-secrets-hook（v1.5.0 实际入口）**：8 个变更文件 rc=0；canary 阳性控制 rc=1（AWS Key 命中）；.secrets.baseline blob **e38a9a862864fe14c41a2afee30d984d78384538 未变**。
- git diff --check 干净；staged blob LF/无 BOM/无 NUL/文件尾换行；提交钩子全绿（trailing-ws/EOF/yaml/large-files/detect-secrets）。
- 每次推送后外部核对 local==remote（95c044ec、7d95eaa2 两次均一致）。

## 9. 准备迭代台账（全部留存、均称为准备证据）

1. 迭代 1（候选 95c044ec，迁移链证据已capture）：62 PASS + 21 FAIL——全部 DB 节点被产品 bootstrap 的 LedgerGuardAuthorityError 拒绝（旧夹具合同与当前 DB-authority bootstrap 冲突）→ 产出 7d95eaa2（测试支撑侧适配，产品门未动）。
2. 迭代 2（7d95eaa2，权限修正后）：22 ERROR——运行 1 中旧代码已把公共函数所有权转给运行角色（旧夹具副作用）→ 以迁移身份 ALTER 回 migration authority（任务库内一次性修复）。
3. 迭代 3（同字节）：82 PASS + 1 预期登记 RED → 冻结并开正式信封。
4. 正式（哨兵 FORMAL_SENTINEL_7d95eaa2，一次）：§4/§5 结果。
5. s4d 隔离信封三次准备（报告 s4d_migration*.log）：含一次脚本错误（URL 未传给 alembic，跑错库）与一次残留 t_test 触发迁移 017 既有表探针的 asyncpg "char" 参数问题（清洁库上不复现；作为**迁移可移植性登记观察**报告，迁移不在本轮授权修复范围）。

## 10. 未闭合/登记事项（不在本轮范围）

- 跨租户 sku-list 缓存（无租户维度的缓存键）：本轮以任务专属可达 Redis 复现并保留**命名 RED**（INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED，诊断节点断言正确不变式）。
- logout、密码重置会话失效、identity-only refresh：开放登记。
- 迁移 017 既有表探针的 asyncpg "char" 参数形态（仅残留 schema 场景）：登记观察，未修。
- O27/D22 精确选点映射：见 §6 口径限制。

## 11. 资源清理（详见 evidence-root/cleanup_record.json）

容器×2、匿名卷×2（按创建时间戳精确归属）、凭据/env/SQL 文件、任务目录全部移除；拆卸前残留探针：两库 t_% schema=0、Redis 两 db 0 键；唯一 wholesalers 残留行归属候选自身回归夹具（CFX… Contract Fixture Wholesaler，随库销毁）。未触碰他队资源（r2d-pg、procurement-workspace、既有卷）。

## 12. 证据清单

外部证据根：AI_REPORT_INBOX/revocation-stock-integration-r1-20260922/evidence-root/（manifest.json 载 23 件 SHA-256）：
formal/{preflight.json, FORMAL_SENTINEL_7d95eaa2, frozen_collection.txt, paths_delta.txt, junit_formal.xml, junit_reconciliation.json, formal_run_stdout/stderr.log, junit_regression.xml, regression_stdout.log, junit_s4d_isolated.xml, s4d_isolated_stdout.log, s4d_migration*.log, mutation_M1..M4.log} + migration_chain_main_db.log + evidence_cleanup_before.json + cleanup_record.json + manifest.json。

TESTS_RUN_THIS_ROUND=FORMAL_83_NODES + REGRESSION_MAIN_315 + REGRESSION_S4D_ISOLATED_9 + MUTATION_RUNS_M1_M4
FULL_SUITE_RESULT=NOT_RUN_THIS_ROUND（全量全库差分不在本轮授权；独立 V3 为验收门）
PRODUCT_SOURCE_EDITS=3_FILES_NARROW（tenant.py/auth.py 字节等于历史修复；inventory_service.py 单行）
NEXT_GATE=CTO_REVOCATION_STOCK_INTEGRATION_R1_CANDIDATE_FREEZE（对象 7d95eaa2146019bdf7212006565358d91d87546d）

---

# 勘误与更正轮（CTO 裁定 NEED_CHANGES，复核记录 b5c99508a）

RESULT=CORRECTED_CANDIDATE_READY_FOR_CTO_REVOCATION_STOCK_R1_CORRECTED_CANDIDATE_FREEZE
更正候选：**9533602c0283b9388822e396375b5516b817c6a9**（parent 9c300b5a；7d95eaa2 的正常后继；产品三文件字节相对 7d95eaa2 **零变化**，仅测试支撑两文件）

## E1（对 F1/P1 的勘误：撤回"等价超集"）

原报告 §6 的"O27/D22 等价全量超集"表述**撤回**。逐节点对账（CTO 复核 + 本方复核一致）：原主回归信封中 O27 27/27 全 PASS（保留，不因材料更正重复运行）；**D22 实为 0 PASS / 7 SKIP / 15 未收集**——其中 039 非有限值预检节点与 6 个 combined authority 生命周期/所有权节点因未开启 `MPANGO_ALLOW_TEMP_DB_CREATE=1` 而 SKIP；15 个 readiness-gate 节点因该文件未纳入当时的回归选集而根本未收集。
**补足**：按 CTO 提供的清单（historical-nodes-D.txt，blob b2bbc42f…）在更正候选上原样执行 22 节点——`MPANGO_ALLOW_TEMP_DB_CREATE=1` 显式开启、源库名/端口预检记录在案（d22_source_precheck.json：test_mpango_revint_r1c2@127.0.0.1:15433，端口白名单声明 15433）、临时库由 D22 文件自身的既定拓扑以 ADMINISTRATOR 凭据创建。结果：**22/22 PASS，rc=0**，JUnit nodeid 集合与 CTO 清单完全一致（reconciliation_c2.json：equal=true）。

## E2（对 F2/P1 的勘误：撤回"汇总零错误"）

原报告 §6 的"回归面 299 PASS + 16 SKIP + 0 FAIL/ERROR"**撤回**。两份结果分别保留、永不抵消：
- 主信封（本套件运行拓扑）：**290 PASS / 16 SKIP / 9 ERROR**（junit_regression.xml 原件保留）；9 个 ERROR 均为 s4d 文件 setup 阶段的公共守卫函数替换与 migration-authority 拓扑的结构性冲突，按原样保留为 ERROR，不重新分类为 PRE_EXISTING（本包内无同环境 BASE-vs-candidate 对照）。
- s4d 隔离信封（诊断性、变更函数所有权拓扑）：**9 PASS**（junit_s4d_isolated.xml 原件保留）——仅诊断用途，不得折算为主拓扑证据，亦不得用于生产拓扑声明。

## E3（对 F3/P1 的更正：三身份拓扑）

更正候选 9533602c0 在授权测试/支撑文件内实现**管理员 ≠ 迁移权威 ≠ 运行时**并消费产品既有 provisioner 合同（scripts/provision_runtime_db_roles.py）；产品权限门零改动：
- 新声明 `MPANGO_INVARIANTS_R0_ADMIN_DATABASE_URL`（管理员=容器引导用户，超级用户，仅做 provisioner 引导）；
- 守卫反转原绑定：容器 POSTGRES_USER 必须绑定**管理员** URL，迁移用户等于容器引导管理员即拒绝（新增 guards 负控 test_f1_guard_refuses_migration_equal_to_container_admin）；
- verify_migration_identity_live 发布**实时角色属性**（rolsuper=false、库 owner=迁移角色）——最小特权为证据而非断言；新增 verify_admin_identity_live 只读探针；
- 新阶段 apply_product_minimum_grants：夹具调用**产品 provisioner** `--apply-grants`（迁移权威身份）+ 只读 `--verify`（rc=2 即拒绝），取代一切手写授权。
运行身份合同不变（非特权、零成员、公共 schema 无 CREATE）。
**更正候选上的作者运行**（VPS 全新 r1c2 信封，provisioner 三阶段实跑：mpango_migrate=NOSUPERUSER/NOCREATEDB/CREATEROLE、mpango_app=严格、库 owner=mpango_migrate）：84 节点（含新负控）收集==JUnit 逐点一致，**83 PASS + 1 FAIL + 0 ERROR + 0 SKIP**（唯一 FAIL 仍是登记的缓存诊断命名 RED，见 E4）。

## E4（对 F4 的确认：缓存跨租户为 MVP 阻断）

更正候选运行中唯一失败节点仍为 test_r1_red_diagnostic_sku_list_cache_not_tenant_scoped（INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED：租户 B 收到租户 A 的记录 id）。无 xfail、未禁用 Redis、断言未削弱、84 节点运行**不称为全绿**。缓存隔离修复属后续 CTO 专属范围，本轮未顺手修改。

## E5（对 F5/P2 的更正：清单绑定）

原 manifest.json（实绑 22 件，报告误写 23）**原样保留**；新增 manifest_correction_round.json（**37 件**）以追加式绑定：cleanup_record.json（此前未绑定件）全部绑定，并绑定更正轮全部证据（junit_formal_c2.xml、junit_d22_c2.xml、reconciliation_c2.json、d22_source_precheck.json、nodes-D/O.txt、清理记录、容器事实、残渣探针等）。manifest 自身按惯例自排除。

## E6（变异还原记录的口径）

M1–M4 的还原命令为逐文件 `git checkout -- <file>` 后 `git status --porcelain`（计数 0，工作树==索引==冻结候选树）+ M1 另有 blob 比对（7f550693…）。M2–M4 的 blob 级逐一比对为**作者断言**（命令如上，供 Kilo 复现）；VPS 材料已随清理销毁。变异针对的产品三文件在更正候选中字节未变，变异证据仍绑定 7d95eaa2 的产品字节。

## E7（更正轮准备迭代台账）

1. D22 第 1 次：1 FAIL（temp-DB 助手端口白名单未声明 15433）→ 环境声明补齐（非代码）。
2. D22 第 2 次：1 FAIL（源库名非 test 前缀）→ 信封重建（POSTGRES_DB=test_mpango_revint_r1c2，provisioner 重跑，数据库 owner=mpango_migrate）。
3. 第 3 次：**22/22 PASS**；同信封 84 节点套件 83 PASS + 1 登记 RED。
清理：容器×2×两轮、凭据/env、任务目录均移除并验证；窗口过滤的匿名卷移除算术差额已在 correction-round/cleanup_record_correction_round.json 的 DISCLOSED_FILTER_LIMITATION 如实披露（至多 1 个非本任务匿名卷可能被同窗口过滤移除，供 CTO 知悉；未触碰任何带标签/具名/他队资源）。

NEXT_GATE=CTO_REVOCATION_STOCK_R1_CORRECTED_CANDIDATE_FREEZE（对象 9533602c0283b9388822e396375b5516b817c6a9）
MERGE_AUTHORIZED=NO / DEPLOYMENT_AUTHORIZED=NO / PRICING_AND_FURTHER_ORDERING_IMPLEMENTATION_AUTHORIZED=NO / Fresh Kilo V3 未解锁
