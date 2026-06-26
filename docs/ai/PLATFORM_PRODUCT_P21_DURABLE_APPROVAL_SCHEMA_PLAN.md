# Platform Product P21-B -- Durable Approval Store Schema Plan + Test Plan

**Status:** Planning only (P21-B). No migration files, no tables created, no runtime
backend changes, no storage switch, no frontend, no alembic changes, no tests written,
and no dependency changes. Accepted by the CTO before any P21-C migration may begin.
**Phase:** P21-B Durable Approval Store Schema Plan + Test Plan
**Date:** 2026-06-26
**Base:** `df92bb0` (origin/platform-dev -- P21-A durable approval store contract merged;
P21-A_CONTRACT_MERGED)
**Depends on:** P21-A (Durable Approval Store Contract: logical data model, security and
redaction, maker-checker / quorum consistency, state machine, retention / purge / export,
migration boundary, API compatibility), and transitively P10 (identity-only super_admin
guard, PlatformAuditEvent, source-status vocabulary, redact_metadata allowlist), P18
(Controlled Platform Actions), P19 (Approval Workflow), P20 (Durable Approval Governance,
in-memory / existing-safe non-executing skeleton).
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P21-A defined the durable approval store **contract** as logical storage records. P21-B
converts that contract into an **implementation-ready** artifact set: the exact future
schema / migration plan, the storage-adapter interface contract, the constraint and
transaction plan, and the test plan. After P21-B is accepted, a future P21-C may
implement the additive migration (CTO-gated) and P21-D may wire the runtime adapter.

P21-B produces the plan only. It writes:

- the **schema plan**: exact tables, columns, types, nullability, defaults, indexes,
  uniqueness constraints, and foreign-key-like relationships for the five durable tables
  (sections 3, 4, 5);
- the **transaction plan**: future transactional boundaries and race handling
  (section 6);
- the **storage-adapter interface contract**: function signatures, return shapes, error
  cases, idempotency behavior, and the no-execution invariant (section 7);
- the **migration plan for P21-C**: naming, additive-only rules, rollback, dry-run, and
  pre / post validation (section 8);
- the **test plan for P21-C / P21-D**: test groups with expected counts (section 9);
- **acceptance criteria** (section 10) and **counterexamples** (section 11);
- the **P21-C entry gate** (section 12) and the **future AI Operator Copilot trace**
  (section 13);
- full **traceability** from every major P21-A contract requirement to a planned schema
  and test artifact (section 2).

The single most important invariant, unchanged from P21-A and repeated throughout:

> **Approval is not execution, and durability is not execution.** The schema, the
> constraints, the transactions, the adapter, the migration, and the tests all preserve
> `execution_allowed == false`, `execution_gate == blocked`, and `executed == false`.
> There is no path in P21-B (or in the P21-C / P21-D it plans) from a persisted approval
> to execution.

### 1.2 Non-goals (explicit, for ALL of P21-B)

- No migration files, no tables created, no alembic changes, no generated DB files.
- No runtime backend code, no endpoint changes, no storage switch (P20 stays in-memory /
  existing-safe).
- No frontend, no test code, no dependency or package / lockfile change.
- No auth / RBAC / session / tenancy / payment / business-data code or rewrite.
- **No execution of any controlled action.** `execution_allowed` stays `false`,
  `execution_gate` stays `blocked`, `executed` stays `false`.
- No tenant mutation; `tenant_id` is a scoped identifier only.
- No start of P21-C. P21-C (the migration) is CTO-gated and remains additive /
  platform-schema-only.
- No touch of product-dev-recovered, no push to any product branch, no merge or push of
  platform-dev.

## 2. Source Contract Traceability

Every major P21-A contract requirement is tagged with a traceability ID and mapped to a
planned schema artifact (table / column / constraint / index) and a planned test artifact
(test group). ID prefixes: `P21A-S` = schema / data-model requirement; `P21A-R` =
redaction / security; `P21A-Q` = maker-checker / quorum; `P21A-T` = state-machine
transition; `P21A-L` = retention / lifecycle / purge / export; `P21A-M` = migration
boundary; `P21A-A` = API compatibility. Planned tables: T1 requests, T2 decisions, T3
audit events, T4 idempotency keys, T5 retention jobs. Test groups G1-G14 are defined in
section 9.

| ID | P21-A requirement (section) | Planned schema artifact | Planned test |
|---|---|---|---|
| P21A-S1 | requests record shape (3.1) | T1 durable_approval_requests + all listed columns (3.1) | G1, G4 |
| P21A-S2 | decisions log (3.2) | T2 durable_approval_decisions (3.2) | G1, G7 |
| P21A-S3 | durable append-only audit (3.3) | T3 durable_approval_audit_events, append-only guard (3.3, 5) | G1, G6 |
| P21A-S4 | digest-only idempotency table (3.4) | T4 durable_approval_idempotency_keys (3.4) | G1, G5 |
| P21A-S5 | retention / purge queue (3.5) | T5 durable_approval_retention_jobs (3.5) | G1, G10 |
| P21A-S6 | restart-safe consistency (3.6) | store_version optimistic lock + atomic transactions (5, 6) | G4 |
| P21A-R1 | raw idempotency key never stored (4.2) | digest-only columns + constraint C-R1 (5) | G5, G6 |
| P21A-R2 | redaction before persistence (4.1) | reason_redacted / metadata_redacted columns + C-R2 (5) | G6 |
| P21A-R3 | never-persisted list (4.3) | C-R3 content-scan invariant (5) | G6 |
| P21A-R4 | tenant_id scoped identifier only (4.4) | C-R4 no business-table FK (5) | G12 |
| P21A-R5 | no raw request bodies in audit (4.5) | audit stores digest only + C-R5 (5) | G6 |
| P21A-Q1 | maker / checker identity-only super_admin (5.1) | C-Q1 actor columns (5) | G7 |
| P21A-Q2 | maker cannot self-approve (5.2) | C-Q2 checker_actor_id != maker_actor_id (5) | G7 |
| P21A-Q3 | distinct checkers only (5.3) | UNIQUE (approval_id, checker_actor_id) + C-Q3 (5) | G7, G8 |
| P21A-Q4 | transactional quorum (5.4) | C-Q4 atomic quorum recompute (5, 6) | G8 |
| P21A-Q5 | quorum floor by class (5.5) | C-Q5 quorum_required floor (5) | G7 |
| P21A-Q6 | idempotent on digest match (5.6) | C-Q6 decision_digest dedup (5) | G5 |
| P21A-Q7 | conflicting decisions rejected (5.7) | C-Q7 conflict + store_version (5, 6) | G8 |
| P21A-Q8 | restart does not weaken (5.8) | persisted quorum recompute (6) | G4 |
| P21A-T1 | quorum gates approval (6) | transition guard + C-T1 (6) | G9 |
| P21A-T2 | reject is final (6) | C-T2 terminal guard (5, 6) | G9 |
| P21A-T3 | approved never executed (6) | C-T3 execution_allowed=false invariant (5) | G11 |
| P21A-T4 | every transition audited atomically (6) | C-T4 audit-in-transaction (6) | G9 |
| P21A-T5 | supersession / failed_validation terminal (6) | C-T5 terminal guards (5) | G9 |
| P21A-T6 | no transition executes (6) | C-T6 executed=false invariant (5) | G11 |
| P21A-L1 | retention / purge / export (7) | retention_class + durable_retain_until + T5 (3.1, 3.5) | G10 |
| P21A-L2 | legal_hold prevents purge (7.2) | C-L2 retention_class=legal_hold skip (5, 6) | G10 |
| P21A-M1..M8 | migration gates (8) | migration plan (8) | G2 |
| P21A-A1 | API compatibility (9) | adapter return shapes (7) | G13 |

The constraint IDs (C-...) are defined in section 5. Each is an application-enforced or
schema-enforced invariant that the P21-C migration and P21-D adapter must satisfy, and
that the test plan verifies.

## 3. Proposed Schema Plan

The five logical tables from P21-A are made concrete. The DDL below is an **illustrative
sketch inside this document**, not a migration file (section 8). All tables live in the
platform / public schema, are additive-only, and reference no product business table.
Types use SQL-standard names portable across the platform's target engine; `uuid`,
`timestamptz`, `jsonb`, `char(64)` (SHA-256 hex), `bigint`, `int`, `bool`, `varchar`,
`text`, and `enum` (created as checked varchar or native enum per engine). Every table is
`extra = forbid` in spirit (no undeclared columns). All timestamps are UTC ISO-8601.

Two columns are refinements that make P21-A's logical model implementation-ready and are
called out explicitly: `maker_actor_id` (P21-A named the field `maker`; renamed for
symmetry with `checker_actor_id` and to read as an actor id) and `executed` (P21-A
referenced the P18 `executed` flag; P21-B materializes a local `executed` column that is
always `false` in P21 so the durable record is restart-safe and self-describing without
reaching into the P18 request). Both map to P21-A via traceability (section 2).

### 3.1 durable_approval_requests (T1)

```text
CREATE TABLE durable_approval_requests (
  approval_id            uuid        PRIMARY KEY,                       -- required
  action_id              uuid        NOT NULL,                          -- FK-like -> P18 request (executed=false); never mutated
  tenant_id              uuid        NULL,                              -- scoped identifier ONLY; never a business FK
  action_type            enum        NOT NULL,                          -- P18 action_type
  action_class           enum        NOT NULL,                          -- read | write | write_request
  state                  enum        NOT NULL,                          -- see 4.1
  maker_actor_id         varchar     NOT NULL,                          -- identity-only super_admin; never a checker (C-Q1,C-Q2)
  maker_at               timestamptz NOT NULL,
  quorum_required        int         NOT NULL,                          -- floor per action_class (C-Q5)
  quorum_met             bool        NOT NULL DEFAULT false,
  decision               enum        NULL,                              -- approve | reject
  reason_redacted        text        NOT NULL,                          -- redacted via P10 allowlist (C-R2)
  metadata_redacted      jsonb       NULL,                              -- redacted via P10 allowlist (C-R2)
  request_digest         char(64)    NOT NULL,                          -- SHA-256 of canonical request envelope
  idempotency_key_digest char(64)    NOT NULL,                          -- SHA-256 of client key; raw key NEVER stored (C-R1)
  source_status          enum        NOT NULL,                          -- valid|unknown|unavailable|degraded (mirrors P18/P13)
  validation_status      enum        NOT NULL,                          -- valid|source_unknown|superseded_scope|stale
  execution_allowed      bool        NOT NULL DEFAULT false,            -- always false in P21 (C-T3)
  execution_gate         enum        NOT NULL DEFAULT 'blocked',        -- blocked|not_authorized; only blocked in P21
  executed               bool        NOT NULL DEFAULT false,            -- always false in P21 (C-T6); materializes P18 flag
  redaction_applied      bool        NOT NULL DEFAULT true,
  storage_class          enum        NOT NULL,                          -- durable|existing_safe|memory
  retention_class        enum        NOT NULL,                          -- standard|long|legal_hold (C-L2)
  expires_at             timestamptz NOT NULL,                          -- decision-window TTL; future at creation
  durable_retain_until   timestamptz NOT NULL,                          -- retention TTL after terminal state
  superseded_by          uuid        NULL,                              -- self-ref -> approval_id
  previous_state         enum        NULL,
  last_audit_event_id    uuid        NULL,                              -- FK-like -> durable_approval_audit_events
  correlation_id         varchar     NULL,
  store_version          int         NOT NULL DEFAULT 1,                -- optimistic concurrency (P21A-S6)
  created_at             timestamptz NOT NULL,
  updated_at             timestamptz NOT NULL
);
```

Indexes / constraints (planned):

- PRIMARY KEY: `approval_id`.
- UNIQUE partial index `uq_requests_active_digest` on `(request_digest)` WHERE `state IN
  ('pending_review','approved_execution_blocked')` -- one active approval per scope
  (supersession).
- UNIQUE partial index `uq_requests_open_action_maker` on `(action_id, maker_actor_id)`
  WHERE `state NOT IN (terminal states)` -- one open request per (action, maker).
- INDEX `ix_requests_state` on `(state)`.
- INDEX `ix_requests_tenant_state` on `(tenant_id, state)`.
- INDEX `ix_requests_purge_scan` on `(retention_class, durable_retain_until)` -- purge
  sweep dequeue.
- INDEX `ix_requests_expire_scan` on `(expires_at)` WHERE `state = 'pending_review'` --
  expiry sweep.
- INDEX `ix_requests_source_val` on `(source_status, validation_status)`.
- INDEX `ix_requests_action` on `(action_id)`.
- FK-like (logical): `action_id` -> P18 request; `last_audit_event_id` -> T3;
  `superseded_by` -> `approval_id` (self).

### 3.2 durable_approval_decisions (T2)

```text
CREATE TABLE durable_approval_decisions (
  decision_id            uuid        PRIMARY KEY,
  approval_id            uuid        NOT NULL,                          -- FK -> T1, ON DELETE RESTRICT
  checker_actor_id       varchar     NOT NULL,                          -- identity-only super_admin; != maker (C-Q1,C-Q2)
  decision               enum        NOT NULL,                          -- approve | reject
  reason_redacted        text        NOT NULL,                          -- redacted (C-R2)
  metadata_redacted      jsonb       NULL,                              -- redacted (C-R2)
  idempotency_key_digest char(64)    NOT NULL,                          -- digest only (C-R1)
  decision_digest        char(64)    NOT NULL,                          -- SHA-256 of canonical decision payload (C-Q6)
  confirm                bool        NOT NULL,                          -- explicit confirmation token
  audit_event_id         uuid        NOT NULL,                          -- FK -> T3
  correlation_id         varchar     NULL,
  created_at             timestamptz NOT NULL
);
```

Indexes / constraints:

- PRIMARY KEY: `decision_id`.
- UNIQUE `uq_decisions_approval_checker` on `(approval_id, checker_actor_id)` -- one
  decision per checker per approval (C-Q3).
- UNIQUE `uq_decisions_approval_idem` on `(approval_id, idempotency_key_digest)` --
  idempotency within an approval (C-Q6).
- INDEX `ix_decisions_approval` on `(approval_id)`.
- INDEX `ix_decisions_checker` on `(checker_actor_id)`.
- FK: `approval_id` -> T1 (RESTRICT); `audit_event_id` -> T3.

### 3.3 durable_approval_audit_events (T3)

```text
CREATE TABLE durable_approval_audit_events (
  event_id            uuid        PRIMARY KEY,
  approval_id         uuid        NULL,                                -- null only before the record exists
  action_id           uuid        NULL,
  actor_id            varchar     NOT NULL,                            -- identity-only actor; 'system' for expiry/purge/sweep
  actor_role          enum        NOT NULL,                            -- super_admin|support_operator|engineering_operator|system
  identity_context    enum        NOT NULL,                            -- identity_only|tenant_contextual|tenant_scoped_token|tenant_admin|system|unknown
  event_type          enum        NOT NULL,                            -- see 4.8
  decision            enum        NULL,                                -- approve | reject
  audit_result        enum        NOT NULL,                            -- see 4.9
  previous_status     enum        NULL,
  next_status         enum        NULL,
  reason_redacted     text        NOT NULL,                            -- redacted; NEVER a raw request body (C-R5)
  metadata_redacted   jsonb       NULL,
  request_digest      char(64)    NULL,
  redaction_applied   bool        NOT NULL DEFAULT true,
  tenant_id           uuid        NULL,                                -- scoped identifier only
  quorum_required     int         NULL,
  quorum_met          bool        NULL,
  source_status       enum        NULL,
  validation_status   enum        NULL,
  correlation_id      varchar     NULL,
  sequence_no         bigint      NOT NULL,                            -- monotonic per-approval sequence
  created_at          timestamptz NOT NULL
);
```

Indexes / constraints:

- PRIMARY KEY: `event_id`.
- UNIQUE `uq_audit_approval_seq` on `(approval_id, sequence_no)` -- strict per-approval
  ordering.
- INDEX `ix_audit_approval_time` on `(approval_id, created_at)`.
- INDEX `ix_audit_event_type` on `(event_type)`.
- INDEX `ix_audit_actor` on `(actor_id)`.
- INDEX `ix_audit_time` on `(created_at)` -- retention-window export scan.
- Append-only: no UPDATE path; DELETE only via whole-record retention purge (P21A-S3).
  Enforced in P21-D by granting the adapter INSERT-only privileges on T3.

### 3.4 durable_approval_idempotency_keys (T4)

```text
CREATE TABLE durable_approval_idempotency_keys (
  idempotency_id         uuid        PRIMARY KEY,
  scope_key              enum        NOT NULL,                          -- open | decide
  scope_id               varchar     NOT NULL,                          -- (maker_actor_id, action_id) | (approval_id, checker_actor_id)
  idempotency_key_digest char(64)    NOT NULL,                          -- SHA-256 of RAW key; raw key NEVER stored (C-R1)
  payload_digest         char(64)    NOT NULL,                          -- SHA-256 of canonical payload; replay match key (C-Q6)
  result_ref             uuid        NULL,                              -- approval_id or decision_id for replay
  first_seen_at          timestamptz NOT NULL,
  last_seen_at           timestamptz NOT NULL,
  created_at             timestamptz NOT NULL
);
```

Indexes / constraints:

- PRIMARY KEY: `idempotency_id`.
- UNIQUE `uq_idem_scope` on `(scope_key, scope_id, idempotency_key_digest)`.
- INDEX `ix_idem_digest` on `(idempotency_key_digest)`.

### 3.5 durable_approval_retention_jobs (T5)

```text
CREATE TABLE durable_approval_retention_jobs (
  job_id              uuid        PRIMARY KEY,
  job_type            enum        NOT NULL,                            -- retention_purge|retention_export|revalidation_sweep
  target_approval_id  uuid        NULL,                                -- FK -> T1; null for batch sweep/export
  retention_class     enum        NULL,                                -- standard|long|legal_hold
  eligible_at         timestamptz NOT NULL,                            -- when durable_retain_until elapses / export window opens
  locked_by           varchar     NULL,                                -- SYSTEM worker lock owner
  locked_at           timestamptz NULL,
  status              enum        NOT NULL DEFAULT 'pending',          -- pending|running|completed|failed|skipped
  audit_event_id      uuid        NULL,                                -- FK -> T3 (e.g. approval_purged)
  attempts            int         NOT NULL DEFAULT 0,
  created_at          timestamptz NOT NULL,
  updated_at          timestamptz NOT NULL
);
```

Indexes / constraints:

- PRIMARY KEY: `job_id`.
- UNIQUE partial `uq_jobs_active_target_type` on `(target_approval_id, job_type)` WHERE
  `status IN ('pending','running')` -- at most one active job per target/type.
- INDEX `ix_jobs_dequeue` on `(status, eligible_at)` -- dequeue order.
- INDEX `ix_jobs_retention` on `(retention_class)`.

## 4. Enum Plan

Exact allowed enum values (planned). Enums are created native where the engine supports
CHECK-free enums, else as `varchar` with a CHECK whitelist; either way the value sets are
closed and validated at the boundary.

- **4.1 approval states** (T1.state, previous_state; T3.previous_status / next_status):
  `pending_review`, `approved_execution_blocked`, `rejected`, `expired`, `cancelled`,
  `superseded`, `failed_validation`. There is no `executing`, `executed`, `queued`, or
  `ready_to_execute` value.
- **4.2 action classes** (T1.action_class): `read`, `write`, `write_request`.
- **4.3 execution gate** (T1.execution_gate): `blocked`, `not_authorized`. Only `blocked`
  is reachable in P21.
- **4.4 source status** (T1.source_status; T3.source_status): `valid`, `unknown`,
  `unavailable`, `degraded` -- mirrors the P13 / P14 / P18 source-status vocabulary
  (unknown is never healthy).
- **4.5 validation status** (T1.validation_status; T3.validation_status): `valid`,
  `source_unknown`, `superseded_scope`, `stale`.
- **4.6 retention class** (T1.retention_class; T5.retention_class): `standard`, `long`,
  `legal_hold`.
- **4.7 decision type** (T1.decision, T2.decision, T3.decision): `approve`, `reject`.
- **4.8 audit event type** (T3.event_type): `approval_opened`,
  `approval_decision_recorded`, `approval_quorum_met`, `approval_rejected`,
  `approval_expired`, `approval_cancelled`, `approval_superseded`,
  `approval_failed_validation`, `approval_read`, `approval_exported`, `approval_denied`,
  `approval_purged`. (Closed set, identical to P21-A; no new event semantics.)
- **4.9 audit result** (T3.audit_result): `success`, `denied`, `idempotent`, `conflict`,
  `expired`, `error`. (`idempotent` and `conflict` distinguish a replayed decision from a
  rejected conflicting one; `expired` marks TTL-driven outcomes; `error` is reserved for
  store-level failures that still must be audited.)

Additional enum-like columns: `actor_role` =
`super_admin|support_operator|engineering_operator|system`; `identity_context` =
`identity_only|tenant_contextual|tenant_scoped_token|tenant_admin|system|unknown`;
`storage_class` = `durable|existing_safe|memory`; T4 `scope_key` = `open|decide`; T5
`job_type` = `retention_purge|retention_export|revalidation_sweep`; T5 `status` =
`pending|running|completed|failed|skipped`.

## 5. Constraint Plan

Planned invariants. Each is enforced by schema constraints, by the P21-D adapter, or
both; the test plan (section 9) verifies each.

- **C-R1 raw idempotency key never stored.** Only `idempotency_key_digest` (and
  `decision_digest`) exist; no column, index, log, backup, or audit field may hold the
  raw key. The raw key is hashed at the boundary and discarded.
- **C-R2 redaction before persistence.** Every `reason_redacted` / `metadata_redacted`
  value passes the P10 `redact_metadata` allowlist before INSERT; `redaction_applied =
  true` is NOT NULL with default true on T1 and T3.
- **C-R3 never-persisted list.** Content-scan invariant: no raw secret, DSN, host, port,
  host:port, token, password, cookie, auth header, stack trace, raw exception, or tenant
  business payload in any persisted column (verified by G6).
- **C-R4 tenant_id scoped identifier only.** `tenant_id` is nullable, carries no business
  meaning, and has no FK to any product table; no durable column references
  orders/payments/invoices/customers/inventory/ledgers.
- **C-R5 no raw request bodies in audit.** T3 stores `request_digest` (a hash) and
  redacted reason/metadata only; never the raw P18 request/response body.
- **C-Q1 identity-only super_admin actors.** `maker_actor_id` and `checker_actor_id` are
  populated only from an authenticated identity-only super_admin; the adapter rejects
  support_operator / engineering_operator / tenant-contextual identities and audits
  `approval_denied`.
- **C-Q2 maker cannot be checker.** A decision with `checker_actor_id = maker_actor_id`
  is rejected before INSERT (no self-decision row ever persists), audited as
  `approval_denied`.
- **C-Q3 one decision per checker per approval.** UNIQUE `(approval_id,
  checker_actor_id)`; a repeat is idempotent (C-Q6) or a conflict (C-Q7), never a second
  vote.
- **C-Q4 transactional quorum.** `quorum_met` is recomputed inside the same transaction
  as the decision INSERT, from the committed set of distinct approve checkers excluding
  the maker.
- **C-Q5 quorum floor.** `quorum_required >= 2` for `write` / `write_request`; `>= 1` for
  `read` (if opened); enforced at create and never lowered below the floor.
- **C-Q6 idempotent on digest match.** A repeat decision whose `decision_digest` matches
  the prior row returns the prior result with no new row and no new audit event
  (`audit_result = idempotent`); the UNIQUE `(approval_id, idempotency_key_digest)` and
  `(approval_id, checker_actor_id)` constraints back this.
- **C-Q7 conflicting decisions rejected.** A repeat decision with a differing
  `decision_digest`, or any approve after a reject, is rejected and audited as
  `approval_denied` with `audit_result = conflict`.
- **C-T1 quorum gates approval.** Transition `pending_review ->
  approved_execution_blocked` is allowed only when the transactional distinct-approve
  count crosses `quorum_required` with no reject.
- **C-T2 reject is final.** Once `state = rejected`, no later approve changes state; the
  adapter denies and audits.
- **C-T3 execution_allowed always false in P21.** `execution_allowed` defaults false; no
  P21 code path sets it true. Enforced as an application invariant plus a documented
  guard (a permanent DB CHECK(false) is intentionally NOT added, because it would block a
  future separately-approved execution phase; the column default + adapter invariant + G11
  tests hold the line in P21).
- **C-T4 audit-in-transaction.** Every state transition writes exactly one T3 row in the
  same transaction as the T1/T2 change and bumps `store_version`.
- **C-T5 terminal guards.** `rejected`, `superseded`, `failed_validation`, `expired`, and
  `cancelled` are terminal; no transition revives them (no UPDATE sets state back to a
  non-terminal value).
- **C-T6 executed always false in P21.** `executed` defaults false; no P21 code path,
  trigger, job, or adapter call sets it true; verified by G11.
- **C-L1 approved state is approved_execution_blocked only.** The only "approved" state
  is `approved_execution_blocked`; there is no `approved` / `ready` / `queued` state.
- **C-L2 legal_hold prevents purge.** A T1 row with `retention_class = legal_hold` is
  never selected by `purge_eligible_records`; T5 purge jobs for such rows are dequeued as
  `skipped` and audited.
- **C-X1 no-execution invariant.** Across all tables, constraints, transactions, and
  adapter calls, no operation sets `execution_allowed = true`, `execution_gate != blocked`
  , or `executed = true`, and no operation runs the underlying P18 action.

## 6. Transaction Plan

Future transactional boundaries (implemented in P21-C / P21-D). Each boundary is a single
transaction that commits the request state, the decisions log, the audit event, the
idempotency row, and (where relevant) a retention job together, or rolls them all back.
Race conditions in P21-C / P21-D are handled by a combination of: row-level locking
(`SELECT ... FOR UPDATE` on the T1 row at the start of a decision / transition),
optimistic concurrency (`store_version` bump; a transition whose `store_version` did not
advance is rejected as stale), unique constraints as contention backstops (C-Q3, C-Q6),
and idempotency dedup (C-Q6). There is no two-phase commit beyond the durable store; the
P18 request is referenced, not enrolled.

- **create_request(tx, payload, idempotency_key):** hash idempotency_key and payload at
  the boundary; redact reason/metadata; INSERT T1 (state=pending_review,
  execution_allowed=false, executed=false, store_version=1); INSERT T4
  (scope=open); INSERT T3 (approval_opened, audit_result=success, sequence_no=1); COMMIT.
  Duplicate open with matching payload_digest returns the prior approval (idempotent); a
  differing payload_digest is a conflict (denied). Race: UNIQUE `uq_requests_active_digest`
  and `uq_idem_scope` backstops make a concurrent duplicate open fail one writer, which
  retries/reads the winner.
- **submit_decision(tx, approval_id, checker, decision, idempotency_key):** SELECT FOR
  UPDATE the T1 row; reject if `checker_actor_id = maker_actor_id` (C-Q2), if not
  identity-only super_admin (C-Q1), if terminal (C-T2/C-T5), if a conflicting decision
  exists (C-Q7); else compute `decision_digest`, check idempotency (C-Q6); INSERT T2;
  recompute `quorum_met` from distinct approve checkers excluding maker (C-Q4); if quorum
  crossed and no reject, set state=approved_execution_blocked (C-T1); INSERT T3
  (decision_recorded, and quorum_met if crossed; audit_result=success or idempotent);
  bump store_version; COMMIT. Race: SELECT FOR UPDATE + store_version serialize
  concurrent checkers; exactly one writer crosses quorum; the other sees the updated row
  and records its decision against the new state (no split-brain, verified by G8).
- **quorum_transition:** folded into submit_decision (C-T1) -- there is no separate
  unguarded quorum mutation; quorum is crossed only inside the decision transaction.
- **reject_transition:** the first reject inside submit_decision sets state=rejected
  (terminal, C-T2), decision=reject, and emits `approval_rejected`; later approves are
  denied (C-Q7).
- **expire_transition(job):** SYSTEM actor; SELECT FOR UPDATE pending (or approved past
  durable TTL) rows whose `expires_at` elapsed; set state=expired (terminal); INSERT T3
  (approval_expired); bump store_version; COMMIT. Idempotent via the terminal guard.
- **cancel_transition(tx, approval_id, actor):** maker / super_admin; SELECT FOR UPDATE;
  if pending_review, set state=cancelled; INSERT T3 (approval_cancelled); COMMIT.
- **supersede_transition(tx, new_approval_id, request_digest):** when a new approval for
  the same `request_digest` is created, SELECT FOR UPDATE the prior active approval; set
  state=superseded, superseded_by=new_approval_id; INSERT T3 (approval_superseded);
  COMMIT. Guarded by `uq_requests_active_digest`.
- **purge_export_job(job):** SYSTEM actor; for purge, SELECT eligible terminal rows past
  `durable_retain_until` with `retention_class != legal_hold` (C-L2); whole-record delete
  of T1+T2+T4+T3 rows for that approval in one transaction; INSERT a final
  `approval_purged` T3 row (retained per class) for the bundle; set T5 job status=completed
  ; COMMIT. legal_hold rows are skipped (status=skipped) and audited. Export jobs write a
  redacted bundle and an `approval_exported` event; they delete nothing.

No transaction enrolls the P18 request, mutates the P17 registry, or executes anything.
`execution_allowed`, `execution_gate`, and `executed` are never written to a non-P21
value by any transaction.

## 7. Storage Adapter Interface Contract

Planning-only pseudocode. **No backend files are created in P21-B.** The adapter is the
future seam between the P20-B in-memory / existing-safe skeleton and a durable backend;
P21-D wires it. Every function preserves the no-execution invariant (C-X1): none of them
sets `execution_allowed=true`, `execution_gate!=blocked`, `executed=true`, or runs the P18
action. Return shapes use a `Result[T, StoreError]` convention; `StoreError` codes include
`not_authorized`, `self_decision_denied`, `decision_conflict`, `idempotent_replay`,
`expired`, `terminal`, `unknown_source`, `stale_write`, `read_only`, `not_found`, and
`store_unknown`. Every call appends exactly one audit event (or is itself an audit read).

```text
# Planning-only interface (pseudocode). Not created as a file in P21-B.
DurableApprovalStore:

  create_request(payload, idempotency_key) -> Result[ApprovalRecord, StoreError]
    # Redacts reason/metadata; hashes idempotency_key + payload; opens T1 at
    # pending_review with execution_allowed=false, executed=false. Idempotent on
    # matching payload_digest; conflicting payload_digest -> decision_conflict.
    # Audits approval_opened. Never executes.

  list_requests(filters, page) -> Result[Page[ApprovalRecord], StoreError]
    # Identity-only-super_admin queue read. Support/engineering see only their own
    # scoped rows. Read is redacted and audited as approval_read. Never writes.

  get_request(approval_id) -> Result[ApprovalRecord, StoreError]
    # Returns the durable record (state, maker, checkers, quorum_*, decision,
    # execution_allowed=false, executed=false). Audited as approval_read.

  submit_decision(approval_id, decision, approver_id, reason, idempotency_key,
                  confirm) -> Result[DecisionResult, StoreError]
    # Enforces C-Q1..C-Q7 inside one transaction (section 6). DecisionResult carries
    # the new state, quorum_met, audit_event_id, and a replay flag. Rejects
    # self-decision, conflict, terminal, non-identity-only, and unknown-source writes.
    # Never sets execution_allowed=true or executed=true.

  append_audit_event(event) -> Result[AuditEvent, StoreError]
    # INSERT-only into T3 (append-only). Redacted. Used by the adapter internally and
    # by SYSTEM jobs. Never UPDATE/DELETE (purge is whole-record via purge_eligible).

  find_by_idempotency_digest(scope_key, scope_id, idempotency_key_digest,
                             payload_digest) -> Result[IdempotencyLookup, StoreError]
    # Returns the prior result_ref when (digest) matches and payload_digest matches
    # (idempotent_replay); returns a conflict marker when the digest matches but the
    # payload_digest differs. Raw key is never passed in (caller hashes first).

  expire_due_requests(now) -> Result[int, StoreError]
    # SYSTEM sweep; expires pending rows past expires_at and approved rows past durable
    # TTL to state=expired; emits approval_expired per row. Idempotent.

  purge_eligible_records(now) -> Result[int, StoreError]
    # SYSTEM sweep; whole-record purges terminal rows past durable_retain_until EXCLUDING
    # retention_class=legal_hold (C-L2); emits approval_purged per bundle. Never an
    # operator call; never skips the purge audit event.

  export_record(approval_id, window) -> Result[RedactedBundle, StoreError]
    # Identity-only super_admin; returns ONLY export-safe fields (section 7 of P21-A);
    # never raw key/secret/DSN/host:port/token/password/cookie/auth header/body/payload.
    # Audited as approval_exported. Deletes nothing.
```

Error / idempotency rules: a duplicate `submit_decision` with matching
`decision_digest` returns the prior `DecisionResult` with `replay=true` and writes no new
row/event; a mismatching one returns `decision_conflict`. A `create_request` replay with
matching `payload_digest` returns the prior `ApprovalRecord`. Any call that would violate
C-X1 is unreachable by construction (the adapter exposes no such operation).

## 8. Migration Plan for P21-C

P21-B **does not create migration files.** The following is the plan a future CTO-approved
P21-C must follow.

- **Naming convention.** Migration files live under the platform migration path
  (alembic-style versioned, e.g.
  `YYYYMMDDHHMM_p21c_durable_approval_store.py` or the repo's equivalent monotonic
  revision id), additive only. Five CREATE TABLE statements (T1-T5) plus their enums /
  indexes / unique constraints. No ALTER on existing tables.
- **Target schema.** Platform / public schema only (matches P21-A section 8). A different
  schema requires separate explicit approval.
- **Additive-only rules.** CREATE TABLE / CREATE INDEX / CREATE TYPE / CREATE UNIQUE
  CONSTRAINT only. No ADD COLUMN to, DROP COLUMN from, RENAME, or ALTER of any existing
  product, tenant, payment, auth, or RBAC table. No tenant-schema migration.
- **Rollback expectations.** A tested downgrade that DROPs only the five new tables (and
  their enums/indexes), leaving all existing data intact, plus a documented restore path.
  Rollback must not touch any pre-existing object.
- **Dry-run checks.** A schema-inspection / DDL-preview diff (no data change) run against
  an ephemeral test database before any application outside ephemeral test DBs. The diff
  must show only new objects.
- **Pre-migration validation.** Confirm target DB is at the expected base; confirm no
  `durable_approval_*` objects pre-exist; confirm additive-only DDL preview.
- **Post-migration validation.** Confirm the five tables exist with the exact columns,
  types, nullability, defaults, enums, indexes, and unique constraints from section 3;
  confirm no existing table was altered (schema diff is additions-only); confirm
  `execution_allowed` / `executed` defaults are false; confirm G1 schema tests pass
  against the real schema; confirm rollback downgrades cleanly.
- **Gates (from P21-A section 8, restated).** Additive; no existing product tables
  changed; no tenant schema migration unless separately approved; public/platform schema
  only unless explicitly approved; rollback plan required; dry-run / schema-inspection
  gate required; CTO approval required; no execution / no tenant mutation / no storage
  switch before P21-D.

P21-C creates the tables but does **not** switch runtime storage (P20-B stays in-memory /
existing-safe) and does **not** execute anything. Runtime adapter wiring is P21-D.

## 9. Test Plan for P21-C / P21-D

Test groups with expected counts. P21-B writes no tests; these are the planned groups a
future phase must implement.

- **G1 schema tests (>= 12):** each table has exactly its declared columns, types,
  nullability, defaults, enums, and `extra = forbid` discipline; the unique / index
  objects exist; `execution_allowed` / `executed` default false; no undeclared column.
- **G2 migration dry-run tests (>= 6):** additive-only DDL preview; downgrade removes only
  the five tables; no existing table altered (schema diff additions-only); base-DB
  precondition; idempotent apply; rollback restore path.
- **G3 adapter unit tests (>= 18):** one or more per adapter function in section 7,
  covering happy path, each StoreError code, and idempotency replay.
- **G4 restart persistence tests (>= 5):** pending review, partial quorum, recorded
  decision, audit event, and idempotency row survive a simulated restart; state and
  quorum_met unchanged; restart does not weaken separation or quorum (P21A-Q8).
- **G5 idempotency digest tests (>= 6):** replayed open / decision with matching
  payload_digest is idempotent; mismatching is a conflict; raw key never stored; only the
  digest is present; decision_digest dedup; scope correctness.
- **G6 redaction persistence tests (>= 6):** content scan of every persisted
  reason_redacted / metadata_redacted / audit field against the P10 allowlist returns
  clean; redaction_applied=true everywhere; no raw request body in audit; never-persisted
  list enforced; tenant payload rejected.
- **G7 maker-checker tests (>= 8):** self-decision rejected and never persisted; second
  distinct checker required for write quorum; identity-only super_admin enforced;
  tenant-contextual denied; quorum floor by class; reject is final; cancel by maker;
  separation recorded.
- **G8 quorum race tests (>= 5):** concurrent conflicting decisions serialize to exactly
  one outcome; no split-brain quorum; store_version rejects stale writes; partial approve
  stays pending; concurrent duplicate opens resolve to one.
- **G9 state transition tests (>= 9):** each allowed transition (section 6 / P21-A 6)
  lands with one audit event and a store_version bump; each forbidden transition is
  rejected; terminals are terminal; supersession links superseded_by.
- **G10 retention / purge / export tests (>= 8):** purge fires only after
  durable_retain_until on a terminal record via a SYSTEM job; legal_hold suspends purge
  (C-L2); whole-record purge; approval_purged emitted; export is redacted and audited and
  contains no never-exported field; operator cannot purge; expiry sweep; revalidation
  sweep.
- **G11 no-execution tests (>= 5):** quorum-met approval reaches
  approved_execution_blocked and leaves execution_allowed=false, execution_gate=blocked,
  executed=false; no transition runs the action; no job sets executed=true; the adapter
  exposes no execution operation.
- **G12 no-tenant-mutation tests (>= 5):** no P17 registry / lifecycle / flag / tenant
  business record read or written; tenant_id is a scoped id only and not joinable to
  business tables; no durable column references business tables.
- **G13 API compatibility tests (>= 6):** POST create, GET list, GET by id, POST decision
  preserve P20 response shapes; execution_allowed always false; idempotency durable after
  restart; P20-C frontend needs no semantic change (additive fields only).
- **G14 GitNexus scope tests (>= 2):** detect_changes for the durable store change is
  scoped to the platform durable-approval storage surface; no product / tenant / payment /
  auth / RBAC process is affected.

Total planned tests: >= 101 across G1-G14 (counts are floors).

## 10. Acceptance Criteria

A future phase that implements this plan is accepted only when all hold:

1. **The five planned tables exist exactly as specified** (T1-T5) with the columns,
   types, nullability, defaults, enums, indexes, and unique constraints from section 3
   (G1).
2. **The schema is additive-only.** The migration creates new objects only; no existing
   product / tenant / payment / auth / RBAC table is altered (G2).
3. **`maker_actor_id` and `checker_actor_id` are identity-only super_admin** and the
   maker is never a checker on the same approval (C-Q1, C-Q2; G7).
4. **One decision per checker per approval** via UNIQUE `(approval_id, checker_actor_id)`
   (C-Q3; G7, G8).
5. **Quorum is recomputed transactionally from distinct approve checkers excluding the
   maker**, with the floor enforced by action_class (C-Q4, C-Q5; G7, G8).
6. **The raw idempotency key is never stored**; only `idempotency_key_digest` /
   `decision_digest` exist (C-R1; G5, G6).
7. **Duplicate decisions are idempotent on payload-digest match** and rejected as
   conflicts on mismatch (C-Q6, C-Q7; G5, G8).
8. **Redaction is applied before persistence** to every reason / metadata / audit field;
   `redaction_applied = true` everywhere (C-R2; G6).
9. **No raw secret / DSN / host / port / token / password / cookie / auth header / stack
   trace / tenant payload** is ever persisted (C-R3; G6).
10. **Audit events store no raw request / response body**; only digests and redacted
    reason / metadata (C-R5; G6).
11. **`execution_allowed` is always false** in P21; no code path, job, or adapter call
    sets it true (C-T3, C-X1; G11).
12. **`executed` is always false** in P21; no transition, trigger, or job sets it true
    (C-T6, C-X1; G11).
13. **The only approved state is `approved_execution_blocked`**; there is no
    executing / executed / queued / ready state (C-L1; G9, G11).
14. **Reject is final** for that approval_id; terminals are terminal (C-T2, C-T5; G9).
15. **Every transition commits atomically** with exactly one audit event and a
    store_version bump, and survives a restart in the same state (C-T4, P21A-S6; G4, G9).
16. **`legal_hold` prevents purge**; purge is SYSTEM retention-expiry only and emits
    `approval_purged` (C-L2; G10).
17. **`tenant_id` is a scoped identifier only** with no FK to any product business table;
    no tenant mutation occurs (C-R4; G12).
18. **The migration is reversible** (downgrade removes only the five tables), dry-run /
    schema-inspection gated, platform-schema-only, and CTO-approved (section 8; G2).
19. **API compatibility holds**: P20 response shapes are preserved for create / list /
    get / decision; `execution_allowed` is always false; the P20-C frontend needs no
    semantic change (P21A-A1; G13).
20. **Race conditions are handled**: concurrent decisions serialize to one outcome with no
    split-brain quorum (section 6; G8).
21. **No runtime code, migration file, table, frontend, test, or dependency change ships
    in P21-B**; P21-B is docs and ledger only.

## 11. Counterexamples (must fail or be rejected)

1. **B1 -- a migration file or table created in P21-B.** Any `.py`/`.sql` migration,
   alembic change, CREATE TABLE, or generated DB file added in P21-B -- rejected; P21-B is
   plan / docs only.
2. **B2 -- runtime backend or endpoint change in P21-B.** Any backend code, endpoint, or
   storage switch from the P20-B in-memory / existing-safe store -- rejected.
3. **B3 -- an approved action executing.** Any path that runs the P18 action or sets
   `execution_allowed = true` / `executed = true` -- rejected (C-X1).
4. **B4 -- the raw idempotency key persisted.** Any column / index / log / audit field
   holding the plaintext key -- rejected (C-R1).
5. **B5 -- self-approval persisted.** A decision row with `checker_actor_id =
   maker_actor_id` -- rejected and never persisted (C-Q2).
6. **B6 -- a second vote from the same checker counted.** A repeat decision from the same
   `checker_actor_id` that increments quorum -- rejected; idempotent or conflict only
   (C-Q3, C-Q6, C-Q7).
7. **B7 -- quorum of one on a write.** A `write` / `write_request` approval reaching
   `approved_execution_blocked` with a single checker -- rejected (C-Q5).
8. **B8 -- a split-brain quorum.** Two concurrent conflicting decisions both committing
   because `store_version` was not checked -- rejected; exactly one commits (section 6).
9. **B9 -- a raw secret persisted.** Any persisted reason / metadata / audit field with a
   credential / DSN / host / port / token / password / cookie / auth header / stack trace
   -- rejected (C-R2, C-R3).
10. **B10 -- an audit event storing a raw request body.** A persisted audit field echoing
    the raw P18 request / response body -- rejected (C-R5).
11. **B11 -- `execution_allowed` or `executed` set true.** Any default, trigger, job, or
    adapter call that makes either true in P21 -- rejected (C-T3, C-T6).
12. **B12 -- a non-`approved_execution_blocked` approved state.** Any `approved` / `ready`
    / `queued` / `executing` / `executed` state value -- rejected (C-L1, 4.1).
13. **B13 -- a rejected / terminal approval revived.** A transition moving a `rejected` /
    `superseded` / `failed_validation` / `expired` / `cancelled` row back to a non-terminal
    state -- rejected (C-T2, C-T5).
14. **B14 -- tenant_id joined to business data.** A persisted `tenant_id` that is an FK
    into a product table, or a durable column referencing business tables -- rejected
    (C-R4).
15. **B15 -- legal_hold purged.** A purge job that deletes a `retention_class = legal_hold`
    row -- rejected (C-L2).
16. **B16 -- an operator purge.** Any role (including identity-only super_admin) manually
    deleting a durable record / decision / audit event -- rejected; purge is SYSTEM
    retention-expiry only.
17. **B17 -- an unaudited transition.** Any state change (or denial / purge) landing
    without exactly one T3 row in the same transaction -- rejected (C-T4).
18. **B18 -- an export leaking sensitive data.** An exported bundle with a raw key /
    secret / DSN / host:port / token / password / cookie / auth header / body / payload --
    rejected.
19. **B19 -- a non-additive migration.** A P21-C migration that ALTERs / DROPs / RENAMEs
    any existing table or touches tenant schema -- rejected (section 8).
20. **B20 -- a runtime storage switch in P21-C.** Switching P20-B to the durable backend
    before P21-D and separate approval -- rejected.
21. **B21 -- an AI agent executing or self-approving.** Any AI copilot path that executes,
    sets execution_allowed=true, or decides without an operator -- rejected (section 13).
22. **B22 -- frontend / auth / package changes in P21-B.** Any frontend, auth / RBAC /
    session, or package / lockfile change -- rejected; P21-B is docs and ledger only.

## 12. P21-C Entry Gate

P21-C may implement the **migration only**, and only after explicit CTO approval. P21-C
must:

- Remain **additive** and **public / platform schema only**: CREATE TABLE / INDEX / TYPE /
  CONSTRAINT for T1-T5; no ALTER / DROP / RENAME of any existing object.
- Perform **no tenant schema migration** and touch **no product business paths**.
- **Not switch runtime P20 storage** yet (P20-B stays in-memory / existing-safe) unless
  separately approved; a runtime cutover is P21-D.
- Satisfy every gate in section 8 (rollback, dry-run, pre / post validation) and pass G1
  and G2 against a real (ephemeral-test) schema.
- Not execute any action, not mutate tenant state, and not set `execution_allowed` /
  `executed` true.

**P21-D is the earliest possible runtime adapter wiring phase** (implementing the section
7 adapter against the P21-C tables and switching P20-B's storage_class to durable behind a
separate gate). P21-C must begin from this plan and the P21-A contract and may not change
the tables, columns, types, enums, constraints, state machine, security rules, retention
rules, API compatibility, or audit fields without a new contract / plan revision accepted
by the CTO.

## 13. Future AI Operator Copilot Trace

Planning only. Later, durable approvals will support AI-generated **draft** requests
through this substrate, never around it. The planned trace:

- **tool call trace ID.** Every AI tool call that reads platform state or proposes an
  action carries a `correlation_id` (the tool-call trace id) that becomes the durable
  record's `correlation_id` and is written into T3 audit events. No AI call is
  unattributed.
- **operator confirmation.** The AI may draft a P18 action request, but the durable
  `create_request` lands only after an explicit human identity-only super_admin confirms
  and becomes the `maker_actor_id`. The AI is never the maker and never the checker.
- **approval record linkage.** The AI-proposed draft is linked to the resulting
  `approval_id` / `action_id` via `correlation_id`, so every AI proposal is traceable to a
  human-gated durable approval (and to its decisions and audit events).
- **no direct execution.** There is no AI path to `execution_allowed = true`, no AI
  self-approval, no AI break-glass, and no AI-driven `submit_decision`. Even an
  AI-assisted, quorum-met approval stays `approved_execution_blocked`.
- **audit linkage.** Every AI-assisted open / decision / denial is audited in T3 with the
  AI proposal recorded as redacted `metadata_redacted` and `actor_role` set to the
  confirming operator's role (or `system` for AI-initiated reads). Real execution remains
  separately gated behind a future execution contract that must run through the P16
  governed harness.

This section names a future boundary only. P21-B implements no AI copilot, grants no AI
execution power, and adds no AI-specific runtime or schema artifact.

## 14. Docs-Only and Planning-Only Statement

P21-B is **docs-only and planning-only**. It ships:

- `docs/ai/PLATFORM_PRODUCT_P21_DURABLE_APPROVAL_SCHEMA_PLAN.md` -- this plan.
- `docs/ai/README.md` -- the P21-B entry in the Platform Product Track read order.
- `ai-ledger/platform/2026-06-26_p21b_durable_approval_schema_plan.md` -- the ledger.

There is **no runtime code, no backend, no frontend, no migration file, no table, no
alembic change, no generated DB file, no test code, and no dependency change** in P21-B.
P21-B converts the P21-A contract into an implementation-ready schema / migration /
adapter / test plan; it does not create, execute, persist (beyond the plan), migrate,
switch storage, or implement anything. **Approval is not execution, and durability is not
execution.** Execution is reserved for a separately approved future phase and must run
through the P16 governed harness. **P21-C is not started.**
