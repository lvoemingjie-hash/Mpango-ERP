# P21-D-D Runtime Storage Cutover Gate

**Phase:** P21-D-D (runtime storage cutover gate)
**Date:** 2026-06-30
**Track:** platform durable approval store (P21), built on the P20 durable approval API

**Branch:** `codex/platform-p21dd-runtime-storage-cutover-gate-2026-06-30`
**Base:** `origin/platform-dev` at `4488dba` (merge: P21-D-C durable approval adapter
implementation). `origin/platform-dev` is NOT merged and NOT advanced by this slice.
**Commit chain:** single commit at branch tip (code + tests + this ledger). The exact
feature-branch HEAD SHA is recorded in the final report, not pinned here (an amend would
change it).

## Objective

Cut the P20 durable approval runtime storage over from the unrecoverable in-process
memory queue to the P21-D-C durable store adapter, behind an EXPLICIT, auditable,
reversible readiness gate. The default runtime mode is DURABLE (production). The
in-memory store is retained ONLY as an explicit test/dev backend. When the durable
store is not ready the gate fails CLOSED (a clear 503), never silently falling back to
memory and never fabricating a durable record as success.

Approval is not execution and durability is not execution. No controlled action is
executed, no tenant state is mutated, and `execution_allowed` / `executed` /
`execution_gate` keep their safe values on every record.

## Modified files (scope)

All changes are within the allowed platform scope (`backend/api/v1/platform/p20/**`,
`backend/api/v1/platform/p21/**` is read-only here, `backend/tests/test_platform_p2*`).

The P21-D-D commit contains 7 files total: the 6 code/test files below plus this
ledger. (GitNexus `detect_changes` reports `changed_files=5` because it compares
tracked content and excludes new/untracked files -- the new test file and this
ledger.) The follow-up R1 correction edits only stale docstrings/comments in
`p21/adapter.py` (text only, no logic) plus this count wording; it is recorded
separately and does not change the P21-D-D runtime behavior described here.

- `backend/api/v1/platform/p20/services.py` - storage-mode resolver, `DurableStoreNotReady`
  closed vocabulary, readiness gate, validating durable mapper, error maps, and four
  public handlers that dispatch on the resolved mode. The existing in-memory logic is
  retained verbatim as the explicit `_memory_*` backend.
- `backend/api/v1/platform/p20/routes.py` - the four P20 endpoints now go through the
  gate; list/read/decision became `async` and thread the request `db`; a
  `_raise_storage_not_ready` helper translates a gate failure to 503.
- `backend/tests/test_platform_p20_durable_approval_governance.py` - the existing
  in-memory suite now forces explicit memory mode (autouse), resetting on teardown.
- `backend/tests/test_platform_p21_durable_approval_adapter_skeleton.py` - the obsolete
  "P20 must not reference p21" scans replaced with cutover-aware scans (services now wire
  the adapter behind the gate; schemas stay clean).
- `backend/tests/test_platform_p21_durable_approval_adapter_implementation.py` - the two
  obsolete no-cutover source scans replaced with cutover-wiring scans.
- `backend/tests/test_platform_p21dd_runtime_storage_cutover_gate.py` - NEW focused gate
  suite (36 tests) against an ephemeral Postgres.

No `p21/**` source, `app.py`, `models/__init__.py`, alembic, env.py, dependency,
lockfile, baseline, CI, deploy, or frontend file is touched.

## Exact runtime behavior before vs after

**Before (P20-B + P21-D-C):** the four P20 endpoints always used the module-level
in-memory globals (`_STORE`, `_STORE_BY_CREATE_KEY`, `_AUDIT_LOG`). Records carried
`storage == "memory"` and were lost on process restart. The P21-D-C concrete adapter
existed but was never imported by P20 (it stayed `is_live_store == False`).

**After (P21-D-D):**
- `get_storage_mode()` resolves override > env flag > `durable` default. The env flag
  `MPANGO_P20_DURABLE_APPROVAL_STORAGE=memory` selects the explicit memory backend; any
  other value (and the unset default) is DURABLE.
- DURABLE mode: each operation runs the readiness gate, then the durable adapter. Records
  carry `storage == "durable"` and are restart-safe (persisted to the P21-C1 public
  tables by the adapter).
- MEMORY mode (explicit test/dev): unchanged in-memory behavior, `storage == "memory"`.
- The durable adapter itself is unchanged and still `is_live_store == False`; the P20
  service gate is what elects durability at runtime.

## Storage mode and gate behavior

Readiness gate (`_check_durable_readiness`): constructs the adapter (marks the session
system-scope for the tenant guardrail bypass) and counts the five P21-C1 durable tables
in `information_schema`. Returns one closed-vocabulary outcome:
- ready (all five tables present, DB reachable) -> proceed via the adapter;
- `storage_not_ready` (reachable but schema/tables missing, or adapter init failed);
- `unavailable` (DB unreachable / query error).

Operation failures after a passed readiness check (an unexpected adapter exception) fail
CLOSED to `degraded`. A malformed (non-UUID) approval_id on read/decision maps to
not-found (404 / shaped denial), matching the in-memory contract, not to a store fault.

The four closed failure codes are `storage_not_ready | unavailable | degraded`. The P20
routes translate any `DurableStoreNotReady` to HTTP 503 with
`{code, message, storage:"durable", unavailable_reason}`. There is NO silent memory
fallback in DURABLE mode: the in-memory `_STORE` is never written on the durable path,
and a denial on the durable path carries `storage == "durable"` (never `memory`).

The explicit mapper (`_from_durable_record`) does not loosely merge dicts: it re-asserts
`execution_allowed is False`, `executed is False`, `execution_gate == "blocked"`,
`redaction_applied is True`, and `storage == "durable"`, failing CLOSED (raising) if a
durable record ever violated them.

## Tests with counts (real, re-run counts)

- `test_platform_p20_durable_approval_governance.py` - 71 passed (explicit memory mode).
- `test_platform_p21_durable_approval_adapter_skeleton.py` - 32 passed (cutover-aware
  source scans + unchanged skeleton surface).
- `test_platform_p21_durable_approval_models.py` - 26 passed (unchanged).
- `test_platform_p21_durable_approval_adapter_implementation.py` - 23 passed (P21-D-C
  adapter, unchanged behavior, updated wiring scans).
- `test_platform_p21_durable_approval_migration.py` - 6 passed (run against an ephemeral
  DB; skips on the dev-DB safety guard otherwise).
- `test_platform_p21dd_runtime_storage_cutover_gate.py` - 36 passed (NEW).
- Regression: `test_platform_p10_contracts.py`, `test_platform_p18_controlled_actions.py`,
  `test_platform_p19_approval_workflow.py`, `test_platform_audit_api.py`,
  `test_platform_p17_registry.py` - 315 passed, 0 failed.

P21-D-D NEW suite coverage: storage-mode resolver + closed vocabulary (pure); readiness
ready / storage_not_ready / unavailable / shell-degraded; durable create/list/read/
decision through the DB adapter; restart-safety across a NEW session; store NOT ready ->
create/decision/read/list raise and the route returns 503; no silent memory fallback
(`_STORE` stays empty); no raw key/reason leak on the not-ready path; idempotency digest
preserved + digest-only in DB; maker-checker identity binding; quorum of distinct
checkers; reject-final; source-honesty; approval NEVER executes; explicit memory mode is
marked `storage == "memory"`; mapper fails CLOSED on a violating record; route-layer 503
and 404.

## GitNexus analyze + detect_changes

- `npx gitnexus analyze`: indexed cleanly. 8,022 nodes | 24,631 edges | 510 clusters |
  300 flows (300 is the stable platform-runtime flow count; node/cluster counts fluctuate
  slightly across re-indexes).
- `detect_changes` (compare vs `origin/platform-dev`): `changed_count=93`,
  `affected_count=21`, `changed_files=5`, `risk_level=critical`. This is EXPECTED and OK
  for a platform-runtime cutover: every affected process is a P20 route
  (create/list/read/decision + the guard) flowing to PlatformAuditLog / the durable
  adapter / `DurableStoreNotReady` / `_http_exc`. PRODUCT-BUSINESS TOKEN HITS: NONE
  (no order/payment/invoice/inventory/ledger/customer/retail/wholesale/sku/finance/
  shipment/fulfill/reservation/receivable/credit/collection/product flow is affected).
  Every changed symbol is under `p20/` or `tests/`; OUT-OF-SCOPE symbols: NONE. The
  stop-condition gate ("no product business process affected") passes.

## Forbidden path audit

Changed paths: the six files listed above. None touch `product-dev-recovered/`, tenant
business flows, payment/billing, auth/RBAC/session, frontend, a new migration / alembic
revision, env.py, package/lockfile, the secrets baseline, or CI/deploy infra. `git diff
--check origin/platform-dev` is clean (no whitespace errors).

detect-secrets: the pre-commit detect-secrets hook with the repo's configured baseline
returns clean (exit 0) on all six files. The baseline file is not modified.

## Security invariants

- identity-only super_admin guard unchanged (P10 guard reused); the maker/checker bind to
  the authenticated actor (never the client payload), enforced by the adapter.
- maker-checker separation, distinct checkers, reject-final, and quorum are enforced by
  the durable adapter (mirroring P20-B exactly) with `store_version` optimistic locking.
- idempotency key stored/echoed only as a one-way SHA-256 digest; raw key never persisted
  or echoed (verified by a durable digest-only scan).
- reason / metadata redacted before persistence (P18 redaction reused); the not-ready
  path echoes no raw key/reason (dedicated test).
- unknown/unavailable source_status is never fabricated healthy; approve requires an
  available source.
- approval NEVER executes: every durable record is re-validated to
  `execution_allowed == False`, `executed == False`, `execution_gate == "blocked"`
  (fail-closed mapper; no-execution source scan).

## Known limitations

- In DURABLE mode the feature requires the P21-C1 migration (020) to be applied; until
  then every durable approval operation returns 503 `storage_not_ready`. This is the
  intended fail-closed gate, not a defect.
- DURABLE create denial for an unresolvable P18 reference returns a shaped not-found
  record and is not written as a durable audit row (consistent with "a denial creates no
  request row"). Durable denial-audit for that pre-adapter case is deferred.
- Retention / export durable operations remain deferred (P21-D-future), as in P21-D-C.
- An asyncpg prepared-statement concern on the readiness `text()` query across pooled
  connections was investigated and ruled out: the readiness query runs cleanly across
  many pooled reuses in the suite (the earlier failures were a test-helper argument-order
  bug, not a production issue).

## Risk classification

- Overall: LOW (platform-runtime-additive; no product/business/auth/migration change;
  full reversible gate; comprehensive tests).
- The DURABLE-default change is the one production-visible behavioral shift and is
  intentionally fail-closed (503 until the migration is applied). Classified LOW /
  mitigated: it can never fake success or silently fall back to memory, and it is
  reversible by setting the memory env flag or by reverting the slice.
- detect_changes `critical` is EXPECTED for this phase type and passes the real
  "no product business process affected" gate.

## Blockers

None for CTO review.

## Explicit statements

- No execution: no P18 controlled action is executed; `execution_allowed`/`executed`
  stay false, `execution_gate` stays "blocked".
- No tenant mutation: no tenant lifecycle / registry / provisioning / business data is
  changed.
- No migration: no new alembic revision; migration 020 (P21-C1) remains the head.
- No auth/RBAC/session rewrite: the P10 identity-only guard is reused unchanged.
- No frontend: no frontend file is touched.
- `origin/platform-dev` is NOT merged and NOT pushed; only the isolated feature branch is
  pushed.
- P22 is NOT started.

## Revision history (text-only corrections; no runtime logic change)

The P21-D-D runtime behavior is unchanged across these revisions; each only
corrects stale boundary docstrings/comments/ledger wording left over from the
P20-B / P21-D-B "in-memory skeleton" era.

**R1 (commit `a2c1c6f`, on top of P21-D-D `872aff8`):** corrected stale cutover
text in `backend/api/v1/platform/p21/adapter.py` (module + skeleton/concrete
class docstrings, `IS_LIVE_STORE` / `ADAPTER_PHASE` / `is_live_store` /
`__init__` / `AUDIT_RESULT_BY_EVENT_TYPE` comments, section header,
`StoreNotImplementedError` docstring, and the skeleton `create_request` message
string) and the top docstrings of `backend/api/v1/platform/p20/services.py` and
`backend/api/v1/platform/p20/routes.py`; plus this ledger's file-count wording.
Removed all "P20 never imports p21", "NO RUNTIME STORAGE CUTOVER", "running store
stays memory", and "P21-D-1 / P21-D-2 deferred" claims. `is_live_store=False` and
`ADAPTER_PHASE="P21-D-B-skeleton"` values unchanged. R1 commit = 4 files.

**R2 (commit at branch tip, on top of `a2c1c6f`):** CTO-review follow-up fixing
the remaining PACKAGE-LEVEL boundary text:
- `backend/api/v1/platform/p21/__init__.py` - rewritten: states the package
  contains the durable adapter (skeleton P21-D-B + concrete P21-D-C); the P20
  P21-D-D readiness gate may select it as durable storage; the adapter never
  executes a controlled action.
- `backend/api/v1/platform/p20/__init__.py` - rewritten: durable approvals default
  to P21 durable storage through the P21-D-D readiness gate; explicit memory mode
  is test/dev only; approval is not execution.
- `backend/api/v1/platform/p20/schemas.py` - module docstring + the two `storage`
  field description strings rewritten: schemas preserve the P20 API shape across
  durable and explicit memory modes; `storage` distinguishes `"durable"` vs
  `"memory"`; no execution. The `storage` field default (`"memory"`) and type
  (`str`) are unchanged (not a logic change).
- this ledger - R2 section added; file counts kept accurate.

R2 commit = 4 files (the three package files above plus this ledger).

Post-R2 grep across `backend/api/v1/platform/p20/` and `p21/` shows 0 hits for:
`no P20 route or service is rewired`, `runtime storage cutover / feature flag`,
`NOT imported by api.v1.platform.p20`, `stays in-memory`, `in-memory only`,
`all in process-local memory` (whole-file search, so line-wrapped phrasing is
caught too). No runtime logic and no test was changed by R1 or R2.
