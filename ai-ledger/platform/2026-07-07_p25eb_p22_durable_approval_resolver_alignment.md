# P25-EB P22 Durable Approval Resolver Alignment

**Phase:** P25-EB -- align the P22 default durable-approval resolver to the P20/P21 durable READ path (NO in-memory fallback)
**Date:** 2026-07-07
**Branch:** `codex/platform-p25eb-p22-durable-approval-resolver-alignment-2026-07-07`
**Base:** `079cfcd1` (P25-EA merge; includes the durable approval runtime P20/P21 cutover)
**Author:** Codex (Claude worker)
**Status:** Complete. R0 = async durable-read resolver + all P22 test files green. R1 = CTO repair:
the 4 executor-denial route tests now pass via the environment-agnostic operator secret (the test
override header correctly fails closed under MPANGO_ENV=production); the obsolete
`test_default_resolver_reads_p20_in_memory_store` is replaced by 6 durable-read-path unit proofs;
10 new P25-EB integration proofs cover the durable approval -> dry-run -> request -> governed
backup.check preflight happy path plus the full fail-closed matrix. Ready for CTO review.

---

## 1. Summary

P25-EB closes the resolver-alignment gap surfaced during the P25-EA closeout: the P22 controlled
execution skeleton resolved a `durable_approval_id` through a DEFAULT resolver that read the OLD P20
in-memory store. After the P20/P21 durable cutover (P21-DD), the durable approval is the single
source of truth and the in-memory store is gone from the runtime path. P22 had to follow.

This slice makes the P22 default resolver read through the SAME durable runtime path P20 uses after
the cutover: storage-readiness-gated `read_durable_approval`. It FAILS CLOSED -- if durable storage
is not ready or the read fails, the default resolver returns `None` (not-found -> blocked) and
NEVER falls back to the old in-memory store. The override seam (injected test snapshots) is
preserved for deterministic, DB-free tests; production uses the durable default.

To thread the async durable read through, the three service-boundary functions became async with an
optional `db: Optional[AsyncSession]` parameter:

- `services.evaluate_dry_run(..., db=None)`
- `services.record_execution_request(..., db=None)`
- `seam.evaluate_preflight_gate(..., db=None)`

The routes `await` these and forward the request `db` session (the existing `get_db` dependency).
The governed backup.check completion already passed a session and now forwards it into the preflight.

This is backend-only, P22-scoped, additive on the async boundary, and preserves every existing P22
invariant: nothing is executed by a dry-run / request (`executed=False`,
`execution_allowed=False`); result_state is only ever `dry_run_passed | blocked` for P22-B request
recording; the G15 static adapter descriptor is unchanged; the seam stays a non-executing preflight.

> **Approval is not execution.** A durable, quorum-met approval at
> `approved_execution_blocked` is a PRECONDITION for a passed dry-run and a recorded request; the
> durable READ path only resolves whether that precondition holds. It never executes anything.

---

## 2. Base / Branch / Commit Chain

- **Base SHA:** `079cfcd1` (P25-EA merge; the product branch tip carrying the P20/P21 durable
  runtime cutover).
- **Worktree:** the P25-EB branch, published with the explicit refspec
  `git push origin <branch>:<branch>`. `product-dev` / `product-dev-recovered` are NOT pushed.
- **Commit chain (base..tip):** reported in the chat report on completion.

`product-dev-recovered` is NOT merged and NOT the push target. Only the isolated P25-EB branch is
published.

---

## 3. What changed (R1 final: 4 backend source + 4 backend tests + 1 new test file + this ledger)

### Backend source (P22 only; P20 / P21 / P17 untouched)

- `backend/api/v1/platform/p22/services.py`
  - `_default_resolve_approval` is now `async`, signature
    `(approval_id, *, db: Optional[AsyncSession])`. It lazily imports
    `_check_durable_readiness` + `read_durable_approval` from P20, gates on readiness, reads via the
    durable path, and maps the record through `_snapshot_from_p20_record`. FAILS CLOSED: not-ready
    / missing / raised / no-db all return `None`. NO memory fallback.
  - `_resolve_approval` is now `async`, signature `(approval_id, *, db=None)`. Override seam is
    preserved (sync override called directly); otherwise the async durable default is used.
  - `evaluate_dry_run` is now `async` with `db=None` kwarg; resolves the approval via
    `await _resolve_approval(..., db=db)`.
  - `record_execution_request` is now `async` with `db=None` kwarg; re-validates the approval via
    the async resolver at request time.
  - `set_approval_resolver` / `reset_approval_resolver` unchanged (the test/dev seam).

- `backend/api/v1/platform/p22/seam.py`
  - `evaluate_preflight_gate` is now `async` with `db=None` kwarg; resolves the durable approval via
    `await _p22b._resolve_approval(request.durable_approval_id, db=db)`.

- `backend/api/v1/platform/p22/governed_execution.py`
  - The preflight call site now `await evaluate_preflight_gate(seam_request, db=db)`.

- `backend/api/v1/platform/p22/routes.py`
  - `execution_dry_run_route` and `create_execution_request_route` now
    `await services.evaluate_dry_run(..., db=db)` / `await services.record_execution_request(..., db=db)`.

### Backend tests

- `backend/tests/test_platform_p22_controlled_execution.py`
  - The 4 executor-denial route tests (`test_dry_run_support_operator_denied_as_executor`,
    `..._engineering_operator_...`, `..._tenant_contextual_super_admin_denied`,
    `..._tenant_admin_denied`) now send `OPERATOR_HEADERS` (the environment-agnostic machine
    credential) so the P10 guard passes in ANY env; the executor precondition then reads the
    authenticated non-super-admin identity and blocks with `executor_not_identity_super_admin`.
    The test-override header was unreliable under `MPANGO_ENV=production` (it correctly fails
    closed outside test|testing env).
  - The obsolete `test_default_resolver_reads_p20_in_memory_store` is REMOVED. It asserted the old
    in-memory read path which no longer exists. It is replaced by 6 durable-read-path unit proofs
    (see below).
  - Added 6 default-resolver proofs: returns None without a db session; returns None without an
    approval_id; FAILS CLOSED when durable storage is not ready (NO memory fallback -- the in-memory
    store is seeded and STILL returns None); reads the durable path when ready and maps fields
    (`available` -> `known`); returns None when the durable read returns None; returns None when the
    durable read raises (fail closed).

- `backend/tests/test_platform_p22e1_runtime_governed_adapter_seam.py`
  - Preflight tests updated to the async `evaluate_preflight_gate(..., db=db)` signature. 29/29 green.

- `backend/tests/test_platform_p22e3_backup_check_source_probe.py`
  - Route tests patched with an identity-only super_admin auth context (via `_enable_auth`) so the
    P10 guard passes via the identity path under `MPANGO_ENV=production`; the freshness assertion
    uses `datetime.now(timezone.utc)` so the P17 24h freshness window does not mark a fixed past
    timestamp stale. 28/28 green.

- `backend/tests/test_platform_p22g_governed_backup_check.py`
  - Service-level helpers `_passed_dry_run` / `_record_request` are async; route tests use
    `asyncio.run(...)` and `_enable_auth(monkeypatch)` for the identity path. 26/26 green.

- `backend/tests/test_platform_p25eb_durable_approval_resolver_integration.py` (NEW)
  - 10 integration proofs of the durable approval -> P22 alignment through the DEFAULT resolver
    (no override). Happy path: durable-resolved dry-run passes; execution request recorded at
    `dry_run_passed`; governed backup.check preflight passes and completes a fresh-success read.
    Fail-closed matrix: missing approval -> `approval_not_found`; action mismatch ->
    `action_mismatch_approval`; non-approved state -> `approval_state_not_approved_execution_blocked`
    + `quorum_not_met`; storage not ready -> `approval_not_found` with NO memory fallback (the
    read is never consulted past the readiness gate); read raises -> fail closed; no db session ->
    fail closed. Plus a non-execution invariant.

### No backend migration / no frontend / no P20 / P21 / P17 source change.

---

## 4. The alignment contract

Before P25-EB the P22 default resolver read the P20 in-memory store (`set_storage_mode("memory")`).
After the P21-DD durable cutover that store is no longer the runtime path. P22 now resolves through:

```
_resolve_approval(approval_id, *, db)
  |-- override seam (test/dev)  -> injected snapshot (sync, deterministic)
  '-- _default_resolve_approval(approval_id, *, db)
        |-- no approval_id OR no db  -> None (fail closed, no read)
        '-- import _check_durable_readiness, read_durable_approval (P20)
              |-- readiness = await _check_durable_readiness(db)
              |     '-- not ready / raised  -> None (NO memory fallback)
              '-- rec = await read_durable_approval(approval_id, db=db)
                    '-- None / raised  -> None (fail closed)
                    '-- _snapshot_from_p20_record(rec)  -> ApprovalSnapshot
```

**Fail-closed guarantees:**
- No `db` session -> no durable read, returns None (approval_not_found).
- Durable storage not ready -> returns None, the read is never consulted.
- Durable read missing / raises -> returns None.
- At NO point does the resolver consult an in-memory store. There is no fallback path.

---

## 5. Test results (R1)

All P22 test files green; the new P25-EB integration file green.

```
tests/test_platform_p22_controlled_execution.py        61 passed
tests/test_platform_p22e1_runtime_governed_adapter_seam.py  29 passed
tests/test_platform_p22e3_backup_check_source_probe.py     28 passed
tests/test_platform_p22g_governed_backup_check.py          26 passed
tests/test_platform_p25eb_durable_approval_resolver_integration.py  10 passed
```

**Pre-existing, out-of-scope note.** A small number of P20/P21 ROUTE tests
(`test_platform_p21dd_runtime_storage_cutover_gate.py`,
`test_platform_p21e_durable_approval_runtime_closeout.py`,
`test_platform_p20_durable_approval_governance.py`) currently fail in this runner because they rely
on the `X-Platform-Test-Override` header to pass the P10 guard, and the runner has
`MPANGO_ENV=production` (the test override correctly fails closed outside test|testing env). These
are NOT P25-EB regressions: P25-EB touches only P22 source and P22 tests; no P20/P21 file is
modified. The P22 route tests were made robust to this by using the operator secret
(`OPERATOR_HEADERS`) / identity-only super_admin path.

---

## 6. Gates

- `git diff --check`: clean (no whitespace errors).
- Added-line ASCII sweep: clean (no non-ASCII in added lines).
- `detect-secrets`: `.secrets.baseline` unchanged; no new secrets.
- Forbidden-path audit: only P22 source + P22/P25-EB tests touched; no migration / tenant / payment /
  product / P16 / P17 / P20 / P21 source path.
- Scope Diff Gate: `git diff --name-status` is limited to the P22 module + P22/P25-EB tests + this
  ledger; no out-of-scope file, no large deletion, no backend migration / deploy drift.
- Worktree clean after commit.

---

## 7. Non-execution invariants (preserved)

- P22-B request records stay `executed=False`, `execution_allowed=False`, `execution_started=False`;
  result_state only `dry_run_passed | blocked`.
- The G15 static `backup.check` adapter descriptor is unchanged (`not_implemented` /
  `source_unknown`).
- The seam (`seam.py`) stays a NON-EXECUTING preflight boundary; the governed backup.check
  completion is the only REALIZED read action and is unchanged in shape.
- No subprocess / shell / SQL / pg_dump / restore / queue / worker / tenant mutation / migration /
  auth rewrite / frontend / dependency change was introduced.
