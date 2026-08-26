# DC-12R1-MVP-L1-J1-H2-C-R1-R1 — Canonical Neutrality Runtime Proof 与测试残留收口

- 日期：2026-08-27（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-J1-H2-C-R1-R1（Canonical Neutrality Runtime Proof and
  Test-Residue Closure）
- 验证层级：V3_MERGE_CRITICAL_TEST_INFRASTRUCTURE；CLAIM_CEILING：
  `CANDIDATE_READY_FOR_KILO_DELTA_REVIEW_ONLY`
- BASE：`8ad346e52ff812638a6ac35205b3aade68e20005`（本地 == 远端复核）
- 只读接受证据：`KILO_E2 = acd836bb1cc8d229088f8041cea86230f60609e7`
  （= `origin/reports/dc12r1-mvp-l1-j1-h2-c-r1-v1-e1-kilo-linear-source-review-2026-08-26`
  tip，逐位一致）；受保护基线
  `origin/product-dev-recovered@2c20d58c…` 未漂移。
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-r1-r1-canonical-neutrality-residue-closure-2026-08-27`
- 授权范围：恰 2 文件（本台账 + H2-C 后端测试文件）。产品源码、既有
  s1_db fixture、迁移、模型、依赖、前端、authService.ts、冻结 harness、
  protected refs 均零改动。

## 1. Phase 2 — 原缺陷确定性复现（未修改 BASE，精确因果，不引用 full-suite 总数）

- 任务自有 fresh 栈：PG16（127.0.0.1:15456）+ Redis7（127.0.0.1:16406）；
  Alembic 唯一 head `037_payment_declarations_schema`；任务自有 venv
  （Python 3.12.10 + 锁定 requirements + 锁定测试依赖，bcrypt 4.0.1）。
- 运行前精确快照：wholesalers/retailers/bindings/invitations/tokens/
  uuid-schemas 全零（0/0/0）。
- 在未修改 BASE 上运行 H2-C 后端模块（4 测试，其中 2 个 DB 测试）：
  4/4 通过后，DB 精确残留：
  - wholesaler `208c3039-c408-441b-85fc-3cd174bc3daf`（code `S1TF794B`）
  - retailer `ee265021-b026-44f8-bd59-14e8c2e338d5`
  - binding `0ec71247-83df-43a4-a608-5b5f9a51bc07`
  - invitation `b554d7a2-50cd-4eaa-9e5a-1ded1ba888c1`
  - reset token `6b2c3b94-1343-4383-9cbc-a18a729a0f5a`
  - schemas `t_208c3039c408441b85fc3cd174bc3daf`（末测试存活链）与
    `t_e3ec7cdbbe4a4ef5ba24f819e17b468c`（前测试孤儿 schema）。
- 机制证明：s1_db fixture 仅在每个测试**前**以 `LIKE 'S1T%'`/全表 DELETE
  清公共表，测试**后**无清理、从不 DROP schema；末测试公共行存活，
  前测试 schema 成为孤儿。此为本模块自身新增残留的逐身份因果证明。

## 2. Phase 3 — 有界测试卫生修复（仅本模块文件内）

- 不再消费 s1_db：文件本地 `h2c_registry` fixture + `_Registry`
  （setup_token/reset_token/binding/invitation/retailer/wholesaler 精确 id
  + 精确 schema 名）；模块级 `_MODULE_REGISTRY` 汇总。
- finalizer 无条件运行（测试体成败皆运行）；teardown 失败照常抛出，
  不掩盖原失败（pytest 同时报告）。
- fresh connection 按 FK 安全顺序精确清理：setup/reset token → binding →
  invitation → retailer → wholesaler → 精确 schema 名 DROP（CASCADE 仅限
  该 schema 内对象）。零 LIKE/前缀/通配符/全表删除/全局 reset/DROP
  DATABASE。
- 第二个 fresh connection 零证明：每个精确 id 与 schema 均不存在
  （`_prove_zero`）。
- 既有 4/0/29 full-suite 债务归 full-suite 血统所有；本模块只清理自建
  身份，不触碰他人债务（交互 bundle 中 S1/H2-B 的既有残留模式保持原样）。

## 3. Phase 4 — HC07-HC10 真实 HTTP canonical neutrality

- 真实 ASGI endpoint `POST /api/v1/client/auth/forgot-password`；正式
  retailer 生命周期供给（invitation → register → consume_setup；
  HC10 不消费 setup 使邮箱保持未验证——已在源码核实
  `email_verified_at` 仅在 consume 后设置）。
- 四态断言全部通过：status==200；精确键集
  success/data/message/timestamp；`success is True`；`data == {}`；
  `message` 精确等于 `NEUTRAL_RETAILER_CREDENTIAL_MESSAGE`；timestamp
  为非空字符串且 `datetime.fromisoformat` 可解析。
- 仅将 timestamp 值替换为 `<SENTINEL>` 后四对象逐键相等。
- 不声称 raw-byte equality、响应时长 equality 或 timing side-channel
  关闭。
- 副作用：HC07 恰 1 token + 1 email；HC08/09/10 零 token、零 email。
- 全部运行身份经 Phase 3 fixture 精确清理。
- 状态变更：HC07-HC10 由 R1 的 `NOT_YET_RUNTIME_PROVEN`（仅前端 mock 的
  canonical equality）升级为真实 HTTP pre-gate proof（非权威浏览器门）。

## 4. Phase 5 — 真实性门（C1-C4 全 RED + SHA-256 字节恢复）

| 变异 | 内容 | RED | 恢复 |
|---|---|---|---|
| C1 | 删除终末清理 | 3 failed | SHA-256 一致 |
| C2 | 只清公共行、不 DROP schema | 1 failed + 3 teardown ERROR（schema 证明） | SHA-256 一致 |
| C3 | 只 DROP schema、不清公共身份 | 3 failed + 3 ERROR（公共行证明） | SHA-256 一致 |
| C4 | forgot 端点中性 message 临时变异 | canonical 测试 1 failed | SHA-256 一致（api/v1/client/auth.py，变异后按字节恢复） |

恢复后全部测试 GREEN。变异期间产生的临时残留均已按精确身份清理归零。

## 5. Phase 6 — 门禁结果

- 模块自然序 6/6 GREEN，运行后 DB 精确身份/schema 全零（ws=0/rt=0/
  schemas=0）。
- 模块显式反向序 6/6 GREEN，运行后残留为零。
- 交互顺序（本模块 → residue proof（模块末测试）→ S1 credential 三件套
  + H2-B runtime closure）：44/44 GREEN。
- focused bundle 最终字节自然序与反向序各 44/44 GREEN。
- py_compile、`git diff --check`、scoped pre-commit + detect-secrets、
  严格 UTF-8/无 BOM/LF（无 CR）：全部通过。
- GitNexus analyze/status：本分支重建索引并 up-to-date。
- 本轮未在 Windows 重跑完整后端 full suite（按任务不要求）；父级
  Windows 红集（8F/35E，Alembic 基础设施类）仍为环境门控差异，**不得**
  引用为零红或合并证据。

## 6. Ledger Truth — 措辞修正与状态区分

1. **撤回** R1 台账中"已知 4/0/29 测试卫生债务保持原状（属既有披露，
   非本任务新增）"的旧措辞：该表述隐含 H2-C 模块自身零残留贡献。
   Phase 2 已逐身份证明 H2-C BASE 的 DB 测试**新增**了模块级残留
   （每次运行 1 条存活链 + 1 个孤儿 schema），属既有 4/0/29 债务之外的
   新增量。本更正仅记录于本台账；R1 台账原文未修改（历史报告不改写）。
2. 分层状态：
   - 既有 full-suite debt：4/0/29（wholesalers/registrations/uuid
     schemas，外部归因）——保持存在，归 full-suite 血统。
   - H2-C BASE 新增测试残留：本台账 §1 的精确身份（已于复现后按精确
     身份清理）。
   - R1-R1 实施的精确清理：§2 的 registry/finalizer/二次连接零证明；
     模块此后每次运行净贡献为零。
   - HC07-HC10：`NOT_YET_RUNTIME_PROVEN` → 真实 HTTP pre-gate proof
     （§3）；权威浏览器执行仍属后续独立门。
3. s1_db fixture 本体未修改（禁改项）；S1/H2-B 测试的既有残留模式
   未被触碰或清除。

## 7. 裁决

FINAL VERDICT:
**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R1_R1_CANDIDATE_READY_FOR_KILO_DELTA_REVIEW**

CLAIM_CEILING：`CANDIDATE_READY_FOR_KILO_DELTA_REVIEW_ONLY`。
推送并证明 local == remote 后 STOP：不启动 Kilo、Lubuntu、Playwright、
合并、部署或 PRICING。
