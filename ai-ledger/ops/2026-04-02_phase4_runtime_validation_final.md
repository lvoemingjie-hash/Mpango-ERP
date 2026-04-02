# Phase 4 运行时验证 — 最终证明

日期：2026-04-02
环境：本地开发（backend: http://localhost:8000，gateway/nginx 存在但本次直接命中 backend）
结论：Phase 4 已在真实运行环境上完全通过（ACCEPTED）

---

## 一、执行概要
- 目标：完成 Phase 4 在恢复后的 Docker/数据库环境上的全量运行时验证
- 覆盖范围：
  - 登录
  - 租户选择（返回新 token）
  - 列出已绑定零售商
  - 列出 SKU 列表
  - 设定/更新零售商价格
  - 验证价格列表出现相应价格
  - 使用“瘦”下单负载创建批发订单（不包含 unit_price / product_name）
  - 验证请求负载不含 unit_price
  - 验证订单列表显示服务器解析的价格
- 结果：全部步骤 2xx/201 成功，Phase 4 接受

---

## 二、环境与容器状态
- 确认容器：
  - mpango_postgres: Up (healthy)
  - mpango_redis: Up (healthy)
  - mpango_backend: Up (healthy) — 已重建镜像
  - mpango_gateway: Up
  - mpango_frontend: Up (healthy)

- 关键运维命令：
```
# 由于仅重启不会加载最新代码，需重建镜像
docker compose build --no-cache backend

docker compose up -d backend
```

---

## 三、操作步骤与证据

### 1) 登录
- 命令：
```
POST /api/v1/auth/login
Content-Type: application/json
{ "email": "admin@mpango.demo", "password": "DemoAdmin2026!" }
```
- 状态码：200 OK
- 结果：返回 access_token、roles、available_tenants（含 DEMO001）

### 2) 租户选择（返回新 token）
- 命令：
```
POST /api/v1/auth/select-tenant
Authorization: Bearer <login_token>
{ "tenant_id": "a0000000-0000-4000-8000-000000000001" }
```
- 状态码：200 OK
- 结果：返回新的 access_token；tenant_schema = t_a0000000000040008000000000000001

### 3) 列出零售商绑定
- 命令：
```
GET /api/v1/retailers/bindings
Authorization: Bearer <tenant_token>
```
- 状态码：200 OK
- 结果：1 个绑定（Nairobi Central Duka，retailer_id = b0000000-0000-4000-8000-000000000001）

### 4) 列出 SKUs
- 命令：
```
GET /api/v1/skus
Authorization: Bearer <tenant_token>
```
- 状态码：200 OK
- 结果：10 个 SKU；本次使用 SKU-FLOUR-001（id = c8b85bcb-2548-427e-bfe3-da2b9ba1acb4）

### 5) 查询价格（初始为空）
- 命令：
```
GET /api/v1/pricing/prices?retailer_id=b0000000-0000-4000-8000-000000000001
Authorization: Bearer <tenant_token>
```
- 状态码：200 OK
- 结果：items=[]，total=0

### 6) 设置/更新零售商价格
- 命令/负载：
```
PUT /api/v1/pricing/prices
Authorization: Bearer <tenant_token>
{
  "retailer_id": "b0000000-0000-4000-8000-000000000001",
  "sku_id": "c8b85bcb-2548-427e-bfe3-da2b9ba1acb4",
  "price": 185.50
}
```
- 状态码：200 OK
- 结果：{"action":"created"}，价格为 185.50 KES

### 7) 再次查询价格（确认存在）
- 命令：
```
GET /api/v1/pricing/prices?retailer_id=b0000000-0000-4000-8000-000000000001
```
- 状态码：200 OK
- 结果：出现 SKU-FLOUR-001 项，price="185.50"

### 8) 创建批发订单（瘦负载，无 unit_price/product_name）
- 命令/负载：
```
POST /api/v1/orders
Authorization: Bearer <tenant_token>
{
  "retailer_id": "b0000000-0000-4000-8000-000000000001",
  "items": [{ "sku_code": "SKU-FLOUR-001", "quantity": 2 }],
  "notes": "Phase 4 runtime validation order"
}
```
- 状态码：201 Created
- 结果要点：
  - 返回订单 id：6685d83e-70c1-4dc9-a5ce-b2a1677c85ea
  - items[0].unit_price = "185.50"（由服务器基于零售商价格表解析）
  - total_amount = "371.00"（185.50 × 2）
  - product_name = "Pembe Wheat Flour 2kg"（由服务器基于 SKU 解析）

### 9) 订单列表核验（含服务器解析价格）
- 命令：
```
GET /api/v1/orders
Authorization: Bearer <tenant_token>
```
- 状态码：200 OK
- 结果：最新一条为上一步创建的订单（id 匹配），unit_price=185.50、total_amount=371.00、status=draft

---

## 四、关键技术发现
- 仅使用 `docker restart` 不能加载最新代码；需要重建镜像：
```
docker compose build --no-cache backend
docker compose up -d backend
```
- 这一步是导致先前 `/api/v1/pricing/prices` 返回 404 的唯一原因；并非代码缺陷

---

## 五、结论
- Phase 4 运行时验证已全部通过，符合 `docs/ai/PHASE4_FRONTEND_CONTRACT.md` 的接口约定
- 服务器已按约定在下单时解析 `unit_price` 与 `product_name`，前端仅需提交 sku_code + quantity 的“瘦负载”
- 本报告对应日期：2026-04-02，标题：phase4_runtime_validation_final
