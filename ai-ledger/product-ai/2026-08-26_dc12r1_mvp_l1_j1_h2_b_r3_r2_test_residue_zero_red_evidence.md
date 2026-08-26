# DC-12R1-MVP-L1-J1-H2-B-R3-R2 — 测试残留与 Zero-Red 证据收口（Test Residue and Zero-Red Evidence Closure）

- 日期：2026-08-26（+08:00）；执行者：Zcode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r3-r2-test-residue-zero-red-evidence-closure-2026-08-26`
  （自父提交 `13a8d25ca8d40dbc0b1ac05aa8206d5dcf56f070` = R3-R1 tip 创建）
- 中期裁决：`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_INDEPENDENT_ZERO_RED`
- 授权范围：恰 3 文件 delta —— ① 测试文件
  `backend/tests/test_dc12r1_j1_h2_b_r3_r1_user_role_assignment_async_serialization.py`；
  ② R3-R1 台账真相修正；③ 本台账。**`backend/crud/user.py` 零改动**
  （SHA-256 与 R3-R1 提交逐字节一致，未发现新的产品缺陷）。

## 1. R3-R1 证据为何不权威（修正依据）

1. A/B 两轮（各 3708 passed / 1 failed）非 literal zero-red；唯一 failed
   （pw1r3 限流计时测试）当时虽经 parent 对照定性为预存，但根因未闭合。
2. R3-R2 定位 pw1r3 根因：该测试需任务专用
   `PW1R3_TEST_REDIS_URL`（未设置时回退 `redis://127.0.0.1:26379/15`
   ——sentinel 端口，无监听，必然连接失败）。R3-R1 两轮均未设置该变量。
3. R3-R1 测试文件的租户清理只发生在节点**前**；节点后残留仅靠下一节点
   前置清理掩盖，末节点残留可存活至套件结束 —— 残留合同不成立。

## 2. 本修订的测试文件改动（残留合同闭合）

1. **双向清理**：`_r3r1_isolation` 对每个节点前后各执行一次
   `_cleanup_tenant_state_fail_closed()`。
2. **终末清理 fail-closed + fresh session**：清理在全新
   `AsyncSessionLocal` 会话中 drop 全部 wholesaler 派生 schema + 孤儿
   uuid 命名 schema、删除 registrations/wholesalers、commit，随后在
   **另一个** fresh 会话复读三个残留维度，任何异常或幸存行/模式即抛错。
3. **清理失败不掩盖测试体失败**：清理位于 teardown —— pytest 将其记为
   独立 teardown ERROR，测试体失败（FAIL）独立保留、不被改写。
4. **T9 残留证明节点**（`test_t9_final_residue_zero`）：跳过前置清理，
   在 fresh 会话读 public.wholesalers / public.tenant_registrations /
   uuid 命名 pg_namespace schema；模块基线为空（fresh 栈/独跑）时断言
   **绝对零**，否则断言相对模块入口基线**零新增**。
5. **策略泄漏防护保留并加验**：JwtAuthStrategy 双层换入/同一性还原保持
   R3-R1 语义；新增模块级 `_r3r2_module_guard` 在末节点后 fail-closed
   复核两层均已恢复 MockAuthStrategy（无共享 app 泄漏）。
6. **t1 断言修正（开发期自纠，如实记录）**：R3-R2 变异门运行中 t1 出现
   一次 `updated_at < created_at`（1.1s 倒置）。定性：PG `now()` 为事务
   **开始**时间戳，池化连接复用可使后发请求继承更早开启的事务，跨请求
   墙钟序不是产品合同（探针脚本 + DB 行直查确认正常路径 updated >
   created）。t1 断言放宽为存在性（两时间戳均可序列化非空——正是旧缺陷
   死点），删除 `>=` 排序断言。

## 3. 确定性变异门（残留证明为活证明）

- 变异：删除 `_r3r1_isolation` teardown 中的终末清理调用（保留 email
  sink 清理；二进制安全替换，LF 保持）。
- 结果：**仅 `test_t9_final_residue_zero` RED**（1 failed / 8 passed；
  t8 的租户 schema + wholesaler + registration 存活被 T9 捕获）。
- 恢复：自快照逐字节恢复（最终 LF 候选 SHA-256
  `00c64a891cb0529d4f37e206d6cfe559e84c1f10d23c051ac0ca780efe1de748`），
  重跑 9/9 GREEN。

### 开发期自纠之二：CRLF 字节事故（如实记录）

变异脚本首版用 `Path.write_text`（Windows 文本模式）重写文件，把整份
测试文件转成 CRLF（831 行全带 CR）——`git diff --check` 报全文件尾随
空白后当即发现。影响：CRLF 期间的一次 full suite A（3710 passed zero-red
但字节非最终）与一次中途终止的 suite B 作废。处置：二进制安全
CRLF→LF 转换（33444→32613 字节）、快照与变异门以 LF 字节全部重做、
两栈完全重置（重建 DB + FLUSHALL + DB15/26379 证明）后以最终 LF 字节
重跑全部权威运行。静态门（py_compile / diff --check / pre-commit /
detect-secrets / UTF-8 无 BOM 无 CR）以最终字节复验全过。

## 4. 栈与预检（每栈 full suite 前）

- Stack A：`r3r2_a_pg`（PG16-alpine，fresh 卷/DB `test_r3r2_a`@15441）+
  `r3r2_a_redis`（Redis7@16400）；Stack B：`r3r2_b_pg`@15442 +
  `r3r2_b_redis`@16401。容器全新重建（旧 R3-R1 full 栈容器连卷删除）。
- **PG 栈参数 `max_connections=300`**（首次 Run A 尝试在套件尾部
  `test_s4_jobs_local::test_enqueue_job` 出现
  `asyncpg.TooManyConnectionsError`（PG16-alpine 默认 100；3700+ 测试
  多引擎峰值贴近上限）。定性：非代码缺陷——本模块运行后
  `pg_stat_activity` 仅 1 连接（零泄漏），单独随后重跑 s4_jobs_local
  11/11 通过；属栈供给余量问题，以容器参数解决并全程披露）。
- 每栈：Alembic base→037；`FLUSHALL`；**DB15 DBSIZE=0 证明**；
  **netstat 无 :26379 套接字证明**（pw1r3 不触碰 sentinel 回退口）；
  focused 自然序 97/97 + 逆序 97/97（本文件 + test_users_roles_api +
  test_rbac_enforcement + test_security_s2_5 + H2-B runtime closure）；
  预检后清租户残留 + FLUSHALL 再启 full suite。
- 运行环境变量：`TEST_DATABASE_URL`、`REDIS_URL=<stack>/0`、
  `PW1R3_TEST_REDIS_URL=redis://127.0.0.1:1640x/15`、
  `MPANGO_ALLOW_TEMP_DB_CREATE=1`、`MPANGO_TEMP_DB_ALLOWED_PORTS=<pg口>`、
  `REPORTING_USER_PASSWORD=postgres`。

## 5. 权威 full suite（每栈恰一次，final LF bytes）

运行字节（运行时实测）：测试文件
`00c64a891cb0529d4f37e206d6cfe559e84c1f10d23c051ac0ca780efe1de748`；
`backend/crud/user.py`
`95c89cbd1d017313d68141614957f36e2209965bb41ba5c3aece8942868d0fd5`
（与 R3-R1 提交逐字节一致）。

- **Run A（r3r2_a_pg@15441 + r3r2_a_redis@16400，DB `test_r3r2_a`）**：
  **3710 passed / 0 failed / 0 errors / 0 xpassed / 48 skipped / 15 xfailed**
  （1544s；junit: stackA-junit.xml）。
- **Run B（r3r2_b_pg@15442 + r3r2_b_redis@16401，DB `test_r3r2_b`）**：
  **3710 passed / 0 failed / 0 errors / 0 xpassed / 48 skipped / 15 xfailed**
  （1513s；junit: stackB-junit.xml）。
- A==B 对比（compare_junit.py + junit-accounting-split.txt）：
  **total 3773 == 3773；passed 3710 == 3710；skipped 48 == 48；xfailed
  15 == 15；failed/errors/xpassed 0 == 0；skip 与 xfail 的 node+reason
  集合逐项全等（onlyA=0 onlyB=0）；accounting gap = 0（两栈各自
  passed+skipped+xfailed+failed+errors+xpassed == total）。RESULT: PASS。**
- **post-run 残留归因**：Run A 后 4 wholesalers / 0 registrations /
  29 uuid 命名 schema —— 全部由本模块**之后**运行的其他测试文件产生
  （本模块运行中 T9 + 双向清理已证零；脏库上重放本模块 9/9 后
  **0/0/0**，即本模块净贡献为零且可将库恢复为零）。
  Run B 后：**4 / 0 / 29（与 A 完全同形）；重放后 0/0/0**。
- pw1r3 7/7 通过（PW1R3_TEST_REDIS_URL=DB15 生效；DB15 运行前空证明 +
  26379 零套接字证明）。
- 作废运行（如实披露）：CRLF 字节期间的一次 suite A（虽 3710 zero-red，
  字节非最终）与一次中途终止的 suite B；另有一次 max_connections=100
  栈上的 suite A 尝试（1 failed：s4_jobs_local 连接耗尽，栈参数问题）。

## 6. 禁止项遵守

未修改 `backend/crud/user.py`（零新产品缺陷证据）；未运行 Playwright；
未触碰冻结 harness/protected refs/frontend/迁移/依赖；未合并、未部署、
未启动 H2-C/HE2。

## 7. 提交与推送

- 父提交：`13a8d25ca8d40dbc0b1ac05aa8206d5dcf56f070`（唯一父）；
  delta 恰 3 文件（测试文件 + R3-R1 台账勘误 + 本台账）；
  `backend/crud/user.py` 与父提交字节一致（未入 delta）。
- 提交后：`npx gitnexus analyze`（索引至提交树）→
  `npx gitnexus status`（Indexed == Current）→ `git push origin <branch>`
  → `git rev-parse` vs `git ls-remote` 比对 local == remote。
- 权威运行字节=提交字节：Run A/B 启动前实测
  `run-bytes-sha256.txt`（测试 `00c64a89…`、crud `95c89cbd…`）与提交
  内容一致；运行期间工作树未再变更（git status 干净后提交）。

## 8. 下一步

冻结（STOP）等待 Kilo bounded review；CTO 裁决
`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R3_R2_MERGE_REVIEW` 后受控合并。
