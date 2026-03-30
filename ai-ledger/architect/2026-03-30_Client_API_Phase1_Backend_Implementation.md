# Client App Phase 1 + 2 — Full Stack Implementation Report

**日期**: 2026-03-30  
**版本目标**: v0.3.0 — Retailer Client App  
**Phase**: 1 (Backend) + 2 (Frontend) 完成  
**状态**: ✅ Phase 1 + 2 完成

---

## 1. 背景

根据《Mpango ERP v0.2.3 功能实现状态盘点报告》中的识别，PRD v1.0 要求的**零售商客户端体验**（商品浏览、下单、订单历史）尚未实现。CTO 批准启动 Retailer Client 开发轨道，定位为 **Mpango 从 ERP → B2B 平台的第一步**。

CTO 同时下达了 3 个 P0 强制修正：

| # | 问题 | 修正 |
|---|---|---|
| ❶ | retailer_id 不能从前端传入（越权风险） | `retailer_id = server_resolve(current_user)` |
| ❷ | Client API 必须返回 View Model，不能暴露 DB Model | 新建 `schemas/client.py`，隐藏成本价，stock_level 枚举 |
| ❸ | 必须定义订单状态机 | 内部状态映射为 Client 可见状态：CREATED→CONFIRMED→DELIVERED |

---

## 2. 新建文件清单

| 文件 | 用途 |
|---|---|
| `backend/schemas/client.py` | Client View Model 定义（产品、订单、库存等级枚举、状态映射） |
| `backend/api/v1/client/__init__.py` | Client API 模块包 |
| `backend/api/v1/client/dependencies.py` | **核心安全组件**：`resolve_client_identity()` — 从 JWT 服务端解析 retailer_id |
| `backend/api/v1/client/products.py` | 产品浏览 API（列表 + 详情） |
| `backend/api/v1/client/orders.py` | 订单管理 API（创建 + 列表 + 详情 + 取消） |

## 3. 修改文件清单

| 文件 | 修改内容 |
|---|---|
| `backend/api/app.py` | 注册 `/api/v1/client/products` 和 `/api/v1/client/orders` 路由 |

---

## 4. API 端点清单

| Method | Path | 描述 | 安全机制 |
|---|---|---|---|
| `GET` | `/api/v1/client/products` | 商品列表（分页、搜索、分类筛选） | JWT + tenant guardrail + binding 验证 |
| `GET` | `/api/v1/client/products/{id}` | 商品详情 | 同上 |
| `POST` | `/api/v1/client/orders` | 创建订单 | retailer_id 从 JWT 服务端解析，**不接受请求体传入** |
| `GET` | `/api/v1/client/orders` | 订单列表（仅当前零售商） | 强制 `WHERE retailer_id = resolved_id` |
| `GET` | `/api/v1/client/orders/{id}` | 订单详情（仅本人订单） | 所有权校验 |
| `POST` | `/api/v1/client/orders/{id}/cancel` | 取消订单（仅 CREATED/CONFIRMED） | 所有权 + 状态机校验 |

---

## 5. CTO P0 修正落地详情

### ❶ retailer_id 安全解析

**文件**: `api/v1/client/dependencies.py` → `resolve_client_identity()`

解析链路：
```
JWT → user_id → tenant_schema.users.email
    → public.retailers WHERE email = user_email
    → public.wholesaler_retailer_bindings WHERE retailer_id + tenant_id + status='active'
    → return ClientIdentity(retailer_id=...)
```

任何环节失败均返回 HTTP 403，绝不 fallback。

### ❷ View Model 设计

**文件**: `schemas/client.py`

- `ClientProductSummary` / `ClientProductDetail`：不暴露 cost_price
- `StockLevel` 枚举：`OUT_OF_STOCK | LOW | MEDIUM | HIGH`（阈值: 0/10/50）
- `can_order = is_active AND quantity_on_hand > 0`
- `compute_stock_level()` 将原始库存数量转为枚举

### ❸ 订单状态机映射

**文件**: `schemas/client.py` → `CLIENT_VISIBLE_STATUSES`

```
Internal          → Client Visible
─────────────────────────────────
draft             → CREATED
confirmed         → CONFIRMED
partially_paid    → CONFIRMED
paid              → CONFIRMED
fulfilled         → DELIVERED
cancelled         → CANCELLED
voided            → CANCELLED
returned          → RETURNED
```

Client 侧权限：
- ✅ CREATE（创建订单）
- ✅ VIEW（查看自己的订单）
- ✅ CANCEL（仅 draft/confirmed）
- ❌ 不能 confirm / pay / fulfill / return

---

## 6. 架构原则遵循

| 原则 | 状态 |
|---|---|
| Stateless frontend | ✅ 所有状态通过 JWT 传递 |
| API first | ✅ 先建 API，前端后续对接 |
| Tenant-aware requests | ✅ 所有端点通过 JWT tenant claim 隔离 |
| 不新建表 | ✅ 复用现有 skus / inventory_stocks / orders / order_items |
| 不破坏现有架构 | ✅ 新增 /client/* 路由，不修改任何现有端点 |

---

## 7. 已知 TODO（留给后续 Phase）

| 项目 | 说明 |
|---|---|
| `price` 字段 | 当前返回 `0.00`，需等 CRM 定价模型（客户专属价/等级价）落地后接入 |
| `unit_price` in order items | 同上，当前 `0.00`，需定价模型 |
| 前端 Client App | Phase 2 — React + TypeScript + Tailwind |
| 集成验证 | Phase 3 — E2E 登录→浏览→下单→历史 |

---

## 8. Phase 2 — 前端 Client App 实现（已完成）

### 8.1 新建文件清单

| 文件 | 用途 |
|---|---|
| `frontend/src/types/client.ts` | Client View Model 类型定义（`ClientProduct`、`ClientOrder`、`StockLevel` 等） |
| `frontend/src/services/clientProductService.ts` | 对接 `/client/products` API |
| `frontend/src/services/clientOrderService.ts` | 对接 `/client/orders` API |
| `frontend/src/components/layout/ClientLayout.tsx` | 零售商端布局（顶栏 + 内容区 + 底部导航，移动端友好） |
| `frontend/src/pages/client/ClientLoginPage.tsx` | 零售商登录页（自动选择首个租户） |
| `frontend/src/pages/client/ProductListPage.tsx` | 商品列表（卡片网格、搜索、库存徽章） |
| `frontend/src/pages/client/ProductDetailPage.tsx` | 商品详情（描述、库存状态、数量选择器、加入订单） |
| `frontend/src/pages/client/CreateOrderPage.tsx` | 创建订单（行项管理、商品选择器弹窗、提交） |
| `frontend/src/pages/client/OrderListPage.tsx` | 订单列表（状态筛选标签、订单卡片） |
| `frontend/src/pages/client/OrderDetailPage.tsx` | 订单详情（项目列表、状态时间线、取消按钮） |

### 8.2 修改文件

| 文件 | 修改内容 |
|---|---|
| `frontend/src/router/AppRouter.tsx` | 新增 `/client/*` 路由树 + `ClientLayout` + 6 个 Client 页面导入 |

### 8.3 路由结构

```
/client/login          → ClientLoginPage（公开）
/client                → ProductListPage（需认证）
/client/products/:id   → ProductDetailPage
/client/orders         → ClientOrderListPage
/client/orders/new     → CreateOrderPage
/client/orders/:id     → OrderDetailPage
```

### 8.4 UI 设计要点

| 特性 | 实现 |
|---|---|
| 移动端优先 | `max-w-lg` 居中，底部导航栏，大触控目标 |
| 卡片式商品 | 2 列网格，图标占位、名称、SKU、库存徽章 |
| 库存展示 | `HIGH`→绿、`MEDIUM`→黄、`LOW`→橙、`OUT_OF_STOCK`→红（不暴露数字） |
| 订单创建 | 行项管理 + 底部弹窗式商品选择器 + 数量 +/- |
| 订单状态 | 3 步时间线（Created → Confirmed → Delivered）+ 取消状态 |
| 空状态 | 每个列表页均有图标 + 描述 + CTA 按钮 |
| 加载骨架 | 卡片和列表均有 `animate-pulse` 骨架屏 |

### 8.5 TypeScript 验证

```
pnpm tsc --noEmit → 0 errors
```

---

## 9. 完整用户流程

```
Retailer Login (/client/login)
  ↓ JWT authentication + auto tenant selection
Product List (/client)
  ↓ Browse, search, view stock levels
Product Detail (/client/products/:id)
  ↓ View description, select quantity, "Add to Order"
Create Order (/client/orders/new)
  ↓ Manage line items, add more products, submit
  ↓ POST /api/v1/client/orders (retailer_id from JWT)
Order Confirmation → redirects to Order Detail
  ↓
Order List (/client/orders)
  ↓ Filter by status, view history
Order Detail (/client/orders/:id)
  ↓ View items, status timeline, cancel if allowed
```

---

## 10. 已知 TODO（留给 Phase 3 及后续）

| 项目 | 说明 |
|---|---|
| `price` 字段 | 当前返回 `0.00`，需等 CRM 定价模型（客户专属价/等级价）落地后接入 |
| 商品图片 | 当前为图标占位，需接入商品图片上传/CDN |
| M-Pesa 支付 | PRD 要求，当前无支付网关集成 |
| Push 通知 | 订单状态变更通知零售商 |
| E2E 测试 | Phase 3 — 端到端集成验证 |
| 零售商注册自助流 | 当前需由批发商创建用户，未来需自助注册 |
