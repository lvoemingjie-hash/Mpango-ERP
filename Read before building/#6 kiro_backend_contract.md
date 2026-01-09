# Mpango ERP — Backend Development Contract

**Version:** 1.0  
**Owner:** Jeff（Product Owner）+ ChatGPT（Architect） + GLM  
**Target:** KIRO Code + Backend Developers  
**Tech Stack:** FastAPI + PostgreSQL + Alembic + Modular Architecture

---

## 目的

本契约用于确保 AI 工具（Kiro、Cursor、Claude Code 等）在生成后端代码时：

- 结构完整
- 逻辑连续  
- 无关键遗漏

## 技术栈

- **Web Framework:** FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy 2.0+
- **Migration:** Alembic
- **Validation:** Pydantic v2
- **Authentication:** JWT + RBAC
- **Testing:** pytest + httpx

## 目录结构

```
backend/
├── main.py                    # FastAPI 主文件
├── database/
│   ├── __init__.py
│   ├── session.py            # 数据库会话
│   └── base.py               # Base 类
├── api/
│   ├── __init__.py
│   └── v1/
│       ├── __init__.py
│       ├── auth.py           # 认证路由
│       ├── users.py          # 用户路由
│       └── [module].py       # 业务模块路由
├── models/
│   ├── __init__.py
│   ├── base.py               # 基础模型类
│   ├── user.py               # 用户模型
│   └── [module].py           # 业务模块模型
├── schemas/
│   ├── __init__.py
│   ├── user.py               # 用户 DTO
│   └── [module].py           # 业务模块 DTO
├── crud/
│   ├── __init__.py
│   ├── base.py               # 基础 CRUD 类
│   ├── user.py               # 用户 CRUD
│   └── [module].py           # 业务模块 CRUD
├── core/
│   ├── __init__.py
│   ├── config.py             # 配置管理
│   ├── security.py           # 安全相关
│   └── exceptions.py         # 异常处理
├── alembic/                  # 数据库迁移
├── tests/                    # 测试目录
├── requirements.txt          # 依赖管理
└── .env                      # 环境变量
```

## 数据库层

### 1. 会话管理 (`database/session.py`)
```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from core.config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 2. 基类 (`database/base.py`) 统一使用UUID
```python
from sqlalchemy import Column, Integer, DateTime, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class BaseModel(Base):
    __abstract__ = True
    
    id = UUID PRIMARY KEY DEFAULT gen_random_uuid()
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    is_deleted BOOLEAN DEFAULT false
    
```

### 3. 数据库初始化
- **禁止** 在应用代码中直接操作数据库结构
- **必须** 使用 Alembic 进行所有数据库变更
- **必须** 提供初始化脚本

## 环境变量

### `.env` 文件
```env
DATABASE_URL=postgresql://user:password@localhost/dbname
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### 配置管理 (`core/config.py`)
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"

settings = Settings()
```

## FastAPI 主文件

### `main.py` 结构
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.v1 import auth, users, [modules]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    yield
    # 关闭时执行

app = FastAPI(
    title="Mpango ERP API",
    version="1.0.0",
    lifespan=lifespan
)

# 路由注册
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
# 其他业务模块路由...
```

## 模块化要求

### 1. 业务模块结构
每个业务模块必须包含：
- `models/[module].py` - 数据模型
- `schemas/[module].py` - Pydantic DTO
- `crud/[module].py` - CRUD 操作
- `api/v1/[module].py` - API 路由

### 2. 模型继承
```python
from database.base import BaseModel
from sqlalchemy import Column, String

class User(BaseModel):
    __tablename__ = "users"
    
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
```

### 3. CRUD 基类
```python
from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy.orm import Session
from database.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)

class CRUDBase(Generic[ModelType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model
    
    def get(self, db: Session, id: int) -> Optional[ModelType]:
        return db.query(self.model).filter(self.model.id == id).first()
    
    def get_multi(self, db: Session, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return db.query(self.model).offset(skip).limit(limit).all()
```

## 代码质量

### 1. 路由规范
- 使用依赖注入进行权限验证
- 统一异常处理
- 完整的类型注解

### 2. 模型规范
- 继承 BaseModel
- 明确的字段定义
- 适当的索引和约束

### 3. Schema 规范
- 输入输出分离
- 完整的验证规则
- 清晰的字段文档

## 强制要求

1. **所有模型** 必须继承 `BaseModel`
2. **所有路由** 必须使用类型注解
3. **所有 CRUD** 必须继承 `CRUDBase`
4. **所有配置** 必须通过 Pydantic Settings
5. **所有数据库操作** 必须通过 Alembic

# 补充
1. 登录：要求传 tenant_code → 查 public.wholesalers → 签发含 tenant_id/tenant_schema 的 JWT。

2. 每个请求：在 get_db 里 SET LOCAL search_path（事务内），保证 ORM 自动落到 tenant schema。

3. RBAC：实现 has_permission(token, permission_code)，并在每个路由挂 Depends(require_permission(...))

4. 每个测试会话创建独立 tenant schema（t_test_xxx），并在请求 token 里写入对应 tenant_schema
---

**重要提醒：** 所有后端代码生成任务必须明确引用此契约，确保遵循以上规范。