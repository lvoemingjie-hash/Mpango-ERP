# MPANGO MVP Invariants R1/R1/V3-R1 Independent Safety Evidence Review

## Identity
- AUTHORIZATION_ID=CTO-AUTH-MPANGO-MVP-INVARIANTS-R1-R1-V3-R1-2026-09-08
- TASK=MPANGO-MVP-INVARIANTS-R1-R1-V3-R1
- CANDIDATE=69495712ad408000317d53e9e8e275bc35f5bf78
- PARENT=baea994322821723cf900d653b36bfa098cf79ca
- PRODUCT_FIX_BASELINE=a516d2b3257f782ce068e71e8730c05541f08931
- PROTECTED_PRODUCT_BASELINE=bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f
- CANDIDATE_BRANCH=zcode/mpango-mvp-invariants-r1-r1-test-evidence-closure-2026-09-08
- REPORT_BRANCH=reports/mpango-mvp-invariants-r1-r1-v3-r1-opencode2-2026-09-08
- CTO_SCOPE_ERRATUM_ACCEPTED=yes
- Claim ceiling: INDEPENDENT_AUTH_STOCK_AND_TEST_SAFETY_EVIDENCE_WITH_REGISTERED_KNOWN_REDS_ONLY
- No product merge, no deployment, no product fix approval.

Prior V3 STOP preserved and not rewritten:
- docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_RUN_LOG.md
  sha256=2ed95c638c92384d08c660635a885f35ed8d96bdcd41862d8c09364b5ce26740
- docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_RECORD.md
  sha256=fefa1e6d74c4f5bd0cf3befa311f43034cd582bd90ce64df5f7dbb5fde43ac2b
- docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_REPORT.md
  sha256=4e3f8f141e95c07ddacce84ea2bf43fac1f4be1642e9dda5f413ab1c10018cd0

## Preflight
- git fetch --all --prune: completed.
- candidate, parent, product baseline, and protected baseline identity checks: exact.
- candidate detached worktree created from 69495712ad408000317d53e9e8e275bc35f5bf78.
- worktree is clean except for this report branch output.
- git diff --check: clean.
- PRODUCT_FIX_BASELINE..CANDIDATE diff set: 19 paths, exactly 6 modified and 13 added.
- product source paths changed: 0.
- all 19 paths decode as UTF-8, have no BOM, have no NUL bytes, are LF-only, and have worktree sha256 identical to blob sha256.
- GitNexus unavailable in this environment: no MCP tool and no CLI binary. Manual per-path review used instead; no false PASS claimed.

## Runtime
- Fresh task-owned PostgreSQL 16 container: mpango_v3r1_pg
  - image=postgres:16-alpine
  - owner label=mpango.owner=zcode-mvp-invariants-r1-r1-v3-r1
  - loopback binding=127.0.0.1:60211->5432
- Fresh task-owned Redis 7 container: mpango_v3r1_redis
  - image=redis:7-alpine
  - owner label=mpango.owner=zcode-mvp-invariants-r1-r1-v3-r1
  - loopback binding=127.0.0.1:60212->6379
- Redis reachable probe: PONG.
- Final focused matrices:
  - Redis reachable with declared ownership: 55 passed, 2 failed, 177 warnings.
  - Redis unreachable: 55 passed, 1 failed, 1 skipped, 187 warnings.
- Registered known REDs only:
  - tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_red_concurrent_full_return_single_economic_effect
  - tests/test_mpango_mvp_invariants_r0_revocation.py::test_r1_red_diagnostic_sku_list_cache_not_tenant_scoped
- No unexpected RED, ERROR, extra SKIP, or known-RED green outcome in the final matrices.

## Redis Ownership Negative Control
- Direct helper probe against the task-owned Redis returned refusal before deletion:
  - RESULT=refused-ownership(GUARD_REFUSED_REDIS_OWNERSHIP: missing required environment: MPANGO_INVARIANTS_R0_PG_OWNER. Cache-key deletion requires a declared, task-owned Redis instance.)
  - DELETE_CALLS=0
- This is the zero-delete proof for undeclared ownership.

## Secret Scan
- detect-secrets-hook version=1.5.0.
- Synthetic canary containing a test AWS key pattern: rc=1 as expected.
- Real scan argv: detect-secrets-hook --baseline .secrets.baseline <19 candidate paths>.
- Real scan covered the exact 19 candidate paths: rc=0.
- Baseline sha256 before and after scan: c8f3aa245b94d4f4b0242ae8c5a64fbf1f4716483baae91ad65f78735c0290e6.
- Baseline bytes were unchanged.

## CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS
- backend/tests/mpango_invariants_r0_support.py
- backend/tests/test_mpango_invariants_r0_r1_guards.py
- backend/tests/test_mpango_mvp_invariants_r0_revocation.py

## CODE_PATH_TO_TEST_MATRIX
- backend/tests/mpango_invariants_r0_support.py -> shared guards for task-owned PG/Redis/JWT setup, ownership proofs, and teardown behavior used by both matrices and the undeclared-ownership negative control.
- backend/tests/test_mpango_invariants_r0_r1_guards.py -> guard assertions for Redis ownership proof, exact-key cleanup, and refusal paths.
- backend/tests/test_mpango_mvp_invariants_r0_revocation.py -> revocation and cache diagnostic coverage; one registered known RED is expected only when Redis is reachable and owned.
- backend/tests/test_mpango_mvp_invariants_r0_concurrency.py -> concurrency and duplicate-return economics coverage; one registered known RED is expected only when Redis is reachable and owned.

## NEGATIVE_AND_FAILURE_PATHS
- Reachable declared matrix: the two registered known REDs above.
- Unreachable matrix: the duplicate-return RED remains; the cache diagnostic path is SKIP because the premise is absent.
- Undeclared ownership negative control: helper refused before deletion and deleted zero keys.
- GitNexus unavailable: no MCP/CLI support to run analyze/status.
- Full suite and browser runtime were not run in this round.

## FALSIFICATION_RESULT
- Final evidence did not produce any unexpected RED, ERROR, or extra SKIP.
- The only REDs were the two registered known REDs under the reachable declared-ownership premise.
- The undeclared-ownership probe falsified unsafe deletion by proving DELETE_CALLS=0.
- No detect-secrets finding was produced.

## UNCOVERED_NEW_PATHS
- docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_RUN_LOG.md: preserved prior STOP evidence; reviewed and hashed, not runtime-executed.
- docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_RECORD.md: preserved prior STOP evidence; reviewed and hashed, not runtime-executed.
- docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_REPORT.md: preserved prior STOP evidence; reviewed and hashed, not runtime-executed.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/EXPECTED_SET.md: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/FILES_MANIFEST.md: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/INTEGRITY_APPENDIX.md: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/NODE_RECONCILIATION.md: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/RUN_IDENTITY_BASE.md: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/RUN_IDENTITY_CANDIDATE.md: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/SELF_REVIEW.md: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/evidence/focused_reachable_summary.txt: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/evidence/focused_unreachable_summary.txt: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/evidence/frozen_base_invariants_pw1r3_nodes.txt: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/evidence/frozen_base_summary.txt: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/evidence/frozen_candidate_invariants_pw1r3_nodes.txt: report artifact only.
- docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/evidence/frozen_candidate_summary.txt: report artifact only.

## FULL_SUITE_RESULT
NOT_RUN_THIS_ROUND

## BROWSER_RUNTIME
NOT_RUN

## CTO Review Addendum
See `cto_review_addendum.md` for the F1/F2/F3 corrections and the evidence-completeness notes.
