# S8-SEC: Aikido 安全扫描修复报告

**日期**：2026-02-11（第二轮更新）
**触发来源**：Aikido Security SAST 扫描（仓库 #1520606）
**原始报告**：
- [`ai-ledger/test/2026-2-10_MpangoERP aikido report.md`](../test/2026-2-10_MpangoERP%20aikido%20report.md)（第一轮）
- [`ai-ledger/test/2026-2-11MpangoERP aikido.md`](../test/2026-2-11MpangoERP%20aikido.md)（第二轮）
**修复执行**：Cascade AI + CPO 审核
**状态**： 全部可修复项已完成

---

## 1. 修复概览

| 风险等级 | 原始数量 | 已修复 | 误报/不适用 | 待手动处理 |
|----------|----------|--------|-------------|------------|
| **Critical** (SQL 注入) | 10 条 |  10 | 0 | 0 |
| **High** (密钥泄露) | 9 类 (38 子项) |  15 文件 | 0 |  ai-ledger 文档 + Git 历史 |
| **High** (依赖漏洞) | 2 个 |  2 | 0 | 0 |
| **Medium** (CI Action + 文件包含) | 4 条 |  1 | 0 |  3 (CI Actions 不在本地) |
| **Medium** (测试密钥) | 5 条 |  5 | 0 | 0 |
| **Low** (测试/文档密钥 + assert) | 8 条 |  5 | 3 误报 | 0 |

> **代码修复**：共 26 个文件变更，0 个新增依赖。
> **待手动处理**：Git 历史清理、密钥轮换、GitHub Actions 锁定、ai-ledger 文档脱敏。

---

## 2. Critical  SQL 注入修复（第一轮完成）

### 2.1 修复策略

创建共享安全工具 `db/sql_safety.py`，提供 `validate_identifier()` 函数：

```python
# db/sql_safety.py
SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")

def validate_identifier(value: str, label: str = "identifier") -> str:
    if not SAFE_IDENTIFIER_RE.match(value):
        raise ValueError(f"Unsafe {label}: {value!r}")
    return value
```

### 2.2 修复文件清单

| 文件 | 修复方式 |
|------|---------|
| `db/sql_safety.py` | **新建**  共享标识符验证工具 |
| `jobs/reporting_jobs.py` | bind parameter `:lock_key` + `validate_identifier()` |
| `scripts/create_wholesaler.py` | 移除 schema 前缀 + `validate_identifier()` |
| `database/session.py` | `validate_identifier()` 前置 |
| `database/reporting_session.py` | `validate_identifier()` 前置 |
| `api/context/tenant.py` | `validate_identifier()` 前置 |
| `core/governance/db_resolver.py` | `validate_identifier()` 前置 |
| `services/reporting/query_builder.py` | `validate_identifier()` 前置 |

---

## 3. High  密钥泄露修复

### 3.1 第一轮修复（2026-02-10）

| 文件 | 原始问题 | 修复方式 |
|------|----------|---------|
| `docker-compose.yml` L12 | 硬编码 POSTGRES_PASSWORD |  `${POSTGRES_PASSWORD:?must be set}` |
| `docker-compose.yml` L56 | DATABASE_URL 含硬编码密码 |  `${POSTGRES_PASSWORD}` 变量引用 |
| `docker-compose.yml` L61 | SECRET_KEY 含硬编码默认值 |  `${SECRET_KEY:?must be set}` |
| `backend/check_enum.py` L3-4 | 硬编码 DB 密码 + SECRET_KEY |  `RuntimeError` 要求环境变量 |
| `tests/conftest.py` L14-15 | 硬编码凭据 |  `hashlib.sha256()` 生成测试密钥 |
| `tests/setup_test_schema.py` L12-13 | 同上 |  同上 |
| `tests/drop_test_schema.py` L6-7 | 同上 |  同上 |

### 3.2 第二轮修复（2026-02-11） 新发现

| 文件 | 原始问题 | 修复方式 |
|------|----------|---------|
| `ai-ledger/backend/s8-sec_aikido_remediation.md` L77,89 | 修复报告本身包含明文密码 |  `REDACTED_PASSWORD` / `REDACTED_SECRET_KEY` |
| `scripts/s5_5_pentest.py` L13 | 硬编码 DB 密码 |  `os.environ.get("DATABASE_URL")` |
| `scripts/s5_tenant_migration.py` L12 | 同上 |  同上 |
| `scripts/s5_verify_deployment.py` L6 | 同上 |  同上 |
| `scripts/s6_1_verify_views.py` L6-7 | 硬编码 DB + reporting 密码 |  `DATABASE_URL` + `REPORTING_DATABASE_URL` 环境变量 |
| `alembic/versions/011_s6_p_reporting_role.py` L27 | 硬编码 reporting 密码 |  `os.environ.get("REPORTING_USER_PASSWORD")` |
| `database/reporting_session.py` L71 | reporting 密码有硬编码 fallback |  移除 fallback，要求环境变量 |
| `tests/test_s6_2_materialized_views.py` L245 | 硬编码 reporting 密码 |  `os.environ.get("REPORTING_USER_PASSWORD")` |
| `tests/test_s6_3_dashboard_api.py` L354 | 同上 |  同上 |

### 3.3 待手动处理

| 项目 | 操作 | 优先级 |
|------|------|--------|
| **密钥轮换** | 已暴露的 POSTGRES_PASSWORD、SECRET_KEY、REPORTING_USER_PASSWORD 必须在所有环境中轮换 |  24h |
| **Git 历史清理** | 使用 BFG Repo-Cleaner 清除历史中的密钥 |  24h |
| **ai-ledger 文档脱敏** | 手动将 `ai-ledger/architect/`、`ai-ledger/ops/` 等文档中的密钥示例替换为占位符 |  1 周 |
| **`.secrets.baseline`** | 若在远程仓库存在，需删除并加入 `.gitignore` |  1 周 |

---

## 4. High  依赖漏洞修复（第二轮新增）

| 包名 | 修复前 | 修复后 | CVE | 修复方式 |
|------|--------|--------|-----|---------|
| **axios** (前端) | 1.13.2 | 1.13.5 | CVE-2026-25639 (原型污染) | `package.json` 版本约束  `^1.13.5` + `npm install` |
| **cryptography** (后端) | 46.0.4 | 46.0.5 | CVE-2026-26007 (EC 密钥验证缺陷) | `pyproject.toml` 新增直接依赖 `>=46.0.5` + `poetry update` |

---

## 5. Medium  CI Action 锁定 & 文件包含攻击

### 5.1 文件包含攻击   已修复（第一轮）

`backend/jobs/export_jobs.py` 的 `read_metadata()` / `_write_metadata()` 新增双重防护：
- 正则验证 `file_id`（仅允许 `[a-zA-Z0-9_-]`）
- 路径解析验证（`resolve()` + `startswith`）

### 5.2 CI Action 锁定   待手动处理

`.github/workflows/` 目录不在本地工作区。需在 GitHub 仓库中将以下 Action 锁定到 commit hash：

```yaml
- uses: gitleaks/gitleaks-action@v2         @<commit-hash>
- uses: trufflesecurity/trufflehog@main     @<commit-hash>
- uses: snyk/actions/python@master          @<commit-hash>
```

### 5.3 测试文件密钥   已修复（第一轮）

| 文件 | 修复方式 |
|------|---------|
| `b6_verification_tests.py` |  `os.environ.get("B6_TENANT_*_PASSWORD")` |
| `backend/check_enum.py` |  `RuntimeError` 要求环境变量 |
| `tests/conftest.py` |  `hashlib.sha256()` 生成测试密钥 |
| `tests/setup_test_schema.py` |  同上 |
| `tests/drop_test_schema.py` |  同上 |

---

## 6. Low  测试/文档密钥 & assert

### 6.1 已修复

| 文件 | 修复方式 |
|------|---------|
| `tests/test_security_s2_5.py` L102 | 硬编码 SECRET_KEY  `hashlib.sha256()` |
| `tests/performance/locustfile.py` L57 | 硬编码密码  `os.environ.get()` |
| `docs/security/secrets-quickstart.md` L86 | `sk_live_abc123xyz`  `YOUR_API_KEY_HERE` |
| `scripts/seed_bi_assets.py` L347 | `assert`  `raise RuntimeError` |

### 6.2 误报（不需修复）

| 文件 | 说明 |
|------|------|
| `tests/test_jwt_utils.py` L101 | 故意构造的无效 JWT（`...invalid_signature`），用于测试解码失败 |
| `tests/test_security_s2_5.py` L37,63,89 | 故意包含弱子串的 SECRET_KEY，用于测试验证器拒绝逻辑 |
| `tests/performance/locustfile.py` L57 | 报告显示 `REDACTED_SECRET`，实际已修复为 `os.environ.get()` |

---

## 7. 修改文件总清单

### 第一轮（2026-02-10） 18 个文件

| # | 文件 | 操作 |
|---|------|------|
| 1 | `db/sql_safety.py` | **新建**  共享 SQL 标识符验证 |
| 2 | `jobs/reporting_jobs.py` | bind params + validate |
| 3 | `scripts/create_wholesaler.py` | 移除 schema 前缀 + validate |
| 4 | `database/session.py` | 添加 validate_identifier |
| 5 | `database/reporting_session.py` | 添加 validate_identifier |
| 6 | `api/context/tenant.py` | 添加 validate_identifier |
| 7 | `core/governance/db_resolver.py` | 添加 validate_identifier |
| 8 | `services/reporting/query_builder.py` | 添加 validate_identifier |
| 9 | `docker-compose.yml` | 移除硬编码密码 |
| 10 | `backend/check_enum.py` | 要求环境变量 |
| 11 | `tests/conftest.py` | 生成测试密钥 |
| 12 | `tests/setup_test_schema.py` | 生成测试密钥 |
| 13 | `tests/drop_test_schema.py` | 生成测试密钥 |
| 14 | `tests/test_security_s2_5.py` | 生成测试密钥 |
| 15 | `tests/performance/locustfile.py` | 密码改为环境变量 |
| 16 | `b6_verification_tests.py` | 密码改为环境变量 |
| 17 | `jobs/export_jobs.py` | 路径遍历防护 |
| 18 | `scripts/seed_bi_assets.py` | assert  raise |

### 第二轮（2026-02-11） 10 个文件

| # | 文件 | 操作 |
|---|------|------|
| 19 | `ai-ledger/backend/s8-sec_aikido_remediation.md` | 脱敏明文密码 |
| 20 | `frontend/package.json` | axios ^1.6.2  ^1.13.5 |
| 21 | `backend/pyproject.toml` | 新增 cryptography >=46.0.5 |
| 22 | `scripts/s5_5_pentest.py` | 硬编码 DB URL  环境变量 |
| 23 | `scripts/s5_tenant_migration.py` | 同上 |
| 24 | `scripts/s5_verify_deployment.py` | 同上 |
| 25 | `scripts/s6_1_verify_views.py` | 硬编码 DB + reporting URL  环境变量 |
| 26 | `alembic/versions/011_s6_p_reporting_role.py` | 硬编码 reporting 密码  环境变量 |
| 27 | `database/reporting_session.py` | 移除 fallback 密码 |
| 28 | `tests/test_s6_2_materialized_views.py` | 硬编码 reporting 密码  环境变量 |
| 29 | `tests/test_s6_3_dashboard_api.py` | 同上 |
| 30 | `docs/security/secrets-quickstart.md` | 假 API key  占位符 |

---

## 8. 后续行动清单

###  立即（24h 内）

- [ ] 轮换所有已暴露的密钥（POSTGRES_PASSWORD、SECRET_KEY、REPORTING_USER_PASSWORD）
- [ ] 执行 Git 历史清理（BFG Repo-Cleaner）
- [ ] 在所有部署环境中更新密钥
- [ ] 创建 `.env.example` 模板文件，列出所有必需的环境变量

###  短期（1 周内）

- [ ] 锁定 `.github/workflows/` 中的 Action 到 commit hash
- [ ] 脱敏 `ai-ledger/` 文档中的密钥示例
- [ ] 删除 `.secrets.baseline`（如存在）并加入 `.gitignore`
- [ ] 在 CI 中集成 `detect-secrets` 预提交钩子

###  中期（2 周内）

- [ ] 再次运行 Aikido SAST 扫描，确认所有问题已关闭
- [ ] 部署密钥管理系统（AWS Secrets Manager / HashiCorp Vault）
- [ ] 制定《密钥管理手册》和自动轮换策略
- [ ] 建立定期依赖安全扫描机制（dependabot / renovate）

---

## 9. 新增环境变量清单

本轮修复引入了以下必需的环境变量：

| 变量名 | 用途 | 使用位置 |
|--------|------|----------|
| `POSTGRES_PASSWORD` | PostgreSQL 主密码 | `docker-compose.yml` |
| `SECRET_KEY` | JWT 签名密钥 | `docker-compose.yml`, `check_enum.py` |
| `DATABASE_URL` | 主数据库连接串 | 所有 backend 脚本 |
| `REPORTING_USER_PASSWORD` | reporting_user 密码 | `reporting_session.py`, alembic migration, 测试 |
| `REPORTING_DATABASE_URL` | reporting 数据库连接串 | `s6_1_verify_views.py` |
| `LOCUST_TEST_EMAIL` | 性能测试邮箱 | `locustfile.py` |
| `LOCUST_TEST_PASSWORD` | 性能测试密码 | `locustfile.py` |
| `B6_TENANT_A_PASSWORD` | B6 测试租户 A 密码 | `b6_verification_tests.py` |
| `B6_TENANT_B_PASSWORD` | B6 测试租户 B 密码 | `b6_verification_tests.py` |
| `TEST_DATABASE_URL` | 测试数据库连接串（可选） | `conftest.py`, `setup_test_schema.py`, `drop_test_schema.py` |
