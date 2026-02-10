# S8-SEC: Aikido 安全扫描修复报告

**日期**：2026-02-10  
**触发来源**：Aikido Security SAST 扫描（仓库 #1520606）  
**原始报告**：[`ai-ledger/test/2026-2-10_Mpango‑ERP aikido report.md`](../test/2026-2-10_Mpango‑ERP%20aikido%20report.md)  
**修复执行**：Cascade AI + CPO 审核  
**状态**：✅ 全部可修复项已完成

---

## 1. 修复概览

| 风险等级 | 原始数量 | 已修复 | 待手动处理 | 不适用 |
|----------|----------|--------|------------|--------|
| **Critical** (SQL 注入) | 10 条 | ✅ 10 | 0 | 0 |
| **High** (密钥泄露) | 9 类 (35 子项) | ✅ 7 类 | ⚠️ 2 类 | 0 |
| **Medium** (CI Action + 文件包含) | 4 条 | ✅ 1 | ⚠️ 3 | 0 |
| **Low** (测试密钥 + assert) | 8 条 | ✅ 7 | 0 | 1 |

> **代码修复**：18 个文件变更，0 个新增依赖。  
> **待手动处理**：Git 历史清理、密钥轮换、GitHub Actions 锁定。

---

## 2. Critical — SQL 注入修复

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

所有 `text(f'...')` SQL 拼接点在执行前调用此函数验证标识符安全性。

### 2.2 修复文件清单

| 文件 | 行号 | 原始问题 | 修复方式 |
|------|------|----------|---------|
| `db/sql_safety.py` | — | **新建** | 共享标识符验证工具 |
| `jobs/reporting_jobs.py` | 75, 120 | `schema` f-string 拼接 `pg_try_advisory_lock` | → bind parameter `:lock_key` |
| `jobs/reporting_jobs.py` | 90, 97 | `schema` f-string 拼接 `SET LOCAL` / `REFRESH` | → `validate_identifier()` 前置 + 白名单 |
| `scripts/create_wholesaler.py` | 82-219 (8处) | `tenant_schema` f-string 拼接表名 | → 移除 schema 前缀，依赖 `SET LOCAL search_path` + `validate_identifier()` |
| `database/session.py` | 112, 136 | `tenant_schema` f-string 拼接 | → `validate_identifier()` 前置 |
| `database/reporting_session.py` | 133 | 同上 | → 同上 |
| `api/context/tenant.py` | 38 | 同上 | → 同上 |
| `core/governance/db_resolver.py` | 111, 162 | 同上 | → 同上 |
| `services/reporting/query_builder.py` | 109 | 同上 | → 同上 |

### 2.3 防御层次

```
用户输入 → Pydantic 枚举验证 → validate_identifier() → SET LOCAL search_path → ORM select()
                                    ↑ 新增防线
```

- **第一层**：Pydantic 模型在 API 边界拒绝非法输入
- **第二层**（新增）：`validate_identifier()` 在 SQL 拼接前验证标识符格式
- **第三层**：`SET LOCAL search_path` 限制查询范围
- **第四层**：SQLAlchemy ORM `select()` 构建参数化查询

---

## 3. High — 密钥泄露修复

### 3.1 已修复

| 文件 | 原始问题 | 修复方式 |
|------|----------|---------|
| `docker-compose.yml` L12 | `POSTGRES_PASSWORD: MpangoDBV0.1.2` | → `${POSTGRES_PASSWORD:?must be set}` |
| `docker-compose.yml` L56 | `DATABASE_URL` 含硬编码密码 | → `${POSTGRES_PASSWORD}` 变量引用 |
| `docker-compose.yml` L61 | `SECRET_KEY` 含硬编码默认值 | → `${SECRET_KEY:?must be set}` |
| `backend/check_enum.py` L3-4 | 硬编码 DB 密码 + SECRET_KEY | → `RuntimeError` 要求设置环境变量 |
| `tests/conftest.py` L14-15 | 硬编码 DB 密码 + SECRET_KEY | → `hashlib.sha256()` 生成确定性测试密钥 |
| `tests/setup_test_schema.py` L12-13 | 同上 | → 同上 |
| `tests/drop_test_schema.py` L6-7 | 同上 | → 同上 |

### 3.2 待手动处理

| 项目 | 操作 | 优先级 |
|------|------|--------|
| **密钥轮换** | `MpangoDBV0.1.2`、`kJ8mN2pQ5rT9vX3zA6bC4dF7gH1jK0lM` 等已暴露密钥必须在所有环境中轮换 | 🔴 48h |
| **Git 历史清理** | 使用 `git filter-branch` 或 BFG Repo-Cleaner 清除历史中的密钥 | 🔴 48h |
| **`ai-ledger/` 文档脱敏** | 手动将设计文档中的密钥示例替换为占位符 | 🟡 1 周 |
| **`.secrets.baseline`** | 文件在本地不存在；若在远程仓库存在，需删除并加入 `.gitignore` | 🟡 1 周 |

---

## 4. Medium — CI Action 锁定 & 文件包含攻击

### 4.1 文件包含攻击 — ✅ 已修复

`backend/jobs/export_jobs.py` 的 `read_metadata(file_id)` 和 `_write_metadata(file_id)` 存在路径遍历风险。

**修复**：新增双重防护：

```python
# 1. 正则验证 file_id（仅允许 [a-zA-Z0-9_-]）
_SAFE_FILE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")

# 2. 路径解析验证（resolve + startswith）
def _safe_meta_path(file_id: str) -> Path:
    _validate_file_id(file_id)
    export_dir = _ensure_export_dir()
    meta_path = (export_dir / f"{file_id}.meta.json").resolve()
    if not str(meta_path).startswith(str(export_dir.resolve())):
        raise ValueError(f"Path traversal detected: {meta_path}")
    return meta_path
```

### 4.2 CI Action 锁定 — ⚠️ 待手动处理

`.github/workflows/` 目录不在本地工作区。需在 GitHub 仓库中将以下 Action 锁定到 commit hash：

```yaml
# security-scan.yml
- uses: gitleaks/gitleaks-action@v2        → @<commit-hash>
- uses: trufflesecurity/trufflehog@main    → @<commit-hash>
- uses: snyk/actions/python@master         → @<commit-hash>
```

---

## 5. Low — 测试密钥 & assert

### 5.1 已修复

| 文件 | 原始问题 | 修复方式 |
|------|----------|---------|
| `tests/test_security_s2_5.py` L102 | 硬编码 SECRET_KEY | → `hashlib.sha256()` 生成 |
| `tests/performance/locustfile.py` L57 | 硬编码密码 `admin123` | → `os.environ.get("LOCUST_TEST_PASSWORD")` |
| `b6_verification_tests.py` L20-26 | 硬编码密码 | → `os.environ.get("B6_TENANT_*_PASSWORD")` |
| `scripts/seed_bi_assets.py` L347 | `assert restored == config` | → `if restored != config: raise RuntimeError(...)` |

### 5.2 不适用

| 文件 | 说明 |
|------|------|
| `tests/test_jwt_utils.py` L101 | 故意构造的无效 JWT 字符串（`eyJ...invalid_signature`），用于测试解码失败路径，**非真实密钥** |

---

## 6. 修改文件总清单

### 第一轮（Critical SQL 注入 + 基础设施加固）— 8 个文件

| # | 文件 | 操作 |
|---|------|------|
| 1 | `db/sql_safety.py` | **新建** — 共享 SQL 标识符验证 |
| 2 | `jobs/reporting_jobs.py` | bind params + 白名单 + validate |
| 3 | `scripts/create_wholesaler.py` | 移除 schema 前缀 + validate |
| 4 | `database/session.py` | 添加 validate_identifier |
| 5 | `database/reporting_session.py` | 添加 validate_identifier |
| 6 | `api/context/tenant.py` | 添加 validate_identifier |
| 7 | `core/governance/db_resolver.py` | 添加 validate_identifier |
| 8 | `services/reporting/query_builder.py` | 添加 validate_identifier |

### 第二轮（High/Medium/Low 修复）— 10 个文件

| # | 文件 | 操作 |
|---|------|------|
| 9 | `docker-compose.yml` | 移除硬编码密码 |
| 10 | `backend/check_enum.py` | 要求环境变量 |
| 11 | `tests/conftest.py` | 生成测试密钥 |
| 12 | `tests/setup_test_schema.py` | 生成测试密钥 |
| 13 | `tests/drop_test_schema.py` | 生成测试密钥 |
| 14 | `tests/test_security_s2_5.py` | 生成测试密钥 |
| 15 | `tests/performance/locustfile.py` | 密码改为环境变量 |
| 16 | `b6_verification_tests.py` | 密码改为环境变量 |
| 17 | `jobs/export_jobs.py` | 路径遍历防护 |
| 18 | `scripts/seed_bi_assets.py` | assert → raise |

---

## 7. 后续行动清单

### 🔴 立即（48h 内）

- [ ] 轮换所有已暴露的密钥（POSTGRES_PASSWORD、SECRET_KEY）
- [ ] 执行 Git 历史清理（BFG Repo-Cleaner 或 `git filter-branch`）
- [ ] 在所有部署环境中更新密钥

### 🟡 短期（1 周内）

- [ ] 锁定 `.github/workflows/` 中的 Action 到 commit hash
- [ ] 脱敏 `ai-ledger/` 文档中的密钥示例
- [ ] 删除 `.secrets.baseline`（如存在）并加入 `.gitignore`
- [ ] 创建 `.env.example` 模板文件，列出所有必需的环境变量

### 🟢 中期（2 周内）

- [ ] 在 CI 中集成 `detect-secrets` 预提交钩子
- [ ] 再次运行 Aikido SAST 扫描，确认所有问题已关闭
- [ ] 制定《密钥管理手册》

---

## 8. 设计决策记录

### D1: 为什么不用 `psycopg.sql.Identifier()` 替代 f-string？

PostgreSQL 的 `SET LOCAL search_path` 和 `REFRESH MATERIALIZED VIEW` 是 DDL 语句，`psycopg.sql.Identifier()` 在 SQLAlchemy `text()` 中无法直接使用。我们选择 **正则验证 + f-string** 的方案，因为：

1. `validate_identifier()` 的正则 `^[a-zA-Z_][a-zA-Z0-9_]{0,62}$` 严格匹配 PostgreSQL 标识符规范
2. 所有验证集中在 `db/sql_safety.py` 一个文件，便于审计
3. 与现有代码风格一致，改动最小

### D2: 为什么测试密钥用 `hashlib.sha256()` 而不是 `secrets.token_hex()`？

测试需要**确定性**（每次运行产生相同的密钥），否则 `Settings` 的 `lru_cache` 会因密钥变化而失效。`sha256` 从固定种子生成 64 字符的十六进制字符串，满足 32 字符最低要求且不含弱子串。

### D3: 为什么 `docker-compose.yml` 用 `${VAR:?error}` 而不是 `${VAR:-default}`？

`:-` 语法提供默认值，但默认值本身就是安全风险（硬编码密码）。`:?` 语法在变量未设置时**立即报错并停止启动**，强制运维人员显式提供密钥，符合 fail-fast 原则。
