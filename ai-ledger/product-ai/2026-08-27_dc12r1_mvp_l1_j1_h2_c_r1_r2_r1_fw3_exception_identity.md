# DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1 — FW3 原始异常对象身份证明收口

- 日期：2026-08-27（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1（FW3 Original-Exception Identity
  Proof Closure）
- 验证层级：V1_FOCUSED_TEST_AUTHENTICITY_CORRECTION；CLAIM_CEILING：
  `CANDIDATE_READY_FOR_KILO_DELTA_REVIEW_ONLY`
- BASE：`8aced8c7d6d034a0ac2c4b849b3586464f8c5710`（R2 tip，远端一致）
- KILO_STOP：`de1c88cce96b39c63ea6b3eddda9f7d0278218b9`
  （= `origin/reports/dc12r1-mvp-l1-j1-h2-c-r1-r2-v1-kilo-bounded-re-review-2026-08-27`
  tip，逐位一致；Phase 2 §2.7 裁定 **P1 TEST_FALSE_GREEN**）
- 受保护基线：`origin/product-dev-recovered@2c20d58c…`（未漂移）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-r1-r2-r1-fw3-exception-identity-closure-2026-08-27`
- 授权范围：恰 2 文件（H2-C 测试模块 + 本台账）。

## 1. Kilo P1 TEST_FALSE_GREEN（R2 的 FW3 假绿缺陷，如实记录）

R2 的 FW3 在外层 `except AssertionError` 中以 `caught = AssertionError()`
**新建**实例（原始对象身份被销毁），随后仅断言 `caught is not None`——
类型成立即通过，**从未证明原始 canonical AssertionError 对象穿透
`_residue_lifecycle` 存活**。`_residue_lifecycle` 本身的 body-only 传播
路径（`raise body_error`）是保身份的；假绿出在测试的捕获形态。

## 2. 修正实现（仅测试模块）

FW3 重写为推荐形态：

1. **真实 canonical assertion**：对真实 HTTP 响应体断言
   `r7.json()["message"] == NEUTRAL_RETAILER_CREDENTIAL_MESSAGE + "::fw3-unreachable"`
   ——真实数据、真实断言表达式、按构造确定性失败（真实中性 message 永不
   等于不可达期望值）；**不是**手工 `raise AssertionError()`。
2. **内层捕获 + 原样 re-raise**：`except AssertionError as exc:
   original_assertion = exc; raise`。
3. **外层捕获传播异常**（在 `_residue_lifecycle` 之外），同时保留
   BaseException 分支捕获可能的 group 包装。
4. **对象身份断言**：`assert propagated is original_assertion`
   （仅 `is` 身份；不断言类型/消息/成员性/`is not None`）。
5. 保留全部既有证明：真实副作用（token + email）、清理、sink/override/
   连接零残留（`_assert_window_outcomes` + 模块末测试）。

## 3. 真实性反例门（identity falsification）

临时将 `_residue_lifecycle` 的 body-only 传播路径改为
`raise AssertionError(str(body_error))`（新建对象、丢失身份）：

- FW3 **确定性 RED**（1 failed：`propagated is original_assertion` 失败）。
- 按候选字节恢复（SHA-256 `39e451c0d79ad64824b77687cc90e98cbb22d90b08baff3df0305ff290208de1`
  逐位一致）后 FW3 **GREEN**。
- 未通过修改/删除身份断言刷绿（断言保持原样，反例只改被测传播路径）。

## 4. 运行结果（fresh 栈：PG16@15458 + Redis7@16408 + Alembic 唯一 head）

- FW3 单节点：1/1 GREEN。
- FW1–FW5：5/5 GREEN。
- 模块自然序：11/11 GREEN。
- 模块显式反向序：11/11 GREEN。
- 同一 Python 进程连续两轮：11/11 + 11/11 GREEN（无状态继承）。
- py_compile、`git diff --check`、scoped pre-commit + detect-secrets、
  严格 UTF-8/无 BOM/无 NUL/LF、GitNexus analyze/status（up-to-date）
  全部通过。

## 5. Ledger Truth

1. R2（`8aced8c7`）被本轮 R2-R1 **supersede**：R2 的 FW3 捕获形态
   （新建实例 + `is not None`）不再代表候选字节；以本轮身份证明形态
   为准。历史 R2 台账不改写。
2. 本轮**仅关闭 P1 TEST_FALSE_GREEN**（Kilo STOP `de1c88cc`）。
3. 不重新声称：产品修复、full-suite zero-red、Lubuntu PASS、
   Playwright PASS 或 merge-ready。

## 6. 裁决

FINAL VERDICT:
**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R1_R2_R1_CANDIDATE_READY_FOR_KILO_DELTA_REVIEW**

CLAIM_CEILING：`CANDIDATE_READY_FOR_KILO_DELTA_REVIEW_ONLY`。
推送并证明 local == remote、工作树 clean 后 STOP：不启动 Kilo、
Lubuntu、Playwright、合并或部署。
