# P0 Phase 1 执行记录 — 打通 E2E 核心链路

**日期:** 2026-03-10  
**执行者:** AI Full-Stack Developer  
**依据:** `ai-ledger/architect/2026-03-10-mvp-gap-analysis.md` §4 P0 Action Plan  
**目标:** 打通"批发商入驻 → 商品管理 → 订单完成 → 库存扣减"核心链路

---

## 变更清单

### Task 1: Backend — 订单状态机 & 库存扣减

#### 1.1 `backend/crud/order.py`
- **STATE_TRANSITIONS** 字典新增 `pay`（confirmed → paid）和 `fulfill`（paid → fulfilled）两条流转规则
- 新增 `pay_order()` 函数 — 校验状态后将订单标记为已付款
- 新增 `fulfill_order()` 函数 — 校验状态后将订单标记为已发货
- 更新模块文档注释，反映完整状态机

#### 1.2 `backend/api/v1/orders.py`
- **`POST /orders/{id}/pay`** — 新路由，使用 `OrderService.transition()` 实现原子状态变更 + 分录记账
- **`POST /orders/{id}/fulfill`** — 新路由，使用 `OrderService.transition()` + **库存自动扣减**
  - 遍历 `order.items`，通过 `sku_code` 查找 `SKU.id`
  - 对 `inventory_stocks` 表执行 `quantity_on_hand -= item.quantity`
  - 在同一数据库事务中完成（原子性保障）
- 新增导入：`pay_order`, `fulfill_order` from `crud.order`

#### 架构决策
- `pay` / `fulfill` 端点复用 `return` 端点已有的 `OrderService.transition()` 模式，获得：
  - 行级锁（`SELECT FOR UPDATE`）
  - 领域状态机校验（`core/domain/order_state.py`）
  - 业务不变式检查（如"未付款不能发货"）
  - 复式分录记账（`LedgerService`）
  - 通知触发（fire-and-forget email/SMS）

---

### Task 2: Frontend — 服务层 & UI 联调

#### 2.1 `frontend/src/services/skuService.ts`（新建）
- 封装 `/api/v1/skus` 的完整 CRUD
- 方法：`getAll`, `getByCode`, `create`, `update`
- 类型定义：`SKU`, `SKUCreateRequest`, `SKUUpdateRequest`

#### 2.2 `frontend/src/services/orderService.ts`
- 新增 `pay(id)` → `POST /orders/{id}/pay`
- 新增 `fulfill(id)` → `POST /orders/{id}/fulfill`

#### 2.3 `frontend/src/pages/orders/OrderListPage.tsx`
- 新增 `handlePay` 处理函数 — 调用 `orderService.pay()`，显示成功 Toast
- 新增 `handleFulfill` 处理函数 — 弹出确认对话框 + 调用 `orderService.fulfill()`，显示成功 Toast
- 新增 `canPay()` / `canFulfill()` 辅助函数，基于 `ALLOWED_TRANSITIONS` 映射
- 操作栏新增：
  - **"Mark Paid"** 按钮（绿色） — 当 `status === confirmed` 时显示
  - **"Fulfill"** 按钮（翠绿色） — 当 `status === paid` 时显示

---

## 状态机完整流转图（实现后）

```
Draft → Confirmed → Paid → Fulfilled → Returned
  ↓        ↓                               
Voided  Cancelled                          
```

## E2E 核心链路（现已打通）

```
批发商入驻 (POST /wholesalers)
    ↓
录入商品 (POST /skus) + 初始化库存 (inventory_stocks)
    ↓
零售商注册绑定 (POST /retailers/register)
    ↓
创建订单 (POST /orders)
    ↓
确认订单 (POST /orders/{id}/confirm)  → 分录：DR 应收 / CR 收入
    ↓
标记付款 (POST /orders/{id}/pay)      → 分录：DR 现金 / CR 应收
    ↓
发货完成 (POST /orders/{id}/fulfill)  → 库存扣减 + 通知
    ↓
[可选] 退货 (POST /orders/{id}/return) → 冲销分录
```

## 修改文件列表

| 文件 | 操作 | 行数变化 |
|---|---|---|
| `backend/crud/order.py` | 修改 | +78 行 |
| `backend/api/v1/orders.py` | 修改 | +160 行 |
| `frontend/src/services/skuService.ts` | 新建 | +55 行 |
| `frontend/src/services/orderService.ts` | 修改 | +6 行 |
| `frontend/src/pages/orders/OrderListPage.tsx` | 修改 | +50 行 |

## 待办（Phase 2）

- [ ] 创建 SKU 管理页面（`SKUListPage.tsx`）— 后端 CRUD 已就绪，前端服务已创建
- [ ] 修复 Sidebar 404（Team、Settings 页面缺失）
- [ ] "Customers" 导航改为零售商绑定列表
- [ ] 创建 UserListPage（Team 页面）

---

*记录完毕。所有变更基于实际代码修改，未涉及猜测。*
