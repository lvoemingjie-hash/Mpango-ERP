# DC-12R1-MVP-L1-HE2-ET1-M0 — Current-Baseline Controlled Merge Readiness Rehearsal

- Date: 2026-08-28 (+08:00); Executor: Zcode
- Task: DC-12R1-MVP-L1-HE2-ET1-M0
- Verification tier: V3_MERGE_READINESS_REHEARSAL
- Claim ceiling: LOCAL_MERGE_REHEARSAL_PASS_ONLY
- Final adjudication: PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_M0_LOCAL_MERGE_READINESS_REHEARSAL
- Machine-readable companion: `findings.csv` (same branch)

## 1. Inputs (all verified against live remote tips after `git fetch --all --prune`)

| Ref | SHA | Live remote ref (exact tip match) |
|---|---|---|
| TARGET | `2c20d58c88a0a8f5175f4d11041d03b6ca785e06` | `refs/heads/product-dev-recovered` |
| SOURCE | `2582750dedfb591e801703ff57bea69fbe91c605` | `refs/heads/zcode/dc12r1-mvp-l1-he2-et1-r1-e1-provenance-review-independence-2026-08-28` |
| KILO_FINAL | `180c9346feb28e5daaa6e47d5aab30b35c1b6360` | `refs/heads/reports/dc12r1-mvp-l1-he2-et1-r1-e1-v1-kilo-final-cumulative-review-2026-08-28` |
| CODEXL_E2E_FINAL | `ec823cc210ce498837d3b3f3b284db998698c62f` | `refs/heads/reports/dc12r1-mvp-l1-he2-et1-r1-e1-v2-codexl-lubuntu-independent-e2e-final-2026-08-28` |

## 2. Proof Gate

- `git merge-base TARGET SOURCE` = `6e9470a1daa5d6eece29724316fdd8aef6b737c1`
  == EXPECTED_MERGE_BASE (exact match).
- merge-base..TARGET: **57 files** (expected ~57).
- merge-base..SOURCE: **46 files** (expected ~46).
- Path intersection of the two sides: **0** — gate passed, no STOP.

## 3. Local merge rehearsal (never pushed)

- Isolated worktree created from the EXACT TARGET commit with temporary local
  branch `integration/he2-et1-m0-rehearsal-2026-08-28`.
- Command: `git merge --no-ff --no-edit 2582750d…` → **exit 0**.
- Rehearsal merge commit: `b0ecd282313061928c831cd6c3d5ac02e3126a7f`
  - Parent 1 (TARGET): `2c20d58c88a0a8f5175f4d11041d03b6ca785e06`
  - Parent 2 (SOURCE): `2582750dedfb591e801703ff57bea69fbe91c605`
  - Tree: `cdf110ad72cf39040c29e085b713042c66dd1090`
- **Zero conflicts, zero manual modifications** (`git status` clean
  immediately after merge; no conflict markers anywhere).
- Structural proof of a clean merge:
  - `git diff --name-only TARGET rehearsal-merge` = exactly the 46
    SOURCE-side paths; 0 of the 57 TARGET-side paths changed.
  - `git diff TARGET rehearsal-merge -- backend/ frontend/src/ scenarios/`
    = 0 paths; deletions vs TARGET = 0 → no TARGET product file was deleted
    or overwritten.
  - All 46 SOURCE-side files are blob-identical (`git rev-parse
    SOURCE:path` == `rehearsal-merge:path`) in the merge tree.

## 4. Gates run ON the local rehearsal merge commit

| Gate | Result |
|---|---|
| Governance unittests | **116/116 OK** (`python -m unittest discover -s harness-governance/tests`) |
| Mutation gate | **66 RED / 9 GREEN PASS** — all 66 mutations intended-RED (48 tamper + 1 mode proof + 2 validator-scope + 15 authority-E2E), 9 controls GREEN |
| Candidate-tree integrity | OK — tree digest identical before/after the mutation gate |
| Structural validator | **exit 0 — STRUCTURAL_GATE PASS** |
| Release validator | **exit 3 — RELEASE_GATE BLOCKED**, attributed ONLY to pre-existing P0/P1 debt `DEBT-AUTH-CRITICAL-TUPLES`, `DEBT-COMMERCE-CRITICAL-TUPLES` (+1 real-device debt), unchanged by this merge |
| `git diff --check` | clean (no whitespace/conflict markers) |
| detect-secrets (vs `.secrets.baseline`) | **no new findings**; baseline file byte-restored after the tool run (snapshot-verified) |
| Strict encoding scan over all 103 touched paths | **clean** — UTF-8 decodable, no BOM, no NUL, no U+FFFD, no raw cp1252 0x97 (every 0x97 occurrence is a valid UTF-8 continuation byte; a bare one cannot survive UTF-8 decode) |
| JSON parse | 17/17 config + schema + inventory JSON files parse |
| YAML parse | 3/6 `.github/workflows/*.yml` parse strictly; `s1-2-ci-gate.yml`, `s2-7-ci-gates.yml`, `s5-ci-gate.yml` fail **strict** pyyaml — **pre-existing at the merge-base**: these files are absent from BOTH diff sides and blob-identical between TARGET and SOURCE, so the merge neither introduced nor worsened them |
| E2E authority core chain (8 cases) | **8/8 PASS on the merge tree itself** — GREEN case: rc=0, FINISHED, sentinel_calls=1, collect_child_spawns=1, nonce_match; RED cases (superuser, empty URL, capability flag, missing command, nonce tamper, node drift, profile drift): all VOID with sentinel=0. Executed against a FRESH throwaway PG (`he2et1_m0_pg16`, postgres:16-alpine on 127.0.0.1:15446, role `m0_gate` rolsuper=f/rolcreatedb=t, instance superuser `m0_admin` for the superuser RED case); the container AND its volumes were removed after the run and port 15446 verified CLOSED |

- **No product full-suite was run; Playwright was not run** (per task
  prohibition). The 8-case E2E harness is stdlib+pytest governance tooling
  and touches no product runtime.
- Cross-reference: Codex-L independent E2E final (`ec823cc2`, branch
  `reports/…codexl-lubuntu-independent-e2e-final-2026-08-28`) corroborates
  the 8/8 result — note its proof was executed on **SOURCE bytes**, not on
  this merge tree; the merge-tree runtime proof is the fresh-PG run above.

## 5. Limits and honest non-claims

- **REMOTE_ENFORCEMENT_NOT_VERIFIED**: nothing in this rehearsal proves any
  remote/GitHub-side enforcement (branch protection, required checks, or
  merge behavior on the server).
- **The rehearsal merge commit `b0ecd282…` was NOT pushed** and does not
  exist on any remote; cleanup below removed its branch and worktree.
- Release validator remains **exit 3 (BLOCKED)** on the merge tree for the
  pre-existing P0/P1 debt; this rehearsal does not clear or downgrade it.
- This report is a LOCAL merge readiness rehearsal only. It is **not** a
  merge approval and does not authorize any push of `product-dev-recovered`
  or of any merge commit.

## 6. Cleanup (post-rehearsal)

- Rehearsal worktree `../he2et1_m0_rehearsal` and local branch
  `integration/he2-et1-m0-rehearsal-2026-08-28` deleted.
- `git ls-remote origin | grep integration/he2-et1-m0` → empty (no merge
  commit remote ref exists).
- TARGET / SOURCE / protected refs re-verified unchanged after cleanup
  (see findings.csv `cleanup-*` rows).
- This report branch was created directly FROM SOURCE (`2582750d…`) and
  pushed; local == remote verified.

## 7. Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_M0_LOCAL_MERGE_READINESS_REHEARSAL**

STOP — awaiting CTO review.
