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

## 3. Schema Layout

### 3.1 public schema

- **Tables**:
  - `wholesalers` (租户注册表：id, code, name, plan_type, etc.)

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
   ```
   - 解析 tenant_code → tenant_id → 计算 tenant_schema

3. **JWT 签发**:
   JWT claims 必须包含：
   - tenant_id (UUID)
   - tenant_schema (string)
   - user_id (UUID)

### 4.2 Authenticated Requests
- **Tenant 来源**: 仅从 JWT claims 中获取（tenant_schema）
- **DB Session 设置**: 每个请求/事务开始时，middleware/dependency 必须执行：
  ```sql
  SET LOCAL search_path TO "<tenant_schema>", public;
  ```
  这样 ORM 模型会自动解析到正确的租户 schema

## 5. Tenant Provisioning
当创建新批发商（新租户）时，按以下步骤执行：

1. **插入租户注册表**:
   ```sql
   INSERT INTO public.wholesalers (id, code, name, plan_type, created_at)
   VALUES (gen_random_uuid(), :code, :name, :plan, now());
   ```

2. **创建租户 schema**:
   ```sql
   CREATE SCHEMA IF NOT EXISTS "<tenant_schema>";
   ```

3. **运行 Alembic migrations**:
   ```bash
   alembic upgrade head -x tenant_schema=<tenant_schema>
   ```

4. **种子数据 (Seed RBAC)**:
   - 插入默认角色：admin, sales, warehouse, finance
   - 插入默认权限：users:read, orders:create, 等
   - 创建角色-权限映射（role_permissions）
   - 创建首个管理员用户