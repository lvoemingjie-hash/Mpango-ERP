# 安全检查清单

**目的**: 确保生产部署不包含安全漏洞，特别是敏感信息泄露和弱密码问题。

## 1. 密钥管理检查

### 要求

- ✅ **所有密钥必须来自环境变量或 secrets 文件**
- ❌ **禁止在代码中硬编码 SECRET_KEY、DB 密码、JWT 密钥等**
- ❌ **禁止在 docker-compose.yml 中明文存储敏感信息**

### 检查位置

#### 代码文件检查

```bash
# 搜索硬编码的密钥模式
grep -r "SECRET_KEY.*=" backend/ --include="*.py" | grep -v "os.getenv\|os.environ\|settings"

# 搜索硬编码的数据库密码
grep -r "PASSWORD.*=" backend/ --include="*.py" | grep -v "os.getenv\|os.environ\|settings"

# 搜索硬编码的 JWT 密钥
grep -r "JWT.*KEY.*=" backend/ --include="*.py" | grep -v "os.getenv\|os.environ\|settings"
```

#### Docker Compose 检查

```bash
# 检查 docker-compose.yml 中是否有明文密码
grep -A5 -B5 "PASSWORD\|SECRET\|KEY" docker-compose.yml
```

#### 环境变量检查

```bash
# 确认必需的环境变量已设置 (生产部署前)
echo "Required env vars:"
echo "- SECRET_KEY: ${SECRET_KEY:+SET}"
echo "- DATABASE_URL: ${DATABASE_URL:+SET}"
echo "- REDIS_URL: ${REDIS_URL:+SET}"

# 检查 secrets 目录
ls -la secrets/ 2>/dev/null || echo "secrets/ directory not found"
```

### 修复指南

如果发现硬编码:

1. **代码中硬编码**: 移动到 `core/config.py` 的环境变量读取
2. **Compose 中明文**: 移动到 `secrets/prod.env` 文件
3. **测试数据**: 确保测试环境使用不同密钥

## 2. 默认管理员密码检查

### 要求

- ✅ **禁止内置弱密码或空密码管理员账户**
- ✅ **首次部署后，必须在 30 分钟内修改默认 admin 密码**
- ✅ **密码策略**: 至少 12 位，包含大小写字母、数字、特殊字符

### 检查步骤

#### 数据库初始化检查

```bash
# 检查数据库初始化脚本是否有默认 admin
grep -i "admin\|root" database/init.sql

# 检查是否有默认密码插入
grep -A5 -B5 "INSERT.*user" database/init.sql
```

#### 应用启动检查

```bash
# 检查应用代码是否创建默认 admin
grep -r "create.*admin\|insert.*admin" backend/ --include="*.py"
```

#### 部署后验证

```bash
# 部署后立即检查 (前 30 分钟)
# 1. 确认 admin 用户存在但密码已修改
echo "Check admin user creation logs and password change requirements"

# 2. 验证密码强度
echo "Password must be changed within 30 minutes of first deployment"
```

### 安全部署流程

#### 首次部署

1. **部署前准备**
   ```bash
   # 生成强密钥
   openssl rand -hex 32  # 用于 SECRET_KEY
   openssl rand -base64 32  # 用于 JWT 密钥
   ```

2. **部署中监控**
   ```bash
   # 启动应用后立即检查日志
   docker logs mpango_backend | grep -i "admin\|password\|created"
   ```

3. **部署后 30 分钟内**
   ```bash
   # 强制修改默认密码
   echo "ADMIN_PASSWORD_CHANGE_REQUIRED=1" >> secrets/prod.env
   docker compose restart backend
   ```

## 3. 敏感信息泄露检查

### 日志检查

```bash
# 检查日志是否输出密码/token
docker logs mpango_backend | grep -i "password\|token\|secret\|key" | head -10

# 检查错误日志是否暴露敏感信息
docker logs mpango_backend | grep -i "error\|exception" | jq '.message' 2>/dev/null | grep -i "password\|token"
```

### 配置文件检查

```bash
# 检查所有配置文件
find . -name "*.env*" -o -name "*.yml" -o -name "*.yaml" | xargs grep -l "PASSWORD\|SECRET\|KEY" | head -10

# 检查备份文件
find backups/ -name "*.sql" | head -5 | xargs grep -l "password\|secret" || echo "No sensitive data in backups found"
```

## 4. 网络安全检查

### 端口暴露检查

```bash
# 检查不必要的端口暴露
grep -A5 "ports:" docker-compose.yml

# 推荐: 只暴露必要端口 (8000 for API, 5173 for frontend in dev)
```

### 健康检查安全

```bash
# 确保 /health 不暴露敏感信息
curl http://localhost:8000/health | jq .
# 应该只返回 status, service, version, timestamp
```

## 5. 定期安全审计

### 每月检查清单

- [ ] 密钥轮换 (至少每 90 天)
- [ ] 备份文件访问权限检查
- [ ] 日志文件敏感信息清理
- [ ] 依赖包安全更新
- [ ] 用户权限审计

### 工具辅助

```bash
# 使用安全扫描工具 (可选)
pip install safety
safety check

# 检查依赖漏洞
pip audit
```

## 紧急响应

### 密钥泄露处理

1. **立即轮换所有密钥**
2. **检查日志中的使用痕迹**
3. **通知相关方**
4. **审计受影响数据**

### 弱密码发现

1. **强制所有用户修改密码**
2. **启用密码策略检查**
3. **记录安全事件**

## 总结

**安全优先级**: 密钥管理 > 密码策略 > 信息泄露防护 > 网络安全

**零容忍**: 任何硬编码敏感信息都是阻断性问题，必须在部署前修复。
