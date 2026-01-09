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

## 强制要求

1. **所有模型** 必须继承 `BaseModel`
2. **所有路由** 必须使用类型注解
3. **所有 CRUD** 必须继承 `CRUDBase`
4. **所有配置** 必须通过 Pydantic Settings
5. **所有数据库操作** 必须通过 Alembic

## 多租户补充要求

1. 登录：要求传 tenant_code → 查 public.wholesalers → 签发含 tenant_id/tenant_schema 的 JWT。
2. 每个请求：在 get_db 里 SET LOCAL search_path（事务内），保证 ORM 自动落到 tenant schema。
3. RBAC：实现 has_permission(token, permission_code)，并在每个路由挂 Depends(require_permission(...))
4. 每个测试会话创建独立 tenant schema（t_test_xxx），并在请求 token 里写入对应 tenant_schema

---

**重要提醒：** 所有后端代码生成任务必须明确引用此契约，确保遵循以上规范。