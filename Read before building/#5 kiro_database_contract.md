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

以下模型构成了我们基于角色的访问控制（RBAC）系统的基石。

### public.wholesalers (Tenant Registry)
Column Name  Type           Constraints                         Notes
----------  -------------  ----------------------------------  -----------------------------
id          uuid           PRIMARY KEY, default gen_random_uuid  tenant_id
code        varchar(32)    UNIQUE, NOT NULL                     tenant_code, regex ^[A-Z0-9]+$, immutable (app-level)
name        varchar(255)   NOT NULL
address     text           NULL
contact     text           NULL
plan_type   varchar(50)    NULL
createdat   timestamptz    NOT NULL, DEFAULT now
updatedat   timestamptz    NOT NULL, DEFAULT now
isdeleted   boolean        NOT NULL, DEFAULT false
deletedat   timestamptz    NULL

Indexes
- UNIQUE (code)
#### 添加审计字段
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




### `users`
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

### `roles`
| Column Name | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PRIMARY KEY | Default: `gen_random_uuid()` |
| `name` | `varchar(100)` | UNIQUE, NOT NULL | e.g., 'Admin', 'Manager' |
| `description` | `text` | | |
| `created_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `is_deleted` | `boolean` | NOT NULL, DEFAULT `false` | |
| `deleted_at` | `timestamptz` | nullable | |
| `created_by` | `uuid` | FOREIGN KEY -> `users.id` | |
| `updated_by` | `uuid` | FOREIGN KEY -> `users.id` | |

### `permissions`
| Column Name | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PRIMARY KEY | Default: `gen_random_uuid()` |
| `code` | `varchar(100)` | UNIQUE, NOT NULL | e.g., 'user:create', 'product:read' |
| `description` | `text` | | |
| `created_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `is_deleted` | `boolean` | NOT NULL, DEFAULT `false` | |
| `deleted_at` | `timestamptz` | nullable | |
| `created_by` | `uuid` | FOREIGN KEY -> `users.id` | |
| `updated_by` | `uuid` | FOREIGN KEY -> `users.id` | |

### `user_roles` (Join Table)
| Column Name | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PRIMARY KEY | Default: `gen_random_uuid()` |
| `user_id` | `uuid` | NOT NULL, FOREIGN KEY -> `users.id` ON DELETE CASCADE | |
| `role_id` | `uuid` | NOT NULL, FOREIGN KEY -> `roles.id` ON DELETE CASCADE | |
| `created_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `UNIQUE(user_id, role_id)` | | | |

### `role_permissions` (Join Table)
| Column Name | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PRIMARY KEY | Default: `gen_random_uuid()` |
| `role_id` | `uuid` | NOT NULL, FOREIGN KEY -> `roles.id` ON DELETE CASCADE | |
| `permission_id` | `uuid` | NOT NULL, FOREIGN KEY -> `permissions.id` ON DELETE CASCADE | |
| `created_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `UNIQUE(role_id, permission_id)` | | | |

#### 添加审计字段
| Column Name | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | PRIMARY KEY | Default: `gen_random_uuid()` |
| `name` | `varchar(100)` | UNIQUE, NOT NULL | e.g., 'Admin', 'Manager' |
| `description` | `text` | | |
| `created_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `updated_at` | `timestamptz` | NOT NULL, DEFAULT `now()` | |
| `is_deleted` | `boolean` | NOT NULL, DEFAULT `false` | |
| `deleted_at` | `timestamptz` | nullable | |
| `created_by` | `uuid` | FOREIGN KEY -> `users.id` | |
| `updated_by` | `uuid` | FOREIGN KEY -> `users.id` | |


---

## 4. 模块扩展规范

所有业务模块（库存、采购、销售等）的表设计**必须**遵循以下规范：

- **表命名**: `module_purpose` 格式，如 `inventory_products`, `sales_orders`。
- **事务表**（如库存流转、财务记录）**必须**包含：
    | Column Name | Type | Notes |
    |---|---|---|
    | `source_type` | `varchar(50)` | e.g., 'purchase', 'sale', 'adjust' |
    | `quantity` | `decimal(18, 4)` | Signed value for in/out |
    | `reference_id` | `uuid` | Links to source order/document |

---

## 5. 应用层规范

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

## 6. 运维与部署规范

### Alembic
- 项目必须包含 `alembic.ini`, `env.py`, `versions/`。
- `env.py` 必须正确配置 `target_metadata`。
- **流程**: `alembic revision --autogenerate -m "message"` -> Code Review -> `alembic upgrade head`。

### 测试
- **Framework**: `pytest` + `pytest-asyncio`.
- **Test Data**: Use `factory_boy` for fixtures.
- **Database Isolation**: Each test must run against a fresh, transactional database, rolled back after each test.

### 备份与恢复
- 生产库**必须**每日备份，并**必须**每季度测试恢复流程。
- 重大迁移前，**必须**在 staging 环境完成完整的 `downgrade` 测试。

### 验收检查清单
- [ ] 数据库容器成功启动 (`docker compose up postgres`)。
- [ ] `alembic upgrade head` 执行成功。
- [ ] 基础查询成功 (`SELECT count(*) FROM users;`)。
- [ ] `psql` 可连接并列出所有表 (`\dt`)。
- [ ] 应用服务可启动，并成功访问一个 API 端点。

---

## 7. 未来演进路径

- **当前阶段**: 使用自托管的 PostgreSQL 或 RDS for PostgreSQL。
- **成长阶段**: 迁移到 **Amazon Aurora Serverless v2**，以获得高可用性和自动扩缩容能力。
- **最终目标**: 利用 Aurora 的全球数据库能力，为帝国提供全球化的服务。

---

## 8. 附录

### 推荐的 PostgreSQL 扩展
```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
```
- **用途**: 提供 `gen_random_uuid()` 函数和加密支持。

## 9. Alembic 多 schema 迁移策略
1. Alembic 支持 -x tenant_schema=...，对每个 tenant schema 执行升级。

2. tenant provisioning：建 schema → alembic upgrade → seed roles/permissions。

3.
### Alembic multi-schema migrations (MVP)

- 所有 tenant schema 共享一套 Alembic 迁移脚本（单一 version history）。
- Alembic 通过 `-x tenant_schema=<schema_name>` 参数指定当前要升级的 schema。

#### env.py 约定（示意）

- 从 `config.get_main_option("tenant_schema")` 或 `config.cmd_opts.tenant_schema` 读取 tenant_schema。
- 在运行 migration 前设置：
  - `context.configure(..., version_table_schema="public", version_table="alembic_version", target_metadata=Base.metadata, include_schemas=True)`
  - 在 `run_migrations_online()` 中执行：
    - `connection.execute(sa.text(f'SET LOCAL search_path TO "{tenant_schema}", public'))`

#### 命令行使用

- 升级单个租户 schema：
  - `alembic upgrade head -x tenant_schema=t_1234`
- 新租户 provision 时：
  1. 创建 schema：`CREATE SCHEMA IF NOT EXISTS "t_1234";`
  2. 运行：`alembic upgrade head -x tenant_schema=t_1234`
  3. 插入该租户的种子数据（角色、权限、首个 admin 用户等）。

#### 运维脚本建议

- 提供一个管理脚本（Python 或 Makefile）循环所有 tenant：
  - 读取 `public.wholesalers` 表中的所有 `tenant_schema`。
  - 对每个 schema 执行一次 `alembic upgrade head -x tenant_schema=<schema>`。
- 确保 Alembic 的 version table 存在于 `public`，而不是每个 tenant schema，否则会导致版本状态无法集中管理。




---

## 10. Changelog

### v1.2 (2025-06-10)
- **重构**: 彻底重构文档结构，消除所有重复和冲突定义。
- **统一**: 全局规则中统一了主键、审计、软删除、外键策略。
- **明确**: 核心模型只保留唯一的 Markdown 表格定义，并增加了 `created_by`, `updated_by` 等审计字段。
- **规范**: 整合了应用层和运维规范，形成完整的开发到部署闭环。
- **更新**: UUID 生成函数统一为更现代的 `gen_random_uuid()`。

### v1.1 (2025-06-10)
- Initial draft with basic RBAC models and conventions.
