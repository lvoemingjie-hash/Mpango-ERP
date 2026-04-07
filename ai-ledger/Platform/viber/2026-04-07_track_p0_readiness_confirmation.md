# Track P0 就绪确认报告

**日期：** 2026-04-07  
**Agent：** Vibecoder（Platform AI, Track B）  
**分支：** `platform-dev`  
**最新提交：** `04c266f1` (fix: finalize phase 3 backend pricing endpoints)  
**版本：** v0.2.0

---

## 一、代码现状认知

### 1.1 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn (async) |
| ORM | SQLAlchemy 2.0 (asyncpg) |
| 数据库 | PostgreSQL 15+ (pgvector 可选) |
| 缓存 | Redis 7 |
| 迁移管理 | Alembic (多 schema 支持) |
| 认证 | JWT + RBAC (22+ permissions) |
| 前端 | React + TypeScript |
| 任务队列 | LocalJobQueue (内置, 5 workers) |
| 监控 | Prometheus metrics + structured JSON logging |

### 1.2 项目结构

```
backend/
├── main.py              # FastAPI app 入口
├── api/
│   ├── app.py           # 中间件注册、路由配置
│   ├── dependencies.py  # JWT → tenant context 注入
│   ├── context.py       # 请求级上下文
│   └── v1/              # 17 个 API 模块, 63 个端点
├── models/              # 17 个模型文件
│   ├── base.py          # Base/AuditMixin/PublicBaseModel
│   ├── wholesaler.py    # 租户注册表 (public schema)
│   ├── user.py, order.py, inventory_stock.py, ...  # 业务模型 (tenant schema)
│   └── audit.py         # 审计日志
├── db/
│   ├── tenant_filter.py # 全局租户过滤器 (ContextVar + SQLAlchemy event)
│   └── session.py       # AsyncSession 工厂 + search_path 切换
├── alembic/             # 17 个迁移文件 (001→017)
└── core/                # config, security, jobs, governance
```

### 1.3 多租户架构（关键）

系统采用 **双层隔离** 策略（已确认为 DR-001）：

**第一层：Schema-per-Tenant（主隔离）**
- JWT 携带 `tenant_schema`（格式 `t_<uuid_no_dashes>`）
- 通过 PostgreSQL `search_path` 切换到对应 tenant schema
- 所有业务数据（orders, inventory, payments 等）存储在各自 schema 下
- 租户创建时动态创建 schema

**第二层：tenant_id Guardrail（辅助过滤）**
- `db/tenant_filter.py` 使用 Python `ContextVar` 存储当前租户上下文
- SQLAlchemy event 自动注入 `WHERE tenant_id = ?` 条件
- `run_as_system(reason="...")` 可显式绕过（需提供理由）

**租户注册表：**
- `public.wholesalers` 是租户注册表
- 包含字段：code, name, address, contact, plan_type
- `Wholesaler.get_tenant_schema()` 从 UUID 派生 schema 名

**Auth 流程：**
- JWT payload 包含 `tenant_schema` 和 `user_id`
- `dependencies.py` 从 request state 解析 tenant context
- `session.py` 中 `get_tenant_db_session()` 返回已绑定 schema 的 session

### 1.4 模块完成状态

| 模块 | API 文件 | 模型文件 | 状态 |
|------|----------|----------|------|
| 认证 (Auth) | auth.py | user.py | ✅ 完成 |
| 用户/角色管理 | users.py, roles.py | user.py | ✅ 完成 |
| 订单管理 | orders.py | order.py | ✅ 完成 |
| 库存管理 | inventory.py | inventory_stock.py, inventory_movement.py | ✅ 完成 |
| 支付管理 | payments.py | ledger.py | ✅ 完成 |
| 财务报表 | finance.py | reporting.py, report.py | ✅ 完成 |
| 仪表板/BI | dashboards.py, metrics.py | report.py, reporting.py | ✅ 完成 |
| 零售商管理 | retailers.py | retailer.py | ✅ 完成 |
| SKU 管理 | skus.py | sku.py | ✅ 完成 |
| 邀请管理 | invitations.py | invitation.py | ✅ 完成 |
| 审计日志 | data_export.py | audit.py | ✅ 完成 (public schema) |
| 系统作业 | jobs_test.py | job.py | ✅ 完成 |
| 数据导出 | exports.py | — | ✅ 完成 |
| 健康检查 | health.py | — | ✅ 完成 |
| 通知 | — | — | ⚡ Stub |
| **平台管理** | — | — | ❌ **尚未开始** |
| **计费系统** | — | — | ❌ **尚未开始** |
| **订阅管理** | — | — | ❌ **尚未开始** |

---

## 二、平台轨道边界确认

### 2.1 允许操作 ✅

| 操作 | 说明 |
|------|------|
| 创建平台表 | `tenants`, `subscriptions`, `billing_invoices`, `usage_metrics` 等（仅 public schema） |
| 创建平台 API | 在 `backend/api/v1/platform/` 下新增端点 |
| 创建平台管理前端 | 平台管理后台、仪表板 |
| 添加 Alembic 迁移 | 仅限平台表的新迁移 |
| 读取业务表 | 只读访问 orders/inventory/payments 等（用于集成和监控） |
| 使用 `run_as_system()` | 跨租户平台操作（需提供理由） |
| 扩展 `public.wholesalers` | 添加平台相关字段（plan, status, created_at 等） |

### 2.2 禁止操作 ❌

| 禁止项 | 原因 |
|--------|------|
| 修改业务表结构 | orders, inventory_stocks, payments, retailers |
| 修改产品 API 端点 | `backend/api/v1/` 下已有的端点 |
| 修改业务逻辑 | 任何 product services 中的逻辑 |
| 删除或重命名列 | 破坏 API 向后兼容性 |
| 修改租户隔离架构 | schema-per-tenant 已锁定为 DR-001 |
| 修改认证模型 | JWT + RBAC 模型不可变 |

### 2.3 合并规则

- 平台功能不得破坏产品 API
- 产品功能必须尊重租户隔离
- 每个 Sprint 前冻结 API Schema
- 合并前检查 `alembic heads`（如有 2 heads 必须 merge）

---

## 三、关键约束确认

### 3.1 多租户约束
- ✅ 确认：架构为 Schema-per-Tenant (DR-001)
- ✅ 确认：JWT 携带 `tenant_schema` 用于 search_path 路由
- ✅ 确认：`tenant_id` 为辅助过滤层
- ✅ 确认：`run_as_system()` 是唯一的跨租户操作方式

### 3.2 数据库约束
- ✅ 确认：所有数据库变更必须通过 Alembic 迁移
- ✅ 确认：业务表在 tenant schema 下，平台表在 public schema 下
- ✅ 确认：Alembic 支持 `alembic upgrade head -x tenant_schema=t_xxx` 按租户迁移
- ✅ 确认：17 个迁移文件链完整（001→017），无 head 分叉

### 3.3 API Contract 约束
- ✅ 确认：遵循 Progressive Contract（向后兼容）
- ✅ 确认：禁止删除字段、禁止修改字段类型
- ✅ 确认：OpenAPI spec 在 `docs/contracts/openapi.yaml`

### 3.4 文档治理约束
- ✅ 确认：`docs/ai/` 为共享记忆系统
- ✅ 确认：重大决策必须记录到 `decision-register/`
- ✅ 确认：每次有意义的开发会话需在 `ai-ledger/` 留记录
- ✅ 确认：决策层级：Contracts > decision-register > CTO_CONTEXT > PROJECT_MEMORY > 代码

---

## 四、Track P0 就绪状态

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 分支正确 | ✅ | `platform-dev`，tracking `origin/platform-dev` |
| 仓库可访问 | ✅ | GitHub remote fetch/push 正常 |
| Git 环境 | ✅ | git 2.43.0 |
| Python 环境 | ✅ | Python 3.12.3 + venv + 全部依赖已安装 |
| 数据库 | ✅ | PostgreSQL 15 运行中（port 5433） |
| Redis | ✅ | Redis 7 运行中（port 6379） |
| Backend 启动 | ✅ | `GET /health → 200 OK`，v0.2.0 |
| Alembic 迁移 | ✅ | `017_retailer_prices (head)`，无分叉 |
| OpenCode CLI | ✅ | v1.3.3（通过 npx 缓存） |
| gh CLI | ✅ | v2.45.0，PR/Issue 操作可用 |
| 必读文档已读 | ✅ | README, CTO_COCKPIT, DUAL_MACHINE_PROTOCOL, STARTUP_CHECKLIST, CTO_CONTEXT |
| 多租户架构理解 | ✅ | Schema-per-Tenant + tenant_id 双层隔离 |
| 平台边界理解 | ✅ | 清晰区分允许/禁止操作 |
| 平台 API 目录 | ⏳ | `backend/api/v1/platform/` 尚未创建（Track P0 首个任务） |
| Docker Compose | ⚠️ | 无 compose 插件，使用 docker run 手动管理（不影响开发） |

---

## 五、风险与注意事项

### 5.1 已识别风险

| 风险 | 级别 | 缓解措施 |
|------|------|----------|
| 端口冲突（5432 被 memorizer-pg 占用） | 低 | backend 使用 5433，已在 .env 中配置 |
| 无 Docker Compose | 低 | 使用 docker run 手动管理，功能等效 |
| `reporting_session.py` 模块级 import 竞态 | 低 | 需要 export REPORTING_USER_PASSWORD 环境变量 |
| .env 文件 Windows 换行符 | 低 | 已修复（sed -i 's/\r$//'） |
| 缺少 t_dev tenant schema 的业务表 | 中 | 当前 DB 只有 public schema 的 9 张表，tenant schema 内的表需通过 Alembic + tenant 参数创建 |

### 5.2 开发注意事项

1. **平台表必须放在 public schema**：平台表（tenants, subscriptions 等）使用 `PublicBaseModel` 而非 `BaseModel`
2. **新增迁移文件编号从 018 开始**：遵循现有命名规范
3. **使用 `run_as_system()` 访问业务数据**：平台监控/统计需要跨租户查询时必须使用此机制
4. **不要修改 `public.wholesalers` 的核心字段**：如需扩展，添加新列而非修改现有列
5. **双机协调**：Track A (Windows/Machine A) 产品线在 `product-dev` 分支，Track B (Lubuntu/Machine B) 平台线在 `platform-dev` 分支，通过 GitHub 同步

---

## 六、Go / No-Go 结论

### ✅ **GO — 准备开始 Track P0**

所有关键检查项已通过。代码库理解充分，开发环境就绪，平台边界清晰，约束条件已确认。

**建议首个任务**（按 `PLATFORM_TRACK_STARTUP_CHECKLIST.md` Phase 4 选择一项开始）：

1. **租户注册文档与脚手架** — 创建 `backend/api/v1/platform/` 目录结构，定义 platform API 路由
2. **平台管理信息模型** — 设计平台层的数据模型（扩展 wholesalers 或新建 tenants 表）
3. **审计日志边界与生命周期设计** — 审查现有 `sys_audit_logs` 表，规划平台级审计需求

**不推荐的起点：**
- ❌ 认证重写
- ❌ 租户架构重写
- ❌ 跨切面迁移变更

---

*本报告由 Vibecoder（Platform AI）基于实际代码和文档生成，不依赖外部记忆。*
