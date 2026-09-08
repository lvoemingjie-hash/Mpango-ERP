# SELF_REVIEW（R1-R1 提交前全面自查）

> 逐项给出证据位置与判定（PASS / KNOWN_RED / NOT_PROVEN）。自查不是独立评审。
> 证据根目录：本目录（E=）、候选 worktree（W=worktrees/zcode_mpango_mvp_invariants_r1_r1_2026-09-08）、
> 仓库外原始日志（R=C:/Users/Jeff0/MPANGO ERP/_zcode_mvp_invariants_r1r1_*.log）。

## A. 正确性：三项发现逐一对应真实入口、正常对照和独立失败原因

| 项 | 判定 | 证据 |
|---|---|---|
| F1 隔离证明改用同参同码+记录级断言 | **PASS** | 真实入口：`test_r1_control_tenant_isolation_same_query_same_code_db_only`（W/backend/tests/test_mpango_mvp_invariants_r0_revocation.py，GET /api/v1/skus 真实 HTTP，两租户 IDENTICAL q 参数、同一 sku_code、不同 id+name）；共享断言 `assert_listing_exactly_own_tenant`（同文件，唯一实现）；正常对照接受本租户记录（聚焦冻结两前提均 PASS，R=_focused_unreach.log/_focused_reach.log）；反例拒绝混合/异租户结果（guards 5 节点中 2 个，W/.../test_mpango_invariants_r0_r1_guards.py 末节，调用同一共享函数） |
| F3 三个解耦负控 | **PASS** | (a) 活租户内缺用户 → `test_r1_refresh_nonexistent_user_in_active_tenant_principal_branch`（POST /api/v1/auth/refresh 真实 HTTP，断言 code==PRINCIPAL_NOT_FOUND——租户分支 TENANT_NOT_FOUND 不能再遮蔽）；(b) 仅改签名 → `test_r1_control_refresh_wrong_signature_refused`：claims 从真实签发 token 解码后仅换签名键（`_forged_refresh`），录制哨兵证明 `_validate_contextual_refresh_subject` 未被调用，断言 code==INVALID_REFRESH_TOKEN；(c) 主体查询有界故障 → `test_r1_refresh_subject_db_fault_zero_issuance`：FastAPI dependency_override 仅对 `{schema}.users` SELECT 注入即时异常（真实路由/真实批发商查询不受影响），断言 issuer 调用计数==0、响应无 token、状态非 2xx（不伪装 401），随后同主体故障解除后 200 正常签发 |
| F2 最终字节全量差分 | **PASS** | E=/RUN_IDENTITY_CANDIDATE.md、RUN_IDENTITY_BASE.md、NODE_RECONCILIATION.md；R=_frozen_cand.log、_frozen_base.log（原始，未覆盖）；两侧等价独立容器+同 venv+同命令+同准备步骤；汇总与逐节点均命中预列 EXPECTED_SET |

## B. 反例强度：错租户、错误签名、缺用户、数据库故障不被无关守卫遮蔽

| 项 | 判定 | 证据 |
|---|---|---|
| 混合/异租户结果被共享断言拒绝 | **PASS** | guards::`rejects_mixed_tenant_results`、`rejects_foreign_tenant_result` 喂坏形状给真实共享断言 → AssertionError（含 "CONTROL_R1_ISOLATION"）；guards 全文件 31/31 PASS（R=_focused_unreach.log） |
| 签名层失效可被察觉 | **PASS** | FM2 证伪（开发期，core/security.py decode_token 注入 verify_signature=False → 错误签名节点 RED：实际签发了会话，401 断言失败）；恢复后 sha256 `c983b2af…` 字节一致（/tmp/r1r1_bak/security.sha 记录，dev-only，未入候选） |
| 缺用户分支独立命中 | **PASS** | (a) 节点断言具体 code==PRINCIPAL_NOT_FOUND；遮蔽形态被 guards::`rejects_masked_code` 反例拒绝（TENANT_NOT_FOUND 形状喂入必须 raise）；FM1 证伪（开发期移除 `_validate_contextual_refresh_subject(db, payload)` 调用 → 该节点 RED）后 auth.py sha256 `dbdbac96…` 字节恢复一致（/tmp/r1r1_bak/auth.sha） |
| 数据库故障不签发 | **PASS** | 节点内置 `fault["hits"]>=1` 空转护栏（故障未触发即 fail）+ issuer 计数==0 + 无 token 断言；guards::`no_issuance_assertion_rejects_issuer_use_and_tokens` 证明 issuer 被调用/带 token 两种坏形状均被真实共享断言拒绝；FM1 同样使该节点 RED（harness 护栏触发） |

## C. 事务与资源

| 项 | 判定 | 证据 |
|---|---|---|
| 失败回滚/并发任务终结/部分夹具失败清理 | **PASS（本轮未改动这些路径，R0-R2 对照保持）** | 聚焦冻结 51 PASS 含 barrier-timeout/task-exception/rejected-return-rollback 三对照（R=_focused_*.log 逐节点行） |
| 原始流水不折叠 | **PASS** | concurrency::`r1_control_adjustment_read_helper_preserves_duplicate_rows`（DB 级：注入重复 reason 行后读取 helper 返回原始 2 行、共享断言拒绝）；全量与聚焦均 PASS |
| 任务归属及零残留 | **PASS** | 每次运行的会话夹具七重归属核验（容器/标签/镜像/端口/db/user/引擎/探针）；聚焦运行后 t_%=0（dev 容器核验）；全量残留为既有失败文件临时 schema，随任务容器销毁；VOID-1 容器已删除；dev/cand/base 容器全部带任务标签（清理见 RUN_LOG §资源） |
| 已知双退 RED 不折叠流水 | **PASS** | 聚焦/全量中 `red_concurrent_full_return...` 保持 FAILED（KNOWN_RED，-200.0000） |

## D. 回归证据

| 项 | 判定 | 证据 |
|---|---|---|
| 每次运行绑定精确字节 | **PASS** | E=/RUN_IDENTITY_*.md：HEAD/树哈希 + 4 个测试文件 SHA256 + 容器 ID/env/venv 版本/命令/退出码；BASE 侧为 detached 干净树 |
| 逐节点变化完整 | **PASS** | E=/NODE_RECONCILIATION.md §1-§5：共享节点唯一状态变化=目标反例转绿；候选+15（逐个归类）/BASE+2（更名+随机参数化）；FAILED 差=1、ERROR 差=6（同机制新节点）、SKIP 集合恒等 |
| skip 与未证明范围显式列出 | **PASS** | E=/NODE_RECONCILIATION.md §6（skip 原因全录+上轮 19-skip 差文件级归因）；未证明范围见 §F 未覆盖清单 |

## E. 范围

| 项 | 判定 | 证据 |
|---|---|---|
| 产品与冻结路径无漂移 | **PASS** | `git status`：仅 3 个允许测试文件修改 + support name 参数 + 本目录/报告文档；pw1r3/产品/迁移/依赖锁/.secrets.baseline 零字节变化（BASE..工作树 diff 仅列允许文件）；证伪变异全部 sha256 恢复且不入候选 |
| 未把测试预期改成产品错误结果 | **PASS** | 全部新断言断言"正确行为"（隔离、独立分支、零签发、缓存租户安全）；命名 RED（缓存诊断）断言的是登记风险的**反面（正确不变量）**，其 RED 即风险存在性证明；无任何断言被放松（聚焦断言值与 R0-R2 一致，撤权 RED 节点断言原样） |

## F. 发布

| 项 | 判定 | 证据 |
|---|---|---|
| 累计 diff | **PASS** | 提交前 `git status --porcelain` + `git diff --stat` 逐文件核对 = FILES_MANIFEST §冻结清单（3 测试修改 + support + 3 报告勘误 + 本目录 6 文件 + RUN_LOG 增节） |
| 严格编码 | **PASS** | 12 个变更文件 UTF-8 无 BOM 校验（Python 逐文件 decode + BOM 检查，PASS，本轮运行记录于命令历史） |
| diff-check | **PASS** | `git diff --check`（含 --cached）rc=0 |
| 只读秘密扫描（实际 argv/rc） | **PASS** | argv：`python -m detect_secrets.main hook --baseline .secrets.baseline <12 个变更文件>`；rc=0；`.secrets.baseline` 前后 sha256 `f49c86223abc95af12d0f6c60938050a68a84e332a94a444800cd93450bd16bf` 不变 |
| 清单与实际提交一致 | **PASS** | 提交后 `git show --stat HEAD` 对照 FILES_MANIFEST（见 RUN_LOG §提交记录） |
| GitNexus | **PASS（有据披露）** | `gitnexus analyze --skip-agents-md`（本 worktree 索引 zcode_mpango_mvp_invariants_r1_r1_2026-09-08，exit 0）；`impact` 三共享助手均 0 上游/LOW（索引在测试字节定稿后建立）；`gitnexus detect-changes` CLI 1.5.3 无此子命令（`unknown command`）——与前两轮记录一致（MCP-only 面），如实披露并以 `git status` + staged diff 逐文件核对替代，不以文件计数冒充图分析 |
| local==remote | **PASS（推送后外部核验）** | 见 RUN_LOG §提交记录（推送后 ls-remote 比对） |

## G. 未覆盖 / NOT_PROVEN 清单

1. **NOT_PROVEN：缓存可达同键跨租户读的修复**——本轮仅复现并命名 RED（授权边界），缓存实现未改，风险仍在。
2. **NOT_PROVEN：撤权文件的全量内执行**——既有 MPANGO_ENV 收集期泄漏使其全量内恒 ERROR；其权威证据绑定聚焦冻结运行。全量内"撤权修复在全量环境也可用"不可由本差分证明（两侧同受限，非本轮差异）。
3. **NOT_PROVEN：任意声明替换令牌（伪造已签名 claims）**——属签名伪造场景，本轮仅在"仅改签名"维度验证。
4. **identity-only refresh、select-tenant 铸造、deduct_stock/restock 锁刷新、logout/密码重置撤销**——维持上轮登记，未获授权，未验证修复。
5. skip 节点的"应跳过理由正确性"按其显式前提文本采信（预置 schema/环境变量类），未逐条独立复验跳过条件本身。
