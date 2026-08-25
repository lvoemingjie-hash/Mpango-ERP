# DC-12R1-MVP-L1-HE2-R3-R2-V1 — Kilo Bounded EOL Portability Closure Review

- 日期：2026-08-25（+08:00）；审查者：Kilo
- 模式：源码真实性审查（冻结状态，只读审查 + 独立测试运行，不合并、不部署、不启动 H2-B-R3-R1）
- 审查对象：`246eb190fc07866f098a380e61ebdc5bd9428a04`
- 父提交：`68a68027e6b2d57ab35a77142b187c6301762de5`（HE2-R3-R1 BASE）
- 分支：`codex/dc12r1-mvp-l1-he2-r3-r2-mutation-eol-portability-closure-2026-08-25`

## 执行边界声明

- **未运行 Playwright**（无浏览器旅程、无运行时 JSON/JUnit）
- **未启动产品运行时**（无 backend、无前端 dev server、无 PG/Redis）
- **未合并、未部署、未启动 H2-B-R3-R1**
- 独立运行了 unittest 和 mutation gates（见 Phase 4）

## 冻结输入

| 项目 | 值 |
|------|-----|
| 候选 | `246eb190fc07866f098a380e61ebdc5bd9428a04` |
| BASE | `68a68027e6b2d57ab35a77142b187c6301762de5` |
| 累计 base | `94b0c30034d04d1bad87f926a4b09e3dbbe3c6db` |
| 中间 base | `5a380586caab4f662d7e1dfbc7899cf5bd3bc300` |
| 分支 | `codex/dc12r1-mvp-l1-he2-r3-r2-mutation-eol-portability-closure-2026-08-25` |
| 已接受先例 STOP | `635128180d7207deb893874df771a9889e345807` |

## Phase 1 — Proof Gate

| 步骤 | 结果 | 证据 |
|------|------|------|
| `git fetch --all --prune` | 通过 | 远程分支存在 |
| 候选 == remote tip | 通过 | `246eb190` == `origin/codex/...` |
| `candidate^` == BASE | 通过 | `git rev-parse HEAD~1` = `68a68027` |
| R3-R2 delta 恰好 4 文件 | 通过 | `git diff --name-status 68a68027..HEAD` = 4 文件 |
| 累计 delta 统计 | 通过 | `git diff --stat 68a68027..HEAD` = 4 files / +245 / -7 |
| product/runtime/schema/workflow/.secrets.baseline 无漂移 | 通过 | `git diff --name-only` 确认无此类路径 |

### R3-R2 Delta 文件清单（4 文件）

1. `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r3_r2_mutation_eol_portability.md` — **新增**：R3-R2 台账
2. `harness-governance/inventory/protocol-deltas.json` — 更新（新增 PD-2026-08-25-HE2-R3-R2-MUTATION-EOL-PORTABILITY delta）
3. `harness-governance/tests/run_red_mutations.py` — 更新（新增 `_detect_native_eol`、`_to_native_eol`、`_apply_validator_patch`；修改 `_run_validator_mutation`）
4. `harness-governance/tests/test_harness_governance_validator.py` — 更新（新增 `MutationEolPortabilityTests` 7 个直接真相测试）

## Phase 2 — Cumulative Source Review (EOL Portability)

### 2.1 _detect_native_eol / _to_native_eol / _apply_validator_patch / _run_validator_mutation 审查

| 检查项 | 结果 | 证据 |
|--------|------|------|
| LF/CRLF 均唯一命中 | PASS | `_detect_native_eol` 返回 `"\n"` 或 `"\r\n"`；`_to_native_eol` 将 canonical patch 转换为 native EOL；`_apply_validator_patch` 在 native EOL 上执行 `text.count(old)` |
| mixed EOL fail closed | PASS | `_detect_native_eol` 返回 `None` 时，`_apply_validator_patch` 返回 `(None, "MIXED_EOL")`，文件不被修改 |
| 0 锚点 fail closed | PASS | `text.count(old) != 1` 返回 `(None, "PATCH-ANCHOR-NOT-UNIQUE")`，文件不被修改 |
| 重复锚点 fail closed | PASS | 同上，`count > 1` 也返回 `PATCH-ANCHOR-NOT-UNIQUE` |
| fail-closed 不得计作 RED | PASS | `_run_validator_mutation` line 637-642: `fail_category is not None` 时 `return`，不进入 RED 判定逻辑 |
| finally 无条件恢复原始 bytes | PASS | `finally: VALIDATOR.write_bytes(original)` |
| 恢复后完整 bytes + SHA-256 双相等 | PASS | line 662-668: `restored == original` AND `sha256(restored) == sha256(original)` |
| 候选 validator blob 未全局归一化 | PASS | 仅 patch strings 在应用时转换；validator 文件本身 checkout 保持 native EOL |

### 2.2 关键代码路径

```python
def _detect_native_eol(data):
    lf = data.count(b"\n")
    cr = data.count(b"\r")
    crlf = data.count(b"\r\n")
    if cr == 0 and lf > 0:
        return "\n"
    if cr == crlf and lf == crlf and cr > 0:
        return "\r\n"
    return None  # mixed EOL -> fail closed

def _to_native_eol(text, native_eol):
    if native_eol == "\n":
        return text
    return text.replace("\n", "\r\n")

def _apply_validator_patch(original, patch):
    native_eol = _detect_native_eol(original)
    if native_eol is None:
        return None, "MIXED_EOL"
    old, new = (_to_native_eol(part, native_eol) for part in patch)
    text = original.decode("utf-8")
    if text.count(old) != 1:
        return None, "PATCH-ANCHOR-NOT-UNIQUE"
    return text.replace(old, new).encode("utf-8"), None

def _run_validator_mutation(name, patch, failures):
    original = VALIDATOR.read_bytes()
    mutated, fail_category = _apply_validator_patch(original, patch)
    if fail_category is not None:
        failures.append(f"{name}: {fail_category}")
        print(f"  {name:<40} FAIL CLOSED ({fail_category})")
        return
    try:
        VALIDATOR.write_bytes(mutated)
        # ... RED proof ...
    finally:
        VALIDATOR.write_bytes(original)
    # Full bytes + SHA-256 dual equality
    restored = VALIDATOR.read_bytes()
    if (hashlib.sha256(restored).digest() != hashlib.sha256(original).digest()
            or restored != original):
        failures.append(f"{name}: validator blob NOT byte-identical after restore")
```

## Phase 3 — Scanner Adversarial Review

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 独立验证 tracked/untracked .py/.ts/.md/.yml/.toml/无扩展名 | PASS | `_scanner_candidate_files` 使用 `git ls-files --cached --others --exclude-standard` + `os.walk` fallback |
| exact base_sha/evidence_sha/evidence_commit 40/64 hex 在五个允许文件外必须 RED | PASS | `_SCANNER_ALLOWED_FILES` frozenset；N19 测试通过 |
| 任意 key 不被排除 | PASS | `test_arbitrary_key_not_excluded` |
| 前后附加 secret 不被排除 | PASS | `test_prefix_and_suffix_attached_values_stay_green` |
| 错误长度不被排除 | PASS | `test_wrong_length_hex_not_excluded` |
| bytes 匹配，无 errors=replace | PASS | `_SCANNER_HEX_RE_BYTES` 使用 `rb'...'` 原始字节 |
| .secrets.baseline regex / 字符串 regex / bytes regex 语义一致性 | PASS | `_SCANNER_HEX_RE` (str) 和 `_SCANNER_HEX_RE_BYTES` (bytes) 模式相同；detect-secrets baseline 独立扫描 clean |

## Phase 4 — Test Authenticity

### 4.1 独立运行 96/96 unittest（CRLF checkout）

| 检查项 | 结果 |
|--------|------|
| unittest 数量 | 96 |
| 通过 | 96 |
| 失败 | 0 |
| 命令 | `PYTHONPATH=harness-governance/tests python -m unittest harness-governance.tests.test_harness_governance_validator -v` |
| 耗时 | ~28.3s |
| checkout | core.autocrlf=true，目标文件 CR>0 |

### 4.2 独立运行 37 RED + 5 GREEN（CRLF checkout）

| 类别 | 数量 | 结果 |
|------|------|------|
| RED mutations (tamper) | 34 | 34 RED as intended |
| RED mode proof (N14) | 1 | RED as intended (exit 3, RELEASE_GATE=BLOCKED) |
| RED validator-scope (N20/N21) | 2 | **RED as intended**（probes escaped）→ restored: blob identical, probes RED again |
| GREEN controls | 5 | 5 GREEN as intended |
| Tree integrity | 1 | OK (byte-identical before/after) |
| PATCH ANCHOR ERROR | 0 | **零 PATCH ANCHOR ERROR** |

**总计：** 37 RED + 5 GREEN + tree integrity OK + 零 PATCH ANCHOR ERROR

### 4.3 N20/N21 修复验证

| 检查项 | 结果 | 证据 |
|--------|------|------|
| N20/N21 真正修改候选 validator | PASS | `_apply_validator_patch` 在 LF/CRLF fixture 上均返回 `mutated != original` |
| 恢复后 blob 字节一致 | PASS | `_run_validator_mutation` line 662-668: `restored == original` AND `sha256` digests equal |
| RED→恢复 GREEN 完整周期 | PASS | N20/N21 均先 RED（probes escaped），恢复后 restored validator 再次 catching probes |

### 4.4 新增 7 个直接真相测试

| 测试 | 真实性证据 |
|------|-----------|
| `test_lf_validator_fixture_patches_hit_uniquely` | 直接调用 `_apply_validator_patch`，LF fixture，断言 `mutated.count(b"\r") == 0` |
| `test_crlf_validator_fixture_patches_hit_uniquely` | 直接调用 `_apply_validator_patch`，CRLF fixture，断言 `mutated.count(b"\r") == mutated.count(b"\r\n")` |
| `test_lf_and_crlf_mutations_are_semantically_equal` | 断言 `mutated_crlf.replace(b"\r\n", b"\n") == mutated_lf` |
| `test_write_and_restore_cycle_is_byte_exact` | 写临时文件、读回、断言 bytes 相等 + sha256 相等 |
| `test_mixed_eol_fails_closed_without_modifying_the_file` | mixed EOL blob → `MIXED_EOL`，断言真实 validator 文件未被修改 |
| `test_zero_anchor_fails_closed` | 无锚点 blob → `PATCH-ANCHOR-NOT-UNIQUE` |
| `test_duplicate_anchor_fails_closed` | 重复锚点 blob → `PATCH-ANCHOR-NOT-UNIQUE`，断言真实文件未被修改 |

**关键证据：** 无 `vi.mock` 或 `unittest.mock`；所有测试调用真实 `run_red_mutations` 模块中的真实 helper 函数。

## Phase 5 — Gate Matrix

| 门 | 命令 | 预期 | 实际 | 结果 |
|----|------|------|------|------|
| structural 94b0c300..HEAD | `python validator.py --mode structural --base-sha 94b0c300...` | exit 0 | exit 0 | PASS |
| structural 68a68027..HEAD | `python validator.py --mode structural --base-sha 68a68027...` | exit 0 | exit 0 | PASS |
| release | `python validator.py --mode release` | exit 3 | exit 3 (RELEASE_GATE=BLOCKED) | PASS |
| diff-check | `git diff --check` | clean | clean | PASS |
| pre-commit/detect-secrets | `detect-secrets scan ... --baseline .secrets.baseline` | clean | exit 0 | PASS |
| strict UTF-8/no-BOM/LF | 目标文件核验 | blobs UTF-8, no BOM, CRLF in CRLF checkout | 4/4 目标文件 UTF-8=True, BOM=False, CRLF=True | PASS |
| GitNexus analyze | `npx gitnexus analyze .` | 成功 | 15,703 nodes / 47,393 edges / 816 clusters / 300 flows | PASS |
| 同名 SKU 图噪声 | 披露 | 816 clusters 为正常知识图谱结构 | 非缺陷 | INFO |

### release exit 3 语义说明

```
RELEASE_BLOCKED: open P0/P1 release-blocking debt 'DEBT-AUTH-CRITICAL-TUPLES', 'DEBT-COMMERCE-CRITICAL-TUPLES'
```

这是正确的阻断语义：存在 2 个 P0 release-blocking 债务（`DEBT-AUTH-CRITICAL-TUPLES` 和 `DEBT-COMMERCE-CRITICAL-TUPLES`），结构门虽 GREEN，但 release gate 必须 BLOCKED，exit code 3。

## Phase 6 — Evidence Truth

### 6.1 真实链验证

```
68a68027 (HE2-R3-R1: scanner all-file scope + evidence truth closure)
  → 246eb19 (HE2-R3-R2: mutation EOL portability closure)
```

**验证结果：** PASS — `git log --oneline 68a68027..246eb19` 显示线性链，无分叉。

### 6.2 旧 tip/parent 声明已标记 SUPERSEDED_METADATA_ONLY

| 文件 | 状态 |
|------|------|
| `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r3_delta_chain_scanner_bypass_closure.md` | 顶部有 `SUPERSEDED_METADATA_ONLY` 横幅，声明 `FINAL_REPORT_TIP = 8eb61d21` 及 parent/tip 声明已 superseded |
| `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r3_r1_scanner_all_file_scope_evidence_truth.md` | 引用旧声明并标记 SUPERSEDED |

### 6.3 不要求 committed report 声称自身 SHA

- R3-R2 台账未包含 `FINAL_REPORT_TIP = 246eb19` 或类似自引用 SHA 声明
- 证据链记录为 `68a68027 → 246eb19`，候选为链的延续

### 6.4 Branch protection 状态

| 检查项 | 结果 |
|--------|------|
| GitHub API /branches/{branch}/protection | REMOTE_ENFORCEMENT_NOT_VERIFIED (无 GITHUB_TOKEN，无法验证) |
| 本地 rulesets 检查 | 不可用（需要远程 API） |
| 分类 | **REMOTE_ENFORCEMENT_NOT_VERIFIED** — 如实披露，未声称已验证 |

## Phase 7 — Dual-Checkout Gate Proof

### 7.1 autocrlf=false checkout (LF-only)

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 目标文件 CR 数量 | CR=0 | `harness_governance_validator.py`: CR=0, CRLF=0; `run_red_mutations.py`: CR=0, CRLF=0 |
| unittest | 96/96 OK | 在 LF-only worktree (`C:\Users\Jeff0\_review_dc12r1_he2_r3_r2_eol_portability_closure_2026-08-25`) 运行 |
| 37 RED + 5 GREEN | 全部通过 | 同上 |
| N20/N21 | RED → restored GREEN | 同上 |
| PATCH ANCHOR ERROR | 0 | 同上 |

### 7.2 autocrlf=true checkout (CRLF)

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 目标文件 CR 数量 | CR>0 | `harness_governance_validator.py`: CR=1874, CRLF=1874; `run_red_mutations.py`: CR=918, CRLF=918 |
| unittest | 96/96 OK | 在 CRLF worktree (`C:\Users\Jeff0\_review_dc12r1_he2_r3_r2_eol_crlf_2026-08-25`) 运行 |
| 37 RED + 5 GREEN | 全部通过 | 同上 |
| N20/N21 | RED → restored GREEN | 同上 |
| PATCH ANCHOR ERROR | 0 | 同上 |
| git status clean | clean | 验证通过 |

## Phase 8 — Deliverables

| 项目 | 状态 |
|------|------|
| 新 reports 分支 | `reports/dc12r1-mvp-l1-he2-r3-r2-v1-kilo-bounded-eol-portability-closure-review-2026-08-25` |
| review.md | 本文件 |
| findings.csv | 配套发现清单 |
| local SHA == remote SHA | 推送后验证 |
| 候选/受保护 refs 未修改 | PASS — 只读审查 |

## 裁决

```
PASS_FOR_CTO_DC12R1_MVP_L1_HE2_R3_R2_V1_KILO_BOUNDED_EOL_CLOSURE_REVIEW
```

### 核验摘要

| 维度 | 结果 |
|------|------|
| Proof Gate | PASS（候选 == remote tip，parent == BASE，delta 4 files / +245 / -7，产品路径零漂移） |
| Cumulative Source Review | PASS（EOL portability closure：LF/CRLF 唯一命中、mixed/0/重复锚点 fail-closed、finally 无条件恢复、bytes+SHA-256 双相等） |
| Scanner Adversarial Review | PASS |
| Test Authenticity (96/96 unittest) | PASS |
| Test Authenticity (37 RED + 5 GREEN) | PASS（37 RED + 5 GREEN + tree integrity OK + 零 PATCH ANCHOR ERROR） |
| N20/N21 修复验证 | PASS（真实 RED→恢复 GREEN，恢复后 blob 字节一致） |
| Dual-Checkout Gate | PASS（LF-only 和 CRLF 双 checkout 均通过） |
| Gate Matrix | PASS（structural 94b0c300/68a68027..HEAD exit 0；release exit 3；diff-check/detect-secrets/UTF-8/LF clean；GitNexus 15,703 nodes） |
| Evidence Truth | PASS（链 68a68027 → 246eb19 已验证；旧 FINAL_REPORT_TIP 声明标记 SUPERSEDED_METADATA_ONLY；branch protection = REMOTE_ENFORCEMENT_NOT_VERIFIED） |

### 关键修复说明

本候选修复了上一轮（HE2-R3-R1）的 D1/D2 缺陷：

| 旧缺陷 | 修复机制 |
|--------|----------|
| N20/N21 mutation patches 在 Windows CRLF 工作树无法应用 | `_detect_native_eol` 检测 checkout native EOL；`_to_native_eol` 将 canonical LF patch 转换为 native EOL |
| PATCH ANCHOR ERROR 在 Windows 上恒现 | patch 字符串在应用时转换为 native EOL，确保 `text.count(old)` 正确返回 1 |
| 恢复后字节一致性未被 N20/N21 验证 | 现在 N20/N21 完成完整 RED→恢复→GREEN 周期，恢复后通过 `bytes == original` AND `sha256 == sha256(original)` 双验证 |
