# DC-12R1-MVP-L1-HE2-ET1-R2-R2-R1-M2-E1 — Post-Merge Execution, Publication and Evidence-Truth Closure

- Date: 2026-08-29 (+08:00); Executor: Zcode
- Task: DC-12R1-MVP-L1-HE2-ET1-R2-R2-R1-M2-E1
- BASE/MERGE: `cdb39e96a50b308aff91d4e94fd8526e7540d921`
- Verification tier: V2_POST_MERGE_INTEGRATION
- Claim ceiling: POST_MERGE_EVIDENCE_CLOSURE_ONLY
- Verdict: PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R2_R2_R1_M2_E1_POST_MERGE_EXECUTION_AND_EVIDENCE_TRUTH_CLOSURE
- Machine-readable companion: `findings.csv` (same branch)
- This report commit's parent is exactly `cdb39e96…` (verified below).

## 1. Frozen-ref verification (live remote, after `git fetch --all --prune`)

| Ref | SHA | State |
|---|---|---|
| product-dev-recovered | `cdb39e96a50b308aff91d4e94fd8526e7540d921` | == MERGE (post-M2 tip) |
| SOURCE (R2-R2-R1 branch) | `7fdb7c59ae23cf3891a99420bebd60cb8802be06` | unchanged |
| KILO_FINAL | `38ea191d62c40b00b2de97c5d967cfb6c0717159` | unchanged |
| LUBUNTU_FINAL | `78febbae740e0a51575961357629cd5201f516ee` | unchanged |
| M1-E1 report branch | `49f2dc106ac3cd46a80654c972323ccf37cab970` | unchanged |
| main | `134ea59e02204842e55ebe36f721f44df5a33737` | unchanged (untouched) |

## 2. Fresh detached worktree at the MERGE SHA — structure re-verified

- Worktree `../he2et1_m2e1`, detached at `cdb39e96…`.
- Parents: `2c20d58c…` (TARGET product-dev-recovered pre-merge) +
  `7fdb7c59…` (SOURCE) — exact.
- Tree: `9d35b3018d60c04c7c91dadd38c6bae60d61becc` — exact.
- Paths entered from SOURCE (TARGET..MERGE): **56**; all 56 are exactly the
  M1 SOURCE-side list (comm overlap 56).

## 3. Fresh GitNexus index (no sibling-clone reuse)

- Re-fetched `gitnexus@1.6.10` (npm pack + install, `--ignore-scripts`)
  after the tarball had been cleaned in M2.
- `gitnexus analyze .` executed INSIDE the MERGE worktree → exit 0.
- `gitnexus status`: Repository = the MERGE worktree; **Indexed commit:
  cdb39e9 == Current commit: cdb39e9; Status: up-to-date**; full analyzer
  runner identity recorded (cliVersion 1.6.10, node v22.17.1 win32 x64,
  build digest `d312836d…`, 242 packages / 10490 artifacts digest
  `3fd4d673…`). The stale sibling-clone index from M2 was NOT reused.
- Disclosed: FTS/BM25 extension unavailable (mapping unaffected).

## 4. Execution gates ON the MERGE worktree

| Gate | Result |
|---|---|
| `python -m unittest discover -s harness-governance/tests -p "test_*.py" -v` | **158/158 OK** (verbose run; Python 3.12.10, pytest 9.1.1, psycopg 3.3.4) |
| `python harness-governance/validator/authority_runner.py --self-test` | **PASS** (SELFTEST: OK …) |
| `run_e2e_core_chain.py` (fresh PG16 + Redis7) | **8/8 PASS** |
| `run_e2e_redis_cases.py` (same fresh stack) | **7/7 PASS** |
| Fresh-stack preconditions | role `m2e1_gate` rolsuper=**false**, rolcreatedb=**true** (psql-verified); Redis **DB15 empty** (`DBSIZE` → 0, redis-cli verified); sentinel **26379 unreachable** (socket probe) |
| Structural validator | exit **0** |
| Release validator | exit **3** — RELEASE_GATE BLOCKED, attributed ONLY to the two pre-existing debts `DEBT-AUTH-CRITICAL-TUPLES`, `DEBT-COMMERCE-CRITICAL-TUPLES` |
| `git diff --check HEAD^1..HEAD` | exit 0 |
| detect-secrets (read-only `detect-secrets-hook --baseline`) | true exit code 0 (no pipes); baseline sha256 `c8f3aa245b94…` IDENTICAL before/after — the baseline was not rewritten |
| Strict encoding over the 113 merge-diff paths | clean — UTF-8, no BOM, no NUL, no CR, no U+FFFD |

Fresh stack details: containers `he2et1m2e1_pg16` (postgres:16-alpine,
role `m2e1_gate` LOGIN CREATEDB, trust auth scoped to the task container)
and `he2et1m2e1_redis7` (redis:7-alpine, DB15 empty), on a dedicated
docker network `he2et1m2e1_net`, host ports 127.0.0.1:15452 (PG) and
127.0.0.1:16385 (Redis). All removed WITH volumes and the network after
the runs; both ports verified CLOSED.

## 5. 85 RED / 9 GREEN — not re-run, classified by exact tree SHA

The mutation gate (85 RED / 9 GREEN) was executed at M1 on rehearsal
merge `ad3f0d24` whose tree is `9d35b3018d60c04c7c91dadd38c6bae60d61becc`.
This round's worktree re-proves the MERGE tree is the SAME
`9d35b301…` (§2). Classification: **M1_SAME_TREE_REUSED_EVIDENCE** — the
mutation results are valid for this merge tree by tree-SHA identity; they
were not re-run (per round instructions).

## 6. Evidence-wording correction

- REMOTE_PUSH_SUCCEEDED=**true** — M2 pushed `cdb39e96…` to
  `product-dev-recovered` (push rc 0; remote tip re-verified == merge).
- REMOTE_ENFORCEMENT_NOT_VERIFIED=**true** — unchanged and re-affirmed.
- **RETRACTED:** the M2 close-out sentence "this push is the first
  corroboration of the previous remote-enforcement caveat" (and any
  reading that a successful push proves required checks / branch
  protection are enabled). A successful push proves only
  `REMOTE_PUSH_SUCCEEDED`; it says nothing about branch protection or
  required checks, which remain unverified.

## 7. Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R2_R2_R1_M2_E1_POST_MERGE_EXECUTION_AND_EVIDENCE_TRUTH_CLOSURE**

Report commit parent == `cdb39e96a50b308aff91d4e94fd8526e7540d921`
(verified). STOP. H2-C, PRICING, SKU and deployment remain frozen; the
formal merge itself is complete and was NOT reverted or re-pushed; the
push proves only `REMOTE_PUSH_SUCCEEDED`.

## 8. Publication evidence model (M2-E2 appendix)

PUBLICATION_EVIDENCE_MODEL: a committed report records PRIOR IMMUTABLE
publication facts — e.g. PUB04 records
ORIGINAL_M2_E1_PUBLICATION_SHA=925df992a3b80ef044cc41f3957cea9e9f03e2c5
with ORIGINAL_M2_E1_LOCAL_REMOTE=PASS (proven immediately after that
push). A report commit can never truthfully pre-claim its own final SHA
or its own local==remote equality, because both are determined only at
push time; the E2 tip's equality is therefore proven after push and
reported in the external final response only.

Machine-readable fixes in this commit (findings.csv): the duplicate
finding ID CL01 is resolved — the classification row is renamed EV01
(M1_SAME_TREE_REUSED_EVIDENCE) and the three cleanup rows are renamed
CU01/CU02/CU03; all 31 finding IDs are globally unique and the CSV
strict-parses. PUB04 no longer reads DEFER-TO-PUSH.

Unchanged and re-affirmed: MERGE_SHA=cdb39e96a50b308aff91d4e94fd8526e7540d921;
REMOTE_PUSH_SUCCEEDED=true; REMOTE_ENFORCEMENT_NOT_VERIFIED=true; every
execution-gate result in sections 4–5. E2 verdict:
PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R2_R2_R1_M2_E2_PUBLICATION_AND_
FINDINGS_INTEGRITY_CLOSURE (publication metadata only; nothing re-run;
formal merge remains complete at cdb39e96).
