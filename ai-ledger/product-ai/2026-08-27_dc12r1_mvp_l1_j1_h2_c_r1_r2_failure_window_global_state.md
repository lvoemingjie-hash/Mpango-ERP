# DC-12R1-MVP-L1-J1-H2-C-R1-R2 — Failure-Window 与全局测试状态收口

- 日期：2026-08-27（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-J1-H2-C-R1-R2（Failure-Window and Global Test-State
  Residue Closure）
- 验证层级：V3_MERGE_CRITICAL_TEST_INFRASTRUCTURE；CLAIM_CEILING：
  `CANDIDATE_READY_FOR_KILO_RE_REVIEW_ONLY`
- BASE：`d1198f3ba30b39016299fe449087980310ff5df1`（本地 == 远端复核）
- KILO_STOP：`09a61608c54eb6c6491abb34eb79fac57ac72680`
  （= `origin/reports/dc12r1-mvp-l1-j1-h2-c-r1-r1-v1-kilo-bounded-delta-review-2026-08-27`
  tip，逐位一致）
- 受保护基线：`origin/product-dev-recovered@2c20d58c…`（未漂移）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-r1-r2-failure-window-global-state-closure-2026-08-27`
- 授权范围：恰 2 文件（H2-C 测试模块 + 本台账）。产品源码、共享
  fixture、前端、迁移、依赖、harness 均零改动（diff 复核）。

## 1. Kilo 两项 P1 STOP（如实记录，不淡化）

1. **P1 TEST_HYGIENE_DEFECT（失败窗口）**：R1-R1 的 finalizer 只清理
   registry 中已登记的精确 ID；测试体在 commit 与手工登记之间失败时，
   已提交对象滞留 registry 之外。
2. **P1 GLOBAL_TEST_STATE_RESIDUE（全局测试状态）**：dev retailer email
   sink 从不在测试后清理（BASE 证据：HC07-HC10 真实运行后 1 封 delivery
   跨测试存活于同进程）；`_real_client` 无条件 pop
   `app.dependency_overrides`，会摧毁既有的外部 override。

## 2. Phase 2 — 未修改 BASE 上的缺陷复现（throwaway 文件，证据后删除）

1. **失败窗口（静默残留变体）**：按 Kilo 切点 3 复现（registration
   commit 后、ID 登记前失败）。**机制修正（如实记录）**：本 schema 的
   token→retailer FK 为 `ON DELETE CASCADE`（`confdeltype='c'`，
   非可延迟），Kilo 字面描述的"FK violation 回滚清理事务"路径在
   R1-R1 BASE 上**不发生**（登记了 retailer 的场景下未登记 token 会随
   级联删除消失）；可复现的真实缺陷是**静默残留**——未登记的已提交
   retailer 行在 finalizer 零报错的情况下存活，且 registry-only 零证明
   仍然通过（更隐蔽）。R1-R2 的锚点再发现方案同时关闭两种形态
   （无论 FK 行为如何）。
2. **email sink**：BASE 的 h2c_registry teardown 后 sink 非零
   （复现测试通过）；同进程内先跑真实 HC07-HC10 再检查，输出
   `IN-PROCESS SINK AFTER HC07-HC10 RUN: 1 delivery(ies) survive`。
3. **override**：BASE 的无条件 pop 使预置外部 override 被摧毁
   （复现测试通过）。进入前状态不能假设为空——已按此设计恢复语义。

## 3. Phase 3-6 — 修复实现（仅授权测试模块内）

1. **稳定锚点（副作用发生前登记）**：exact email/phone 于
   `_plan_identity` 最前；wholesaler id + schema 于 `_make_tenant`
   返回即刻；invitation code 于返回即刻。
2. **finalizer 再发现（hydration）**：fresh connection 按锚点重新发现
   retailer（exact email/phone）、binding（exact wholesaler/retailer
   范围）、invitation（exact code + exact wholesaler 范围）、setup/reset
   token（exact retailer_id），与已登记 ID 去重后执行 FK-safe exact-ID
   清理。零 LIKE/前缀/通配符/全表删除/全局 reset/DROP DATABASE。
   即使测试在 commit 后、手工登记前失败，finalizer 也能找到全部对象。
3. **可直测生命周期**：`_residue_lifecycle` async context manager
   （pytest fixture 仅包装）。body/hydrate/cleanup/zero-proof 失败分别
   保留；多失败用 `ExceptionGroup`/`BaseExceptionGroup` 聚合且不覆盖
   原 body 异常；清理按步 best-effort（单步失败不中断其余安全步骤，
   失败步骤重试一次，愈合的瞬态失败仍计入 cleanup 错误上报）；全部
   engine/session 在 finally 关闭。
4. **全局状态**：模块入口 sink 非空即 fail closed；每个 teardown 的
   finally 清 sink；`_override_guard` 保存进入前精确值并在 finally
   恢复（绝不无条件 pop）；`_MODULE_STATE` 模块开始初始化、结束清空
   （同进程两轮运行零继承）；末测试证明 DB 锚点/ID、schema、sink、
   override（逐键对象同一性）与连接（相对模块入口基线的 delta——
   其他模块的既有池连接归其所有）全轴为零。
5. **FW1-FW5 真实失败窗口测试**（每项证明：原始 sentinel 保留、DB
   精确对象为零、schema 为零、sink 为零、override 恢复、无连接残留）：
   FW1 registration commit 后、sweep 前抛 sentinel；FW2 token/email
   产生后、ID 登记前抛 sentinel；FW3 canonical 断言在副作用产生后失败；
   FW4 override 安装后请求路径失败（外部 override 精确存活）；FW5
   cleanup 瞬态失败与 body failure 同时存在（ExceptionGroup 双保留，
   重试后 DB 归零）。

## 4. Phase 7 — 变异门（C1-C8，最终字节 SHA-256 恢复）

针对最终提交字节（test 模块 `e405d392…`；`api/v1/client/auth.py`
`8894d1f4…`）：

| 变异 | RED | 恢复 |
|---|---|---|
| C1 删除终末清理 | 6 failed + 3 errors | SHA-256 一致 |
| C2 只清公共行不 DROP schema | 6 failed + 3 errors | SHA-256 一致 |
| C3 只 DROP schema 不清公共行 | 6 failed + 3 errors | SHA-256 一致 |
| C4 中性 message 临时变异（产品） | canonical 测试 1 failed | SHA-256 一致 |
| C5 删除锚点再发现 | 6 failed + 3 errors（FW 静默残留） | SHA-256 一致 |
| C6 删除 sink teardown | 6 failed（sink 证明） | SHA-256 一致 |
| C7 不恢复精确 override | FW4 1 failed | SHA-256 一致 |
| C8 取消异常聚合 | FW5 1 failed | SHA-256 一致 |

恢复后全模块 11/11 GREEN。变异期间临时残留均按精确身份清理。

## 5. Phase 8 — 门禁

- 模块自然序 11/11 GREEN；显式反向序 11/11 GREEN。
- 同一 Python 进程连续两轮模块级生命周期：两轮各 11/11 GREEN，状态零继承。
- 模块 → S1/H2-B focused 交互顺序 49/49 GREEN。
- focused bundle 自然序与反向序各 49/49 GREEN（反向序初跑暴露的
  "1 lingering connection"为 S1 模块既有池连接，已改为相对模块入口的
  delta 证明并复验双向 GREEN）。
- 模块自身残留归零（h2c-% 邮箱零售商 = 0；S1 既有残留模式保持原状，
  归其血统所有）。
- py_compile、`git diff --check`、scoped pre-commit + detect-secrets、
  严格 UTF-8/无 BOM/LF、GitNexus analyze/status（up-to-date）全部通过。
- 本轮未运行完整后端 full suite；父级 Windows 红集仍为环境门控差异，
  **不作为 zero-red 或合并证据**。

## 6. Ledger Truth

1. R1-R1（d1198f3b）的 failure-window 与 global-state 处理**被本轮
   R1-R2 取代**：R1-R1 的 registry-only finalizer、无 sink 清理、
   无条件 override pop 均已按 §3 修复。历史台账不改写。
2. Kilo 两项 P1 STOP 原文记录于 §1，未淡化为观察项；其中 P1-A 的
   FK-rollback 机制描述与本 schema 的 CASCADE 现实不符（§2.1），
   该差异是对证据的修正，不是对 STOP 的降级——静默残留形态同样
   构成 P1 测试卫生缺陷且已被修复关闭。
3. 三种状态面区分：**数据库残留**（精确身份/锚点清理 + 二次连接
   零证明）、**内存邮件 sink**（入口 fail-closed + teardown finally
   清空 + 末测试零证明）、**dependency override**（精确值恢复 +
   模块级逐键同一性证明）。
4. Kilo STOP 报告中的 trailing whitespace 仅记录为 **P3 publication
   hygiene**（报告分支发布卫生），不归类为候选产品或测试缺陷。

## 7. 裁决

FINAL VERDICT:
**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R1_R2_CANDIDATE_READY_FOR_KILO_RE_REVIEW**

CLAIM_CEILING：`CANDIDATE_READY_FOR_KILO_RE_REVIEW_ONLY`。
推送并证明 local == remote 后 STOP：不启动 Kilo、Lubuntu、Playwright、
合并或部署。
