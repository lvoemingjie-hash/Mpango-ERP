# Multi-Tenancy Spec (MVP)

## 1. Decision

- **Strategy**: Schema-per-tenant (one tenant == one wholesaler schema).
- **Tenant entity**: Wholesaler.
- **Tenant identifier**:
  - `tenant_code`: `Wholesaler.code` (长期租户标识符，用于登录和租户定位)
  - `tenant_id`: `Wholesaler.id` (UUID)
  - `tenant_schema`: 从 `tenant_id` 派生，命名规则 `t_<uuid_without_dashes>`
- **Invite code**: `Retailer.invite_code` (一次性邀请凭证，与 tenant_code 分离)

## 2. Identifiers & Format Rules

### 2.1 tenant_code (Wholesaler.code)

- **Format**: 仅允许大写字母 A-Z 和数字 0-9（正则：`^[A-Z0-9]+$`）
  - 示例：`ABC`, `ABC123`, `XYZ01`
- **Length**: 2-32 字符
- **Uniqueness**: 全局唯一（`public.wholesalers` 表中）
- **Mutability**: 不可变（immutable），一旦创建不允许修改（MVP 阶段通过应用层强制执行）
- **Usage**: 登录时必须提供，用于解析租户

### 2.2 tenant_schema

- **Derivation**: 从 `tenant_id` (Wholesaler.id UUID) 派生
- **Naming rule**: `t_<uuid_without_dashes>`
  - 示例：UUID `1f2e3d4c-5b6a-7c8d-9e0f-1a2b3c4d5e6f` → schema `t_1f2e3d4c5b6a7c8d9e0f1a2b3c4d5e6f`
- **Storage**: 每个租户一个独立的 PostgreSQL schema

### 2.3 invite_code (Retailer.invite_code)

- **Purpose**: 一次性零售商注册邀请码（由批发商发出）
- **Format**: 灵活（字母数字，可包含短横线）
- **Lifecycle**: Valid → Used → Invalid（一次性使用后失效）
- **Implementation (MVP)**:
  - 在 `Retailer` 或独立的 `retailer_invites` 表中添加 `used_at` (timestamp) 或 `is_used` (boolean) 字段
  - 注册时验证：未使用 + 属于正确的 tenant
  - 使用后立即标记为已用，拒绝后续使用
#### Retailer invite_code

- **字段**：Retailer.invite_code + Retailer.invite_used_at (datetime).
- **规则**：invite_used_at 为 NULL 时可用；第一次成功注册时写入当前时间，之后任何使用该 invite_code 的请求都返回 4xx。


## 3. Schema Layout

### 3.1 public schema

- **Tables**:
  - `wholesalers` (租户注册表：id, code, name, plan_type, etc.)
  - 可选：任何跨租户操作表（MVP 中无）

### 3.2 tenant schema (t_xxx)

所有租户作用域的表都存储在租户 schema 中，包括：

- **Auth/RBAC**: `users`, `roles`, `permissions`, `user_roles`, `role_permissions`
- **CRM/Sales**: `retailers`, `customer_profiles`, `orders`, `order_items`
- **Product/Inventory**: `products`, `product_attributes`, `inventory`, `inventory_logs`
- **Procurement**: `suppliers`, `purchase_orders`, `purchase_order_items`, `inbound_logs`
- **Finance**: `payments` (or `payment_records`)

## 4. Request → Tenant Resolution

### 4.1 Login Flow

1. **Client 提交**:
   - `tenant_code` (Wholesaler.code)
   - `username`
   - `password`

2. **Backend 处理**:
   ```sql
   SELECT id, code, name FROM public.wholesalers WHERE code = :tenant_code;
解析 tenant_code → tenant_id → 计算 tenant_schema

JWT 签发:

JWT claims 必须包含：

tenant_id (UUID)

tenant_schema (string)

user_id (UUID)

示例 payload:

json
{
  "tenant_id": "1f2e3d4c-5b6a-7c8d-9e0f-1a2b3c4d5e6f",
  "tenant_schema": "t_1f2e3d4c5b6a7c8d9e0f1a2b3c4d5e6f",
  "user_id": "a1b2c3d4-...",
  "exp": 1234567890
}
安全要求:

登录后，后端不得接受来自 client 的 X-Tenant-* header 或 query param 中的 tenant 信息（防止伪造）

### 4.2 Authenticated Requests
Tenant 来源: 仅从 JWT claims 中获取（tenant_schema）

DB Session 设置:

每个请求/事务开始时，middleware/dependency 必须执行：

sql
SET LOCAL search_path TO "<tenant_schema>", public;
这样 ORM 模型会自动解析到正确的租户 schema

## 5. Data Access Rules
Tenant-scoped tables: 所有业务表（users, orders, products 等）使用 search_path 自动路由到租户 schema

Cross-tenant queries: MVP 中不允许跨租户查询

Admin/Super-admin: MVP 中不支持跨租户管理功能（out of scope）

## 6. Tenant Provisioning
当创建新批发商（新租户）时，按以下步骤执行：

插入租户注册表:

sql
INSERT INTO public.wholesalers (id, code, name, plan_type, created_at)
VALUES (gen_random_uuid(), :code, :name, :plan, now());
创建租户 schema:

sql
CREATE SCHEMA IF NOT EXISTS "<tenant_schema>";
运行 Alembic migrations:

bash
alembic upgrade head -x tenant_schema=<tenant_schema>

- Run Alembic migrations for this tenant schema using
  `alembic upgrade head -x tenant_schema=<schema_name>` (see "Alembic multi-schema migrations (MVP)" section for details).
  
  种子数据 (Seed RBAC):

插入默认角色：admin, sales, warehouse, finance

插入默认权限：users:read, orders:create, 等

创建角色-权限映射（role_permissions）

创建首个管理员用户:

在租户 schema 的 users 表中插入第一个 admin 用户

关联到 admin 角色




## 7. Migrations Strategy (Alembic)
Migration history: 每个租户 schema 维护一套独立的 migration history

Alembic env.py 配置:

支持 -x tenant_schema=<schema> 参数

设置 search_path 或 version_table_schema=<tenant_schema>

Local dev: 默认使用单一租户 schema（如 t_dev）进行开发

## 8. Testing
Test tenant schema:

每个测试会话创建独立的租户 schema（如 t_test_xxx）

或复用 t_test 但每次测试后清空所有表

Test JWT:

测试请求必须包含有效的 JWT，包含 tenant_id, tenant_schema, user_id

## 9. Registration URL Format (from PRD)
URL 示例: /mpango_register?invite=8452&tenant=ABC

参数说明:

tenant=ABC: 对应 Wholesaler.code (tenant_code)

invite=8452: 对应 Retailer.invite_code (一次性邀请码)

处理规则:

先验证 tenant 参数，确认批发商存在

再验证 invite 参数，确认邀请码有效且未使用

防止跨租户滥用（invite 必须属于指定的 tenant）

## 10. Out of Scope (MVP)
以下功能在 MVP 阶段不实现：

跨租户查询（Cross-tenant queries）

数据库级行级安全（DB-level RLS）

Super-admin 跨租户管理功能

Tenant schema 的动态迁移或合并

text

***

