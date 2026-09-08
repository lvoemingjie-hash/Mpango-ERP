# MPANGO-MVP-INVARIANTS-R1 任务报告：撤权链与库存并发修复（2026-09-08）

执行者：Windows ZCode（Zcode-W）。验证层级：`V3_MERGE_CRITICAL`。
声明上限：`PRODUCT_FIX_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW_ONLY`。
未合并、未部署、未改业务合同、未处理退货经济语义、未改迁移/依赖声明/.secrets.baseline/治理验证器。

## BASE / BRANCH / CANDIDATE_SHA / EXACT_CHANGED_FILES

- BASE：`1485c3f5b59e45357462e40975537cbf3932d3b0`（fetch 后 ls-remote 与远端
  `zcode/mpango-mvp-invariants-r0-r2-2026-09-07` 精确一致；父链 a511369e → 29bd720d → 产品基线 bd2373cb）。
- BRANCH：`zcode/mpango-mvp-invariants-r1-auth-stock-fix-2026-09-08`（自 BASE 普通提交，无 amend/rebase/force-push）。
- CANDIDATE_SHA：分支 HEAD（普通推送；报告自身不引用 commit 前的 SHA，完整 SHA 与
  local==remote 核验记录于 RUN_LOG §七及外部最终回报）。
- EXACT_CHANGED_FILES（相对 BASE，两个提交）：
  - 产品：`backend/api/context/tenant.py`、`backend/api/v1/auth.py`、`backend/services/inventory_service.py`
  - 测试：`backend/tests/test_mpango_mvp_invariants_r0_revocation.py`、
    `backend/tests/test_mpango_mvp_invariants_r0_concurrency.py`、
    `backend/tests/test_mpango_invariants_r0_r1_guards.py`、
    `backend/tests/test_pw1r3_rate_limit_context.py`（必要对齐）
  - 报告：`docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_RECORD.md`（含范围表/调用链）、
    `..._RUN_LOG.md`、`..._TASK_REPORT.md`（本文件）、
    `2026-09-07_MPANGO_MVP_INVARIANTS_R0_TASK_REPORT.md` 与 `..._RUN_LOG.md`（仅 O1 措辞更正）
  - `backend/tests/mpango_invariants_r0_support.py` 零字节变化。

## ROOT_CAUSE_AND_FIX

1. **软删用户继续访问**（INVARIANT_R0_SOFT_DELETED_USER_ACCESS）：`resolve_tenant_context` 只查
   用户存在与 is_active；软删（is_deleted=true、is_active 保持 true）不可见。修复：同函数增加
   `USER_DELETED` 核验（读当前行）。
2. **停用租户继续访问**（INVARIANT_R0_SUSPENDED_TENANT_ACCESS）：从不读 `public.wholesalers`。
   修复：新增 `assert_tenant_active`——按 token.tenant_id 查 wholesalers（显式 public. 前缀），
   行缺失/is_deleted → `TENANT_NOT_FOUND`，status≠active → `TENANT_NOT_ACTIVE`（仅 active 放行，
   suspended/deactivated/provisioning/paused/archived 一律 fail-closed）。
3. **refresh 为死亡主体签发会话**（INVARIANT_R0_REFRESH_*×3）：端点零 DB 校验纯重签。修复：
   `refresh_token` 增加 `Depends(get_db_session)`（HTTP 经 DI、直呼显式传参，同一实现）；
   contextual 分支重签前 `_validate_contextual_refresh_subject`：wholesaler 存在+active；schema
   从行派生（不信 token 声明）并过 `validate_identifier`；`{schema}.users` 行存在+is_active+非
   is_deleted；缺 schema/表 fail-closed 401；其余异常传播（不签发）。identity-only 分支不变（登记）。
4. **并发调整丢失更新**（INVARIANT_R0_STOCK_LOST_UPDATE）：`adjust_stock` 先无锁读（行入
   identity map）后 `FOR UPDATE` 重选但无 `populate_existing`，锁后仍用旧属性计算（10+7+5→15）。
   修复：重选加 `.execution_options(populate_existing=True)`（模块既有 `_locked_stock_by_sku_code`
   范式）——锁后从行现状计算（→22，流水链完整一致）。

## CODE_PATH_TO_TEST_MATRIX

| 修复点 | 真实入口测试 | 直呼/单元 |
|---|---|---|
| tenant.py USER_DELETED | red_soft_deleted_user…（GET /api/v1/skus 全中间件栈，401） | — |
| tenant.py TENANT_NOT_FOUND/NOT_ACTIVE | red_active_user_in_suspended_tenant…（同上，401） | — |
| auth.py refresh 校验 | red_refresh_×3 + control_refresh_live_subject + r1 wrong_signature/wrong_type（POST /api/v1/auth/refresh 真实 HTTP） | — |
| 隔离 | r1_control_tenant_isolation（双租户 GET /skus + refresh 各归各） | — |
| inventory populate_existing | red_concurrent_stock_adjustments（两真实连接+事件屏障，终值 22+共享链断言） | control_single_adjustment、失败回滚、屏障超时、任务异常、拒绝请求回滚 |
| 读取 helper 保留原始行 | r1_control_adjustment_read_helper_preserves_duplicate_rows（DB 级） | guards exact_cto_counterexample 等 12 项 |

## CHANGED_OR_ADDED_TESTS

- 更新（节点名与断言值保持 1:1，仅执行入口/预期措辞更新）：R0 的 7 个产品 RED 中 6 个的目标用例
  （refresh×3 改真实 HTTP）；guards `rejects_duplicate_reason_rows` docstring、
  `rejects_duplicate_collapsed_to_two`→更名 `rejects_chained_duplicate_reason_rows`（O1）。
- 新增：`test_r0_assertion_chain_exact_cto_counterexample_rows`（O1 精确原反例 A(17→22)×2、B(10→17)：
  原始三行 SET 拒绝；折叠形态==合法 B→A 链必须接受）、
  `test_r1_control_adjustment_read_helper_preserves_duplicate_rows`、
  `test_r1_control_refresh_wrong_signature_refused`、`test_r1_control_refresh_wrong_token_type_refused`、
  `test_r1_control_tenant_isolation_no_cross_read`。
- 必要对齐：`test_pw1r3_rate_limit_context.py` `rl_tenant` 夹具补 active wholesalers 行
  （新不变量按设计拒绝“注册表外租户”；限流断言零变化）。

## POSITIVE_AND_NEGATIVE_RESULTS

正（全部 PASS）：活跃用户访问 200；活主体 refresh 200 且新 token 于 /api/v1/skus 可用；双租户隔离；
错误签名 401；错误类型 401 INVALID_TOKEN_TYPE；单次调整+负库存失败回滚；屏障超时/任务异常回滚清理；
拒绝请求暂存写入零残留+后续请求恰一次经济效果；单次退货单次经济效果。
负（修复后全部按契约拒绝）：软删用户 401；停用租户 401；refresh 三类无效主体 401 且响应零 token 物料。

## FALSIFICATION_AND_RESTORE_RESULTS

| 退化 | 实测 | 恢复 |
|---|---|---|
| D1a 移除 is_deleted 检查 | soft-deleted RED（suspended 仍绿） | sha256 一致 → 回绿 |
| D1b 移除 assert_tenant_active 调用 | suspended RED（soft-deleted 仍绿） | sha256 一致 → 回绿 |
| D2 移除 refresh 校验调用 | 3 个 refresh RED | sha256 一致 → 回绿 |
| D3 移除 populate_existing | lost-update RED（15.00=基线反例原值） | sha256 一致 → 回绿（44+1） |

## FOCUSED_SUITE / FULL_SUITE

- 聚焦（三文件，任务独占 PG16，可达/不可达 Redis 两前提各一次）：**45 节点 = 44 PASS + 1 已知 RED**
  （INVARIANT_R0_DOUBLE_RETURN，−200.0000 与基线同值，按指令单列未修复）。原 7 RED 中 6 个转绿。
- 全量（`pytest tests/ --no-header -q -rfE`，任务独占 PG16+任务 Redis，MPANGO_ENV=staging）：
  候选 **21F/3684P/69S/15x/40E** vs BASE 同环境串行差分 **20F/3702P/50S/15x/37E**。逐节点差分：
  56 节点两侧共同（既有：alembic 临时库类 29E+5F、MPANGO_ENV 模块级泄漏致撤权文件全量内 ERROR——
  守卫按设计拒绝、孤立/聚焦运行正常、dc11t2/dc11t4c/dc12a_r2/j1_h2c/s1_r5/pw1r3_101st 等 19F）；
  仅候选 5（3 新节点继承同泄漏 + 2 pw1r3 经必要对齐后消除）；仅 BASE 1（丢失更新 RED 转绿的确证）。
  skip 计数差 19 仅有计数无节点清单（-rfE 限制），归因 BASE 第二序运行的库态差异；本任务触碰文件 0 skip。

## REMAINING_KNOWN_RED / UNCOVERED_PATHS

- 已知未修复 RED：`test_r0_red_concurrent_full_return_single_economic_effect`（并发重复退货双经济效果；
  restock_on_return/transition 同型，按指令范围外单列）。
- 范围外同型登记（不改）：select-tenant 为死亡主体铸造（不可用）token；identity-only refresh 无 DB 校验；
  deduct_stock/restock 无 populate_existing（无同会话先前读）；RBAC 缓存加载器；sku 列表缓存键无租户维度
  （可达 Redis 时存在跨租户读缓风险——本轮以每租户独立 q 隔离对照并登记）；logout/密码重置无撤销（指令明示）。
- 未覆盖：/inventory/adjust 与 /auth/refresh 的 HTTP/RBAC 头层之外的 Nginx/TLS/浏览器；refresh 轮换/重放策略；
  全量进程中撤权文件因既有 MPANGO_ENV 泄漏无法执行（以聚焦+孤立运行覆盖）。

## SELF_REVIEW_FINDINGS_AND_DISPOSITION

1. 正确性：三处根因均在决策点修复；真实入口全覆盖（矩阵）；失败路径只读/回滚不变；正常路径对照全绿。
2. 回归面：GitNexus+源读确认调用方（resolve 仅 JwtAuthStrategy；refresh 无其他产品调用方；adjust_stock 单调用方）；
   全量差分无未解释回归；pw1r3 对齐属预期行为变化波及。缓存/锁序无变化（同行锁仅生效性修复）。
3. 测试真实性：全部真实模块/真实 SQL/真实 HTTP；证伪证明断言因目标语义失败而非夹具/语法/环境错误。
4. 范围与安全：变更恰为范围表所列；无默认连接（七重归属守卫+迁移显式 URL）；共享资源零触碰（任务独占
   PG16+Redis 容器，标签核验后删除）；detect-secrets hook 退出 0 且 baseline 字节未变；退化实验全部
   sha256 恢复；无遗留后台任务。
5. 报告真值：所有声明可定位至 RUN_LOG 中的命令/退出码/耗时；R0 基线 RED 值引自既有证据未冒充重跑。

## RESOURCE_CLEANUP / OPEN_RISKS / NEXT_GATE

- 清理：任务容器 PG/Redis 标签核验后删除（含卷）；BASE 差分工作树移除；env 脚本（合成口令）保留仓库外可删；
  任务 worktree 保留（分支已推送）。
- 开放风险：并发重复退货（已知 RED）；停用租户无 HTTP 写入口（测试直写状态，与外部探针同法）；
  sku 列表缓存键租户维度缺失；全量套件 MPANGO_ENV 模块级泄漏（测试卫生）。
- NEXT_GATE：CTO 审查 → 风险相称的独立验证。不自行合并/部署。

---

## 勘误（R1-R1，2026-09-08；保留原结论来源，原文未改）

1. **撤回过强结论**：本报告 §FOCUSED_SUITE / FULL_SUITE 中"skip 计数差 19……归因 BASE 第二序运行
   的库态差异"为无节点级证据的推测，且"无任何由本修复引入的未解释回归"的表述超出了当时证据
   （pw1r3 文件级复跑不能代表最终字节的完整差分；该轮全量的 pw1r3 限流 Redis 实际不可达
   （PW1R3_TEST_REDIS_URL 默认 26379），fail-open 下 6 个 bucket/burst 节点的"通过"不构成真实限流
   证据，`test_101st_anonymous...` 的失败亦为该环境前提所致而非既有产品缺陷）。上述归因与结论由
   R1-R1 冻结差分替代：`docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/`
   （EXPECTED_SET / RUN_IDENTITY_* / NODE_RECONCILIATION / SELF_REVIEW）。
2. **运行字节绑定澄清**：上轮全量运行的库为聚焦运行预迁移过的同一容器（迁移由聚焦套件的归属夹具
   先行完成）；全量套件自身不提供早期迁移。R1-R1 冻结差分改用全新容器 + 显式准备步骤（见该目录
   EXPECTED_SET §环境准备），VOID-1 事故记录同存。
