# Mpango‑ERP 安全审计报告
**报告日期**：2025‑09‑27
**审计范围**：全部代码库（包括后端、CI、文档、测试、性能脚本）
**审计工具**：SAST、Secrets‑Scan、GitHub Actions linting、静态分析

---

## 1️⃣ 审计概览

| 风险等级 | 问题数量 | 涉及子项（子 Issue） |
|----------|----------|----------------------|
| **Critical** | 1 类（SQL 注入）| 10 条 |
| **High** | 1 类（密钥泄露）| 9 条（实际 35 条子项） |
| **Medium** | 2 类 | 4 条（3 个 GitHub Action 未锁定 + 1 个文件包含攻击） |
| **Low** | 3 类 | 8 条（4 个测试文件泄漏 JWT / SECRET_KEY + 2 个文档/性能脚本泄漏 + 1 个不安全的 `assert`） |

> **总计**：10 条 Critical、9 条 High、4 条 Medium、8 条 Low = **31 条**（其中 35 条为密钥子项）

> 所有问题均来自同一次提交 `dfljeff01‑commits`，建议立即追溯该提交的所有内容并进行代码审查。

---

## 2️⃣ 详细问题列表

### 2.1 Critical – Potential SQL injection via string‑based query concatenation

| 文件 | 行号 | 代码片段 | 说明 |
|------|------|----------|------|
| `backend/jobs/reporting_jobs.py` | 75 | `text(f"SELECT pg_try_advisory_lock(hashtext('mv_refresh_{schema}'))")` | `schema` 直接拼接，易被注入 |
| `backend/jobs/reporting_jobs.py` | 120 | `text(f"SELECT pg_advisory_unlock(hashtext('mv_refresh_{schema}'))")` | 同上 |
| `backend/scripts/create_wholesaler.py` | 82 | `text(f'SELECT * FROM \"{tenant_schema}\".users WHERE email = :email')` | `tenant_schema` 拼接，导致跨租户泄露 |
| `backend/scripts/create_wholesaler.py` | 119 | `text(f'SELECT * FROM \"{tenant_schema}\".roles WHERE name = :name')` | 同上 |
| `backend/scripts/create_wholesaler.py` | 139 | `text(f'INSERT INTO \"{tenant_schema}\".user_roles (user_id, role_id) VALUES (:user_id, :role_id)')` | 同上 |
| `backend/scripts/create_wholesaler.py` | 177 | `text(f'SELECT * FROM \"{tenant_schema}\".permissions WHERE code = :code')` | 同上 |
| `backend/scripts/create_wholesaler.py` | 195 | `text(f'SELECT id FROM \"{tenant_schema}\".roles WHERE name = :name')` | 同上 |
| `backend/scripts/create_wholesaler.py` | 207 | `result = await db.execute(text(f'SELECT id FROM \"{tenant_schema}\".permissions'))` | 同上 |
| `backend/scripts/create_wholesaler.py` | 214 | `text(f'SELECT * FROM \"{tenant_schema}\".role_permissions WHERE role_id = :role_id AND permission_id = :perm_id')` | 同上 |
| `backend/scripts/create_wholesaler.py` | 219 | `text(f'INSERT INTO \"{tenant_schema}\".role_permissions (role_id, permission_id) VALUES (:role_id, :perm_id)')` | 同上 |

**修复**：全部改为参数化查询或使用 ORM；对 `schema` / `tenant_schema` 进行白名单校验后再拼接。

---

### 2.2 High – Secret leaks（9 类）

| 文件 | 行号 | 泄露内容 | 风险 |
|------|------|----------|------|
| `ai-ledger/architect/2026-01-09_architecture_project-bootstrap.md` | 438 | `"password": REDACTED_SECRET` | 生产配置 |
| `ai-ledger/ops/2026-01-20_ops_boot_contract_verification.md` | 216 | `SECRET_KEY=*****************.1.2` | CI/运维 |
| `docker-compose.yml` | 54 | `SECRET_KEY=*****************.1.2` | 容器编排 |
| `docker-compose.yml` | 12 | `PASSWORD: **********.1.2` | 容器编排 |
| `ai-ledger/ops/backup_postgres_cron.md` | 117 | `PASSWORD=**********.1.2` | 备份脚本 |
| `b6_verification_tests.py` | 25 | `"password": *********123"` | 测试文件（仍属生产泄露） |
| `ai-ledger/ops/2026-02-01_track_s1-1_secrets_governance.md` | 89 | `SECRET_KEY: …cdoB` | 文档 |
| `ai-ledger/ops/2026-02-01_track_s1-1_secrets_governance.md` | 18 | `password: **********.1.2` | 文档 |
| `.secrets.baseline` | 130‑346 (共 20 行) | `secret": "************************************xxxx"` (20 条) | 基准文件（全部泄露） |
| `backend/check_enum.py` | 4 | `SECRET_KEY", "****************************K0lM"` | 代码 |
| `backend/tests/setup_test_schema.py` | 13 | 同上（标记 **Low**） | 测试文件 |
| `backend/tests/conftest.py` | 15 | 同上（标记 **Low**） | 测试文件 |
| `backend/tests/drop_test_schema.py` | 7 | 同上（标记 **Low**） | 测试文件 |
| `ai-ledger/backend/2026-02-06_s3_c_caching_benchmarking.md` | 137 | `auth_me:********************************4000` | 文档 |
| `.github/workflows/s2-7-ci-gates.yml` | 17 | `SECRET_KEY: …ning` | CI 工作流 |
| `.github/workflows/s5-ci-gate.yml` | 16 | 同上 | CI 工作流 |

**修复**：
1. **立即轮换**所有暴露的密钥（SECRET_KEY、PASSWORD、auth_me 等）。
2. **彻底删除**或 **重写 Git 历史**（`git filter-branch`、`git rebase`）以去除历史记录。
3. 迁移到 **环境变量**、**Docker secrets**、或 **AWS Secrets Manager / HashiCorp Vault**。

---

### 2.3 Medium – CI 第三方 Action 未锁定（Supply‑chain 攻击风险）

| 工作流文件 | 行号 | 当前使用 | 建议的锁定方式 |
|-----------|------|----------|----------------|
| `.github/workflows/security-scan.yml` | 44 | `uses: gitleaks/gitleaks-action@v2` | `uses: gitleaks/gitleaks-action@<commit‑hash>` |
| `.github/workflows/security-scan.yml` | 50 | `uses: trufflesecurity/trufflehog@main` | `uses: trufflesecurity/trufflehog@<commit‑hash>` |
| `.github/workflows/security-scan.yml` | 121 | `uses: snyk/actions/python@master` | `uses: snyk/actions/python@<commit‑hash>` |

**修复**：在每个 `uses` 行加入对应的 **commit hash**（可在相应 Action 的 **Releases** 页面查看），避免使用 `v2`、`main`、`master` 等可变的分支/标签。

---

### 2.4 Medium – Potential file inclusion attack

| 文件 | 行号 | 代码 | 说明 |
|------|------|------|------|
| `backend/jobs/export_jobs.py` | 341 | `with open(meta_path, "r", encoding="utf-8") as f:` | `meta_path` 未经验证，攻击者可通过相对路径读取系统文件（如 `/etc/passwd`、`/proc/self/environ`） |

**修复**：
1. 对 `meta_path` 进行 **路径白名单**（仅允许在特定目录下）。
2. 使用 `os.path.abspath`、`os.path.realpath` 验证路径是否落在允许的根目录下。
3. 如需读取外部文件，考虑使用 **`pathlib.Path`** 并配合 **`strict=True`** 进行严格验证。

---

### 2.5 Low – Secret leaks in test / doc files

| 文件 | 行号 | 泄露内容 | 备注 |
|------|------|----------|------|
| `backend/tests/test_jwt_utils.py` | 101 | JWT Token (已脱敏) | 标记 **Low**（测试文件） |
| `docs/security/secrets-quickstart.md` | 86 | `API_KEY = "*************3xyz"` | 标记 **Low**（文档） |
| `backend/tests/test_security_s2_5.py` | 37, 63, 89, 102 | 4 条 `SECRET_KEY="…"` | 标记 **Low**（测试文件） |
| `backend/tests/performance/locustfile.py` | 57 | `password = REDACTED_SECRET` | 标记 **Low**（性能脚本） |

**修复**：
- 将所有 **hard‑coded** 密钥替换为 **环境变量**、**fixture** 或 **动态生成**（如 `uuid4()`、`secrets.token_hex()`）。
- 删除或使用 **`pytest.fixture`** 提供模拟密钥。
- 对于仅在 **CI** 中使用的示例密钥，考虑放在 **`ci‑secrets`** 或 **GitHub Secrets**，避免直接提交到仓库。

---

### 2.6 Low – Dangerous use of `assert`

| 文件 | 行号 | 代码 | 说明 |
|------|------|------|------|
| `backend/scripts/seed_bi_assets.py` | 347 | `assert restored == config, f"Round-trip failed for {report['title']}"` | 生产环境中 **PYTHONOPTIMIZE=1** 时 `assert` 被忽略，安全检查失效。 |

**修复**：
```python
if restored != config:
    raise RuntimeError(f"Round-trip failed for {report['title']}")
```
或使用 `logging` 记录错误后抛出 **自定义异常**。

---

## 3️⃣ 风险评级矩阵

| 等级 | 影响范围 | 紧急程度 | 建议处理时限 |
|------|----------|----------|--------------|
| **Critical** (SQL 注入) | 可导致数据库被完全控制、跨租户泄露 | 极高 | **24 h** |
| **High** (密钥泄露) | 账户被横向渗透、服务被破坏、合规违规 | 极高 | **48 h** |
| **Medium** (CI Action 未锁定、文件读取) | 可能被供应链攻击、读取敏感文件 | 中等 | **1 周** |
| **Low** (测试/文档/assert) | 对生产影响有限，但仍有风险 | 低 | **2 周**（或视业务需求决定） |

---

## 4️⃣ 修复建议（按风险等级）

### 4.1 Critical – SQL 注入
1. **全部改为参数化查询**（`text(...).bindparams(...)`）。
2. **对 `schema/tenant_schema` 做白名单校验**后再拼接。
3. 如业务必需使用动态表名，考虑 **ORM**（SQLAlchemy）或 **安全查询构建器**。
4. **部署 WAF**（如 Cloudflare、AWS WAF）并开启 **数据库审计日志**。

### 4.2 High – 密钥泄露
1. **立即轮换**所有泄露的密钥（包括生产、测试、CI、文档）。
2. **彻底清除** Git 历史：
   ```bash
   git filter-branch --force --index-filter \
   'git rm --cached --ignore-unmatch \
       ai-ledger/architect/2026-01-09_architecture_project-bootstrap.md \
       docker-compose.yml \
       .secrets.baseline \
       ...' \
   --prune-empty --tag-name-filter cat -- --all
   ```
3. **迁移到密钥管理系统**：
   - Docker Swarm 使用 `secrets:` 节点
   - Kubernetes 使用 `Secret` + `external-secrets`
   - AWS Secrets Manager / HashiCorp Vault 自动注入
4. **更新 CI/CD**：`.github/workflows/*.yml` 中全部改为 `${{ secrets.* }}`。
5. **加入预提交钩子**（`detect-secrets`、`git-secrets`）防止以后泄露。

### 4.3 Medium – CI Action & 文件读取

| 问题 | 修复步骤 |
|------|----------|
| **Action 未锁定** | 1. 获取对应 **commit hash**（Release 页面）<br>2. 修改 `uses: <owner>/<repo>@<hash>`<br>3. 重新运行 CI，验证仍正常工作 |
| **文件包含攻击** | 1. 对 `meta_path` 做绝对路径验证：`abs = Path(meta_path).resolve()`<br>2. 确保 `abs` 落在 `allowed_root` 目录内：<br>```python<br>if not str(abs).startswith(str(allowed_root)):<br>    raise ValueError("Invalid file path")<br>```<br>3. 如需更细粒度，使用 **whitelist**（后缀、目录） |

### 4.4 Low – 测试/文档密钥 & assert

| 问题 | 修复步骤 |
|------|----------|
| **测试文件密钥** | 1. 将硬编码密钥改为 `os.getenv("TEST_SECRET")` <br>2. 在 CI 中注入 `TEST_SECRET` <br>3. 使用 `pytest.fixture` 或 `unittest.mock` 模拟 |
| **文档密钥** | 1. 将示例改为占位符（如 `YOUR_API_KEY_HERE`）<br>2. 在 README 中说明如何从安全存储获取 |
| **assert** | 替换为 `raise` 异常，或使用 `logging.warning` 后继续业务逻辑（如果业务可接受） |

---

## 5️⃣ 行动清单（Check‑list）

### 立即（24 h 内）
- [ ] 轮换所有 **Critical** SQL 注入中的 `schema`、`tenant_schema` 参数化修复。
- [ ] 轮换所有 **High** 密钥泄露（SECRET_KEY、PASSWORD、auth_me 等），并在对应平台（如 AWS、数据库）禁用旧密钥。
- [ ] 执行 `git filter-branch`（或等价历史重写）彻底删除 **High** 泄露文件。

### 短期（48 h 内）
- [ ] 将 **Medium** GitHub Action 改为 commit‑hash 锁定。
- [ ] 对 `export_jobs.py` 中的 `meta_path` 加入路径白名单。
- [ ] 将 **Low** 测试/文档/性能脚本中的硬编码密钥改为环境变量或动态生成。
- [ ] 将所有 **Low** `assert` 替换为异常抛出。

### 中期（1 周内）
- [ ] 在 CI 中加入 **detect‑secrets** / **truffleHog** 扫描，防止新泄露。
- [ ] 将 `.secrets.baseline` 删除并加入 `.gitignore`，改用集中密钥管理。
- [ ] 更新 **Docker‑Compose**、**Kubernetes** 配置，使用 `secrets:` 或 **External Secrets Operator**。
- [ ] 对 `dfljeff01‑commits` 提交进行代码审查，确保后续没有类似失误。

### 长期（2 周内）
- [ ] 完成 **SAST**、**Secrets** 持续集成（每次 PR 自动扫描）。
- [ ] 制定并发布《密钥管理手册》，组织团队安全培训。
- [ ] 部署 **WAF** 与 **数据库审计**，并建立监控报警。

---

## 6️⃣ 结论

- 本次审计共发现 **31 条**安全风险（10 Critical SQL 注入、9 High 密钥泄露、4 Medium CI/文件读取、8 Low 测试/文档/assert）。
- **SQL 注入**与**密钥泄露**属于 **最高优先级**，必须在 **24‑48 h**内完成修复，否则可能导致数据库被完全控制、跨租户泄露或服务被横向渗透。
- **CI Action 锁定**、**文件读取**风险相对可控，但仍需在 **1 周**内完成，以防止供应链攻击或信息泄露。
- **测试/文档/assert**等低风险问题可在本迭代结束时统一清理，但建议在 **2 周**内全部落实，以防后患。

> **关键点**：所有泄露密钥仍在 Git 历史中存在，必须手动标记为已解决并彻底清除；仅删除文件本身并不能消除风险。

执行上述行动后，建议再次运行 SAST 与 Secrets 扫描，确保 **所有问题均为“已关闭”**，并记录审计报告以备合规检查。祝项目顺利加固，安全无虞！ 🚀
