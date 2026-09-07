# MPANGO-MVP-INVARIANTS-R0 任务报告（测试候选）

日期：2026-09-07。执行者：Windows ZCode。
性质：产品缺陷复现与回归测试候选。**本候选包含已知失败（命名 RED）回归测试，不是绿色合并候选，不能直接集成。** 未修改任何产品实现、生产 schema/迁移、HE2/R9 或 .secrets.baseline；未合并、未部署。

## 0. 基线与候选

| 项 | 值 |
|---|---|
| 预期基线 | bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f |
| `git fetch --all --prune` 后 `origin/product-dev-recovered` | bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f（一致，无漂移） |
| worktree | `C:\Users\Jeff0\MPANGO ERP\worktrees\zcode_mpango_mvp_invariants_r0_2026-09-07` |
| 任务分支 | `zcode/mpango-mvp-invariants-r0-2026-09-07`（自基线新建，普通推送，未合并） |
| 候选 SHA | 见推送记录（分支 HEAD）；报告自身不引用自 commit 前的 SHA |

fetch 期间唯一远端变化：`reports/lubuntu-validation` 前移（9c14ecc4→22648346），与产品基线分支无关，不影响本任务。

## 1. 新增测试与覆盖的真实产品路径

新增 3 个文件（均为新增，无产品文件改动）：

- `backend/tests/mpango_invariants_r0_support.py` — 共享夹具：loopback 数据库守卫（拒绝非本机库）、JWT 策略守卫（拒绝 MPANGO_ENV=test 的 Mock 路径）、用产品自身 `scripts/bootstrap_tenant_schema.bootstrap` 建租户 schema、逐测试唯一租户与清理。
- `backend/tests/test_mpango_mvp_invariants_r0_concurrency.py` — 4 个测试（2 对照 + 2 命名 RED）。
- `backend/tests/test_mpango_mvp_invariants_r0_revocation.py` — 8 个测试（3 对照 + 5 命名 RED）。

每个测试 docstring 按"正常对照 / 目标缺陷 / 环境前提 / 执行入口 / 未覆盖范围"五段声明。

| 测试 | 结果 | 真实产品路径 |
|---|---|---|
| test_r0_control_single_adjustment_and_failed_adjustment_rollback | PASS | `InventoryService.adjust_stock`（POST /api/v1/inventory/adjust 调用的同一服务函数）：单次调整生效、失败调整全额回滚（值与流水均不残留） |
| test_r0_red_concurrent_stock_adjustments_no_lost_update | **RED** `INVARIANT_R0_STOCK_LOST_UPDATE`（10+7+5 → 实际 15.00） | 同上，两个真实连接 + asyncio 事件屏障：A 读后暂停 → B 提交 → A 恢复 |
| test_r0_control_single_full_return_single_economic_effect | PASS | 订单全生命周期真实入口：`create_order`/`confirm_order`/`pay_order`（CanonicalPaymentService）/`fulfill_order`/`return_order`（OrderService.transition + restock_on_return）路由函数；单次退货恰一次经济效果 |
| test_r0_red_concurrent_full_return_single_economic_effect | **RED** `INVARIANT_R0_DOUBLE_RETURN_CASH`（refund cash −200.0000） | 同上生命周期 + 两个真实连接在 `return_order` 路由预读取处确定性交错 |
| test_r0_control_active_user_active_tenant_can_access | PASS | 完整 HTTP 栈（JWT 中间件 → resolve_tenant_context → RBAC → GET /api/v1/skus），ASGITransport |
| test_r0_control_deactivated_user_denied | PASS | 同上；证明 is_active=false 已被拒绝，缺口在 is_deleted/租户状态 |
| test_r0_red_soft_deleted_user_in_active_tenant_denied | **RED** `INVARIANT_R0_SOFT_DELETED_USER_ACCESS`（200） | 同上；软删状态与产品 `soft_delete_user` 写入一致（is_deleted=true、is_active 保持 true） |
| test_r0_red_active_user_in_suspended_tenant_denied | **RED** `INVARIANT_R0_SUSPENDED_TENANT_ACCESS`（200） | 同上；租户状态置 suspended（仓库当前无写该状态的 API 入口） |
| test_r0_red_refresh_nonexistent_principal_no_session | **RED** `INVARIANT_R0_REFRESH_NONEXISTENT_PRINCIPAL` | `api.v1.auth.refresh_token`（POST /api/v1/auth/refresh 处理器，无认证依赖属产品现状） |
| test_r0_red_refresh_soft_deleted_user_no_session | **RED** `INVARIANT_R0_REFRESH_DELETED_USER` | 同上；用户行真实存在后软删 |
| test_r0_red_refresh_suspended_tenant_no_session | **RED** `INVARIANT_R0_REFRESH_SUSPENDED_TENANT` | 同上；活跃用户 + suspended 租户 |
| test_r0_control_refresh_live_subject_issues_usable_session | PASS | refresh 对活主体签发的新 access token 在 HTTP 路由上真实可用（证明 RED 案例唯一变量是主体存续） |

## 2. 基线 PASS/RED 汇总

完整运行（任务独占 PostgreSQL 16，真实服务与真实数据库，无 SQL mock，无 sleep）：**12 个测试，5 PASS（全部对照），7 命名 RED（全部为目标缺陷复现）**。多次运行结果确定一致。运行明细见 `2026-09-07_MPANGO_MVP_INVARIANTS_R0_RUN_LOG.md`。

## 3. 业务写入口表（二.1 交付）

事实来源：基线源码直接阅读 + 只读探查。事务所有者统一说明：租户路由经 `get_tenant_db_session`，commit 由认证中间件 `finalize_tenant_context(success=2xx)` 持有；路由/服务一般只 flush。public 路由用 `get_db_session`，部分端点自 commit。

| 动作 | 路由 | 服务/CRUD | 加锁位置 | 流水/旁路写入 | 既有测试 |
|---|---|---|---|---|---|
| 创建订单 | POST /api/v1/orders（orders.py:354） | 路由内校验绑定/服务端解价 → `crud.order.create_order`（crud/order.py:323） | 无 | 无 | 各 schema 契约测试 |
| 确认 | POST /api/v1/orders/{id}/confirm（orders.py:590） | 预读取（无锁）→ `crud.confirm_order`（crud/order.py:387）+ `InventoryService.reserve_on_confirm` | 库存行 `FOR UPDATE + populate_existing`（inventory_service.py:53） | inventory_reservations + stocks；**不写 ledger_entries**（OrderService CONFIRMED 记账分支未被此入口调用） | test_s5d5 等（种入 confirmed 单，未见真实入口记账断言） |
| 收款 | POST /api/v1/orders/{id}/pay（orders.py:649） | `_get_order_by_id_for_update`（FOR UPDATE，orders.py:220）→ `CanonicalPaymentService.confirm_payment`（skip_prechecks=True，锁定单传入） | 订单行 FOR UPDATE；幂等键两次预查 + 唯一约束 | payments；OrderService PAID 时按整单额记 cash/receivable（order_service.py:290）；credit 记绑定余额 ±；到 PAID 后 `update_cash_transfer_to_completed`（payment_repository.py:234） | test_dc11d（并发回放）、test_dc12r1_s3_s2b_i2a |
| 履约 | POST /api/v1/orders/{id}/fulfill（orders.py:894） | 预读取 → `db.expire(order)` 强制重读 → OrderService.transition(FULFILLED) → `deduct_on_fulfillment` | 订单行 FOR UPDATE（对象已 expire）；库存行 FOR UPDATE + populate_existing | inventory_movements（deduction）、reservations→consumed | 部分 |
| 取消（供应商） | POST /api/v1/orders/{id}/cancel（orders.py:988） | **预读取（无锁）**，`release_reservation` 由旧状态决定 → `crud.cancel_order`（crud/order.py:495）+ `release_on_cancel` | 无订单锁；库存行 FOR UPDATE + populate_existing | reservations→released | 无并发用例 |
| 取消（零售商） | POST /api/v1/client/orders/{id}/cancel（client/orders.py:381） | 双键归属读取（无锁）→ 同一 `crud.cancel_order` | 同上 | 同上 | 少量 |
| 退货 | POST /api/v1/orders/{id}/return（orders.py:1048） | **预读取（无锁）**→ OrderService.transition(RETURNED)（FOR UPDATE 但无 populate_existing，order_service.py:96）→ `restock_on_return` | 库存行 FOR UPDATE（无 populate_existing，inventory_service.py:549） | ledger_entries（reference_type='refund'：revenue +、cash −）+ inventory_movements（restock） | 无并发用例 |
| 申报确认 | POST /api/v1/declarations/{id}/confirm（declarations.py:298） | `PaymentDeclarationService.confirm_declaration`（payment_declaration_service.py:167）：声明行 FOR UPDATE → `CanonicalPaymentService.confirm_payment(force_completed=True, allocate_receipt=True)` | 声明行 + 绑定行 + 订单行 FOR UPDATE | payment_declarations、payments（completed+收据）、orders、receipt_sequences | test_dc12r1_s3_s2b_i2b |
| 库存调整 | POST /api/v1/inventory/adjust（inventory.py:176） | `InventoryService.adjust_stock`（inventory_service.py:388） | 库存行 FOR UPDATE **无 populate_existing（缺陷点）** | inventory_movements（adjustment） | 本轮新增 |
| 用户停用 | PUT /api/v1/users/{id}（users.py:172） | `update_user`（is_active） | 无 | users | 少量 |
| 用户删除（软） | DELETE /api/v1/users/{id}（users.py:228） | `soft_delete_user`（crud/user.py:307）：is_deleted=true，**不动 is_active** | 无 | users | 少量 |
| 租户停用 | **无 API 入口**（全仓无写 public.wholesalers.status 的路由；platform v0 只读） | — | — | — | 无 |
| refresh | POST /api/v1/auth/refresh（auth.py:450） | 纯重签：decode → 按 claims 重发 access+refresh，**零数据库校验** | 无 | 无 | 本轮新增 RED |
| logout | POST /api/v1/auth/logout（auth.py:550） | 无状态，无服务端撤销（docstring 自认 MVP） | 无 | 无 | 无 |
| 密码重置 | POST /api/v1/auth/reset-password（auth.py:844） | `PasswordResetService.consume_reset`（password_reset_service.py:305）：重置令牌行 FOR UPDATE、跨 schema 扇出改密 | 重置令牌行 FOR UPDATE | users.password_hash（多 schema 副本） | test_dc12r1_j1_h2b |

## 4. 两个付款入口调查（二.3 交付）

**`CanonicalPaymentService.confirm_payment`（canonical_payment_service.py:163）——唯一在线付款写入口：**

- 订单状态校验：非 confirmed/partially_paid 拒绝（:273-278）；PAID 单仅接受 cash/transfer 回款且有 credit exposure（:243-264）；credit 规则（单一、无先行现金、金额=整单，:279-298）。
- 订单行锁：`_get_order_by_id_for_update` FOR UPDATE（:115-121, :215）。
- 幂等：`get_by_idempotency_key` 预查 + replay 返回（:200-236）+ 数据库唯一约束兜底（路由层 IntegrityError 恢复，orders.py:842）。
- 状态推进 pending→completed：非 credit 的 cash/transfer 在订单到 PAID 后由 `update_cash_transfer_to_completed`（payment_repository.py:234）批量置 completed（canonical :366-367）；credit 回款与 force_completed（申报确认）直接以 completed 落库；否则为 **pending**（草稿收款形态）。
- 余额更新：credit 销售加绑定余额（:351-357）；credit 回款减余额（:337-343，走 `PaymentService._apply_outstanding_balance_delta`）。
- 记账：通过 `OrderService.transition`，PAID 时按整单额记 cash/receivable（order_service.py:290-309）；PARTIALLY_PAID 不记账（部分现金 40 无账簿即源于此）。

**`PaymentService.create_payment`（payment_service.py:56）——当前不可达的旁路实现：**

- HTTP 入口 `POST /api/v1/payments` 已在路由层直接禁用（payments.py:91-97，恒 409 PAYMENT_WRITE_PATH_DISABLED 并指向订单付款入口）。
- 全仓生产代码无其他调用者（仅 Canonical 复用其 `_apply_outstanding_balance_delta`；grep 证实）。
- 与 canonical 的差异：**无订单状态检查**（draft 也能建 payment——CTO D02 的"草稿付款风险"在该函数源码层面成立，但因路由禁用当前不可达）、**无订单行锁**、**无订单状态推进、无任何 ledger 写入**、transfer 直接 completed 否则 pending、credit 加余额、幂等键仅查重不与状态机联动。
- 结论（含证据边界）：本轮未重放"演练库四笔零收款有现金账订单"的写入溯源——**不能**用该演练库现象证明任何一条路径是写入来源（CTO D01 裁定维持）。源码层面可证的是：canonical 入口有完整状态门 + 幂等 + 状态推进；`create_payment` 是缺同 等 防线的残留实现。修复方向是收敛/删除旁路实现，而不是新造状态机。

## 5. 外部结论的证实 / 修正 / 仍缺证据

**已证实（本轮独立复现，命名 RED）：**
1. 库存并发丢失更新：10+7+5 → 15.00（外部 15 一致）；失败回滚本身正常（对照 PASS）。
2. 并发完整退货双计：refund cash −200、revenue +200（外部一致）；对照单次退货恰 −100/+100、restock 1 次。
3. 软删用户（is_active 保持 true）在活跃租户持旧 token 访问 GET /api/v1/skus → 200。
4. 活跃用户在 suspended 租户 → 200。
5. refresh 对不存在主体/软删用户/停用租户均照发新会话（外部"refresh_nonexistent_principal_issued"扩展到三个场景）。
6. deactivate（is_active=false）路径现状已正确拒绝（外部报告未单独重跑的活跃租户软删 HTTP 场景，本轮补齐；同时证明缺口精确在 is_deleted 与租户状态，不是整个解析器）。
7. 生命周期对照证实：确认入口不产生任何 ledger（外部"确认绕过记账"的源码事实，本轮以真实入口对照测试固化观察基础）。

**修正/收窄：** 无。本轮结果与外部报告及 CTO D01/D02 裁定一致，未发现需修正的外部结论。补充证据边界：并发测试直接调用路由函数，绕过 HTTP 依赖层（与外部探针同一边界）；撤权测试走完整 HTTP 栈，但 access token 为测试进程签名材料签发（非登录端点产出）。

**仍缺证据（留给下一轮）：** 平台身份 guard 与 platform_operators 实时校验；密码重置后旧 refresh 会话的实际存活链（本轮未写该组合测试）；logout 无撤销的端到端影响；多 worker/重启下的中间件幂等（进程内字典）；PostgreSQL 15 生产版本对照（本轮用 16，与外部一致；根因在 ORM 层，与版本无关，但未做 15 验证）。

## 6. 证据保留：取消撞收款 / 部分现金 / 赊销退货（二.4 交付）

三项**未转为断言型测试**（任务指令：预期结果待业务合同决定，不自行规定）。外部已复现证据保留于 `AI_REPORT_INBOX/external-architecture-2026-09-06/`（counterexamples.json / supplementary-probes.json），本轮源码定位如下，待业务决定事项详见 `2026-09-07_MPANGO_MVP_INVARIANTS_R0_PENDING_DECISIONS.md`：

1. **取消撞收款**：取消路由用预读对象判断释放预留（orders.py:1012）并无锁调 `crud_cancel_order`；收款事务在其间提交后订单仍转 cancelled（外部 counterexamples.json：state=cancelled, payment=100）。待决定：已有收款（部分/全额）时取消的合法性与经济后果（原路退回/转预收/拒绝取消）。
2. **部分现金不入账**：PARTIALLY_PAID 不产生任何 ledger；到 PAID 按整单额补记（order_service.py:290）。待决定："已收现金必须逐笔可核对"与"整单结清时点"的记账政策（含确认时点收入/应收）。
3. **赊销退货**：完整退货固定记 revenue +/cash −（ledger_service.py:319-359），不冲应收、不清绑定余额（外部 supplementary-probes.json：outstanding 仍 100、cash −100、实收 0）。待决定：未收应收冲销 vs 应退款 vs 实际退款三分事实及绑定余额清算规则。

## 7. 修复建议与最小涉及范围

| 优先 | 缺陷 | 最小修复面 | 是否依赖 SKU/业务合同 |
|---|---|---|---|
| 1 | refresh/撤权失效链 | `api/v1/auth.py` refresh 增加主体/租户/会话校验；`api/context/tenant.py` resolve_tenant_context 增加 is_deleted 与租户状态检查（或 `crud/user.py get_user_with_permissions` 过滤 is_deleted）；users 表需会话版本/撤销载体（迁移） | **不依赖**（策略细节：撤销即时性 vs TTL 由所有者确认即可开工） |
| 2 | 库存调整丢失更新 | `inventory_service.py adjust_stock`（:415）与 `restock_on_return`（:549）补 `populate_existing=True`（照 :58 既有模式）；或改条件原子 UPDATE | **不依赖** |
| 3 | 并发退货双计 | `order_service.transition` 锁读补 populate_existing；退货/冲销分配业务唯一标识 + 唯一约束（涉及 orders/ledger 迁移） | 状态读新鲜度修复**不依赖**；业务唯一键形态需与退货政策协调，但可先落"订单一次性退货"唯一键 |
| 4 | 取消撞收款 | 取消入口改锁后读 + 原状态条件更新，共享命令边界 | **部分依赖**：技术防护（锁后拒绝）不依赖；"有收款能否取消"必须等业务合同 |
| 5 | 部分现金/确认记账/赊销退货语义 | ledger_service/order_service 记账时点与事实表 | **依赖**：必须等业务/会计决策（D04） |
| 6 | 付款旁路收敛 | 删除或显式废弃 `PaymentService.create_payment`（当前不可达） | **不依赖**（纯收敛） |

优先级 1/2 即外部报告建议顺序 1-2 的 Windows 产品线部分；3-5 与 SKU 路径/迁移协调（CTO：共同订单/库存路径不未经协调同时修改）。

## 8. 精确命令与运行环境

```bash
# 任务独占 PostgreSQL（一次性，任务结束已删除；口令为合成 disposable 值，仅存在于
# 运行时环境与已删除容器，不在仓库内留存）
docker run -d --name mpango-zcode-inv-r0-20260907-pg --label mpango.owner=zcode-mvp-invariants-r0 \
  -e POSTGRES_USER=inv_r0_lab -e POSTGRES_PASSWORD=<synthetic-disposable-password> -e POSTGRES_DB=inv_r0_lab \
  -p 127.0.0.1::5432 postgres:16-alpine     # 实际映射 127.0.0.1:61310

# 公共迁移（一次性）
cd backend && DATABASE_URL=postgresql://inv_r0_lab:<synthetic-disposable-password>@127.0.0.1:61310/inv_r0_lab \
  REPORTING_USER_PASSWORD=<synthetic-disposable-password> MPANGO_ENV=staging \
  <venv>/python -m alembic upgrade head     # → 037_payment_declarations_schema

# 测试运行（两个文件，一次完整运行 ≈50s）
cd backend && TEST_DATABASE_URL=$DATABASE_URL DATABASE_URL=$DATABASE_URL \
  MPANGO_ENV=staging REDIS_URL=redis://127.0.0.1:1/15 SECRET_KEY=<64hex> \
  PUBLIC_FRONTEND_URL=http://127.0.0.1:1 REPORTING_USER_PASSWORD=<synthetic-disposable-password> \
  <venv>/python -m pytest tests/test_mpango_mvp_invariants_r0_concurrency.py \
                          tests/test_mpango_mvp_invariants_r0_revocation.py
```

运行时：Python 3.12.10、SQLAlchemy 2.0.45、asyncpg 0.31.0、FastAPI 0.128.0、pytest 8.4.2、pytest-asyncio 0.26.0、PostgreSQL 16-alpine（专用容器）。依赖版本与外部审查运行时一致。venv 在仓库外（`C:\Users\Jeff0\MPANGO ERP\_zcode_mvp_invariants_r0_venv`），不随分支提交。测试文件含环境守卫：数据库 host 非 loopback 或 MPANGO_ENV=test（Mock 策略）时直接失败，防误指向既有环境。

## 9. GitNexus 流程记录

- 编辑前 impact：`gitnexus analyze --skip-agents-md`（worktree）成功建索引；`gitnexus impact/context` 查询失败："Trying to read a database file with a different version. Database file version: 42, Current build storage version: 40"（与 CTO 2026-09-07 审阅记录的同一不兼容）。以直接源码阅读替代：本候选仅新增测试文件，未触碰任何产品符号；各测试触达的产品入口已在第 1/3 节逐一列出。
- 提交前 detect_changes：CLI 1.5.3 无该子命令（历史记录中的 detect_changes 为 MCP 工具面）。以 `git status --porcelain` + `git diff --stat` 逐文件核对替代，staged 内容 = 5 个新文件（3 测试 + 2 文档 + 运行日志），无产品文件。

## 10. 事故记录（如实）

一次 `alembic upgrade head` 因仅导出 TEST_DATABASE_URL 未导出 DATABASE_URL，回退到 alembic.ini 硬编码地址（127.0.0.1:5432 既有 mpango_erp 库）。只读核查确认该库当时已在 head 037，命令为无操作（no output 的 upgrade），**未产生任何变更**。随后修正环境变量并仅对任务库执行迁移。既有环境全程未被写入、重置或清理。

## 11. 资源清理结果

- 容器 `mpango-zcode-inv-r0-20260907-pg`：标签核验 `mpango.owner=zcode-mvp-invariants-r0` 后 `docker rm -f` + 匿名卷删除（见下方清理命令输出记录）。
- 测试自清理：全部租户 schema（DROP CASCADE）与 public 行删除，运行后核查 `t_%` schema = 0、wholesalers/retailers = 0。
- 未触碰：mpango_postgres、dc12r1_*、mpango_redis、mpango_prod_* 等全部既有容器/库/卷；外部审查目录与其 lab-venv 只读未用。
- venv 目录保留（仓库外，供复核重跑）；如需删除：`rm -rf "C:\Users\Jeff0\MPANGO ERP\_zcode_mvp_invariants_r0_venv"`。

## 12. 停止点

按任务指令：完成测试候选提交与普通推送后停止，交 CTO 审查。不自动修产品、不合并、不部署。本轮明确不能作为绿色合并候选：7 个命名 RED 是对基线真实缺陷的固化复现，修复后应原样转绿，不得修改预期。
