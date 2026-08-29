# DC-12R1-MVP-L1-HE2-ET1-R2-R2-R1-M1 — Final Controlled Merge Rehearsal

- Date: 2026-08-29 (+08:00); Executor: Zcode
- Task: DC-12R1-MVP-L1-HE2-ET1-R2-R2-R1-M1
- Verification tier: V3_MERGE_CRITICAL_GOVERNANCE
- Claim ceiling: LOCAL_MERGE_READINESS_REHEARSAL_ONLY
- Final adjudication: PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R2_R2_R1_M1_LOCAL_MERGE_READINESS_REHEARSAL
- Machine-readable companion: `findings.csv` (same branch)
- Supersedes: the M0 rehearsal report (58b8e2ac, already marked
  SUPERSEDED_BY_HE2_ET1_R2_REDIS_AUTHORITY_DEFECT) — M1 rehearses the
  FULL candidate chain through R2-R2-R1, not the pre-R2 tree.

## 1. Inputs (verified against live remote tips after `git fetch --all --prune`)

| Ref | SHA | Live remote ref (exact tip match) |
|---|---|---|
| TARGET | `2c20d58c88a0a8f5175f4d11041d03b6ca785e06` | `refs/heads/product-dev-recovered` (unchanged since M0) |
| SOURCE | `7fdb7c59ae23cf3891a99420bebd60cb8802be06` | `refs/heads/zcode/dc12r1-mvp-l1-he2-et1-r2-r2-r1-baseline-child-proof-truth-2026-08-29` (local == remote) |

## 2. Proof Gate

- `git merge-base TARGET SOURCE` = `6e9470a1daa5d6eece29724316fdd8aef6b737c1`
  — identical to the M0 expected merge-base (the candidate chain grew
  only on the SOURCE side).
- merge-base..TARGET: **57 files**; merge-base..SOURCE: **56 files**.
- Path intersection of the two sides: **0**.

## 3. Local merge rehearsal (never pushed)

- Isolated worktree from the EXACT TARGET with temporary local branch
  `integration/he2-et1-m1-rehearsal-2026-08-29`.
- `git merge --no-ff --no-edit 7fdb7c59…` → **exit 0, ZERO conflicts,
  ZERO manual modifications** (status clean immediately after).
- Rehearsal merge commit: `ad3f0d244e3e28db0f3b1e17192a88d0112d1a04`
  - Parent 1 (TARGET): `2c20d58c88a0a8f5175f4d11041d03b6ca785e06`
  - Parent 2 (SOURCE): `7fdb7c59ae23cf3891a99420bebd60cb8802be06`
  - Tree: `9d35b3018d60c04c7c91dadd38c6bae60d61becc`
- Structural proof: `git diff --name-only TARGET merge` = exactly the 56
  SOURCE-side paths; 0 product paths (`backend/`, `frontend/src/`,
  `scenarios/`) touched; 0 deletions vs TARGET; **all 56 SOURCE-side blobs
  byte-identical** in the merge tree (`git rev-parse SOURCE:path ==
  merge:path` for every path).

## 4. Gates run ON the local rehearsal merge commit

| Gate | Result |
|---|---|
| Governance unittests | **158/158 OK** (Python 3.12.10, pytest 9.1.1, psycopg 3.3.4) |
| Mutation gate | **85 RED / 9 GREEN PASS** — tree integrity byte-identical before/after |
| Runner `--self-test` | OK |
| Live Redis authority cases | **7/7 PASS** on the merge tree with FRESH throwaway redis7 (`he2et1m1_redis7` DB15) + PG16 (`he2et1m1_pg16`, role `m1_gate` rolsuper=f/rolcreatedb=t): GREEN full chain (rc=0, FINISHED, sentinel=1, collect_spawns=1), wrong-db, invalid-port, DB15-nonempty, post-preflight-disappearance (child fail-closed, command=0), unreachable, sentinel-26379-reachable |
| Authority core chain | **8/8 PASS** on the merge tree (same fresh stack; runner and child are two real processes in every CLI case) |
| Structural validator | **exit 0 — PASS** |
| Release validator | **exit 3 — BLOCKED**, attributed ONLY to pre-existing P0/P1 debt (`DEBT-AUTH-CRITICAL-TUPLES`, `DEBT-COMMERCE-CRITICAL-TUPLES`) |
| `git diff --check` | clean |
| detect-secrets (read-only hook vs `.secrets.baseline`) | **true exit code 0** (captured without pipes); baseline sha256 `c8f3aa245b94…` IDENTICAL before/after the check; baseline proven byte-identical to `16ea089b` on the merge tree (the R2-R2-R1 restoration carried through the merge) |
| Strict encoding scan over all 113 touched paths | **clean** — UTF-8, no BOM, no NUL, no CR, no U+FFFD |
| JSON parse | 17/17 existing config + schema + inventory JSON files parse (package.json/tsconfig.json absent at this root — not parse failures) |
| Workflow YAML strict parse | 3/6 parse; `s1-2-ci-gate.yml`, `s2-7-ci-gates.yml`, `s5-ci-gate.yml` fail strict pyyaml — **pre-existing at the merge-base**: blob-identical across TARGET == SOURCE == merge tree and absent from both diff sides (same attribution as M0) |

No product full-suite; no Playwright; no deployment.

## 5. Limits and honest non-claims

- **REMOTE_ENFORCEMENT_NOT_VERIFIED** — nothing here proves any
  GitHub-side enforcement (branch protection, required checks, or server-
  side merge behavior).
- The rehearsal merge commit `ad3f0d24…` was **NOT pushed**; no remote
  merge ref exists (verified in cleanup).
- Release validator remains **exit 3 (BLOCKED)** for the pre-existing
  P0/P1 debt; this rehearsal does not clear or downgrade it.
- This is a LOCAL merge readiness rehearsal ONLY — **not a merge
  approval**. It does not authorize pushing `product-dev-recovered` or
  any merge commit.

## 6. Cleanup (post-rehearsal)

- Rehearsal worktree `../he2et1_m1_rehearsal` and local branch
  `integration/he2-et1-m1-rehearsal-2026-08-29` deleted.
- `git ls-remote origin | grep integration/he2-et1-m1` → empty.
- Fresh containers removed WITH volumes (`docker rm -f -v`): 0 remaining,
  ports 15451/16384 verified CLOSED.
- TARGET / SOURCE remote tips re-verified unchanged after cleanup.
- This report branch was created directly FROM SOURCE (`7fdb7c59…`) and
  pushed; local == remote verified.

## 7. Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R2_R2_R1_M1_LOCAL_MERGE_READINESS_REHEARSAL**

STOP — awaiting CTO adjudication. Kilo remains un-started per the chain's
standing instruction; the candidate's own verdict ceiling
(CANDIDATE_READY_FOR_KILO_REVIEW_ONLY from R2-R2-R1) still governs the
SOURCE side.
