# DR-001: Schema-per-Tenant Multi-Tenancy Strategy

## Decision ID
`DR-001`

## Title
Adopt Schema-per-Tenant as the Multi-Tenancy Isolation Strategy

## Status
✅ **Approved & Implemented**

## Date
2025-01-09

## Context
Mpango ERP 需要支持多个批发商（Wholesaler）同时使用系统，每个批发商是一个独立的租户。需要选择合适的多租户隔离策略来确保：
1. 数据安全隔离
2. 性能可接受
3. 运维可管理
4. 成本可控

## Decision
**采用 Schema-per-Tenant 策略**

每个批发商（租户）拥有独立的 PostgreSQL Schema，所有租户共享同一个数据库实例。

### 核心设计
```
Database: mpango_erp
├── public (schema)
│   └── wholesalers (租户注册表)
├── t_<tenant_uuid_1> (schema)
│   ├── users
│   ├── roles
│   ├── orders
│   └── ...
├── t_<tenant_uuid_2> (schema)
│   ├── users
│   ├── roles
│   ├── orders
│   └── ...
└── ...
```

### 租户标识符
| 标识符 | 来源 | 用途 |
|--------|------|------|
| tenant_code | Wholesaler.code | 登录时用户输入 |
| tenant_id | Wholesaler.id (UUID) | 内部标识 |
| tenant_schema | `t_<uuid_without_dashes>` | 数据库schema名 |

## Rationale

### 为什么选择 Schema-per-Tenant

| 策略 | 隔离性 | 性能 | 运维复杂度 | 成本 | 决策 |
|------|--------|------|------------|------|------|
| Database-per-Tenant | 最高 | 最好 | 高 | 高 | ❌ MVP阶段成本过高 |
| **Schema-per-Tenant** | 高 | 好 | 中 | 中 | ✅ 采纳 |
| Row-level (shared table) | 低 | 一般 | 低 | 低 | ❌ 隔离性不足 |

### 关键优势
1. **数据隔离**: 每个租户的数据物理隔离在独立schema中
2. **查询简化**: 通过 `SET search_path` 自动路由，无需每个查询加租户条件
3. **迁移管理**: 可以对单个租户执行迁移，支持灰度发布
4. **备份恢复**: 可以单独备份/恢复某个租户的数据
5. **性能**: 索引在schema级别，查询性能好

## Authority
- **L0**: `Multi-Tenancy Spec (MVP).md` - Section 1 Decision
- **L0**: `Database Contract.md` - Section 9 Alembic multi-schema

## Impact

### 影响范围
- 所有数据库表设计
- 所有数据库查询
- Alembic迁移策略
- 租户provisioning流程
- 备份恢复策略

### 影响的AI角色
| AI Role | Impact |
|---------|--------|
| Backend AI | 必须使用 `get_tenant_db_session` 依赖 |
| Ops AI | 需要管理多schema迁移和备份 |
| Reviewer AI | 验证所有查询都通过租户会话 |

## Implementation

### 1. 租户注册表 (public schema)
```sql
CREATE TABLE public.wholesalers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(32) UNIQUE NOT NULL,  -- tenant_code
    name VARCHAR(255) NOT NULL,
    ...
);
```

### 2. 租户Schema命名
```python
def get_tenant_schema(wholesaler_id: UUID) -> str:
    return f"t_{str(wholesaler_id).replace('-', '')}"
```

### 3. 请求级Schema切换
```python
async def get_tenant_db(tenant_schema: str):
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(f'SET LOCAL search_path TO "{tenant_schema}", public')
        )
        yield session
```

## Constraints
1. **禁止跨租户查询**: MVP阶段不支持跨租户数据访问
2. **Schema命名不可变**: 一旦创建，tenant_schema名称不可更改
3. **迁移必须全量**: 所有租户必须运行相同版本的迁移

## Risks
| Risk | Mitigation |
|------|------------|
| Schema数量过多影响性能 | 监控schema数量，必要时拆分数据库 |
| 迁移失败导致租户不一致 | 迁移脚本必须幂等，支持重试 |
| 误操作删除schema | 严格的权限控制，定期备份 |

## Related Decisions
- DR-002: CRUD Base Class Design
- DR-003: Alembic Multi-Schema Migration Strategy

---

**Created by:** Architect AI
**Approved by:** Product Owner (implicit via L0 spec)
**Date:** 2025-01-09
