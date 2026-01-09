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

# 测试数据库配置 (使用异步内存数据库)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)

@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="function")
async def async_session():
    """创建独立的异步数据库会话，并在测试结束后清理"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(scope="function")
async def async_client(async_session):
    """创建异步测试客户端，并覆盖数据库依赖"""
    def override_get_db():
        return async_session

    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    # 清理依赖覆盖
    app.dependency_overrides.clear()

@pytest.fixture
def sample_user_data():
    """示例用户数据"""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User"
    }

@pytest.fixture
def admin_token():
    """管理员令牌"""
    # 这里应该生成真实的 JWT token
    return "Bearer admin_token_here"
```

### 2.2 数据工厂
```python
# tests/factories.py
import factory
from factory.alchemy import SQLAlchemyModelFactory
from models.user import User

class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "commit"

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    full_name = factory.Faker("name")
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
    """测试成功创建用户"""
    response = await async_client.post("/api/v1/users", json=sample_user_data)
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["success"] is True
    assert data["data"]["username"] == sample_user_data["username"]
    assert data["data"]["email"] == sample_user_data["email"]
    assert "password" not in data["data"]  # 确保密码不返回

@pytest.mark.asyncio
async def test_create_user_duplicate_email(async_client: AsyncClient, sample_user_data):
    """测试重复邮箱创建用户"""
    # 先创建一个用户
    await async_client.post("/api/v1/users", json=sample_user_data)
    
    # 尝试创建相同邮箱的用户
    response = await async_client.post("/api/v1/users", json=sample_user_data)
    
    assert response.status_code == status.HTTP_409_CONFLICT
    data = response.json()
    assert data["success"] is False
    assert "email" in data["error"]["message"].lower()

@pytest.mark.asyncio
async def test_create_user_invalid_data(async_client: AsyncClient):
    """测试无效数据创建用户"""
    invalid_data = {
        "username": "ab",  # 太短
        "email": "invalid-email",  # 无效邮箱
        "password": "123"  # 太短
    }
    
    response = await async_client.post("/api/v1/users", json=invalid_data)
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    assert data["success"] is False
    assert len(data["error"]["details"]) > 0

@pytest.mark.asyncio
async def test_get_users_unauthorized(async_client: AsyncClient):
    """测试未授权访问用户列表"""
    response = await async_client.get("/api/v1/users")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.asyncio
async def test_get_users_authorized(async_client: AsyncClient, admin_token):
    """测试授权访问用户列表"""
    headers = {"Authorization": admin_token}
    response = await async_client.get("/api/v1/users", headers=headers)
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert "items" in data["data"]
    assert "pagination" in data["data"]
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
# tests/unit/test_models.py
import pytest
from sqlalchemy.exc import IntegrityError
from models.user import User

def test_user_creation(db_session):
    """测试用户模型创建"""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password"
    )
    db_session.add(user)
    db_session.commit()
    
    assert user.id is not None
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.created_at is not None

def test_user_unique_email(db_session):
    """测试邮箱唯一性约束"""
    user1 = User(username="user1", email="test@example.com", hashed_password="hash1")
    user2 = User(username="user2", email="test@example.com", hashed_password="hash2")
    
    db_session.add(user1)
    db_session.commit()
    
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.commit()
```

### 4.2 CRUD 测试
```python
# tests/unit/test_crud.py
import pytest
from crud.user import user_crud
from schemas.user import UserCreateDTO

@pytest.mark.asyncio
async def test_create_user(db_session):
    """测试创建用户 CRUD"""
    user_data = UserCreateDTO(
        username="testuser",
        email="test@example.com",
        password="testpassword123"
    )
    
    user = await user_crud.create(db_session, obj_in=user_data)
    
    assert user.username == user_data.username
    assert user.email == user_data.email
    assert user.hashed_password != user_data.password  # 确保密码已加密

@pytest.mark.asyncio
async def test_get_user_by_email(db_session, sample_user_data):
    """测试通过邮箱获取用户"""
    # 先创建用户
    created_user = await user_crud.create(db_session, obj_in=sample_user_data)
    
    # 通过邮箱查找
    found_user = await user_crud.get_by_email(db_session, email=sample_user_data["email"])
    
    assert found_user is not None
    assert found_user.id == created_user.id
    assert found_user.email == sample_user_data["email"]
```

## 5. 集成测试

### 5.1 业务流程测试
```python
# tests/integration/test_workflows.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_user_registration_and_login_workflow(async_client: AsyncClient):
    """测试用户注册和登录完整流程"""
    # 1. 注册用户
    user_data = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "securepassword123"
    }
    
    register_response = await async_client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201
    
    # 2. 登录用户
    login_data = {
        "username": user_data["username"],
        "password": user_data["password"]
    }
    
    login_response = await async_client.post("/api/v1/auth/login", json=login_data)
    assert login_response.status_code == 200
    
    token_data = login_response.json()
    assert "access_token" in token_data["data"]
    
    # 3. 使用 token 访问受保护资源
    headers = {"Authorization": f"Bearer {token_data['data']['access_token']}"}
    profile_response = await async_client.get("/api/v1/users/me", headers=headers)
    
    assert profile_response.status_code == 200
    profile_data = profile_response.json()
    assert profile_data["data"]["username"] == user_data["username"]
```

## 6. Mock 和外部依赖

### 6.1 外部服务 Mock
```python
# tests/unit/test_external_services.py
import pytest
from unittest.mock import patch, AsyncMock
from services.email_service import send_email

@pytest.mark.asyncio
@patch('services.email_service.smtp_client')
async def test_send_email_success(mock_smtp):
    """测试邮件发送成功"""
    mock_smtp.send_message = AsyncMock(return_value=True)
    
    result = await send_email(
        to="test@example.com",
        subject="Test Subject",
        body="Test Body"
    )
    
    assert result is True
    mock_smtp.send_message.assert_called_once()

@pytest.mark.asyncio
@patch('services.email_service.smtp_client')
async def test_send_email_failure(mock_smtp):
    """测试邮件发送失败"""
    mock_smtp.send_message = AsyncMock(side_effect=Exception("SMTP Error"))
    
    result = await send_email(
        to="test@example.com",
        subject="Test Subject",
        body="Test Body"
    )
    
    assert result is False
```

## 7. 覆盖率要求

### 7.1 最低覆盖率标准
- **单元测试覆盖率：** ≥ 90%
- **API 测试覆盖率：** ≥ 85%
- **总体覆盖率：** ≥ 85%

### 7.2 覆盖率配置
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

## 8. CI/CD 集成

### 8.1 Makefile 命令
```makefile
# Makefile
.PHONY: test test-unit test-api test-integration coverage lint format

# 运行所有测试
test:
	pytest

# 运行单元测试
test-unit:
	pytest tests/unit/

# 运行 API 测试
test-api:
	pytest tests/api/

# 运行集成测试
test-integration:
	pytest tests/integration/

# 生成覆盖率报告
coverage:
	pytest --cov=. --cov-report=html --cov-report=term

# 代码检查
lint:
	ruff check .

# 代码格式化
format:
	ruff format .

# 完整的 CI 检查
ci: lint test coverage

```

### 8.2 GitHub Actions 集成
```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install poetry
        poetry install # ruff 会被自动安装
    
    - name: Run tests
      run: |
        make ci

    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## 9. 测试最佳实践

### 9.1 测试命名规范
- **测试文件：** `test_*.py`
- **测试类：** `Test*`
- **测试函数：** `test_*`
- **描述性命名：** `test_create_user_with_valid_data_should_return_201`

### 9.2 测试组织原则
- **AAA 模式：** Arrange（准备）、Act（执行）、Assert（断言）
- **单一职责：** 每个测试只验证一个功能点
- **独立性：** 测试之间不应有依赖关系
- **可重复性：** 测试结果应该是确定的

### 9.3 断言最佳实践
```python
# 好的断言
assert response.status_code == 200
assert "username" in response.json()["data"]
assert len(users) == 5

# 避免的断言
assert response.status_code  # 不明确
assert response.json()  # 不具体
```

## 10. 强制要求

1. **所有 API** 必须有对应的测试
2. **所有测试** 必须使用 fixture 管理数据
3. **所有异步代码** 必须使用 pytest-asyncio
4. **所有外部依赖** 必须进行 Mock
5. **覆盖率** 必须达到最低标准
6. **CI/CD** 必须集成测试流程

---

**重要提醒：** 所有团队成员必须遵守此测试契约，确保代码质量和系统稳定性。