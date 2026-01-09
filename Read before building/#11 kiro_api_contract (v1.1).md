下面是根据你提供的 `kiro_api_contract-v1.1.md` 进一步补齐“状态码统一规范 + error.details 结构 + 三个关键接口错误示例”，并且**保持 1~12 章节编号不变**后的最终可复制版本。[1]

```md
# Mpango ERP – API Contract

**Version:** 1.1 (MVP frozen)  
**Owner:** Jeff（Product Owner）+ ChatGPT（Architect） + GLM  
**Target:** KIRO Code + Backend Developers + Frontend Developers  
**Tech Stack:** FastAPI + PostgreSQL + Pydantic + JWT

---

## 1. API 设计原则

### 1.1 RESTful 风格
- **必须** 遵循 REST 架构风格
- **必须** 使用标准 HTTP 方法（GET, POST, PUT, DELETE）
- **必须** 使用合理的 HTTP 状态码

#### 1.1.1 HTTP 状态码统一规范（MVP）
为避免实现歧义，MVP 阶段统一约定：
- Create（POST 创建资源）：**201 Created**
- Action（POST 执行动作，如 confirm/receive/ship/cancel/submit）：**200 OK**
- Update（PUT 更新资源）：**200 OK**
- Delete（DELETE 删除资源）：**204 No Content**（如需返回统一响应体，可改用 200 OK，但必须全项目一致）

### 1.2 统一数据格式
- **必须** 使用 JSON 作为数据交换格式
- **必须** 使用 UTF-8 编码
- **必须** 遵循统一的响应格式

---

## 2. API 路径规范

### 2.1 核心路径前缀
```
/api/v1/
```

### 2.2 路径结构
```
/api/v1/{resource}
/api/v1/{resource}/{id}
/api/v1/{resource}/{id}/{sub-resource}
```

### 2.3 示例路径
```
GET    /api/v1/users              # 获取用户列表
GET    /api/v1/users/{id}         # 获取单个用户
POST   /api/v1/users              # 创建用户
PUT    /api/v1/users/{id}         # 更新用户
DELETE /api/v1/users/{id}         # 删除用户
```

### 2.4 Idempotency（MVP）
#### 2.4.1 Header
- Header: `Idempotency-Key: <string>`
- Constraints (MVP):
  - 1-64 chars
  - 推荐使用 UUIDv4 字符串

#### 2.4.2 强制要求 Idempotency-Key 的接口（MVP）
仅以下两类操作强制 Idempotency-Key：
1) 入库确认（Inbound receive / Goods receipt）
2) 转账收款创建（Transfer payment create，method=transfer）

#### 2.4.3 服务端幂等行为（MVP）
- 幂等作用域：按 tenant 隔离（tenant 从 JWT claim 获取）。
- 同一个 Idempotency-Key 重复请求：
  - 若请求体一致：返回同一份成功响应，不重复执行副作用（不重复入库/不重复记账）。
  - 若请求体不同：返回 409，错误码 `IDEMPOTENCY_KEY_CONFLICT`。

---

## 3. 请求规范

### 3.1 POST 请求 DTO
**所有 POST 请求必须使用 Pydantic DTO**

```python
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

class UserCreateDTO(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = Field(None, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "email": "john@example.com",
                "password": "securepassword123",
                "full_name": "John Doe"
            }
        }
```

### 3.2 分页规范
**所有列表请求必须实现分页**

```python
class PaginationParams(BaseModel):
    page: int = Field(1, ge=1, description="页码，从1开始")
    size: int = Field(10, ge=1, le=100, description="每页数量，最大100")

# 查询参数示例
GET /api/v1/users?page=1&size=20
```

---

## 4. 响应格式规范

### 4.1 成功响应格式
```json
{
  "success": true,
  "data": {},
  "message": "操作成功",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 4.2 分页响应格式
```json
{
  "success": true,
  "data": {
    "items": [],
    "pagination": {
      "page": 1,
      "size": 10,
      "total": 100,
      "pages": 10
    }
  },
  "message": "获取成功",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 4.3 错误响应格式
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "输入数据验证失败",
    "details": [
      { "field": "email", "message": "邮箱格式不正确" }
    ]
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 4.4 业务错误码（MVP）
- 400 `MISSING_IDEMPOTENCY_KEY`
  - 需要 Idempotency-Key 的接口未提供该 header。
- 409 `IDEMPOTENCY_KEY_CONFLICT`
  - 相同 Idempotency-Key 但请求体不一致。
- 409 `INVALID_STATE`
  - 不允许的状态流转（如：入库时 PO 非 pending）。
- 409 `INSUFFICIENT_INVENTORY`
  - confirm order 库存不足。
- 409 `DUPLICATE_TRANSACTION_ID`
  - transfer payment 的 transaction_id 重复（建议每 tenant 唯一）。
- 403 `PERMISSION_DENIED`
  - RBAC 权限不足。
  
  Rule (MVP): Error codes are UPPERCASE and MUST NOT contain underscores (e.g., use MISSINGIDEMPOTENCYKEY, not MISSING_IDEMPOTENCY_KEY).



### 4.5 Error details structure（MVP）
业务错误（400/409/403）响应必须满足以下结构（details 可选，但若存在必须为数组）：
```json
{
  "success": false,
  "error": {
    "code": "SOME_CODE",
    "message": "Human-readable message",
    "details": [
      {
        "field": "optional_field_name",
        "message": "optional_detail_message",
        "meta": {
          "optional_key": "optional_value"
        }
      }
    ]
  },
  "timestamp": "2026-01-06T12:00:00Z"
}
```

---

## 5. DTO 规范

### 5.1 目录结构
```
backend/schemas/
├── __init__.py
├── user.py          # 用户相关 DTO
├── auth.py          # 认证相关 DTO
├── sales.py         # 订单相关 DTO
├── procurement.py   # 采购相关 DTO
├── finance.py       # 支付相关 DTO
└── [module].py      # 其他业务模块 DTO
```

### 5.2 DTO 命名规范
- 创建：`{Resource}CreateDTO`
- 更新：`{Resource}UpdateDTO`
- 响应：`{Resource}ResponseDTO`
- 列表：`{Resource}ListResponseDTO`

### 5.3 DTO 示例（User）
```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

class UserCreateDTO(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    password: str = Field(..., min_length=8)

class UserUpdateDTO(BaseModel):
    email: Optional[str] = Field(None, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    full_name: Optional[str] = Field(None, max_length=100)

class UserResponseDTO(BaseModel):
    id: UUID
    username: str
    email: str
    full_name: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
```

---

## 6. 权限验证

### 6.1 JWT 认证
- **必须** 使用 JWT 进行身份验证
- **必须** 在 Authorization 头中传递 Bearer Token
- Multi-tenancy（MVP）：
  - tenant 必须从 JWT claims 获取（如 tenant_id、tenant_schema），不信任 client header/query 传入的 tenant 信息。

### 6.2 RBAC 权限系统
- **必须** 实现基于角色的访问控制
- **必须** 通过依赖注入进行权限检查
- Permission code format (MVP): `<resource><action>` (no colon).
- Examples: usersread, ordersconfirm, purchaseordersreceive


### 6.3 权限依赖示例
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def require_permission(permission: str):
    def permission_checker(credentials: HTTPAuthorizationCredentials = Depends(security)):
        token = credentials.credentials
        if not has_permission(token, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )
        return token
    return permission_checker

@router.get("/users")
async def get_users(_: str = Depends(require_permission("users:read"))):
    pass
```

---

## 7. 业务接口清单（MVP）

### 7.1 Sales（Orders）

#### POST /api/v1/orders
- Status code: 201 Created
- Permission: `orders:create`
- Description: create order (status=pending). 库存不扣减（MVP）。
- Request DTO:
```python
from pydantic import BaseModel, Field
from typing import List
from uuid import UUID

class OrderItemCreateDTO(BaseModel):
    product_id: UUID
    quantity: int = Field(..., ge=1)
    price: float = Field(..., gt=0)

class OrderCreateDTO(BaseModel):
    retailer_id: UUID
    items: List[OrderItemCreateDTO] = Field(..., min_length=1)
```

#### POST /api/v1/orders/{order_id}/confirm
- Request body: empty (no JSON body). Client should send no body (or `{}` if the client library forces a body, server must treat it as empty).
- Status code: 200 OK
- Permission: `orders:confirm`
- Description (MVP frozen): confirm 时扣减库存；库存不足则失败。
- Idempotency-Key: NOT required (but must be safe to retry).
- Success: order.status -> confirmed, inventory reduced, inventory_logs created.

Response example:
```json
{
  "success": true,
  "data": {
    "order_id": "11111111-1111-1111-1111-111111111111",
    "status": "confirmed"
  },
  "message": "Order confirmed",
  "timestamp": "2026-01-06T12:00:00Z"
}
```

Error cases:
- 409 INSUFFICIENT_INVENTORY
- 409 INVALID_STATE

Error example: INVALID_STATE
```json
{
  "success": false,
  "error": {
    "code": "INVALID_STATE",
    "message": "Order cannot be confirmed from current status",
    "details": [
      {
        "field": "status",
        "message": "Expected pending",
        "meta": {
          "order_id": "11111111-1111-1111-1111-111111111111",
          "current_status": "shipped"
        }
      }
    ]
  },
  "timestamp": "2026-01-06T12:00:00Z"
}
```

Error example: INSUFFICIENT_INVENTORY
```json
{
  "success": false,
  "error": {
    "code": "INSUFFICIENT_INVENTORY",
    "message": "Not enough inventory to confirm order",
    "details": [
      {
        "field": "items",
        "message": "Inventory insufficient for one or more items",
        "meta": {
          "order_id": "11111111-1111-1111-1111-111111111111",
          "product_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
          "requested_qty": 10,
          "available_qty": 3
        }
      }
    ]
  },
  "timestamp": "2026-01-06T12:00:00Z"
}
```

#### POST /api/v1/orders/{order_id}/ship
- Status code: 200 OK
- Permission: `orders:ship`
- Description (MVP frozen): 仅变更状态，不变更库存。

#### POST /api/v1/orders/{order_id}/cancel
- Status code: 200 OK
- Permission: `orders:cancel`
- Description: pending/confirmed 可取消；confirmed 取消需回滚库存并写 cancel 类型 InventoryLog。

---

### 7.2 Procurement（Purchase Orders / Inbound）

#### POST /api/v1/purchase-orders
- Status code: 201 Created
- Permission: `purchase_orders:create`
- Description: create purchase order (status=draft).

#### POST /api/v1/purchase-orders/{purchase_order_id}/submit
- Status code: 200 OK
- Permission: `purchase_orders:submit`
- Description: draft -> pending.

#### POST /api/v1/purchase-orders/{purchase_order_id}/receive
- Status code: 200 OK
- Permission: `purchase_orders:receive`
- Idempotency-Key: REQUIRED
- Description:
  - inbound receive increases inventory and creates inventory_logs (change_type=purchase) referencing purchase_order_id.

Request DTO:
```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID

-Rules (MVP):
- `received_at` is optional.
- If `received_at` is not provided, server MUST set `received_at = now()` (server current time).
- Response.data.received_at MUST always be returned (either client provided or server-generated).

class InboundReceiveItemDTO(BaseModel):
    product_id: UUID
    quantity: int = Field(..., ge=1)

class InboundReceiveDTO(BaseModel):
    received_at: Optional[datetime] = None
    items: List[InboundReceiveItemDTO] = Field(..., min_length=1)
```

Response example:
```json
{
  "success": true,
  "data": {
    "purchase_order_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "status": "received",
    "received_at": "2026-01-06T12:00:00Z",
    "inbound_log_count": 3
  },
  "message": "Inbound received",
  "timestamp": "2026-01-06T12:00:00Z"
}
```

Error cases:
- 400 MISSING_IDEMPOTENCY_KEY
- 409 IDEMPOTENCY_KEY_CONFLICT
- 409 INVALID_STATE

Error example: MISSING_IDEMPOTENCY_KEY
```json
{
  "success": false,
  "error": {
    "code": "MISSING_IDEMPOTENCY_KEY",
    "message": "Idempotency-Key header is required for inbound receive"
  },
  "timestamp": "2026-01-06T12:00:00Z"
}
```

Error example: IDEMPOTENCY_KEY_CONFLICT
```json
{
  "success": false,
  "error": {
    "code": "IDEMPOTENCY_KEY_CONFLICT",
    "message": "Idempotency-Key has been used with a different request body",
    "details": [
      {
        "field": "Idempotency-Key",
        "message": "Conflicting payload for the same key",
        "meta": {
          "purchase_order_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        }
      }
    ]
  },
  "timestamp": "2026-01-06T12:00:00Z"
}
```

Error example: INVALID_STATE
```json
{
  "success": false,
  "error": {
    "code": "INVALID_STATE",
    "message": "Purchase order cannot be received from current status",
    "details": [
      {
        "field": "status",
        "message": "Expected pending",
        "meta": {
          "purchase_order_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
          "current_status": "draft"
        }
      }
    ]
  },
  "timestamp": "2026-01-06T12:00:00Z"
}
```

---

### 7.3 Finance（Payments）

#### POST /api/v1/payments
- Status code: 201 Created
- Permission: `payments:create`
- Description: create payment for an order.

Request DTO:
```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID

PaymentMethod = Literal["cash", "transfer", "credit"]

class PaymentCreateDTO(BaseModel):
    order_id: UUID
    amount: float = Field(..., gt=0)
    method: PaymentMethod
    transaction_id: Optional[str] = None
    paid_at: Optional[datetime] = None
```

MVP rules:
- If method == "transfer":
  - Idempotency-Key: REQUIRED
  - transaction_id: REQUIRED

Response example:
```json
{
  "success": true,
  "data": {
    "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "order_id": "11111111-1111-1111-1111-111111111111",
    "amount": 100.0,
    "method": "transfer",
    "transaction_id": "MPESA_ABC_123",
    "paid_at": "2026-01-06T12:00:00Z"
  },
  "message": "Payment created",
  "timestamp": "2026-01-06T12:00:00Z"
}
```

Error cases:
- 400 MISSING_IDEMPOTENCY_KEY (transfer)
- 422 VALIDATION_ERROR (transfer missing transaction_id)
- 409 IDEMPOTENCY_KEY_CONFLICT (transfer)
- 409 DUPLICATE_TRANSACTION_ID (transfer, recommended)

Error example: VALIDATION_ERROR (missing transaction_id)
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "输入数据验证失败",
    "details": [
      {
        "field": "transaction_id",
        "message": "Field required for transfer payments"
      }
    ]
  },
  "timestamp": "2026-01-06T12:00:00Z"
}
```

Error example: IDEMPOTENCY_KEY_CONFLICT
```json
{
  "success": false,
  "error": {
    "code": "IDEMPOTENCY_KEY_CONFLICT",
    "message": "Idempotency-Key has been used with a different request body",
    "details": [
      {
        "field": "Idempotency-Key",
        "message": "Conflicting payload for the same key",
        "meta": {
          "order_id": "11111111-1111-1111-1111-111111111111"
        }
      }
    ]
  },
  "timestamp": "2026-01-06T12:00:00Z"
}
```

Error example: DUPLICATE_TRANSACTION_ID
```json
{
  "success": false,
  "error": {
    "code": "DUPLICATE_TRANSACTION_ID",
    "message": "transaction_id already exists",
    "details": [
      {
        "field": "transaction_id",
        "message": "Duplicate transfer transaction",
        "meta": {
          "transaction_id": "MPESA_ABC_123"
        }
      }
    ]
  },
  "timestamp": "2026-01-06T12:00:00Z"
}
```

---

## 8. 异常处理

### 8.1 全局异常处理器
**必须** 实现以下异常处理：

```python
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from fastapi.responses import JSONResponse
from datetime import datetime

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "输入数据验证失败",
                "details": exc.errors()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=409,
        content={
            "success": False,
            "error": {
                "code": "INTEGRITY_ERROR",
                "message": "数据完整性约束违反"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    )
```

### 8.2 自定义异常
```python
class BusinessException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
```

---

## 9. API 版本管理

### 9.1 版本策略
- **当前版本：** v1
- **路径前缀：** `/api/v1/`
- **向后兼容：** 新版本必须保持向后兼容

### 9.2 版本升级
- 破坏性变更需要新版本号
- 旧版本保持至少 6 个月支持期

---

## 10. 文档要求

### 10.1 Swagger 文档
- **必须** 在 `/docs` 提供 Swagger UI
- **必须** 在 `/redoc` 提供 ReDoc 文档

### 10.2 API 描述
```python
@router.post("/users", response_model=UserResponseDTO)
async def create_user(user_data: UserCreateDTO, db: Session = Depends(get_db)):
    """
    创建新用户

    - **username**: 用户名，3-50字符
    - **email**: 邮箱地址，必须唯一
    - **password**: 密码，最少8字符
    """
    pass
```

---

## 11. 测试要求

### 11.1 API 测试覆盖
**每个 API 必须包含以下测试：**
- 正常流程测试
- 错误参数测试
- 权限验证测试
- 边界条件测试
- 幂等测试（仅对强制 Idempotency-Key 的接口）

### 11.2 测试示例
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_user_success(client: AsyncClient):
    response = await client.post("/api/v1/users", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123"
    })
    assert response.status_code == 201
    assert response.json()["success"] is True

@pytest.mark.asyncio
async def test_inbound_receive_requires_idempotency_key(client: AsyncClient):
    response = await client.post(
        "/api/v1/purchase-orders/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/receive",
        json={"items": [{"product_id": "cccccccc-cccc-cccc-cccc-cccccccccccc", "quantity": 1}]}
    )
    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "MISSING_IDEMPOTENCY_KEY"
```

### 11.3 测试说明
- 每个 API 至少包含以下测试用例：
  - 正常流程
  - 非法参数 / 校验失败
  - 权限不足
  - 边界值
  - 对强制 Idempotency-Key 的接口，必须包含幂等行为测试

---

## 12. 强制要求
1. **禁止硬编码字符串**  
   - 所有错误消息、错误码、业务状态码必须定义为常量或枚举，集中管理，便于前后端对齐与国际化。
2. **必须使用类型注解**  
   - 所有 FastAPI 路由处理函数、service 层函数的参数和返回值必须有完整的 Python 类型注解。
3. **列表 API 必须分页**  
   - 所有返回列表的 API 必须支持统一的分页参数（page, size），禁止返回“全量列表”。
4. **必须验证权限**  
   - 所有需要认证的 API 必须通过 RBAC 权限检查（`require_permission("<code>")`），禁止“临时跳过权限验证”。
5. **必须有异常处理链路**  
   - 实现全局异常处理器（validation、IntegrityError、BusinessException 等），确保返回统一格式的错误响应。

---

**重要提醒：** 所有与此规范不符的 API 实现必须重写，确保完全遵循以上标准。
```

