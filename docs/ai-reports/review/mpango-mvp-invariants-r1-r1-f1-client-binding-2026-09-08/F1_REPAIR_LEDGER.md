# F1 Repair Ledger

## Identity

- BASE_CANDIDATE=69495712ad408000317d53e9e8e275bc35f5bf78
- BASE_CANDIDATE_BRANCH=zcode/mpango-mvp-invariants-r1-r1-test-evidence-closure-2026-09-08
- PRODUCT_FIX_BASELINE=a516d2b3257f782ce068e71e8730c05541f08931
- PROTECTED_PRODUCT_BASELINE=bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f
- PRIOR_V3_REPORT=0ec0f92e83578cbec8c6e89583257df5707e8cf6
- PRIOR_CTO_ADDENDUM_REPORT=40fcbd32bd803fd34be2ae8feba5d172134347ef
- REPORT_BRANCH=zcode/mpango-mvp-invariants-r1-r1-f1-client-binding-2026-09-08
- WORKTREE=/home/ivy/Desktop/mpango-f1-client-binding-2026-09-08
- FINAL_CANDIDATE_SHA=TO_BE_EXTERNALLY_VERIFIED_AFTER_PUSH

## Scope

Modified paths are limited to:

1. backend/tests/mpango_invariants_r0_support.py
2. backend/tests/test_mpango_mvp_invariants_r0_r1_guards.py
3. backend/tests/test_mpango_mvp_invariants_r0_revocation.py
4. docs/ai-reports/review/mpango-mvp-invariants-r1-r1-f1-client-binding-2026-09-08/F1_REPAIR_LEDGER.md

Product delta is 0. No product source, migration, dependency, baseline, or prior evidence file was edited.

## Repair Summary

- `verify_task_redis_ownership_sync(client)` now proves the actual cached client/pool binding before any ping or delete.
- The guard compares host, port, database index, and scheme/TLS binding against the declared `REDIS_URL`.
- `_delete_sku_list_cache_keys(keys)` now:
  - gets the cached client,
  - proves ownership on that same client,
  - pings only after ownership proof,
  - deletes only the exact precomputed keys.
- No wildcard SCAN or pattern delete is used in the final helper.

## Actual Binding Proof

Positive binding case exercised in the guard tests:

- Declared URL: `redis://localhost:60212/15`
- Actual client pool target: host `127.0.0.1`, port `60212`, db `15`, scheme `redis`, tls `false`
- Docker inspect proof:
  - owner label: `zcode-mvp-invariants-r1-r1`
  - image: `redis:7-alpine`
  - loopback mapping: `127.0.0.1:60212 -> 6379/tcp`
- Ownership helper return: `127.0.0.1:60212`
- Delete helper positive result:
  - `ping_calls=1`
  - `delete_calls=1`
  - `delete_args=('skus_list:1:10:None:R1ISOSHAREDAB12CD34',)`
  - `scan_calls=0`
  - `scan_iter_calls=0`
  - `keys_calls=0`

## CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS

- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_redis_ownership_accepts_normalized_loopback_binding`
- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_redis_ownership_refuses_client_binding_mismatches`
- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_redis_ownership_refuses_incomplete_client_binding`
- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_redis_ownership_refuses_missing_connection_pool`
- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_redis_ownership_refuses_missing_connection_kwargs`
- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_redis_ownership_refuses_docker_metadata_mismatches`
- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_sku_list_cache_key_shape_is_exact`
- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_redis_eviction_delete_helper_accepts_bound_client_and_exact_key`
- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_redis_eviction_delete_helper_refuses_cached_client_binding_mismatch_before_ping`
- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_redis_eviction_delete_helper_reports_unreachable_after_proven_binding`
- `tests/test_mpango_invariants_r0_r1_guards.py::test_r1_guard_redis_eviction_delete_helper_refuses_missing_pool_before_ping`
- `tests/test_mpango_mvp_invariants_r0_revocation.py::test_r1_control_tenant_isolation_same_query_same_code_db_only`
- `tests/test_mpango_mvp_invariants_r0_revocation.py::test_r1_red_diagnostic_sku_list_cache_not_tenant_scoped`

## CODE_PATH_TO_TEST_MATRIX

| Code path | Test coverage |
| --- | --- |
| `backend/tests/mpango_invariants_r0_support.py::verify_task_redis_ownership_sync(client)` | positive binding proof; port/db/scheme mismatch rejection; incomplete binding rejection; missing `connection_pool` rejection; missing `connection_kwargs` rejection; Docker label/image/port-mapping mismatch rejection |
| `backend/tests/mpango_invariants_r0_support.py::_describe_redis_client_target` | client binding mismatch tests; incomplete binding tests; missing pool/kwargs tests |
| `backend/tests/test_mpango_mvp_invariants_r0_revocation.py::_delete_sku_list_cache_keys(keys)` | exact-key positive path; cached-client binding mismatch before ping; reachable binding then ping failure => `cache-unreachable`; missing pool before ping; no scan/pattern calls |
| `backend/tests/test_mpango_mvp_invariants_r0_revocation.py::_sku_list_cache_key(q)` | exact cache key shape test |
| `backend/tests/test_mpango_mvp_invariants_r0_revocation.py::assert_listing_exactly_own_tenant` | mixed-tenant same-code rejection; foreign-tenant same-code rejection; real isolation control |
| `backend/tests/test_mpango_mvp_invariants_r0_revocation.py::assert_refresh_refused_with_code` | masked-code negative control; token-bearing 401 negative control |
| `backend/tests/test_mpango_mvp_invariants_r0_revocation.py::assert_refresh_fault_carries_no_issuance` | issuer-use and token-bearing fault negative control |

## NEGATIVE_AND_FAILURE_PATHS

- Port mismatch between declared Redis URL and cached client binding -> refused ownership, zero ping, zero delete.
- DB mismatch between declared Redis URL and cached client binding -> refused ownership, zero ping, zero delete.
- Scheme/TLS mismatch between declared URL and cached client binding -> refused ownership, zero ping, zero delete.
- Missing `connection_pool` -> refused ownership, zero network delete.
- Missing `connection_kwargs` -> refused ownership, zero network delete.
- Missing host/port/db in the client binding -> refused ownership, zero network delete.
- Docker owner label mismatch -> refused ownership.
- Docker image mismatch -> refused ownership.
- Docker loopback port mapping mismatch -> refused ownership.
- Cached client mismatch detected before ping -> refused ownership, ping_calls=0.
- Ping failure after proven binding -> `cache-unreachable(...)`, delete_calls=0.
- Exact-key helper mutation to reintroduce wildcard scan -> red on `scan_calls == 1`.
- Mutation that removed client-binding comparison -> red on port/db/scheme mismatch cases.
- Mutation that moved ping ahead of ownership proof -> red on the pre-ping refusal check.

## FALSIFICATION_RESULT

Mutation tests were run on temporary edited states and each was RED at the semantic assertion:

1. Removed the actual client-binding comparison in `verify_task_redis_ownership_sync(client)`.
   - Command: `pytest tests/test_mpango_invariants_r0_r1_guards.py -k 'client_binding_mismatches' -q`
   - Result: `3 failed, 48 deselected`
   - Failing assertion: binding mismatch cases no longer raised `GuardRefused`.

2. Moved ping ahead of ownership proof in `_delete_sku_list_cache_keys(keys)`.
   - Command: `pytest tests/test_mpango_invariants_r0_r1_guards.py -k 'delete_helper_refuses_cached_client_binding_mismatch_before_ping' -q`
   - Result: `1 failed, 50 deselected`
   - Failing assertion: the helper no longer stayed pre-ping and did not refuse ownership first.

3. Reintroduced wildcard SCAN in `_delete_sku_list_cache_keys(keys)`.
   - Command: `pytest tests/test_mpango_invariants_r0_r1_guards.py -k 'delete_helper_accepts_bound_client_and_exact_key' -q`
   - Result: `1 failed, 50 deselected`
   - Failing assertion: `scan_calls == 1`.

Recovered final gate:

- Command: `pytest tests/test_mpango_invariants_r0_r1_guards.py -q`
- Result: `51 passed, 2 warnings`

## UNCOVERED_NEW_PATHS

- No known uncovered paths in the edited test/support surface after the focused guard gate.
- System-level runtime paths were intentionally not exercised in this repair:
  - PostgreSQL product runtime: NOT_RUN
  - Redis product runtime: NOT_RUN
  - Full suite: `FULL_SUITE_RESULT=NOT_RUN_THIS_ROUND`
  - Browser runtime: `BROWSER_RUNTIME=NOT_RUN`

## FULL_SUITE_RESULT

NOT_RUN_THIS_ROUND

## BROWSER_RUNTIME

NOT_RUN

## GitNexus

Unavailable in this workspace (`gitnexus` command not found). No GitNexus PASS is claimed.

## Retained Product REDs

The repair does not change the registered product REDs:

- `tests/test_mpango_mvp_invariants_r0_concurrency.py::test_r0_red_concurrent_full_return_single_economic_effect`
- `tests/test_mpango_mvp_invariants_r0_revocation.py::test_r1_red_diagnostic_sku_list_cache_not_tenant_scoped`

## Cleanup and Drift

- Fresh detached worktree was created from `BASE_CANDIDATE`.
- `backend/core/cache.py` was not modified.
- `.secrets.baseline` was not modified.
- No product tracked delta was introduced.
- Candidate/parent refs remained pinned to the frozen base for this repair branch.
