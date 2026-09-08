# 逐节点对账：最终候选 vs BASE 1485c3f5（冻结全量差分）

> **修订（R1-R2 整改，2026-09-08）**：原解析器漏配多空格对齐与含空格参数化 id，只解析 3590/3577、
> 误报 candidate-only/base-only 为 15/2。完整解析为 **候选 3837 / BASE 3824**、candidate-only **18** /
> base-only **5**（新增 3+3 个含空格参数化节点，全部 PASSED）；其余结论（唯一状态变化、FAILED/ERROR/
> SKIP 差分）经完整解析维持不变。解析缺陷与更正细节见 INTEGRITY_APPENDIX.md §2；本文以下为原文，
> 其中的 3590/3577/15/2 数字以本修订为准。

解析方法：两侧 `-ra -v` 原始日志的逐节点行（`tests/...::<node> <STATUS> [n%]`）解析为
nodeid→状态映射（候选 3590 节点、BASE 3577 节点；两者均少于收集清单的 3837/3824，因参数化
展开与收集计数的口径差，两侧口径一致故差分有效），按 nodeid 求差。

## 1. 共享节点状态变化：恰 1 处

| 节点 | BASE | 候选 | 归类 |
|---|---|---|---|
| `tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_red_concurrent_stock_adjustments_no_lost_update` | FAILED（基线 RED，终值 15.00） | **PASSED** | 预期：产品修复（adjust_stock populate_existing）的差分确证 |

**这是两侧唯一一处共享节点状态变化**——即最终字节下产品修复相对基线的全部行为差，在套件层面
恰好等于被修复的那个反例，无任何伴随漂移。

## 2. 仅候选存在的节点（15）

| 节点 | 全量内状态 | 聚焦冻结权威证据 |
|---|---|---|
| guards::`exact_cto_counterexample_rows`（O1 精确原反例） | PASSED | —（无 DB） |
| guards::`rejects_chained_duplicate_reason_rows`（O1 更名后继） | PASSED | — |
| guards::`isolation_assertion_rejects_mixed_tenant_results`（F1 反例） | PASSED | — |
| guards::`isolation_assertion_rejects_foreign_tenant_result`（F1 反例） | PASSED | — |
| guards::`refresh_refusal_assertion_rejects_masked_code`（F3 反例） | PASSED | — |
| guards::`refresh_refusal_assertion_rejects_token_bearing_401`（F3 反例） | PASSED | — |
| guards::`no_issuance_assertion_rejects_issuer_use_and_tokens`（F3 反例） | PASSED | — |
| concurrency::`r1_control_adjustment_read_helper_preserves_duplicate_rows`（O1 DB 级） | PASSED | PASS |
| revocation::`r1_control_refresh_wrong_signature_refused`（F3.2 解耦重写） | ERROR（环境） | PASS（不可达前提 51P 之一） |
| revocation::`r1_control_refresh_wrong_token_type_refused` | ERROR（环境） | PASS |
| revocation::`r1_control_tenant_isolation_same_query_same_code_db_only`（F1 重设计，更名自 no_cross_read） | ERROR（环境） | PASS（两前提均 PASS） |
| revocation::`r1_red_diagnostic_sku_list_cache_not_tenant_scoped`（F1.3 有界诊断） | ERROR（环境） | 可达前提：**命名 RED**（登记风险复现）；不可达前提：显式 SKIP（前提缺失） |
| revocation::`r1_refresh_nonexistent_user_in_active_tenant_principal_branch`（F3.1） | ERROR（环境） | PASS |
| revocation::`r1_refresh_subject_db_fault_zero_issuance`（F3.3） | ERROR（环境） | PASS |
| u6i3::`test_invalid_or_missing_raw_token_fails_neutrally[u6i3-missing-e5f631c1…]` | PASSED | 参数化含随机 UUID；BASE 侧同节点为另一随机实例（见 §4） |

"ERROR（环境）"= 全量内撤权文件 setup 守卫 `GUARD_REFUSED_MOCK_AUTH`（既有 6 个旧测试文件在
收集期硬设 MPANGO_ENV=test 未还原）。该机制两侧同构：BASE 的 8 个撤权节点在全量内同为 ERROR。
聚焦冻结运行（无污染进程、真实 JWT 守卫通过）给出这些节点的权威结果，如上列。

## 3. 仅 BASE 存在的节点（2）

| 节点 | BASE 状态 | 说明 |
|---|---|---|
| guards::`test_r0_assertion_chain_rejects_duplicate_collapsed_to_two` | PASSED | O1 更正：该节点在候选更名为 `rejects_chained_duplicate_reason_rows`（§2 第 2 行），断言体保留原坏快照形状 |
| u6i3::`…[u6i3-missing-03c54790…]` | PASSED | 随机 UUID 参数化实例（与候选的随机实例同节点不同 id），两侧各 1 且均 PASSED |

## 4. 失败集合差分（FAILED 短摘要逐 nodeid）

- 仅 BASE：`red_concurrent_stock_adjustments_no_lost_update`（1）——修复转绿
- 仅候选：**无**
- 共享 18 FAILED 两侧完全相同（17 既有 nodeid 见 EXPECTED_SET + 已知双退 RED）

## 5. 错误集合差分（ERROR 短摘要逐 nodeid）

- 仅候选：6 个撤权新增/更名节点（§2 所列，同一收集期泄漏机制）
- 仅 BASE：无
- 共享 37 ERROR 两侧完全相同（29 real_alembic + 8 撤权 R0-R2 节点）
- 多阶段 ERROR 口径：逐节点流中每个 nodeid 只记一次终态；ERROR@teardown 不重复计数

## 6. SKIP 对账（F2 核心）

- 两侧 skip 计数 **69 = 69**，且逐 nodeid 集合完全一致（按共享状态差分中无任何 SKIPPED 变化）。
- 原因分布（两侧相同，取自 -ra 摘要）：19× `set PAYMENTS_SCHEMA_REQUIRE_LIVE=1...`；
  19× `S3-B prepared tenant prerequisites are missing for 't_u1r1_test'`；15+5× `set
  MPANGO_ALLOW_TEMP_DB_CREATE=1...`；3× openapi.yaml 未生成；3× Requires running Alembic CLI；
  2× runtime import HTTP 环境变量缺失；2× SQL profiling 未启用。（摘要行 68 vs 计数行 69：
  dc11t4h 一个参数化 skip 的摘要行缺失，属呈现伪影，两侧对称，逐节点流中两侧均为 69 且集合一致。）
- **旧 19-skip 差（上轮 69 vs 50）的最终处置**：旧日志为 `-q -rfE`，无 skip 节点行——nodeid 级
  不可恢复（维持 FILES_MANIFEST 的"未知"结论）。但本轮从旧日志的文件级进度条（s 计数）恢复了
  **文件级归因**：差异全部（+19/0）位于 `tests/test_s3b_fresh_tenant_live_runtime_proof.py`
  （候选序运行先行建立了 S3-B 预置租户 `t_u1r1_test`，BASE 序运行继承该库后同文件 0 跳过）。
  等价初始状态的冻结差分中该文件两侧同为 19 跳过——**证实上轮差异为库态继承伪影，与字节无关**；
  上轮报告把它作为"库态差异"的猜测成立，但当时证据不足，措辞已按勘误撤回并以本轮证据替代。

## 7. 对账结论

- 预期集合内的状态：全部吻合（候选 18F/43E/69S/15x；BASE 19F/37E/69S/15x）。
- 未解释的新失败 / 新错误 / 新跳过：**0**（STOP 判据未触发）。
- 最终字节下产品修复的套件级行为差 = 恰 1 个目标反例转绿；其余一切两侧相同。
