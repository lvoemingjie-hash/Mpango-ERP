# P21-E Durable Approval Runtime Closeout + Proof Packet

**Phase:** P21-E (durable approval runtime closeout / readiness proof)
**Date:** 2026-06-30
**Track:** platform durable approval store (P21), over the P20 durable approval API and
the P21-D-D runtime storage cutover gate.

**Branch:** `codex/platform-p21e-durable-approval-runtime-closeout-2026-06-30`
**Base:** `origin/platform-dev` at `a6f5ef8` (merge: P21-D-D runtime storage cutover gate).
`origin/platform-dev` is NOT merged and NOT advanced by this slice; only the isolated
feature branch is pushed.
**Commit chain:** base `a6f5ef8` -> `c0c21a1` (P21-E closeout proof tests) -> this ledger
commit. The branch tip SHA is recorded in the final report rather than pinned here (an
amend would change it; short SHAs are used throughout to keep the ledger secret-scan
clean).

## Objective

Close out the P21 durable approval store by PROVING the runtime already forms an
auditable, restart-safe, default-DURABLE approval storage loop. This is NOT new feature
work and NOT a controlled-action execution slice. It is a closeout / proof / hardening
slice that (a) re-verifies the runtime behavior committed in P21-D-D, and (b) strengthens
the proof surface at the layers not previously exercised (the full ROUTE lifecycle, the
restart boundary for LIST and for a quorum-reaching DECISION, the route-level 503 leak
surface, and the durable adapter source for execution-path references).

Approval is not execution, and durability is not execution. No controlled action is
executed, no tenant state is mutated, and `execution_allowed` / `executed` /
`execution_gate` keep their safe values on every record.

## Modified files (scope)

All changes are within the allowed platform scope
(`backend/tests/test_platform_p2*`). This slice is a single NEW test file plus this
ledger (2 files). No file under `backend/api/v1/platform/p20/**` or
`backend/api/v1/platform/p21/**` is modified -- those are read-only here and are only
re-verified.

- `backend/tests/test_platform_p21e_durable_approval_runtime_closeout.py` (NEW) - 8
  self-contained integration tests (closeout proof packet). See the Proof matrix below.
- `ai-ledger/platform/2026-06-30_p21e_durable_approval_runtime_closeout.md` (NEW) - this
  ledger.

## Runtime behavior summary (re-verified, unchanged from P21-D-D)

The runtime behavior was committed by P21-D-D and is NOT changed by P21-E. P21-E only
re-verifies and strengthens the proof. Confirmed from
`backend/api/v1/platform/p20/services.py`, `p20/routes.py`, `p20/schemas.py`, and
`backend/api/v1/platform/p21/adapter.py`, `p21/models.py`:

- **Default mode is DURABLE.** `p20.services.get_storage_mode()` resolves
  test-override -> `MPANGO_P20_DURABLE_APPROVAL_STORAGE` env flag -> DURABLE default. Any
  value other than the literal `memory` stays DURABLE (no silent memory activation).
- **Explicit memory mode is test/dev only.** Reachable only via the `set_storage_mode`
  test seam or the exact env value `memory`; the memory backend carries
  `storage == "memory"` and is never selected in production.
- **Store-not-ready fails CLOSED -> 503.** `_check_durable_readiness` requires the DB
  reachable AND all five P21-C1 public tables present; otherwise it returns a closed
  `DurableStoreNotReady` code (`storage_not_ready` | `unavailable` | `degraded`) which the
  route translates to HTTP 503 (`p20/routes._raise_storage_not_ready`). The closed detail
  shape is `{code, message, storage:"durable", unavailable_reason}`.
- **No silent memory fallback.** In DURABLE mode the four public handlers never touch the
  in-memory `_STORE`; a not-ready store raises rather than fabricating a record.
- **Frontend-compatible response shape.** Both backends return the `DurableApprovalRecord`
  / `DurableApprovalQueue` shapes; only `storage` differs (`durable` vs `memory`).
- **No execution.** `execution_allowed == False`, `executed == False`,
  `execution_gate == "blocked"`, `redaction_applied == True` on every record; the
  validating mapper `_from_durable_record` re-asserts these and fails CLOSED if a durable
  record ever violated them.

## Proof matrix (requirement -> exact test name)

Existing tests are cited as `module::class::test`; P21-E additions are marked **(P21-E)**.
Test files: `tp20g` = `test_platform_p20_durable_approval_governance.py`,
`tp21dd` = `test_platform_p21dd_runtime_storage_cutover_gate.py`,
`tp21ai` = `test_platform_p21_durable_approval_adapter_implementation.py`,
`tp21e` = `test_platform_p21e_durable_approval_runtime_closeout.py`.

### 1. Runtime proof review
| Requirement | Proof test(s) |
| --- | --- |
| Default mode is durable | `tp21dd::TestStorageModeResolver::test_default_mode_is_durable` |
| Explicit memory is test/dev only | `tp21dd::TestStorageModeResolver::test_env_memory_flag_selects_memory`; `tp21dd::TestExplicitMemoryMode::test_memory_mode_uses_in_memory_store` |
| Store-not-ready -> 503, no memory write | `tp21dd::TestStoreNotReady::test_create_raises_and_writes_no_memory`, `::test_decision_raises_and_writes_no_memory`, `::test_read_and_list_raise_when_not_ready` |
| No silent memory fallback | `tp21dd::TestStoreNotReady::test_no_silent_memory_fallback_record_returned`; `tp21dd::TestRestartSafety::test_create_survives_new_session` (asserts `_STORE` empty); **(P21-E)** `tp21e::TestRouteLayerEndToEndCloseout::test_full_durable_lifecycle_route_layer`, `tp21e::TestRouteLayerFailureModeCloseout::*` |
| Response shape frontend-compatible | **(P21-E)** `tp21e::TestRouteLayerEndToEndCloseout::test_route_create_response_shape_frontend_compatible` (asserts every contract field present + typed) |

### 2. Restart-safety proof
| Requirement | Proof test(s) |
| --- | --- |
| create via service; record survives restart (read) | `tp21dd::TestRestartSafety::test_create_survives_new_session`; `tp21ai::test_restart_safety_new_adapter_reads_back`; `tp21ai::test_audit_sequence_no_monotonic_across_restart` |
| LIST still finds the record after restart | **(P21-E)** `tp21e::TestRestartSafetyCloseout::test_list_finds_record_after_session_restart` |
| DECISION still works after restart boundary (reaches quorum) | **(P21-E)** `tp21e::TestRestartSafetyCloseout::test_decision_reaches_quorum_across_restart_boundary` |

### 3. End-to-end route proof (POST / GET queue / GET by id / POST decision)
| Requirement | Proof test(s) |
| --- | --- |
| Full durable lifecycle at the route layer | **(P21-E)** `tp21e::TestRouteLayerEndToEndCloseout::test_full_durable_lifecycle_route_layer` |
| approval does not execute (every step) | same (asserts `executed`/`execution_allowed` False at create, each decision, and quorum) |
| quorum met -> `approved_execution_blocked` | same (checker-2 -> `quorum_pending`; checker-3 -> `approved`, state `approved_execution_blocked`) |
| `executed=false`, `execution_allowed=false`, `execution_gate=blocked` | same (asserted on create, GET-by-id, both decisions, and the quorum record) |

### 4. Failure-mode proof
| Requirement | Proof test(s) |
| --- | --- |
| Missing migration/schema -> `storage_not_ready` / 503 | `tp21dd::TestReadinessGate::test_storage_not_ready_when_schema_missing`; `tp21dd::TestStoreNotReady::test_create_raises_and_writes_no_memory` |
| DB unavailable -> `unavailable` / 503 | `tp21dd::TestReadinessGate::test_unavailable_when_db_unreachable`; **(P21-E)** `tp21e::TestRouteLayerFailureModeCloseout::test_route_503_unavailable_when_db_unreachable` |
| Degraded adapter write -> fail CLOSED (no memory success) | `tp21dd::TestDegradedPath::test_create_degraded_when_op_fails_after_readiness` |
| Raw reason / idempotency key do not leak in FAILURE response | `tp21dd::TestStoreNotReady::test_not_ready_leaks_no_raw_key_or_reason` (service); **(P21-E)** `tp21e::TestRouteLayerFailureModeCloseout::test_route_503_storage_not_ready_leaks_no_raw_key_or_reason` (route response body) |

### 5. Security invariant review (re-verified)
| Invariant | Proof test(s) |
| --- | --- |
| identity-only super_admin guard unchanged | `tp20g::TestPermissions::*` (guard not modified; git diff shows no `routes.py`/guard change) |
| maker = authenticated actor | `tp20g::TestIdentityBinding::test_response_maker_is_actor_not_payload`, `::test_no_actor_decision_denied` |
| checker = authenticated actor | `tp20g::TestIdentityBinding::test_payload_approver_matching_actor_accepted`, `::test_payload_approver_mismatch_denied` |
| same actor cannot approve own request | `tp20g::TestDualControl::test_same_actor_cannot_create_then_approve`; `tp21dd::TestDurableDualControl::test_maker_cannot_self_decide` |
| quorum requires distinct checkers | `tp20g::TestDualControl::test_two_distinct_auth_actors_meet_quorum`, `::test_system_fallback_cannot_count_toward_quorum`; `tp21dd::TestDurableDualControl::test_quorum_requires_two_distinct_checkers` |
| raw idempotency key never stored or echoed | `tp20g::TestIdempotencyDigest::test_raw_create_key_not_in_store_only_digest`, `::test_response_echoes_digest_not_raw_key`; `tp21ai::test_raw_idempotency_key_never_persisted`; `tp21dd::TestDurableIdempotency::test_create_key_digest_only_no_raw_in_db` |
| reason / metadata redacted | `tp20g::TestRedaction::*`; `tp21ai::test_raw_secret_reason_redacted_before_persistence`; **(P21-E)** `tp21e::TestRouteLayerEndToEndCloseout::test_route_create_redacts_secret_reason_on_durable_path` |
| source_status unknown/unavailable never treated as healthy | `tp20g::TestP18Boundary::test_unknown_source_cannot_approve`, `::test_available_is_never_fabricated`; `tp21dd::TestDurableDualControl::test_approve_denied_against_unknown_source` |
| approval is not execution | `tp20g::TestSafetyInvariants::*`; `tp21ai::test_no_execution_invariant_across_lifecycle`; **(P21-E)** `tp21e::TestNoExecutionSourceInvariantCloseout::test_durable_runtime_source_references_no_execution_path` |

## Test commands and counts

Run from `backend/` with the shared venv and `PYTHONPATH=backend` (and a non-weak
`SECRET_KEY`, `MPANGO_ENV=test`). Integration tests spin their own throwaway
`postgres:15` container (never the developer DB) and skip cleanly when docker is absent.

P21-E new suite (the closeout packet):

```
python -m pytest tests/test_platform_p21e_durable_approval_runtime_closeout.py \
                 -m integration -q
-> 8 passed
```

Directive-gated durable-approval surface (combined; the 6 suites that share the
integration fixture model):

```
python -m pytest \
  tests/test_platform_p20_durable_approval_governance.py \
  tests/test_platform_p21dd_runtime_storage_cutover_gate.py \
  tests/test_platform_p21_durable_approval_adapter_implementation.py \
  tests/test_platform_p21e_durable_approval_runtime_closeout.py \
  tests/test_platform_p21_durable_approval_models.py \
  tests/test_platform_p21_durable_approval_adapter_skeleton.py \
  -q
-> 196 passed
```

Per-file collected counts:

| File | Collected | Status |
| --- | --- | --- |
| `test_platform_p20_durable_approval_governance.py` | 71 | passed |
| `test_platform_p21dd_runtime_storage_cutover_gate.py` | 36 | passed |
| `test_platform_p21_durable_approval_adapter_implementation.py` | 23 | passed |
| `test_platform_p21e_durable_approval_runtime_closeout.py` (NEW) | 8 | passed |
| `test_platform_p21_durable_approval_models.py` | 26 | passed |
| `test_platform_p21_durable_approval_adapter_skeleton.py` | 32 | passed |
| `test_platform_p21_durable_approval_migration.py` | 6 | skip in isolation (see Known limitations) |
| `test_platform_p21_durable_approval_schema.py` | 31 | skip in isolation (see Known limitations) |

The full migration chain `001..020` (including `020_durable_approval_store`) is applied
end-to-end by every integration fixture's `alembic upgrade head`, so migration 020 is
re-proven applied-and-working on every integration run.

## Validation gates

- `git diff --check origin/platform-dev..HEAD` -> CLEAN (no whitespace/conflict markers).
- P21-D-D runtime tests -> 36 passed.
- P20 durable approval governance tests -> 71 passed.
- P21 adapter / models / skeleton tests -> 23 + 26 + 32 passed.
- P21-E closeout tests -> 8 passed.
- Non-ASCII scan on the changed file -> ASCII-clean (0 non-ASCII bytes).
- Secret scan against the configured baseline -> 0 new findings (raw scan also 0; the 10
  inline test fixtures are marked allowlist and suppressed).
- Forbidden-path audit -> CLEAN. The only changed paths are
  `backend/tests/test_platform_p21e_durable_approval_runtime_closeout.py` and this ledger.
  No path under product/tenant/payment/auth/frontend/alembic/env.py/lockfile/baseline/CI
  or any P22 path is touched.
- `npx gitnexus analyze` -> indexed successfully (8,081 nodes | 24,760 edges | 528
  clusters | 300 flows).
- GitNexus `detect_changes` (scope `compare`, base `origin/platform-dev`) -> 20 changed
  symbols, ALL confined to the new test file; **0 affected processes**; **risk_level:
  low**. No production execution flow is touched.
- Worktree clean -> verified at branch tip after the ledger commit (see final report).

## Security invariant review (self-review, Round 1 - Security)

Reviewed specifically for: silent memory fallback, identity spoofing, raw key/reason
leakage, approval accidentally becoming execution, and source_status becoming falsely
healthy. Findings: none.

- No silent memory fallback: every durable-path test asserts `_STORE == {}`; the
  store-not-ready path raises and writes nothing; `_from_durable_record` fails CLOSED.
- No identity spoofing: maker/checker bind to the authenticated actor; a client-supplied
  maker/approver that differs from the actor is denied on both backends.
- No raw key/reason leakage: the create key is stored only as a SHA-256 digest; reason /
  metadata are redacted via the P18 allowlist on every path; the 503 failure body is a
  fixed closed shape that cannot echo a raw key or reason (proven at the route layer).
- Approval != execution: no execution-path token (`execute_action` / `run_action` /
  `apply_action` / `executed = True` / `execution_allowed = True`) appears in either the
  P20 services or the P21 concrete adapter source; the adapter only calls the P18
  redaction/sanitization helpers; quorum resolves to `approved_execution_blocked` with
  `executed`/`execution_allowed` still False.
- source_status is never fabricated healthy: `SOURCE_STATUS_MAP` never upgrades
  unknown/unavailable/degraded; an approve requires `validation_status == "valid"`.

## Reproducibility review (self-review, Round 2 - Reproducibility)

Reviewed specifically for: hidden local DB assumptions, manual SQL requirements, test
order dependency, undocumented Docker-only assumptions, and skipped tests counted as
proof. Findings: none blocking.

- No hidden local DB assumption: a throwaway `postgres:15` container hosts self-contained
  `p21e_mig` / `p21e_bare` databases; the fixture asserts the URL never contains the
  developer DB names; it skips (not fails) without docker.
- No manual SQL: prerequisites mirror `database/init.sql` programmatically and migration
  020 is applied via `alembic upgrade head`.
- No test-order dependency: autouse per-test fixtures reset the storage mode, clear the
  in-memory store, and truncate the durable tables; each test is independent.
- Multi-request route lifecycle uses `NullPool` (documented in the helper) so sequential
  TestClient requests never reuse a stale pooled connection.
- No skipped test is counted as P21-E proof: all 8 P21-E tests RUN and PASS in the
  validation environment (docker present).

## Risk classification

- **Change class:** test-only, additive (one new self-contained integration test file).
- **Runtime risk:** NONE. No runtime, schema, migration, auth/RBAC, or frontend file is
  modified; the durable approval runtime is unchanged from P21-D-D and only re-verified.
- **Blast radius (GitNexus `detect_changes`):** 0 affected processes; risk_level low; all
  changed symbols are within the new test file.
- **Reversibility:** fully reversible (delete the test file; the branch is not merged).

## Known limitations

1. **`test_platform_p21_durable_approval_migration.py` (6) and
   `test_platform_p21_durable_approval_schema.py` (31) skip in isolation and ERROR only
   when run AFTER the integration suites.** This is a PRE-EXISTING test-ordering
   interaction, NOT a P21-E regression: those suites decide skip-vs-run from
   `DATABASE_URL`, and the integration fixtures set `DATABASE_URL` to their throwaway
   container during module setup; by the time these suites run, the container is torn down
   and they attempt to connect to a dead URL. Confirmed pre-existing by reproducing the
   same errors with the prior P21-D-D + adapter files alone (no P21-E file present). Both
   skip cleanly when run in isolation. Migration 020 itself is re-proven applied-and-working
   by every integration fixture's `alembic upgrade head`. Fixing the ordering interaction
   is out of P21-E scope (it is test-harness behavior, not P21 runtime logic).
2. P21-E adds no new functional capability by design (closeout / proof / hardening only).
3. Retention / export operations (`expire_due_requests`, `purge_eligible_records`,
   `export_record`) remain deferred to the separately CTO-gated P21-D-future slice; this is
   unchanged by P21-E and is not a regression.

## P21 status recommendation

**P21_DURABLE_APPROVAL_STORE_READY**

Rationale: the P21-C1 public migration (020) is merged and re-proven applied; the P21-D-C
concrete durable adapter implements create / read / list / decide against the public tables
with restart-safe, atomic transactions and digest-only idempotency; the P21-D-D runtime
gate defaults to DURABLE, retains memory only as an explicit test/dev backend, and fails
CLOSED to 503 when the store is not ready with NO silent memory fallback; and P21-E closes
the remaining proof gaps (route lifecycle, restart LIST/quorum, route-level 503 leak
surface, adapter no-execution source invariant). Approval is provably not execution;
durability is provably not execution; the store is restart-safe across session/adapter
recreation.

## Explicit statements

- No controlled action is executed (approval is not execution; durability is not
  execution).
- No tenant mutation and no P17 registry mutation.
- No new migration / alembic revision (migration 020 is unchanged; only re-applied by
  integration fixtures).
- No `env.py` change.
- No auth / RBAC / session rewrite (the P10 identity-only guard is reused unchanged).
- No frontend change.
- `origin/platform-dev` is NOT merged and NOT pushed by this slice; only the isolated
  feature branch is pushed.
- P22 is NOT started.
