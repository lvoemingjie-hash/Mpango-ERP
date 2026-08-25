# DC-12R1-MVP-L1-J1-H2-B-R3-R1 — 用户角色分配异步序列化收口（User Role Assignment Async Serialization Closure）

- 日期：2026-08-26（+08:00）；执行者：ZCode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r3-r1-user-role-assignment-async-serialization-closure-2026-08-26`
  （自候选父提交 `0267ea73b77c1246232124278892de11739f408e` = H2-B-R3 tip 创建）
- 接受证据核对：Kilo source review `f795e0fb…`、Lubuntu STOP `9d6b3e43…`、
  冻结 harness `8c7e84779cc1810baab32859d3dc353e1028384a` 均未触碰；
  HE2 治理分支未成为本产品分支 base（分支唯一父 = `0267ea73`）。
- 裁决目标：`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R3_R1_MERGE_REVIEW`

## 1. 确认因果链（实现前锁定，实测复核一致）

`PUT /api/v1/users/{user_id}/roles`：
`assign_user_roles_endpoint → assign_roles_to_user → user_to_read`

1. `User.updated_at` 带 SQL 表达式 onupdate（`models/base.py` AuditMixin：
   `onupdate=func.now()`）。`user.roles = roles` + `await db.flush()` 产生
   UPDATE，其 `updated_at = now()` 为服务端求值 —— flush 后该 scalar 过期
   （post-fetch，客户端不知值）。
2. 旧代码 `await db.refresh(user, ["roles"])` 是**局部** refresh：SQLAlchemy
   2.0.45 语义（已读安装源码 docstring 证实）—— 只 expire+重载**命名**属性；
   `updated_at` 保持过期。
3. `user_to_read(user)` 同步读 `user.updated_at`（users.py:55）→ 过期属性
   触发隐式 IO → AsyncSession 无 greenlet 上下文 →
   `sqlalchemy.exc.MissingGreenlet` → 已成功提交的角色分配对客户端变 500。
4. RED 实证（修复前，真实 PG16+ASGI+正式供给链）traceback 精确命中：
   `users.py:315 assign_user_roles_endpoint → users.py:55 updated_at=user.updated_at
   → orm/state.py _load_expired → MissingGreenlet`。

## 2. GitNexus impact（编辑前门禁）

- 本任务 worktree 全新索引：`npx gitnexus analyze`
  （28,766 节点 / 60,071 边 / 829 簇 / 300 flows）。
- `impact assign_roles_to_user -r <worktree> --direction upstream --depth 3`：
  **LOW**（impacted 1；direct 1 —— `assign_user_roles_endpoint` CALLS 0.9；
  affected_processes 0）。未达 HIGH/CRITICAL → 按门禁继续。
- 函数签名与返回类型（`User`）不变，唯返回对象的加载状态变完整 —— 唯一
  直接调用方源兼容。

## 3. 产品修复（恰 1 个产品文件，最小正确所有者层）

`backend/crud/user.py::assign_roles_to_user`：flush 后以显式重查询替换局部
refresh ——

```python
refreshed = await db.execute(
    select(User)
    .where(User.id == user.id)
    .options(selectinload(User.roles))
    .execution_options(populate_existing=True)
)
return refreshed.scalar_one()
```

- `populate_existing`：从已 flush 的 UPDATE 强制重读**全部** scalar state
  （含 DB 端 `updated_at`），不依赖偶然 identity-map 状态（合同 #7）；
- `selectinload(User.roles)`：显式重绑 roles（合同 #3）；
- 全部加载发生在 await 边界内；返回后同步序列化零隐式 SQL（合同 #4）；
- 不捕获/吞噬任何异常、不删响应字段、不 mock user_to_read（合同 #1）；
- `expire_on_commit`、api.py、拦截器、迁移、依赖、前端零改动（合同 #2、
  禁止项）；INVALID_ROLE/USER_NOT_FOUND 失败合同、权限校验、事务原子性
  （flush-only，提交权仍在请求边界）与响应结构不变（合同 #5/#6）。
- 依据：SQLAlchemy 官方对更开放 reload 的建议即 populate_existing
  （Session.refresh docstring 原文引荐）。

未触碰同文件 `create_user`/`update_user` 的既有局部 refresh（不在本缺陷
确认范围；create 为 INSERT+RETURNING 即时取回，无过期问题）。

## 4. 测试（新增 1 个真实 PG16/ASGI 测试文件，8 测试）

`backend/tests/test_dc12r1_j1_h2_b_r3_r1_user_role_assignment_async_serialization.py`

供给路径 = 冻结浏览器旅程 M1 的正式双租户链：signup → verify-email →
setup-credential（真实 admin 角色 + ADMIN_PERMISSIONS 含 users:create +
roles:assign）→ login → select-tenant（contextual JWT）→ 真实 RBAC 中间件。
真实策略注入方式：共享 app 在 MPANGO_ENV=test 下默认 MockAuthStrategy（忽略
Authorization），本套件 fixture 将活的 AuthenticationMiddleware 实例
（`_strategy`）换为真实 `JwtAuthStrategy` 并在测试后恢复 —— 与生产同类、
零 mock 认证；测试间逐租户 DROP SCHEMA 隔离。

| # | 断言 | 结果 |
|---|---|---|
| T1 | 正式租户 + 真实 users:create；PUT roles → 200 + 完整 scalar 集（id/email/full_name/is_active/created_at/updated_at）+ admin 角色；updated_at≥created_at | PASS（旧码 RED：500） |
| T2 | CRUD 级：assign 返回后同步跑 `user_to_read`，引擎级 before_cursor_execute 探针 → **零 SQL**、无 MissingGreenlet、字段全非空 | PASS（旧码 RED） |
| T3 | fresh session：绑定真实持久化且**恰好一次**（绑定到该 admin role id）；二次相同 PUT 替换不复制 | PASS |
| T4 | 非法 UUID / 未知 UUID / 混合有效+未知 → 精确 400 INVALID_ROLE，user_roles 零残留 | PASS |
| T5 | 不存在用户 → 精确 404 USER_NOT_FOUND | PASS |
| T6 | 两租户同邮箱各建副本、各分配本租户 admin：role id 互不相交、绑定互不越界、GET /users 各见恰 1 副本 | PASS |
| T7 | 真实权限链：owner 经 users:create+roles:assign 成功；无角色成员同链被 403 PERMISSION_DENIED 且零绑定 | PASS |
| T8 | CRUD 内 assign 后 rollback → fresh session 零 user_roles 残留 | PASS |

## 5. 变异真值门（全部先 RED、恢复后字节一致、再 GREEN）

候选 `backend/crud/user.py` SHA-256：
`95c89cbd1d017313d68141614957f36e2209965bb41ba5c3aece8942868d0fd5`

| 门 | 变异（临时，均已恢复） | RED | 恢复后 |
|---|---|---|---|
| M1 | 恢复旧局部 `refresh(user, ["roles"])` | T1+T2 双 RED（MissingGreenlet） | 字节一致 → GREEN |
| M2 | scalar 全刷但 `db.expire(user, ["roles"])`（返回未 eager-load roles 的对象） | T1+T2 双 RED | 字节一致 → GREEN |
| M3 | CRUD 内同步探测过期属性并 try/except 吞掉 MissingGreenlet，原样返回 | T1 RED（端点仍炸） | 字节一致 → GREEN |
| M4a | 去掉 flush+重载，直接返回内存对象 | T3/T8 意外 GREEN（诚实披露：请求边界 commit 自带 flush，持久化仍发生 —— 恰证明 T3 测的是端到端真实持久化而非 CRUD 内部时序） | 字节一致 → GREEN |
| M4b | flush 后 CRUD 内提前 `commit`（破坏事务边界） | T8 RED（rollback 后残留绑定） | 字节一致 → GREEN |
| M4c | flush 后 CRUD 内 `rollback` 取消事务 | T3 RED（零持久化） | 字节一致 → GREEN |

每项恢复后 sha256 与候选逐一相同并重跑 GREEN（证据目录 m*-red.txt / m*-green.txt）。

## 6. 门禁结果（最终树）

| 门 | 结果 |
|---|---|
| focused 自然序（新文件 + test_users_roles_api + test_rbac_enforcement + test_security_s2_5 + H2-B runtime closure） | 96/96 PASS |
| focused 反向序（文件序倒置） | 96/96 PASS |
| 新文件内部 T8→T1 逆序 | 8/8 PASS |
| 双 fresh-stack 完整后端套件 | 见下（Run A / Run B） |
| `py_compile`（2 变更 py 文件） | OK |
| `git diff --check` | clean |
| pre-commit（4 hooks，实际运行） | 全 Passed |
| detect-secrets（2 变更文件） | 0 发现（测试夹具假密串带 `# pragma: allowlist secret`） |
| UTF-8 / 无 BOM / 无 CR | 2 文件全过 |
| GitNexus detect_changes + re-analyze + status | 提交后执行（见 §8） |

双 fresh-stack（各全新 PG16-alpine + Redis7 容器 + fresh DB + alembic
base→037 + FLUSHALL；`MPANGO_ALLOW_TEMP_DB_CREATE=1` +
`MPANGO_TEMP_DB_ALLOWED_PORTS=<stack端口>` 授权真实 alembic/temp-db
证据测试）：

- Run A（h2b_r3r1_full_a_pg@15441 + full_a_redis@16400）：
  **3708 passed / 1 failed / 48 skipped / 15 xfailed**。
- Run B（h2b_r3r1_full_b_pg@15442 + full_b_redis@16401）：
  **3708 passed / 1 failed / 48 skipped / 15 xfailed**（与 Run A 逐项一致，
  唯一 failed 同为下述预存 pw1r3 项）。

唯一失败 `test_pw1r3_rate_limit_context.py::test_101st_anonymous_is_429_…`
**预存且与本 delta 无关**（三重定性）：
1. 该文件单跑于本任务栈同样失败（redis FLUSHALL 后仍失败）；
2. **base 提交 `0267ea73`（无本 delta）独立 worktree 同栈同环境单跑同样
   失败**（对照证据 full-suite-a-final.log / base control run）；
3. 失败路径为限流窗口计时测试（100+ 真实请求），与 users/roles CRUD 无
   交集。除该预存项外 literal zero-red。

开发期自纠（如实记录）：首轮 full suite 暴露本测试文件 fixture 的真实
卫生缺陷 —— 策略恢复对 dict 型 `entry.kwargs` 误用 `setattr` 抛
AttributeError，teardown 中断，JwtAuthStrategy 泄漏进共享 app，污染同进程
后续 dc3b 真实认证测试（4 failed）。修复：双层（built stack 活实例 +
user_middleware spec）一致性换入/同一性检查还原；探针测试验证恢复后为
MockAuthStrategy、dc3b 干扰消除；此后所有 focused/变异/full suite 以最终
文件重跑（*-final.txt 证据）。

## 7. 禁止项遵守

未运行 Playwright；未修改冻结 harness（j1h2b-forgot-reset/** 零改动）；未
合并、未部署、未启动 H2-C；frontend/**、migrations/models/schema、
dependencies/lockfiles、api.py 通用拦截器、H2-B password-reset 行为零改动；
protected refs 未触碰。

## 8. 提交与推送

- 父提交：`0267ea73b77c1246232124278892de11739f408e`（唯一父，HE2 未入
  base）；delta 恰 3 文件（1 产品源码 + 1 测试 + 本台账）。
- 提交后顺序：`npx gitnexus analyze`（重建索引至提交树）→
  `npx gitnexus status`（Indexed commit == Current commit）→
  `git push origin <branch>` → `git rev-parse <branch>` 与
  `git ls-remote origin <branch>` 比对证明 local == remote（证据见任务
  证据目录 gitnexus-reanalyze-final.txt / gitnexus-status-final.txt /
  push-local-remote-proof.txt）。
- `git diff --name-only <parent> HEAD` 恰为上述 3 文件，无其他差异。

## 9. 下一步

冻结（STOP）等待 Kilo bounded source review；其后由 CTO 裁决
`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R3_R1_MERGE_REVIEW` 受控合并。
