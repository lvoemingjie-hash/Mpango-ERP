# MPANGO-MVP-INVARIANTS-R1 任务记录：撤权链与库存并发修复（2026-09-08）

> 执行者：Windows ZCode（Zcode-W）。主管与最终审查：Windows Codex CTO。
> 验证层级：`V3_MERGE_CRITICAL`；声明上限：`PRODUCT_FIX_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW_ONLY`。
> 授权范围：诊断、实现、回归、自查及普通候选分支推送。不合并、不部署、不改业务合同、不处理退货经济语义。

## 0. 基线与分支身份

| 项 | 值 |
|---|---|
| BASE（fetch 后核对） | `1485c3f5b59e45357462e40975537cbf3932d3b0` = 远端 `zcode/mpango-mvp-invariants-r0-r2-2026-09-07` HEAD（ls-remote 精确一致） |
| 父链 | a511369e（R0-R1）→ 29bd720d（R0）→ 产品基线 bd2373cb（R0 系列未改产品码） |
| 本轮分支 | `zcode/mpango-mvp-invariants-r1-auth-stock-fix-2026-09-08`（自 BASE 普通提交） |
| worktree | `C:\Users\Jeff0\MPANGO ERP\worktrees\zcode_mpango_mvp_invariants_r1_fix_2026-09-08` |

R0-R2 候选已由 CTO 于 2026-09-08 裁决为 `ACCEPTED_AS_KNOWN_RED_REGRESSION_BASELINE_WITH_NONBLOCKING_OBSERVATION`，
并明确"下一步应制定撤权/refresh 与库存丢失更新的有界产品修复任务"。本任务即该修复轮。

目标：原 7 个产品命名 RED 中 **6 个转绿**（并发调整丢失更新、软删用户访问、停用租户访问、refresh×3）；
**并发重复退货（INVARIANT_R0_DOUBLE_RETURN）按指令继续独立列为已知未修复问题**，保持 RED。

## 1. 文件范围表（实施前登记）

产品代码（3 个文件，均为目标行为直接涉及）：

| 文件 | 变更 | 对应缺陷 |
|---|---|---|
| `backend/api/context/tenant.py` | `resolve_tenant_context` 增加 is_deleted 与租户（public.wholesalers）存续/状态核验，失败 401 fail-closed | INVARIANT_R0_SOFT_DELETED_USER_ACCESS / INVARIANT_R0_SUSPENDED_TENANT_ACCESS |
| `backend/api/v1/auth.py` | `refresh_token`（POST /auth/refresh 处理器）增加数据库主体/租户校验（contextual 分支），新增 `Depends(get_db_session)` 依赖 | INVARIANT_R0_REFRESH_NONEXISTENT_PRINCIPAL / _DELETED_USER / _SUSPENDED_TENANT |
| `backend/services/inventory_service.py` | `adjust_stock` 加锁重选增加 `.execution_options(populate_existing=True)`（对齐本模块 `_locked_stock_by_sku_code` 既有正确范式） | INVARIANT_R0_STOCK_LOST_UPDATE |

测试（5 个文件，必要测试与措辞更正）：

| 文件 | 变更 |
|---|---|
| `backend/tests/test_mpango_mvp_invariants_r0_revocation.py` | refresh RED 用例适配新函数签名（显式传 db）；新增真实 HTTP refresh 正负对照（活主体 200+新 token 可用、三类无效主体 401、无效签名/错误类型 401）；新增租户隔离对照；新增"拒绝不产生新会话"断言 |
| `backend/tests/test_mpango_mvp_invariants_r0_concurrency.py` | 新增读取 helper 行数保留对照（adjustment_movements 不去重，端到端 DB 级证明）；docstring 由"预期 RED"更新为"回归（修复后应 PASS）"，断言值不变 |
| `backend/tests/test_mpango_invariants_r0_r1_guards.py` | O1 措辞更正：更名误标"CTO 原反例"的用例并改docstring；补入精确原始三行反例 A(17→22)×2、B(10→17)（原始 3 行 SET 拒绝；其 dict 折叠形态与合法 B→A 链不可区分、必须接受——这正是读取 helper 必须保留原始行的原因） |
| `backend/tests/test_pw1r3_rate_limit_context.py` | **必要测试对齐（全量差分发现）**：`rl_tenant` 夹具的合成租户原本无 public.wholesalers 行——新租户存续不变量按设计对其 401（平台注册表外租户 fail-closed），两限流测试因此失败。夹具补一行精确任务自有 active wholesalers 行（teardown 按 id 精确删除）；限流契约断言零变化 |
| `backend/tests/mpango_invariants_r0_support.py` | 预留（最终未需改动，零字节变化） |

报告（docs/ai-reports/review/）：

| 文件 | 变更 |
|---|---|
| `2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_RECORD.md` | 本文件（范围表+调用链，首提交） |
| `2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_REPORT.md` | 最终任务报告（§交付清单） |
| `2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_RUN_LOG.md` | 开发期逐次运行、证伪、全量分类 |
| `2026-09-07_MPANGO_MVP_INVARIANTS_R0_TASK_REPORT.md` / `..._RUN_LOG.md` | 仅 O1 措辞更正（把 R2 合成的 A(10→15)/A(15→20)/B(20→27) 误标为"CTO 原反例/折叠后仍可识别"处改为准确表述；经济预期不变） |

不触碰：`.secrets.baseline`、治理验证器、依赖（requirements/poetry）、迁移（alembic/）、共享 conftest、HE2/R9、SKU 候选、
logout/密码重置策略、select-tenant 与 identity-only refresh（登记为范围外同型问题，见 §3）。

## 2. 调用链分析

### 2a. 撤权-访问链（HTTP 任意租户路由）

```
HTTP 请求（Authorization: Bearer <access>）
→ main.app AuthenticationMiddleware（绑定 JwtAuthStrategy，app 工厂绑定）
→ JwtAuthStrategy.authenticate（验签/过期/类型）
→ JwtAuthStrategy.resolve_tenant_context（auth/strategies/jwt.py:35 委托）
→ api.context.tenant.resolve_tenant_context（api/context/tenant.py:80）
   ├─ create_tenant_session（SET LOCAL search_path "<schema>", public）
   ├─ crud.user.get_user_with_permissions（crud/user.py:126）
   │    └─ select(User)…【无 is_deleted 过滤】→ 缺口 1
   ├─ 【从不读取 public.wholesalers.status / is_deleted】→ 缺口 2
   └─ TenantContext 挂 request.state
→ 路由执行（db = tenant_ctx.session）
→ finalize_tenant_context（success = response.status_code < 400 → commit/rollback）
```

缺口 1 → 软删用户（soft_delete_user 写入 is_deleted=true、is_active 保持 true）以旧 token 继续拿到 200（RED 3）。
缺口 2 → 租户 suspended 后任意活跃用户继续 200（RED 4）。

修复点即 `resolve_tenant_context`（中间件唯一汇聚点，Mock 策略有独立实现不受影响）：

1. `user.is_deleted == True` → 401 `USER_DELETED`；
2. 按token.tenant_id 查 `public.wholesalers`（显式 public. 前缀，避免 search_path 歧义）：行缺失或 `is_deleted` → 401 `TENANT_NOT_FOUND`；`status != 'active'` → 401 `TENANT_NOT_ACTIVE`。仅 `active` 放行（suspended/deactivated/provisioning/paused/archived 一律拒绝，fail-closed，与 wholesalers.status 列注释及 P10/P17 生命周期词汇一致）；
3. 查询失败：既有 `_is_missing_tenant_resource_error` 分支保留（缺 schema/表 fail-closed 401）；其余异常照旧传播（500，不签发、不放大静默失败）。

### 2b. 撤权-refresh 链

```
POST /api/v1/auth/refresh（HTTP；无 Authorization 依赖，refresh token 在 body）
→ api.v1.auth.refresh_token(request: RefreshTokenRequest)
   ├─ decode_token（验签/过期）→ 类型必须 refresh
   ├─ identity-only 分支：create_identity_token 纯重签【无 DB；范围外，登记】
   └─ contextual 分支：create_contextual_token 纯重签 claims【零 DB 校验】→ 缺口 3
```

真实 HTTP 依赖现状：该路由**没有任何 DB 依赖**（同文件 login/select-tenant 均用 `Depends(get_db_session)` 公共 schema 会话）。
修复：签名增加 `db: AsyncSession = Depends(get_db_session)`——HTTP 经 DI 注入、直呼测试显式传参，校验逻辑同一实现（不会"仅直呼有效"）。

contextual 分支校验（签名验过之后、重签之前）：

1. `get_wholesaler_by_id(db, payload.tenant_id)`（crud/wholesaler.py:13，已过滤 is_deleted）→ 行缺失 → 401 `TENANT_NOT_FOUND`；`status != 'active'` → 401 `TENANT_NOT_ACTIVE`；
2. 租户 schema 名**从 wholesaler 行派生**（`t_<hex>`），不信任 token 的 schema 声明；仍过 `validate_identifier` 后以 schema 限定 SQL 查 `{schema}.users` 行：缺失 → 401 `PRINCIPAL_NOT_FOUND`；`is_deleted` → 401 `PRINCIPAL_DELETED`；`is_active=false` → 401 `PRINCIPAL_INACTIVE`（与 select-tenant 的用户查询同范式，补上其缺失的 is_deleted 维度）；
3. 缺 schema/表错误 fail-closed 401（复用 `_is_missing_tenant_resource_error` 判定）；其余 DB 异常向外传播（500 同样不签发，且不把基础设施故障伪装成 token 无效）。

事务路径：校验只读，不写；会话由 FastAPI 依赖栈正常关闭。拒答路径零写入（HTTP 层无 logout 副作用）。

### 2c. 库存调整链（丢失更新）

```
POST /api/v1/inventory/adjust（HTTP：RBAC+日志后调服务）
→ InventoryService.adjust_stock（services/inventory_service.py:388）
   ├─ InventoryRepository.get_stock_by_sku_code（无锁读；行对象进入会话 identity map）①
   ├─ select(InventoryStock).with_for_update() 重锁 ②【无 populate_existing】
   ├─ qty_before = stock.quantity_on_hand ←②在 identity map 命中①的旧值，行锁白拿
   ├─ 计算/负库存 409/写 movement（before/after 均自旧值）
   └─ flush；HTTP 下由中间件 finalize（<400 commit）
```

并发交错（RED 复现形）：A 完成①后在仓-barrier 停；B 全程完成并 commit（10→17）；A 恢复，②拿到行锁但 ORM
不刷新已加载属性 → qty_before 仍为 10 → 写 10+5=15 覆盖 B 的 17 → 终值 15（外部证据与 R0 实测一致），且流水链
（两行同起点 10）与终值矛盾（assert_adjustment_chain 拒绝）。

修复：②加 `.execution_options(populate_existing=True)`（模块内 `_locked_stock_by_sku_code`:57-58 /
`_locked_stock_by_sku_id`:82-83 / `release_on_cancel`:176-177 / `deduct_on_fulfillment`:329-330 既有同款正确范式）。
锁后对象属性与已提交现实一致 → A 见 17 → 终值 22；流水链 B(10→17)→A(17→22) 完整一致。提交边界不动。

## 3. 同模块/同链路同型问题登记（范围外，如实记录不修）

| 位置 | 同型描述 | 处置 |
|---|---|---|
| `inventory_service.restock_on_return`（:553 加锁无 populate_existing，且函数顶部先无锁读） | 与 adjust_stock 完全同型的可利用丢失更新形态；属并发重复退货 RED 的回补路径 | **已知未修复**（指令明示重复退货本轮不修，保持 RED） |
| `order_service.transition`（:100 加锁，路由预读无锁） | 重复退货 RED 的状态机路径 | 同上，已知未修复 |
| `inventory_service.deduct_stock`（:268/:278）、`restock`（:512） | 加锁无 populate_existing，但函数内首次按 sku_id 取行（无同会话先前读）；可利用性取决于调用方是否预读 | 登记；本轮不改（不在目标 RED 内） |
| `auth.select-tenant` | 为 is_deleted 用户/非 active 租户铸造 contextual token（修复后该 token 在中间件处被拒，访问不可达，但铸造行为存在） | 登记；指令不扩大范围 |
| identity-only refresh | 无租户绑定，无法做单一 DB 主体校验，纯重签 | 登记；范围外 |
| `_get_user_with_permissions_cached`（auth.py:573） | RBAC 角色加载不过滤 is_deleted；修复后中间件先拒，实际不可达 | 纵深备注，不改 |
| logout/密码重置 | 无会话撤销平台/改密不撤会话 | 指令明示不改 |

## 4. 验证计划（对应指令第三节）

1. 任务独占 PG16（新容器、任务标签、七重归属核验、迁移 head=037 断言）——复用 R1 起的归属守卫机制；
2. 聚焦回归：R0 三文件（guards/concurrency/revocation）+ 新增 HTTP refresh/隔离对照。预期：原 7 RED 中 6 个转绿、
   `red_concurrent_full_return_single_economic_effect` 单独保持 RED，全部对照 PASS；
3. 证伪：分别退化三处修复关键点（tenant.py 撤权核验、auth.py refresh 校验、inventory_service populate_existing）
   → 对应语义断言必须 RED；恢复后字节一致且重新 GREEN；
4. 后端全量套件于同一独占环境运行，结果区分新增失败/既有失败/环境失败/skip-xfail；
5. 运行后残留核查（t_% schema=0、public 行=0）、错误容器归属演练零写入。

## 5. 实施历史（本节随实施追加）

1. **f905bcee**（首提交）：本任务记录（范围表+调用链），无代码变更。
2. 产品修复三处（见 §1 范围表与 §2 调用链）：
   - `api/context/tenant.py`：新增 `assert_tenant_active`（按 token.tenant_id 查
     `public.wholesalers`，仅 `status='active'` 且未删除放行；返回派生 schema 名）；
     `resolve_tenant_context` 增加 `USER_DELETED` 与租户存续/状态核验。
   - `api/v1/auth.py`：新增 `_validate_contextual_refresh_subject`（wholesaler 存在+active；
     schema 从行派生并过 `validate_identifier`；`{schema}.users` 行存在+is_active+非 is_deleted；
     缺 schema/表 fail-closed 401；其余异常传播不签发）；`refresh_token` 签名增加
     `db: AsyncSession = Depends(get_db_session)`，contextual 分支重签前调用校验；
     identity-only 分支保持不变（登记为范围外）。
   - `services/inventory_service.py`：`adjust_stock` 加锁重选加
     `.execution_options(populate_existing=True)`（对齐模块既有 `_locked_stock_by_sku_code`
     范式），锁后从行现状计算。
3. 测试更新：revocation 文件 refresh 三用例与活主体对照改真实 HTTP（POST /api/v1/auth/refresh），
   拒答断言同时验证零 token 物料；新增错误签名/错误类型对照与双租户隔离对照；concurrency 文件
   新增读取 helper 行数保留对照；guards 文件 O1 更正并补精确原反例对照；R0 报告/运行日志 O1 措辞更正。
4. 聚焦回归（任务独占 PG16）：45 节点 = 44 PASS + 1 已知 RED（重复退货，−200.0000 与基线同值）。
5. 证伪：D1a/D1b/D2/D3 四次退化分别触发对应语义 RED（归因互不波及），恢复后 sha256 字节一致、
   聚焦回归整体回绿（44 PASS + 1 已知 RED）。
6. GitNexus：本 worktree 新建索引成功；`impact` 查询在本轮可用（需 `--repo` 指定索引）——
   adjust_stock：1 直接调用方（api/v1/inventory.py:adjust_inventory）、0 受影响流程、LOW；
   resolve_tenant_context / refresh_token：图中 0 上游（HTTP 路由/中间件入口为图叶），
   以直读源码的调用链分析补充（§2）。与 R0-R2 记录的存储版本 42vs40 故障不同，本轮未复现该故障，如实并列。
7. 全量套件 + BASE 差分（详见 RUN_LOG §四）：候选与 BASE 同环境串行全量，逐节点差分仅有——
   6 个目标 RED 转绿、pw1r3 两测试因新租户存续不变量对"无 wholesalers 行的合成租户"按设计 401
   （必要测试对齐：`rl_tenant` 夹具补精确 active wholesalers 行 + 按 id 清理，限流断言零变化；
   对齐后 7 节点=6 PASS+1 既有 FAIL，后者 BASE 孤立复跑亦败）、新节点继承既有 MPANGO_ENV 泄漏。
   无未解释回归。
8. 自查 refinements：`TENANT_ACTIVE_STATUS` 常量单一来源（tenant.py 公共常量，auth.py 引用；
   纯命名重构零行为变化，重构后撤权文件 11/11 复绿、三文件终跑 44 PASS+1 已知 RED）；
   评估后**不**在访问路径增加 schema 声明交叉核验（登记为纵深防御备注：其防御价值以签名密钥
   已泄漏为前提，且会结构性破坏 pw1r3 合成 schema 设计）。
9. 残留说明：聚焦套件运行后残留核查为零（RUN_LOG §三）；全量两轮运行后库内留有 36 个 t_% schema
   与 5 行 wholesalers——来源为既有失败/错误测试文件的临时租户（29 个 alembic ERROR 类为主），
   另 1 行 PW1R3RL 源自一次被 timeout 终止的 pytest 进程（无法执行 teardown；夹具清理本身经
   前后计数核验无缺陷）。任务库为一次性容器，最终随容器删除；未触碰任何既有库。
