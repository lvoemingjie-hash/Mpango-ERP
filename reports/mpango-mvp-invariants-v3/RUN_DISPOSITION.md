# RUN DISPOSITION — MPANGO-MVP-INVARIANTS-R1-REVOCATION-STOCK-V3-VPS(append-only)

DATE: 2026-09-16 | EXECUTOR_AS_AUTHORIZED: Kilo | ACTUAL_EXECUTOR: Zcode-W(差异已登记)
CTO_RULING: FORMAL_RESULTS_RETAINED__EVIDENCE_CHAIN_INSUFFICIENT__NO_ACCEPTANCE
(复核记录:AI_REPORT_INBOX 内 CTO 对 invariants-v3 运行的只读复核;REPORT_COMMIT 基线见 git 历史)

## CTO 只读复核确认的可信事实(不撤回)
- 收集:52 items / 1 deselected / 51 selected
- 正式:51 passed / 0 failed / 0 errors / 0 skipped,rc=0
- 7 个并发节点已执行;已知重复退货节点未出现在选中集合(与授权排除一致)

## 三项发现与处置
1. P1 凭据文件:.pg16-credentials(48 字节,mtimes 2026-09-16 17:53:30+08)→ **已按精确路径销毁**(shred/rm,2026-09-16T19:52:26+08,内容从未读取、未哈希、未转存);同目录余 evidence/results/tools,无其他凭据文件。
2. P1 证据链不足:预检/身份/策略绑定/资源绑定材料未保留于声明任务根;worktree 已在此前清理中移除,无法重绑字节。**如实接受**;不做任何补造。
3. P2 共享 venv(sku-delivery-r2-v4-r1/venv)非本任务冻结环境:**如实登记**;不必然致错,但独立环境证据不成立。

## 处置结论
- 本轮降级为 **NO_ACCEPTANCE**(原 PASS 声明作废,以本文件为准)。
- 撤权与库存:**独立验收未闭合**;不合并、不部署。
- 后续:如需权威结论,由 CTO 另行授权 **V3-R1**(新 worktree、新任务专属 venv、运行前持久化 preflight/身份/资源绑定/策略实例类型、规范 nodeid 清单 + JUnit,再唯一一次正式调用)。
- 六项修复的行为验证事实(51 passed)保留原样,不据以升级任何结论。
