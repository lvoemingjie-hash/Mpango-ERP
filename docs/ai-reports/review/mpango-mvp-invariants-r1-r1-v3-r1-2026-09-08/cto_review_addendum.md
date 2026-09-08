# CTO Review Addendum

This addendum preserves the original published review and records the CTO's
disposition without rerunning PG/Redis/pytest/browser or changing candidate
code. It narrows the claim ceiling to the evidence actually available in this
workspace.

## F1: Redis ownership is not fully bound to the deleting client

The offline counterexample is a real control-flow gap, not a wording issue:

- `backend/tests/mpango_invariants_r0_support.py:56`
  - `verify_task_redis_ownership_sync`
- `backend/tests/test_mpango_mvp_invariants_r0_revocation.py:393`
  - `_delete_sku_list_cache_keys`
- `backend/core/cache.py:58`
  - `get_redis_client`

The guard proves a task-owned Redis instance from `os.environ`, but the delete
helper uses the cached client returned by `get_redis_client()` and does not
re-bind or compare that client to the proven target before calling `delete`.
That means the report's undeclared-ownership zero-delete probe is valid but
does not close the "verified B, deleted on A" gap described by the CTO.

Disposition: unresolved safety gap. The report should not be read as proving
actual client/pool binding for deletion.

## F2: Raw evidence bundle was not located in the checked workspace

The workspace contains the published summary artifacts, but not a raw task-root
bundle with the per-command logs the CTO asked for.

Located and preserved:

- `docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_RUN_LOG.md`
  sha256=2ed95c638c92384d08c660635a885f35ed8d96bdcd41862d8c09364b5ce26740
- `docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_RECORD.md`
  sha256=fefa1e6d74c4f5bd0cf3befa311f43034cd582bd90ce64df5f7dbb5fde43ac2b
- `docs/ai-reports/review/2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_TASK_REPORT.md`
  sha256=4e3f8f141e95c07ddacce84ea2bf43fac1f4be1642e9dda5f413ab1c10018cd0
- `docs/ai-reports/review/mpango-mvp-invariants-r1-r1-v3-r1-2026-09-08/review.md`
- `docs/ai-reports/review/mpango-mvp-invariants-r1-r1-v3-r1-2026-09-08/findings.csv`

Not found in the current workspace:

- `offline_verify.py`
- `offline_results.json`
- `published-review.md`
- `published-findings.csv`
- a non-empty task-private evidence root under `/home/ivy/AI_REPORT_INBOX`

Disposition: raw call/log/JUnit/preflight/cleanup records are not independently
proven from this workspace. They should be marked NOT_FOUND / NOT_PROVEN, not
backfilled from the summary artifacts.

## F3: Corrections to the published review wording

1. The three `2026-09-08_MPANGO_MVP_INVARIANTS_R1_AUTH_STOCK_*` documents are
   preserved author-run artifacts. They are not a separate on-disk independent
   V3 STOP record. I did not locate a distinct STOP artifact in the current
   workspace.
2. `NEGATIVE_AND_FAILURE_PATHS` should be read as:
   - duplicate-return RED is present in both reachable and unreachable Redis
     matrices;
   - the cache-diagnostic RED is present only when Redis is reachable and
     owned;
   - when Redis is unreachable, that cache-diagnostic node SKIPs because the
     premise is absent.
3. `UNCOVERED_NEW_PATHS` should name actual unproven code paths, not document
   artifacts. The unresolved code paths are the client-binding split between
   the ownership guard and the delete helper, plus the cached-client reuse path
   in `core/cache.py`.

## Evidence references available in this branch

- `docs/ai-reports/review/mpango-mvp-invariants-r1-r1-2026-09-08/*`
  - `EXPECTED_SET.md`
  - `FILES_MANIFEST.md`
  - `INTEGRITY_APPENDIX.md`
  - `NODE_RECONCILIATION.md`
  - `RUN_IDENTITY_BASE.md`
  - `RUN_IDENTITY_CANDIDATE.md`
  - `SELF_REVIEW.md`
  - `evidence/focused_reachable_summary.txt`
  - `evidence/focused_unreachable_summary.txt`
  - `evidence/frozen_base_invariants_pw1r3_nodes.txt`
  - `evidence/frozen_base_summary.txt`
  - `evidence/frozen_candidate_invariants_pw1r3_nodes.txt`
  - `evidence/frozen_candidate_summary.txt`

These are the only branch-local evidence references currently available to me.
They support the published summary, but they do not substitute for the missing
raw task-root bundle.

