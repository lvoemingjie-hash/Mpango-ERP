# MPANGO-MVP-INVARIANTS 任务报告（测试候选）

> **R2 修订版（2026-09-07）**：本版按 CTO 对 R1 候选（a511369e）的 NEED_CHANGES 裁决
> （F1/P1 事务对齐、F2/P2 流水去重盲区）以普通后继提交修订，闭合两处测试缺口。
> R2 变更摘要：
> - **F1**：`_return_outcome` 事务决策对齐真实中间件——成功请求在助手内 commit、
>   被文档化 409 拒绝的请求先 rollback 再在事务外分类；新增数据库回归对照
>   （夹具注入"暂存写入+文档化 409"与"暂存写入+未知异常"，证明失败请求零残留、
>   另一请求可提交、最终恰一次经济效果、未知异常不吞不漏）。
> - **F2**：`adjustment_movements` 返回原始行列表（不再按 reason 建字典）；
>   库存断言提取为共享助手 `assert_adjustment_chain`（support 模块），真实并发测试
>   与 guards 正负对照调用同一实现；无序链检查同时接受 B→A（10→17→22）与
>   A→B（10→15→22）两种合法串行序；重复行/重复 reason/未知 reason/缺流水/
>   错误终值/单行代数错误/丢失更新形态全部拒绝。
>   **（2026-09-08 R1 轮按 CTO O1 更正）**R2 所用的三行 A(10→15)/A(15→20)/B(20→27)
>   是自造的额外坏快照而非 CTO 原反例；其折叠形态恰好因"无行始于初值"被拒绝，
>   不代表折叠普遍可识别。CTO 精确原反例为 A(17→22)×2、B(10→17)、final=22——
>   原始三行经 SET 拒绝；但其 dict 折叠形态与合法 B→A 链完全相同、必须被接受，
>   即折叠后信息不可恢复，这正是读取 helper 必须保留原始行的原因。
> 修订历史：R0（29bd720d）→ R1（a511369e）→ 本版 R2；均普通提交，未 amend/rebase/force-push。
> R1 轮已获 CTO 接受的改进（归属守卫、JWT 实证、措辞修正、七个产品 RED）全部保留。

日期：2026-09-07。执行者：Windows ZCode。
性质：产品缺陷复现与回归测试候选。**本候选包含已知失败（命名 RED）回归测试，不是绿色合并候选，不能直接集成。** 未修改任何产品实现、共享 conftest、生产 schema/迁移、依赖、HE2/R9、SKU 候选或 .secrets.baseline；未合并、未部署。

## 0. 基线与候选

| 项 | 值 |
|---|---|
| 产品基线 | bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f（`origin/product-dev-recovered` 复核一致） |
| R0 候选 | 29bd720d4267ca3516377a32eef90658cdb109ba |
| R1 候选（本任务 BASE，CTO 审查对象） | a511369e491db37584673ea88a3c82ed721c2a04 |
| worktree（R2） | `C:\Users\Jeff0\MPANGO ERP\worktrees\zcode_mpango_mvp_invariants_r0_r2_2026-09-07` |
| 任务分支（R2） | `zcode/mpango-mvp-invariants-r0-r2-2026-09-07`（自 a511369e 普通提交，普通推送，未合并） |
| 候选 SHA | 见推送记录（分支 HEAD）；报告自身不引用自 commit 前的 SHA |

## 1. 测试清单与覆盖的真实产品路径

文件（相对 `backend/tests/`）：
- `mpango_invariants_r0_support.py` — 共享夹具与共享断言：任务归属证明（七重核验）、JWT 策略实证、受监督后台任务、TenantIdentity；R2 新增 `assert_adjustment_chain`（唯一库存断言实现，真实并发测试与 guards 对照共用，无平行副本）。
- `test_mpango_mvp_invariants_r0_concurrency.py` — 7 节点（4 对照 + 2 命名 RED + 1 拒绝请求回滚对照）。
- `test_mpango_mvp_invariants_r0_revocation.py` — 8 节点（3 对照 + 5 命名 RED）。
- `test_mpango_invariants_r0_r1_guards.py` — 25 节点（守卫负控 3 + JWT 工厂正反例 9 + 退货结果契约 4 + 调整链共享助手正反例 9），除守卫正路径外不连数据库。

每个产品路径测试 docstring 按"正常对照 / 目标缺陷 / 环境前提 / 执行入口 / 未覆盖范围"五段声明。

| 节点 | 结果 | 真实产品路径 |
|---|---|---|
| control_single_adjustment_and_failed_adjustment_rollback | PASS | `InventoryService.adjust_stock`（POST /api/v1/inventory/adjust 调用的同一服务函数）：单次调整生效、失败调整值与流水均不残留 |
| red_concurrent_stock_adjustments_no_lost_update | **RED** `INVARIANT_R0_STOCK_LOST_UPDATE`（10+7+5 → 实测 15.00） | 同上，两条真实连接 + 事件屏障；原始流水行交 `assert_adjustment_chain`（共享助手）核对 |
| harness_control_barrier_timeout_cancels_and_rolls_back | PASS | 夹具安全：屏障永不释放 → GUARD_HARNESS_TIMEOUT、任务取消并等待、事务回滚无残留、锁无泄漏、teardown 成功 |
| harness_control_task_exception_rolls_back_and_cleans | PASS | 夹具安全：屏障释放后调整以 409 失败 → 类型化异常传播、回滚干净、teardown 成功 |
| control_rejected_return_rolls_back_staging_write（R2/F1 回归） | PASS | 事务行为对照：夹具注入"暂存写入+文档化 409"经真实 `_return_outcome` 执行 → 暂存写入零残留；随后的真实退货请求 commit 且恰一次经济效果；未知异常向外传播、回滚且不吞（pytest.raises 在事务上下文之外捕获） |
| control_single_full_return_single_economic_effect | PASS | 订单全生命周期真实入口 create/confirm/pay(Canonical)/fulfill/return(OrderService+restock)；单次退货恰一次经济效果 |
| red_concurrent_full_return_single_economic_effect | **RED** `INVARIANT_R0_DOUBLE_RETURN`（refund cash −200.0000） | 同上生命周期 + 两个真实连接在 return 路由预读取处确定性交错；两个请求结果均收集分类，成功 commit / 文档化 409 rollback 后再分类（F1 对齐），经济断言恒执行 |
| control_active_user_active_tenant_can_access | PASS | 完整 HTTP 栈（JWT 中间件 → resolve_tenant_context → RBAC → GET /api/v1/skus） |
| control_deactivated_user_denied | PASS | 同上；is_active=false 已被拒绝，缺口精确在 is_deleted/租户状态 |
| red_soft_deleted_user_in_active_tenant_denied | **RED** `INVARIANT_R0_SOFT_DELETED_USER_ACCESS`（200） | 同上；软删状态与产品 soft_delete_user 写入一致 |
| red_active_user_in_suspended_tenant_denied | **RED** `INVARIANT_R0_SUSPENDED_TENANT_ACCESS`（200） | 同上；租户 suspended（仓库无写该状态的 API 入口） |
| red_refresh_nonexistent_principal_no_session | **RED** `INVARIANT_R0_REFRESH_NONEXISTENT_PRINCIPAL` | `api.v1.auth.refresh_token`（POST /auth/refresh 处理器） |
| red_refresh_soft_deleted_user_no_session | **RED** `INVARIANT_R0_REFRESH_DELETED_USER` | 同上；用户行真实存在后软删 |
| red_refresh_suspended_tenant_no_session | **RED** `INVARIANT_R0_REFRESH_SUSPENDED_TENANT` | 同上；活跃用户 + suspended 租户 |
| control_refresh_live_subject_issues_usable_session | PASS | refresh 活主体新 token 在 HTTP 路由真实可用（RED 案例唯一变量是主体存续） |
| guards 文件 25 节点 | PASS | 见 §4/§5/§6/§6b |

## 1b. 节点映射（R1 32 节点 → R2 40 节点）

| R1 节点 | R2 后继 |
|---|---|
| concurrency 6 节点 | 全部同名保留；adjustment RED 的流水断言改调共享 `assert_adjustment_chain`（F2） |
| （无） | +1 `control_rejected_return_rolls_back_staging_write`（F1 数据库回归：三阶段，见 §1 表） |
| revocation 8 节点 | 不变 |
| guards 3 归属负控 + 9 JWT 工厂 + 4 退货契约 | 不变 |
| guards `assertion_logic_accepts_correct_adjustment_algebra`（平行实现正例） | 删除，替换为 `assertion_chain_accepts_b_then_a_serial_order` + `assertion_chain_accepts_a_then_b_serial_order`（调共享助手） |
| guards `assertion_logic_rejects_lost_update_algebra`（平行实现反例） | 删除，替换为 `assertion_chain_rejects_lost_update_journal`（调共享助手） |
| （无） | +7 反例：`rejects_duplicate_reason_rows`（重复 reason 三行）、`rejects_duplicate_collapsed_to_two`（R2 自造链式重复坏快照；**R1 轮按 CTO O1 更正**：非 CTO 原反例，已更名 `rejects_chained_duplicate_reason_rows`，CTO 精确原反例 A(17→22)×2、B(10→17) 另立对照）、`rejects_unknown_reason`、`rejects_missing_movement`、`rejects_wrong_final_value`、`rejects_wrong_single_row_algebra`（以上全部调共享助手，无平行实现） |

计数由 R1 的"25 PASS + 7 RED（32 节点）"变为 R2 的"**33 PASS + 7 产品命名 RED（40 节点）**"。

## 2. 最终完整运行结果（R2）

命令见 §8；退出码 **1**（存在预期 RED 时的正常退出码）；耗时 ≈59s；开发期运行（§运行日志）与最终运行结果一致。

分类：
- **产品命名 RED（7，全部预期，实测值与 R0/R1/外部证据一致）**：并发调整丢失更新 15.00≠22；并发退货 −200/2 次回补；软删用户 200；停用租户 200；refresh ×3 照发会话。
- **生命周期/焦点对照 PASS（5）**：单次调整+失败回滚；单次退货单次效果；活跃访问；is_active=false 拒绝；活主体 refresh 可用。
- **清理/事务路径对照 PASS（3）**：屏障超时取消回滚；任务异常回滚清理；**拒绝请求（文档化 409）暂存写入零残留 + 后续请求可提交 + 未知异常传播回滚**（R2/F1）。
- **守卫/断言逻辑单测 PASS（25）**：归属负控 3、JWT 工厂 9、退货结果契约 4、调整链共享助手正反例 9（R2/F2）。
- **未执行断言**：无（无 skip/xfail）。

运行后核查：任务库 `t_%` schema = 0、public.wholesalers/retailers = 0（F1 探针行位于租户 schema 内，schema 全部级联删除即为"失败请求零残留"的库级证明）。

## 3. 业务写入口表

见 R0 版本（本文件 git 历史）第 3 节，R1 无产品源码变化，入口表不变。要点重述：确认（CRUD+预留，无订单锁）、收款（订单锁+Canonical 全防线）、履约（expire+OrderService+deduct）、取消（预读无锁+CRUD）、退货（预读无锁+OrderService 无 populate_existing+restock）、申报确认（声明行锁+Canonical force_completed）、库存调整（FOR UPDATE 无 populate_existing）、用户停用/软删（无锁）、租户停用（无 API 入口）、refresh（零 DB 校验）、logout（无撤销）、密码重置（改密不撤销会话）。

## 4. 任务归属证明（R1 §一.1）

pytest 运行必须导出：`TEST_DATABASE_URL`、`DATABASE_URL`（两者必须相同目标）、`MPANGO_INVARIANTS_R0_PG_CONTAINER`、`MPANGO_INVARIANTS_R0_PG_OWNER`。会话夹具 `r0_task_database` 在**任何写入之前**依次核验：

1. 四个环境变量齐备（缺一拒绝）；
2. TEST_DATABASE_URL == DATABASE_URL（迁移/bootstrap/pytest 同一目标，拒绝分叉）；
3. URL host 必须 loopback、库名非空；
4. owner 标签必须 `zcode-mvp-invariants-*` 命名空间；
5. `docker inspect`：声明的容器存在、`mpango.owner` 标签与声明一致、镜像为 postgres:16、5432 映射为 `127.0.0.1:<URL端口>`、容器 `POSTGRES_DB`/`POSTGRES_USER` 与 URL 一致（拒绝指向既有库）；
6. 活动引擎（database.session.async_engine）host/port/database 与核验目标一致；
7. 实况探针：`current_database()` 一致、`version()` 为 PostgreSQL 16。

迁移由该夹具执行：`alembic upgrade head` 子进程显式注入已核验的 DATABASE_URL（REPORTING_USER_PASSWORD 缺失即拒绝），完成后核对 `public.alembic_version` == `037_payment_declarations_schema`。**alembic.ini 默认地址不可能被使用**（env.py 仅在 DATABASE_URL 存在时覆盖，而守卫保证它必存在且指向任务容器）。

负控演练（记录于 RUN_LOG，未随库提交）：声明错误容器 → `GUARD_REFUSED_DATABASE_OWNERSHIP`，零写入；MPANGO_ENV=test → `GUARD_REFUSED_MOCK_AUTH`，零写入；大小写/空白变体 → 产品 Settings 直接拒绝启动（见 §5）。

## 5. JWT 实证（R1 §一.2）

- 守卫用与产品 `auth.factory` 完全相同的归一化（`os.getenv("MPANGO_ENV","production").strip().lower()`）判断 test 归一 → 拒绝（覆盖 `test`/`TEST`/` test `/`\tTest` 等变体）。
- 随后核对**应用中间件实际绑定的策略实例**：遍历 `app.user_middleware` 定位 `AuthenticationMiddleware`，断言其 `strategy` 实例类型名为 `JwtAuthStrategy` 且非 `MockAuthStrategy`（app.py:84 绑定点）。HTTP 证据因此绑定到真实运行路径，而非环境字符串。
- 工厂单测（guards 文件 9 节点）证明：所有 test 归一变体 → MockAuthStrategy；staging/production 变体 → JwtAuthStrategy。
- 事实记录：产品两层行为不一致——`core.config.Settings` 的 Literal 校验对 `TEST`/` test ` 等变体直接拒绝启动，仅精确小写 `test` 能到达工厂 Mock 分支；守卫按更严格方向（归一判断）处理，宁可多拒。此不一致为源码观察，留产品线参考。

## 6. 正确结果对照与断言逻辑单测（R1 §三"正确结果能否被接受"）

guards 文件 6 节点直接验证断言与分类逻辑本身（合成输入，不涉产品、不连库）：
- 退货结果契约：`[成功,成功]` 与 `[成功,409 INVALID_STATE_TRANSITION]` 均被接受；`[成功,500]` 被拒绝（OUTCOME_CONTRACT）。
- 单次经济效果快照：正确的 −100/+100、1 次回补、库存 10 被接受；基线双计形态（−200/2 次/11）被拒绝。
- 调整流水代数：正确链（起点 {10,17}、终点 {17,22}、Δ{5,7}、10+12=22）被接受；丢失更新日志形态（双起点 10）结合实测终值 15 被拒绝。

这些是**测试级对照，证明断言能接受正确行为**；不冒充产品修复通过，本轮未修改产品、未要求转绿。旧缺陷保持被抓住：7 个命名 RED 在基线上原样复现（实测值与 R0/外部证据一致），断言未向错误结果妥协。

## 6b. 库存调整链共享助手（R2/F2）

`assert_adjustment_chain(movements, initial, final_observed, expected)` 位于 support 模块，是库存调整不变量的**唯一实现**：真实并发 RED 测试（数据库原始行）与 guards 全部 9 个正反例（合成行）调用同一函数，无任何平行断言副本。检查顺序：
1. 原始行数 == 预期调整数（重复/缺失行在进入代数前即拒绝——闭合 CTO 离线诊断揭示的"按 reason 折叠掩盖重复行"false-green；**R1 轮按 CTO O1 补注**：精确原反例 A(17→22)×2、B(10→17) 的折叠形态与合法 B→A 链不可区分，故防线必须在读取侧保留原始行）；
2. 每个 reason 恰好一次、无未知 reason（重复身份=重复经济效果）；
3. 每行 before+delta==after；delta 多重集匹配；
4. 无序链：恰一行起点为 initial，其终点=initial+delta=另一行起点，另一行终点==实测终值（同时接受 B→A 与 A→B 两种合法串行序；丢失更新形态"两行同起点 10"被拒）；
5. initial+总增量==实测终值。

时间戳从不用于推断执行顺序。

## 7. 证据保留与待业务决定

不变，见 `2026-09-07_MPANGO_MVP_INVARIANTS_R0_PENDING_DECISIONS.md`（取消撞收款/部分现金/赊销退货三项不设断言）。补充措辞规范：**"确认入口不产生账簿"为源码观察**（orders.py:590 走 CRUD+预留、未调用 OrderService CONFIRMED 记账分支），对照测试未对确认后账簿状态作任何断言；断言化须待业务合同决定收入/应收时点后进行。

## 8. 精确命令与运行环境

```bash
# 任务独占 PostgreSQL（一次性；任务结束已删除）
docker run -d --name mpango-zcode-inv-r0r2-20260907-pg --label mpango.owner=zcode-mvp-invariants-r0-r2 \
  -e POSTGRES_USER=inv_r0r2_lab -e POSTGRES_PASSWORD=<synthetic-disposable-password> -e POSTGRES_DB=inv_r0r2_lab \
  -p 127.0.0.1::5432 postgres:16-alpine     # 实际映射 127.0.0.1:57435

# 运行环境（仓库外 env 脚本注入；口令为合成 disposable 值，不随分支提交）
#   TEST_DATABASE_URL = DATABASE_URL = postgresql://inv_r0r2_lab:<pw>@127.0.0.1:57435/inv_r0r2_lab
#   MPANGO_INVARIANTS_R0_PG_CONTAINER = mpango-zcode-inv-r0r2-20260907-pg
#   MPANGO_INVARIANTS_R0_PG_OWNER     = zcode-mvp-invariants-r0-r2
#   MPANGO_ENV=staging  REDIS_URL=redis://127.0.0.1:1/15  SECRET_KEY=<64hex>
#   PUBLIC_FRONTEND_URL=http://127.0.0.1:1  REPORTING_USER_PASSWORD=<synthetic>
source /c/Users/Jeff0/MPANGO\ ERP/_zcode_mvp_invariants_r0r2_env.sh

# 测试运行（迁移由会话夹具对已核验目标执行，不再手工 alembic）
cd backend && <venv>/python -m pytest \
  tests/test_mpango_invariants_r0_r1_guards.py \
  tests/test_mpango_mvp_invariants_r0_concurrency.py \
  tests/test_mpango_mvp_invariants_r0_revocation.py
# 退出码：0=全绿（本轮预期不出现）；1=存在产品命名 RED（本轮 40 节点，33 PASS / 7 RED）
```

运行时：Python 3.12.10、SQLAlchemy 2.0.45、asyncpg 0.31.0、FastAPI 0.128.0、pytest 8.4.2、pytest-asyncio 0.26.0、PostgreSQL 16-alpine（任务容器）。venv 复用 R0 的仓库外环境（`_zcode_mvp_invariants_r0_venv`，依赖与基线 requirements 一致，未改动）。

## 9. GitNexus 流程记录（R1）

- `gitnexus analyze --skip-agents-md` 对任务 worktree 建立索引成功（R1 轮索引 commit 29bd720 up-to-date；R2 轮沿用同一 CLI）。`gitnexus impact adjust_stock` 等图查询失败："Trying to read a database file with a different version. Database file version: 42, Current build storage version: 40"——与 R0 及 CTO 2026-09-07 记录的同一不兼容，且在全新索引上仍复现，说明是 CLI 构建与存储格式版本错位，不是索引过期。CTO 本轮的 context/compare 可用性与本执行环境的查询结果不一致，如实并列记录，不互相否定。
- `gitnexus impact/context` 查询：与 R0/CTO 记录相同的存储版本不兼容（file version 42 vs build 40）即失败。如实报告：本轮未获得符号级影响图，不以文件计数冒充影响分析，不以过期图宣布零风险。替代：直接源码阅读——本候选改动全部位于 `backend/tests/`（3 个测试文件 + 1 个支持模块 + 1 个新守卫单测文件）与 `docs/`（3 个报告文件），不触碰任何产品符号；测试触达的产品入口已在 §1 表格逐行列出。
- 提交前变更核对：CLI 无 detect-changes 子命令（历史记录中的 detect_changes 为 MCP 工具面）。以 `git status --porcelain` + 暂存 diff 逐文件核对替代，staged 内容仅限上述 8 个任务文件，无产品文件。

## 10. 事故记录（R1 措辞修正）

**迁移命令误指向既有数据库（2026-09-07，R0 轮）。** R0 期间一次手工 `alembic upgrade head` 因只导出 TEST_DATABASE_URL 未导出 DATABASE_URL，按 alembic.ini 默认地址连到了 127.0.0.1:5432 的既有 mpango_erp 库。当时核对的证据：该库 `public.alembic_version` 读数为 037（与任务目标 head 相同）；命令输出没有任何 "Running upgrade" 行、也没有报错。**但仅凭 head=037 不能断定"绝无变更"**——无法排除该命令在既有库上产生其他写入或副作用的可能性，且当时未留存该库的完整前后对照。故按"变更情况未知"处理：该既有库是否受到任何影响，证据不足，不作无变更声明；该命令未被重放。R1 后的流程消除了这类风险：迁移不再手工执行，由归属证明通过后的会话夹具对显式核验目标执行。既有环境全程未被写入、重置或清理（本轮及 R0 轮的容器操作仅涉及各自任务独占容器）。

## 11. 资源清理结果

- 容器 `mpango-zcode-inv-r0r2-20260907-pg`：标签核验 `mpango.owner=zcode-mvp-invariants-r0-r2` 后删除（含匿名卷）。R0/R1 任务容器此前已按同流程删除。
- 测试自清理：全部租户 schema 与 public 行删除，最终运行后核查 `t_%`=0、wholesalers/retailers=0（RED 测试同样清理；F1 探针行随租户 schema 级联删除）。
- 安全演练证明拒绝路径零写入（错误容器声明演练后 schema 数为 0）。
- 未触碰：mpango_postgres、dc12r1_*、mpango_redis、mpango_prod_* 等全部既有容器/库/卷；外部审查目录只读未用。
- venv 与 env 脚本保留在仓库外（`_zcode_mvp_invariants_r0_venv`、`_zcode_mvp_invariants_r0r2_env.sh`，后者含合成 disposable 口令）；如需删除：`rm -rf`/`rm -f` 两者即可。

## 12. 停止点

按任务指令：R1 候选普通推送后停止，交 CTO 最终审查。不合并、不部署、不自行启动产品修复。本候选仍不能作为绿色合并候选：7 个命名 RED 是对基线真实缺陷的固化复现，修复后应原样转绿，不得修改预期。
