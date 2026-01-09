# Mpango ERP System

**版本：** 1.0.0  
**作者：** Jeff Lee + GPT-5  
**描述：** 基于 Spec-Kit 构建的批发零售 ERP 系统，用于支持非洲市场的多租户数字化运营。

## 架构概览

- **当前阶段**: 模块化单体架构 (FastAPI + React + PostgreSQL)
- **多租户**: Schema-per-tenant 策略
- **认证**: JWT + RBAC 权限控制

## 技术栈

### 后端
- **框架**: FastAPI (Python 3.11+)
- **数据库**: PostgreSQL 15+ 
- **ORM**: SQLAlchemy 2.0 (async)
- **迁移**: Alembic
- **缓存**: Redis + Celery

### 前端
- **框架**: React 18 + Vite + TypeScript
- **样式**: TailwindCSS
- **状态管理**: Zustand
- **表单**: React Hook Form + Zod

## 快速启动

```bash
# 启动数据库和Redis
docker compose up -d postgres redis

# 启动后端 (端口8000)
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload

# 启动前端 (端口5173，避免3000端口冲突)
cd frontend
npm install
npm run dev
```

## 模块说明

- **认证模块 (auth)**: JWT认证、多租户登录
- **用户管理 (users)**: RBAC权限、角色管理
- **销售管理 (sales)**: 零售商下单、订单跟踪、批发商发货管理
- **客户关系管理 (CRM)**: 批发商邀请、客户档案、信用额度管理  
- **库存管理 (inventory)**: 库存同步、商品录入、库存调整
- **采购管理 (procurement)**: 供应商管理、采购单、入库记录
- **财务管理 (finance)**: 支付记录、账单管理

## 多租户架构

- **租户标识**: tenant_code (登录用) + tenant_schema (数据隔离)
- **数据隔离**: 每个批发商独立的PostgreSQL schema
- **权限控制**: 基于JWT claims的租户级RBAC

## 开发规范

请严格遵循 `docs/contracts/` 目录下的开发契约文档。