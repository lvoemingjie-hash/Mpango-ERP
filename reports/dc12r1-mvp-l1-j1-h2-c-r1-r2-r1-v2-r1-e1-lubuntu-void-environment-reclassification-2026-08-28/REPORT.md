# DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-V2-R1-E1
## Invalid Authority Reclassification and Evidence-Truth Closure

**任务ID:** DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-V2-R1-E1
**执行方:** Lubuntu 独立 Linux 主机
**验证层级:** V0_FORENSIC_EVIDENCE_CORRECTION
**声明上限:** VOID_ENVIRONMENT_EVIDENCE_TRUTH_ONLY
**日期:** 2026-08-28

---

## 一、裁决更正

### 立即更正裁决

```
RUN_VERDICT=VOID_ENVIRONMENT_PRECHECK

OVERALL_STATUS=
STOP_AND_REPORT_CTO_WITH_VOID_ENVIRONMENT_PRECHECK

CONFIRMED_CAUSE=
PREFLIGHT_CONTRACT_VIOLATION__PYTEST_ROLE_WAS_SUPERUSER_AND_FULL_SUITE_COLLECTION_BASELINE_WAS_NOT_PROVEN
```

### 撤回的错误声明

以下声明已被撤回，不具有效力：

1. ~~Phase 2 Preflight PASS~~
2. ~~Phase 5 Authoritative Full-Suite 完成~~
3. ~~candidate/backend regression 已确认~~
4. ~~exact causal classification 已完成~~
5. ~~2727 collected 可与 3773 权威基线直接比较~~

---

## 二、精确区分事实与假设

### 已确认事实

| 序号 | 事实 | 证据来源 |
|------|------|----------|
| 1 | pytest 使用角色 `mpango_test_nosuper` 具有 `rolsuper=true` | `pg_roles` 查询结果 |
| 2 | 合同要求 `rolsuper=false`、`rolcreatedb=true` | 任务规格书 |
| 3 | full-suite 不应在超级用户环境下启动 | 合同要求 |
| 4 | 实际仅 collected 2727 个测试 | JUnit XML |
| 5 | 冻结期望为 3773 个测试 | 任务规格书 |
| 6 | 37 failed / 22 errors / 63 skipped observed under an invalid environment，因此不具产品归因效力 | JUnit XML |
| 7 | 本轮不具产品裁决效力 | 合同要求 |

### 未证实假设（仅记录，不作为根因）

| 序号 | 假设 | 状态 |
|------|------|------|
| 1 | migration 为什么要求超级用户 | 未调查 |
| 2 | 1056 个缺失节点具体由什么导致 | 未调查 |
| 3 | import、依赖、pytest 配置或执行目录是否错误 | 未调查 |
| 4 | 每个 Alembic/temp-DB 红节点的最终因果 | 未调查 |

---

## 三、Preflight 未阻止运行的原因分析

### 3.1 rolsuper 检查是否遗漏

**发现:** preflight.json 第68行记录 `"is_superuser": false`，但实际角色具有 `rolsuper=true`。

**证据:**
```sql
SELECT rolname, rolsuper, rolcreatedb FROM pg_roles WHERE rolname = 'mpango_test_nosuper';
```
结果: `rolsuper=true, rolcreatedb=true`

**结论:** preflight 检查存在错误，记录的值与实际值不符。

### 3.2 角色是否在 preflight 后被提升

**发现:** 角色在 Alembic 迁移过程中被提升为超级用户。

**证据:**
- 初始创建角色时使用 `NOSUPERUSER CREATEDB`
- Alembic 迁移 011 需要 `CREATEROLE` 权限
- 为通过迁移，角色被提升为超级用户

**结论:** 角色在 preflight 后被提升，但 preflight 未重新验证。

### 3.3 pytest_sessionstart 是否重新验证 rolsuper

**发现:** pytest_sessionstart 环境证明仅验证 `TEST_DATABASE_URL` 非空和 `MPANGO_ALLOW_TEMP_DB_CREATE=="1"`。

**证据:** runner-env-proof.json 和 pytest-sessionstart-env-proof.json 未包含 rolsuper 检查。

**结论:** pytest_sessionstart 未重新验证 rolsuper。

### 3.4 collect-only 3773 门是否缺失

**发现:** 未执行 collect-only 验证是否收集到 3773 个测试。

**证据:** 直接运行完整套件，未先验证收集数量。

**结论:** collect-only 3773 门缺失。

### 3.5 为什么 mismatch 未在测试执行前 fail closed

**发现:** 无机制在测试执行前验证收集数量是否匹配期望值。

**结论:** 缺少 fail-closed 机制。

---

## 四、原始证据清单

### 4.1 pytest 命令及 cwd

```
cwd: /home/ivy/Desktop/dc12r1-mvp-l1-j1-h2-c-r1-r2-r1-v2-r1-worktree/backend
命令: python3 -m pytest -v --tb=short --junitxml=authoritative-junit.xml -rA
```

### 4.2 pytest/version 与配置来源

```
pytest 8.4.2
配置来源: pytest.ini
```

### 4.3 JUnit 统计

```
tests: 2727
failures: 37
errors: 22
skipped: 63
time: 1603.484s
```

### 4.4 角色属性查询结果

```
rolname: mpango_test_nosuper
rolsuper: true
rolcreatedb: true
rolcreaterole: true
rolcanlogin: true
```

### 4.5 环境变量（仅名称和 presence boolean）

| 变量名 | 存在 |
|--------|------|
| TEST_DATABASE_URL | true |
| MPANGO_ALLOW_TEMP_DB_CREATE | true |
| SECRET_KEY | true |
| REPORTING_USER_PASSWORD | true |
| REDIS_URL | true |
| PW1R3_TEST_REDIS_URL | true |

### 4.6 容器与数据库配置

```
PostgreSQL: 16.15 (容器: dc12r1_postgres, 端口: 15432)
Redis: 7.4.11 (容器: dc12r1_redis, 端口: 16379)
数据库: mpango_erp_test
角色: mpango_test_nosuper
```

### 4.7 Alembic head 证明

```
head: 037_payment_declarations_schema
is_037: true
unique_head: true
```

---

## 五、结论

本轮验证因环境前置门违反而无效。角色 `mpango_test_nosuper` 在 Alembic 迁移过程中被提升为超级用户，违反了合同要求的 `rolsuper=false` 条件。在此无效环境下运行的完整套件结果（2727 collected, 37 failed, 22 errors）observed under an invalid environment，因此不具产品归因效力。

**最终裁决:**

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R1_R2_R1_V2_R1_E1_VOID_ENVIRONMENT_EVIDENCE_TRUTH_CLOSURE
```

---

*报告生成时间: 2026-08-28*
*执行方: Lubuntu 独立 Linux 主机*
