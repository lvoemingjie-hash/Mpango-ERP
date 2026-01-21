# 生产部署 Runbook

**目标**: 提供完整的生产环境操作指南，确保即使在半睡眠状态下也能安全操作。

**前提**: Docker Compose 环境正常，所有服务已部署。

---

## 快速状态检查

### 查看当前版本和状态

```bash
# 查看应用版本
curl http://localhost:8000/ | jq .version

# 查看健康状态
curl http://localhost:8000/health

# 查看容器状态
docker compose ps

# 查看最近的 git tag
git describe --tags --abbrev=0
```

---

## 容器管理

### 重启单个服务

```bash
# 重启 backend
docker compose restart backend

# 重启 database
docker compose restart postgres

# 重启所有服务
docker compose restart
```

### 停止/启动服务

```bash
# 停止所有服务 (维护模式)
docker compose down

# 启动所有服务
docker compose up -d

# 启动特定服务
docker compose up -d backend
```

### 查看服务日志

```bash
# 查看 backend 最近 100 行日志
docker compose logs --tail=100 backend

# 实时查看日志
docker compose logs -f backend

# 查看今天的所有错误
docker compose logs --since today backend | grep ERROR

# 按 request_id 查看特定请求
docker compose logs backend | jq 'select(.request_id == "your-request-id")'
```

---

## 备份和恢复

### 手动触发备份

```bash
# 执行备份脚本
./ai-ledger/ops/backup_postgres.sh /opt/mpango/backups

# 验证备份成功
ls -la /opt/mpango/backups/mpango_backup_$(date +%Y%m%d)_*.sql
```

### 恢复数据库

```bash
# 停止应用
docker compose down

# 恢复备份 (替换 YOUR_BACKUP_FILE.sql)
docker exec -i mpango_postgres pg_restore \
    --host=postgres \
    --port=5432 \
    --username=mpango \
    --dbname=mpango_erp \
    --no-password \
    --clean \
    --create \
    < /opt/mpango/backups/YOUR_BACKUP_FILE.sql

# 重启应用
docker compose up -d
```

---

## 故障排查

### /health 返回 500

**症状**: `curl http://localhost:8000/health` 返回 500 错误

**检查步骤**:

```bash
# 1. 查看健康检查日志
docker compose logs --tail=20 backend | grep health

# 2. 检查数据库连接
docker exec mpango_postgres pg_isready -U mpango -d mpango_erp

# 3. 检查应用进程
docker compose exec backend ps aux | grep uvicorn

# 4. 查看完整错误日志
docker compose logs --tail=50 backend | jq 'select(.levelname == "ERROR")'

# 可能的解决方案:
# - 重启 backend: docker compose restart backend
# - 如果数据库问题: docker compose restart postgres
# - 如果是代码错误: 检查最新日志，联系开发团队
```

### Backend 容器 Exit 1

**症状**: `docker compose ps` 显示 backend 状态为 Exit 1

**检查步骤**:

```bash
# 1. 查看退出原因
docker compose logs backend | tail -20

# 2. 检查启动日志中的错误
docker compose logs backend | grep -A5 -B5 "ERROR\|Exception\|Failed"

# 3. 验证环境变量
docker compose exec backend env | grep -E "(DATABASE_URL|SECRET_KEY|REDIS_URL)"

# 4. 检查数据库可用性
docker compose exec postgres pg_isready -U mpango -d mpango_erp

# 常见原因和解决方案:
# - 数据库连接失败: 等待 postgres 完全启动 (healthcheck 通过)
# - 环境变量缺失: 检查 secrets/prod.env 文件
# - 端口冲突: 检查 8000 端口是否被占用 (netstat -tlnp | grep 8000)
# - 依赖问题: 检查 Docker 构建日志
```

### 高错误率

**症状**: 监控显示错误率 > 5%

**检查步骤**:

```bash
# 1. 查看最近 1 小时错误
docker compose logs --since 1h backend | jq 'select(.levelname == "ERROR") | .message' | sort | uniq -c | sort -nr

# 2. 按租户查看错误分布
docker compose logs --since 1h backend | jq -r 'select(.levelname == "ERROR") | .tenant_id' | sort | uniq -c | sort -nr

# 3. 检查数据库性能
docker compose exec postgres psql -U mpango -d mpango_erp -c "SELECT * FROM pg_stat_activity;"

# 4. 检查磁盘空间
df -h
docker system df

# 可能的解决方案:
# - 数据库连接池耗尽: 重启 backend
# - 磁盘空间不足: 清理日志/备份文件
# - 特定租户问题: 联系该租户技术支持
```

### 内存/CPU 使用率高

**检查步骤**:

```bash
# 查看容器资源使用
docker stats mpango_backend mpango_postgres mpango_redis

# 查看应用进程
docker compose exec backend ps aux | head -10

# 检查数据库连接数
docker compose exec postgres psql -U mpango -d mpango_erp -c "SELECT count(*) FROM pg_stat_activity;"

# 可能的解决方案:
# - 重启服务: docker compose restart
# - 如果持续高: 检查应用代码性能问题
```

---

## 日常维护

### 日志轮转

```bash
# 查看日志大小
docker compose logs backend | wc -l

# 如果日志过大，重启服务清理 (Docker 会清理旧日志)
docker compose restart backend
```

### 磁盘清理

```bash
# 查看磁盘使用
df -h

# 清理 Docker 系统
docker system prune -f

# 清理旧备份 (保留 7 天)
find /opt/mpango/backups -name "*.sql" -type f -mtime +7 -delete
```

---

## 紧急情况处理

### 数据丢失

1. **立即停止写入**: `docker compose down`
2. **从备份恢复**: 参考"恢复数据库"步骤
3. **验证数据完整性**
4. **通知相关方**

### 安全事件

1. **隔离受影响服务**: `docker compose down`
2. **更换密钥**: 更新 secrets/prod.env
3. **审计日志**: 检查入侵痕迹
4. **通知安全团队**

### 完全重建

```bash
# 完全清理并重建
docker compose down -v  # 删除卷
docker system prune -a  # 清理所有
git pull  # 获取最新代码
docker compose up -d --build
```

---

## 联系和升级

- **开发团队**: 联系核心开发人员处理代码相关问题
- **基础设施**: 联系 OPS 团队处理环境相关问题
- **紧急联系**: 24/7 应急响应电话

**记住**: 操作前备份，操作后验证，遇到问题不要慌张，按步骤检查。
