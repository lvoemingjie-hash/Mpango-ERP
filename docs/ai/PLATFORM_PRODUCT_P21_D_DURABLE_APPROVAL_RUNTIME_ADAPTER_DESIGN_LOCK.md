# Platform Product P21-D -- Durable Approval Runtime Adapter Design Lock

**Status:** Discovery + design lock only (P21-D-a). No runtime code, no backend
handlers, no ORM model registration, no frontend UI, no migration, no alembic
change, no tests, and no dependency changes. This document locks the design of
the P21-D runtime adapter BEFORE any P21-D runtime slice may begin, exactly as
P21-A locked the store contract and P21-B locked the schema plan before any
P21-C migration. A future P21-D runtime slice may begin only after explicit CTO
approval (sections 8 and 11).
**Phase:** P21-D-a Durable Approval Runtime Adapter Discovery + Design Lock
**Date:** 2026-06-29
**Base:** `fc9eb40` (platform-dev after P21-C1.1: the additive, reversible,
public-schema-only `020_durable_approval_store` migration is merged; the five
durable tables and their fifteen enum types exist in the public schema; the P21
contract is accepted).
**Depends on:** P10 (identity-only super_admin guard, PlatformAuditEvent,
source-status vocabulary, redact_metadata allowlist), P11 (Platform Admin
Cockpit boundary), P13/P14 (observability plus unavailable_reason /
degraded_reason), P15 (Incident Triage read-only contract), P16 (Worktree
Execution Harness), P17 (Registry and Tenant Lifecycle Contract), P18
(Controlled Platform Actions: action catalog, validate, request, request detail,
request queue, registry source status), P19 (Approval Workflow: approve resolves
to execution_blocked), P20 (Durable Approval Governance: maker-checker, quorum,
execution readiness gate; P20-B is an in-memory / existing-safe non-executing
skeleton with no migration and no database), P21-A (Durable Approval Store
Contract), P21-B (Durable Approval Schema + Test Plan), P21-C0 (migration
readiness gate), P21-C1 / P21-C1.1 (the merged public-schema-only durable
approval store migration + self-contained ephemeral-DB G1 / G2 tests).
**Author:** Codex (Claude worker)
**Relationship to P21-D0:** P21-D0 is a separate, parallel Goose Middleman
shadow pilot that stood up a project-local Review Bus (.review/ mailbox,
recipe, deterministic PowerShell runner). P21-D0 is governance / coordination
infrastructure only; it is NOT the durable approval runtime adapter and it does
not wire any runtime storage. This P21-D-a design lock governs the runtime
adapter only. The two are independent concerns that happen to share the P21-D
phase label; see section 9.

---

## 1. Goal and Non-Goals

### 1.1 Goal

P21-A locked the durable *storage* contract. P21-B turned that contract into an
implementation-ready schema / migration plan. P21-C1 merged the additive,
reversible, public-schema-only migration: the five durable tables
(`durable_approval_requests`, `durable_approval_decisions`,
`durable_approval_audit_events`, `durable_approval_idempotency_keys`,
`durable_approval_retention_jobs`) and their fifteen enum types now exist in the
public schema. P21-C1 created the tables but, per the P21-A migration boundary
(section 8.8), **did not switch runtime storage and did not execute anything**.

Today the running durable approval store is the P20-B in-memory skeleton. It
holds every pending review, partial quorum, in-flight decision, and audit event
in three process-local Python globals. A process restart loses all of it: there
is no restart-safe ledger, no durable audit, and no retention substrate in the
running system, even though the tables to hold them now exist.

P21-D is the **runtime adapter** phase: it wires the existing P20-B store
surface (the four service functions and their response shapes) to the durable
P21-C1 tables so that approval records, decisions, audit events, and idempotency
rows are restart-safe -- while changing no safety rule, executing nothing, and
preserving the P20 API response shapes.

P21-D-a fixes the design of that adapter as a docs-only contract before any
runtime slice may begin:

1. The **discovery** of the exact runtime surface that must be rewired: the
   P20-B in-memory store globals, the four service functions, their sync / async
   split, the four HTTP endpoints, the response models, and the P18 dependency
   boundary (section 3).
2. The **locked adapter design**: how each in-memory operation maps to a durable
   transaction against the P21-C1 tables; the new columns that must be populated
   (`store_version`, `sequence_no`, `metadata_redacted`, `audit_result`,
   `confirm`, `storage_class`); the concurrency model (single-transaction
   atomicity plus `store_version` optimistic locking for the quorum race); the
   API-compatibility rules; the unknown / degraded / read-only fallback; and the
   P18 boundary (section 4).
3. The **slice map** for P21-D: D-a (this docs-only design lock) -> D-1 (ORM
   model registration + adapter implementation, runtime, CTO-gated) -> D-2
   (runtime storage cutover / flag, CTO-gated) -> future (retention jobs,
   export) -- with every runtime slice gated behind explicit CTO approval
   (section 8).
4. The **test plan pointers**, **acceptance criteria**, and **counterexamples**
   scoped to the adapter (sections 6 and 7).

P21-D-a is **discovery + design lock only**. It ships **no runtime code, no
model registration, no migration, no table, no test code**.

The single most important invariant of P21, carried forward unchanged:

> **Approval is not execution, and durability is not execution.** A durable,
> restart-safe, retention-aware store is still not an execution path. A durable
> approval that reaches `approved_execution_blocked` with a satisfied quorum is
> still not executed. It does not run the action, does not mutate any P17
> registry field or lifecycle state, and leaves `execution_allowed == false`.
> Wiring the runtime store to durable tables makes approvals survive a restart;
> it does not make them run.

### 1.2 In scope (design-lock layer only)

- Discover and document the exact P20-B runtime surface that P21-D rewires (the
  three in-memory globals, the four service functions, the sync / async split,
  the four endpoints, the response models, the P18 calls).
- Lock the adapter boundary: which in-memory state maps to which durable table,
  and how each public operation becomes a durable transaction.
- Lock the concurrency model: single-transaction atomicity, `store_version`
  optimistic locking for the quorum race, and the unique constraints that enforce
  distinct-checker and idempotency.
- Lock the new-column population rules (`store_version`, `sequence_no`,
  `metadata_redacted`, `audit_result`, `confirm`, `storage_class`) and the
  audit `audit_result` derivation.
- Lock the API-compatibility rules (P20 response shapes preserved; durability
  metadata is additive; no field removed or renamed; `execution_allowed` /
  `executed` stay false).
- Lock the unknown / degraded / read-only fallback (unknown is never healthy).
- Lock the P18 dependency boundary (the P18 *request* store is out of scope for
  P21-D; only the durable *approval* store is rewired).
- Define the P21-D slice map and the CTO gate that every runtime slice must
  pass.
- Define the test-plan pointers, acceptance criteria, and counterexamples for a
  future P21-D runtime implementation.

### 1.3 Non-goals (explicit, for ALL of P21-D, not only P21-D-a)

- No runtime code, no backend handlers, no ORM model registration, no frontend
  UI, no migration, no alembic change, no test code, and no dependency changes.
- **No runtime storage cutover in P21-D-a.** The running P20-B store stays
  in-memory / existing-safe. A real cutover is a separately approved runtime
  slice (D-1 / D-2), and only after explicit CTO approval (section 8).
- **No execution of any controlled action.** A durable, restart-safe approval
  that reaches quorum and `approved_execution_blocked` still does not execute.
  `execution_allowed` stays `false`, `execution_gate` stays `blocked`, and the
  P18 `executed` flag stays `false`.
- **No automation runner, no execution scheduler, no queue drain.** The durable
  store persists maker-checker decisions and audit events. It is not a hidden
  execution queue. `durable_approval_retention_jobs` is a future retention /
  purge / revalidation sweep driven by a SYSTEM actor; it never dispatches
  execution.
- **No AI agent execution.** This design lock names no AI execution path. The
  future AI Operator Copilot boundary (P21-A section 14) is unchanged.
- **No notification / escalation implementation.**
- No real rollback / restore. `backup.restore_test_request` stays request-only.
- No auth / RBAC / session / tenancy / payment / business-data code or rewrite.
  P21-D reuses the P10 identity-only guard and the P20-B-R1 authenticated-actor
  binding unchanged.
- No P18 request-store change. P21-D rewires the durable *approval* store only.
- No product business code, no touch of product-dev-recovered, no push to any
  product branch, and no merge or push of platform-dev.

## 2. Relationship to Prior Phases

P21-D introduces **no new auth, RBAC, session, observability, data-source,
action, or governance concept**. It is the runtime adapter that connects the
already-accepted P20-B store surface to the already-merged P21-C1 tables.

| Prior phase | What P21-D consumes / extends |
|---|---|
| **P10** identity-only guard, PlatformAuditEvent, redact_metadata allowlist | The adapter runs behind the same P10 guard. Redaction-before-persist reuses the P10 / P18 allowlist verbatim. The P20 route-level outcome audit (`append_audit_entry`) is unchanged. |
| **P13 / P14** unavailable_reason / degraded_reason | The adapter's unknown / degraded / read-only fallback reuses this vocabulary (section 4.6). |
| **P16** Worktree Execution Harness | Untouched. P21-D never invokes the harness and never unlocks execution. |
| **P17** Registry and Tenant Lifecycle | Untouched. A durable approval still references a P18 request that may target a P17 field; the durable store still never mutates the P17 registry. |
| **P18** Controlled Platform Actions | The adapter still calls the P18 helpers (`_item_for`, `_redact_reason`, `_sanitize_text`, `redact_metadata`, `get_stored_request`, `known_action_type`, `_resolve_action_source_status`) to resolve `action_id` / `action_type` / source status / action class. The P18 **request** store stays as-is; P21-D rewires the **approval** store only (section 4.7). |
| **P19** Approval Workflow | Untouched. Approve still resolves to `execution_blocked`. |
| **P20** Durable Approval Governance (P20-B in-memory skeleton) | **P21-D rewires the P20-B store surface to the durable tables.** The four service functions and their response shapes are the contract the adapter must preserve (section 3). |
| **P21-A** Store Contract | The adapter must satisfy every P21-A acceptance criterion and counterexample (no execution; restart-safe; maker-checker; transactional quorum; digest-only idempotency; redaction-before-persistence; no raw secrets / bodies; retention / purge / export; API compatibility). |
| **P21-B** Schema + Test Plan | The adapter targets the exact P21-B / P21-C1 tables, columns, enums, indexes, and constraints. The G1-G14 test plan from P21-B is the implementation target for the future runtime slice. |
| **P21-C1** Migration | The five durable tables already exist in public. P21-D does not add or alter a migration; it reads and writes the existing tables. |

In one line: P18 creates controlled action requests but does not execute; P19
approves / rejects but approval is not execution; P20 adds maker-checker / quorum
in memory; P21-A / B defined and P21-C1 merged the durable tables; **P21-D wires
the P20-B runtime store surface to those tables so approvals survive a restart,
while executing nothing and preserving the P20 API shapes.** Approved durable
approvals remain `approved_execution_blocked` with `execution_allowed == false`
and `executed == false`.

## 3. Discovery: The Runtime Surface P21-D Rewires

This section records the exact, code-grounded surface that any P21-D runtime
slice must preserve. All paths are relative to the repository root; symbol names
are stable, line numbers are intentionally omitted (they drift).

### 3.1 The P20-B in-memory store

File `backend/api/v1/platform/p20/services.py` holds the running durable
approval store in three module-level globals:

- `_STORE: dict[str, _StoredDurableApproval]` -- `approval_id` -> record.
- `_STORE_BY_CREATE_KEY: dict[str, str]` -- SHA-256 digest of the create
  `idempotency_key` -> `approval_id`. The raw key is never stored.
- `_AUDIT_LOG: list[DurableApprovalAuditEvent]` -- flat append-only list of
  audit events.

The records are plain `__slots__` Python objects (`_StoredDurableApproval`,
`_CheckerDecision`), **not ORM models**. There is no database table, no
migration, and no session. `reset_store()` and `audit_log()` are test seams.

The store exposes four public operations:

| Operation | Signature shape | Async? | Uses `db`? | State it touches |
|---|---|---|---|---|
| `create_durable_approval(...)` | keyword-only; resolves P18 context | **async** | **yes** (`AsyncSession`) | `_STORE`, `_STORE_BY_CREATE_KEY`, `_AUDIT_LOG` |
| `submit_decision(approval_id, ...)` | keyword args after id | **sync** | **no** | `_STORE`, `_AUDIT_LOG` |
| `read_durable_approval(approval_id)` | id only | **sync** | **no** | `_STORE` (read) |
| `list_durable_approvals(limit, offset, status, action_type, tenant_id)` | filters | **sync** | **no** | `_STORE` (read) |

**Critical design fact:** `create_durable_approval` is already async and already
receives `db`, because it resolves the P18 source status. `submit_decision`,
`read_durable_approval`, and `list_durable_approvals` are synchronous and do not
receive `db`, because they are pure in-memory operations today. A durable
adapter must perform database I/O on every operation, so these three must become
**async and receive `db`** (section 4.5). That is a service-layer signature
change; it is the single unavoidable runtime ripple of P21-D, and it is contained
to `services.py` + `routes.py` (section 3.3).

Safety logic already enforced in `services.py` that the adapter must preserve
exactly:

- **Identity binding (P20-B-R1):** the maker / checker is the authenticated
  identity-only super_admin actor. A client-supplied `maker` / `approver_id` is
  accepted only as an assertion that must equal the authenticated actor;
  otherwise it is an identity spoof and is denied. No system / operator-secret
  fallback may be a maker or checker.
- **Maker-checker:** `checker == maker` is denied and never persisted.
- **Distinct checkers:** each checker records at most one decision per approval;
  a repeat with the same decision is idempotent, a flip is a conflict.
- **Quorum:** write / write_request floor of two distinct approve checkers
  (excluding the maker); read floor of one. `quorum_met` becomes true only when
  the distinct approve count reaches the floor and no reject is recorded.
- **Reject is final:** any single reject moves the approval to `rejected`
  (terminal); a later approve is denied.
- **Source honesty:** an approve requires `validation_status == "valid"` (an
  available P18 source). An unknown / unavailable source is stored verbatim and
  blocks approve, never fabricated as available.
- **Redaction:** reason / comment / metadata pass through the P18 redaction
  (`_redact_reason`, `redact_metadata`, `_sanitize_text`) before any store write
  or audit emit.
- **Digest-only idempotency:** the raw `idempotency_key` is hashed at the
  boundary (`_digest`); only the SHA-256 digest is stored / compared / echoed.
- **No execution:** `execution_allowed` and `executed` are always `false`;
  `execution_gate` is always `"blocked"`; `storage` is `"memory"`.

### 3.2 The response models (the API-compatibility contract)

File `backend/api/v1/platform/p20/schemas.py` defines the response shapes the
adapter MUST preserve (P21-A section 9):

- `DurableApprovalRecord` -- the uniform create / read / decision response. Notable
  fields: `approval_id`, `action_id`, `tenant_id`, `action_type`,
  `action_class`, `state`, `maker`, `maker_at`, `checkers` (list of
  `CheckerDecisionSummary`), `quorum_required`, `quorum_met`, `decision`,
  `reason`, `request_digest`, `idempotency_key_digest`, `expires_at`,
  `durable_retain_until`, `execution_allowed` (always false), `execution_gate`
  (always "blocked"), `redaction_applied` (always true), `storage` ("memory"
  today), `retention_class`, `validation_status`, `superseded_by`,
  `previous_state`, `audit_event_id`, `correlation_id`, `source_status`,
  `result`, `message`, `executed` (always false), `created_at`, `updated_at`.
  `extra="forbid"` on every model.
- `DurableApprovalQueue` -- `items`, `total`, `limit`, `offset`, `storage`,
  `executed` (false).
- `CheckerDecisionSummary` -- `checker_id`, `decided_at`, `decision`,
  `reason_redacted`, `audit_event_id`.
- `DurableApprovalAuditEvent` -- the in-memory audit payload (not directly an
  HTTP response, but the shape the adapter writes to the audit table).

The closed vocabularies (states, decision types, action classes, identity
contexts, actor roles, source statuses, validation statuses, execution gates,
retention classes, event types) are defined in `schemas.py` and must remain
stable. The future AI Operator Copilot / retention fields (`superseded_by`,
`retention_class`, `validation_status`) are already present and simply become
populated rather than static.

### 3.3 The HTTP endpoints

File `backend/api/v1/platform/p20/routes.py` exposes four endpoints, all behind
`require_platform_operator_with_p20_audit` (the P10 identity-only guard plus a
best-effort access-denied audit) and all already injected with
`db: AsyncSession = Depends(get_db)`:

- `POST /api/v1/platform/p20/durable-approvals` ->
  `create_durable_approval_route` -> `await services.create_durable_approval(...)`.
- `GET /api/v1/platform/p20/durable-approvals` ->
  `list_durable_approvals_route` -> `services.list_durable_approvals(...)` (sync;
  no `await`; `db` available but unused by the service).
- `GET /api/v1/platform/p20/durable-approvals/{approval_id}` ->
  `read_durable_approval_route` -> `services.read_durable_approval(...)` (sync).
- `POST /api/v1/platform/p20/durable-approvals/{approval_id}/decisions` ->
  `submit_decision_route` -> `services.submit_decision(...)` (sync).

Every route also calls `_write_outcome_audit` (P14 platform audit via
`append_audit_entry`) which is independent of the durable audit log and is
unchanged by P21-D. The route layer is where the sync -> async ripple lands:
`list` / `read` / `decision` add `db=db` to the service call and `await` it. No
response model changes; no new endpoint; no path change.

### 3.4 The durable target (P21-C1)

The five merged public-schema tables (file
`backend/alembic/versions/020_durable_approval_store.py`) and their enum types /
indexes / uniqueness constraints are the adapter's target. The adapter writes no
new migration and alters no existing object. Key durable columns that have **no
direct in-memory counterpart** and that the adapter must therefore populate
(section 4.4):

- `durable_approval_requests.store_version` (int, default 1) -- optimistic lock;
  bumped on every state transition. P20-B has no versioning.
- `durable_approval_requests.storage_class` (enum durable | existing_safe |
  memory) -- the adapter writes `durable`.
- `durable_approval_audit_events.sequence_no` (bigint) -- monotonic per-approval
  audit sequence. P20-B's `_AUDIT_LOG` is a flat unnumbered list.
- `durable_approval_audit_events.audit_result` (enum) -- the durable audit
  outcome. P20-B's `DurableApprovalAuditEvent` has no result field; the adapter
  derives it from the event type / transition outcome.
- `durable_approval_decisions.confirm` (bool) -- the explicit confirmation token
  persisted per decision.
- `metadata_redacted` (on requests, decisions, audit events) -- redacted metadata
  persisted. P20-B redacts metadata for audit but does not store it.
- `durable_approval_idempotency_keys` with `scope_key` (open | decide),
  `scope_id`, `payload_digest`, `result_ref` -- a structured idempotency table
  that generalizes P20-B's two maps (`_STORE_BY_CREATE_KEY` for open;
  per-checker `decision_digest` for decide).

## 4. Locked Adapter Design

This is the design P21-D-a freezes. A future P21-D runtime slice implements
against this design and may not change it without a new design-lock revision
accepted by the CTO.

### 4.1 Boundary

The adapter replaces the three in-memory globals with reads and writes against
the P21-C1 tables, **behind the same four public service functions**. No new
public operation is introduced. The route layer, the response models, the guard,
and the P18 helpers are preserved.

| In-memory global | Durable target |
|---|---|
| `_STORE[approval_id]` (`_StoredDurableApproval`) | `durable_approval_requests` (+ `durable_approval_decisions` for the checkers log) |
| `_STORE_BY_CREATE_KEY[create_digest]` | `durable_approval_idempotency_keys` (`scope_key = open`) |
| per-checker `decision_digest` dedup | `durable_approval_idempotency_keys` (`scope_key = decide`) + `durable_approval_decisions` uniqueness |
| `_AUDIT_LOG` | `durable_approval_audit_events` |
| (none today) | `durable_approval_retention_jobs` -- future, not populated by the base adapter |

### 4.2 Operation mapping

- **create** (open): one transaction inserts the `durable_approval_requests` row
  at `pending_review` (`execution_allowed = false`, `execution_gate = blocked`,
  `executed = false`, `redaction_applied = true`, `storage_class = durable`,
  `store_version = 1`), the `approval_opened` audit event (`sequence_no = 1`),
  and the `open` idempotency row (`payload_digest` from the canonical create
  envelope). Create idempotency: a matching `payload_digest` returns the prior
  `result_ref` (idempotent); a mismatch is a conflict. All P20-B create-time
  denials (no authenticated actor, identity spoof, missing reason / key /
  confirm, past `expires_at`, unresolvable P18 reference) remain denials and
  emit an `approval_denied` audit event; they persist no request row.
- **decide** (approve / reject): one transaction reads the request row (with
  locking, 4.3), enforces maker-checker / distinct-checker / reject-final /
  source-honesty exactly as P20-B does, inserts the `durable_approval_decisions`
  row (`confirm`, `decision_digest`, redacted reason / metadata, linked
  `audit_event_id`), inserts the `decide` idempotency row, recomputes `quorum_met`
  from the committed distinct-approve set, and on a state transition bumps
  `store_version`, sets `previous_state`, updates `state` / `decision` /
  `updated_at` / `last_audit_event_id`, and appends the
  `approval_decision_recorded` event (plus `approval_quorum_met` or
  `approval_rejected` as appropriate). The decision audit `sequence_no` is the
  prior max + 1 for that `approval_id`. A deny / duplicate / conflict still
  emits an `approval_denied` (or idempotent no-op) audit event and commits no
  decision row.
- **read**: a read-only transaction selects the request row, its decisions
  (ordered), and its audit events; maps them to `DurableApprovalRecord`. Emits
  an `approval_read` audit event (redacted), matching the P20-A
  read-is-audited rule. `execution_allowed` / `executed` stay false.
- **list**: a read-only filtered query over `durable_approval_requests` (filters:
  `state`, `action_type`, `tenant_id`; pagination `limit` / `offset`), mapped to
  `DurableApprovalQueue`. `executed` stays false.

### 4.3 Concurrency and atomicity (the quorum race, P21-A 5.4 / 5.7 / C8)

- Every create and every decide is a **single transaction**: the request row
  mutation, the decision row, the idempotency row(s), and the audit event(s)
  commit atomically or not at all. There is no partial quorum, no orphaned
  decision, and no orphaned audit event after a rollback.
- The decide transaction enforces the transition with **`store_version`
  optimistic locking**: the `UPDATE ... WHERE approval_id = ? AND store_version =
  ?` advances only if the version is unchanged; a stale write (a concurrent
  conflicting decision) affects zero rows and is retried, denied, or resolved
  idempotent. Exactly one outcome commits; there is no split-brain quorum
  (P21-A C8, test T7).
- The unique constraints from P21-B / P21-C1 backstop the optimistic lock:
  `durable_approval_decisions(approval_id, checker_actor_id)` enforces
  distinct-checker; `durable_approval_decisions(approval_id,
  idempotency_key_digest)` enforces per-approval decide idempotency;
  `durable_approval_idempotency_keys(scope_key, scope_id,
  idempotency_key_digest)` enforces create / decide idempotency. The
  `uq_requests_active_digest` partial unique index drives supersession.

### 4.4 New-column population (locked)

- `store_version`: 1 at create; bumped by exactly 1 on every state transition.
- `sequence_no`: per-`approval_id` monotonic audit sequence; computed inside the
  transaction from the current max for that approval.
- `storage_class`: `durable` for rows written by the adapter.
- `audit_result`: derived from the transition outcome (for example
  `approval_opened` -> recorded; `approval_quorum_met` -> approved;
  `approval_rejected` -> rejected; `approval_denied` -> denied). The exact enum
  mapping is fixed in the future runtime slice against the P21-C1
  `_audit_result` value set, and must not lose information relative to the
  in-memory event.
- `confirm`: the explicit decision confirmation token, persisted verbatim (it is
  already a boolean the caller supplied; not a secret).
- `metadata_redacted`: the P10 / P18-redacted metadata, persisted (the raw
  metadata is never persisted).

### 4.5 API compatibility (P21-A section 9)

- The four `DurableApproval*` response models are unchanged. No field is removed
  or renamed. `extra="forbid"` is preserved.
- `execution_allowed` is always `false`; `executed` is always `false`;
  `execution_gate` is always `"blocked"`.
- Durability is **additive**: the response `storage` value moves from `"memory"`
  to `"durable"` at cutover, and the adapter MAY add `storage_class: durable` and
  `restart_safe: true` as additive fields. No existing P20 field is removed or
  renamed. The P20-C read-only frontend needs no semantic change; if
  restart-safety badges are surfaced they are display-only.
- The service-layer sync -> async change on `submit_decision` /
  `read_durable_approval` / `list_durable_approvals` is internal; the HTTP
  request / response contract is unchanged.

### 4.6 Unknown / degraded / read-only fallback (P21-A 3.6)

Unknown is never healthy. If the adapter cannot confirm an approval's state,
quorum, or validation after a restart or a partial store outage, it:

- refuses to advance the approval to `approved_execution_blocked`;
- serves reads with a `degraded` / `unknown` badge and an `unavailable_reason`
  (P13 / P14 vocabulary);
- denies writes with `unavailable_reason = store_unknown`.

The adapter never fabricates an available source, a met quorum, or a valid
state. A read-only / degraded path is preferred over a fabricated healthy one.

### 4.7 P18 dependency boundary (locked)

P21-D rewires the durable **approval** store only. The P18 **request** store
(`get_stored_request`, `known_action_type`, `_resolve_action_source_status`,
`_item_for`) and the P18 redaction helpers (`_redact_reason`, `_sanitize_text`,
`redact_metadata`) are consumed unchanged. `action_id` / `action_type` / source
status / action class resolution is identical to P20-B. If a future phase moves
the P18 request store to its own durable substrate, that is a separate,
separately approved phase outside P21-D.

## 5. Relationship to the P21-D0 Goose Middleman (boundary)

P21-D0 (branch `codex/platform-p21d0-goose-middleman-config-2026-06-29`, status
`shadow_complete`) stood up a project-local **Review Bus**: a `.review/` mailbox
(projects context, tasks, outbox, inbox, audit, state), a Goose recipe, and a
deterministic PowerShell runner. Its authority model is explicit: Codex CTO is
the only final gate; Goose is a low-privilege dispatcher / recorder that never
touches runtime code, never merges or pushes, and never writes an approval
marker; Claude implements approved tasks.

**Boundary statement:** the Goose middleman is governance / coordination
infrastructure. It is NOT the durable approval runtime adapter and it wires no
runtime storage. This P21-D-a design lock governs the runtime adapter only.
P21-D0's outbox handoff explicitly says "SHADOW ONLY -- DO NOT START P21-D1" and
"Claude should NOT begin any implementation work. Await explicit Codex/user
signal before proceeding." This design lock honors that: it is a docs-only design
lock (not P21-D1 implementation), and it reaffirms in section 8 that no P21-D
runtime slice may begin without explicit CTO approval.

## 6. Test Plan Pointers (future runtime slices; none written in P21-D-a)

A future P21-D runtime implementation must satisfy the P21-B G1-G14 plan and the
P21-A T1-T11 plan, scoped to the adapter. The adapter-specific emphasis:

- **Restart persistence (P21-A T3):** a pending review, partial quorum, recorded
  decision, audit event, and idempotency row all survive a simulated process
  restart; `state` and `quorum_met` are unchanged.
- **Idempotency digest (P21-A T4):** a replayed create / decision with a matching
  `payload_digest` is idempotent; the raw key is never stored; only the digest is
  present in `durable_approval_idempotency_keys`.
- **Redaction persistence (P21-A T5):** a content scan of every persisted reason,
  comment, metadata, and audit `reason_redacted` against the P10 / P18 allowlist
  returns clean; `redaction_applied == true` everywhere.
- **Maker-checker transaction (P21-A T6):** a self-decision is rejected and never
  persisted; a second distinct checker is required for write quorum; the
  decision + state + audit + idempotency commit atomically.
- **Quorum race (P21-A T7):** concurrent conflicting decisions from distinct
  checkers serialize to exactly one outcome via `store_version`; no split-brain
  quorum; a stale write is rejected.
- **No-execution (P21-A T9):** a quorum-met approval reaches
  `approved_execution_blocked` and leaves `execution_allowed == false`,
  `execution_gate == blocked`, and P18 `executed == false`.
- **No-tenant-mutation (P21-A T10):** no P17 registry field, lifecycle, flag, or
  tenant business record is read or written; `tenant_id` is a scoped id only.
- **API compatibility:** the P20 response shapes are byte-compatible (durability
  metadata additive only); the P20-C frontend needs no semantic change.
- **GitNexus scope (P21-A T11):** `detect_changes` for the adapter change is
  scoped to the platform durable-approval surface; no product, tenant, payment,
  auth, or RBAC process is affected.

## 7. Acceptance Criteria

A future P21-D runtime slice is accepted only when all of the following hold
(P21-D-a itself is accepted when the docs-only criteria in section 11 hold):

1. **The adapter never executes.** A quorum-met approval reaches
   `approved_execution_blocked` and leaves `execution_allowed == false`,
   `execution_gate == blocked`, and P18 `executed == false`.
2. **The store is restart-safe.** A pending review, partial quorum, decision,
   audit event, and idempotency row survive a restart; `state` and `quorum_met`
   are unchanged; `sequence_no` ordering is preserved.
3. **Maker-checker separation holds in the durable store.** No approval reaches
   `approved_execution_blocked` with the maker among its checkers; a
   self-decision is rejected, never persisted, and audited.
4. **Quorum is transactionally consistent.** A write / write_request approval
   reaches `approved_execution_blocked` only with at least two distinct approve
   checkers (none the maker) committed in one transaction; `store_version`
   rejects stale writes.
5. **Distinct checkers only.** The `(approval_id, checker_actor_id)` uniqueness
   holds; a second decision from the same checker is idempotent or a conflict.
6. **The four P20 service functions and their response shapes are preserved.**
   No field is removed or renamed; `extra="forbid"` holds; durability metadata
   is additive; the P20-C frontend needs no semantic change.
7. **The sync -> async ripple is contained** to `services.py` + `routes.py`; no
   other runtime module changes its public contract.
8. **The new columns are populated correctly:** `store_version` bumps per
   transition; `sequence_no` is monotonic per approval; `storage_class = durable`;
   `audit_result` is derived without information loss; `confirm` and
   `metadata_redacted` are persisted; raw metadata is never persisted.
9. **The P18 boundary holds:** `action_id` / `action_type` / source status /
   action class resolution is identical to P20-B; the P18 request store is
   unchanged.
10. **Unknown is never healthy:** an unreadable / partially available store
    serves a degraded / unknown badge and denies writes with
    `unavailable_reason = store_unknown`; it never fabricates a healthy state.
11. **Digest-only idempotency and redaction-before-persistence hold** (P21-A
    criteria 10-13).
12. **The migration boundary holds:** no new migration, no existing object
    altered; the adapter reads and writes only the merged P21-C1 tables in the
    public schema.

## 8. P21-D Slice Map and the CTO Gate

P21-D is decomposed into gated slices. **No runtime slice may begin without
explicit CTO approval.** This restates and honors the P21-D0 "await explicit
Codex/user signal" instruction.

- **P21-D-a (this document): discovery + design lock.** Docs-only. Locks the
  adapter design. No runtime code, no migration, no model registration, no
  execution, no storage switch.
- **P21-D-1 (future, CTO-gated): ORM model registration + adapter
  implementation.** Runtime. Registers `PublicBaseModel` ORM models for the five
  durable tables (read/write, public schema), implements the adapter behind the
  four service functions, populates the new columns, and adds the G1-G14 / T1-T11
  adapter tests against an ephemeral DB. **Still no storage cutover and no
  execution:** the running store may remain in-memory behind a flag until D-2.
- **P21-D-2 (future, CTO-gated): runtime storage cutover.** Flips the running
  store from in-memory to the durable adapter (feature flag or wiring change).
  Restart-safety becomes live. No execution; no tenant mutation; API-compatible.
- **P21-D-future (future, separately approved): retention jobs, redacted export,
  supersession sweeps, AI Operator Copilot trace.** Each separately gated.

A runtime storage cutover is the "further separately approved step" named in the
P21-A migration boundary (section 8.8). P21-D-a does not perform it and does not
authorize it; only an explicit CTO approval recorded in `decision-register/` and
a P21-D-1 / P21-D-2 slice may.

## 9. Counterexamples (a future runtime slice must reject these)

1. **An approved action executing.** A quorum-met approve that runs, schedules,
   dispatches, or applies the P18 action, or sets `execution_allowed == true` --
   rejected.
2. **A storage cutover without CTO approval.** Flipping the running P20-B store
   to the durable adapter outside an approved P21-D-2 slice -- rejected.
3. **A sync service left after cutover.** `submit_decision` / `read` / `list`
   remaining synchronous (no DB I/O) after the adapter is live, so writes are
   lost on restart -- rejected.
4. **A split-brain quorum.** Two concurrent conflicting decisions both committing
   because `store_version` was not checked -- rejected; exactly one commits.
5. **A raw idempotency key or raw metadata persisted.** Any column holding the
   plaintext key, raw metadata, or raw reason -- rejected (contract violation).
6. **A self-decision persisted.** A `durable_approval_decisions` row with
   `checker_actor_id == maker_actor_id` -- rejected and audited.
7. **A public-API field removed or renamed.** Any change to the four
   `DurableApproval*` response shapes that breaks P20 compatibility -- rejected.
8. **An unknown store fabricated healthy.** Serving `approved_execution_blocked`
   or `quorum_met == true` when the store cannot confirm state -- rejected.
9. **The adapter touching the P18 request store or any P17 / tenant business
   table.** -- rejected; P21-D rewires the approval store only.
10. **A new migration or an altered existing object.** -- rejected; the adapter
    reads and writes the merged P21-C1 tables only.

## 10. Docs-Only and Design-Lock-Only Statement

P21-D-a is **docs-only and design-lock-only**. It ships:

- `docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md`
  -- this design lock.
- `docs/ai/README.md` -- the P21-D entry in the Platform Product Track read
  order, with its gating paragraph.
- `ai-ledger/platform/2026-06-29_p21da_discovery_design_lock.md` -- the ledger.

There is **no runtime code, no backend handler, no ORM model registration, no
frontend, no migration, no alembic change, no table, no test code, and no
dependency change** in P21-D-a. P21-D-a locks the runtime adapter design only; it
does not execute, persist (beyond defining the design), migrate, switch storage,
invoke, or implement any approval, action, store, or execution path. **Approval
is not execution, and durability is not execution.** A runtime storage cutover is
reserved for a separately approved P21-D-2 slice and must run through no execution
path. **P21-D-1 is not started.**

## 11. Docs-Only Acceptance Criteria (P21-D-a)

Section 7 lists the acceptance criteria for a future P21-D **runtime** slice.
P21-D-a is a docs-only design lock, so it is accepted on a separate, narrower
basis -- all of the following must hold:

1. **Three-file scope.** Only
   `docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md`
   (new), `docs/ai/README.md` (P21-D read-order entry + gating paragraph), and
   `ai-ledger/platform/2026-06-29_p21da_discovery_design_lock.md`. No backend,
   frontend, alembic, test, package, lockfile, baseline, or product path is
   touched.
2. **No runtime artifact.** No runtime code, no backend handler, no ORM model
   registration, no migration, no alembic change, no table, no test code, and no
   dependency change.
3. **No execution and no storage switch.** No controlled action is run; the
   running P20-B store stays in-memory / existing-safe; no runtime cutover is
   introduced or authorized (a cutover is reserved for a separately approved
   P21-D-2 slice; section 8).
4. **Design locked, not implemented.** Section 4 records the frozen adapter
   design (boundary, operation mapping, concurrency, new-column population, API
   compatibility, unknown / degraded fallback, P18 boundary) that a future
   runtime slice must implement against. **P21-D-1 is not started.**
5. **CTO gate reaffirmed.** No P21-D runtime slice may begin without explicit
   CTO approval recorded in `decision-register/` (section 8), honoring the
   P21-D0 "await explicit signal" instruction.
6. **Artifact hygiene.** `git diff --check` is clean; the three files are pure
   ASCII (0 non-ASCII hits, per the platform convention); no self-referential
   commit SHA is embedded (short SHAs / descriptions only); and `detect-secrets`
   against the configured baseline reports no new secret material at commit.

Approval is not execution, and durability is not execution. P21-D-1 is not
started.
