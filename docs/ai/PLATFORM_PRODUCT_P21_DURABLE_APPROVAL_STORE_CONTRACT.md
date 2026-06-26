# Platform Product P21 -- Durable Approval Store Contract

**Status:** Contract only (P21-A). No runtime code, no backend handlers, no frontend
UI, no migrations, no alembic changes, no tests, and no dependency changes. Accepted by
the CTO before any P21-B schema/migration plan may begin.
**Phase:** P21-A Durable Approval Store Contract
**Date:** 2026-06-26
**Base:** `82ee1c1` (origin/platform-dev -- P20 durable approval governance closeout:
P20-A contract, P20-B in-memory non-executing backend skeleton, P20-C read-only
frontend console, and P20-D master closeout all merged; P20_DURABLE_APPROVAL_GOVERNANCE_READY)
**Depends on:** P10 (identity-only super_admin guard, PlatformAuditEvent, source-status
vocabulary, redact_metadata allowlist), P11 (Platform Admin Cockpit boundary), P12
(Support Console support-safe subset), P13/P14 (Operations Observability plus
unavailable_reason / degraded_reason), P15 (Incident Triage read-only contract), P16
(Worktree Execution Harness), P17 (Platform Registry and Tenant Lifecycle Contract), P18
(Controlled Platform Actions Contract: action catalog, validate, request, request detail,
request queue, registry source status), P19 (Controlled Action Approval Workflow
Contract: approve resolves to execution_blocked; in-memory store only), P20 (Durable
Approval Governance Contract: persistent record shape, dual-control policy, execution
readiness gate, durable audit, state machine; P20-B is an in-memory / existing-safe
non-executing skeleton with no migration and no database).
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P20 delivered durable approval *governance* -- the record shape, dual-control policy,
execution readiness gate, audit contract, and state machine -- and a P20-B *in-memory,
non-executing* backend skeleton plus a P20-C read-only frontend console. P20-B stores
approval records and decisions in process memory (or an existing-safe adapter) only. A
process restart loses every pending review, every partial quorum, and every in-flight
decision; there is no restart-safe ledger, no durable audit, and no retention / purge
substrate. P20 deliberately left durable persistence open: P20-B migrations were
default-denied and the store is in-memory / existing-safe only.

P21 is the **durable approval store** layer. It does not execute anything. It defines the
production-grade persistence contract -- the tables / logical storage records,
restart-safe consistency, digest-only idempotency, redaction-before-persistence, durable
append-only audit, retention / purge / export, the migration boundary, and API
compatibility -- so that any future durable backend (P21-B plan, P21-C migration) is
bounded before a single table is created.

P21-A fixes the boundary before any P21 implementation may begin:

1. The **durable storage model contract**: the logical tables
   (`durable_approval_requests`, `durable_approval_decisions`,
   `durable_approval_audit_events`, `durable_approval_idempotency_keys`,
   `durable_approval_retention_jobs`), required fields, nullable rules, enum values,
   indexes, uniqueness constraints, and foreign-key-like relationships.
2. The **security and redaction contract**: the raw idempotency key is never stored
   (digest only); reason / comment / metadata are redacted before persistence; no raw
   DSN, host, port, token, password, cookie, secret, or auth header is persisted;
   `tenant_id` is a scoped identifier only, never business payload; audit events store no
   raw request body.
3. The **maker-checker / quorum consistency contract** for the durable store: maker and
   checker are both bound to an authenticated identity-only super_admin actor; the maker
   cannot approve / reject its own request; checkers are distinct identities only; the
   quorum count is transactionally consistent; duplicate decisions are idempotent only on
   payload-digest match; conflicting decisions are rejected.
4. The **state machine contract** for durable storage: the seven P20 states with
   restart-safe persistence, allowed and forbidden transitions, and the explicit rule
   that no transition executes the underlying P18 action.
5. The **retention / purge / export contract** for the durable store.
6. The **migration boundary**: what a future P21-C migration may create, and the gates
   any such migration must satisfy; P21-A creates nothing now.
7. The **API compatibility contract**: the future durable backend preserves P20 API
   response shapes unless a new versioned contract is approved.

P21-A is **contract only**. It ships **no runtime code, no migration, no table**.

The single most important invariant of P21, repeated throughout this document:

> **Approval is not execution, and durability is not execution.** A durable,
> restart-safe, retention-aware store is still not an execution path. A durable approval
> that reaches `approved_execution_blocked` with a satisfied quorum is still not executed.
> It does not run the action, does not mutate any P17 registry field or lifecycle state,
> and leaves `execution_allowed == false`. There is no path in P21 from a persisted
> approval to execution. Durability makes approvals survive a restart; it does not make
> them run.

### 1.2 In scope (contract layer)

- Define the durable storage model contract: the five logical tables / records, required
  fields, nullable rules, enum values, indexes, uniqueness constraints,
  foreign-key-like relationships, and restart-safe consistency rules.
- Define the security and redaction contract for persistence (digest-only idempotency,
  redaction-before-persistence, the never-persisted list, `tenant_id` scope, no raw
  request bodies in audit).
- Define the maker-checker / quorum consistency contract for the durable store
  (transactional quorum, distinct checkers, idempotent-on-digest decisions, conflict
  rejection).
- Define the durable state machine with restart-safe persistence semantics and the
  no-execution rule.
- Define the retention / purge / export contract for the durable store.
- Define the migration boundary and the gates a future P21-C migration must satisfy.
- Define the API compatibility contract.
- Define the test plan, acceptance criteria, and counterexamples.
- Define the P21-B entry gate (schema / migration plan and tests only; no production
  migration, no storage switch).
- Define the future AI Operator Copilot boundary against this substrate.

### 1.3 Non-goals (explicit, for ALL of P21, not only P21-A)

- No runtime code, no backend handlers, no frontend UI, no migrations, no alembic
  changes, no test code, and no dependency changes.
- **No production migration and no real durable backend switch in P21-A or P21-B.**
  P21-A defines the contract only. P21-B may define the schema / migration plan and tests
  only. A real migration that creates any table is reserved for P21-C and only after
  explicit CTO approval (section 8, section 13).
- No auth / RBAC / session / tenancy / payment / business-data code or rewrite. P21
  reuses the P10 identity-only guard conceptually; it defines no new auth transport.
- **No execution of any controlled action.** A durable, restart-safe approval that
  reaches quorum and `approved_execution_blocked` still does not execute.
  `execution_allowed` stays `false`, `execution_gate` stays `blocked`, and the P18
  `executed` flag stays `false`.
- **No automation runner, no execution scheduler, no queue drain.** The durable store
  persists maker-checker decisions and audit events. It is not a hidden execution queue.
  `durable_approval_retention_jobs` is a future retention / purge / revalidation sweep
  queue driven by a SYSTEM actor; it never dispatches execution.
- **No AI agent execution.** P21-A names a future AI Operator Copilot boundary
  (section 14). It does not implement, run, or grant any AI agent the power to execute.
- **No notification / escalation implementation.** P21-A may name notification as a
  future contract; it does not implement outbound channels, templates, or recipients.
- No real rollback / restore. `backup.restore_test_request` stays request-only.
- No product business code, no touch of product-dev-recovered, no push to any product
  branch, and no merge or push of platform-dev.

## 2. Relationship to Prior Phases (P10 through P20)

P21 introduces **no new auth, RBAC, session, observability, data-source, action, or
governance concepts**. It is the durable *storage* layer that P20 left open (P20-B is
in-memory / existing-safe; no migration; no real durable backend).

| Prior phase | What P21 consumes / extends |
|---|---|
| **P10** identity-only guard, PlatformAuditEvent, source-status vocabulary, redact_metadata allowlist | The durable store runs behind the P10 identity-only super_admin guard. The durable audit event table is a persisted specialization of PlatformAuditEvent. The P10 redact_metadata allowlist is applied to every persisted reason, comment, and metadata value before it touches durable storage. |
| **P11 / P12 / P13 / P14 / P15** Cockpit, Support Console, Observability, Incident Triage | P21 changes none of these surfaces. A future approved phase may surface durable-storage badges (restart-safe, retention class); P21-A adds no cockpit or console controls. |
| **P16** Worktree Execution Harness | Any future execution must run through the P16 governed harness. P21-A defines the durable store; it never invokes the harness and never unlocks execution. |
| **P17** Registry and Tenant Lifecycle | A durable approval wraps a P18 request that targets a P17 field or lifecycle transition. The durable store persists the *decision about* that request; it never mutates the P17 registry. |
| **P18** Controlled Platform Actions | P18 creates controlled action *requests* but does not execute them. A durable approval references a recorded P18 `action_id` (`result == accepted`, `executed == false`). The durable store never flips the P18 `executed` flag. P18 `source_status` remains a hard precondition for quorum and durable re-validation. |
| **P19** Approval Workflow | P19 *approves / rejects* but approval is not execution; every P19 approval resolves to `execution_blocked`. P21 persists the P19 / P20 approval lifecycle durably; it does not change P19's "approve is not execute" rule. |
| **P20** Durable Approval Governance | P20 adds maker-checker / quorum but its store is **in-memory / existing-safe** (P20-B: no migration, no database). **P21 defines durable storage for P20 records.** The P21 logical tables materialize the P20 `ApprovalRecord`, `ApprovalDecision`, audit event, idempotency, and retention shapes into a restart-safe, retention-aware substrate. **Approved durable approvals remain `approved_execution_blocked` with `execution_allowed == false` and `executed == false`.** P21 weakens no P20 safety rule; it only makes the record survive a restart. |

In one line, restated for the record: P18 creates controlled action requests but does not
execute; P19 approves / rejects but approval is not execution; P20 adds maker-checker /
quorum but is in-memory; P21 defines durable storage for P20 records; approved durable
approvals remain `approved_execution_blocked` with `execution_allowed == false` and
`executed == false`.

## 3. Proposed Durable Data Model

P21-A defines the durable store contract as **logical storage records**. No table is
created, migrated, or implemented in P21-A. All records are `extra = forbid` (no
undeclared columns, no leaks). All timestamps are UTC ISO-8601 (`timestamptz`). All
`reason`, `comment`, and `metadata` values pass through the P10 `redact_metadata`
allowlist before persistence (section 4). The store is append-mostly for audit and
state-journaled for the request record: a transition updates `state`, `previous_state`,
`store_version`, `quorum_met`, `decision`, `validation_status`, `last_audit_event_id`,
and `updated_at` only. Every write is transactional so that the quorum count, the
decisions log, the audit event, and the idempotency row land together or not at all
(section 5).

### 3.1 durable_approval_requests

The persisted durable approval record (the P20 `ApprovalRecord`, made restart-safe). This
is the single source of truth for a durable approval's state.

```text
durable_approval_requests {
  approval_id            : uuid        -- PK. required. Unique per durable approval.
  action_id              : uuid        -- required. FK-like -> P18 ActionRequestResponse
                                        -- (P18 result == accepted, executed == false).
                                        -- Never mutated by the durable store.
  tenant_id              : uuid        -- nullable. Scoped identifier only (section 4).
                                        -- Null for platform-wide actions. Never a
                                        -- business payload and never an FK into a
                                        -- product business table.
  action_type            : enum        -- required. A P18 action_type.
  action_class           : enum        -- required. read | write | write_request. Maps
                                        -- the P18 classification; governs quorum (5.5).
  state                  : enum        -- required. pending_review |
                                        -- approved_execution_blocked | rejected |
                                        -- expired | cancelled | superseded |
                                        -- failed_validation (section 6).
  maker                  : varchar     -- required. Identity-only super_admin actor id
                                        -- that opened the request. Never a checker.
  maker_at               : timestamptz -- required. UTC ISO-8601.
  quorum_required        : int         -- required. Floor per action_class (5.5): write
                                        -- and write_request >= 2; read >= 1 if opened.
  quorum_met             : bool        -- required. DEFAULT false. True only when the
                                        -- distinct approve checkers (none the maker) >=
                                        -- quorum_required and no reject is recorded.
  decision               : enum        -- nullable. approve | reject | null. Null until a
                                        -- terminal decision.
  reason                 : text        -- required. REDACTED before persist (section 4).
  request_digest         : char(64)    -- required. SHA-256 of the canonical request
                                        -- envelope. Drives supersession and dedup.
  idempotency_key_digest : char(64)    -- required. SHA-256 of the client idempotency
                                        -- key. The RAW key is NEVER stored (4.2).
  expires_at             : timestamptz -- required. UTC ISO-8601; MUST be in the future
                                        -- at creation. The decision-window TTL.
  durable_retain_until   : timestamptz -- required. UTC ISO-8601. Retention TTL after the
                                        -- record reaches a terminal state.
  execution_allowed      : bool        -- required. DEFAULT false. Always false in P21.
  execution_gate         : enum        -- required. blocked | not_authorized. DEFAULT
                                        -- blocked. The only value reachable in P21 is
                                        -- blocked.
  redaction_applied      : bool        -- required. DEFAULT true.
  storage_class          : enum        -- required. durable | existing_safe | memory.
                                        -- P21-A defines the durable contract; P21-C may
                                        -- create the durable tables only under the
                                        -- migration gate (section 8).
  retention_class        : enum        -- required. standard | long | legal_hold.
                                        -- legal_hold suspends automated purge (7.2).
  validation_status      : enum        -- required. valid | source_unknown |
                                        -- superseded_scope | stale. The durable
                                        -- re-validation result.
  superseded_by          : uuid        -- nullable. FK-like -> approval_id (self-ref).
  previous_state         : enum        -- nullable. State before the last transition.
  last_audit_event_id    : uuid        -- nullable. FK-like ->
                                        -- durable_approval_audit_events.event_id.
  correlation_id         : varchar     -- nullable.
  created_at             : timestamptz -- required. UTC ISO-8601.
  updated_at             : timestamptz -- required. UTC ISO-8601.
  store_version          : int         -- required. Optimistic-concurrency / schema
                                        -- version. Bumped on every state transition.
}
```

Indexes / constraints (logical):

- PK: `approval_id`.
- Unique partial: one *active* (non-terminal) approval per `(request_digest)` scope to
  drive supersession (`state IN (pending_review, approved_execution_blocked)`).
- Unique partial: one open request per `(action_id, maker)` while not terminal.
- Index: `(state)`; `(tenant_id, state)`; `(retention_class, durable_retain_until)` for
  the purge sweep; `(expires_at)` for the expiry sweep; `(action_id)`; `(maker)`.
- FK-like (logical, enforced by a future implementation, never against product tables):
  `action_id` -> P18 request; `last_audit_event_id` -> audit events;
  `superseded_by` -> `approval_id`.

### 3.2 durable_approval_decisions

Each checker decision materialized as a row (the P20 `checkers` log, made durable and
queryable for quorum).

```text
durable_approval_decisions {
  decision_id            : uuid        -- PK. required.
  approval_id            : uuid        -- required. FK-like ->
                                        -- durable_approval_requests.approval_id. ON
                                        -- DELETE RESTRICT (purge is whole-record, 7.3).
  checker_id             : varchar     -- required. Identity-only super_admin actor id.
                                        -- MUST differ from maker (5.2).
  decision               : enum        -- required. approve | reject.
  reason_redacted        : text        -- required. REDACTED before persist (section 4).
  idempotency_key_digest : char(64)    -- required. SHA-256 of the client key. The RAW
                                        -- key is never stored.
  decision_digest        : char(64)    -- required. SHA-256 of the canonical decision
                                        -- payload (approval_id, checker_id, decision,
                                        -- request_digest). Drives idempotent dedup (5.6).
  confirm                : bool        -- required. Explicit confirmation token. A
                                        -- decision lands only after this is true.
  audit_event_id         : uuid        -- required. FK-like ->
                                        -- durable_approval_audit_events.event_id.
  correlation_id         : varchar     -- nullable.
  created_at             : timestamptz -- required. UTC ISO-8601.
}
```

Indexes / constraints:

- PK: `decision_id`.
- Unique: `(approval_id, checker_id)` -- one decision per checker per approval (distinct
  checkers only).
- Unique: `(approval_id, idempotency_key_digest)` -- idempotency within an approval.
- Index: `(approval_id)`; `(checker_id)`.
- FK-like: `approval_id` -> requests; `audit_event_id` -> audit events.

### 3.3 durable_approval_audit_events

Append-only durable audit log. The P20 audit event, made restart-safe and
retention-bound. No UPDATE path; no single-row DELETE; only whole-record purge at
retention expiry (section 7), itself audited.

```text
durable_approval_audit_events {
  event_id            : uuid        -- PK. required. Unique.
  approval_id         : uuid        -- nullable. Null only before the record exists.
  action_id           : uuid        -- nullable. Null where no P18 action is involved.
  actor_id            : varchar     -- required. Identity-only actor id; SYSTEM for
                                    -- expiry / purge / sweep jobs.
  actor_role          : enum        -- required. super_admin | support_operator |
                                    -- engineering_operator | system.
  identity_context    : enum        -- required. identity_only | tenant_contextual |
                                    -- tenant_scoped_token | tenant_admin | system |
                                    -- unknown.
  event_type          : enum        -- required. Closed set (table below).
  decision            : enum        -- nullable. approve | reject | null.
  previous_status     : enum        -- nullable. State before this event.
  next_status         : enum        -- nullable. State after this event.
  reason_redacted     : text        -- required. REDACTED (P10 allowlist). Never a raw
                                    -- request body (4.5).
  request_digest      : char(64)    -- nullable. SHA-256 of the request envelope.
  redaction_applied   : bool        -- required. DEFAULT true.
  tenant_id           : uuid        -- nullable. Scoped identifier only.
  quorum_required     : int         -- nullable.
  quorum_met          : bool        -- nullable.
  validation_status   : enum        -- nullable.
  correlation_id      : varchar     -- nullable.
  sequence_no         : bigint      -- required. Monotonic per-approval audit sequence.
  created_at          : timestamptz -- required. UTC ISO-8601.
}
```

Indexes / constraints:

- PK: `event_id`.
- Unique: `(approval_id, sequence_no)` -- strict per-approval ordering.
- Index: `(approval_id, created_at)`; `(event_type)`; `(actor_id)`; `(created_at)` for
  the retention-window export scan.
- Append-only: no UPDATE path; DELETE only via whole-record retention purge.

Closed `event_type` set (same semantics as P20, persisted; P21 adds no new event
semantics, only persistence):

| event_type | When it fires |
|---|---|
| `approval_opened` | A durable request is opened, validated, and recorded (state -> pending_review). |
| `approval_decision_recorded` | A checker records an approve or reject (per checker). |
| `approval_quorum_met` | The collective approve reaches quorum; state -> approved_execution_blocked. |
| `approval_rejected` | A checker reject lands; reject is final. |
| `approval_expired` | Decision-window TTL elapsed, or a decision was attempted on an expired approval. |
| `approval_cancelled` | The maker / super_admin cancels a pending approval. |
| `approval_superseded` | A newer approval supersedes this one; links superseded_by. |
| `approval_failed_validation` | Durable re-validation fails; records validation_status. |
| `approval_read` | An operator reads a record, the queue, or history (audited; redacted). |
| `approval_exported` | A super_admin exports a redacted retention bundle. |
| `approval_denied` | Any operation is denied: permission, identity, expired, reject-then-approve, decision conflict, unknown-source write, self-approval, read-only fallback, stale write, or malformed request. |
| `approval_purged` | Automated retention expiry purges a terminal record (SYSTEM actor only). |

### 3.4 durable_approval_idempotency_keys

Idempotency dedup table. Digest-only by construction. The raw key is hashed at the
boundary and discarded; only the digest and a payload digest are persisted.

```text
durable_approval_idempotency_keys {
  idempotency_id         : uuid        -- PK. required.
  scope_key              : enum        -- required. open | decide.
  scope_id               : varchar     -- required. (maker, action_id) for open;
                                        -- (approval_id, checker_id) for decide.
  idempotency_key_digest : char(64)    -- required. SHA-256 of the RAW client key. The
                                        -- RAW key is never stored, logged, returned, or
                                        -- audited.
  payload_digest         : char(64)    -- required. SHA-256 of the canonical request /
                                        -- decision payload. Idempotent replay matches
                                        -- this.
  result_ref             : uuid        -- nullable. Reference to the recorded result
                                        -- (approval_id or decision_id) for replay.
  first_seen_at          : timestamptz -- required.
  last_seen_at           : timestamptz -- required.
  created_at             : timestamptz -- required.
}
```

Indexes / constraints:

- PK: `idempotency_id`.
- Unique: `(scope_key, scope_id, idempotency_key_digest)`.
- Index: `(idempotency_key_digest)`.
- Never stores the raw key. A replay returns the prior `result_ref` only when
  `payload_digest` matches; a mismatch is a conflict and is rejected (5.6).

### 3.5 durable_approval_retention_jobs

Future queue for automated retention expiry, purge, revalidation sweep, and redacted
export bundles. Driven by a SYSTEM actor only; never by an operator; never a dispatch of
execution.

```text
durable_approval_retention_jobs {
  job_id              : uuid        -- PK. required.
  job_type            : enum        -- required. retention_purge | retention_export |
                                    -- revalidation_sweep.
  target_approval_id  : uuid        -- nullable. FK-like ->
                                    -- durable_approval_requests.approval_id. Null for
                                    -- batch sweep / export jobs.
  retention_class     : enum        -- nullable. standard | long | legal_hold.
  eligible_at         : timestamptz -- required. When durable_retain_until elapses (or
                                    -- the export window opens).
  locked_by           : varchar     -- nullable. SYSTEM worker lock owner.
  locked_at           : timestamptz -- nullable.
  status              : enum        -- required. pending | running | completed | failed
                                    -- | skipped. DEFAULT pending.
  audit_event_id      : uuid        -- nullable. FK-like -> audit events (for example
                                    -- approval_purged).
  attempts            : int         -- required. DEFAULT 0.
  created_at          : timestamptz -- required.
  updated_at          : timestamptz -- required.
}
```

Indexes / constraints:

- PK: `job_id`.
- Unique partial: at most one pending / running job per `(target_approval_id, job_type)`.
- Index: `(status, eligible_at)` for dequeue; `(retention_class)`.
- `legal_hold` targets are dequeued as `skipped` and audited; purge is suspended while
  legal_hold is set (section 7).

### 3.6 Restart-safe consistency rules (contract)

- A pending review, partial quorum, recorded decision, audit event, and idempotency row
  all survive a process restart. After restart the durable store is the source of truth;
  in-memory P20-B state is a cache at most.
- Every state transition, decision, and audit event is written in a single transaction
  so that the quorum count, the decisions log, the request `state` / `store_version`,
  the audit event, and the idempotency row commit atomically (section 5).
- `store_version` provides optimistic concurrency: a transition that does not advance
  `store_version` is rejected as a stale write. This is the durable guard against
  lost-update races on quorum (5.7).
- Unknown is never healthy: if the store cannot confirm an approval's state, quorum, or
  validation after a restart or partial outage, it refuses to advance the approval to
  `approved_execution_blocked`, serves reads with a `degraded` / `unknown` badge, and
  denies writes with `unavailable_reason = store_unknown`.

## 4. Security and Redaction Contract

### 4.1 Redaction before persistence

- Every `reason`, `comment`, and `metadata` value passes through the P10
  `redact_metadata` allowlist at the boundary -- before it touches durable storage, the
  audit log, any response, queue item, or export.
- `redaction_applied == true` is required on every persisted record and every audit
  event. A record or event persisted with `redaction_applied == false` is a contract
  violation.
- A content scan of every persisted reason, comment, and metadata value against the P10
  allowlist must return clean (test plan T5).

### 4.2 Idempotency key is digest-only

- The client `idempotency_key` is accepted on open and decide for deduplication. **Only
  its SHA-256 digest is stored** (`idempotency_key_digest`). The raw key is hashed at the
  boundary and never persisted, logged, returned, or audited.
- A plaintext idempotency key is treated as a secret: it must not appear in any persisted
  column, response, queue item, audit field, backup, or export (counterexamples C3, C10,
  C17).
- The raw key is discarded immediately after hashing; no column, log, backup, or export
  retains it.

### 4.3 The never-persisted list

The following must NEVER appear in any persisted column, response, queue item, audit
field, backup, or export:

- raw secret, DSN, connection string, hostname, port, host:port pair;
- token, password, API key, cookie, auth header (for example `X-Platform-Operator`,
  `Authorization`, `Cookie`, `Set-Cookie`);
- raw idempotency key (digest only);
- stack trace, raw exception, raw log line;
- raw request body or raw response body of the underlying P18 request (4.5);
- tenant business payload: orders, payments, invoices, customers, inventory, ledgers.

### 4.4 tenant_id is a scoped identifier only

- `tenant_id` is stored only as a scoped platform identifier (the P17 tenant the action
  targets, where applicable). It is never a business payload and never a foreign key into
  product business tables.
- No column in the durable store references a product business table (orders, payments,
  invoices, customers, inventory, ledgers). The durable store references P18 request ids
  and P20 / P21 approval ids only.
- A persisted `tenant_id` must not be joinable to tenant business data through the
  durable store.

### 4.5 Audit events store no raw request bodies

- Audit events store `reason_redacted`, `request_digest` (a hash), redacted metadata, and
  status fields only. They MUST NOT store the raw request body or raw response body of
  the underlying P18 action request.
- The raw P18 request envelope is referenced by `action_id` (a stable id) and summarized
  by `request_digest` (a SHA-256). The envelope itself is never copied into the durable
  store or the audit log.
- Any persisted audit field that reconstructs or echoes the raw request body is a
  contract violation (counterexample C11).

## 5. Maker-Checker and Quorum Consistency Contract

P21 inherits the P20 dual-control policy and tightens it for a *durable, concurrent*
store: multiple checkers may decide concurrently after a restart or across nodes, so
quorum must be transactionally consistent.

### 5.1 Actors (unchanged from P20)

- **maker** and **checker** are both bound to an authenticated **identity-only
  super_admin** actor. support_operator and engineering_operator may open within their
  P18 scope only and may never be checkers.
- tenant admin, tenant-contextual super_admin, and tenant-scoped token are denied on
  every durable-store operation (open, decide, cancel, read, queue, export).

### 5.2 The maker cannot approve / reject its own request

- A decision whose `checker_id == maker` is denied and audited as `approval_denied`
  (self-approval forbidden). The maker can never be a checker on its own approval.
- The durable store enforces this in the same transaction that would insert the decision
  row; no self-decision row is ever persisted.

### 5.3 Distinct checker identities only

- Every checker on a single approval MUST differ from every other checker. The unique
  constraint `(approval_id, checker_id)` (3.2) makes a second decision from the same
  `checker_id` either idempotent (5.6) or a conflict, never a second quorum vote.

### 5.4 Quorum count is transactionally consistent

- `quorum_met` is recomputed inside the same transaction that inserts a decision, from
  the committed set of distinct approve checkers (none the maker, no reject). The request
  `state`, `quorum_met`, `store_version`, the decision row, the audit event, and the
  idempotency row commit atomically.
- `pending_review` reaches `approved_execution_blocked` only when the transactional
  distinct-approve-checker count crosses `quorum_required` with no reject.

### 5.5 Quorum floor by action_class

- **write** (`tenant.pause`, `tenant.resume`, `incident.flag_set`, `incident.flag_clear`,
  `lifecycle.transition`): `quorum_required >= 2` distinct checkers, none the maker.
- **write_request** (`backup.restore_test_request`): `quorum_required >= 2` distinct
  checkers, none the maker. Even at quorum the action stays `execution_blocked`.
- **read** (`provisioning.recheck`, `backup.check`): a durable approval is optional; if
  opened, `quorum_required >= 1` checker distinct from the maker.
- The floor may be configured upward per action_type or tenant by a future governance
  change, never below the floor, never below 2 for write / write_request.

### 5.6 Duplicate decisions are idempotent only on payload-digest match

- A repeat decision with the same `(approval_id, checker_id)` and a `decision_digest`
  that matches the prior row is idempotent: it returns the prior result and writes no
  new state, no new audit event, and no new decision row.
- A repeat with a different `decision_digest` (a conflicting decision from the same
  checker) is a decision conflict: it is rejected and audited as `approval_denied`.

### 5.7 Conflicting decisions are rejected

- An approve and a reject cannot both count. The first reject on an approval makes the
  approval `rejected` (terminal, final for that approval_id); a later approve is denied
  and audited (reject is final).
- Concurrent conflicting decisions are serialized by the transaction plus the
  `store_version` optimistic lock: exactly one outcome commits; the other is retried,
  denied, or idempotent per 5.6. There is no split-brain quorum (test plan T7).

### 5.8 Restart does not weaken separation or quorum

- After a restart, the durable store recomputes `quorum_met` from the persisted
  decisions log. A maker can never become its own checker, a partial approve can never be
  promoted to approved without crossing the floor, and a rejected approval can never be
  re-opened. Restart changes neither the actors nor the quorum floor.

## 6. State Machine Contract

P21 reuses the P20 seven-state machine unchanged. P21 adds the *storage* guarantee: each
state, including `pending_review`, is persisted and survives a restart. **No transition
executes the underlying P18 action.**

```text
 pending_review --+--> approved_execution_blocked
                  +--> rejected            (terminal, final)
                  +--> expired             (terminal)
                  +--> cancelled           (terminal)
                  +--> failed_validation   (terminal)

 approved_execution_blocked --+--> superseded         (terminal)
                              +--> failed_validation  (terminal)
                              +--> expired            (terminal, durable TTL)
```

Allowed transitions:

- `pending_review` -> `approved_execution_blocked` (quorum met, transactional, 5.4).
- `pending_review` -> `rejected` (any reject; final).
- `pending_review` -> `expired` (decision-window TTL elapsed).
- `pending_review` -> `cancelled` (maker / super_admin before quorum).
- `pending_review` -> `failed_validation` (re-validation fails).
- `approved_execution_blocked` -> `superseded` (newer same-scope approval).
- `approved_execution_blocked` -> `failed_validation` (re-validation fails post-quorum).
- `approved_execution_blocked` -> `expired` (durable TTL).

Forbidden transitions:

- Any -> any executing / executed / queued / ready_to_execute state. **None exists.**
- `rejected` -> anything. Reject is final for that approval_id.
- `superseded` / `failed_validation` / `expired` / `cancelled` -> anything (all terminals
  are terminal; no revival, no re-heal).
- `approved_execution_blocked` -> `pending_review` (no un-approve).

Required invariants (storage lens):

1. Quorum gates approval, transactionally (5.4).
2. Reject is final for that approval_id; a later approve is denied and audited.
3. Approved never becomes executed; `approved_execution_blocked` has no transition to any
   executing or executed state.
4. Every transition is persisted atomically with exactly one audit event and a
   `store_version` bump, and survives a restart in the same state.
5. Supersession and failed_validation are terminal and explicit.
6. **None of these transitions executes the underlying P18 action;** `execution_allowed`
   stays `false`, `execution_gate` stays `blocked`, and P18 `executed` stays `false`.

## 7. Retention, Purge, and Export Contract

### 7.1 retention_class and durable_retain_until

- Every record carries `retention_class` in {standard, long, legal_hold} and a
  `durable_retain_until` timestamp. The record and its audit events are retained until
  `durable_retain_until` after the record reaches a terminal state.
- `retention_class` sets the retention floor. The floor may be raised by a future
  governance change, never lowered below the legal minimum for the class.

### 7.2 legal_hold behavior

- `retention_class = legal_hold` suspends automated purge. A legal_hold record and its
  audit events are never purged while the hold is set, even after `durable_retain_until`
  elapses.
- Setting or clearing legal_hold is audited. legal_hold is never a path to mutation or
  execution; it only extends retention.

### 7.3 Purge eligibility

- Purge is **automated retention expiry only**, performed by a SYSTEM actor via
  `durable_approval_retention_jobs` after `durable_retain_until` elapses on a terminal
  record that is not on legal_hold.
- Purge is **never an operator-initiated action**: no role, including identity-only
  super_admin, may manually delete or purge a durable record, decision, idempotency row,
  or audit event.
- Purge is whole-record: a request row, its decisions, its idempotency rows, and its
  audit events are purged together (or retained together under legal_hold).

### 7.4 Export-safe fields

- An identity-only super_admin may export a **redacted** audit / retention bundle (CSV or
  JSON) for a bounded time window via a `retention_export` job. Export is append-only
  audited as `approval_exported`.
- Export-safe fields: `approval_id`, `action_id`, `tenant_id` (scoped id only), `state`,
  `maker`, `decision`, `quorum_required`, `quorum_met`, `event_type`,
  `previous_status`, `next_status`, `actor_id`, `actor_role`, `identity_context`,
  `request_digest`, `idempotency_key_digest`, `validation_status`, `retention_class`,
  `created_at`.

### 7.5 Fields never exported

- raw idempotency key, raw secret, DSN, connection string, host, port, host:port, token,
  password, API key, cookie, auth header, raw request body, raw response body, stack
  trace, raw exception, raw log line, and tenant business payload are never exported.
- An export that includes any never-exported field is a contract violation
  (counterexample C17).

### 7.6 Purge audit event requirements

- Every purge emits exactly one `approval_purged` audit event (SYSTEM actor, redacted)
  recording the `approval_id`, `retention_class`, `durable_retain_until`, and the fact of
  expiry.
- A purge without an `approval_purged` audit event, or an operator-initiated purge, is a
  contract violation (counterexample C16).

## 8. Migration Boundary

P21-A defines what a future **P21-C** migration *may* create. **P21-A creates nothing
now.** No migration, alembic change, table, or column is added in P21-A or P21-B.

A future P21-C migration that creates the durable tables (3.1-3.5) MUST satisfy all of
the following gates:

1. **Additive only.** The migration creates new tables / indexes only. It adds no column
   to, drops no column from, and renames no existing product table.
2. **No existing product tables changed.** No existing backend, product, tenant, payment,
   auth, or RBAC table is altered.
3. **No tenant schema migration unless separately approved.** Tenant / business schema is
   untouched. A tenant-schema migration requires a separate explicit approval outside
   P21.
4. **public / platform schema only unless explicitly approved.** New tables live in the
   platform / public schema. A different schema requires separate explicit approval.
5. **Rollback plan required.** The migration ships a tested downgrade / revert that
   removes only the new tables and leaves all existing data intact, plus a verified
   restore path.
6. **Dry-run / schema-inspection gate required.** The migration is validated by a dry-run
   or schema-inspection diff (DDL preview, no data change) before it is applied anywhere
   outside an ephemeral test database.
7. **CTO approval required.** P21-C is the *earliest* phase that may run the migration,
   and only after explicit CTO approval. P21-A and P21-B may not.
8. **No execution, no tenant mutation, no storage switch before P21-C.** Even P21-C
   creating the tables does not switch runtime storage or execute anything; a runtime
   storage cutover is a further separately approved step.

## 9. API Compatibility Contract

The future durable backend (P21-C+) MUST preserve the P20 API response shapes unless a
new versioned contract is separately approved. The existing frontend P20-C must not need
semantic changes.

- **POST create durable approval** (open): same request body and same response shape as
  P20-B. A durable backend MAY add restart-safety metadata (for example
  `storage_class: durable`, `restart_safe: true`) but MUST NOT remove or rename existing
  P20 response fields. `execution_allowed` remains `false`; `state` is `pending_review`.
- **GET list** (queue): same filters, pagination, and item shape as P20-B. Durability
  does not change the queue contract; it only makes the queue survive a restart.
- **GET by id** (detail): same record shape as P20-B, including `state`, `maker`,
  `checkers`, `quorum_required`, `quorum_met`, `decision`, `execution_allowed`,
  `execution_gate`, `validation_status`, `retention_class`, `durable_retain_until`, and
  `redaction_applied`. Durability is additive.
- **POST decision**: same request body (`decision`, `approver_id`, `reason`,
  `idempotency_key`, `confirm`) and same response shape as P20-B. Idempotency is now
  durable (5.6): a replay after restart returns the prior result on digest match.

Compatibility rules:

- No P20 response field is removed or renamed without a new versioned contract.
- No new field carries a secret, raw key, raw body, or tenant payload.
- `execution_allowed` is always `false`; no endpoint returns an executing / executed
  state.
- The frontend P20-C read-only console needs no semantic change; it continues to call the
  same endpoints. If restart-safety badges are surfaced, they are additive display only.

## 10. Test Plan (future phases)

P21-A defines the expected tests; it writes none. A future implementation must include:

- **T1 schema contract tests** -- every table has exactly its declared columns, types,
  nullability, enums, defaults, and `extra = forbid` discipline; no undeclared column.
- **T2 migration tests** -- the P21-C migration is additive, reversible (downgrade
  removes only new tables), and passes a dry-run / schema-inspection diff; no existing
  table is altered.
- **T3 restart persistence tests** -- a pending review, partial quorum, recorded
  decision, audit event, and idempotency row all survive a simulated process restart;
  `state` and `quorum_met` are unchanged after restart.
- **T4 idempotency digest tests** -- a replayed open / decision with a matching
  `payload_digest` is idempotent (no new row, no new event); a raw key is never stored;
  only the digest is present.
- **T5 redaction persistence tests** -- a content scan of every persisted reason,
  comment, metadata, and audit `reason_redacted` against the P10 allowlist returns clean;
  `redaction_applied == true` everywhere.
- **T6 maker-checker transaction tests** -- a self-decision (`checker_id == maker`) is
  rejected and never persisted; a second distinct checker is required for write quorum;
  the decision + state + audit + idempotency commit atomically.
- **T7 quorum race tests** -- concurrent conflicting decisions from distinct checkers
  serialize to exactly one outcome; there is no split-brain quorum; `store_version`
  rejects stale writes.
- **T8 retention / purge / export tests** -- purge fires only after
  `durable_retain_until` on a terminal record, only via a SYSTEM job, and emits
  `approval_purged`; legal_hold suspends purge; export is redacted and audited and
  contains no never-exported field; an operator cannot purge.
- **T9 no-execution tests** -- a quorum-met approval reaches `approved_execution_blocked`
  and leaves `execution_allowed == false`, `execution_gate == blocked`, and P18
  `executed == false`; no transition runs the action.
- **T10 no-tenant-mutation tests** -- no P17 registry field, lifecycle, flag, or tenant
  business record is read or written by the durable store; `tenant_id` is a scoped id
  only and is not joinable to business tables.
- **T11 GitNexus scope tests** -- `detect_changes` for the durable store change is scoped
  to the platform durable-approval storage surface; no product, tenant, payment, auth, or
  RBAC process is affected.

## 11. Acceptance Criteria

A future phase that implements this contract is accepted only when all of the following
hold:

1. **Durable approval never executes.** Quorum-met approval reaches
   `approved_execution_blocked` and leaves `execution_allowed == false`,
   `execution_gate == blocked`, and P18 `executed == false`. There is no execution path.
2. **The store is restart-safe.** A pending review, partial quorum, decision, audit
   event, and idempotency row survive a restart; `state` and `quorum_met` are unchanged.
3. **Maker-checker separation holds in the durable store.** No approval reaches
   `approved_execution_blocked` with the maker among its checkers; a self-decision is
   rejected, never persisted, and audited.
4. **Quorum is transactionally consistent.** A write / write_request approval reaches
   `approved_execution_blocked` only with at least two distinct approve checkers (none
   the maker) committed in one transaction; a partial approve stays `pending_review`.
5. **Distinct checkers only.** The `(approval_id, checker_id)` uniqueness holds; a second
   decision from the same checker is idempotent or a conflict, never a second vote.
6. **Only identity-only super_admin may be a checker;** support_operator,
   engineering_operator, tenant admin, tenant-contextual super_admin, and tenant-scoped
   token are denied on every operation and every denial is audited.
7. **The lifecycle states are exactly the seven defined;** there is no
   `ready_to_execute`, `queued_for_run`, `executing`, or `executed` state.
8. **Reject is final for that approval_id;** a later approve is denied and audited.
9. **Every durable approval expires;** `expires_at` is required and in the future at
   creation; an expired approval cannot be accepted.
10. **The idempotency key is digest-only;** an audit / content scan finds no raw
    idempotency key in any persisted column, response, queue item, or audit field.
11. **Redaction-before-persistence is total;** every persisted reason / comment / metadata
    and audit `reason_redacted` scans clean; `redaction_applied == true` everywhere.
12. **No raw secrets / DSNs / hosts / ports / tokens / passwords / cookies / auth headers
    or tenant payload** appear in any persisted column, response, or audit field.
13. **Audit events store no raw request / response body;** only redacted reason, digests,
    and status fields are persisted; the audit log is append-only.
14. **Destructive and tenant-mutating actions stop;** they reach at most
    `approved_execution_blocked` and never execute or mutate tenant data.
15. **Purge is automated retention expiry only;** SYSTEM actor via
    `durable_approval_retention_jobs`; no operator purge; legal_hold suspends purge;
    every purge emits `approval_purged`.
16. **Export is redacted and audited;** it contains only export-safe fields and never a
    never-exported field.
17. **The migration (when it lands in P21-C) is additive, reversible, dry-run-gated,
    platform-schema-only, and CTO-approved;** P21-A and P21-B add no migration.
18. **API compatibility holds;** P20 response shapes are preserved; `execution_allowed`
    is always `false`; the P20-C frontend needs no semantic change.
19. **No runtime code, migration, frontend, tests, or dependency changes ship in
    P21-A;** P21-A is docs and ledger only.

## 12. Counterexamples (must fail or be rejected)

1. **C1 -- an approved action executing.** A quorum-met approve that runs, schedules,
   dispatches, or applies the underlying P18 action, or that sets
   `execution_allowed == true` -- rejected; approved must be
   `approved_execution_blocked` with no execution.
2. **C2 -- self-approval persisted.** A decision row with `checker_id == maker` that is
   stored or counts toward quorum -- rejected and audited; never persisted.
3. **C3 -- the raw idempotency key persisted.** A column, log, backup, or audit field
   that holds the plaintext idempotency key instead of its SHA-256 digest -- rejected
   (contract violation).
4. **C4 -- a tenant admin operating the durable store.** Any tenant admin successfully
   opening, deciding, reading, or exporting -- rejected and audited as `approval_denied`.
5. **C5 -- a tenant-contextual super_admin as checker.** A super_admin with a selected
   tenant context acting as checker -- rejected and audited as `approval_denied`.
6. **C6 -- quorum of one on a write.** A `tenant.pause` approval reaching
   `approved_execution_blocked` with a single checker -- rejected; the write quorum
   floor is two distinct checkers (none the maker).
7. **C7 -- a partial approve promoted after restart.** A `pending_review` approval with
   `quorum_met == false` that is executed, rendered approved, or advanced to
   `approved_execution_blocked` after a restart without crossing the floor -- rejected.
8. **C8 -- a stale-write quorum.** Two concurrent conflicting decisions both committing
   (split-brain quorum) because `store_version` was not checked -- rejected; exactly one
   outcome commits.
9. **C9 -- a conflicting same-checker decision counted twice.** A second decision from
   the same `checker_id` with a different `decision_digest` that counts as a second vote
   -- rejected as a conflict and audited.
10. **C10 -- a raw secret persisted.** Any persisted reason / comment / metadata / audit
    field containing a credential, DSN, host, port, connection string, token, password,
    cookie, auth header, stack trace, or raw exception -- rejected (redaction violation).
11. **C11 -- an audit event storing a raw request body.** A persisted audit field that
    echoes or reconstructs the raw P18 request / response body -- rejected (contract
    violation).
12. **C12 -- a rejected approval re-opened.** A transition that moves a `rejected`
    approval back to `pending_review` or `approved_execution_blocked` -- rejected; reject
    is final.
13. **C13 -- a terminal approval revived.** A transition returning a `superseded` /
    `failed_validation` / `expired` / `cancelled` approval to a non-terminal state --
    rejected.
14. **C14 -- tenant_id joined to business data.** A persisted `tenant_id` that is a
    foreign key into a product business table, or a durable-store column referencing
    orders / payments / invoices / customers / inventory / ledgers -- rejected.
15. **C15 -- a migration added in P21-A or P21-B.** Any backend, frontend, migration,
    alembic change, table, test, or dependency change added in P21-A or P21-B --
    rejected; P21-A is docs / ledger only and P21-B is plan / tests only.
16. **C16 -- an operator manually purging.** Any role (including identity-only
    super_admin) that manually deletes or purges a durable record, decision, idempotency
    row, or audit event -- rejected; purge is SYSTEM retention expiry only.
17. **C17 -- an export leaking sensitive data.** An exported bundle that includes a raw
    idempotency key, raw secret, DSN, host:port, token, password, cookie, auth header,
    raw request body, or tenant payload -- rejected; export is redacted and audited.
18. **C18 -- a runtime storage cutover in P21-A / P21-B.** Switching the running P20-B
    store to the durable backend before P21-C and CTO approval -- rejected; P21-A and
    P21-B do not switch runtime storage.
19. **C19 -- the durable store acting as an execution queue.** A consumer / worker /
    scheduler / runner that drains approved approvals and runs them, or a
    `durable_approval_retention_jobs` row that dispatches execution -- rejected.
20. **C20 -- an unaudited transition.** Any persisted state change (including denied,
    superseded, failed_validation, or purge) that lands without exactly one durable audit
    event carrying all required fields -- rejected (contract violation).
21. **C21 -- an AI agent executing directly.** Any AI copilot path that executes a
    controlled action, sets `execution_allowed == true`, or decides / approves without an
    operator -- rejected (section 14).
22. **C22 -- a notification leaking sensitive info.** (Forward reference.) Any future
    notification tied to a durable approval that emits a raw secret / DSN / host:port /
    token / password / cookie / auth header / raw idempotency key / raw body / tenant
    payload -- rejected; P21-A names notification as a future contract and permits no
    such leak.

## 13. P21-B Entry Gate (future)

A future P21-B is permitted to define **only**:

- the **schema / migration plan** for the durable tables (3.1-3.5) as a written, reviewed
  plan (DDL sketch, indexes, constraints, rollback plan, dry-run procedure); and
- **tests** for that plan (schema contract tests, migration / reversibility tests, and
  dry-run / schema-inspection tests) -- written, but run only against ephemeral test
  databases.

P21-B (and all of P21 before P21-C) **must not**:

- run any production migration, alembic change, or table creation;
- switch runtime storage from the P20-B in-memory / existing-safe store to a durable
  backend;
- execute any controlled action or mutate tenant state;
- rewrite auth / RBAC / session / tenancy;
- implement notification / escalation, real rollback / restore, or an execution path;
- touch product-dev-recovered or any product business path.

**P21-C is the earliest phase that may implement the migration**, and only after explicit
CTO approval and only under all gates in section 8. Even P21-C creating the tables does
not switch runtime storage or execute anything. P21-B must begin from this contract and
may not change the tables, fields, enums, constraints, state machine, security rules,
retention rules, API compatibility, or audit fields without a new contract revision
accepted by the CTO.

## 14. Future AI Operator Copilot Note

Any future AI Operator Copilot must operate **through** this durable approval substrate,
never around it. The boundary:

- The AI may **read platform state** via approved, read-only tools (P15 triage, P13 / P14
  observability, P17 registry read, P18 request queue read).
- The AI may **propose controlled actions** and draft P18 action requests, but only as
  proposals.
- The AI may **create draft action requests only after explicit operator confirmation**
  -- a human identity-only super_admin must be the maker. The AI is never the maker and
  never the checker.
- The AI **cannot execute actions directly.** There is no AI path to
  `execution_allowed == true`, no AI self-approval, and no AI break-glass.
- **Every AI action must be audited** as a durable audit event (for example
  `approval_opened` / `approval_denied`, with the AI proposal recorded as redacted
  metadata and actor_role set to the confirming operator's role or `system`).
- **AI tool calls must be linked to approval records** via `correlation_id` /
  `action_id` / `approval_id`, so every AI proposal is traceable to a human-gated
  durable approval.
- **Real execution remains separately gated** behind a future execution contract that
  must run through the P16 governed harness. The durable store records AI-assisted
  maker-checker decisions; it does not run them.

This section names a future boundary only. P21-A implements no AI copilot, grants no AI
execution power, and adds no AI-specific runtime code.

## 15. Docs-Only and Contract-Only Statement

P21-A is **docs-only and contract-only**. It ships:

- `docs/ai/PLATFORM_PRODUCT_P21_DURABLE_APPROVAL_STORE_CONTRACT.md` -- this contract.
- `docs/ai/README.md` -- the P21 entry in the Platform Product Track read order.
- `ai-ledger/platform/2026-06-26_p21a_durable_approval_store_contract.md` -- the ledger.

There is **no runtime code, no backend, no frontend, no migration, no alembic change, no
table, no test code, and no dependency change** in P21-A. P21-A defines the durable
approval store contract only; it does not execute, persist (beyond defining the
contract), migrate, switch storage, invoke, or implement any approval, action, store, or
execution path. **Approval is not execution, and durability is not execution.** Execution
is reserved for a separately approved future phase and must run through the P16 governed
harness. **P21-B is not started.**
