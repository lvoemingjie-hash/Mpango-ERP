# ORDER R2 E1 F1-F3 — KILO V3 INDEPENDENT TARGETED VALIDATION REPORT

AUTHORIZATION_ID: CTO-AUTH-ORDER-R2-E1-F1-F3-KILO-V3-2026-09-19
EXECUTOR: Fresh Kilo context (Kilo V3) — not ZCode, not Kimi, not the source author
EXECUTION_HOST: Tencent VPS VM-0-3-ubuntu (1.14.247.12), fresh task root
  /home/ubuntu/order-e1-verify/order-e1-f1f3-kilo-v3-20260919 with task-owned resources only
VERIFICATION_TIER: V3_INDEPENDENT_TARGETED
RISK_TIER: FINANCIAL_ATOMICITY_AND_DATA_INTEGRITY
CLAIM_CEILING: ORDER_R2_E1_F1_F3_INDEPENDENT_TARGETED_EVIDENCE_ONLY
DATE: 2026-09-19

## 1. Formal disposition

PASS_FOR_CTO_ORDER_R2_E1_F1_F3_KILO_V3_TARGETED

Two formal invocations, one per authorized partition, each under its own atomic noclobber
sentinel. Neither partition was retried, amended or re-launched. Zero retries occurred.

- Partition A (runtime + bootstrap behavior, F4_039 explicitly deselected):
  27 passed, 0 failed, 0 errors, 0 skipped — rc=0, 42.20s (03:15:44Z → 03:16:30Z)
- Partition B (migration preflight opt-in, exactly one node):
  1 passed, 0 failed, 0 errors, 0 skipped — rc=0, 1.53s (03:20:16Z → 03:20:21Z)

Formal invocation count: 2 total (1 + 1). FULL_SUITE_RESULT=NOT_RUN.

## 2. Identity (independently re-verified this round)

- Remote branch codex/order-state-r2-e1-source-revision-f1-f3-20260919 tip == candidate
  2df6a3bfe8a7975b05f882cda19a6ac390b7a978 (evidence/git-identity-kilo.txt)
- candidate tree 39b3c2c43d2c84db0497a34f1030824e70bd79e4; base f734e7b03e6905b9ce1a5abefdb4e2c782f22723
  (tree ef8d9e159bd016653662dae416681df9be60aa5d); base IS ancestor; 4 ordinary linear successor
  commits, 0 merges; cumulative delta is EXACTLY the five named paths; git diff --check CLEAN
- Fresh clone from https://github.com/lvoemingjie-hash/Mpango-ERP.git; new detached worktree at the
  candidate; porcelain 0 entries; worktree tree == candidate tree
- Network honesty note: GitHub became intermittently unreachable from the VPS mid-preparation.
  The remote tip was verified in real time from the VPS earlier in the same preparation session
  (before degradation) and re-verified in real time from the executor's Windows control plane;
  both observations recorded with provenance in evidence/git-identity-kilo.txt and
  evidence/preflight-A.json. The candidate objects themselves were fetched from the remote by the
  fresh clone. No evidence artifact depends on a cached assertion.

## 3. Partition results — required evidence mapping (directive §2.4)

| Required evidence | Result | Artifact(s) |
|---|---|---|
| JUnit XML per partition | formal-results-A.xml (27/27 pass), formal-results-B.xml (1/1 pass) | evidence/ |
| stdout/stderr/rc per partition | captured at launch | results/pytest-output-A.txt, pytest-stderr-A.txt, rc in results/emission-A.log; same for B |
| node-set reconciliation per partition | collected == JUnit == selected; sets IDENTICAL; zero skip/fail/error | evidence/node-reconciliation-A.json, node-reconciliation-B.json |
| frozen node lists | A: 28 collected / 27 selected (F4_039 deselected); B: 1 node | evidence/frozen-collection-A.txt, selected-nodes-A.txt, selected-nodes-B.txt, frozen-collection-B.txt |
| financial before/after snapshots | A: before 03:02:22Z and after 03:17:07Z both all-zero, head 039 unchanged; B: source DB untouched by design, disposable DBs absent before and after | evidence/financial-before-A.txt, financial-after-A.txt, financial-before-B.txt, financial-after-B.txt |
| committed tests' internal zero-residue assertions | enforced inside the passing runs (provisioned_pool teardown zero-residue + sentinel fingerprint; s2_clean_db zero residue + unchanged public counts after every test) | visible in results/pytest-output-A.txt; assertions are part of the 27 passing nodes |
| exact candidate blob hashes before/after | all five paths: worktree files identical to candidate blobs before AND after both partitions | evidence/blob-hashes-kilo.txt, blob-hashes-after-kilo.txt |
| clean worktree proof | porcelain 0; HEAD == candidate; tree == candidate tree; delta-path diff empty; diff --check CLEAN | evidence/clean-worktree-proof-kilo.txt |
| read-only real detect-secrets scan with positive control | detect-secrets-hook 1.5.0: five candidate-blob extracts rc=0 against the candidate's committed baseline; positive control rc=1 (hook effective); baseline digest 5401aca4042522d4ec984ac2a2d3a8d4e08d2444a94a4019417c30274dfbb115 = candidate blob digest (not a smudged worktree digest); baseline unchanged after scan | evidence/secrets-scan-summary-kilo.txt, secrets-baseline-digest-kilo.txt, results/secrets-scan-kilo/ |
| exact formal invocation count, sentinels, start/end/PID | 2 formal invocations (A:1, B:1); sentinels FORMAL_SENTINEL_A (03:15:44Z) and FORMAL_SENTINEL_B (03:20:16Z); full start/end/PID/rc in emission records | evidence/invocations-and-sentinels-kilo.txt, results/emission-A.log, results/emission-B.log |
| task ownership + cleanup proof | containers labeled task/owner/authorization/partition; both removed; zero task-labeled containers remain; credential + env files destroyed; ports released; DBs destroyed with containers; B disposable DBs proven absent at cluster level pre-removal | evidence/container-records-kilo.txt, cleanup-proof-kilo.txt, temp-db-absence-B.txt |
| preflight sanitized evidence (before either launch) | candidate/tree/base, clean worktree, exact path delta, selected node IDs, exact command, Python + PostgreSQL versions, image identity, labels, loopback ports, database name, alembic head, role/session identity + attributes, env-name presence (no values), cleanup ownership | evidence/preflight-A.json, preflight-B.json, role-attributes-A.txt, role-attributes-B.txt, pg-server-version-A.txt, pg-server-version-B.txt, pip-freeze-kilo-v3.txt |

## 4. Nine required F1-F3 evidence groups — all covered by passing named nodes (Partition A)

1. retailer-mismatched payment rejected before any persistent change — test_e1f1_retailer_mismatched_payment_with_consistent_totals_rejected PASSED
2. inconsistent hold snapshot with matching aggregate cache rejected — test_e1f1_hold_snapshot_inconsistent_with_lifecycle_rejected PASSED
3. legal confirmed / converted-credit / settled-cash histories accepted — test_e1f1_legal_history_reconcile_positive_controls PASSED
4. cross-wholesaler, missing binding, populated-schema-missing-hold-table, non-canonical mapping, soft-deleted-only history fail closed — test_e1r1_* (3 nodes) + test_e1r2_* (2 nodes) PASSED
5. duplicate effective credit rows rejected on direct collection AND declaration confirmation — test_e1f2_split_credit_rejected_on_direct_collection, test_e1f2_split_credit_rejected_on_declaration_confirm PASSED
6. soft-deleted duplicate credit row does not create a false rejection — test_e1f2_soft_deleted_duplicate_credit_is_legal PASSED
7. observed real SQL writes put binding update after payment/receipt/ledger work — test_e1f3_settlement_binding_write_is_last_real_sql_order PASSED
8. fault at final binding update rolls back payment/hold/order/ledger/receipt/cache — test_e1f3_fault_at_binding_step_rolls_back_whole_settlement PASSED
9. SR1 hold-catalog gates retain conforming positive controls — test_sr1_f5_extra_constraint_on_hold_table_rejected, test_sr1_f5_extra_index_on_hold_table_rejected PASSED

(Plus SR1-F1/F2/F3/F4 runtime gates and the full E1 node set — see formal-results-A.xml for all 27.)

## 5. Partition B — migration preflight opt-in details

- Exactly one node: test_sr1_f4_039_preflight_rejects_non_finite_amounts — PASSED
- MPANGO_ALLOW_TEMP_DB_CREATE=1 set ONLY in Partition B's env file (env-partition-b.sh); never
  present in Partition A. MPANGO_TEMP_DB_ALLOWED_PORTS=15442 scoped to Partition B.
- Separate task PostgreSQL cluster (container kilo-order-e1-f1f3-pg-b, 127.0.0.1:15442) with a
  dedicated role oe1f3_kilo_b_run holding exactly the disposable-database authority the committed
  test's own contract requires (CREATEDB + CREATEROLE, NOSUPERUSER, NOBYPASSRLS, database owner).
  This authority was NOT exposed to Partition A (different container, different env, role without
  CREATEDB).
- The committed test created disposable databases test_r2sr1f4_<hex>, ran real alembic to
  038_catalog_identity_vertical_slice, exercised the 039 preflight against NaN/Infinity/-Infinity
  effective payment history (named invalid-history refusal, zero writes, version still 038), and
  dropped the disposable databases fail-closed. Cluster-level absence re-verified post-run
  (evidence/temp-db-absence-B.txt: remaining=0).

## 6. Runtime facts (independently observed)

- Real PostgreSQL 16.15 (postgres:16 image, imageID sha256:f1c3376c26f2..., Debian
  16.15-1.pgdg13+2), loopback 127.0.0.1:15441 (A) / 15442 (B), task databases
  order_e1_f1f3_kilo_a (A) and test_kilo_b_formal (B, identity-only source), alembic head
  039_order_credit_holds on A. No SQL mock, no source substitution, no sleep-based proof.
- Real candidate services under the real ASGI app with JwtAuthStrategy bound (r1_client/client
  fixtures). Python 3.12.3, pytest 8.4.2, pytest-asyncio 0.26.0 (pinned; evidence/pip-freeze-kilo-v3.txt).
- Redis NOT_REQUIRED (no redis instance created; no redis references in the collected files or
  fixture chain — consistent with the candidate's own fixture design).
- Preparation honesty: two pre-sentinel preparation failures, both fixed before any freeze and
  logged (alembic 011 required REPORTING_USER_PASSWORD in the migration env; transient GitHub
  unreachability during identity re-verification). Full-chain smoke validations on THROWAWAY
  databases passed before each freeze (A: alembic->039 + 1 real node, DB dropped; B: the ACTUAL
  F4_039 node on a throwaway source DB, DB dropped, no leftovers). Smoke runs were preparation,
  not formal invocations; each partition's formal invocation count remains exactly 1.

## 7. Privilege topology — disclosed limitation (not silently transplanted, not weakened)

Partition A used the candidate-supported topology: ONE dedicated non-superuser role
oe1f3_kilo_run (LOGIN, CREATEROLE, NOSUPERUSER, NOCREATEDB, NOBYPASSRLS) owning the task database
and running both the migration prep and the formal invocation. CREATEROLE is required by migration
011 (reporting_role/reporting_user) and tolerated ONLY as a disclosed limitation of the current
candidate bootstrap topology. This proves nothing about production least privilege. The tenant
DB-authority line remains a separately reviewed integration dependency; nothing in this run
transplants it or weakens roles to pass tests. Role attribute evidence:
evidence/role-attributes-A.txt (oe1f3_kilo_run login=1 createrole=1 super=0 createdb=0
bypassrls=0), evidence/role-attributes-B.txt (oe1f3_kilo_b_run login=1 createrole=1 super=0
createdb=1 bypassrls=0 — partition-B-only authority).

## 8. Prohibitions and unexecuted gates

- MERGE: NOT AUTHORIZED by this report. DEPLOYMENT: NOT AUTHORIZED by this report.
- This PASS closes ONLY the three E1 source findings (F1, F2, F3) under the stated claim ceiling.
  It does NOT approve merge until (a) the separate tenant DB-authority integration contact surface
  is reviewed, and (b) the final combined-candidate gate is reviewed.
- FULL_SUITE_RESULT=NOT_RUN (full-suite authorization explicitly not granted this round).
- Unexecuted gates: tenant DB-authority integration contact surface review; final combined-candidate
  gate; production least-privilege topology validation (not exercisable against this candidate).
- The ZCode E2 report was read as prior evidence only; no pass result, preflight or topology
  assertion was copied into this result. All artifacts here were independently generated from this
  task's own fresh clone, worktree, venv, containers and evidence generators.

## 9. Evidence root

/home/ubuntu/order-e1-verify/order-e1-f1f3-kilo-v3-20260919/
(evidence/, results/, prep/, FORMAL_SENTINEL_A, FORMAL_SENTINEL_B, repo clone, clean detached
worktree at 2df6a3bf, venv — retained; credentials and env files destroyed; see
evidence/cleanup-proof-kilo.txt)

DISPOSITION: PASS_FOR_CTO_ORDER_R2_E1_F1_F3_KILO_V3_TARGETED
