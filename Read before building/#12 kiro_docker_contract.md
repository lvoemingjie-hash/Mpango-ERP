# Mpango ERP – Docker Contract

**Version:** 1.0  
**Owner:** Jeff + ChatGPT + GLM  
**Target:** KIRO Code + DevOps  
**Stack:** FastAPI + React + PostgreSQL + Nginx + Docker Compose

---

## 1. docker-compose.yml

### 1.1 完整配置
```yaml
version: '3.8'

services:
  backend:
    build: 
      context: ./backend
      dockerfile: Dockerfile
    container_name: mpango_backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/mpango_db
      - SECRET_KEY=your-secret-key-here
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./backend:/app
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: mpango_frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      - REACT_APP_API_URL=http://localhost:8000/api/v1
    command: npm run dev

  db:
    image: postgres:15-alpine
    container_name: mpango_db
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=mpango_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  nginx:
    image: nginx:alpine
    container_name: mpango_nginx
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - backend
      - frontend

volumes:
  postgres_data:
```

### 1.2 关键要求
- **必须** 包含健康检查
- **必须** 设置服务依赖关系
- **必须** 支持热重载（开发环境）
- **必须** 使用环境变量配置

## 2. Backend Dockerfile

### 2.1 生产环境 Dockerfile
```dockerfile
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Poetry
RUN pip install poetry

# 配置 Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# 复制依赖文件
COPY pyproject.toml poetry.lock ./

# 安装依赖
RUN poetry install --only=main && rm -rf $POETRY_CACHE_DIR

# 复制应用代码
COPY . .

# 创建非root用户
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.2 开发环境 Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Poetry
RUN pip install poetry

# 配置 Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1

# 复制依赖文件
COPY pyproject.toml poetry.lock ./

# 安装所有依赖（包括开发依赖）
RUN poetry install

# 复制应用代码
COPY . .

EXPOSE 8000

# 开发环境启动命令（支持热重载）
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### 2.3 要求
- **必须** 使用 Poetry 管理依赖
- **必须** 优化构建缓存
- **必须** 使用非 root 用户运行
- **必须** 支持健康检查端点

## 3. Frontend Dockerfile

### 3.1 多阶段构建
```dockerfile
# 构建阶段
FROM node:18-alpine AS builder

WORKDIR /app

# 复制 package 文件
COPY package*.json ./

# 安装依赖
RUN npm ci --only=production

# 复制源代码
COPY . .

# 构建应用
RUN npm run build

# 生产阶段
FROM nginx:alpine AS production

# 复制构建结果
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### 3.2 开发环境 Dockerfile
```dockerfile
FROM node:18-alpine

WORKDIR /app

# 复制 package 文件
COPY package*.json ./

# 安装依赖
RUN npm install

# 复制源代码
COPY . .

EXPOSE 3000

# 开发服务器
CMD ["npm", "run", "dev"]
```

### 3.3 要求
- **必须** 使用多阶段构建（生产环境）
- **必须** 优化镜像大小
- **必须** 支持热重载（开发环境）

## 4. PostgreSQL 设置

### 4.1 环境变量
```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=mpango_db
```

### 4.2 初始化脚本 (`database/init.sql`)
```sql
-- 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 创建基础表结构（如果需要）
-- 注意：主要的表结构应该通过 Alembic 管理
```

### 4.3 要求
- **必须** 使用持久化存储
- **必须** 配置健康检查
- **必须** 设置合理的连接参数

## 5. Nginx 配置

### 5.1 nginx.conf
```nginx
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }

    upstream frontend {
        server frontend:3000;
    }

    server {
        listen 80;
        server_name localhost;

        # 前端路由
        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # API 路由
        location /api/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # CORS 头部
            add_header Access-Control-Allow-Origin *;
            add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS";
            add_header Access-Control-Allow-Headers "Content-Type, Authorization";
        }

        # 处理 OPTIONS 请求
        location ~ ^/api/.*$ {
            if ($request_method = OPTIONS) {
                add_header Access-Control-Allow-Origin *;
                add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS";
                add_header Access-Control-Allow-Headers "Content-Type, Authorization";
                return 204;
            }
        }
    }
}
```

### 5.2 要求
- **必须** 正确转发请求头
- **必须** 处理 CORS
- **必须** 配置合理的超时时间

## 6. 环境变量模板

### 6.1 .env.example
```env
# 数据库配置
DATABASE_URL=postgresql://postgres:password@localhost:5432/mpango_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=mpango_db

# JWT 配置
SECRET_KEY=your-super-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# 应用配置
DEBUG=true
ENVIRONMENT=development

# 前端配置
REACT_APP_API_URL=http://localhost:8000/api/v1
```

## 7. 开发环境要求

### 7.1 启动命令
```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重建镜像
docker-compose up --build
```

### 7.2 访问地址
- **前端应用：** http://localhost:3000
- **后端 API：** http://localhost:8000
- **API 文档：** http://localhost:8000/docs
- **数据库：** localhost:5432

## 8. 生产环境要求

### 8.1 安全配置
- **必须** 使用强密码
- **必须** 配置 HTTPS
- **必须** 限制网络访问
- **必须** 定期备份数据

### 8.2 性能优化
- **必须** 配置资源限制
- **必须** 启用日志轮转
- **必须** 监控服务状态

## 9. 部署要求

### 9.1 云平台支持
- **计划支持：** AWS, Azure, GCP
- **容器编排：** Kubernetes (未来)
- **CI/CD：** GitHub Actions

### 9.2 监控和日志
- **必须** 集成健康检查
- **必须** 配置日志收集
- **必须** 设置告警机制

## 10. 强制要求

1. **所有服务** 必须有健康检查
2. **所有配置** 必须通过环境变量
3. **所有密码** 必须使用强密码
4. **所有镜像** 必须优化大小
5. **所有服务** 必须支持优雅关闭

---

**重要提醒：** 所有 Docker 相关实现必须遵守此契约，确保部署的一致性和可靠性。