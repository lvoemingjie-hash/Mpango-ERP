# PostgreSQL 自动备份配置指南

## 概述

基于当前 Docker/Postgres 布局，使用 cron + docker exec pg_dump 实现每日自动备份。

## 前提条件

1. Docker Compose 运行状态正常
2. 备份脚本已放置在宿主机: `ai-ledger/ops/backup_postgres.sh`
3. 脚本有执行权限: `chmod +x ai-ledger/ops/backup_postgres.sh`

## 备份目录配置

### 推荐目录结构

```bash
# 创建备份目录 (宿主机)
sudo mkdir -p /opt/mpango/backups
sudo chown $(whoami):$(whoami) /opt/mpango/backups

# 或使用项目相对目录
mkdir -p ./backups
```

### Docker Compose 挂载 (可选)

如果需要从容器外部访问备份，可以在 docker-compose.yml 添加 volume:

```yaml
volumes:
  - ./backups:/opt/mpango/backups
  # 其他 volumes...
```

## Cron 配置

### Linux/macOS

```bash
# 编辑 crontab
crontab -e

# 添加每日凌晨 2:00 执行备份
0 2 * * * /path/to/mpango-erp/ai-ledger/ops/backup_postgres.sh /opt/mpango/backups >> /var/log/mpango_backup.log 2>&1

# 示例输出:
0 2 * * * /home/user/mpango-erp/ai-ledger/ops/backup_postgres.sh /opt/mpango/backups >> /var/log/mpango_backup.log 2>&1
```

### Windows Task Scheduler

```powershell
# 创建定时任务 (每日凌晨 2:00)
schtasks /create /tn "MpangoDailyBackup" /tr "powershell.exe -ExecutionPolicy Bypass -File 'C:\path\to\mpango-erp\ai-ledger\ops\backup_postgres.sh' 'C:\backups'" /sc daily /st 02:00 /ru System
```

## 备份文件管理

### 自动清理

脚本默认保留最近 7 天的备份文件。

### 手动清理

```bash
# 查看备份文件
ls -la /opt/mpango/backups/

# 删除特定备份
rm /opt/mpango/backups/mpango_backup_20231201_020000.sql

# 删除 30 天前的备份
find /opt/mpango/backups -name "mpango_backup_*.sql" -type f -mtime +30 -delete
```

## 恢复步骤

### 场景 1: 完全恢复 (开发/测试环境)

```bash
# 停止应用
docker compose down

# 删除并重新创建数据库容器 (会丢失所有数据)
docker compose rm -f postgres
docker volume rm mpango_postgres_data  # 如果需要完全重置

# 重启数据库
docker compose up -d postgres

# 等待数据库就绪
sleep 30

# 恢复备份
docker exec -i mpango_postgres pg_restore \
    --host=postgres \
    --port=5432 \
    --username=mpango \
    --dbname=mpango_erp \
    --no-password \
    --clean \
    --create \
    < /opt/mpango/backups/mpango_backup_20231201_020000.sql

# 重启应用
docker compose up -d
```

### 场景 2: 恢复到新数据库 (生产环境安全恢复)

```bash
# 创建新的数据库容器用于恢复测试
docker run -d --name postgres_restore \
    -e POSTGRES_DB=mpango_erp_restore \
    -e POSTGRES_USER=mpango \
    -e POSTGRES_PASSWORD=MpangoDBV0.1.2 \
    -p 5433:5432 \
    postgres:15

# 恢复到新数据库
docker exec -i postgres_restore pg_restore \
    --host=localhost \
    --port=5432 \
    --username=mpango \
    --dbname=mpango_erp_restore \
    --no-password \
    --clean \
    --create \
    < /opt/mpango/backups/mpango_backup_20231201_020000.sql

# 验证恢复成功后，停止生产数据库并切换
# (具体步骤根据生产环境而定)
```

## 监控和告警

### 检查备份状态

```bash
# 查看最近备份日志
tail -20 /var/log/mpango_backup.log

# 检查备份文件存在性
ls -la /opt/mpango/backups/mpango_backup_$(date +%Y%m%d)_*.sql

# 检查备份文件大小 (确保不是空的)
du -h /opt/mpango/backups/mpango_backup_$(date +%Y%m%d)_*.sql
```

### 失败处理

如果备份失败，检查:
1. Docker 容器运行状态
2. 数据库连接配置
3. 磁盘空间
4. 日志文件权限

## 安全考虑

- 备份文件包含敏感数据，妥善保管
- 生产环境建议加密备份文件
- 定期验证备份可恢复性
- 考虑异地备份存储
