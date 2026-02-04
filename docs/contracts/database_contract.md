# Mpango ERP — Database Contract
**Version:** 1.2
**Scope:** Backend database schema, migrations, and ORM conventions.
**DB:** PostgreSQL 15+
**Last Updated:** 2025-06-10

## 1. 目标

为 Mpango ERP 提供稳定、可迁移、可扩展、高一致性的数据库基础。此文件为 Kiro 及所有开发者的强制规范：所有 DB 相关生成/修改必须严格符合此契约。

---

## 2. 全局规则（最高纲领）

1.  **命名约定**:
    *   **表名**: `snake_case` and **plural** (e.g., `users`, `products`, `purchase_orders`)。
    *   **列名**: `snake_case` and **singular** (e.g., `user_id`, `product_name`, `created_at`)。
2.  **主键**:
    *   **强制标准**: 所有表**必须**使用名为 `id` 的单列主键。
    *   **类型**: `id` 列**必须**为 `UUID` 类型。
    *   **默认值**: `id` 列**必须**使用 `gen_random_uuid()` 作为默认值。
    *   **复合主键**: **严格禁止**。
3.  **审计与软删除**:
    *   所有表**必须**包含 `created_at` 和 `updated_at` 列。
    *   所有表**必须**包含 `is_deleted` (boolean, default false) 和 `deleted_at` (timestamptz, nullable) 列。
    *   所有业务查询**必须**附带 `WHERE is_deleted = false` 条件。
4.  **用户追踪**:
    *   所有表**必须**包含 `created_by` 和 `updated_by` 列，类型为 `UUID`，外键引用 `users.id`，可为 NULL（系统创建时）。
5.  **外键**:
    *   **命名**: `{referenced_table_name}_id`。
    *   **约束**: 默认为 `NOT NULL`，除非业务明确允许为空。
    *   **级联**: M2M 中间表**必须**使用 `ON DELETE CASCADE`。核心业务表需根据业务逻辑决定，并在契约中明确说明。
6.  **索引**:
    *   所有外键列**必须**创建索引。
    *   所有高频查询字段（如 `email`, `code`）**必须**创建 `btree` 索引。
    *   唯一字段**必须**创建 `unique` 索引。
7.  **DDL 管理**:
    *   所有 DDL 操作**必须**通过 Alembic 迁移管理，**严禁**直接在生产数据库执行 `CREATE/ALTER` 语句。

---

## 3. 核心模型

### public.wholesalers (Tenant Registry)
| Column Name | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PRIMARY KEY, default gen_random_uuid() | tenant_id |
| `code` | `varchar(32)` | UNIQUE, NOT NULL | tenant_code, regex ^[A-Z0-9]+$, immutable |
| `name` | `varchar(255)` | NOT NULL | |
| `address` | `text` | NULL | |
| `contact` | `text` | NULL | |
| `plan_type` | `varchar(50)` | NULL | |
| `created_at` | `timestamptz` | NOT NULL, DEFAULT now() | |
| `updated_at` | `timestamptz` | NOT NULL, DEFAULT now() | |
| `is_deleted` | `boolean` | NOT NULL, DEFAULT false | |
| `deleted_at` | `timestamptz` | NULL | |

### users (在租户schema中)
| Column Name | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PRIMARY KEY | Default: `gen_random_uuid()` |
| `email` | `varchar(255)` | UNIQUE, NOT NULL | |
| `password_hash` | `varchar(255)` | NOT NULL | |
| `full_name` | `text` | | |
| `is_active` | `boolean` | NOT NULL, DEFAULT `true` | |
| `created_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `is_deleted` | `boolean` | NOT NULL, DEFAULT `false` | |
| `deleted_at` | `timestamptz` | nullable | |
| `created_by` | `uuid` | FOREIGN KEY -> `users.id` | |
| `updated_by` | `uuid` | FOREIGN KEY -> `users.id` | |

### roles (在租户schema中)
| Column Name | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PRIMARY KEY | Default: `gen_random_uuid()` |
| `name` | `varchar(100)` | UNIQUE, NOT NULL | e.g., 'admin', 'sales', 'warehouse', 'finance' |
| `description` | `text` | | |
| `created_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `is_deleted` | `boolean` | NOT NULL, DEFAULT `false` | |
| `deleted_at` | `timestamptz` | nullable | |
| `created_by` | `uuid` | FOREIGN KEY -> `users.id` | |
| `updated_by` | `uuid` | FOREIGN KEY -> `users.id` | |

### permissions (在租户schema中)
| Column Name | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PRIMARY KEY | Default: `gen_random_uuid()` |
| `code` | `varchar(100)` | UNIQUE, NOT NULL | e.g., 'users:read', 'orders:create' |
| `description` | `text` | | |
| `created_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `is_deleted` | `boolean` | NOT NULL, DEFAULT `false` | |
| `deleted_at` | `timestamptz` | nullable | |
| `created_by` | `uuid` | FOREIGN KEY -> `users.id` | |
| `updated_by` | `uuid` | FOREIGN KEY -> `users.id` | |

---

## 4. 应用层规范

### ORM & Migrations
- **ORM**: SQLAlchemy 2.0 (async mode required).
- **Migration Tool**: Alembic.
- **强制规范**:
    1.  **禁止**在业务代码中编写任何原生 SQL 查询。所有数据操作必须通过 SQLAlchemy ORM 进行。
    2.  所有 Alembic 迁移文件的 revision message 必须清晰描述变更内容。
    3.  ORM 模型类名用 `PascalCase`，必须显式声明 `__tablename__`，字段名与数据库列完全一致。
    4.  枚举类型必须使用 Python Enum class。

### Pydantic Schemas
- **必须**区分 `Create`, `Update`, `Read` (Response) Schema。
- **Read Schema** **禁止**返回 `password_hash`。
- `UUID` 字段在 Schema 中应自动序列化为 `str`。

---

## 5. Alembic 多 schema 迁移策略

- 所有 tenant schema 共享一套 Alembic 迁移脚本（单一 version history）。
- Alembic 通过 `-x tenant_schema=<schema_name>` 参数指定当前要升级的 schema。
- 升级单个租户 schema：`alembic upgrade head -x tenant_schema=t_1234`
- 新租户 provision 时：
  1. 创建 schema：`CREATE SCHEMA IF NOT EXISTS "t_1234";`
  2. 运行：`alembic upgrade head -x tenant_schema=t_1234`
  3. 插入该租户的种子数据（角色、权限、首个 admin 用户等）。
