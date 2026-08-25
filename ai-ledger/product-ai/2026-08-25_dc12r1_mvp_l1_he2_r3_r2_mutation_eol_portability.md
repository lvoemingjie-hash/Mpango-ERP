# DC-12R1-MVP-L1-HE2-R3-R2 — Mutation EOL 可移植性收口

- 日期：2026-08-25（+08:00）；执行者：ZCode（Codex 分支署名）
- BASE（BRANCH_BASE）：`68a68027e6b2d57ab35a77142b187c6301762de5`
- 分支：`codex/dc12r1-mvp-l1-he2-r3-r2-mutation-eol-portability-closure-2026-08-25`
- 接受证据：Kilo STOP `635128180d7207deb893874df771a9889e345807`（原样保留，
  不修改、不重写）
- 目标裁决：`SOURCE_GATE_PASS_BUT_REMOTE_ENFORCEMENT_NOT_VERIFIED`
  （本台账不声称本提交自身 SHA；最终远端 tip 于 push 后对话回报。）

## 1. 根因（Kilo STOP 的接受面）

R3-R1 的 `_run_validator_mutation` 以 canonical LF 字符串锚点直接在解码文本
上计数/替换——CRLF checkout（core.autocrlf=true）下锚点 0 命中，N20/N21
以 PATCH ANCHOR ERROR fail-closed，门禁在该类宿主上不可运行。本任务将
patch 应用逻辑改为 EOL 感知；不以 .gitattributes 强制 LF 掩盖缺陷
（validator/schemas/.secrets.baseline/workflow/产品代码零改动）。

## 2. 根因修复（`run_red_mutations.py`）

新增纯函数并重构 `_run_validator_mutation`：

1. `original = VALIDATOR.read_bytes()`（不变）。
2. `_detect_native_eol`：纯 LF → `"\n"`；纯 CRLF → `"\r\n"`；混合 → None。
3. `_N20_PATCH/_N21_PATCH` 保持 canonical LF 字符串。
4. `_to_native_eol` 在应用前把 old/new 转换为原文件 native EOL。
5. 锚点必须精确出现一次（0 或 >1 均 fail closed，类别
   `PATCH-ANCHOR-NOT-UNIQUE`）。
6. 变异文件以 native EOL bytes 写回（保持原 checkout 风格）。
7. finally 无条件写回 original 原始 bytes。
8. 恢复后比较**完整 SHA-256 与完整 bytes equality**（两者都要）。
9. 候选不被整体归一化为 LF（仅 patch 字符串自适应）。
10. 混合 EOL → `MIXED_EOL` fail closed，文件不被修改；
    PATCH ANCHOR ERROR 不计作 RED（FAIL CLOSED 单列）。

## 3. 直接真实性测试（`test_harness_governance_validator.py` +7）

以真实 `run_red_mutations` 模块的真实 helper（零 mock）：

- LF validator fixture（真实仓库字节）：N20/N21 均唯一命中。
- CRLF fixture（真实字节派生）：均唯一命中且变异保持纯 CRLF。
- LF/CRLF 变异结果语义一致（CRLF 归一后逐字节相等）。
- 写入-恢复循环 bytes 精确相同 + SHA-256 相同（两种 EOL 各验）。
- 混合 EOL 明确 fail closed（类别精确 + 文件未动）。
- 0 锚点与重复锚点明确 fail closed。

## 4. 真实双 checkout 门（全新 detached worktree）

- **A（core.autocrlf=false）**：validator CR=0 证明 + 完整 mutation gate
  （37 RED + 5 GREEN + TREE INTEGRITY OK）。
- **B（core.autocrlf=true）**：validator 与 mutation runner CR>0 证明 + 同一
  完整 gate；N20/N21 真实 mutation RED→恢复 GREEN，无 PATCH ANCHOR ERROR；
  `git -c core.autocrlf=true status` 工作树 clean。
- 两个 worktree 均不改候选 validator blob（status/digest 证明）。

## 5. Governance delta 与文件范围

- 新增 `PD-2026-08-25-HE2-R3-R2-MUTATION-EOL-PORTABILITY`：
  base_sha=`68a68027…`、kind=governance、affected_paths 仅
  `harness-governance/tests/`、approval_ref=DC-12R1-MVP-L1-HE2-R3-R2，
  未复用任何旧 ID。
- 授权文件恰 4 个：run_red_mutations.py、
  test_harness_governance_validator.py、protocol-deltas.json、本台账。

## 6. 完整门禁（结果见对话回报与 CI 证据）

全量 governance unittest（96/96）；37 RED + 5 GREEN + tree integrity
（LF/CRLF 各一轮）；structural `94b0c300..HEAD` exit 0；structural
`68a68027..HEAD` exit 0；release exit 3；git diff --check；pre-commit +
detect-secrets；strict UTF-8/no-BOM；`.secrets.baseline` 字节不变；
GitNexus impact 编辑前（LOW/0）+ re-analyze/status 提交后；候选 validator
与 `68a68027` 字节一致。

## 7. 证据纪律与 STOP

Kilo STOP `63512818` 原样保留；台账无自身 SHA 声明；push 后对话回报
BRANCH_BASE、IMPLEMENTATION_SHA、FINAL_REMOTE_TIP、local==remote；远端
required check 继续 NOT_VERIFIED。不启动 Kilo、H2-B-R3-R1、产品运行时、
Playwright、合并或部署。
