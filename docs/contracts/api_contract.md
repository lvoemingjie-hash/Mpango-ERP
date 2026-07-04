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
- Create（POST 创建资源）：**201 Created**
- Action（POST 执行动作，如 confirm/receive/ship/cancel/submit）：**200 OK**
- Update（PUT 更新资源）：**200 OK**
- Delete（DELETE 删除资源）：**204 No Content**

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

### 2.3 Idempotency（MVP）
#### 2.4.1 Header
- Header: `Idempotency-Key: <string>`
- Constraints: 1-64 chars, 推荐使用 UUIDv4

#### 2.4.2 强制要求 Idempotency-Key 的接口（MVP）
1) 入库确认（Inbound receive / Goods receipt）
2) 转账收款创建（Transfer payment create，method=transfer）
3) payment rules
   - transaction_id MUST store M-Pesa reference.
   - Payment creation MUST be idempotent by transaction_id.
   - **Method Mapping**: Use `method: "transfer"` for all mobile money transactions (e.g., M-Pesa, Airtel Money).
   - **Transaction ID**: The `transaction_id` field is MANDATORY for transfers. It must store the external provider's confirmation code (e.g., "QWE12345").
   - The backend MUST enforce uniqueness of `transaction_id` within the tenant scope.
   - Duplicate codes MUST return `409 CONFLICT` with `DUPLICATETRANSACTIONID`.
   - **Idempotency**: The `Idempotency-Key` header is REQUIRED for all transfer payments to prevent double-charging on network retries.


---

## 3. 响应格式规范

### 3.1 成功响应格式
```json
{
  "success": true,
  "data": {},
  "message": "操作成功",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 3.2 分页响应格式
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
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### 3.3 错误响应格式
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

### 3.4 业务错误码（MVP）
- 400 `MISSING_IDEMPOTENCY_KEY`
- 409 `IDEMPOTENCY_KEY_CONFLICT`
- 409 `INVALID_STATE`
- 409 `INSUFFICIENT_INVENTORY`
- 409 `DUPLICATE_TRANSACTION_ID`
- 403 `PERMISSION_DENIED`

---

## 4. 权限验证

### 4.1 JWT 认证
- **必须** 使用 JWT 进行身份验证
- **必须** 在 Authorization 头中传递 Bearer Token
- tenant 必须从 JWT claims 获取

### 4.2 RBAC 权限系统
- **必须** 实现基于角色的访问控制
- Permission code format: `<resource>:<action>`
- Examples: users:read, orders:confirm

---

## 5. 业务接口清单（MVP）

### 5.1 Sales（Orders）
- POST /api/v1/orders (201, orders:create)
- POST /api/v1/orders/{order_id}/confirm (200, orders:confirm)
- POST /api/v1/orders/{order_id}/ship (200, orders:ship)
- POST /api/v1/orders/{order_id}/cancel (200, orders:cancel)

### 5.2 Procurement
- POST /api/v1/purchase-orders (201, purchase_orders:create)
- POST /api/v1/purchase-orders/{id}/submit (200, purchase_orders:submit)
- POST /api/v1/purchase-orders/{id}/receive (200, purchase_orders:receive, Idempotency-Key REQUIRED)

### 5.3 Finance
- POST /api/v1/orders/{order_id}/pay (200, payments:create)
- POST /api/v1/payments is legacy-disabled and returns 409 `PAYMENT_WRITE_PATH_DISABLED`.

---

## 6. 强制要求

1. **禁止硬编码字符串** - 所有错误消息、错误码必须定义为常量或枚举
2. **必须使用类型注解** - 所有函数必须有完整的 Python 类型注解
3. **列表 API 必须分页** - 禁止返回"全量列表"
4. **必须验证权限** - 所有需要认证的 API 必须通过 RBAC 权限检查
5. **必须有异常处理链路** - 实现全局异常处理器

---

**重要提醒：** 所有与此规范不符的 API 实现必须重写，确保完全遵循以上标准。
