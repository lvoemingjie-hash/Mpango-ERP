# Mpango ERP Project Structure

```
C:\Users\Jeff0\kiro-mpango-erp\
├── README.md                           # 项目说明文档
├── docker-compose.yml                  # Docker编排配置
├── PROJECT_STRUCTURE.md               # 项目结构说明
│
├── docs/                              # 文档目录
│   └── contracts/                     # 开发契约文档
│       ├── architecture_contract.md   # 架构契约
│       ├── Boot contract.md           # 系统级生产契约（L0.5），约束 Backend / Frontend / Ops / Test / AI Agent
│       ├── database_contract.md       # 数据库契约
│       ├── backend_contract.md        # 后端开发契约
│       ├── frontend_contract.md       # 前端开发契约
│       ├── multi_tenancy_spec.md      # 多租户规范
│       └── rbac_matrix.md             # RBAC权限矩阵
│
├── backend/                           # 后端API服务
│   ├── main.py                        # FastAPI主入口
│   ├── requirements.txt               # Python依赖
│   ├── Dockerfile                     # 后端Docker配置
│   ├── .env                          # 环境变量
│   ├── .env.example                  # 环境变量示例
│   ├── alembic.ini                   # Alembic配置
│   │
│   ├── core/                         # 核心模块
│   │   ├── __init__.py
│   │   ├── config.py                 # 配置管理
│   │   ├── security.py               # 安全相关（JWT、密码）
│   │   └── exceptions.py             # 异常定义
│   │
│   ├── database/                     # 数据库层
│   │   ├── __init__.py
│   │   ├── base.py                   # 基础模型类
│   │   └── session.py                # 数据库会话管理
│   │
│   ├── models/                       # SQLAlchemy模型
│   │   ├── __init__.py
│   │   ├── base.py                   # 基础模型
│   │   ├── wholesaler.py             # 批发商模型（租户）
│   │   └── user.py                   # 用户、角色、权限模型
│   │
│   ├── schemas/                      # Pydantic数据模型
│   │   ├── __init__.py
│   │   ├── auth.py                   # 认证相关Schema
│   │   ├── user.py                   # 用户相关Schema
│   │   └── wholesaler.py             # 批发商Schema
│   │
│   ├── crud/                         # 数据库操作层
│   │   ├── __init__.py
│   │   ├── base.py                   # 基础CRUD类
│   │   ├── user.py                   # 用户CRUD操作
│   │   └── wholesaler.py             # 批发商CRUD操作
│   │
│   ├── api/                          # API路由
│   │   ├── __init__.py
│   │   ├── dependencies.py           # 依赖注入（认证、权限）
│   │   └── v1/                       # API v1版本
│   │       ├── __init__.py
│   │       ├── auth.py               # 认证路由
│   │       └── users.py              # 用户管理路由
│   │
│   ├── alembic/                      # 数据库迁移
│   │   ├── env.py                    # Alembic环境配置
│   │   ├── script.py.mako            # 迁移脚本模板
│   │   └── versions/                 # 迁移版本文件
│   │
│   └── tests/                        # 测试目录
│
├── frontend/                         # 前端React应用
│   ├── package.json                  # Node.js依赖
│   ├── vite.config.ts               # Vite配置
│   ├── tsconfig.json                # TypeScript配置
│   ├── tailwind.config.js           # TailwindCSS配置
│   ├── postcss.config.js            # PostCSS配置
│   ├── .eslintrc.cjs                # ESLint配置
│   ├── .prettierrc                  # Prettier配置
│   ├── Dockerfile                   # 前端Docker配置
│   ├── .env                         # 环境变量
│   ├── index.html                   # HTML入口
│   │
│   ├── public/                      # 静态资源
│   │   └── vite.svg                 # Vite图标
│   │
│   └── src/                         # 源代码
│       ├── main.tsx                 # React入口
│       ├── App.tsx                  # 根组件
│       │
│       ├── components/              # 组件目录
│       │   ├── auth/                # 认证组件
│       │   │   └── ProtectedRoute.tsx
│       │   └── layout/              # 布局组件
│       │       ├── Layout.tsx       # 主布局
│       │       ├── Header.tsx       # 头部导航
│       │       └── Sidebar.tsx      # 侧边栏
│       │
│       ├── pages/                   # 页面组件
│       │   ├── auth/                # 认证页面
│       │   │   └── LoginPage.tsx    # 登录页
│       │   ├── users/               # 用户管理页面
│       │   │   └── UsersPage.tsx    # 用户列表页
│       │   └── DashboardPage.tsx    # 仪表板页面
│       │
│       ├── services/                # API服务
│       │   ├── api.ts               # Axios配置
│       │   └── authService.ts       # 认证服务
│       │
│       ├── stores/                  # Zustand状态管理
│       │   └── authStore.ts         # 认证状态
│       │
│       ├── types/                   # TypeScript类型定义
│       │   └── auth.ts              # 认证相关类型
│       │
│       ├── router/                  # 路由配置
│       │   └── index.tsx            # 路由定义
│       │
│       └── styles/                  # 样式文件
│           └── globals.css          # 全局样式
│
├── database/                        # 数据库相关
│   └── init.sql                     # 数据库初始化脚本
│
└── scripts/                         # 脚本目录
    ├── setup.sh                     # 项目设置脚本
    └── dev.sh                       # 开发环境启动脚本
```

## 技术栈

### 后端
- **框架**: FastAPI (Python 3.11+)
- **数据库**: PostgreSQL 15+
- **ORM**: SQLAlchemy 2.0 (async)
- **迁移**: Alembic
- **认证**: JWT + RBAC
- **缓存**: Redis
- **任务队列**: Celery

### 前端
- **框架**: React 18 + Vite
- **语言**: TypeScript
- **样式**: TailwindCSS
- **状态管理**: Zustand
- **路由**: React Router v6
- **表单**: React Hook Form + Zod
- **UI组件**: Headless UI

### 基础设施
- **容器化**: Docker + Docker Compose
- **数据库**: PostgreSQL 15
- **缓存**: Redis 7
- **反向代理**: Nginx (生产环境)

## 多租户架构

- **策略**: Schema-per-tenant
- **租户标识**: tenant_code (登录) + tenant_schema (数据隔离)
- **权限控制**: 基于JWT claims的RBAC系统
- **数据隔离**: 每个批发商独立的PostgreSQL schema

## 端口配置

- **后端API**: http://localhost:8000
- **前端应用**: http://localhost:5173 (避免3000端口冲突)
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **API文档**: http://localhost:8000/docs
