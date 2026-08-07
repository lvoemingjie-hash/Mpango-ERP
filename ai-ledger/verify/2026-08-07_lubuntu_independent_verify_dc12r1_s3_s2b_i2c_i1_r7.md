# Lubuntu 独立验证指令 — DC-12R1-S3-S2B-I2C-I1-R7

> **性质:** 未经 CTO 授权的自行验证(self-initiated,pre-CTO-review)。
> **背景:** R7 (`4c322c2a`) 已推送至远端。CTO 下周一(2026-08-10)统一审查。
>   本验证在 CTO 审查前由 Lubuntu 独立执行,目的是排除本机 worktree 环境对
>   `git diff` 静态守卫的干扰,给出一份非 worktree checkout 下的干净证据。
> **执行者:** Lubuntu(独立环境,非 Zcode 主机会话)。
> **被验证提交:** `4c322c2ac8568d9d1afe04c8968058f8a1c6b90f`
> **分支:** `zcode/dc12r1-s3-s2b-i2c-i1-printable-records-backend-2026-08-04`
> **基线(上一轮 R6):** `f5d06342ae34a3f1e7a1916306950fe41ec0d4d2`

---

## 0. 验证目标

R7 仅修改 2 个文件,**无生产代码变更**:

1. `backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py`
   - R7-1: 用生产链路安全的 PostgreSQL 诊断助手
     `_extract_constraint_name(exc_info.value) == "ux_payments_receipt_number"`
     替换异常文本子串匹配(不解析人类可读异常文本)。
   - R7-2: `try/finally` 真正覆盖**每一个**变异 seed 步骤——
     `oid=None, pay1_id, pay2_id, did=None` 在 `try` 之前初始化;
     订单创建移入 `try`;`finally` 清理全部 ID。
   - R7-3: 保留对 order + pay1_id + pay2_id 的 fresh-session 逐 ID 零残留检查。
2. `ai-ledger/product-ai/2026-08-04_dc12r1_s3_s2b_i2c_i1_printable_records_backend.md`
   - R7 真相:精确命令、新端口、真实总数,无夸大,无过期 R6 标题。

Lubuntu 须独立确认:
- (A) R7 的 3 项代码修正确实存在于 `4c322c2a`。
- (B) printable-records 测试套件(36 用例)在两个独立 PG16/Redis7 栈上 0 failed / 0 errors。
- (C) 全后端套件在非 worktree checkout 下无本机出现的 2 个 `git-diff` 守卫失败。
- (D) R7 diff 只触及上述 2 个允许文件,不触及任何禁止路径。

---

## 1. 前置环境(独立、非 worktree)

Lubuntu 须使用一个**完整 git clone(非 worktree)**,使静态守卫
`git diff --name-only <BASE_REF>` 能正确解析。

```bash
# 1.1 独立 clone(Linux/Lubuntu,非 Zcode 主机的 worktree)
git clone <repo-url> /opt/mpango-i2ci1-r7-verify
cd /opt/mpango-i2ci1-r7-verify
git fetch origin zcode/dc12r1-s3-s2b-i2c-i1-printable-records-backend-2026-08-04
git checkout 4c322c2ac8568d9d1afe04c8968058f8a1c6b90f

# 1.2 确认 HEAD 与 worktree 类型
git rev-parse HEAD          # 必须输出 4c322c2ac8568d9d1afe04c8968058f8a1c6b90f
git rev-parse --git-dir     # 必须是 .git(目录),不是 gitdir: 指针文件
cat .git/HEAD               # 完整 clone 应输出 ref: refs/heads/...
```

依赖(精确锁定版本,与 R7 一致):
`python>=3.11`, `fastapi==0.128.0`, `starlette==0.50.0`, `anyio==4.12.1`,
`httpx==0.28.1`, `sqlalchemy==2.0.45`, `asyncpg==0.31.0`, `alembic==1.18.1`,
`pytest==8.4.2`, `pytest-asyncio==0.26.0`, `pytest-cov==4.1.0`,
`hypothesis==6.150.2`, `bcrypt>=4.0,<4.1`, `openpyxl==3.1.5`, `redis`。
推荐直接用 `pip install -r backend/requirements.txt` 再装 dev/test 组。

---

## 2. 两个独立栈(顺序执行,避免资源争用)

```bash
# 栈 A: PG 59355 / Redis 59356
docker run -d --name lubuntu_r7a_pg \
  -e POSTGRES_PASSWORD=<pw> -e POSTGRES_USER=mpango -e POSTGRES_DB=mpango_erp \
  -p 59355:5432 postgres:16-alpine
docker run -d --name lubuntu_r7a_redis -p 59356:6379 redis:7-alpine

# 栈 B: PG 59357 / Redis 59358
docker run -d --name lubuntu_r7b_pg \
  -e POSTGRES_PASSWORD=<pw> -e POSTGRES_USER=mpango -e POSTGRES_DB=mpango_erp \
  -p 59357:5432 postgres:16-alpine
docker run -d --name lubuntu_r7b_redis -p 59358:6379 redis:7-alpine
```

每栈创建 test-safe 数据库与用户(守卫拒绝用户名 `mpango`/含 `prod`,
数据库名必须匹配 `^(?:test|pytest|ci)[_-][a-z0-9_-]+$`):

```bash
docker exec lubuntu_r7a_pg psql -U mpango -d mpango_erp -c \
  "CREATE USER test_user WITH PASSWORD '<disposable>' CREATEDB SUPERUSER;"
docker exec lubuntu_r7a_pg psql -U mpango -d mpango_erp -c \
  "CREATE DATABASE test_mpango OWNER test_user;"
# 栈 B 同样(对 lubuntu_r7b_pg)
```

每栈执行迁移:

```bash
cd /opt/mpango-i2ci1-r7-verify
# 栈 A
DATABASE_URL="postgresql+asyncpg://test_user:<pw>@127.0.0.1:59355/test_mpango" \
  alembic -c backend/alembic.ini upgrade head
# 栈 B(端口 59357)
```

---

## 3. 必需环境变量(守卫要求)

测试 conftest 与 `async_test_utils.py` 强制以下环境,缺一即 RuntimeError:

```bash
export MPANGO_ENV=test
export MPANGO_ALLOW_TEMP_DB_CREATE=1
export MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost,postgres
export MPANGO_TEMP_DB_ALLOWED_PORTS=59355,59357   # 用哪个栈就列哪个
export POSTGRES_HOST=127.0.0.1
export POSTGRES_USER=test_user
export POSTGRES_PASSWORD=<pw>
export POSTGRES_DB=test_mpango
export TEST_DATABASE_URL="postgresql://test_user@127.0.0.1:59355/test_mpango"
export REPORTING_USER_PASSWORD=<pw>
export REDIS_URL=redis://127.0.0.1:59356/0
```

> 注意:`TEST_DATABASE_URL` 主机必须在 `MPANGO_TEMP_DB_ALLOWED_HOSTS` 内,
> 端口必须在 `MPANGO_TEMP_DB_ALLOWED_PORTS` 内,用户名不能是 `mpango` 或含 `prod`,
> 数据库名必须以 `test`/`pytest`/`ci` 开头。`real_alembic` 测试会校验
> `TEST_DATABASE_URL` 与临时库 source 的连接身份完全一致。

---

## 4. 验证步骤 A — R7 代码修正确实存在

```bash
cd /opt/mpango-i2ci1-r7-verify
# A.1 精确诊断助手(非子串匹配)
grep -n "_extract_constraint_name(exc_info.value)" \
  backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py
# 期望:断言行出现,且与 "ux_payments_receipt_number" 精确相等

# A.2 无 str(exc_info.value) 子串匹配残留
grep -n 'str(exc_info.value)\|"ux_payments_receipt_number" in' \
  backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py
# 期望:无匹配(R6 的子串断言已删除)

# A.3 全部 4 个 ID 在 try 之前初始化
grep -n "oid: uuid.UUID | None = None\|pay1_id = uuid.uuid4()\|pay2_id = uuid.uuid4()\|did = None" \
  backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py
# 期望:TestForcedSeedFailureCleanup 中 4 行均在 try: 之前

# A.4 订单创建在 try 内部
sed -n '/class TestForcedSeedFailureCleanup/,/Step 1/p' \
  backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py | grep -n "oid = await _seed_confirmed_order"
# 期望:该行出现在 try: 之后、Step 1 之前
```

---

## 5. 验证步骤 B — printable-records 套件两栈 0 failed

```bash
cd /opt/mpango-i2ci1-r7-verify/backend
# 栈 A(端口 59355/59356)
POSTGRES_PORT=59355 REDIS_URL=redis://127.0.0.1:59356/0 \
  python -m pytest tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py \
  -p no:cacheprovider -q
# 期望:36 passed, 0 failed, 0 errors

# 反序(顺序无关性证明:先跑清理/谓词类,再跑全套)
python -m pytest \
  tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py::TestForcedSeedFailureCleanup \
  tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py::TestSameSchemaPredicateProof \
  tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py::TestBindingDenial \
  tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py \
  -p no:cacheprovider -q
# 期望:先跑的用例通过,全套 36 通过(无残留)

# 栈 B(端口 59357/59358)— 同上,改端口
```

---

## 6. 验证步骤 C — 全后端套件(关键:非 worktree)

这是本验证的核心价值。Zcode 主机用 worktree,`.git` 指针在容器内不可解析,
导致 2 个静态守卫失败(`test_u6h2`/`test_u6h3` 的
`test_forbidden_wholesaler_api_crud_repository_and_bootstrap_files_are_untouched`)。
Lubuntu 用完整 clone,**这两个守卫应当通过**。

```bash
cd /opt/mpango-i2ci1-r7-verify/backend
# 栈 A — 全后端(顺序,不并行)
POSTGRES_PORT=59355 REDIS_URL=redis://127.0.0.1:59356/0 \
  python -m pytest tests/ -p no:cacheprovider -q -rf --tb=line \
  > /tmp/lubuntu_gate_a.log 2>&1; echo "exit=$?"
tail -4 /tmp/lubuntu_gate_a.log
# 栈 B — 全后端(改端口 59357/59358)
```

**Lubuntu 关键判定:**
- Zcode 主机报告:3162 passed, 100 skipped, 15 xfailed, **2 failed**, 0 errors
  (2 failed = u6h2/u6h3 静态 git-diff 守卫,worktree 工件)
- Lubuntu 完整 clone **期望**:3162 passed, 100 skipped, 15 xfailed,
  **0 failed**, 0 errors(2 个守卫通过)
- 若 Lubuntu 仍出现这 2 个失败,请记录 `git rev-parse --git-dir` 输出与
  `git diff --name-only 6a8ddcf348e9b1bdcc902929011e6212cc675cf8` 的前若干行,
  以便 CTO 判断是 clone 类型还是真问题。

---

## 7. 验证步骤 D — R7 diff 只触及允许文件

```bash
cd /opt/mpango-i2ci1-r7-verify
# D.1 R7 vs R6 只改 2 文件
git diff --stat f5d06342 4c322c2a
# 期望仅:
#   ...printable_records_backend.md
#   .../test_dc12r1_s3_s2b_i2c_i1_printable_records.py

# D.2 禁止路径交集为空(u6h2/u6h3 守卫的断言)
git diff --name-only 6a8ddcf348e9b1bdcc902929011e6212cc675cf8 -- \
  | grep -Fx \
    -e backend/models/wholesaler.py \
    -e backend/api/v1/wholesalers.py \
    -e backend/crud/wholesaler.py \
    -e backend/repositories/wholesaler_repository.py \
    -e backend/api/v1/platform/tenants.py \
    -e backend/api/v1/platform/stats.py
# 期望:无输出(交集为空 → 守卫通过)

# D.3 静态质量
git diff --check                          # 期望:clean
python -m py_compile backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py
detect-secrets scan backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py \
  ai-ledger/product-ai/2026-08-04_dc12r1_s3_s2b_i2c_i1_printable_records_backend.md
# 期望:0 secrets
```

---

## 8. Lubuntu 回执要求

请在 `ai-ledger/verify/` 下产出回执(建议文件名
`2026-08-07_lubuntu_verify_result_dc12r1_s3_s2b_i2c_i1_r7.md`),至少包含:

1. 执行环境:Lubuntu 主机标识、git clone 类型(`git rev-parse --git-dir` 输出)、
   Docker 版本、PG/Redis 镜像 digest。
2. 步骤 A 4 项 grep 结果(每项 pass/fail)。
3. 步骤 B 两栈 printable-records 套件精确总数(passed/failed/errors/skipped)。
4. 步骤 C 两栈全后端套件精确总数 + 完整 `FAILED` 行列表。
   **特别声明 u6h2/u6h3 两个守卫在 Lubuntu 是否通过。**
5. 步骤 D 禁止路径交集是否为空。
6. 一句话结论:`INDEPENDENT_VERIFY_PASS` 或 `INDEPENDENT_VERIFY_FAIL_<reason>`。

回执交回后,等 CTO 下周一(2026-08-10)统一审查 R7 + Lubuntu 回执,
再决定是否进入 controlled merge。

---

## 9. 边界(不得越界)

- 不得修改任何生产代码、迁移、前端、配置、依赖。
- 不得推送到受保护分支。
- 不得启动 I2C-I2 / I2C-I3 / Contract D / events / outbox / migration 038。
- 本验证仅为证据收集,不替代 CTO 审查;CTO 审查前不合并。
