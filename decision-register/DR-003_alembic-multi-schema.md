# DR-003: Alembic Multi-Schema Migration Strategy

## Decision ID
`DR-003`

## Title
Single Migration History with Per-Tenant Schema Execution

## Status
✅ **Approved & Implemented**

## Date
2025-01-09

## Context
采用 Schema-per-Tenant 策略后，需要解决数据库迁移的管理问题：
1. 所有租户schema结构必须保持一致
2. 新租户创建时需要初始化完整的表结构
3. 迁移版本需要集中管理
4. 支持单租户和批量租户迁移

## Decision
**采用单一迁移历史 + 参数化Schema执行策略**

### 核心设计
- 所有租户共享一套 Alembic 迁移脚本
- 版本表 (`alembic_version`) 存储在 `public` schema
- 通过 `-x tenant_schema=<schema>` 参数指定目标schema
- 迁移执行前设置 `SET LOCAL search_path`

## Rationale

### 为什么选择单一迁移历史

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| 每租户独立迁移历史 | 灵活 | 版本不一致风险高 | ❌ |
| **单一历史+参数化执行** | 版本统一，易管理 | 需要循环执行 | ✅ 采纳 |
| 动态DDL生成 | 无需迁移文件 | 不可审计，风险高 | ❌ |

### 关键优势
1. **版本一致性**: 所有租户使用相同的迁移版本
2. **可审计**: 迁移脚本在版本控制中
3. **灰度发布**: 可以先对测试租户执行迁移
4. **回滚支持**: 可以对单个租户执行 downgrade

## Authority
- **L0**: `Database Contract.md` - Section 9 Alembic multi-schema migrations

## Impact

### 影响范围
- `backend/alembic/env.py` 配置
- 租户 provisioning 流程
- 运维迁移脚本

### 影响的AI角色
| AI Role | Impact |
|---------|--------|
| Backend AI | 编写迁移脚本时需考虑多schema |
| Ops AI | 需要实现批量迁移脚本 |

## Implementation

### 1. env.py 配置
```python
def get_tenant_schema():
    tenant_schema = context.get_x_argument(as_dictionary=True).get('tenant_schema')
    if tenant_schema:
        return tenant_schema
    return settings.DEFAULT_TENANT_SCHEMA  # 默认 t_dev

def do_run_migrations(connection: Connection):
    tenant_schema = get_tenant_schema()
    
    # 设置搜索路径
    connection.execute(f'SET LOCAL search_path TO "{tenant_schema}", public')
    
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema="public",  # 版本表在public
        include_schemas=True,
    )
    
    with context.begin_transaction():
        context.run_migrations()
```

### 2. 命令行使用
```bash
# 升级单个租户
alembic upgrade head -x tenant_schema=t_acme01

# 升级开发租户（默认）
alembic upgrade head

# 降级单个租户
alembic downgrade -1 -x tenant_schema=t_acme01
```

### 3. 批量迁移脚本
```python
# scripts/migrate_all_tenants.py
async def migrate_all_tenants():
    async with get_db() as db:
        result = await db.execute(
            select(Wholesaler).where(Wholesaler.is_deleted == False)
        )
        wholesalers = result.scalars().all()
    
    for w in wholesalers:
        schema = w.get_tenant_schema()
        subprocess.run([
            "alembic", "upgrade", "head",
            "-x", f"tenant_schema={schema}"
        ])
```

### 4. 租户Provisioning流程
```python
async def provision_tenant(code: str, name: str):
    # 1. 创建wholesaler记录
    wholesaler = await crud.wholesaler.create(db, WholesalerCreate(code=code, name=name))
    
    # 2. 创建schema
    schema = wholesaler.get_tenant_schema()
    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    
    # 3. 执行迁移
    subprocess.run(["alembic", "upgrade", "head", "-x", f"tenant_schema={schema}"])
    
    # 4. 插入种子数据（角色、权限、admin用户）
    await seed_rbac(schema)
```

## Constraints
1. **迁移脚本必须幂等**: 支持重复执行
2. **禁止schema特定逻辑**: 迁移脚本不能包含租户特定的条件
3. **版本表位置固定**: 必须在 `public` schema

## Risks
| Risk | Mitigation |
|------|------------|
| 迁移失败导致部分租户不一致 | 迁移前备份，失败后重试 |
| 批量迁移耗时过长 | 并行执行，限制并发数 |
| 新迁移破坏现有数据 | staging环境先测试 |

## Related Decisions
- DR-001: Schema-per-Tenant Strategy
- DR-002: CRUD Base Class Design

---

**Created by:** Architect AI  
**Date:** 2025-01-09