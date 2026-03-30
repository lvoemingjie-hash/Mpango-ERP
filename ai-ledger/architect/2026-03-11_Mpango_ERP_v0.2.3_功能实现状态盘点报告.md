# Mpango ERP v0.2.3 功能实现状态盘点报告

**日期**: 2026-03-11  
**版本基线**: v0.2.3 / v0.2.3-r1  
**分析依据**:
- `docs/#1Mpango_ERP_PRD_v10(DETAIL).md`
- `ai-ledger/backend/2026-03-11_v0.2.3_gap_fixes.md`
- `ai-ledger/frontend/2026-03-11_v0.2.3_frontend_adapters.md`
- `ai-ledger/ops/2026-03-11_v0.2.3_release_status_report.md`
- 已落地代码：`backend/api/v1/*`、`frontend/src/pages/*`、`backend/scripts/bootstrap_tenant_schema.py`

---

## 1. 执行摘要（Executive Summary）

当前 `v0.2.3` 已经不是“只有框架和壳子”的阶段，而是一个 **核心批发商后台链路已经可用** 的多租户 ERP 原型：

- **销售主链路** 已基本打通：登录、租户选择、SKU 管理、订单创建、确认、支付、履约、退货、库存扣减、财务概览、Dashboard KPI 已有真实代码和部署验证。
- **v0.2.3 新补齐的缺口** 主要集中在后端业务完备性上：CRM 零售商列表/详情、付款记录查询、库存手动调整与库存流水日志；其中这几项又已出现明确的前端适配痕迹。
- **但距离 PRD v1.0 的完整 MVP 目标仍有明显差距**：采购与供应商管理几乎未落地，客户信用/专属定价未见实现，库存预警与通知未见实现，零售商 App 侧的商品浏览/购物车/M-Pesa/COD/赊销闭环也没有在当前仓库与部署日志中形成明确证据。

**总体判断**：

- 当前版本更适合定义为：**“批发商 ERP 后台核心作业面已成型，CRM/库存运维/财务查询能力正在补齐，但 PRD v1.0 中的采购、供应商、信用定价、零售商端体验仍未完成。”**
- 若以 PRD v1.0 为满分基线，当前更接近 **“后台核心经营闭环可演示，完整业务闭环未达成”**。

---

## 2. 核心业务表与基础设施

### 2.1 已确切落地的底层基础

| 类别 | 已落地内容 | 说明 / 依据 |
|---|---|---|
| 多租户架构 | JWT 派生租户上下文 + `search_path` 隔离 | `api/context/tenant.py`、认证/租户上下文链路已部署验证 |
| 认证体系 | 登录、租户选择、RBAC 权限控制 | `/auth/login`、`/auth/select-tenant`，部署日志已验证 200 |
| 公共 schema 基础表 | `wholesalers`、`retailers`、`wholesaler_retailer_bindings`、`invitations`、`sys_jobs`、`sys_audit_logs`、`sys_reports` | 迁移与 VPS 部署排查日志可证实 |
| 租户 schema 核心业务表 | `users`、`roles`、`permissions`、`user_roles`、`role_permissions`、`skus`、`inventory_stocks`、`inventory_movements`、`orders`、`order_items`、`payments`、`ledger_entries` | `backend/scripts/bootstrap_tenant_schema.py` 明确创建 12 张表 |
| 财务 / BI 基础 | `rpt_*` 报表视图、`mv_sales_daily` 物化视图 | 迁移 `012/013` 与 VPS 修复日志可证实 |
| 部署基础设施 | Docker Compose + Postgres + Redis + Backend + Frontend + Gateway | VPS 已完成部署并经 `/health` 验证 |
| Seed / 演示数据 | Demo tenant、SKU、库存、订单、管理员账号 | `seed_demo_data.py` 与部署验证日志可证实 |

### 2.2 由基础表可反推出的当前边界

| 结论 | 说明 / 依据 |
|---|---|
| 销售、库存、支付、总账基础结构已具备 | 租户 schema 12 张表中已包含 `orders`、`payments`、`ledger_entries`、`inventory_*` |
| CRM 仅具备“零售商档案 + 绑定关系”的基础，不具备完整信用与价格体系 | 当前核心表与修复日志中未见客户等级、信用额度、专属价格相关实体 |
| 采购/供应商模块尚未进入核心租户 schema | `bootstrap_tenant_schema.py` 中完全没有 supplier / purchase_order / goods_receipt / accounts_payable 类表 |
| 高级审批、物流、上游供应商同步未进入当前数据模型 | PRD有规划，但当前表结构和 API 中均无对应痕迹 |

---

## 3. 功能状态矩阵（重点）

## 3.1 销售 / 订单

| 模块 | 子功能 | 当前状态 | 说明 / 依据 |
|---|---|---|---|
| 销售/订单 | 登录、身份认证、租户选择 | 已完整实现 | 后端 `/auth/login`、`/auth/select-tenant` 已部署验证成功；前端有 `LoginPage`、`WorkspaceSelectorPage` |
| 销售/订单 | 订单列表 / 订单详情 | 已完整实现 | `backend/api/v1/orders.py` 提供 `GET /orders`、`GET /orders/{id}`；前端 `OrderListPage` 已在 release log 中标记为 working |
| 销售/订单 | 订单创建 | 已完整实现 | `POST /orders` 已实现；前端订单页已对接 `orderService` |
| 销售/订单 | 订单确认（confirm） | 已完整实现 | `/orders/{id}/confirm` 已存在；前端订单页已接入操作按钮（release log） |
| 销售/订单 | 订单支付标记（pay） | 已完整实现 | `/orders/{id}/pay` 已实现；前端订单页已接入 `pay()`（release log） |
| 销售/订单 | 订单履约（fulfill） | 已完整实现 | `/orders/{id}/fulfill` 已实现；前端订单页已接入 `fulfill()` |
| 销售/订单 | 订单退货（return） | 已完整实现 | `/orders/{id}/return` 已实现；前端订单页已接入 `returnOrder()` |
| 销售/订单 | 履约后自动扣减库存 | 已完整实现 | `orders.py` 中 `fulfill_order()` 明确执行 `inventory_stocks.quantity_on_hand - item.quantity` |
| 销售/订单 | 订单中客户名回填 | 已完整实现 | `v0.2.3_gap_fixes.md` 明确修复 `retailer_name`；前端原本已渲染，无需改码 |
| 销售/订单 | 订单发票查看 / 下载 | 仅后端实现 | `finance.py` 提供 `GET /orders/{order_id}/invoice`；虽旧状态报告提到前端 service 已接，但本次 v0.2.3 日志未明确验证页面跑通，保守归为后端完成 |
| 销售/订单 | 零售商商品浏览与搜索（App 端） | 尚未实现 | PRD 明确要求零售商 App 首页、店铺切换、商品浏览搜索；当前仓库证据主要是批发商后台 `SKUListPage`，无零售商 App 页面或 E2E 证据 |
| 销售/订单 | 购物车与单店铺结算 | 尚未实现 | PRD 明确要求购物车、跨批发商隔离结算；当前 API / 前端中未见 cart 模块 |
| 销售/订单 | M-Pesa 支付 | 尚未实现 | PRD 指明 MVP 重点；当前仅见通用 payment 记录能力，未见 M-Pesa STK Push 接口集成 |
| 销售/订单 | COD 规则控制 | 尚未实现 | PRD要求可配置 COD；当前无客户级 COD 权限/规则模型 |
| 销售/订单 | 赊销支付 / 信用额度校验 | 尚未实现 | 当前未见 credit limit / repayment period / balance check 相关模型与接口 |
| 销售/订单 | 收货地址管理 / 配送备注 | 尚未实现 | PRD有要求；当前订单模型仅见 `notes`，无地址簿/收货地址模块证据 |
| 销售/订单 | 零售商端“我的订单”跨批发商查看 | 尚未实现 | 当前前端是批发商 ERP 后台路由，不是零售商 App 订单中心 |
| 销售/订单 | 物流信息 / 发货追踪 | 尚未实现 | PRD提到后续物流信息录入；当前无 shipment / tracking / driver / route 结构 |

## 3.2 CRM / 客户管理

| 模块 | 子功能 | 当前状态 | 说明 / 依据 |
|---|---|---|---|
| CRM | 邀请码生成与邀请链接 | 已完整实现 | `invitations.py` 提供创建与按 code 查询；前端有 `InvitePage` |
| CRM | 零售商注册与绑定关系 | 已完整实现 | `POST /retailers/register` + `GET /retailers/bindings` 已存在；邀请/绑定链路为既有功能 |
| CRM | 批发商查看客户列表（分页） | 已完整实现 | `v0.2.3_gap_fixes.md` 新增 `GET /retailers`；前端 `RetailerListPage` 已适配分页并已注册路由 `/retailers` |
| CRM | 客户详情查看 | 仅后端实现 | 后端已有 `GET /retailers/{retailer_id}`；但当前前端日志只明确列表页，未见客户详情页 |
| CRM | 客户档案手动新增/编辑/删除 | 尚未实现 | PRD要求完整档案维护；当前 CRM 主要是“绑定零售商列表”，未见 wholesaler 侧完整档案 CRUD 页面/API |
| CRM | 客户分级 / 标签 / 地区筛选 | 尚未实现 | 当前 `RetailerListPage` 展示的是 name/phone/email/address/status，未见等级/标签字段与筛选逻辑 |
| CRM | 客户信用额度与还款周期 | 尚未实现 | PRD明确要求；当前无对应数据模型/API |
| CRM | 客户专属定价 / 等级定价 | 尚未实现 | 当前无 price rule / customer pricing 相关表与接口 |
| CRM | 后台邀请状态（已发送/已注册/已过期/重发）完整运营面板 | 尚未实现 | 当前仅见 invitation create/lookup，与 PRD 要求的完整邀请运营面板仍有距离 |
| CRM | 批量导入客户（CSV/Excel） | 尚未实现 | PRD明确要求；当前无 import API / UI 证据 |

## 3.3 库存 / 商品

| 模块 | 子功能 | 当前状态 | 说明 / 依据 |
|---|---|---|---|
| 库存/商品 | SKU 列表与基础 CRUD | 已完整实现 | 后端 `/skus` CRUD 已存在；前端 `SKUListPage`、`SKUFormModal`、`/skus` 路由已存在 |
| 库存/商品 | 库存列表 / SKU 库存查看 | 已完整实现 | 后端 `GET /inventory/stocks`、`GET /inventory/stocks/{sku_code}`；前端 `InventoryPage` 已接入 |
| 库存/商品 | 按订单查看库存占用/关联库存 | 已完整实现 | `GET /inventory/orders/{order_id}/stocks` 已存在，属于后台辅助能力 |
| 库存/商品 | 手动库存调整 | 已完整实现 | `v0.2.3_gap_fixes.md` 新增 `POST /inventory/adjust`；前端 `InventoryAdjustModal` 明确已适配 |
| 库存/商品 | 库存流水日志 | 已完整实现 | 后端 `GET /inventory/logs`；前端 `InventoryLogPage`、`/inventory/logs` 已适配 |
| 库存/商品 | 库存调整审计字段（before/after/reason/operator） | 已完整实现 | `InventoryMovement` 模型与响应 schema 明确包含前后数量、原因、操作人 |
| 库存/商品 | 商品初始库存 seed | 已完整实现 | release log 明确 `_seed_inventory()` 为每个 SKU 初始化 `quantity_on_hand = 100` |
| 库存/商品 | 库存预警阈值 | 尚未实现 | PRD要求库存预警值与低库存提醒；当前 SKU / stock 页面与 schema 未见 warning threshold 字段 |
| 库存/商品 | 低库存预警看板 / 通知 | 尚未实现 | 当前 Dashboard 关注销售/现金流，不是低库存预警看板 |
| 库存/商品 | 下架商品对零售商端不可见 | 尚未实现 | 后台 SKU 有 `is_active`，但零售商端商品浏览未形成可验证前端链路 |
| 库存/商品 | 商品批量导入 Excel | 尚未实现 | PRD列为 MVP；当前无导入 API / 异步导入结果页 |
| 库存/商品 | 动态字段模板 / 自定义字段 | 尚未实现 | PRD新增要求；当前 SKU 结构为固定字段，无 JSON 自定义字段体系证据 |
| 库存/商品 | AI 辅助录入 / OCR | 尚未实现 | PRD标注 Phase 2；当前无实现证据 |
| 库存/商品 | 上游供应商商品同步 | 尚未实现 | PRD标注 Phase 3；当前无 supplier sync API/表 |

## 3.4 财务 / 账单 / BI

| 模块 | 子功能 | 当前状态 | 说明 / 依据 |
|---|---|---|---|
| 财务 | 财务总览（summary） | 已完整实现 | `GET /finance/summary` + 前端 `FinancePage` 已接入 |
| 财务 | 应收账款列表（receivables） | 已完整实现 | `GET /finance/receivables` + `FinancePage` 表格展示 |
| 财务 | Dashboard KPI 卡片 | 已完整实现 | `dashboards.py` KPI + `DashboardPage` 调用 `dashboardService.getKpiSummary()`；VPS 上已验证 200 |
| 财务 | Dashboard 销售趋势图 | 已完整实现 | `DashboardPage` 调用 `getSalesTrend()`；后端 `/dashboards/charts/sales-trend` 已存在 |
| 财务 | 付款记录列表 | 已完整实现 | `GET /payments` 后端已补齐；前端 `PaymentListPage` 已接入并注册 `/payments` |
| 财务 | 付款记录详情 | 仅后端实现 | `GET /payments/{payment_id}` 存在；当前前端只有列表页，无 payment detail 页面证据 |
| 财务 | 付款创建 | 仅后端实现 | `POST /payments` 已存在；当前没有明确的前端录入/收款页面证据 |
| 财务 | 发票投影视图 | 仅后端实现 | `/orders/{id}/invoice` 已存在；前端本次没有明确新增 invoice 页面 |
| 财务 | 报表/语义分析 API | 仅后端实现 | `/reports/analyze`、`/reports/schema/*` 已存在，但未见对应业务前端查询器 |
| 财务 | 采购应付账款 / 采购对账 | 尚未实现 | PRD明确放在采购后续；当前无 supplier AP 表、无采购对账 UI/API |
| 财务 | 赊销账期控制 | 尚未实现 | PRD在 CRM/Finance 有要求；当前无账期字段与风控规则证据 |
| 财务 | 自动支付回调驱动订单状态流转 | 尚未实现 | 当前 payment 更像记录型接口，未见真实支付网关回调与自动状态机闭环 |

## 3.5 系统设置 / 平台治理

| 模块 | 子功能 | 当前状态 | 说明 / 依据 |
|---|---|---|---|
| 系统设置 | 租户（wholesaler）管理 | 已完整实现 | 后端 `/wholesalers` CRUD；前端 `TenantListPage` 支持分页、创建、编辑、删除 |
| 系统设置 | 用户管理 | 仅后端实现 | 后端 `/users` CRUD + 角色分配齐全；当前未见 `UserListPage` |
| 系统设置 | 角色列表 / 权限分配 | 仅后端实现 | 后端 `/roles`、`PUT /users/{id}/roles` 已存在；前端未见 role/user management 页面 |
| 系统设置 | BI 资产 / 导出引擎 | 仅后端实现 | release status report 列出 `/exports`、`/data-export`、`/api/bi/assets`；前端未见对应页面 |
| 系统设置 | 系统设置页（Settings） | 尚未实现 | 旧报告明确 Sidebar 的 Settings 曾 404，当前已隐藏，不代表功能存在 |
| 系统设置 | 团队管理页（Team） | 尚未实现 | 后端用户接口有，但前端页面未落地 |
| 系统设置 | 审批流 / 高级流程配置 | 尚未实现 | PRD未在当前已落地表/API中体现 |

---

## 4. 三类结果汇总

## 4.1 已完整实现（包含前后端）

| 模块 | 子功能 | 当前状态 | 说明 / 依据 |
|---|---|---|---|
| 认证 | 登录、租户选择 | 已完整实现 | 部署日志已验证，前端页面存在 |
| 销售 | 订单列表、详情、创建、确认、支付、履约、退货 | 已完整实现 | 前后端均有明确代码与 release 证据 |
| 销售 | 订单客户名回填 | 已完整实现 | v0.2.3 后端修复，前端无缝受益 |
| 库存 | SKU 管理页与基础 CRUD | 已完整实现 | `/skus` 后端 + `SKUListPage` 前端 |
| 库存 | 库存查询 | 已完整实现 | `/inventory/stocks*` + `InventoryPage` |
| 库存 | 手动库存调整 | 已完整实现 | `/inventory/adjust` + `InventoryAdjustModal` |
| 库存 | 库存流水日志 | 已完整实现 | `/inventory/logs` + `InventoryLogPage` |
| CRM | 邀请页 / 绑定链路基础能力 | 已完整实现 | invitation API + `InvitePage` |
| CRM | 客户列表（分页） | 已完整实现 | `/retailers` + `RetailerListPage` |
| 财务 | 财务总览、应收账款列表 | 已完整实现 | `FinancePage` 对接 `/finance/summary`、`/finance/receivables` |
| 财务 | Dashboard KPI / 销售趋势 | 已完整实现 | `DashboardPage` 已接 BI 端点，且 KPI 在 VPS 验证通过 |
| 财务 | 付款记录列表 | 已完整实现 | `/payments` + `PaymentListPage` |
| 平台 | 租户管理（wholesaler 管理） | 已完整实现 | `/wholesalers` + `TenantListPage` |

## 4.2 仅后端实现（前端待对接）

| 模块 | 子功能 | 当前状态 | 说明 / 依据 |
|---|---|---|---|
| 销售 | 发票生成 / 下载 | 仅后端实现 | `/orders/{id}/invoice` 已存在，但本次无明确前端页面验证 |
| CRM | 客户详情 | 仅后端实现 | `/retailers/{id}` 已有，未见详情页 |
| 财务 | 付款详情 | 仅后端实现 | `/payments/{id}` 已有，未见详情页 |
| 财务 | 付款创建 | 仅后端实现 | `POST /payments` 已有，未见明确收款录入 UI |
| 财务 | Ad-hoc 报表 / 语义分析 | 仅后端实现 | `/reports/*` 已有，未见前端分析器 |
| 系统设置 | 用户管理 | 仅后端实现 | `/users` CRUD + 角色指派完备，前端页面缺失 |
| 系统设置 | 角色管理 / 角色分配 | 仅后端实现 | `/roles`、`/users/{id}/roles` 存在，前端缺失 |
| 平台 | BI 资产 / 导出能力 | 仅后端实现 | 有 API，无明确前端落地 |

## 4.3 尚未实现（未动工 / 缺失）

| 模块 | 子功能 | 当前状态 | 说明 / 依据 |
|---|---|---|---|
| 销售 | 零售商 App 商品浏览与搜索 | 尚未实现 | PRD要求明确，当前未见零售商端商品店铺前端证据 |
| 销售 | 购物车、结算、跨店铺购物车隔离 | 尚未实现 | 无 cart 数据结构/API |
| 销售 | M-Pesa 支付集成 | 尚未实现 | PRD MVP重点，当前无支付网关集成证据 |
| 销售 | COD / 赊销结算规则 | 尚未实现 | 无客户级支付策略/额度模型 |
| 销售 | 收货地址管理 | 尚未实现 | 无地址实体/API |
| 销售 | 发货物流追踪 | 尚未实现 | 无 shipment/tracking 结构 |
| CRM | 客户建档完整 CRUD | 尚未实现 | 现有 CRM 更接近“绑定零售商列表”，不是完整客户档案系统 |
| CRM | 客户等级、标签、信用额度、还款周期 | 尚未实现 | 无模型/API |
| CRM | 客户专属价 / 等级价 | 尚未实现 | 无 pricing rule 结构 |
| CRM | 批量导入客户 | 尚未实现 | 无 import API |
| 库存 | 库存预警阈值与低库存通知 | 尚未实现 | 当前无 alert 字段与通知机制 |
| 库存 | 商品批量导入 Excel | 尚未实现 | 无导入流程/API |
| 库存 | 动态商品字段模板 | 尚未实现 | 无 JSON 动态字段体系 |
| 库存 | AI 商品识别录入 | 尚未实现 | PRD 标为未来阶段，当前无证据 |
| 采购 | 供应商管理 | 尚未实现 | `bootstrap_tenant_schema.py` 无 supplier 表；无 API |
| 采购 | 采购订单管理 | 尚未实现 | 无 purchase order 表/API |
| 采购 | 收货入库 / 部分收货 | 尚未实现 | 无 goods receipt / PO receiving 结构 |
| 采购 | 采购应付账款 / 对账 | 尚未实现 | 无 supplier AP 模块 |
| 采购 | 上游供应商数据同步 | 尚未实现 | 无 supplier sync API/任务流 |
| 系统设置 | Settings 页面 | 尚未实现 | 无页面、无设置域模型 |
| 系统设置 | 高级审批流 | 尚未实现 | 当前代码与表结构中无体现 |

---


## 6. 最终结论

`v0.2.3` 的真实状态，不应表述为“PRD v1.0 的 MVP 基本做完”，而应更准确地定义为：

> **Mpango ERP 已完成批发商后台主干中的认证、订单、SKU、库存查询/调整、财务概览、CRM 列表等核心能力，形成了可演示的经营后台原型；但 PRD v1.0 中关于采购、供应商、信用定价、库存预警、零售商端采购体验等关键模块仍明显缺失。**

如果要给 CTO 一个简洁判断：

- **后台经营面**：已经进入可展示、可继续深化阶段。
- **PRD v1.0 完整度**：仍未达到完整 MVP 交付。

