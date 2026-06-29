# P21-D-a Durable Approval Runtime Adapter Discovery + Design Lock

Date: 2026-06-29
Phase: P21-D-a (discovery + design lock only). Locks the design of the P21-D
runtime adapter -- the wiring of the existing P20-B in-memory store surface to
the merged P21-C1 durable tables -- BEFORE any P21-D runtime slice may begin,
exactly as P21-A locked the store contract and P21-B locked the schema plan
before any P21-C migration. P21-D-a is docs-only: no runtime code, no ORM model
registration, no migration, no table, no test code, no execution, no storage
switch, and no auth/RBAC/tenancy/payment change.
Branch: codex/auto-p21da-discovery-design-lock-20260629-095843
Base: platform-dev at fc9eb40 (P21-C1.1 merged: the additive, reversible,
public-schema-only 020_durable_approval_store migration is live; the five
durable tables and fifteen enum types exist in public).
Scope: three files only:
  - docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md (new)
  - docs/ai/README.md (P21-D read-order entry + gating paragraph)
  - ai-ledger/platform/2026-06-29_p21da_discovery_design_lock.md (this ledger)

Approval is not execution, and durability is not execution. No controlled action
is ever run. A runtime storage cutover is reserved for a separately approved
P21-D-2 slice.

## 0. Authorization (supervised dispatch)

This P21-D-a docs-only design-lock run is a SUPERVISED DISPATCH that was
explicitly authorized by the user AND by the Codex CTO for this automation test.
The prior "SHADOW MODE" / "SHADOW ONLY" text applied to Goose's automatic
dispatch boundary (P21-D0), NOT to this now-authorized Claude worker run. This
note is recorded so future reviewers do NOT treat this dispatch as
self-authorization: Claude did not start any runtime slice on its own. It was
dispatched by the user + Codex CTO, with a narrowly scoped remit, to (a) keep the
change docs / design-lock only (no runtime adapter implementation), (b) run and
record the missing pre-commit gates, (c) commit the LOCAL branch only with a
docs(platform) message, and (d) NOT push and NOT merge platform-dev. No runtime
slice, no execution, no storage switch, no tenant mutation, no push, and no
platform-dev merge was authorized or performed. This honors section 8: no P21-D
runtime slice may begin without explicit CTO approval, and P21-D-1 is not
started.

## 1. Discovery (what P21-D rewires)

Code-grounded surface recorded in the design lock (section 3 of the contract),
all under backend/api/v1/platform/p20/:

  - services.py: the running durable approval store is three module-level globals
    -- _STORE (approval_id -> _StoredDurableApproval), _STORE_BY_CREATE_KEY
    (create idempotency digest -> approval_id; raw key never stored), and
    _AUDIT_LOG (flat list of DurableApprovalAuditEvent). The records are plain
    __slots__ objects, NOT ORM models; there is no database table and no
    session.
  - Four public operations: create_durable_approval (async, already receives db),
    submit_decision / read_durable_approval / list_durable_approvals (all sync,
    none receive db today). The sync -> async ripple on the latter three is the
    single unavoidable runtime change and is contained to services.py + routes.py.
  - schemas.py: the response models the adapter must preserve --
    DurableApprovalRecord, DurableApprovalQueue, CheckerDecisionSummary,
    DurableApprovalAuditEvent (all extra="forbid") -- plus the closed
    vocabularies (states, decisions, action classes, identity contexts, actor
    roles, source statuses, validation statuses, execution gates, retention
    classes, event types).
  - routes.py: four endpoints behind require_platform_operator_with_p20_audit
    (P10 identity-only guard + access-denied audit), each already injected with
    db: AsyncSession = Depends(get_db). create already awaits its service call;
    list / read / decision call the service synchronously.

Durable target (already merged, P21-C1): the five public-schema tables in
backend/alembic/versions/020_durable_approval_store.py. Columns with no direct
in-memory counterpart that the adapter must populate: store_version,
storage_class, sequence_no, audit_result, confirm, metadata_redacted, and the
structured durable_approval_idempotency_keys (scope_key open|decide, scope_id,
payload_digest, result_ref).

P18 dependency boundary: services.py imports api.v1.platform.p18 and uses
_item_for, _redact_reason, _sanitize_text, redact_metadata, get_stored_request,
known_action_type, _resolve_action_source_status. P21-D rewires the durable
APPROVAL store only; the P18 REQUEST store and redaction helpers are consumed
unchanged.

## 2. What the design lock freezes (section 4 of the contract)

  - Boundary: the three in-memory globals map to the durable tables, behind the
    SAME four service functions. No new public operation.
  - Operation mapping: create inserts request + approval_opened audit + open
    idempotency in one tx; decide inserts decision + decide idempotency, bumps
    store_version, updates state/quorum/last_audit_event_id, appends audit
    events in one tx; read/list are read-only and emit approval_read.
  - Concurrency: single-transaction atomicity + store_version optimistic locking
    for the quorum race (no split-brain); P21-C1 unique constraints backstop
    distinct-checker and idempotency.
  - New-column population rules (store_version per transition; sequence_no
    monotonic per approval; storage_class = durable; audit_result derived
    without information loss; confirm and metadata_redacted persisted; raw
    metadata never persisted).
  - API compatibility: the four DurableApproval* response models unchanged;
    durability metadata additive (storage -> durable; optional storage_class /
    restart_safe); execution_allowed / executed always false; the sync -> async
    change is internal.
  - Unknown/degraded/read-only fallback: unknown is never healthy; degraded
    badge + unavailable_reason = store_unknown; never fabricate a healthy state.
  - P18 boundary: approval store only.

## 3. Slice map + CTO gate (section 8 of the contract)

P21-D-a (docs-only design lock) -> P21-D-1 (ORM models + adapter impl, runtime,
CTO-gated, still no cutover, no execution) -> P21-D-2 (runtime storage cutover,
CTO-gated) -> P21-D-future (retention jobs, export, supersession, AI copilot;
each separately approved). No runtime slice may begin without explicit CTO
approval. This honors the P21-D0 "await explicit Codex/user signal" instruction.

## 4. Relationship to P21-D0 (Goose Middleman)

P21-D0 (codex/platform-p21d0-goose-middleman-config-2026-06-29, status
shadow_complete) stood up a project-local Review Bus (.review/ mailbox + Goose
recipe + deterministic PowerShell runner) as governance / coordination
infrastructure. It is NOT the durable approval runtime adapter and wires no
runtime storage. P21-D-a governs the runtime adapter only. P21-D0's outbox said
"SHADOW ONLY -- DO NOT START P21-D1" and "await explicit Codex/user signal before
proceeding"; P21-D-a is a docs-only design lock (not P21-D1 implementation) and
reaffirms the CTO gate on every runtime slice.

## 5. Risk

LOW. P21-D-a is docs-only. It changes no runtime behavior, no migration, no
table, no test, no dependency, no auth/RBAC/tenancy/payment path, no configured
secret baseline, and no product-dev-recovered path. The design lock is a
planning artifact; the only downstream effect is that a future P21-D runtime
slice must implement against it (or revise it via a new accepted design-lock
revision).

## 6. Stop conditions

None triggered:
  - The design lock required no file outside the three allowed paths.
  - No runtime code, migration, model, frontend, package, lockfile, or baseline
    file is changed.
  - No execution path and no storage switch are introduced.
  - The P21-D0 "await signal" instruction is honored (no runtime slice started).

## 7. Verification and pre-commit gate evidence (docs-only change)

P21-D-a is docs-only. The gates below were run/recorded for this supervised
dispatch. Base ref: HEAD == origin/platform-dev == fc9eb40 (the committed range
is empty; the change is the three working-tree files below). Origin/platform-dev
resolves to fc9eb402be4f7694acb2e55c2384eabf8db83903; merge-base(origin/
platform-dev, HEAD) == fc9eb40 (the declared base).

Changed file set (`git status --porcelain`):
  M  docs/ai/README.md
  ?? ai-ledger/platform/2026-06-29_p21da_discovery_design_lock.md
  ?? docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md

  - **Scope audit:** only the design-lock .md (new), docs/ai/README.md
    (read-order entry + gating paragraph), and this ledger. No backend / frontend
    / alembic / tests / package / lockfile / baseline / product path touched.
  - **git diff --check origin/platform-dev..HEAD:** CLEAN (no output = no trailing
    whitespace, no space-before-tab, no conflict markers). The committed range is
    empty (HEAD == base), and the working-tree README change
    (`git diff --check -- docs/ai/README.md`) is also clean. The two NEW
    untracked files cannot be seen by `git diff --check` until staged
    (`git add -N` was permission-gated in this sandbox), so they were verified
    whitespace-clean by the equivalent content scan: trailing-whitespace pattern
    `[ \t]+$` = 0 hits each; conflict-marker scan for merge-marker starts
    also returned 0 hits.
  - **Non-ASCII scan of the three changed files:** 0 hits. Pattern
    `[^\x00-\x7F]` = 0 matches in docs/ai/README.md, the design-lock .md, and
    this ledger. Pure ASCII, per the platform convention.
  - **No self-referential commit SHA embedded:** short SHAs / descriptions only
    (fc9eb40 is the BASE, not this commit).
  - **Forbidden-path audit (structured, over the changed file set): PASS.** All
    three paths are under docs/ai/ or ai-ledger/platform/. NONE is under
    backend/, frontend/, alembic/, src/, tests/, package.json, package-lock.json,
    pnpm-lock.yaml, .secrets.baseline, decision-register/, product-dev-recovered,
    or any auth / RBAC / session / tenancy / payment / registry path. No runtime
    code, migration, ORM model, frontend, test, package, lockfile, or baseline
    file is changed.

  - **detect-secrets (configured baseline `.secrets.baseline`, pre-commit
    v1.5.0):** PASS. Codex CTO reran the configured-baseline scan after the
    worker handoff:
    `detect-secrets-hook --baseline .secrets.baseline docs/ai/README.md
    docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md
    ai-ledger/platform/2026-06-29_p21da_discovery_design_lock.md`. Exit code 0;
    no findings. The `.secrets.baseline` file is unmodified and is not in the
    changed file set.

  - **GitNexus (`npx gitnexus analyze` + staged `detect_changes`):** PASS / LOW.
    Codex CTO reran `npx gitnexus analyze` from the P21-D-a worktree before
    commit: 7,721 nodes / 23,678 edges / 496 clusters / 300 flows; status up to
    date at base commit `fc9eb40`. After commit, GitNexus was refreshed again at
    `2fb0cea`: 7,724 nodes / 23,678 edges / 499 clusters / 300 flows. GitNexus
    MCP `detect_changes(scope="staged")` before commit and
    `detect_changes(scope="compare", base_ref="origin/platform-dev")` after
    commit both returned changed_count 32,
    affected_count 0, changed_files 3, risk_level low, affected_processes [].
    All changed symbols are markdown file/section nodes in docs/ai/README.md,
    docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md,
    and this ledger. No backend / frontend / alembic / test / product / auth /
    RBAC / tenancy / payment / registry process is affected.

## 8. Final statement

P21-D-a is the docs-only discovery + design lock for the P21-D durable approval
runtime adapter. It records the exact P20-B runtime surface the adapter rewires,
freezes the adapter design (boundary, operation mapping, concurrency, new-column
population, API compatibility, fallback, P18 boundary), defines the gated slice
map, and reaffirms that no P21-D runtime slice may begin without explicit CTO
approval. There is no runtime code, no model registration, no migration, no
storage switch, no execution, no tenant mutation, no auth/RBAC rewrite, no
frontend, and no package / lockfile change. Approval is not execution, and
durability is not execution. P21-D-1 is not started.
