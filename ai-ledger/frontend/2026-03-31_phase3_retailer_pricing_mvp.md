# Phase 3 P0 — Frontend Retailer Pricing Integration

**日期**: 2026-03-31
**执行角色**: Frontend AI
**Phase**: 3 — Pricing First
**状态**: ✅ 完成

---

## 1. 业务背景

随着 Backend 实现了 `retailer_prices` 模型和价格下发，前端需要移除客户端所有硬编码和假逻辑，将服务端返回的真实价格无缝集成到 Retailer 的订货流程中，确保价格展示准确。对于尚未配置价格的商品，应给出合理的提示并阻止下单。

---

## 2. 修改范围与文件清单

### 类型定义更新
**文件**: `frontend/src/types/client.ts`
- 将 `ClientProduct` 中的 `price` 从 `number` 修改为 `number | null`，以匹配后端未定价商品返回 null 的契约。

### 商品列表 (Product List)
**文件**: `frontend/src/pages/client/ProductListPage.tsx`
- **价格展示**: 更新商品卡片，如果价格非空则显示格式化后的价格（如 `KES 1,250.00`）。
- **无价格态**: 若 `price` 为 `null`，则显示灰色的 `"Contact Supplier"` 标签，替代价格显示。

### 商品详情 (Product Detail)
**文件**: `frontend/src/pages/client/ProductDetailPage.tsx`
- **顶部信息区**: 同样增加了大号的价格展示或 `"Contact Supplier for Price"` 的提示。
- **实时小计**: 如果有价格，在修改数量（Quantity）时，实时展示 `Subtotal` 预估金额。
- **无价格态处理**: 将原来仅凭 `is_stock` 判断的错误文案扩展：当 `can_order` 为 `false` 时，明确区分是因为无库存 (`out of stock`) 还是未定价 (`No price configured. Please contact your supplier.`)。

### 购物车/下单页 (Create Order / Cart)
**文件**: `frontend/src/pages/client/CreateOrderPage.tsx`
- **行项目 (Line Item) 数据结构**: 在内部状态 `OrderLineItem` 中增加了 `price` 属性，以便在订单创建时能预览价格。
- **展示优化**: 订单项列表中展示单价。
- **总计估算 (Estimated Total)**: 添加了总价计算逻辑 `calculateTotal`，实时计算订单总额并展示在底部。注意这里标注为 "Estimated Total" 强调前端仅作估算展示，最终订单总额(Total Amount)仍以后端响应为准。
- **选择器卡片**: 浮层中的商品选择器也加上了价格标签，方便客户在选品时比对。

---

## 3. 设计原则执行确认

- [x] **无前端定价逻辑**: 所有的 `price` 数据纯粹来源于服务端 API 响应，没有打折、促销或运费等前端魔改逻辑。
- [x] **无回退价格**: 没有任何 `price || 0` 作为业务默认值的地方。如果无价格就是无价格（展示提示）。
- [x] **不提交价格到后端**: `CreateOrderRequest` 依然保持纯粹的 `sku_code` 和 `quantity`，不包含任何金额字段，完全遵循后端的安全和认证要求。

---

## 4. API 契约与假设

- 后端 `GET /client/products` 包含真实价格，未定价返回 `null`，并且对于未定价商品，`can_order` 直接为 `false`。
- 后端 `POST /client/orders` 会根据 SKU 和当前用户的身份严格计算总价，如果遇到未定价产品会抛出 HTTP 400（前端已有标准的 API Error 处理能力会直接通过 Alert 呈现）。

---

## 5. 发现的障碍与间隙 (Gaps/Blockers)

- 目前前端订单列表中只包含了 `item_count` 和 `total_amount`。订单详情页 (OrderDetailPage) 中订单历史直接从 `ClientOrder` 结构渲染了。经过核对，由于后端的 `ClientOrderItem` 本来就包含了 `unit_price` 和 `subtotal`，并且 `ClientOrder` 包含了真实的 `total_amount`，所以 `OrderListPage` 和 `OrderDetailPage` 实际上不需要修改结构代码，现有的 `formatCurrency` 即可完美工作。
- 编译检查通过 (`npx tsc --noEmit` 0 错误)。

验收达成。Retailer 现在可以基于真实价格产生有效订单。

---

## 6. 修正补丁: 详情页到购物车价格状态传递 (2026-03-31 10:22)

**问题**: 从 `ProductDetailPage` 点击 "Add to Order" 跳转到 `CreateOrderPage` 时，导航 state 中遗漏了 `price` 属性，导致 `CreateOrderPage` 渲染的 "Estimated Total" 在该路径下错误地显示为 `KES 0.00`。

**修复**:
- `frontend/src/pages/client/ProductDetailPage.tsx`
  - 修改了 `handleAddToOrder` 函数，在传递给 `navigate` 的 state payload 中加入了 `price: product.price`。

**验证路径**:
1. 从商品列表通过悬浮 Picker 添加商品 → 已正确取用 `product.price`
2. 从商品详情页添加商品跳转下单 → 现已正确携带 `price`，总计估算准确。

**状态**: 逻辑一致性已修复，后端未受影响，依然作为计价绝对权威。
