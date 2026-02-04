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
      - "5173:5173"
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      - VITE_API_URL=http://localhost:8000/api/v1
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

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

RUN pip install poetry

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

COPY pyproject.toml poetry.lock ./

RUN poetry install --only=main && rm -rf $POETRY_CACHE_DIR

COPY . .

RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.2 要求
- **必须** 使用 Poetry 管理依赖
- **必须** 优化构建缓存
- **必须** 使用非 root 用户运行
- **必须** 支持健康检查端点

## 3. Frontend Dockerfile

### 3.1 多阶段构建
```dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build

FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## 4. 环境变量模板

### 4.1 .env.example
```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/mpango_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=mpango_db

SECRET_KEY=your-super-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

DEBUG=true
ENVIRONMENT=development

VITE_API_URL=http://localhost:8000/api/v1
```

## 5. 开发环境要求

### 5.1 启动命令
```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
docker-compose up --build
```

### 5.2 访问地址
- **前端应用：** http://localhost:5173
- **后端 API：** http://localhost:8000
- **API 文档：** http://localhost:8000/docs
- **数据库：** localhost:5432

## 6. 强制要求

1. **所有服务** 必须有健康检查
2. **所有配置** 必须通过环境变量
3. **所有密码** 必须使用强密码
4. **所有镜像** 必须优化大小
5. **所有服务** 必须支持优雅关闭

---

**重要提醒：** 所有 Docker 相关实现必须遵守此契约，确保部署的一致性和可靠性。
