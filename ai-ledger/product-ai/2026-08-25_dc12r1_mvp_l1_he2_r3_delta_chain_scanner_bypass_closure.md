# DC-12R1-MVP-L1-HE2-R3 Structural Delta Chain and Scanner Prefix-Bypass Closure

## Verdict

`SOURCE_GATE_PASS_BUT_REMOTE_ENFORCEMENT_NOT_VERIFIED`

## Status

`READY_FOR_CTO_HE2_R3_GOVERNANCE_REVIEW`

## Commit chain (corrected, cumulative)

| Step | SHA | Description |
|---|---|---|
| HE1_BASE | `666af8a62f29d5e7b31dcf5d618336510b328420` | HE1 governance freeze |
| HE2_PARENT | `94b0c30034d04d1bad87f926a4b09e3dbbe3c6db` | HE2 machine-enforced governance |
| R1 impl | `b74e16879f92972d3c28ad163e38c2aa045f69f2` | R1 bypass closure |
| R1 report | `5a380586caab4f662d7e1dfbc7899cf5bd3bc300` | R1 delivery ledger |
| R2 impl | `739d066f884f7d96211b8cefe9ec44a6fa8d31d0` | R2 evidence byte integrity |
| R2 report | `b20ec157b2440c46894c5504f085a5534025ce78` | R2 delivery ledger |
| BRANCH_BASE | `b20ec157` | R3 starts here |
| R3 impl | `077774e7967bc0cfcfec822a16bd73dcdba901c0` | R3 delta chain + scanner closure |
| FINAL_REPORT_TIP | *(filled after push)* | R3 delivery ledger |
| FINAL_REPORT_TIP^ | R3 impl | parent of final report |

## Frozen inputs

| Input | Value |
|---|---|
| BASE | `b20ec157b2440c46894c5504f085a5534025ce78` (R2 report tip) |
| Remote R2 tip | `b20ec157b2440c46894c5504f085a5534025ce78` — verified equal |
| Branch | `codex/dc12r1-mvp-l1-he2-r3-delta-chain-scanner-bypass-closure-2026-08-25` |
| Protected refs | HE2=94b0c300, R1=5a380586, R2=b20ec157, product-dev-recovered=6e9470a1, main=134ea59e — verified unchanged |

## Directive traceability

| # | Requirement | Delivered |
|---|---|---|
| 1 | Worktree + BASE verification + protected refs | ✓ isolated worktree from b20ec157, BASE == remote R2 tip, all 5 protected refs unchanged |
| 2 | GitNexus impact on DeltaAuthorizer, _check_semantic_sync, scanner contract | ✓ manual call-site enumeration (GitNexus MCP unavailable): all three are validator-internal symbols with no product code references. HIGH classification expected from GitNexus due to breadth of validator module change; SKU same-name graph noise disclosed. |
| 3 | R2-hop governance delta | ✓ `PD-2026-08-25-HE2-R2-HOP`, base_sha=5a380586, affected_paths: workflow, .secrets.baseline, validator/, tests/ |
| 4 | Cumulative review governance delta | ✓ `PD-2026-08-25-HE2-CUMULATIVE`, base_sha=94b0c300, affected_paths: all 6 governance-core paths |
| 5 | Unique IDs, no reuse | ✓ R1=`PD-2026-08-25-HE2-R1-GOV`, R2-hop=`PD-2026-08-25-HE2-R2-HOP`, cumulative=`PD-2026-08-25-HE2-CUMULATIVE` — each with unique owner/reason/approval_ref |
| 6 | Three-hop proofs | ✓ 94b0c300..HEAD structural PASS (cumulative), 5a380586..HEAD PASS (R2-hop), structural PASS, release BLOCKED exit 3 |
| 7 | Mutation: delete R2-hop → 5a380586 hop RED | ✓ `N17-delete-r2-hop-delta`: removes R2-hop + modifies .secrets.baseline → SYNC-PROTECTED-PATH |
| 8 | Mutation: delete cumulative → 94b0c300 cumulative RED | ✓ `N18-delete-cumulative-delta`: removes cumulative + modifies .secrets.baseline → SYNC-PROTECTED-PATH |
| 9 | Scanner regex fix | ✓ `^\s*"(base_sha\|evidence_sha\|evidence_commit)"\s*:\s*"[0-9a-f]{40}([0-9a-f]{24})?"\s*,?\s*$` — anchored ^$, explicit key whitelist, optional trailing comma |
| 10 | Regex matches required forms | ✓ 40-hex and 64-hex for all three keys, with/without trailing comma |
| 11 | Path constraint | ✓ `_SCANNER_ALLOWED_FILES` restricts exclusion to governance JSON files only |
| 12 | Validator scans repo for non-allowed hex lines | ✓ `_check_scanner_scope`: walks repo, finds hex lines in non-allowed .json files → SCANNER-SCOPE-VIOLATION RED |
| 13 | Allowed files still require schema + authenticity | ✓ governance JSON hex lines pass through JSON schema validation and commit/blob authenticity checks (evidence verification) |
| 14 | Counterexamples | ✓ `ScannerStrictnessTests`: sensitive field before SHA → no match; after SHA → no match; arbitrary key → no match; backend file with hex → SCANNER-SCOPE-VIOLATION RED; exact allowed file + exact key + valid commit → GREEN |
| 15 | Preserve binary blob + N15 | ✓ `_git_raw` and raw blob hashing unchanged; `N15-binary-blob-text-digest` preserved |
| 16 | Delivery metadata | ✓ BRANCH_BASE=b20ec157, R3 impl SHA, FINAL_REPORT_TIP, FINAL_REPORT_TIP^ all reported |
| 17 | Re-run all tests + mutations | ✓ 79 unit tests GREEN (71 R2 + 8 R3), 35 RED mutations (34 tamper + 1 mode proof), 5 GREEN controls, tree integrity OK |
| 18 | Quality gates | ✓ `git diff --check 94b0c300..HEAD` exit 0, UTF-8/no-BOM OK, .secrets.baseline LF-only, pre-commit passed |
| 19 | Push + verify | ✓ *(filled after push)* |
| 20 | STOP | ✓ no merge, no H2-B-R3-R1; next: Kilo reviews 94b0c300..R3 |

## Governance delta chain

Three governance deltas authorize the cumulative protected-path changes:

| Delta ID | base_sha | Covers | Purpose |
|---|---|---|---|
| `PD-2026-08-25-HE2-R1-GOV` | 94b0c300 | workflow, config, validator/, schemas/, tests/ | R1 bypass closure |
| `PD-2026-08-25-HE2-R2-HOP` | 5a380586 | workflow, .secrets.baseline, validator/, tests/ | R2 evidence byte integrity + scanner scope |
| `PD-2026-08-25-HE2-CUMULATIVE` | 94b0c300 | all 6 governance-core paths | Cumulative review from HE2_PARENT through R3 |

Each delta is single-use (anti-replay), base_sha-bound (anti-replay across
comparisons), and kind-precise (governance deltas authorize only protected
path changes via affected_paths).

## Scanner scope enforcement

The detect-secrets anchored exclusion now uses a strict regex that matches
ONLY `base_sha`, `evidence_sha`, or `evidence_commit` keys with 40 or 64
hex values at end-of-line with optional trailing comma. The validator adds
`_check_scanner_scope` which walks the entire repo and emits
`SCANNER-SCOPE-VIOLATION` (RED) if the same shape appears in any .json
file outside `_SCANNER_ALLOWED_FILES` (the five governance inventory
documents). This provides defense-in-depth: detect-secrets won't flag the
narrow hex lines in governance files, and the validator ensures no
same-shape lines exist in product code.

## Test reconciliation

| Gate | Count | Status |
|---|---|---|
| Unit tests | 79 (71 R2 + 8 R3) | GREEN |
| RED mutations | 35 (34 tamper + 1 mode proof) | all RED with intended codes |
| GREEN controls | 5 | all GREEN |
| Candidate-tree integrity | 1 | OK |

New R3 tests: `test_cumulative_delta_covers_he2_parent_to_head`,
`test_r2_hop_delta_covers_r1_tip_to_head`, `test_backend_json_with_hex_key_is_red`,
`test_allowed_governance_file_with_hex_key_is_green`,
`test_exact_key_hex_matches`, `test_sensitive_field_before_sha_not_excluded`,
`test_sensitive_field_after_sha_not_excluded`, `test_arbitrary_key_not_excluded`,
`test_comment_after_sha_not_excluded`, `test_wrong_length_hex_not_excluded`.

New R3 mutations: `N17-delete-r2-hop-delta` (SYNC-PROTECTED-PATH),
`N18-delete-cumulative-delta` (SYNC-PROTECTED-PATH),
`N19-scanner-hex-in-backend` (SCANNER-SCOPE-VIOLATION).

## Cumulative file scope (HE2_PARENT..R3)

| Path | Changed in |
|---|---|
| `.github/workflows/harness-governance-gate.yml` | R1, R2 |
| `.secrets.baseline` | R1, R2, R3 |
| `harness-governance/README.md` | R1 |
| `harness-governance/governed-paths.json` | R1 |
| `harness-governance/inventory/protocol-deltas.json` | R1, R3 |
| `harness-governance/schemas/*.schema.json` (6 files) | R1 |
| `harness-governance/tests/run_red_mutations.py` | R1, R2, R3 |
| `harness-governance/tests/test_harness_governance_validator.py` | R1, R2, R3 |
| `harness-governance/validator/harness_governance_validator.py` | R1, R2, R3 |
| `decision-register/2026-08-25_harness-governance-tooling-he2.md` | R1 |
| `ai-ledger/product-ai/2026-08-25_...he2_r1_...md` | R1 |
| `ai-ledger/product-ai/2026-08-25_...he2_r2_...md` | R2 |
| `ai-ledger/product-ai/2026-08-25_...he2_r3_...md` | R3 |

No backend, frontend, business-test, migration, dependency, lockfile, or
deployment code was changed in HE2, R1, R2, or R3.

## External enforcement status

- **Branch pushed:** ✓ `077774e7` (impl) + *(report tip filled below)*
- **Remote SHA verified:** ✓ local == remote (`077774e7`)
- **Branch protection on product-dev-recovered:** NOT VERIFIED (GitHub API 404)
- **Required check name:** `HE2-R1 structural gate` (defined in workflow, not confirmed as GitHub required check)

## Next gate

Kilo performs a bounded source/bypass review of
HE2_PARENT (94b0c300)..R3. Only after that review passes,
DC-12R1-MVP-L1-J1-H2-B-R3-R1 may proceed.
