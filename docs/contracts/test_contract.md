# Mpango ERP – Test Contract

**Version:** 1.0  
**Owner:** Jeff + ChatGPT + GLM  
**Target:** KIRO Code + Dev Team  
**Test Frameworks:** pytest + httpx + pytest-asyncio

---

## 1. 测试目录结构（强制）

```
backend/
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # 全局测试配置和 fixtures
│   ├── unit/                    # 单元测试
│   │   ├── __init__.py
│   │   ├── test_models.py       # 模型测试
│   │   ├── test_crud.py         # CRUD 测试
│   │   └── test_utils.py        # 工具函数测试
│   ├── api/                     # API 测试
│   │   ├── __init__.py
│   │   ├── test_auth.py         # 认证 API 测试
│   │   ├── test_users.py        # 用户 API 测试
│   │   └── test_[module].py     # 业务模块 API 测试
│   └── integration/             # 集成测试
│       ├── __init__.py
│       └── test_workflows.py    # 业务流程测试
├── pytest.ini                  # pytest 配置
└── Makefile                     # 测试命令简化
```

## 2. 测试数据管理

### 2.1 Fixture 规范
**所有测试数据必须通过 `pytest.fixture` 管理，禁止硬编码数据**

```python
# tests/conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient
import asyncio

from database.base import Base
from database.session import get_db
from main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="function")
async def async_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(scope="function")
async def async_client(async_session):
    def override_get_db():
        return async_session

    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()

@pytest.fixture
def sample_user_data():
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User"
    }

@pytest.fixture
def admin_token():
    return "Bearer admin_token_here"
```

## 3. API 测试规范

### 3.1 异步测试要求
**必须使用 `httpx.AsyncClient` 和 `pytest-asyncio`**

```python
# tests/api/test_users.py
import pytest
from httpx import AsyncClient
from fastapi import status

@pytest.mark.asyncio
async def test_create_user_success(async_client: AsyncClient, sample_user_data):
    response = await async_client.post("/api/v1/users", json=sample_user_data)
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["success"] is True
    assert data["data"]["username"] == sample_user_data["username"]
    assert "password" not in data["data"]

@pytest.mark.asyncio
async def test_create_user_duplicate_email(async_client: AsyncClient, sample_user_data):
    await async_client.post("/api/v1/users", json=sample_user_data)
    response = await async_client.post("/api/v1/users", json=sample_user_data)
    
    assert response.status_code == status.HTTP_409_CONFLICT
    data = response.json()
    assert data["success"] is False
```

### 3.2 测试覆盖要求
**每个 API 端点必须包含以下测试：**

1. **正常流程测试** - 验证正确输入的预期行为
2. **错误参数测试** - 验证无效输入的错误处理
3. **权限验证测试** - 验证认证和授权机制
4. **边界条件测试** - 验证极限情况的处理

## 4. 单元测试规范

### 4.1 模型测试
```python
def test_user_creation(db_session):
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password"
    )
    db_session.add(user)
    db_session.commit()
    
    assert user.id is not None
    assert user.username == "testuser"
```

### 4.2 CRUD 测试
```python
@pytest.mark.asyncio
async def test_create_user(db_session):
    user_data = UserCreateDTO(
        username="testuser",
        email="test@example.com",
        password="testpassword123"
    )
    
    user = await user_crud.create(db_session, obj_in=user_data)
    
    assert user.username == user_data.username
    assert user.hashed_password != user_data.password
```

## 5. 覆盖率要求

### 5.1 最低覆盖率标准
- **单元测试覆盖率：** ≥ 90%
- **API 测试覆盖率：** ≥ 85%
- **总体覆盖率：** ≥ 85%

### 5.2 覆盖率配置
```ini
# pytest.ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --cov=.
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=85
    --asyncio-mode=auto
```

## 6. CI/CD 集成

### 6.1 Makefile 命令
```makefile
.PHONY: test test-unit test-api test-integration coverage lint format

test:
	pytest

test-unit:
	pytest tests/unit/

test-api:
	pytest tests/api/

coverage:
	pytest --cov=. --cov-report=html --cov-report=term

lint:
	ruff check .

ci: lint test coverage
```

## 7. 强制要求

1. **所有 API** 必须有对应的测试
2. **所有测试** 必须使用 fixture 管理数据
3. **所有异步代码** 必须使用 pytest-asyncio
4. **所有外部依赖** 必须进行 Mock
5. **覆盖率** 必须达到最低标准
6. **CI/CD** 必须集成测试流程

---

**重要提醒：** 所有团队成员必须遵守此测试契约，确保代码质量和系统稳定性。
