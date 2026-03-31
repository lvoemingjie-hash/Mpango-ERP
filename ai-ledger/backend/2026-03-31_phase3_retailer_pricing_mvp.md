# Phase 3 P0 — Retailer Pricing MVP

**日期**: 2026-03-31
**执行角色**: Backend AI
**Phase**: 3 — Pricing First
**状态**: ✅ 完成

---

## 1. 业务背景

CTO Phase 3 执行指令明确指出：没有定价，零售商订单在财务上毫无意义。
此前 `GET /client/products` 和 `POST /client/orders` 中的 `price` / `unit_price`
均硬编码为 `0.00`。Phase 3 P0 的首要任务是用服务端解析的真实售价替换它们。

---

## 2. 数据模型

### 新增表: `retailer_prices` (租户 schema)

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | gen_random_uuid() |
| `retailer_id` | UUID NOT NULL | 公共 schema retailers.id |
| `sku_id` | UUID NOT NULL | 租户 schema skus.id |
| `price` | NUMERIC(12,2) NOT NULL | 该零售商的售价 |
| `created_at` | TIMESTAMPTZ | 自动 |
| `updated_at` | TIMESTAMPTZ | 自动 |
| `is_deleted` | BOOLEAN | 软删除 |
| `created_by` / `updated_by` | UUID | 用户追踪 |

**唯一约束**: `(retailer_id, sku_id)` — 每个零售商对每个 SKU 只有一个价格。

**设计原则**:
- 不做促销引擎、折扣规则引擎
- 简单的 retailer + SKU → price 查找
- 价格是服务端权威数据，永远不从客户端输入

---

## 3. 文件变更清单

### 新建文件

| 文件 | 用途 |
|---|---|
| `backend/models/retailer_price.py` | ORM 模型，继承 BaseModel (租户 schema) |
| `backend/alembic/versions/017_retailer_prices.py` | 迁移: 建表 + 索引 + 唯一约束 |
| `backend/repositories/pricing_repository.py` | get_price, get_prices_bulk, set_price |
| `backend/tests/test_phase3_pricing.py` | 12 个测试覆盖全矩阵 |

### 修改文件

| 文件 | 变更 |
|---|---|
| `backend/models/__init__.py` | 注册 `RetailerPrice` 导出 |
| `backend/schemas/client.py` | `price` 字段改为 `Optional[Decimal]`，`can_order` 条件增加 `has_price` |
| `backend/api/v1/client/products.py` | 两个端点均 LEFT JOIN `retailer_prices`，返回真实价格 |
| `backend/api/v1/client/orders.py` | 订单创建时从 `retailer_prices` 解析 `unit_price`，无价格则拒绝 |
| `backend/tests/conftest.py` | 测试 bootstrap 增加 skus, inventory_stocks, retailer_prices 表 |

---

## 4. API 行为变更

### GET /client/products

- 之前: `price: 0.00`, `can_order: in_stock`
- 之后: `price: <real_price | null>`, `can_order: in_stock AND has_price`
- 无价格的产品显示 `price: null` 和 `can_order: false`

### GET /client/products/{id}

- 同上逻辑，单产品详情

### POST /client/orders

- 之前: `unit_price: 0.00` (硬编码)
- 之后: `unit_price` 从 `retailer_prices` 服务端解析
- 无价格的 SKU 返回 400: `"No price configured for '{sku_code}'. Please contact your supplier."`
- `total_amount` 从解析的 `unit_price × quantity` 累加计算
- 请求体中 **无** price/unit_price 字段 — 结构上不可能注入

---

## 5. 安全保证

| 保证 | 实现方式 |
|---|---|
| 价格服务端权威 | `retailer_prices` 表 LEFT JOIN，不接受客户端价格 |
| 无价格注入 | `ClientOrderItemRequest` schema 仅有 `sku_code` + `quantity` |
| 零售商隔离 | JOIN 条件包含 `retailer_id`，A 看不到 B 的价格 |
| 租户隔离 | 表在租户 schema 内，遵循 search_path 隔离 |
| 无价格产品不可下单 | 订单创建时检查 `sell_price is None` → 400 错误 |

---

## 6. 测试矩阵

| # | 测试 | 验证点 |
|---|---|---|
| 1 | `test_get_price_returns_correct_price` | 单价格查询正确 |
| 2 | `test_get_price_returns_none_for_unpriced` | 无价格返回 None |
| 3 | `test_get_prices_bulk` | 批量查询只返回有价格的 |
| 4 | `test_set_price_creates_new` | 新建价格记录 |
| 5 | `test_set_price_updates_existing` | 更新已有价格 |
| 6 | `test_retailer_price_isolation` | A≠B 价格隔离 |
| 7 | `test_retailer_b_has_no_sugar_price` | B 无糖价格 |
| 8 | `test_product_query_with_price_join` | SQL JOIN 正确性 |
| 9 | `test_product_query_price_isolation_between_retailers` | SQL 层零售商隔离 |
| 10 | `test_order_total_from_resolved_prices` | 订单总额计算正确 |
| 11 | `test_order_request_schema_has_no_price_field` | Schema 无价格字段 |
| 12 | `test_unpriced_product_has_can_order_false` | 无价格 can_order=false |
| 13 | `test_retailer_price_model_has_required_fields` | 模型字段完整 |
| 14 | `test_retailer_price_unique_constraint` | 唯一约束存在 |

---

## 7. 迁移说明

```bash
# 对每个租户 schema 运行
alembic -x tenant_schema=t_<tenant_code> upgrade head
```

迁移 `017_retailer_prices` 是纯加法操作：
- 新建表，不修改任何现有表
- 不影响现有订单数据
- 向后兼容：未配价格的产品显示 `price: null`

---

## 8. 修正补丁: price > 0 约束 (2026-03-31 09:57)

**问题**: `retailer_prices.price` 允许零和负值，可能导致无效订单。

**修复**:
- `backend/models/retailer_price.py` — 增加 `CheckConstraint("price > 0")`
- `backend/alembic/versions/017_retailer_prices.py` — 迁移增加 `CHECK(price > 0)`
- `backend/api/v1/client/orders.py` — 服务端下单时增加 `resolved_price <= 0` 拒绝逻辑 (纵深防御)
- `backend/tests/conftest.py` — 测试 bootstrap 表定义增加 `CHECK(price > 0)`
- `backend/tests/test_phase3_pricing.py` — 新增 2 个测试:
  - `test_zero_price_rejected_at_order_time` — 零价格被 DB CHECK 拒绝
  - `test_negative_price_rejected_at_db_level` — 负价格被 DB CHECK 拒绝

**防御层**:
| 层 | 保护 |
|---|---|
| DB CHECK 约束 | `price > 0` — 从根本上阻止非正价格入库 |
| 服务端校验 | `resolved_price <= 0` → 400 错误 (防止绕过场景) |
| Repository `set_price` | 调用方可自行校验 (未加强制，依赖 DB) |

---

## 9. 已知风险与开放问题

| 风险 | 说明 | 缓解 |
|---|---|---|
| 价格数据初始为空 | 新部署后所有产品 price=null, can_order=false | 需要批发商通过管理端或种子脚本设置价格 |
| 无管理端价格设置 UI | 当前只有 repository 层 set_price | Phase 3 后续或批发商端 API 补充 |
| 价格变更审计 | 当前仅靠 updated_at/updated_by | 可后续接入 audit_log |
| 跨 schema FK 不强制 | retailer_id 指向 public.retailers | 与现有订单表设计一致 |

---

## 9. 验收标准对照

| CTO 验收标准 | 状态 |
|---|---|
| 零售商浏览产品看到真实价格 | ✅ |
| 零售商下单存储非零 unit_price | ✅ |
| 订单总额基于服务端定价 | ✅ |
| 无租户隔离或定价权威回退 | ✅ |
