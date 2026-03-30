# Mpango SaaS 平台层实施提案

**日期：** 2026-03-13
**版本：** v3.2（CTO 修正版 - MVP 聚焦）
**基于：** v3.1 + CTO 技术决策
**目标阶段：** v0.3（MVP → SaaS Foundation）

---

## 📋 版本变更说明（v3.1 → v3.2）

### 🔴 CTO 关键决策

| 技术建议 | v3.1 | v3.2 | CTO 原因 |
|---------|------|------|---------|
| **Schema-per-tenant** | 混合模式 | ❌ 不采用 | 与现有架构冲突过大，架构级重构 |
| **Istio Ambient Mesh** | 渐进式迁移 | ❌ 过早 | 当前规模（2-4 services）不需要 |
| **WORM 审计日志** | 分层存储（S3 + Glacier） | ✅ 简化实现 | MVP 阶段不需要完整 CloudTrail |

### 🎯 架构决策（CTO 最终决定）

| 决策 | 说明 |
|------|------|
| **数据隔离** | 继续使用 `tenant_id` 模型（Row-Level Multi Tenancy） |
| **Service Mesh** | ❌ 不上 Istio，Kubernetes + Ingress 足够 |
| **审计日志** | ✅ 简化版本，只需要 `audit_logs` 表 |

---

## 🎯 核心决策总结

### 一、Schema-per-tenant 不采用

**AI 建议：** 每个 tenant 一个 schema

**CTO 决策：** ❌ v0.3 不采用

**原因：**
1. 与现有架构冲突过大，需要架构级重构
2. 现有代码都是 `SELECT * FROM orders WHERE tenant_id = ?`
3. 如果换 schema，需要重写 100+ 查询、所有 repository、所有 API
4. 当前阶段（MVP → v0.3，1-50 tenants）不需要
5. Schema-per-tenant 适合 > 1000 tenants

**CTO 建议：**
- 继续使用 `tenant_id` 模型
- 所有表必须包含 `tenant_id`
- 预留升级路径：未来可以 `tenant_id → schema mapping`

---

### 二、Istio Ambient Mesh 不采用

**AI 建议：** Istio Ambient Mesh 渐进式迁移

**CTO 决策：** ❌ 过早

**原因：**
1. 当前系统可能只有 2-4 services（backend, frontend, db）
2. Service Mesh 通常适合 > 20 services
3. 否则运维复杂度 > 收益
4. 当前 Kubernetes + Ingress 足够

**CTO 建议：**
- 现在不要上 Istio
- 未来阶段（v0.6）微服务拆分后再考虑
- 可以考虑 Istio 或 Linkerd

---

### 三、WORM 审计日志 - 简化实现

**AI 建议：** WORM + CloudTrail + S3 分层存储

**CTO 决策：** ✅ 但简化实现

**原因：**
1. 现在是 MVP SaaS，不是上市公司
2. 不需要完整 CloudTrail

**CTO 建议实现方式：**

新增表：`audit_logs`

字段：
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID,
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

示例：
```text
user_id=23
action=CREATE_ORDER
resource=orders/9812
metadata={"order_id": "9812", "amount": 100}
```

并且：
- 禁止 UPDATE
- 禁止 DELETE
- 只允许 INSERT
- 只允许 SELECT

这已经是 WORM 模型。

---

## 📚 CTO 新增 4 条开发规范

### 1. Migration Governance（数据库迁移治理）

**规则 1：** Track B 禁止修改业务表

**禁止修改的表：**
- `orders`
- `inventory_stocks`
- `payments`
- `retailers`

**只允许修改：**
- `tenants`
- `subscriptions`
- `audit_logs`

**规则 2：** 合并前检查

```bash
# 合并前必须检查
alembic heads

# 如果出现 2 heads，必须执行
alembic merge -m "merge migrations"
```

**规则 3：** 部署流程

CI 必须执行：
```bash
alembic upgrade head
```

确保迁移链完整。

---

### 2. Global Tenant Filter（全局租户过滤器）

**CTO 决策：** ✅ 采纳

**不要依赖：**
```sql
WHERE tenant_id = ?
```
人工写。

**应该在：** SQLAlchemy 实现 `Tenant Query Filter`

**示例：**
```python
Session.query(Order)
# 自动附带 tenant_id = current_tenant
```

**效果：**
- 开发者不可能忘记 `tenant_id`
- 防御性深度防御（Defense-in-Depth）

---

### 3. Progressive API Contract（渐进式 API 契约）

**CTO 决策：** 修改规则

**原规则：** API Contract Lock（完全锁定）
**新规则：** Progressive Contract（渐进式契约）

**原则：** Backward Compatible Only

**允许：**
- 新增字段（optional）
- 新增 endpoint
- 新增 query parameter

**禁止：**
- 删除字段
- 修改字段类型
- 删除 endpoint

**MVP 阶段特点：**
- 字段不断变化
- 如果强制锁定，前端开发效率大幅下降

---

### 4. Platform Billing Module（平台计费模块）

**CTO 决策：** ✅ 必须补

**新增平台表：**

#### subscriptions
```sql
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    plan VARCHAR(50) NOT NULL,  -- standard, premium, enterprise
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, suspended, cancelled
    current_period_start TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### invoices
```sql
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, paid, overdue
    issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    due_at TIMESTAMP NOT NULL,
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### payments_platform（可选）
```sql
CREATE TABLE payments_platform (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    invoice_id UUID REFERENCES invoices(id),
    amount NUMERIC(10, 2) NOT NULL,
    payment_method VARCHAR(50),  -- M-Pesa, Stripe, Bank Transfer
    status VARCHAR(20) NOT NULL,  -- pending, completed, failed
    transaction_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);
```

**最简计费流程：**
1. tenant 注册
2. 创建 subscription
3. 生成 invoice
4. 管理员标记 paid（手动）

**未来可以接：**
- Stripe
- Paddle

---

## 📊 CTO 优先级排序

### 重新排序的优先级

| 优先级 | 功能 | 说明 |
|-------|------|------|
| **P0** | Tenant Registry | 最高优先级 |
| **P0** | Platform Admin Console | 查看租户数量、订单量、错误率 |
| **P1** | Audit Logs | 简化实现（audit_logs 表） |
| **P1** | Billing Module | 订阅、发票 |
| **P2** | Assume Role | 模拟登录租户（debug、support） |

### CTO 对原优先级的调整

**原计划（AI 建议）：**
1. Schema-per-tenant
2. Ambient Mesh
3. WORM 审计日志

**CTO 调整后：**
1. Tenant Registry（最高优先级）
2. Platform Admin Console
3. Audit Logs（简化实现）
4. Billing Module
5. Assume Role

---

## 📁 文档架构（来自 mpango_full_engineering_documentation_system.md）

### 1. Architecture Documents（架构文档）

**定义长期技术架构**

**必需文档：**
- `SaaS Architecture Evolution Plan` ✅ 已存在
- `System Modules Map`
- `Platform Architecture Specification`

**目的：**
- 定义 Mpango 如何从 ERP 演进到 SaaS
- 关键主题：
  - multi-tenant model
  - service architecture
  - data model strategy
  - infrastructure evolution

---

### 2. Engineering Governance Documents（工程治理文档）

**定义工程团队如何工作**

**核心文件：**
- `Engineering Handbook` ✅ 已存在
- `Branch Strategy`
- `Migration Governance`
- `API Contract Rules`

**关键规则：**
- no direct commit to main
- 所有数据库变更通过 Alembic
- 强制 code review
- 向后兼容的 APIs

---

### 3. Platform Layer Documents（平台层文档）

**平台层支持 SaaS 操作**

**核心组件：**
- Tenant Registry
- Subscription Management
- Billing Engine
- Admin Console
- Audit Logging

**关键数据库表：**
- tenants
- subscriptions
- invoices
- audit_logs

---

### 4. Backend Governance Rules（来自 backend_governance.md）

**Rule 1: The "Manageable Entity" Standard**

任何在 Frontend Sidebar/Menu、Dropdown（>1 items）出现，或者是核心配置的实体，必须在 "Phase Freeze" 前有完整的 CRUD endpoints（List, Create, Update, Delete）。

**Rule 2: The "API Completeness Review" Protocol**

在 Track C（Frontend）开始任何模块之前，必须进行 "Frontend-First" review：
- 映射每个 UI 页面/modal 到具体的 API endpoints（List/Create/Update/Delete）
- 验证 Permissions、Uniqueness Checks 和 Error Codes。

---

## 🎯 SaaS 架构演进阶段（来自 mpango_saas_architecture_evolution_plan.md）

### Stage 1 — MVP ERP (v0.2–v0.3)

**规模：** 1–10 tenants

**架构：**
- Monolithic backend API
- Single PostgreSQL database
- Multi-tenant using `tenant_id` column

**核心组件：**
- Backend API
- React frontend
- Retailer ordering portal
- PostgreSQL

**基础设施：**
- Docker
- Basic CI/CD

**重点：**
- 运行稳定和可用的 ERP 功能。

---

### Stage 2 — SaaS Foundation (v0.3–v0.5)

**规模：** 10–100 tenants

**新增平台组件：**
- Tenant Registry
- Platform Admin Console
- Audit logging
- Lightweight billing

**数据库新增：**
- tenants
- subscriptions
- invoices
- audit_logs

**Audit logs 遵循 WORM 模型：**
- Write once
- Read many
- No update or delete

**目标：**
- 将 Mpango 运营为托管的 SaaS 平台。

---

### Stage 3 — Scalable SaaS (v0.6–v0.8)

**规模：** 100–1000 tenants

**新增组件：**
- Horizontal scaling
- Advanced monitoring
- Automated deployment

**数据库优化：**
- Read replicas
- Connection pooling
- Index optimization

---

### Stage 4 — Enterprise SaaS (v1.0+)

**规模：** 1000+ tenants

**新增组件：**
- Multi-region deployment
- Advanced security (SOC 2)
- Enterprise support

**数据库：**
- Sharding（如果需要）
- Separate databases per tier

---

## 🚀 实施计划（v0.3 阶段）

### Phase 1：基础设施准备（Week 1）

**任务 1.1：数据库结构设计**

**目标：** 创建 SaaS Foundation 阶段所需的核心表

**交付物：**
- Alembic migrations
- 数据库 schema
- ORM models

**核心表：**

#### tenants
```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, suspended, deleted
    plan VARCHAR(50) NOT NULL DEFAULT 'standard',  -- standard, premium, enterprise
    tenant_code VARCHAR(50) UNIQUE NOT NULL,
    domain VARCHAR(255),  -- 自定义域名（未来）
    settings JSONB,  -- 租户特定配置
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_tenants_status ON tenants(status);
CREATE INDEX idx_tenants_plan ON tenants(plan);
CREATE UNIQUE INDEX idx_tenants_code ON tenants(tenant_code);
```

#### audit_logs
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID,
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(255),
    metadata JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_audit_logs_tenant_id ON audit_logs(tenant_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);
```

#### subscriptions
```sql
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    plan VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    current_period_start TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    auto_renew BOOLEAN DEFAULT TRUE,
    billing_cycle VARCHAR(20) DEFAULT 'monthly',  -- monthly, yearly
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (tenant_id, status) WHERE status = 'active'
);
```

#### invoices
```sql
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    subscription_id UUID REFERENCES subscriptions(id),
    amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'KES',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    due_at TIMESTAMP NOT NULL,
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_invoices_tenant_id ON invoices(tenant_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_due_at ON invoices(due_at);
```

---

**任务 1.2：Global Tenant Filter 实现**

**目标：** ORM 自动添加 `tenant_id = current_tenant`

**实现方式：**

```python
# database/base.py
from sqlalchemy import event
from sqlalchemy.orm import Query

class BaseQuery(Query):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 自动添加 tenant_id 过滤
        if hasattr(self, '_session') and self._session.info.get('tenant_id'):
            self = self.filter(self._entity.tenant_id == self._session.info['tenant_id'])

# 在 model 中使用
class BaseModel(Base):
    query_class = BaseQuery
    # ...
```

**效果：**
```python
# 查询时自动附加 tenant_id
orders = Order.query.all()
# 自动变成：
# SELECT * FROM orders WHERE tenant_id = current_tenant_id
```

---

**任务 1.3：Migration Governance 配置**

**目标：** 设置 Alembic 双轨迁移规则

**配置文件：** `alembic/env.py`

```python
# Alembic environment configuration
# ...

def run_migrations_online():
    # 获取当前 heads
    heads = command.heads.get_current_heads()

    # 如果有多个 heads，提示合并
    if len(heads) > 1:
        raise Exception(
            f"Multiple migration heads detected: {heads}. "
            "Please run: alembic merge -m 'merge migrations'"
        )

    # ...
```

---

### Phase 2：核心功能开发（Week 2-4）

#### 里程碑 2.1：Tenant Registry（P0）

**任务列表：**

**Week 2:**
1. 实现 Tenant CRUD API
   - `POST /api/v1/platform/tenants` - 创建租户
   - `GET /api/v1/platform/tenants` - 列出租户
   - `GET /api/v1/platform/tenants/{id}` - 获取租户详情
   - `PUT /api/v1/platform/tenants/{id}` - 更新租户
   - `DELETE /api/v1/platform/tenants/{id}` - 删除租户（软删除）

2. 实现 Tenant Code 生成
   - 自动生成唯一的 `tenant_code`
   - 格式：`{prefix}-{random}`，如 `TENANT-ABC123`

3. 实现 Tenant 状态管理
   - active → suspended
   - suspended → active

**Week 3:**
4. 实现 Tenant Settings
   - 租户特定配置（JSONB）
   - 示例：`{"max_users": 10, "max_orders": 1000}`

5. 实现 Audit Logging（Tenant Registry）
   - 记录所有 Tenant 操作
   - 示例：`CREATE_TENANT`, `UPDATE_TENANT`, `DELETE_TENANT`

**验收标准：**
- ✅ 所有 CRUD API 已实现
- ✅ Tenant Code 自动生成且唯一
- ✅ 所有操作记录到 audit_logs
- ✅ API 符合 Progressive Contract 规则

---

#### 里程碑 2.2：Platform Admin Console（P0）

**任务列表：**

**Week 3:**
1. 实现 Dashboard 概览
   - 租户总数
   - 活跃租户数
   - 订单总数（24h）
   - 错误率（24h）

2. 实现 Tenant 列表页
   - 搜索、筛选、分页
   - 状态标签（active, suspended, deleted）
   - 操作按钮（编辑、删除）

3. 实现 Tenant 详情页
   - 基本信息
   - 订阅信息
   - 最近审计日志

**Week 4:**
4. 实现 Audit Logs 查询页
   - 搜索、筛选（按 tenant、action、user、时间）
   - 导出功能（CSV）

5. 实现 Global Tenant Filter 集成
   - Platform Admin 可以查看所有 tenant 的数据
   - 普通 User 只能查看自己 tenant 的数据

**验收标准：**
- ✅ Dashboard 显示实时数据
- ✅ Tenant 列表支持搜索、筛选、分页
- ✅ Audit Logs 可以查询和导出
- ✅ Global Tenant Filter 正确应用

---

#### 里程碑 2.3：Audit Logging（P1）

**任务列表：**

**Week 4:**
1. 实现 Audit Logger 服务
   ```python
   class AuditLogger:
       def log(self, tenant_id, user_id, action, resource, metadata=None):
           audit_log = AuditLog(
               tenant_id=tenant_id,
               user_id=user_id,
               action=action,
               resource=resource,
               metadata=metadata,
               ip_address=self._get_client_ip(),
               user_agent=self._get_user_agent()
           )
           db.session.add(audit_log)
           db.session.commit()
   ```

2. 在关键操作中集成 Audit Logging
   - Tenant CRUD 操作
   - User CRUD 操作
   - Order 创建/更新/删除
   - 其他敏感操作

3. 实现 Audit Logs API
   - `GET /api/v1/platform/audit-logs` - 查询审计日志
   - `GET /api/v1/platform/audit-logs/{id}` - 获取详情
   - `GET /api/v1/platform/audit-logs/export` - 导出 CSV

4. 实现 WORM 约束
   - 在数据库层面禁用 UPDATE 和 DELETE
   ```sql
   CREATE RULE no_update_audit_logs AS ON UPDATE TO audit_logs
   DO INSTEAD NOTHING;

   CREATE RULE no_delete_audit_logs AS ON DELETE TO audit_logs
   DO INSTEAD NOTHING;
   ```

**验收标准：**
- ✅ 所有关键操作都记录到 audit_logs
- ✅ Audit Logs 可以查询和导出
- ✅ WORM 约束已应用（不能修改/删除）

---

#### 里程碑 2.4：Billing Module（P1）

**任务列表：**

**Week 4:**
1. 实现 Subscription CRUD API
   - `POST /api/v1/platform/subscriptions` - 创建订阅
   - `GET /api/v1/platform/subscriptions` - 列出订阅
   - `GET /api/v1/platform/subscriptions/{id}` - 获取详情
   - `PUT /api/v1/platform/subscriptions/{id}` - 更新订阅
   - `DELETE /api/v1/platform/subscriptions/{id}` - 取消订阅

2. 实现 Invoice CRUD API
   - `POST /api/v1/platform/invoices` - 创建发票
   - `GET /api/v1/platform/invoices` - 列出发票
   - `GET /api/v1/platform/invoices/{id}` - 获取详情
   - `PUT /api/v1/platform/invoices/{id}` - 更新状态（paid/overdue）
   - `GET /api/v1/platform/invoices/{id}/download` - 下载 PDF（未来）

3. 实现最简计费流程
   - tenant 注册
   - 自动创建 subscription
   - 每月自动生成 invoice
   - 管理员手动标记 paid

**Week 5:**
4. 实现 Billing Console
   - 租户订阅列表
   - 发票列表
   - 欠款提醒

5. 实现自动发票生成（Cron job）
   ```python
   # 每月 1 号生成下个月的发票
   @app.route('/cron/generate-invoices')
   def generate_invoices():
       for subscription in Subscription.query.filter_by(status='active'):
           invoice = Invoice(
               tenant_id=subscription.tenant_id,
               subscription_id=subscription.id,
               amount=get_plan_price(subscription.plan),
               due_at=get_next_billing_date(subscription)
           )
           db.session.add(invoice)
       db.session.commit()
   ```

**验收标准：**
- ✅ Subscription CRUD API 已实现
- ✅ Invoice CRUD API 已实现
- ✅ 最简计费流程已实现
- ✅ 自动发票生成已实现

---

#### 里程碑 2.5：Assume Role（P2，可选）

**任务列表：**

**Week 5:**
1. 实现 Assume Role API
   - `POST /api/v1/platform/assume-role` - 模拟登录租户
   - `POST /api/v1/platform/exit-role` - 退出模拟

2. 实现 Role 中间件
   - 验证当前用户是否有权限 Assume Role
   - 记录 Assume/Exit 到 audit_logs

3. 实现 Assume Role UI
   - 选择租户
   - 输入原因
   - 模拟登录

**验收标准：**
- ✅ Assume Role API 已实现
- ✅ Role 中间件已实现
- ✅ Assume Role UI 已实现
- ✅ 所有操作记录到 audit_logs

---

### Phase 3：集成测试和上线（Week 5-6）

#### 里程碑 3.1：端到端测试

**任务列表：**

**Week 5:**
1. 测试 Tenant Registry 流程
   - 创建租户
   - 更新租户
   - 删除租户
   - 验证 audit_logs

2. 测试 Platform Admin Console
   - Dashboard 显示正确
   - Tenant 列表正常
   - Audit Logs 查询正常

3. 测试 Billing Module
   - 创建订阅
   - 生成发票
   - 标记 paid

**Week 6:**
4. 测试 Global Tenant Filter
   - Platform Admin 可以查看所有数据
   - 普通 User 只能查看自己数据

5. 测试 Migration Governance
   - 双轨迁移（Track A 和 Track B）
   - 合并 migrations
   - 部署验证

**验收标准：**
- ✅ 所有功能测试通过
- ✅ Global Tenant Filter 正确应用
- ✅ Migration Governance 正确执行

---

#### 里程碑 3.2：性能测试

**任务列表：**

**Week 6:**
1. 压力测试
   - 10 并发用户
   - 100 并发 API 请求
   - 验证响应时间 < 500ms (P95)

2. 数据库性能测试
   - 查询性能
   - 索引效果
   - 连接池

3. Audit Logs 性能测试
   - 1000 条/分钟写入
   - 查询性能（筛选、分页）

**验收标准：**
- ✅ 压力测试通过
- ✅ 数据库性能符合要求
- ✅ Audit Logs 性能符合要求

---

#### 里程碑 3.3：安全测试

**任务列表：**

**Week 6:**
1. 租户隔离测试
   - User A 不能访问 User B 的数据
   - 验证 Global Tenant Filter

2. Audit Logs WORM 约束测试
   - 不能 UPDATE
   - 不能 DELETE
   - 只能 INSERT 和 SELECT

3. API Contract 测试
   - 向后兼容性
   - 禁止删除字段
   - 禁止修改字段类型

**验收标准：**
- ✅ 租户隔离正确
- ✅ WORM 约束生效
- ✅ API Contract 符合规则

---

#### 里程碑 3.4：部署上线

**任务列表：**

**Week 6:**
1. 数据库迁移
   ```bash
   alembic upgrade head
   ```

2. 部署 Backend API
   - Docker build
   - Push to registry
   - Deploy to Kubernetes

3. 部署 Frontend
   - Build React app
   - Deploy to static hosting

4. 监控配置
   - Prometheus
   - Grafana Dashboard

**验收标准：**
- ✅ 部署成功
- ✅ 所有服务正常运行
- ✅ 监控正常

---

## 📊 成本估算

### v0.3 阶段成本（6 周）

| 类别 | 月度成本 | 6 周总计 |
|---------|-----------|----------|
| **基础设施** | $0（已有） | $0 |
| **人力成本** | $82,000 | $123,000 |
| **总计** | **$82,000** | **$123,000** |

**与 v3.1 对比：**
- v3.1：$802/月（包含 Istio Ambient Mesh + S3 分层存储）
- v3.2：$0/月（不上 Istio，简化审计日志）

**结论：** v3.2 更节省！

---

## 🎯 验收标准

### v0.3 SaaS Foundation 阶段验收标准

| 验收项 | 目标值 | 测试方法 |
|---------|--------|----------|
| **租户数量** | 10-50 | Dashboard 显示 |
| **系统可用性** | ≥99% | 压力测试（1000 QPS，持续 1 小时） |
| **租户隔离** | 100% | 渗透测试（跨租户无法访问） |
| **Audit Logs** | 100% 记录 | 所有关键操作都有审计记录 |
| **Migration Governance** | 100% 符合 | 所有数据库变更通过 Alembic |
| **API Contract** | 100% 向后兼容 | 所有 API 符合 Progressive Contract |
| **Billing Module** | 基础功能 | 订阅、发票、手动标记 paid |
| **Platform Admin** | 完整功能 | Dashboard、Tenant 列表、Audit Logs |

---

## 📚 附录

### A. 技术栈参考

- **Alembic 文档：** https://alembic.sqlalchemy.org/
- **SQLAlchemy 文档：** https://docs.sqlalchemy.org/
- **FastAPI 文档：** https://fastapi.tiangolo.com/
- **React 文档：** https://react.dev/

### B. 参考资料

- **SaaS Architecture Evolution Plan** - 平台演进路线图
- **Mpango Engineering Handbook v0.1** - 工程开发手册
- **Mpango Full Engineering Documentation System** - 完整文档系统
- **Backend Governance Rules** - 后端治理规则

### C. 项目管理

- **开发模式：** Boss + OpenClaw + Opencode 协作
- **版本控制：** Git with main/develop 分支策略
- **文档：** Markdown in `/home/ivy/.openclaw/workspace/docs/`
- **CI/CD：** GitHub Actions

---

**批准人：** CTO
**创建人：** Assistant
**版本：** v3.2（CTO 修正版 - MVP 聚焦）
**状态：** 待评审

---

## 总结

本提案采用 **CTO 修正版**，基于以下核心决策：

### ✅ 核心决策

1. **Schema-per-tenant** - ❌ 不采用，继续使用 `tenant_id` 模型
2. **Istio Ambient Mesh** - ❌ 不采用，Kubernetes + Ingress 足够
3. **WORM 审计日志** - ✅ 简化实现，只需要 `audit_logs` 表

### 🎯 新增 4 条开发规范

1. **Migration Governance** - Track B 禁止修改业务表
2. **Global Tenant Filter** - ORM 自动添加 `tenant_id`
3. **Progressive API Contract** - 只允许向后兼容的变更
4. **Platform Billing Module** - 新增订阅、发票模块

### 📊 优先级排序

1. **Tenant Registry**（P0）- 最高优先级
2. **Platform Admin Console**（P0）
3. **Audit Logs**（P1）
4. **Billing Module**（P1）
5. **Assume Role**（P2）

### 📊 预期成果

**v0.3（6 周）：**
- 租户数量：10-50
- 系统可用性：≥99%
- 租户隔离：100%
- Billing 基础功能：✅
- Platform Admin：✅

---

**准备好开始开发了吗？🚀**

*此提案为 CTO 修正版（v3.2），优先考虑 MVP 阶段（v0.3），避免过度设计。*
