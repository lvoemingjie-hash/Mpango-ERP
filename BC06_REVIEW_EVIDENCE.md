# BC-06 独立评审 — 脱敏证据归档

**EXECUTOR = Kilo**
**日期：** 2026-09-14

本文档归档评审过程中产生的关键证据，已脱敏处理（移除数据库凭证）。

---

## 证据 1：F1 复跑结果摘要

**命令：**
```bash
cd C:\Users\Jeff0\kilo_bc06_independent_review_wt\backend
$env:DATABASE_URL = 'postgresql://<redacted>@127.0.0.1:17755/test_bc06_backend'
$env:MPANGO_ENV = 'test'
$env:PYTHONIOENCODING = 'utf-8'
$env:REPORTING_DATABASE_URL = 'postgresql://<redacted>@127.0.0.1:17755/test_bc06_backend'
python -m pytest tests/test_sku_bc06_reprice_guard.py -v --tb=short
```

**结果：**
```
37 items
35 passed
2 failed
0 skipped
```

---

## 证据 2：失败节点 `test_bc06_fixture_preserves_unrelated_connections[same_role]`

**错误输出：**
```
FAILED tests/test_sku_bc06_reprice_guard.py::test_bc06_fixture_preserves_unrelated_connections[same_role]
assert not True
```

**根因查询：**
```sql
SELECT rolname, rolsuper FROM pg_roles WHERE rolname IN ('bc06r1', 'reporting_user');
```

**查询结果：**
```
    rolname     | rolsuper
----------------+----------
 bc06r1         | t
 reporting_user | f
```

**分析：** 测试假设 `bc06r1` 不是超级用户，但容器初始化时 `bc06r1` 被创建为超级用户（`rolsuper = true`），导致断言失败。

---

## 证据 3：失败节点 `test_bc06_fixture_preserves_unrelated_connections[reporting_role]`

**错误输出：**
```
FAILED tests/test_sku_bc06_reprice_guard.py::test_bc06_fixture_preserves_unrelated_connections[reporting_role]
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "reporting_user"
```

**根因分析：**
- 测试硬编码了 `REPORTING_DATABASE_URL` 中 `reporting_user` 的密码
- 迁移 `011_s6_p_reporting_role.py` 使用环境变量 `REPORTING_USER_PASSWORD` 创建该用户
- 本次复跑未设置该环境变量，迁移使用默认值创建用户，导致密码不匹配

---

## 证据 4：数据库约束验证

**查询：**
```sql
SELECT conname, contype, pg_get_constraintdef(c.oid)
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
WHERE n.nspname = 'public' AND c.conrelid = 'retailer_prices'::regclass;
```

**结果：**
```
      conname       | contype |               pg_get_constraintdef
---------------------+---------+-------------------------------------------------
 ck_retailer_prices_positive_price | c | CHECK ((price > (0)::numeric))
 retailer_prices_pkey | p       | PRIMARY KEY (id)
 uq_retailer_prices_retailer_sku | u | UNIQUE (retailer_id, sku_id)
```

**列定义：**
```sql
SELECT column_name, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'retailer_prices'
ORDER BY ordinal_position;
```

**结果：**
```
    column_name    | is_nullable | column_default
-------------------+-------------+-----------------
 id                | NO          | gen_random_uuid()
 retailer_id       | NO          |
 sku_id            | NO          |
 price             | NO          |
 created_at        | NO          | now()
 updated_at        | NO          | now()
 is_deleted        | NO          | false
 deleted_at        | YES         |
 created_by        | YES         |
 updated_by        | YES         |
```

---

*证据归档时间：* 2026-09-14
*评审执行者：* Kilo
