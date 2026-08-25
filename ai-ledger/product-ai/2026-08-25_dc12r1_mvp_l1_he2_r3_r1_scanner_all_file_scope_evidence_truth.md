# DC-12R1-MVP-L1-HE2-R3-R1 — Scanner 全文件范围与证据真相收口

- 日期：2026-08-25（+08:00）；执行者：ZCode（Codex 分支署名）
- BASE（BRANCH_BASE）：`d7ea8027bf7d4ba5ec0a8d2f92965e5061680f34`
- 分支：`codex/dc12r1-mvp-l1-he2-r3-r1-scanner-all-file-scope-evidence-truth-closure-2026-08-25`
- 目标裁决：`SOURCE_GATE_PASS_BUT_REMOTE_ENFORCEMENT_NOT_VERIFIED`
  （本台账提交内部不声称本提交自身 SHA；最终远端 tip 于 push 后在
  对话回报中报告。）

## 1. 证据真相修正（历史真实链）

- **真实链（git 逐提交核实）**：
  `077774e7967bc0cfcfec822a16bd73dcdba901c0`（R3 实现）
  → `8eb61d21b5d23b2052c4a92c33aca6336ee259c4`（R3 delivery ledger SHA 更新）
  → `d7ea8027bf7d4ba5ec0a8d2f92965e5061680f34`（R3 FINAL_REPORT_TIP 文档更新；
  即本任务 BASE）。
- 旧 R3 台账中的 `FINAL_REPORT_TIP = 8eb61d21` 及一切 parent/tip 声明标记为
  **SUPERSEDED_METADATA_ONLY**（旧文件顶部已加横幅）；其门禁结论与 delta
  链仍然有效。
- 远端强制执行状态维持"未验证"（branch protection 未确认）——正是本任务
  目标裁决的第二个从句。

## 2. Scanner 全文件范围（`_check_scanner_scope` 重写）

- **候选集**：`git ls-files --cached --others --exclude-standard -z`（先以
  `rev-parse --show-toplevel == root` 防御外层仓库误挂载）；root 非 git
  工作树（单测临时目录）时回退 `os.walk`。
- **无扩展名白名单**：.py/.ts/.tsx/.md/.yaml/.yml/.toml/.env/json 及一切
  版本控制内普通文件均在扫描面。
- **bytes 逐行匹配**：新增 `_SCANNER_HEX_RE_BYTES`（ASCII bytes 正则），
  文件以二进制读入按行切分——不存在 `errors=replace` 解码路径，不可能
  静默跳过。
- **豁免**：仅五个 `_SCANNER_ALLOWED_FILES` 精确路径可含匹配行；目录排除
  仅经 gitignore（ls-files --exclude-standard）或固定常量
  `FS_COMPARE_IGNORE`（.git/__pycache__/node_modules/.pytest_cache/.venv/
  .gitnexus）——不可经任何可编辑配置关闭。
- 真实仓库全树试跑 GREEN（无误伤）。

## 3. 新增真实性测试（`test_harness_governance_validator.py`）

- `backend/probe.py` 精确 `evidence_sha` 行 → SCANNER-SCOPE-VIOLATION（RED）。
- `frontend/src/probe.ts`、`docs/probe.md`、`workflow/probe.yml`、
  `config/probe.toml` 同形行均 RED（无扩展名白名单的直接证明）。
- 任意 key（commit_hash）、前后附加 secret、错误长度（8/39/65 hex）继续
  GREEN（不误报）；40 与 64 hex 两种长度 RED。
- git 工作树内 tracked `.py` 探针 RED（覆盖 ls-files 路径）。
- 五个允许治理 JSON 合法行 GREEN，且同一报告中 schema/delta/evidence
  校验照常执行（非整体跳过）。
- R2 binary raw-blob 测试全部保留（N15/EVIDENCE-BLOB-MISMATCH 等）。

## 4. 变异门

- **N20**：恢复 `*.json`-only 过滤（扫描循环内）→ py/ts 探针逃逸 → 门禁 RED。
- **N21**：删除非 JSON 路径扫描（候选生成处加 .json 过滤）→ 同 RED。
- 每次变异后验证器文件字节级恢复（sha256 对账）并以恢复版复证探针
  重新 RED；候选树 `tree-integrity` before==after。
- 门禁汇总：**37 RED**（34 显式规则码 + N20/N21 验证器范围）+ 5 GREEN
  控制 + TREE INTEGRITY OK。

## 5. Protocol delta

新增 `PD-2026-08-25-HE2-R3-R1-ALL-FILE-SCOPE`（kind=governance、
base_sha=`d7ea8027…`、owner=cto、approval_ref=DC-12R1-MVP-L1-HE2-R3-R1），
affected_paths 仅本轮实际受保护路径：`harness-governance/validator/`、
`harness-governance/tests/`。不复用任何旧 delta ID。

## 6. 本轮文件清单

1. `harness-governance/validator/harness_governance_validator.py`（范围重写）
2. `harness-governance/tests/test_harness_governance_validator.py`（+12 测试）
3. `harness-governance/tests/run_red_mutations.py`（N20/N21 + VALIDATOR_MUTATIONS）
4. `harness-governance/inventory/protocol-deltas.json`（+1 delta）
5. `ai-ledger/product-ai/2026-08-25_...he2_r3_...md`（SUPERSEDED 横幅）
6. 本台账

## 7. 门禁结果（见对话回报与 CI 证据）

全量治理 unittest 89/89；RED mutations 37 + GREEN 5 + tree-integrity OK；
structural `94b0c300..HEAD` exit 0；structural `d7ea8027..HEAD` exit 0；
release exit 3（RELEASE_GATE=BLOCKED，P0/P1 债务按设计阻断）；
git diff --check、pre-commit、detect-secrets、strict UTF-8/no-BOM、
`.secrets.baseline` LF-only 全绿；GitNexus analyze/status 完成（同名图
噪声如有将披露）。

## 8. STOP

不启动 Kilo、不启动 H2-B-R3-R1、不启动产品运行时、不合并。
push 后于对话中回报 BRANCH_BASE、IMPLEMENTATION_SHA、
REPORT_CONTENT_PARENT、FINAL_REMOTE_TIP 及 local==remote。
