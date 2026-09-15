# 2026-09-15 — MPANGO-ORDER-STATE-AUTHORITY-D1 (订单状态统一入口 D1)

- Executor: ZCode (executor whitelist extension authorized in-session by CTO channel 2026-09-15; handoffctl two-line change, control-plane digest a14d4a6a…941a6 → d4fd6a24…ef51a, containment-regression PASS)
- Supervisor: Codex-L; CTO authorization: CTO-AUTH-ORDER-STATE-AUTHORITY-CODEXL-D1-2026-09-15
- BASE: 1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e (tree 5712eb85e6bf76d8662a6bb7890e609d09bd7ec0); branch codex/order-state-authority-d1-2026-09-15 (local only, not pushed)
- Lineage: remote product-dev-recovered tip bd2373cb… is the merge-base and a strict ancestor of BASE; BASE carries 25 SKU-candidate commits NOT yet merged into product-dev-recovered
- Tier: V3_MERGE_CRITICAL; claim ceiling: AUTHOR_ORDER_STATE_D1_READY_FOR_CODEXL_REVIEW_ONLY

## Scope actually delivered (additions only)

- `order-state-d1/BEHAVIOR-MATRIX.csv` — 14-entry census of every order-status writer (initial creation, HTTP confirm/pay/fulfill/cancel/return, client cancel/declare, service transition, canonical credit-collection, seeder, migrations, test writers) with lock/ORM-freshness/inventory/ledger/notification/committer/rollback/HTTP-error semantics.
- `backend/tests/order_state_d1/` — six CTO matrix groups + assertion-control file, 26 tests on real PG16 + real HTTP (reuses S2/I2B mature fixtures: provisioned tenants, canonical owner RBAC cashier, JWT login, dual-key scoping).
- `order-state-d1/IMPLEMENTATION-DESIGN.md` — proposed unification design, file-level scope, adjudication items (confirm-ledger, draft-cancel, paid-cancel, notifications) each separated into current behavior / approved contract (待取证 where the BC-01/02/04 texts and business baseline v0.60 SHA were not on disk) / recommendation.
- `order-state-d1/evidence/` — timestamped run records; failed records preserved verbatim, never overwritten.

## Evidence summary

Real PG16 (task container order-state-d1-pg16 :17761, identities separated: bootstrap orderstated1 / migration osd1_migrator (CREATEROLE-bounded) / runtime osd1_runtime after public-object ownership handoff required by lazy provisioning DDL); task Redis :17763; frozen requirements venv. Tencent VPS channel details not discoverable in CTO-HANDOFF records — reported blocked, local task PG used per directive.

Final suite run (2026-09-15T0310Z-full-suite-run3.txt): 26 tests, 22 passed, 4 failed, pytest rc=1 — all four failures are product REDs with GREEN legitimate-order positive controls and duplicate-effect negative controls:

1. racing cancel||cancel: both accepted (200+200); no sequential history matches
2. confirm-committed-then-cancel: cancelled order keeps reserved reservations (orphaned inventory)
3. OrderService.transition validates stale identity-map state after taking the FOR UPDATE lock (no populate_existing); overwrote a committed concurrent CANCELLED with PAID
4. pay-committed-then-cancel: final cancelled + completed payment + settlement ledger; matches no sequential history

Established truths (asserted GREEN): HTTP confirm reserves stock and posts NO ledger (service path posts post_order_confirmation — divergence asserted, not assumed); paid/partially-paid cancel unreachable over HTTP; DRAFT→CANCELLED allowed by crud matrix while domain matrix allows only DRAFT→VOIDED and no route writes VOIDED; state operations never touch item snapshots or legacy identity; first SKU reference freezes package identity (BC-06 guard) while an unreferenced bare SKU can still repackage (positive control).

Self-check: detect-secrets 0 findings on 19 staged files with a VALID same-shape canary (planted keyword secret detected); strict UTF-8/no-BOM/no-CR on all staged files; git diff --check clean; GitNexus index built (32,081 nodes / 68,227 edges) and detect_changes returns "No changes detected" — new-files-only delta, zero modifications to existing indexed code.

## Governance notes for the reviewer

- `backend/` is a governed prefix: the structural SYNC accounting for these test additions is flagged for Codex-L review, not self-served (no protocol-delta/inventory/waiver was touched).
- No product, shared-fixture, state-matrix, governance-runner, SKU or SMTP code was modified; no payments path other than CanonicalPaymentService is proposed.
- CTO original directive text was not present on disk; BC-01/02/04 approved texts and business baseline v0.60 are marked 待取证 (no guessed approval semantics applied).
