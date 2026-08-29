# DC-12R1-MVP-L1-HE2-R1 Machine-Enforced Harness Governance Bypass Closure

## Verdict

`SOURCE_GATE_PASS_BUT_REMOTE_ENFORCEMENT_NOT_VERIFIED`

The local governance gate passes all structural, semantic, mutation, and
release-mode checks. The branch has been pushed to origin. Branch protection
on `product-dev-recovered` could not be verified (GitHub API returned 404;
either no protection rule exists or the querying identity lacks permission).
The required check name `HE2-R1 structural gate` is defined in the workflow
but has not been confirmed as a GitHub branch protection required check.

## Status

`READY_FOR_CTO_HE2_R1_GOVERNANCE_REVIEW`

## Objective

Close every bypass class identified in the HE2 governance gate so that
"product changes must synchronize test coverage, debt, and protocol" is
enforced by machine, not by detecting whether a file was touched.

## Frozen inputs

| Input | Value |
|---|---|
| HE1_BASE | `666af8a62f29d5e7b31dcf5d618336510b328420` |
| HE2_PARENT | `94b0c30034d04d1bad87f926a4b09e3dbbe3c6db` |
| HE2-R1 SHA | `b74e16879f92972d3c28ad163e38c2aa045f69f2` |
| Branch | `codex/dc12r1-mvp-l1-he2-r1-governance-bypass-closure-2026-08-25` |
| Remote | `https://github.com/lvoemingjie-hash/Mpango-ERP.git` |
| HE2 branch | `codex/dc12r1-mvp-l1-he2-machine-enforced-harness-governance-2026-08-25` (unchanged at 94b0c300) |
| Protected refs | `origin/product-dev-recovered` = `6e9470a1`, `origin/main` = `134ea59e` — verified unchanged before and after worktree creation |

## Directive traceability

| # | Requirement | Delivered |
|---|---|---|
| 1–5 | Phase 1: proof gate | ✓ fetch, worktree, ancestry verified, protected refs unchanged, baseline 31/14/2 recorded, impact enumerated (all callers in harness-governance/** + CI workflow, no product code, LOW risk) |
| 6–10 | Phase 2: governance self-protection | ✓ hardcoded PROTECTED_PATHS (workflow, config, validator/, schemas/, tests/), MINIMUM_GOVERNED_PREFIXES (backend/, frontend/src/, scenarios/), new governed-paths.schema.json, CONFIG-PREFIXES-EMPTY/DUP/MINIMUM-PREFIX rules, non-waivable protected paths |
| 11–15 | Phase 3: semantic sync | ✓ record-level diff (semantic_view strips notes), per-path coverage via changed node anchors / interaction source+affected paths / debt affected_paths / eligible new deltas, uncovered paths named, notes-only stays RED |
| 16–21 | Phase 4: waiver fail-closed | ✓ paths required/unique/minItems/no wildcards/no repo root, owner+reason+risk(P0-P3)+approval_ref+opened_on+expires_on, per-path union coverage, WVR-EXPIRED always RED, WVR-PATH-PROTECTED for governance core, WVR-UNUSED/WVR-OVERLAP warnings |
| 22–25 | Phase 5: PASS evidence | ✓ 40-hex: existing commit, reachable from branch/tag, evidence_paths at commit; 64-hex: evidence_commit binding + blob-byte SHA-256; all-zero/nonexistent/unreachable/wrong-path/wrong-digest RED; fail-closed outside git; seed 0 PASS |
| 26–31 | Phase 6: delta anti-replay | ✓ base_sha bound to comparison base (None → fail-closed), historical deltas single-use (DELTA-REPLAY), kind-precise authorization, DELTA-BASE-MISMATCH, DELTA-AFFECTED-IDS-EMPTY, STATUS-UNAUTHORIZED for unauthorized transitions (PASS/FAIL leaving, NOT_APPLICABLE in/out, CLOSED reopening) |
| 32–34 | Phase 7: schema fail-closed | ✓ SCHEMA-UNKNOWN-KEYWORD, SCHEMA-BAD-REF, uniqueItems, ANCHOR-MISSING/ANCHOR-LINE-INVALID RED with line-range validation |
| 35–38 | Phase 8: structural vs release | ✓ --mode structural (PR gate, exit 0/1) and --mode release (exit 3 on open P0/P1 release-blocking debt), STRUCTURAL_GATE + RELEASE_GATE in report + markdown, fixed CI check name |
| 39–42 | Phase 9: adversarial tests | ✓ 66 unit tests (original 31 kept/strengthened), 30 RED mutations (14 original + 16 new: config empty/minimum, notes-only, partial path, waiver missing/partial, evidence zero/nonexistent/unreachable/path-missing/blob-mismatch, historical replay, unauthorized relabel, unknown keyword, bad ref, release-blocker mode proof), 5 GREEN controls (pristine, scoped waiver, semantic mapping, multi-waiver union, valid committed evidence), candidate-tree integrity snapshot |
| 43–47 | Phase 10: CI + enforcement | ✓ workflow: PR/push → structural gate (fixed name `HE2-R1 structural gate`), workflow_dispatch → release gate; fetch-depth: 0; local simulation: HE1 bootstrap GREEN, R1-vs-HE2 GREEN, unmapped product change RED, release mode BLOCKED; branch pushed, remote SHA verified; branch protection 404 → SOURCE_GATE_PASS_BUT_REMOTE_ENFORCEMENT_NOT_VERIFIED |
| 48–55 | Phase 11: scope + quality + delivery | ✓ allowed scope only (workflow, harness-governance/**, decision record, .secrets.baseline — disclosed deviation for pre-commit false-positive fix); py_compile OK, UTF-8/no-BOM OK, whitespace OK, stdlib-only imports verified, pre-commit all hooks passed, commit b74e1687, push verified, ledger + verdict |

## Test reconciliation

| Gate | Count | Status |
|---|---|---|
| Unit tests | 66 | GREEN |
| RED mutations | 30 (29 tamper + 1 mode proof) | all RED with intended codes |
| GREEN controls | 5 | all GREEN |
| Candidate-tree integrity | 1 | OK (byte-identical before/after) |
| Historical baseline (HE2 checkpoint) | 31 tests, 14 RED, 2 GREEN | recorded, not modified |

## Scope deviation disclosure

`.secrets.baseline` was modified to allowlist `base_sha|evidence_sha|evidence_commit`
lines in the `should_exclude_line` filter. These lines contain schema-constrained
40/64-hex git object hashes that are not real secrets; every future governance delta
and PASS evidence node would otherwise trip the same false positive. The modification
was required by Phase 11.51 (pre-commit must pass). No other files outside the
allowed scope were changed.

## External enforcement status

- **Branch pushed:** ✓ `b74e1687` on `origin/codex/dc12r1-mvp-l1-he2-r1-governance-bypass-closure-2026-08-25`
- **Remote SHA verified:** ✓ local == remote
- **Branch protection on product-dev-recovered:** NOT VERIFIED (GitHub API 404; no protection rule found or insufficient permission)
- **Required check name:** `HE2-R1 structural gate` (defined in workflow, not confirmed as GitHub required check)

## Change set

1. `harness-governance/validator/harness_governance_validator.py` — validator 2.0.0 (all R1 rules)
2. `harness-governance/schemas/governed-paths.schema.json` — new config schema
3. `harness-governance/schemas/waivers.schema.json` — fail-closed waiver schema
4. `harness-governance/schemas/protocol-deltas.schema.json` — anti-replay delta schema
5. `harness-governance/schemas/inventory.schema.json` — evidence binding fields
6. `harness-governance/schemas/coverage-debt.schema.json` — affected_paths field
7. `harness-governance/schemas/critical-interactions.schema.json` — affected_paths field
8. `harness-governance/governed-paths.json` — config v1.1.0 (inventory_sync_paths removed)
9. `harness-governance/inventory/protocol-deltas.json` — R1 governance delta
10. `harness-governance/tests/test_harness_governance_validator.py` — 66 unit tests
11. `harness-governance/tests/run_red_mutations.py` — 30 RED + 5 GREEN + integrity
12. `harness-governance/README.md` — R1 documentation
13. `.github/workflows/harness-governance-gate.yml` — dual-gate CI
14. `decision-register/2026-08-25_harness-governance-tooling-he2.md` — R1 addendum
15. `.secrets.baseline` — allowlist for schema-constrained hex hashes (disclosed deviation)
16. `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_he2_r1_machine_enforced_harness_governance.md` — this ledger

## Out of scope (explicit)

- HE3 risk-first business inventory backfill — separately authorized.
- Any backend, frontend, migration, deployment, dependency, or product
  behavior change.
- GitHub branch protection configuration — requires repo admin action.
- H2-B-R3-R1 — only after Kilo reviews HE2_PARENT..HE2-R1.

## Next gate

Kilo performs a bounded source/bypass review of
HE2_PARENT (94b0c300)..HE2-R1 (b74e1687). Only after that review passes,
DC-12R1-MVP-L1-J1-H2-B-R3-R1 may proceed.
