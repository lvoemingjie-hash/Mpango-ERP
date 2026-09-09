# Lubuntu V1-R1 独立验证 review — MPANGO-MVP-INVARIANTS-F1-DB-FIXTURE-ROLE-CLOSURE-R2

- 日期：2026-09-09
- 授权：`CTO-AUTH-MPANGO-F1-DB-ROLE-R2-LUBUNTU-V1-R1-2026-09-09`
- 执行者：**Claude Code on Lubuntu**（ivy-20149）——非 Codex-L；Codex-L 角色为监督/交接
- 分支基：本报告直接基于候选，parent == `e0a6363958142ecfbfc48f68cce73fb3a6c32349`（Git commit object ID）
- 候选：`e0a6363958142ecfbfc48f68cce73fb3a6c32349`（Git object ID）；候选字节零写入
- 验证层级：V3_MERGE_CRITICAL；声明上限：LUBUNTU_CURRENT_CANDIDATE_REAL_PG_FIXTURE_LIFECYCLE_ONLY

## 裁决

```text
STOP_AND_REPORT_CTO
R1_DISPOSITION=VOID_ENVIRONMENT_PRECHECK
R1_CAUSE=EXECUTOR_PRECHECK_HARNESS_EXTRACTION_BUG
R1_FORMAL_PYTEST_INVOCATIONS=0
R1_TEST_BODIES_EXECUTED=0
R1_MIGRATION_EXECUTED=NO
PRODUCT_VERDICT=NOT_EVALUATED_BY_THIS_ATTEMPT
LUBUNTU_MUTATION=NOT_RUN_THIS_ROUND
```

失败发生在冻结后的运行时预检（P3 末段）：执行者自写的预检脚本在提取 docker 端口绑定时发生 shell/Python 引号嵌套缺陷（`NameError`），预检返回非预期 rc=1。按授权书「首次非预期失败 → VOID_ENVIRONMENT_PRECHECK，立即清理并 STOP，不得重新预检」执行，未修脚本重跑、未换栈、未改输入。

同一预检中其余全部实质性检查**首次检查即通过**（双连接真实身份、角色五布尔 flag、零成员、空 public 前态、四项规定权限、迁移日志为空）；清理前留档的容器 inspect（已脱敏）独立证明端口绑定实为 `127.0.0.1:55442` —— 环境合规，失败纯粹在提取器。候选缺陷证据：无。

## 独立证据（本轮真实执行，Lubuntu）

证据根（任务机）：`/home/ivy/AI_REPORT_INBOX/mpango-mvp-invariants-f1-db-fixture-role-closure-r2-lubuntu-v1-r1-2026-09-09/`
原始 STOP 记录：同目录 `STOP_RECORD.md`（SHA-256 见 findings.csv，哈希算法为 SHA-256，非 Git object ID）。

| 门 | 结果 | 证据（相对证据根） |
|---|---|---|
| P0 fetch 后 SHA/parent/路径集合复核 | PASS | `logs/p0_proof.log` |
| 旧 STOP 记录 SHA-256 复核（== CTO 实测） | PASS | `logs/p0_proof.log` |
| 新 LF detached worktree（4 文件 blob==file、0 CR/0 NUL、UTF-8） | PASS | `logs/p0_proof.log`, `logs/static_gates_r1.log` |
| `.secrets.baseline` SHA-256 == CTO 重算值（扫描前后一致） | PASS | `logs/detect_secrets_r1.log` |
| P1 CTO 配置脚本（SHA-256 `4d2e97b0…2335`）首次执行 rc=0，24 布尔全 true，0 连接 | PASS | `logs/config_check_p1_attempt1.json` |
| 冻结清单（候选/Python/CWD/env/launcher/argv/端口声明） | DONE | `logs/freeze_manifest.md` |
| P2 冻结后配置检查 rc=0 | PASS | `logs/config_check_p2_frozen.json` |
| P2 collect-only rc=0，恰 21 节点，nodeids 全量留档 | PASS | `logs/collect_only_r1.log`, `logs/collect_nodeids_r1.txt` |
| diff-check（ae84..e0a6、76ab..e0a6）rc=0 ×2 | PASS | `logs/static_gates_r1.log` |
| detect-secrets canary rc=1（真实检出）/ 正式 4 路径 rc=0 | PASS | `logs/detect_secrets_r1.log` |
| P3 唯一 PG16 栈 + 三身份供给（脚本完整写好后一次 rc=0） | PASS | `logs/provision_r1.log` |
| P3 冻结运行时预检（执行一次） | **FAIL rc=1（harness 提取缺陷）** | `logs/runtime_precheck_r1.log`, `logs/container_inspect_r1.json`（已脱敏） |
| 清理（容器/卷/端口/worktree/凭据）+ 既有容器零接触 | DONE | `logs/cleanup_r1.log` |

环境声明一致性（公开布尔值）：DATABASE_URL scheme=postgresql:// TRUE；TEST==DATABASE 字节相同 TRUE；迁移同库不同用户 TRUE；owner 标签 zcode-mvp-invariants- 前缀 TRUE；SECRET_KEY/REPORTING_USER_PASSWORD/REDIS_URL 均为显式独立声明（非 conftest 默认、无未知 .env 补齐）TRUE；私有 env 文件 0600、原字节一致性核验在私有区域执行 TRUE。

## 测试到代码路径映射（候选声明 vs 本轮状态）

21 节点 = 8 F1 守卫/身份 Coroutine 节点 + 1 正控全生命周期 Coroutine + 8 F1 计数器/脱敏 Function 节点 + 4 R2 新增 Function 节点（domain self-check、nonzero 内容断言、timeout bytes、落盘日志）。映射见候选 REPAIR_LEDGER 与本轮 `collect_nodeids_r1.txt`。**本轮 21 节点全部未获正式执行**（formal=0），collect-only 仅证明可收集。

- 新增/修改测试覆盖：候选相对 F1_BASE 的 4 路径与 R2 的 3 路径集合经独立复核（Git 路径集合，非内容重述）；节点级覆盖结论待正式运行。
- 未覆盖项（本轮）：真实 001→037 迁移链、运行身份 bootstrap/读写/清理、负控真实顺序、R2 三脱敏出口真实运行、变异（授权内 NOT_RUN）、guards 全量/四文件矩阵/全量后端/浏览器（授权范围外）。

## 先验证据（仅关联，非本轮复现）

- 旧 V1 轮 Lubuntu 证据（源码审查、GitNexus 353s 索引、静态门）：候选字节未变，按 SHA 关联保留；GitNexus 自报截断限制不变。
- Kilo `22ba1059c1f018f8ca848b1beef785365b1dfc0a`（Git object ID）PASS：唯一 parent == 候选（本轮复核 TRUE）。其报告把两个 40 位 Git blob object ID 标为 SHA-256，属报告元数据问题（CTO 已记录，归档须更正）；本轮 findings.csv 中所有 64 位哈希均为真实 SHA-256、40 位均为 Git object ID，不混称。
- 作者提交消息声明（21/21、MC2 变异恢复等）：未由本轮独立复现。

## 已知产品 RED 保留

候选整体的重复退货 RED、缓存隔离 RED/SKIP 为既有登记项，本轮未触碰、不消除、不据本文件作出任何放行结论。

## 计数（V1→V1-R1 链）

formal pytest：旧 1 + 本轮 0 = 累计 1；test bodies：累计 0；collect：旧 1 + 本轮 1；配置检查：本轮 2（均 rc=0）；供给：旧 1 + 本轮 1（rc=0）；运行时预检：本轮 1（rc=1）；PREPARATION_RED：本轮 0。

## 泄漏披露

清理前留档的容器 inspect JSON 含 docker env 内 bootstrap 口令 1 处 → 已脱敏 → 对公开证据区以全部口令形态（raw/quote/quote_plus）+ SECRET_KEY 复扫 CLEAN。provision/precheck 日志本身不含口令。凭据材料已销毁，私有 env 已脱敏保留结构。

## 建议（供 CTO 定性，非执行者自行豁免）

预检 harness 应纳入 P1 可迭代离线准备范围（对合成 inspect 形状演练），使冻结后不存在未演练代码路径。是否授权 V1-R2 由 CTO 决定。
