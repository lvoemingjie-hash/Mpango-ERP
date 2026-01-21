# 最小可用监控方案

**目的**: 在不引入新服务的情况下，通过现有 Docker / 日志 / health 实现基础观测。

## 1. Uptime 监控

### 方法: Cron + curl 检查

使用系统 cron 定时检查 backend 健康状态，记录到日志文件。

#### Cron 配置示例 (Linux/macOS)

```bash
# 编辑 crontab
crontab -e

# 每分钟检查一次 /health
* * * * * curl -f -s http://localhost:8000/health > /dev/null 2>&1 && echo "$(date): HEALTH_OK" >> /var/log/mpango_uptime.log || echo "$(date): HEALTH_FAIL" >> /var/log/mpango_uptime.log
```

#### Windows Task Scheduler 示例

```powershell
# 创建定时任务 (每分钟执行)
schtasks /create /tn "MpangoHealthCheck" /tr "powershell.exe -Command \"try { $response = Invoke-WebRequest -Uri http://localhost:8000/health -TimeoutSec 10; if ($response.StatusCode -eq 200) { Add-Content -Path 'C:\logs\mpango_uptime.log' -Value \"$(Get-Date): HEALTH_OK\" } } catch { Add-Content -Path 'C:\logs\mpango_uptime.log' -Value \"$(Get-Date): HEALTH_FAIL\" }\" /sc minute /mo 1
```

#### 检查 uptime

```bash
# 查看最近 24 小时的 uptime
tail -n 1440 /var/log/mpango_uptime.log | grep HEALTH_OK | wc -l

# 计算可用率
echo "scale=2; ($(tail -n 1440 /var/log/mpango_uptime.log | grep HEALTH_OK | wc -l) / 1440) * 100" | bc
```

## 2. 错误率监控

### 方法: 日志聚合分析

基于 JSON 结构化日志，使用 jq + grep 统计错误率。

#### 前提条件

- Backend 已启用 JSON 日志 (通过 core.logging_config)
- 日志包含 levelname 字段 (ERROR, WARNING 等)
- 日志输出到 stdout/stderr (Docker logs 可获取)

#### 统计命令示例

```bash
# 获取最近 1 小时的错误日志
docker logs --since 1h mpango_backend | jq -r 'select(.levelname == "ERROR") | .message'

# 计算错误率 (总请求 vs 错误请求)
TOTAL_REQUESTS=$(docker logs --since 1h mpango_backend | jq -r 'select(.levelname) | .request_id' | sort | uniq | wc -l)
ERROR_REQUESTS=$(docker logs --since 1h mpango_backend | jq -r 'select(.levelname == "ERROR") | .request_id' | sort | uniq | wc -l)
echo "Error Rate: $((ERROR_REQUESTS * 100 / TOTAL_REQUESTS))%"

# 按租户统计错误
docker logs --since 1h mpango_backend | jq -r 'select(.levelname == "ERROR") | .tenant_id' | sort | uniq -c | sort -nr

# 按状态码统计 (假设应用日志包含 status_code)
docker logs --since 24h mpango_backend | jq -r 'select(.status_code >= 400) | .status_code' | sort | uniq -c | sort -nr
```

#### 定期报告脚本

```bash
#!/bin/bash
# daily_error_report.sh

LOG_FILE="/var/log/mpango_daily_report.log"
START_TIME=$(date -d '1 day ago' +%Y-%m-%dT%H:%M:%S)

echo "=== Daily Error Report $(date) ===" >> $LOG_FILE

# Total requests today
TOTAL=$(docker logs --since "$START_TIME" mpango_backend | jq -r 'select(.request_id) | .request_id' | sort | uniq | wc -l)
echo "Total requests: $TOTAL" >> $LOG_FILE

# Error requests
ERRORS=$(docker logs --since "$START_TIME" mpango_backend | jq -r 'select(.levelname == "ERROR") | .request_id' | sort | uniq | wc -l)
echo "Error requests: $ERRORS" >> $LOG_FILE

# Error rate
if [ $TOTAL -gt 0 ]; then
    RATE=$((ERRORS * 100 / TOTAL))
    echo "Error rate: ${RATE}%" >> $LOG_FILE
fi

# Top error messages
echo "Top 5 error messages:" >> $LOG_FILE
docker logs --since "$START_TIME" mpango_backend | jq -r 'select(.levelname == "ERROR") | .message' | sort | uniq -c | sort -nr | head -5 >> $LOG_FILE

echo "=== End Report ===" >> $LOG_FILE
```

### 监控阈值建议

- Uptime < 99.9%: 触发告警
- 错误率 > 5%: 调查原因
- 单个租户错误率 > 10%: 重点关注该租户

### 扩展建议

- 将上述脚本集成到现有 cron 中
- 日志轮转避免磁盘满载
- 考虑日志外部存储 (如 S3) 用于长期分析
