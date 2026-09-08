# MPANGO-MVP-INVARIANTS-R1-R1 证据目录文件清单（冻结）

> 指令：CTO-AUTH-MPANGO-MVP-INVARIANTS-R1-R1-2026-09-08。
> 本清单在实施与运行之前冻结；只增补时在文末"增补记录"注明原因，不删改既有条目。
> 本目录不引入任何新治理框架，仅为 F1/F2/F3 闭合的自查、对账与脱敏证据。

## 冻结的提交文件清单（本目录 + 允许修改的既有文件）

本目录新增（全部脱敏后提交）：

| 文件 | 用途 | 状态 |
|---|---|---|
| `FILES_MANIFEST.md` | 本清单（冻结） | 已建 |
| `EXPECTED_SET.md` | 冻结验收前预列的预期节点集合（先于两次全量运行写定） | 待冻结运行前写定 |
| `RUN_IDENTITY_CANDIDATE.md` | 候选冻结运行的字节身份（HEAD/树哈希/测试文件 SHA256/env/容器/venv 版本/命令/退出码） | 待运行后填写 |
| `RUN_IDENTITY_BASE.md` | BASE(1485c3f5) 冻结运行的字节身份（同上） | 待运行后填写 |
| `NODE_RECONCILIATION.md` | 候选 vs BASE 逐节点对账（状态变化/新增/删除/skip 原因/ERROR 去重/预期集合比对/未知即 STOP） | 待对账后填写 |
| `SELF_REVIEW.md` | 提交前全面自查：逐项证据位置 + PASS/KNOWN_RED/NOT_PROVEN 判定 | 待自查后填写 |
| `evidence/`（脱敏摘录） | 冻结运行的关键原始输出摘录（-v 逐节点结果、skip 原因、汇总行、退出码），经脱敏器处理 | 待运行后产生 |

允许修改的既有文件（指令写入范围）：

| 文件 | 本轮变更 |
|---|---|
| `backend/tests/test_mpango_mvp_invariants_r0_revocation.py` | F1：同参同码隔离对照 + 缓存诊断命名 RED；F3：错误签名节点解耦重写 + 活租户缺用户 + 主体查询故障零签发；共享断言助手 |
| `backend/tests/test_mpango_invariants_r0_r1_guards.py` | 新增 5 个语义反例（隔离断言×2、refresh 拒答断言×2、零签发断言×1），全部调用撤权模块的真实共享助手 |
| `backend/tests/mpango_invariants_r0_support.py` | `seed_sku_with_stock` 增加可选 `name` 参数（默认不变） |
| `backend/tests/test_mpango_mvp_invariants_r0_concurrency.py` | 本轮零字节变化（预留写入范围内，实际未动） |
| `docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_REPORT.md` | 追加勘误节（撤回 19-skip 归因推测与过强结论，指向本轮冻结差分） |
| `docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_RUN_LOG.md` | 追加勘误节 + R1-R1 运行记录节 |
| `docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_RECORD.md` | 追加勘误指针节 |

字节保持 BASE（a516d2b3）不变的文件：全部产品源码、`backend/tests/test_pw1r3_rate_limit_context.py`、
迁移、依赖锁、工作流、HE2、业务合同、`.secrets.baseline`。

## 原始运行材料（仓库外，不可覆盖）

| 路径 | 内容 |
|---|---|
| `C:/Users/Jeff0/MPANGO ERP/_zcode_mvp_invariants_r1r1_dev_focused.log` | 开发期聚焦迭代运行输出（原始，不脱敏提交） |
| `C:/Users/Jeff0/MPANGO ERP/_zcode_mvp_invariants_r1r1_frozen_cand.log` | 候选冻结全量运行原始输出（提交前脱敏摘录至 evidence/） |
| `C:/Users/Jeff0/MPANGO ERP/_zcode_mvp_invariants_r1r1_frozen_base.log` | BASE 冻结全量运行原始输出（同上） |
| `C:/Users/Jeff0/MPANGO ERP/_zcode_mvp_invariants_r1r1_env.sh` | 任务 env（合成口令，仓库外） |
| `C:/Users/Jeff0/MPANGO ERP/worktrees/zcode_mpango_mvp_invariants_r1_r1_2026-09-08` | 本任务 worktree（分支 zcode/mpango-mvp-invariants-r1-r1-test-evidence-closure-2026-09-08，BASE a516d2b3） |
| `C:/Users/Jeff0/MPANGO ERP/worktrees/zcode_mpango_mvp_invariants_r1r1_base_ref` | BASE(1485c3f5) 冻结差分专用 detached 工作树 |

## 遗留材料核查记录（F2 前置）

此前 R1 轮全量运行日志 `C:/Users/Jeff0/MPANGO ERP/_zcode_mvp_invariants_r1fix_fullsuite.log` 与
`..._base.log` 以 `-q -rfE` 运行：仅含 FAILED/ERROR 摘要行与文件级进度点（"s" 计数），
**不含 skip 节点 id 与原因**。结论：19 个新增 skip 的 nodeid/原因/运行身份无法从既有留存材料恢复，
如实标为未知；原"库态差异"归因为推测，已在勘误中撤回。恢复尝试记录：以 `grep "^SKIPPED"` 与
进度行复核，两日志均无 SKIPPED 摘要行（-rE 不含 S 报告）。

## 增补记录（R1-R2 整改，2026-09-08）

| 文件 | 用途 |
|---|---|
| `INTEGRITY_APPENDIX.md` | CTO 六项整改的更正与补强记录（VOID 标注、完整对账 3837/3824 与 18/5、真实 detect-secrets-hook、18 路径、双哈希/EOL、Redis 归属+精确键） |
| `evidence/` 增补 | 整改后聚焦两前提 + 三前提实测摘要（见 RUN_LOG §九） |

仓库外新增：`_zcode_mvp_invariants_r1r2_env_redis.sh` / `_zcode_mvp_invariants_r1r2_env_unreach.sh`
（整改轮 env，含/不含 MPANGO_INVARIANTS_R0_REDIS_CONTAINER 声明）。
原始日志不可覆盖原则维持：`_frozen_cand_VOID1.log` 等全部保留。
