# DC-12R1-MVP-L1-HE2-R3-R1-V1 — Kilo Final Cumulative Governance Review

- 日期：2026-08-25（+08:00）；审查者：Kilo
- 模式：源码真实性审查（冻结状态，只读审查 + 独立测试运行，不合并、不部署、不启动 H2-B-R3-R1）
- 审查对象：`68a68027e6b2d57ab35a77142b187c6301762de5`
- 父提交：`d7ea8027bf7d4ba5ec0a8d2f92965e5061680f34`（R3 FINAL_REPORT_TIP）
- 分支：`codex/dc12r1-mvp-l1-he2-r3-r1-scanner-all-file-scope-evidence-truth-closure-2026-08-25`

## 执行边界声明

- **未运行 Playwright**（无浏览器旅程、无运行时 JSON/JUnit）
- **未启动产品运行时**（无 backend、无前端 dev server、无 PG/Redis）
- **未合并、未部署、未启动 H2-B-R3-R1**
- 独立运行了 unittest 和 mutation gates（见 Phase 4）

## 冻结输入

| 项目 | 值 |
|------|-----|
| 候选 | `68a68027e6b2d57ab35a77142b187c6301762de5` |
| 父提交（R3-R1 base） | `d7ea8027bf7d4ba5ec0a8d2f92965e5061680f34` |
| 累计 base | `94b0c30034d04d1bad87f926a4b09e3dbbe3c6db` |
| 中间 base | `5a380586caab4f662d7e1dfbc7899cf5bd3bc300` |
| 分支 | `codex/dc12r1-mvp-l1-he2-r3-r1-scanner-all-file-scope-evidence-truth-closure-2026-08-25` |
| V2 STOP | `3fb185be25b51ae4554c58e8c06c795673c058dd` |
| V3 STOP | `888fd2072afd77d54881e834c592a4b0f587b271` |
| Lubuntu STOP | `f7dd9aa3331217af2f5cab68dad7aa533093401f` |

## Phase 1 — Proof Gate

| 步骤 | 结果 | 证据 |
|------|------|------|
| `git fetch --all --prune` | 通过 | 远程分支存在 |
| 候选 == remote tip | 通过 | `68a68027` == `origin/codex/...` |
| `candidate^` == `d7ea8027` | 通过 | `git rev-parse HEAD~1` = `d7ea8027` |
| `94b0c300` 是祖先 | 通过 | `git merge-base --is-ancestor 94b0c300 HEAD` = true |
| R3-R1 delta 恰好 6 文件 | 通过 | `git diff --name-status d7ea8027..HEAD` = 6 文件 |
| 累计 delta 恰好 19 文件 | 通过 | `git diff --name-status 94b0c300..HEAD` = 19 文件 |
| product-dev-recovered/main 与产品路径未变 | 通过 | `git diff --name-only 94b0c300..HEAD` 无产品路径 |

### R3-R1 Delta 文件清单（6 文件）

1. `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r3_delta_chain_scanner_bypass_closure.md` — 更新（旧台账标记 SUPERSEDED）
2. `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r3_r1_scanner_all_file_scope_evidence_truth.md` — **新增**：R3-R1 台账
3. `harness-governance/inventory/protocol-deltas.json` — 更新（新增 PD-2026-08-25-HE2-R3-R1-ALL-FILE-SCOPE delta）
4. `harness-governance/tests/run_red_mutations.py` — 更新（新增 N20/N21 + scanner probes）
5. `harness-governance/tests/test_harness_governance_validator.py` — 更新（新增 scanner scope/strictness tests）
6. `harness-governance/validator/harness_governance_validator.py` — 更新（_check_scanner_scope 全文件扫描）

### 累计 Delta 文件清单（19 文件，从 94b0c300）

**新增（7）：**
1. `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r1_machine_enforced_harness_governance.md`
2. `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r2_evidence_byte_integrity_packaging_closure.md`
3. `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r3_delta_chain_scanner_bypass_closure.md`
4. `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r3_r1_scanner_all_file_scope_evidence_truth.md`
5. `harness-governance/schemas/governed-paths.schema.json`
6. `.github/workflows/harness-governance-gate.yml`
7. `.secrets.baseline`

**修改（12）：**
1. `decision-register/2026-08-25_harness-governance-tooling-he2.md`
2. `harness-governance/README.md`
3. `harness-governance/governed-paths.json`
4. `harness-governance/inventory/protocol-deltas.json`
5. `harness-governance/schemas/coverage-debt.schema.json`
6. `harness-governance/schemas/critical-interactions.schema.json`
7. `harness-governance/schemas/inventory.schema.json`
8. `harness-governance/schemas/protocol-deltas.schema.json`
9. `harness-governance/schemas/waivers.schema.json`
10. `harness-governance/tests/run_red_mutations.py`
11. `harness-governance/tests/test_harness_governance_validator.py`
12. `harness-governance/validator/harness_governance_validator.py`

## Phase 2 — Cumulative Source Review

### 2.1 治理核心不可由配置或 waiver 关闭

| 检查项 | 结果 | 证据 |
|--------|------|------|
| PROTECTED_PATHS 硬编码 | PASS | `harness_governance_validator.py:87-94` 硬编码 `PROTECTED_PATHS` |
| 配置无法移除保护路径 | PASS | `_check_config_semantics` 验证 governed-paths.json 不能移除 `PROTECTED_PATHS` 中的路径 |
| Waiver 不能覆盖保护路径 | PASS | `_check_waivers` line 978-987: `path_matches(path, protected)` 触发 `WVR-PATH-PROTECTED` |
| 最小 governed prefixes 不可移除 | PASS | `MINIMUM_GOVERNED_PREFIXES = ("backend/", "frontend/src/", "scenarios/")` 硬编码 |

### 2.2 Semantic inventory sync 不可由 notes/无关 JSON 绕过

| 检查项 | 结果 | 证据 |
|--------|------|------|
| NON_SEMANTIC_FIELDS 排除 notes | PASS | `NON_SEMANTIC_FIELDS = frozenset({"notes"})` |
| Sync 要求实际记录变更 | PASS | `_check_semantic_sync` line 1417-1421: `changed_keys` 通过 `semantic_view(item)` 比较，notes-only 变更不产生 `changed_keys` |
| 无关 JSON 不满足 sync | PASS | 仅 node anchor、interaction source/affected path、debt affected path、protocol delta 覆盖 sync |

### 2.3 Waiver 路径、期限、风险、approval_ref 全部 fail-closed

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 路径必须非空 | PASS | `_check_waivers` line 957-963 |
| 禁止通配符 | PASS | `WILDCARD_RE.search(path)` 触发 `WVR-PATH-INVALID` |
| 禁止 repo root 形式 | PASS | path in `{"", ".", "/", ".."}` 触发 `WVR-PATH-INVALID` |
| 保护路径不可 waiver | PASS | `WVR-PATH-PROTECTED` |
| 过期自动失效 | PASS | `is_expired` check，expires < today → `WVR-EXPIRED` |
| owner/reason/risk/approval/dates 必填 | PASS | schema validation + `_check_waivers` |

### 2.4 PASS evidence 必须绑定可达 commit、存在路径及 raw blob SHA-256

| 检查项 | 结果 | 证据 |
|--------|------|------|
| evidence_paths 必填 | PASS | `_verify_one_pass_node` line 1549-1556 |
| evidence_commit 必须存在且可达 | PASS | `git cat-file -t` + `git branch -a --contains` + `git tag --contains` |
| 64-hex evidence_sha 必须绑定 commit | PASS | line 1566-1577 |
| 64-hex blob SHA-256 验证 | PASS | `_git_raw` 返回 bytes，`hashlib.sha256(blob.stdout).hexdigest()` 比对 |
| 40-hex evidence_sha 视为 commit | PASS | line 1566: `COMMIT_SHA_RE.match(evidence)` |

### 2.5 Protocol delta base-bound、kind-bound、不可历史 replay

| 检查项 | 结果 | 证据 |
|--------|------|------|
| base_sha 必须匹配 | PASS | `DeltaAuthorizer.__init__` line 596: `delta.get("base_sha") != base_sha` → RED |
| kind 精确授权 | PASS | `authorizer.authorize(kind, ids=...)` |
| 历史 delta 不可 replay | PASS | `_check_drift` line 1259: `"a historical delta cannot be reused"` |
| 未授权状态转换 | PASS | `_check_status_transitions` |

### 2.6 Schema unknown keyword/bad ref/anchor 越界全部 RED

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 未知 schema keyword | PASS | `check_schema_document` line 316-322: `SCHEMA-UNKNOWN-KEYWORD` |
| 不可解析 $ref | PASS | `_resolve_ref` + `SCHEMA-BAD-REF` |
| Anchor 行号越界 | PASS | `_check_anchor_targets` line 990-1039 |
| 仅支持固定关键字集 | PASS | `SUPPORTED_SCHEMA_KEYWORDS` frozenset |

### 2.7 Structural 与 release gate 语义分离

| 检查项 | 结果 | 证据 |
|--------|------|------|
| structural exit 0 | PASS | 验证器运行通过 |
| release exit 3 | PASS | 存在 open P0/P1 release-blocking debt |
| RELEASE_GATE=BLOCKED | PASS | `DEBT-AUTH-CRITICAL-TUPLES` 和 `DEBT-COMMERCE-CRITICAL-TUPLES` 为 P0 release_blocked |
| Structural GREEN 不构成 release 声明 | PASS | render_markdown line 1730: "Structural GREEN is not a release statement" |

## Phase 3 — Scanner Adversarial Review

### 3.1 全文件扫描范围

| 检查项 | 结果 | 证据 |
|--------|------|------|
| git ls-files --cached --others --exclude-standard | PASS | `_scanner_candidate_files` line 1064-1086 |
| os.walk fallback | PASS | line 1090-1096，固定目录排除 |
| 无扩展名白名单 | PASS | 无 `endswith` 过滤 |
| 排除仅 via gitignore + 固定 FS 集合 | PASS | `FS_COMPARE_IGNORE` frozenset |

### 3.2 十六进制密钥检测

| 检查项 | 结果 | 证据 |
|--------|------|------|
| exact base_sha/evidence_sha/evidence_commit 40/64 hex | PASS | `_SCANNER_HEX_RE_BYTES` regex |
| 五个允许文件外必须 RED | PASS | `_SCANNER_ALLOWED_FILES` frozenset，测试 `test_backend_python_with_exact_evidence_sha_line_is_red` 通过 |
| 任意 key 不被排除 | PASS | `test_arbitrary_key_not_excluded` |
| 前后附加 secret 不被排除 | PASS | `test_prefix_and_suffix_attached_values_stay_green` |
| 错误长度不被排除 | PASS | `test_wrong_length_hex_not_excluded` |
| bytes regex 匹配，无 decode | PASS | `_SCANNER_HEX_RE_BYTES` 使用 `rb'...'` 原始字节 |
| 字符串 regex 与 bytes regex 语义一致 | PASS | `_SCANNER_HEX_RE` (str) 和 `_SCANNER_HEX_RE_BYTES` (bytes) 模式相同 |

### 3.3 detect-secrets 与 .secrets.baseline

| 检查项 | 结果 | 证据 |
|--------|------|------|
| detect-secrets scan clean | PASS | `detect-secrets scan ... --baseline .secrets.baseline` exit 0 |
| .secrets.baseline 0 secrets | PASS | `results` 数组长度为 0 |

### 3.4 git ls-files 与 os.walk fallback

| 检查项 | 结果 | 证据 |
|--------|------|------|
| git ls-files 路径核验 | PASS | `_scanner_candidate_files` 先尝试 git ls-files |
| os.walk fallback 核验 | PASS | 当非 git work tree 时使用 os.walk |
| bytes 匹配 | PASS | `content.splitlines()` + `_SCANNER_HEX_RE_BYTES.match(line)` |
| 无 errors=replace decode | PASS | 文件以 `"rb"` 模式读取，不做文本 decode |

## Phase 4 — Test Authenticity

### 4.1 独立运行 89/89 unittest

| 检查项 | 结果 |
|--------|------|
| unittest 数量 | 89 |
| 通过 | 89 |
| 失败 | 0 |
| 命令 | `python -m unittest harness-governance.tests.test_harness_governance_validator -v` |
| 耗时 | ~27.7s |

### 4.2 独立运行 37 RED mutation + 5 GREEN control

| 类别 | 数量 | 结果 |
|------|------|------|
| RED mutations (tamper) | 34 | 34 RED as intended |
| RED mode proof (N14) | 1 | RED as intended (exit 3, RELEASE_GATE=BLOCKED) |
| RED validator-scope (N20/N21) | 2 | **PATCH ANCHOR ERROR** (defect，见下) |
| GREEN controls | 5 | 5 GREEN as intended |
| Tree integrity | 1 | OK (byte-identical before/after) |

**总计运行：** 35 RED + 2 PATCH ANCHOR ERROR + 5 GREEN + tree integrity OK

### 4.3 N20/N21 缺陷详述

| 缺陷 | 描述 | 影响 |
|------|------|------|
| CRLF patch anchor mismatch | N20/N21 mutation patches 使用 `\n` 行 endings，但候选 validator 文件在 Windows 工作树中有 `\r\n` (core.autocrlf=true)。`text.count(old)` 返回 0，导致 "patch anchor not unique in validator" 错误。 | N20/N21 无法在 Windows 上验证。候选 validator 本身功能正常（structural exit 0），但 mutation gate 的 validator-scope 验证在 Windows 上失效。 |

**根因分析：**
- `run_red_mutations.py` line 590-599: `original = VALIDATOR.read_bytes(); text = original.decode("utf-8"); if text.count(old) != 1`
- `_N20_PATCH` 和 `_N21_PATCH` 的 `old` 字符串使用 `\n` line endings
- 候选 validator blob 在 git 中为 LF-only，但 Windows 工作树 checkout 为 CRLF
- `read_bytes()` 返回 CRLF 内容，`decode("utf-8")` 保留 `\r\n`，导致 `count(old)` 为 0

**恢复后字节一致性：** 由于 patch 无法应用，恢复后字节一致性未被 N20/N21 验证。其他 35 个 mutation + 5 controls + tree integrity check 全部通过。

## Phase 5 — Gate Matrix

| 门 | 命令 | 预期 | 实际 | 结果 |
|----|------|------|------|------|
| structural 94b0c300..HEAD | `python validator.py --root . --mode structural --base-sha 94b0c30034d04d1bad87f926a4b09e3dbbe3c6db` | exit 0 | exit 0 | PASS |
| structural 5a380586..HEAD | `python validator.py --root . --mode structural --base-sha 5a380586caab4f662d7e1dfbc7899cf5bd3bc300` | exit 0 | exit 0 | PASS |
| structural d7ea8027..HEAD | `python validator.py --root . --mode structural --base-sha d7ea8027bf7d4ba5ec0a8d2f92965e5061680f34` | exit 0 | exit 0 | PASS |
| release | `python validator.py --root . --mode release` | exit 3 | exit 3 (RELEASE_GATE=BLOCKED) | PASS |
| diff-check | `git diff --check` | clean | clean | PASS |
| pre-commit/detect-secrets | `detect-secrets scan ... --baseline .secrets.baseline` | clean | exit 0, 0 secrets | PASS |
| strict UTF-8/no-BOM/LF | 源码审查 + 脚本验证 | blobs LF-only | blobs LF-only，working tree CRLF 为 Windows core.autocrlf 预期行为 | PASS |
| GitNexus analyze | `npx gitnexus analyze .` | 成功 | 15,690 nodes / 47,360 edges / 816 clusters / 300 flows | PASS |

## Phase 6 — Evidence Truth

### 6.1 真实链验证

```
077774e7 (DC-12R1-MVP-L1-HE2-R3: structural delta chain + scanner prefix-bypass closure)
  → 8eb61d21 (docs: R3 delivery ledger final SHA and enforcement status)
    → d7ea8027 (docs: R3 FINAL_REPORT_TIP = 8eb61d21)
      → 68a68027 (DC-12R1-MVP-L1-HE2-R3-R1: scanner all-file scope + evidence truth closure)
```

**验证结果：** PASS — `git log --oneline 077774e..68a68027` 显示线性链，无分叉。

### 6.2 旧 tip/parent 声明已标记 SUPERSEDED_METADATA_ONLY

| 文件 | 状态 |
|------|------|
| `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r3_delta_chain_scanner_bypass_closure.md` | 顶部有 `SUPERSEDED_METADATA_ONLY` 横幅，声明 `FINAL_REPORT_TIP = 8eb61d21` 及 parent/tip 声明已 superseded |
| `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r3_r1_scanner_all_file_scope_evidence_truth.md` | 引用旧声明并标记 SUPERSEDED |

### 6.3 不要求 committed report 声称自身 SHA

- R3-R1 台账未包含 `FINAL_REPORT_TIP = 68a68027` 或类似自引用 SHA 声明
- 证据链记录为 `077774e7 -> 8eb61d21 -> d7ea8027`，候选为链的延续

### 6.4 Branch protection 状态

| 检查项 | 结果 |
|--------|------|
| GitHub API /branches/{branch}/protection | REMOTE_ENFORCEMENT_NOT_VERIFIED (401 Unauthorized，无 GITHUB_TOKEN) |
| 本地 rulesets 检查 | 不可用（需要远程 API） |
| 分类 | **REMOTE_ENFORCEMENT_NOT_VERIFIED** — 如实披露，未声称已验证 |

## Phase 7 — Deliverables

| 项目 | 状态 |
|------|------|
| 新 reports 分支 | `reports/dc12r1-mvp-l1-he2-r3-r1-v1-kilo-final-cumulative-governance-review-2026-08-25` |
| review.md | 本文件 |
| findings.csv | 配套发现清单 |
| local SHA == remote SHA | 推送后验证 |
| 候选/受保护 refs 未修改 | PASS — 只读审查 |

## 裁决

```
STOP_AND_REPORT_CTO
```

### 精确缺陷

| # | 缺陷 | 严重性 | 证据 |
|---|------|--------|------|
| D1 | N20/N21 mutation patches 在 Windows 工作树（CRLF）上无法应用，导致 validator-scope mutation gate 无法验证 | HIGH | `run_red_mutations.py` 的 patch strings 使用 `\n`，但文件 checkout 为 `\r\n`；`text.count(old)` 返回 0 |
| D2 | 2 个 validator-scope mutations (N20/N21) 未完成 RED->GREEN 验证周期 | HIGH | 由于 D1，N20/N21 停留在 PATCH ANCHOR ERROR 状态，无法确认修复点可达性和恢复后字节一致性 |

### 通过项摘要

| 维度 | 结果 |
|------|------|
| Proof Gate | PASS |
| Cumulative Source Review | PASS |
| Scanner Adversarial Review | PASS |
| Test Authenticity (89/89 unittest) | PASS |
| Test Authenticity (37 RED + 5 GREEN) | PARTIAL (35 RED + 2 ERROR + 5 GREEN) |
| Gate Matrix | PASS |
| Evidence Truth | PASS |

### 后续建议

1. **修复 N20/N21 mutation script**：在 `_run_validator_mutation` 中 normalize line endings（`text = original.decode("utf-8").replace('\r\n', '\n')`）或使用平台感知的换行符
2. **在 Linux/WSL 上重新运行 N20/N21**：确认 mutations 在 LF 环境下正常工作
3. **验证 branch protection**：在具备 GITHUB_TOKEN 权限的环境中重新检查
