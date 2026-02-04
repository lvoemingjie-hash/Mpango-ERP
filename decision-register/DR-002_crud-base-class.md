# DR-002: Generic CRUD Base Class Design

## Decision ID
`DR-002`

## Title
Implement Generic CRUD Base Class with Soft Delete Support

## Status
✅ **Approved & Implemented**

## Date
2025-01-09

## Context
Mpango ERP 的所有业务模块都需要标准的 CRUD 操作。根据 L0 Database Contract 的要求：
1. 所有表必须支持软删除 (is_deleted, deleted_at)
2. 所有查询必须默认过滤已删除记录
3. 所有表必须有审计字段 (created_at, updated_at, created_by, updated_by)

需要设计一个可复用的 CRUD 基类来确保这些规则被一致执行。

## Decision
**实现泛型 CRUDBase 类，强制软删除和审计字段支持**

### 核心设计
```python
class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: UUID) -> Optional[ModelType]:
        # 默认过滤 is_deleted = false
        ...

    async def get_multi(self, db: AsyncSession, skip: int, limit: int) -> List[ModelType]:
        # 默认过滤 is_deleted = false
        ...

    async def create(self, db: AsyncSession, obj_in: CreateSchemaType) -> ModelType:
        ...

    async def update(self, db: AsyncSession, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType:
        ...

    async def remove(self, db: AsyncSession, id: UUID) -> Optional[ModelType]:
        # 软删除：设置 is_deleted = true, deleted_at = now()
        ...

    async def hard_delete(self, db: AsyncSession, id: UUID) -> bool:
        # 硬删除：谨慎使用
        ...
```

## Rationale

### 为什么使用泛型基类

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| 每个模型独立实现CRUD | 灵活 | 代码重复，规则不一致 | ❌ |
| **泛型基类** | 代码复用，规则统一 | 需要理解泛型 | ✅ 采纳 |
| Mixin模式 | 灵活组合 | 复杂度高 | ❌ |

### 关键优势
1. **规则一致性**: 软删除逻辑集中在基类，不会遗漏
2. **代码复用**: 减少80%以上的CRUD代码
3. **类型安全**: TypeVar绑定确保类型正确
4. **可扩展**: 子类可以覆盖特定方法

## Authority
- **L0**: `Database Contract.md` - Section 2.3 审计与软删除
- **L2**: `Backend Contract.md` - CRUD基类要求

## Impact

### 影响范围
- 所有 `backend/crud/*.py` 文件
- 所有数据库查询逻辑
- 删除操作的行为

### 影响的AI角色
| AI Role | Impact |
|---------|--------|
| Backend AI | 所有CRUD类必须继承CRUDBase |
| Reviewer AI | 验证没有绕过基类的直接查询 |

## Implementation

### 1. BaseModel (SQLAlchemy)
```python
class BaseModel(Base):
    __abstract__ = True

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID, nullable=True)
    updated_by = Column(UUID, nullable=True)

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
```

### 2. CRUDBase 核心方法
```python
async def get(self, db: AsyncSession, id: UUID) -> Optional[ModelType]:
    result = await db.execute(
        select(self.model).where(
            self.model.id == id,
            self.model.is_deleted == False  # 强制过滤
        )
    )
    return result.scalar_one_or_none()

async def remove(self, db: AsyncSession, id: UUID) -> Optional[ModelType]:
    db_obj = await self.get(db, id)
    if db_obj:
        db_obj.soft_delete()  # 软删除
        await db.commit()
    return db_obj
```

### 3. 使用示例
```python
class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        result = await db.execute(
            select(User).where(
                User.email == email,
                User.is_deleted == False  # 继承软删除规则
            )
        )
        return result.scalar_one_or_none()

user = CRUDUser(User)
```

## Constraints
1. **禁止绕过基类**: 不允许直接写 `db.query(Model).all()` 这样的查询
2. **软删除优先**: 除非有明确业务需求，否则使用 `remove()` 而非 `hard_delete()`
3. **审计字段必填**: 所有模型必须继承 BaseModel

## Risks
| Risk | Mitigation |
|------|------------|
| 开发者绕过基类直接查询 | Code Review + Linting规则 |
| 软删除数据累积过多 | 定期归档或清理策略 |
| 泛型类型推断问题 | 使用明确的类型注解 |

## Related Decisions
- DR-001: Schema-per-Tenant Strategy
- DR-003: Alembic Multi-Schema Migration Strategy

---

**Created by:** Architect AI
**Date:** 2025-01-09
