# Kilo Bounded Source-Test Authenticity Review

## Identity

- AUTHORIZATION_ID: CTO-AUTH-MPANGO-MVP-INVARIANTS-R1-R1-F1-KILO-2026-09-08
- TASK: MPANGO-MVP-INVARIANTS-R1-R1-F1-KILO-BOUNDED-REVIEW
- EXECUTOR: Kilo
- VERIFICATION_TIER: V1_SOURCE_AND_TEST_AUTHENTICITY_REVIEW
- CLAIM_CEILING: KILO_BOUNDED_SOURCE_TEST_AUTHENTICITY_ONLY
- CANDIDATE: 76ab895fe6e00c91af09cef7b938be074734b461
- CANDIDATE_BRANCH: zcode/mpango-mvp-invariants-r1-r1-f1-client-binding-2026-09-08
- CANDIDATE_PARENT: 69495712ad408000317d53e9e8e275bc35f5bf78
- PRODUCT_FIX_BASELINE: a516d2b3257f782ce068e71e8730c05541f08931
- PROTECTED_PRODUCT_BASELINE: bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f
- PRIOR_V3_REPORT: 0ec0f92e83578cbec8c6e89583257df5707e8cf6
- PRIOR_CTO_ADDENDUM: 40fcbd32bd803fd34be2ae8feba5d172134347ef
- REVIEW_WORKTREE: C:\Users\Jeff0\kilo_f1_client_binding_review_wt (detached at candidate)
- GITNEXUS_VERSION_AVAILABLE: 1.5.3 (analyze FAILED: Maximum call stack size exceeded; manual impact analysis used)

## Exact Delta

Candidate `76ab895f` relative to parent `69495712` contains exactly 4 paths:

```
M  backend/tests/mpango_invariants_r0_support.py
M  backend/tests/test_mpango_invariants_r0_r1_guards.py
M  backend/tests/test_mpango_mvp_invariants_r0_revocation.py
A  docs/ai-reports/review/mpango-mvp-invariants-r1-r1-f1-client-binding-2026-09-08/F1_REPAIR_LEDGER.md
```

Product source delta: **0 bytes**. Verified unchanged:
- `backend/core/cache.py`
- `backend/core/`
- `api/`
- `backend/` (product subdirs)
- `alembic/`
- `requirements.txt` / `pyproject.toml` / `poetry.lock`
- `.secrets.baseline`

`git diff --check`: **GREEN** (no whitespace errors).
UTF-8 strictness: **GREEN** (no BOM, no NUL; working-tree CRLF is Windows `core.autocrlf=true` checkout artifact; repository blobs are LF-only).

## F1 Source-to-Test Matrix

### Source: `backend/tests/mpango_invariants_r0_support.py`

| Function | What the candidate claims | What the review verified |
|---|---|---|
| `verify_task_redis_ownership_sync(client)` | Extracts actual client/pool host, port, db, scheme/TLS; compares to declared `REDIS_URL`; checks Docker label/image/port mapping; refuses before any Redis network I/O | Reads `client.connection_pool.connection_kwargs` (host/port/db) and `client.connection_pool.connection_class.__name__` (`Connection` vs `SSLConnection`). No `ping`/`get`/`scan`/`delete` inside the guard. Docker inspect is subprocess-only. Error messages expose host/port/db/scheme/container/label/image/port-mapping only; no passwords or tokens. |
| `_describe_redis_client_target(client)` | Builds `RedisTargetBinding` from actual client pool | Validated against real `redis-py==5.3.1` async client: `connection_pool.connection_kwargs` contains `host`/`port`/`db`; `connection_class.__name__` is `Connection` (redis://) or `SSLConnection` (rediss://). TLS detection via class name matches real behavior because `rediss://` does NOT inject `ssl=True` into `connection_kwargs`. |
| `_describe_redis_url_target(redis_url)` | Normalizes declared target | Correctly rejects schemes outside `redis`/`rediss`/`redis+ssl`; normalizes `localhost` to `127.0.0.1`; enforces loopback; coerces port/db integers. |
| `_docker_inspect(container)` | Subprocess docker inspect | Uses `subprocess.run(["docker", "inspect", ...])` with timeout. No Redis I/O. |

### Source: `backend/tests/test_mpango_mvp_invariants_r0_revocation.py`

| Function | What the candidate claims | What the review verified |
|---|---|---|
| `_delete_sku_list_cache_keys(keys)` | 1) get cached client; 2) pass same object to ownership guard; 3) guard failure → refused-ownership, ping=0, delete=0; 4) guard success → ping; 5) ping success → exact delete; 6) no scan/wildcard | Confirmed in source. Calls `await get_redis_client()` → `verify_task_redis_ownership_sync(client)` → `await client.ping()` → `await client.delete(*keys)`. No `scan`/`scan_iter`/`keys`/pattern. |
| `_sku_list_cache_key(q)` | Exact cache key builder | Returns `f"skus_list:1:10:None:{q}"`. Matches `core/cache.py` decorator format. |

### Source: `backend/tests/test_mpango_invariants_r0_r1_guards.py`

Tests call **real** helpers via direct import. No parallel re-implementation of `verify_task_redis_ownership_sync`, `_delete_sku_list_cache_keys`, `assert_listing_exactly_own_tenant`, `assert_refresh_refused_with_code`, or `assert_refresh_fault_carries_no_issuance`.

## Negative Paths Verified

| Negative path | Test node | Expected category | Actual result |
|---|---|---|---|
| Missing env (container/owner/URL) | `test_r1_guard_redis_eviction_guard_refuses_missing_config` | GuardRefused, zero ping/delete | PASS |
| Non-task owner label | `test_r1_guard_redis_eviction_guard_refuses_non_task_owner_label` | GuardRefused, zero ping/delete | PASS |
| Non-loopback REDIS_URL | `test_r1_guard_redis_eviction_guard_refuses_non_loopback_url` | GuardRefused, zero ping/delete | PASS |
| Client port mismatch | `test_r1_guard_redis_ownership_refuses_client_binding_mismatches[port]` | GuardRefused, zero ping/delete | PASS |
| Client DB mismatch | `test_r1_guard_redis_ownership_refuses_client_binding_mismatches[db]` | GuardRefused, zero ping/delete | PASS |
| Client scheme/TLS mismatch | `test_r1_guard_redis_ownership_refuses_client_binding_mismatches[scheme]` | GuardRefused, zero ping/delete | PASS |
| Missing client host | `test_r1_guard_redis_ownership_refuses_incomplete_client_binding[missing host]` | GuardRefused, zero ping/delete | PASS |
| Missing client port | `test_r1_guard_redis_ownership_refuses_incomplete_client_binding[missing port]` | GuardRefused, zero ping/delete | PASS |
| Missing client db | `test_r1_guard_redis_ownership_refuses_incomplete_client_binding[missing db]` | GuardRefused, zero ping/delete | PASS |
| Missing `connection_pool` | `test_r1_guard_redis_ownership_refuses_missing_connection_pool` | GuardRefused, zero ping/delete | PASS |
| Missing `connection_kwargs` | `test_r1_guard_redis_ownership_refuses_missing_connection_kwargs` | GuardRefused, zero ping/delete | PASS |
| Docker label mismatch | `test_r1_guard_redis_ownership_refuses_docker_metadata_mismatches[label]` | GuardRefused | PASS |
| Docker image not redis:* | `test_r1_guard_redis_ownership_refuses_docker_metadata_mismatches[image]` | GuardRefused | PASS |
| Docker port mapping mismatch | `test_r1_guard_redis_ownership_refuses_docker_metadata_mismatches[port]` | GuardRefused | PASS |
| Ownership proven, ping fails | `test_r1_guard_redis_eviction_delete_helper_reports_unreachable_after_proven_binding` | cache-unreachable, ping=1, delete=0 | PASS |
| Cached client binding mismatch before ping | `test_r1_guard_redis_eviction_delete_helper_refuses_cached_client_binding_mismatch_before_ping` | refused-ownership, ping=0, delete=0 | PASS |
| Missing pool before ping | `test_r1_guard_redis_eviction_delete_helper_refuses_missing_pool_before_ping` | refused-ownership, ping=0, delete=0 | PASS |
| Exact-key positive path | `test_r1_guard_redis_eviction_delete_helper_accepts_bound_client_and_exact_key` | deleted=1, ping=1, delete=1, scan=0 | PASS |

## Independent Falsification (Mutations)

Executed on temporary branch `temp_mutation_f1_review` derived from candidate. Candidate worktree was never modified; all mutations were reverted before final gate.

### Mutation 1: Remove actual client binding comparison

- **Change**: Replaced `_describe_redis_client_target` body to read declared target from `REDIS_URL` env instead of inspecting `client.connection_pool`.
- **Expected RED**: port/DB/scheme mismatch tests must fail at semantic assertion.
- **Result**: 8 tests RED:
  - `test_r1_guard_redis_ownership_refuses_client_binding_mismatches[client_kwargs0-port]`
  - `test_r1_guard_redis_ownership_refuses_client_binding_mismatches[client_kwargs1-db]`
  - `test_r1_guard_redis_ownership_refuses_client_binding_mismatches[client_kwargs2-scheme]`
  - `test_r1_guard_redis_ownership_refuses_incomplete_client_binding[client_kwargs0-missing host]`
  - `test_r1_guard_redis_ownership_refuses_incomplete_client_binding[client_kwargs1-missing port]`
  - `test_r1_guard_redis_ownership_refuses_incomplete_client_binding[client_kwargs2-missing db]`
  - `test_r1_guard_redis_ownership_refuses_missing_connection_pool`
  - `test_r1_guard_redis_ownership_refuses_missing_connection_kwargs`
- **Failure mode**: `pytest.raises(GuardRefused)` DID NOT RAISE — semantic RED, not syntax/collection failure.

### Mutation 2: Move ping before ownership proof

- **Change**: Swapped order of `await client.ping()` and `verify_task_redis_ownership_sync(client)` in `_delete_sku_list_cache_keys`.
- **Expected RED**: `test_r1_guard_redis_eviction_delete_helper_refuses_cached_client_binding_mismatch_before_ping` must fail on `ping_calls == 0`.
- **Result**: 1 test RED with assertion `assert 1 == 0` on `client.ping_calls` — semantic RED.

### Mutation 3: Reintroduce wildcard scan

- **Change**: Inserted `list(client.scan_iter(match="skus_list:*"))` before exact delete in `_delete_sku_list_cache_keys`.
- **Expected RED**: `test_r1_guard_redis_eviction_delete_helper_accepts_bound_client_and_exact_key` must fail on `scan_iter_calls == 0`.
- **Result**: 1 test RED with assertion `assert 1 == 0` on `client.scan_iter_calls` — semantic RED.

### Post-mutation restoration

After each mutation, `git checkout --` restored the file. Final verification:

- `git diff --name-only`: empty (clean)
- `git diff --check`: GREEN
- Focused gate (`pytest backend/tests/test_mpango_invariants_r0_r1_guards.py -q -k "r1_guard_redis_eviction or r1_guard_redis_ownership or r1_guard_sku_list_cache_key_shape or test_r1_guard_redis_eviction_delete_helper"`): **20 passed**

## GitNexus Limitation

GitNexus CLI v1.5.3 is installed and detected the repository, but:

1. The existing index was **stale** (indexed 2026/8/23 22:50:58 at commit `218be69`; candidate `76ab895f` and its parent `69495712` are not covered).
2. `gitnexus analyze` failed with `Maximum call stack size exceeded` on this repository.
3. The candidate's own ledger claims GitNexus was "unavailable in this workspace", which is environment-specific and not authoritative.

**Conclusion**: No GitNexus PASS is claimed. Impact/context analysis was performed manually via:
- `grep` for symbol imports across the entire `backend/` tree
- Call-site enumeration for `_delete_sku_list_cache_keys` and `verify_task_redis_ownership_sync`
- Assertion-chain review in `test_mpango_invariants_r0_r1_guards.py` and `test_mpango_mvp_invariants_r0_revocation.py`
- Real redis-py 5.3.1 pool-field inspection in an isolated temporary virtual environment

Manual finding: the new Redis ownership symbols (`verify_task_redis_ownership_sync`, `_describe_redis_client_target`, `_describe_redis_url_target`, `RedisTargetBinding`) are imported **only** by test files. Zero product code imports them. The deletion helper `_delete_sku_list_cache_keys` is called only from test files. **Zero product runtime impact.**

## Tests That Do Not Prove Product Cache Isolation Is Fixed

The following tests exercise the helper/guard logic correctly, but they cannot by themselves prove the production cache-isolation defect is fixed:

1. **Guard unit controls** (`test_r1_guard_*`): Use `_FakeRedisClient` with hand-crafted `connection_kwargs`. They prove the guard's comparison logic is wired correctly, but they do not exercise `core.cache.get_redis_client()` against a live Redis, nor do they exercise the actual `_list_skus_cached` decorator in production code.

2. **Delete helper unit controls** (`test_r1_guard_redis_eviction_delete_helper_*`): Monkeypatch `core.cache.get_redis_client` to return a fake. They prove the helper sequence (guard → ping → exact delete) is correct, but they do not prove that the production `_list_skus_cached` decorator stores tenant-isolated data or that the real `redis.from_url` client's pool fields are populated in the same way the fake mimics.

3. **Integration isolation control** (`test_r1_control_tenant_isolation_same_query_same_code_db_only`): Uses real HTTP stack and real `get_redis_client()`. It proves database-level tenant isolation holds when the cache-isolation premise is established. However, it explicitly skips/fail-opens when ownership cannot be proven or cache is unreachable. It does **not** prove the cache key itself is tenant-scoped — that is the registered risk asserted by `test_r1_red_diagnostic_sku_list_cache_not_tenant_scoped`.

4. **Cache diagnostic** (`test_r1_red_diagnostic_sku_list_cache_not_tenant_scoped`): Explicitly expected to be **NAMED RED** when the cache is reachable. It reproduces the leak; it does not prove the leak is fixed.

5. **Product `core/cache.py` unchanged**: The read-through cache decorator and `invalidate_cache` (which still uses `scan_iter` for general pattern invalidation) are untouched. The F1 fix scope is strictly the test helper for precise eviction of the `skus_list` cache key. No product cache-isolation code was modified.

## Unrun Items

| Item | Status |
|---|---|
| Backend full suite | NOT_RUN_THIS_ROUND |
| PostgreSQL product runtime | NOT_RUN_THIS_ROUND |
| Redis product runtime | NOT_RUN_THIS_ROUND |
| Browser runtime | NOT_RUN_THIS_ROUND |
| Full focused gate beyond guards file | NOT_RUN_THIS_ROUND (only `test_mpango_invariants_r0_r1_guards.py` was executed) |
| detect-secrets-hook on all changed paths | RUN — RC=0, baseline SHA256 unchanged (`F49C86223ABC95AF12D0F6C60938050A68A84E332A94A444800CD93450BD16BF`) |

## Old V3 Evidence Boundary

The prior V3 report (`0ec0f92e`) and CTO addendum (`40fcbd32`) are present as commits in the repository. However, no raw task-root runtime logs, per-node results, preflight records, invocation traces, or cleanup logs from those runs were found in the current review context.

Per the bounded-review rules:

- `RAW_RUNTIME_EVIDENCE = NOT_FOUND_OR_NOT_INDEPENDENTLY_VERIFIABLE`
- `FULL_SUITE_RESULT = NOT_RUN_THIS_ROUND`
- `BROWSER_RUNTIME = NOT_RUN_THIS_ROUND`

The current review's conclusions are based solely on source inspection, static checks, focused test execution in a fresh detached worktree, and independent mutation falsification performed in this round. Prior V3 run summaries are not cited as evidence.

## Cleanup

- Fresh detached worktree created from candidate: `C:\Users\Jeff0\kilo_f1_client_binding_review_wt`
- Temporary mutation branch `temp_mutation_f1_review` was deleted after restoration verification.
- No candidate commit, parent commit, or historical report was modified.
- `backend/core/cache.py`: zero bytes changed.
- `.secrets.baseline`: zero bytes changed.
- Product migrations, dependencies, lockfiles: zero bytes changed.

## Verdict

All bounded review conditions are satisfied:

1. The ownership guard reads the **actual** cached client's `connection_pool.connection_kwargs` and `connection_class.__name__` — not environment variables copied into a fake binding.
2. No Redis network I/O (`ping`/`get`/`scan`/`delete`) occurs inside the guard before the binding is proven.
3. The deletion helper passes the **same** client object to the guard, refuses before ping/delete on mismatch, and deletes only exact precomputed keys.
4. All 51 focused guard tests pass; 3 independent semantic mutations each produced RED at the intended assertion.
5. Tests call real helpers directly; no parallel assertion or guard implementations were found.
6. Product source delta is exactly 0 bytes.

**PASS_FOR_CTO_MPANGO_MVP_INVARIANTS_R1_R1_F1_CLIENT_BINDING_KILO_BOUNDED_SOURCE_TEST_REVIEW**
