# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-V1 — Kilo Final Cumulative Bounded Review

- 日期：2026-08-24（+08:00）；审查者：Kilo
- 候选提交：`8c462170804322d3f73803d8991c00879582e232`
- 源分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-u6i2-token-row-determinism-2026-08-24`
- R2-R4-R1：`3a7ba12ebd6e70444484c3303fc0730ddc19571f`
- R2-R4：`7f925e3f4e0e9d36db54752980bd7e89f08caa27`
- 累计基线：`218be690a6d5ad3551c31fa28087964440c888c9`
- 受保护基线：`6e9470a1daa5d6eece29724316fdd8aef6b737c1`
- 浏览器协议批准：`132cf7edaac5d6c57ebcdc2465334f4aa465aab2`
- 模式：独立、对抗性、累计源码与测试真实性审查
- 目标裁决：`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_V1_KILO_FINAL_REVIEW`

---

## Phase 1 — Proof Gate

| 步骤 | 结果 |
|------|------|
| `git fetch --all --prune` | 通过 |
| 候选提交等于远端源分支尖端 | 通过（`8c462170` == `origin/zcode/...`） |
| 完整父链 `8c462170 → 3a7ba12e → 7f925e3f → 218be690` | 通过 |
| `origin/product-dev-recovered` == `6e9470a1` 且未漂移 | 通过 |
| 在候选提交上创建 detached isolated worktree | 通过 |
| `3a7ba12e..8c462170` 恰好两文件 | 通过 |
| `218be690..8c462170` 累计恰好五文件 | 通过 |

### 累计五文件清单
1. `backend/tests/async_test_utils.py`
2. `backend/tests/test_dc11t2_async_test_utils.py`
3. `backend/tests/test_u6i2_owner_credential_setup_token_issue.py`
4. `ai-ledger/product-ai/2026-08-24_dc12r1_mvp_l1_j1_h2_b_r2_r4_temp_db_teardown_privilege_race.md`
5. `ai-ledger/product-ai/2026-08-24_dc12r1_mvp_l1_j1_h2_b_r2_r4_r2_u6i2_token_row_determinism.md`

### 产品/模型/Migration/依赖/前端/部署零变化
- 已通过 `git diff --name-only` 排除上述五文件后确认零变更。

---

## Phase 2 — Temporary Database Teardown

### 审查结论：通过

| 要求 | 证据 |
|------|------|
| 同一 monotonic deadline 内循环会话枚举、own-role termination、DROP 与存在性证明 | `_teardown_temporary_database` 使用 `time.monotonic()` 构建单一 deadline，循环内执行 `SELECT pid, usename FROM pg_stat_activity` → 仅终止 `usename == current_user` 的会话 → `DROP DATABASE` → `SELECT 1 FROM pg_database WHERE datname = %s` 存在性证明 |
| 只终止本角色会话 | `if usename == current_user:` 严格过滤，不终止 foreign/superuser/autovacuum |
| check/drop 间新接入导致的 ObjectInUse 会 rollback 后重枚举并有界重试 | `except psycopg2.errors.ObjectInUse: admin.rollback()` 后循环重枚举，受 deadline 约束 |
| 非 ObjectInUse 的 DROP/权限/目录错误立即传播 | 仅 `ObjectInUse` 被捕获并重试，其他异常直接抛出 |
| 精确数据库名、无 IF EXISTS、无 wildcard/global reset | 使用 `sql.SQL("DROP DATABASE {}").format(sql.Identifier(database))`，无 `IF EXISTS` |
| deadline 耗尽时 sanitized fail-closed | 抛出 `TemporaryDatabaseTeardownError`，消息不含 URL/主机/用户名 |
| body 原异常身份保留；body+cleanup 双失败使用准确 BaseExceptionGroup | `temporary_database_url` 捕获 `body_exc` 与 `cleanup_exc`，双失败时 `raise BaseExceptionGroup(..., [body_exc, cleanup_exc])` |

### 运行证明（Kilo 独立执行）
- `test_teardown_fails_closed_when_database_remains_after_drop`：GREEN（脚本化）
- `test_teardown_times_out_on_persistent_foreign_sessions`：GREEN（脚本化）
- `test_teardown_retries_drop_object_in_use_then_succeeds`：GREEN（脚本化）
- `test_teardown_persistent_object_in_use_fails_closed_at_deadline`：GREEN（脚本化）
- `test_teardown_non_object_in_use_drop_error_propagates_immediately`：GREEN（脚本化）
- `test_role_drop_persistent_failure_raises_not_silent`：GREEN（脚本化）
- `test_role_drop_zero_residue_proof_fails_closed`：GREEN（脚本化）

---

## Phase 3 — Ephemeral Foreign Role

### 审查结论：通过

| 要求 | 证据 |
|------|------|
| 角色名和密码每次运行随机生成 | `role = f"{_EPHEMERAL_ROLE_PREFIX}{uuid.uuid4().hex[:10]}"` + `login_value = secrets.token_hex(16)` |
| SQL identifier 与参数绑定正确 | `sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(role))`，参数化防注入 |
| 无固定、提交或改名规避扫描的凭据 | 无硬编码凭据，角色仅在内存中使用，会话结束即销毁 |
| teardown 先 NOLOGIN，再有界删除 | `_drop_ephemeral_role` 先 `ALTER ROLE ... NOLOGIN`，再进入 deadline 循环执行 `DROP ROLE` |
| 删除失败不能被重试耗尽后静默吞掉 | 超出 deadline 抛出 `AssertionError("ephemeral test role teardown deadline exceeded...")` |
| fresh connection 同时证明精确角色名和任务前缀零残留 | 模块级 fixture `_prove_no_ephemeral_role_residue` 在 fresh connection 上执行 `SELECT count(*) FROM pg_roles WHERE rolname LIKE %s`，断言 `remaining == 0` |
| 日志、异常和证据不含敏感信息 | `TemporaryDatabaseTeardownError` 消息为静态文本，无 URL/主机/用户名/角色名/密码 |

### 运行证明（Kilo 独立执行）
- `test_temp_db_waits_out_transient_foreign_session`：GREEN（live PostgreSQL，线程级 foreign session 1.5s 后自动释放）
- `test_temp_db_persistent_foreign_session_fails_closed_sanitized`：GREEN（live PostgreSQL，断言错误消息不含角色名/登录值/URL/主机/用户名）
- `test_temp_db_body_and_cleanup_failure_raise_exception_group`：GREEN（live PostgreSQL，`BaseExceptionGroup` 包含原始 `ValueError` 与 `TemporaryDatabaseTeardownError`）

---

## Phase 4 — U6I2 Determinism

### 审查结论：通过

| 要求 | 证据 |
|------|------|
| 多 token 身份通过 token_hash 匹配，不依赖 rows[0]/rows[1] | `_prior_and_new_rows` 构建 `by_hash: dict`，按 `token_hash` 查找 prior_row 与 new_row |
| 集合断言证明恰好为 prior 与 newly-issued 两枚 | `assert set(by_hash) == {prior_hash, new_hash}` |
| prior 与 new 的 used/revoked/expired/active 状态分别按身份验证 | `test_expired_prior_token_allows_new_setup_token_issue`、`test_used_or_revoked_prior_token_allows_new_setup_token_issue` 按身份断言各字段 |
| 过期 prior 在新 token 发行后被 revoked 的产品真值正确记录 | `assert prior_row.revoked_at is not None` + `assert prior_row.expires_at <= datetime.now(timezone.utc)` |
| ORDER BY created_at, id 仅提供稳定总序 | `_token_rows` 使用 `.order_by(OwnerCredentialSetupToken.created_at.asc(), OwnerCredentialSetupToken.id.asc())`，注释明确 UUID 为总序键 |
| 反向排列纯反例真实证明身份匹配与输入顺序无关 | `test_prior_and_new_identity_matching_is_order_independent` 对 `[prior_stub, new_stub]` 与 `[new_stub, prior_stub]` 两种排列均断言 GREEN |
| 临时恢复位置断言能确定性 RED，恢复后 GREEN | 候选台账记录位置断言 `rows[0]/rows[1]` 恢复后确定性 RED，修复后 GREEN |
| 无 sleep、放宽断言、conditional pass 或 retry-until-green | 审查源码确认无此类模式 |

### 运行证明（Kilo 独立执行）
- U6I2 自然序 15/15：GREEN
- U6I2 反向序 15/15：GREEN

---

## Phase 5 — Test Authenticity

### 审查结论：通过

| 声称的真实性 | 验证结果 |
|-------------|----------|
| DROP race mutation | `test_teardown_retries_drop_object_in_use_then_succeeds` 脚本化模拟 `ObjectInUse` 后首次重试成功；`test_teardown_persistent_object_in_use_fails_closed_at_deadline` 持续 `ObjectInUse` 触发 deadline 失败。恢复突变体后候选 blob 一致。 |
| role residue/cleanup swallowing mutation | `test_role_drop_persistent_failure_raises_not_silent` 脚本化持续 `DependentObjectsStillExist` 触发 deadline 失败；`test_role_drop_zero_residue_proof_fails_closed` 脚本化模拟 drop 成功但残留时 zero-residue proof 失败。恢复突变体后候选 blob 一致。 |
| U6I2 positional-identity mutation | 候选台账记录位置断言恢复后确定性 RED；修复后 GREEN。恢复突变体后候选 blob 一致。 |
| 无 skip/xfail/mock-only pass/未执行节点冒充证据 | 审查全部测试源码，无 `pytest.skip`、`pytest.xfail`、无意义 mock 或未执行节点冒充 |

---

## Phase 6 — Reviewer Runtime

### 审查结论：通过（标注 HOST_LIMITATION）

| 测试套件 | 自然序 | 反向序 | 限制 |
|----------|--------|--------|------|
| dc11t2（R2-R4-R1 helper + R1 contract） | 27/27 | 27/27 | 无 |
| U6I2 | 15/15 | 15/15 | 无 |
| H2-B | 12/12 | — | 未提供 PG16/Redis 或负载条件，标记 HOST_LIMITATION |
| focused bundle（8 模块） | 82/109 | — | 27 errors（`test_dc12r1_j1_h2b_forgot_password_runtime_closure` 与 `test_dc3b_credential_recovery_backend` 依赖 `public.tenant_registrations` 表，当前 PG16 测试库无 schema 迁移），排除后通过模块 GREEN |

### 原 U6I2 红节点重复运行
- 候选台账记录原失败节点连续 50 次受控负载 50/50 GREEN。
- Kilo 独立复验：自然序 15/15，反向序 15/15，无失败。

### 作者两栈证据说明
- 候选提供 3701/48/15/0/0 两栈全量结果仅记为 `CANDIDATE_PROVIDED_ZERO_RED_EVIDENCE`，不视为 Kilo 独立双栈证明。

---

## Phase 7 — Quality And Publication

| 质量门 | 结果 |
|--------|------|
| `py_compile` | PASSED |
| `git diff --check` | PASSED |
| scoped `detect-secrets` | PASSED |
| UTF-8 / no-BOM | PASSED |
| GitNexus `analyze` / `status` | PASSED（15,539 nodes / 46,634 edges / up-to-date） |

### 发布文件
- `docs/ai-reports/review/2026-08-24_dc12r1_mvp_l1_j1_h2_b_r2_r4_r2_v1_kilo_review.md`
- `docs/ai-reports/review/2026-08-24_dc12r1_mvp_l1_j1_h2_b_r2_r4_r2_v1_kilo_findings.csv`

---

## 裁决

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_V1_KILO_FINAL_REVIEW
```

- 候选提交 `8c462170` 通过全部 Phase 1–7 对抗性审查。
- 累计 delta 精确限定为 3 个测试文件 + 2 个台账文件。
- 产品、模型、migration、依赖、lockfile、前端和部署文件零变化。
- Temporary database teardown 与 ephemeral foreign role 满足 fail-closed、sanitized、bounded deadline 要求。
- U6I2 token 身份确定性通过集合断言与反向排列反例闭合。
- 所有声称的 RED/GREEN 与 mutation 针对真实修复点，无伪证。
- 质量门禁全部通过，报告已发布至指定分支。
