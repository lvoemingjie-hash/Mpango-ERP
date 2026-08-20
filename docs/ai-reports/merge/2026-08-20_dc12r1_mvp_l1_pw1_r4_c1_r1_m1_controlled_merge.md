# DC-12R1-MVP-L1-PW1-R4-C1-R1-M1 — Controlled No-FF Merge Evidence

**Date**: 2026-08-20
**Operator**: ZCode (task DC-12R1-MVP-L1-PW1-R4-C1-R1-M1)
**Verdict**: `PASS_DC12R1_MVP_L1_PW1_R4_C1_R1_CONTROLLED_MERGE`

## Authorization

CTO authorized this exact candidate to merge into the protected product target
`product-dev-recovered`. No other protected branch was authorized. Authorization
chain (frozen inputs):

| Role | Artifact | SHA |
|---|---|---|
| Kilo source approval | `reports/dc12r1-mvp-l1-pw1-r4-c1-r1-v1-kilo-review-2026-08-20` | `5cff172a80f530c39036c61325dfa9090428d612` |
| Browser evidence | `reports/dc12r1-mvp-l1-pw1-r4-c1-r1-v2-opencode-browser-final-2026-08-20` | `0e1c7ed846f671e50314a3434c695fbb0e8d8d0d` |
| Kilo evidence approval | `reports/dc12r1-mvp-l1-pw1-r4-c1-r1-v2-v1-kilo-evidence-review-2026-08-20` | `b0b1ff4fbe82f378ccff15db138f9d7f19cfea07` |
| Frozen harness | `reports/dc12r1-mvp-l1-pw1-r4-b3-opencode-2026-08-16` | `db84b1325c51a484af55029ce3485d9995b0669a` |

## Merge SHAs and parents

| Item | Value |
|---|---|
| Target (before) | `9067e38f83edb38fcdb53fb5d5eea7e75e85cf5f` (`origin/product-dev-recovered`) |
| Source | `f51c10943b5d1a67569d681e66a6d56e728860b4` (`zcode/dc12r1-mvp-l1-pw1-r4-c1-r1-browser-integration-closure-2026-08-20`) |
| Source parent | `df7c8f15435e6821a4f18fbb476b091761933f8d` (verified) |
| Merge commit | `a29f8db02365737c64d0d8d442e8ef48a8a19d6d` (`MERGE_SHA`) |
| Merge parent 1 | `9067e38f83edb38fcdb53fb5d5eea7e75e85cf5f` (target) |
| Merge parent 2 | `f51c10943b5d1a67569d681e66a6d56e728860b4` (source) |

Merge executed as `git merge --no-ff --no-edit f51c109...` in a clean isolated
worktree at the exact target SHA, on a temporary integration branch
(`tmp/dc12r1-m1-integration-20260820`). Strategy `ort`; zero conflicts; no
manual conflict-resolution edits; no squash, rebase, cherry-pick, force-push, or
history rewrite.

## Exact five-file scope (`9067e38f..MERGE_SHA`)

| Status | File |
|---|---|
| M | `frontend/src/components/layout/MainLayout.tsx` |
| M | `frontend/src/components/layout/Header.tsx` |
| M | `frontend/src/components/layout/Sidebar.tsx` |
| A | `frontend/src/tests/Pw1R4C1MainLayoutResponsive.test.tsx` |
| A | `ai-ledger/product-ai/2026-08-17_dc12r1_mvp_l1_pw1_r4_c1_responsive_main_layout.md` |

No dependency, lockfile, backend, router, auth, permission, or deployment file
appears in the cumulative delta or in any intermediate commit
(`ddfa6e7f`, `4d37a0fb`, `df7c8f15`, `f51c109`).

## Merge-tree equality proof

- `git diff --exit-code MERGE_SHA f51c109` → exit 0 (byte-identical trees).
- `git ls-tree -r MERGE_SHA` == `git ls-tree -r f51c109` (verified identical).
- Therefore the pushed tree is byte-identical to the accepted candidate
  `f51c109`, and the authoritative browser `162/162` result carries over
  without rerunning.

## Post-merge gates (run in `frontend/`, committed lockfiles)

| Command | Result |
|---|---|
| `pnpm install --frozen-lockfile` | exit 0 |
| `pnpm vitest run src/tests/Pw1R4C1MainLayoutResponsive.test.tsx` | **11/11 passed** |
| Same + `--sequence.shuffle --sequence.seed=20260820` | **11/11 passed** |
| `pnpm vitest run src/tests/Header.test.tsx src/tests/PrintableWorkspace.test.tsx src/tests/Pw1R2AuthSessionClosure.test.tsx` | **111/111 passed** |
| `pnpm vitest run` (full) | **23 files / 339 passed / 0 failed** |
| `pnpm build` | exit 0 |

## Quality gates

| Gate | Result |
|---|---|
| `git diff --check 9067e38f..MERGE_SHA` | clean (exit 0) |
| Scoped `pre-commit run --files <five files>` | all Passed (trailing-whitespace, end-of-file, large-files, detect-secrets) |
| Scoped `detect-secrets` (baseline `.secrets.baseline`) | Passed |
| Strict UTF-8 / no BOM / mojibake scan (five files) | clean |
| `npx gitnexus analyze` | success — 15,253 nodes / 45,702 edges / 815 clusters |
| `npx gitnexus status` | up-to-date at `a29f8db` |

## Protected refs before/after

| Ref | Before | After |
|---|---|---|
| `origin/product-dev-recovered` | `9067e38f` | `a29f8db0` (fast-forward, no force) |
| `origin/zcode/...-browser-integration-closure-2026-08-20` | `f51c109` | `f51c109` (untouched) |
| `origin/main` | `134ea59e` | `134ea59e` (untouched) |
| Harness + 3 approval/evidence report refs | `db84b132` / `5cff172a` / `0e1c7ed8` / `b0b1ff4f` | unchanged (verified via `git ls-remote` post-push) |

## Local/remote equality

- `git push origin MERGE_SHA:refs/heads/product-dev-recovered` → accepted as
  fast-forward `9067e38f..a29f8db0`, exit 0.
- Post-push `git ls-remote`: remote `product-dev-recovered` =
  `a29f8db02365737c64d0d8d442e8ef48a8a19d6d` = local `MERGE_SHA`.

## Cleanup

Task-owned worktrees
(`.../zcode_dc12r1_m1_merge_20260820`, `.../zcode_dc12r1_m1_report_20260820`)
and the temporary integration branch
(`tmp/dc12r1-m1-integration-20260820`) were removed after evidence capture.
Source and report branches were not deleted.

## Accepted non-blocking observations

1. **Desktop focus-order change**: the responsive rework changed the desktop
   tab focus order (visible-first-landmark DOM order); accepted with the
   candidate.
2. **Duplicate desktop Logout controls**: two Logout controls exist in the
   desktop layout; accepted with the candidate.
3. **`aria-modal` with external hamburger**: the mobile drawer uses
   `aria-modal` while the hamburger trigger lives outside the dialog element;
   accepted with the candidate.

## Post-publication

STOP after publication. Deployment and the real-business-journey audit wait for
CTO confirmation of the merged SHA and current-truth documentation
synchronization.
