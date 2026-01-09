# Decision Register Entry

## Decision ID
`DR-2025-01-09-002`

## Title
Async Database Session Management with Per-Request Tenant Isolation

## Status
✅ **Approved & Implemented**

## Context
根据 **L0 Multi-Tenancy Spec (MVP)**，系统必须实现Schema-per-tenant策略。每个HTTP请求需要：
1. 从JWT claims中提取 `tenant_schema`
2. 在数据库事务中设置 `SET LOCAL search_path`
3. 确保ORM查询自动路由到正确的租户schema

同时，根据 **L0 Database Contract**，系统必须使用 **SQLAlchemy 2.0 async mode**。

## Decision
**采用异步数据库会话 + 依赖注入 + SET LOCAL search_path 机制**

### 核心实现
```python
# backend/database/session.py
async def get_tenant_db(tenant_schema: str) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            # 设置搜索路径到租户schema
            await session.execute(
                text(f'SET LOCAL search_path TO "{tenant_schema}", public')
            )
            yield session
        finally:
            await session.close()

# backend/api/dependencies.py
async def get_tenant_db_session(
    token_payload: dict = Depends(get_current_user_token)
) -> AsyncSession:
    tenant_schema = token_payload.get("tenant_schema")
    async with get_tenant_db(tenant_schema) as db:
        yield db
```

## Rationale
1. **L0合规性**: 严格遵守Multi-Tenancy Spec的强制要求
2. **事务级隔离**: `SET LOCAL` 确保search_path仅在当前事务生效
3. **安全性**: tenant_schema仅从JWT claims获取，防止客户端伪造
4. **性能**: 异步会话支持高并发场景
5. **开发体验**: 依赖注入使业务代码无需关心租户切换逻辑

## Alternatives Considered
| 选项 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| 同步会话 | 实现简单 | 不符合L0要求（async mode） | ❌ 拒绝 |
| 全局search_path | 无需每次设置 | 线程安全问题，租户泄漏风险 | ❌ 拒绝 |
| 手动schema前缀 | 显式控制 | 代码侵入性强，易出错 | ❌ 拒绝 |
| 异步会话+SET LOCAL | 符合L0，安全隔离 | 需要理解async/await | ✅ 采纳 |

## Impact
### 影响范围
- `backend/database/session.py` - 会话管理核心逻辑
- `backend/api/dependencies.py` - 依赖注入函数
- `backend/api/v1/*.py` - 所有API路由必须使用 `Depends(get_tenant_db_session)`
- `backend/crud/*.py` - 所有CRUD操作接收 `AsyncSession` 参数

### 影响的AI角色
- **Backend AI**: 必须在所有路由中使用 `get_tenant_db_session` 依赖
- **Ops AI**: 需要确保PostgreSQL支持异步连接（asyncpg驱动）
- **Reviewer AI**: 需要验证所有数据库操作都通过租户会话

## Authority
- **来源**: L0 Multi-Tenancy Spec (MVP).md Section 4.2
- **来源**: L0 Database Contract.md Section 5 (ORM & Migrations)
- **规范层级**: L0 (最高优先级，不可绕过)
- **裁决者**: Architect AI（基于L0强制要求）

## Implementation
### 关键代码位置
1. **会话工厂**: `backend/database/session.py`
   - `async_engine` - 异步引擎
   - `AsyncSessionLocal` - 会话工厂
   - `get_tenant_db()` - 租户会话生成器

2. **依赖注入**: `backend/api/dependencies.py`
   - `get_current_user_token()` - JWT验证
   - `get_tenant_db_session()` - 租户会话依赖

3. **使用示例**: `backend/api/v1/users.py`
   ```python
   @router.get("/", response_model=List[UserRead])
   async def read_users(
       db: AsyncSession = Depends(get_tenant_db_session),  # ✅ 租户会话
       current_user: User = Depends(require_permission("users:read"))
   ):
       users = await user.get_multi(db, skip=0, limit=100)
       return users
   ```

## Validation
- [x] 异步引擎配置正确（asyncpg驱动）
- [x] SET LOCAL语句在事务中执行
- [x] 依赖注入链路完整（JWT → tenant_schema → DB session）
- [ ] 集成测试验证租户隔离（TODO: Backend AI）

## Known Risks
1. **性能开销**: 每个请求都执行SET LOCAL
   - **缓解**: PostgreSQL的SET LOCAL开销极小（<1ms）
   
2. **连接池管理**: 异步会话需要正确配置连接池
   - **缓解**: 使用SQLAlchemy默认连接池配置

3. **错误处理**: 如果tenant_schema不存在，会抛出PostgreSQL错误
   - **缓解**: 在租户provisioning时确保schema创建成功

## Related Decisions
- `DR-2025-01-09-003` - JWT Claims Structure (tenant_schema字段)
- 未来决策：连接池大小配置（Ops AI负责）

## Notes
此决策为**架构核心决策**，直接影响数据隔离安全性，必须严格执行。

任何绕过 `get_tenant_db_session` 的数据库操作都是**严重违规**。

---

**Created by:** Architect AI – Kiro  
**Date:** 2025-01-09  
**Last Updated:** 2025-01-09  
**Authority:** L0 Multi-Tenancy Spec + L0 Database Contract