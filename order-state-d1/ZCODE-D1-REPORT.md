# ZCODE-D1-REPORT — MPANGO-ORDER-STATE-AUTHORITY-D1

Author evidence by ZCode. Claim ceiling:
`AUTHOR_ORDER_STATE_D1_READY_FOR_CODEXL_REVIEW_ONLY`. Not a fix claim, not
an independent-verification claim, not an authorization for product
implementation.

## 1. Identity & baseline

| Field | Value |
|---|---|
| Authorization | CTO-AUTH-ORDER-STATE-AUTHORITY-CODEXL-D1-2026-09-15 |
| TASK_ID | MPANGO-ORDER-STATE-AUTHORITY-D1 |
| Supervisor / reviewer | Codex-L |
| Executor | ZCode (executor whitelist extended in-session per CTO-channel authorization 2026-09-15; disclosed below) |
| BASE | 1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e |
| BASE tree | 5712eb85e6bf76d8662a6bb7890e609d09bd7ec0 (verified after fetch) |
| Branch | codex/order-state-authority-d1-2026-09-15 (from exact BASE; local only) |
| Worktree | /home/ivy/Documents/Codex/worktrees/mpango-erp/MPANGO-ORDER-STATE-AUTHORITY-D1 |
| Tier / ceiling | V3_MERGE_CRITICAL / AUTHOR_ORDER_STATE_D1_READY_FOR_CODEXL_REVIEW_ONLY |
| product-dev-recovered | bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f — merge-base and strict ancestor of BASE; BASE additionally carries 25 SKU-candidate commits (BC-06 R2/R2-R1, fixture isolation, integration) NOT merged into product-dev-recovered |

No same-name task branch or HANDOFF registration existed (checked before
creation). HANDOFF dir `CTO-HANDOFF/MPANGO-ORDER-STATE-AUTHORITY-D1/`
managed by the existing six-file `handoffctl` rules.

**Tooling disclosure:** handoffctl's executor whitelist (Codex-L,
OpenCode2) did not admit ZCode; after in-session CTO-channel authorization
I made a two-line minimal extension (init validation + verify schema) —
control-plane digest `a14d4a6a…941a6` → `d4fd6a24…ef51a`,
containment-regression PASS after the change, event recorded. Codex-L
should re-pin or ratify the digest.

**Evidence gap (待取证):** the CTO original directive text, the approved
originals of BC-01/02/04, and business baseline v0.60 (CTO-given SHA not
available to me) were not found on disk. No approval semantics were
guessed; adjudication items carry the gap explicitly.

## 2. Phase 1 — source & behavior reconciliation

Deliverable: `order-state-d1/BEHAVIOR-MATRIX.csv` (14 entries; columns:
allowed-from, target, read path, lock, ORM refresh, inventory, ledger,
notifications, committer, rollback, HTTP codes, identity/snapshot notes,
source anchors). Census: initial creation (wholesaler + client HTTP,
seeder), online state changes (5 wholesaler endpoints, client
cancel/declare), the service writer, canonical credit-collection (no
status write), historical migration 003 (one-time data rewrite; 016/033
are enum-DDL/validation only), and test writers catalogued as non-product.

Mandated focus points, resolved:

1. **HTTP confirm keeps its inventory reservation** — `reserve_on_confirm`
   runs in the same request transaction (GREEN-asserted). It is NOT true
   that "all side effects are bypassed"; what HTTP confirm lacks is the
   ledger posting.
2. **Service-confirm accounting differs from HTTP** —
   `OrderService.transition(CONFIRMED)` posts `post_order_confirmation`
   (receivable/revenue); the HTTP route writes status + reservation only.
   The two are asserted as different; the design does NOT wire them as
   equivalent and flags the decision to the CTO (adjudication item A).
3. **The two matrix differences** — (a) DRAFT→CANCELLED: allowed by the
   crud matrix used by HTTP cancel; the domain matrix permits only
   DRAFT→VOIDED (and VOIDED is unreachable from any HTTP route today);
   (b) PAID/PARTIALLY_PAID→CANCELLED: allowed by the domain matrix
   ("with refund logic" that does not exist anywhere in the codebase) and
   unreachable via HTTP (409, GREEN-asserted).
4. **Lock order & transaction boundary** — pay locks the orders row first
   (locking read is the request's first read); fulfill/return go through
   the service lock (fulfill additionally pre-expires the ORM object,
   return does not); confirm/cancel take NO lock at all and validate
   stale pre-loaded objects; inventory locks per-item stock rows sorted by
   sku_code (FOR UPDATE + populate_existing, SKU/CatalogProduct joined for
   identity + active checks); packaging/price modifications serialize on
   the shared `skus` row lock (`lock_sku_row`), and the FIRST SKU
   reference (order-item insert at creation, inside the creating
   transaction) freezes package identity per the BC-06 history rules.
5. **Identity field** — `order_items.sellable_unit_id → skus.id` (FK
   RESTRICT); state operations touch only status/updated_by: no repricing,
   no snapshot overwrite, no legacy-identity rewrite (GREEN-asserted incl.
   the legacy-item confirm fail-closed rollback).

## 3. Phase 2 — minimal real regression evidence

Infrastructure: task-owned PG16 container (127.0.0.1:17761) and Redis
(17763); identity separation bootstrap `orderstated1` / migration
`osd1_migrator` (CREATEROLE-bounded; REPORTING_USER_PASSWORD provided;
public objects ownership-handed to runtime after the lazy provisioning
DDL requirement was discovered) / runtime `osd1_runtime`; platform
migrations 001→038 applied (head 038, matching BASE expectations). Tencent
VPS channel: details not discoverable in CTO-HANDOFF records — reported
blocked; local task PG used per directive. Shared mpango_postgres:5432 and
other tasks' containers untouched.

Tests: `backend/tests/order_state_d1/` — six matrix groups + controls; real
HTTP (ASGI + JWT via canonical owner RBAC cashier; reuses the S2/I2B
provisioned-tenant fixtures); event barriers with bounded waits
(`asyncio.timeout`), no ordering sleeps; direct-service proofs state their
boundary in the module header.

**Final run (evidence/2026-09-15T0310Z-full-suite-run3.txt): 26 tests —
22 passed, 4 failed, pytest rc=1.** The four failures are the product REDs
(KNOWN_REDS below); every one has a legitimate-order positive control and
duplicate-effect negative control GREEN in the same suite, and the residue
oracles are proven to fire on planted rows.

Test-path map (group → file): baseline → `test_matrix_1_confirm_cancel_baseline.py`;
races → `test_matrix_2_double_connection_races.py`; locked-ORM freshness →
`test_matrix_3_locked_orm_freshness.py`; whole-request rollback →
`test_matrix_4_whole_request_rollback.py`; identity/snapshot/packaging →
`test_matrix_5_identity_snapshot_packaging.py`; pay-cancel race →
`test_matrix_6_payment_cancel_race.py`; helper controls →
`test_matrix_assertion_controls.py`; shared helpers → `support.py` +
`conftest.py` re-exports.

## 4. Phase 3 — implementable design

`order-state-d1/IMPLEMENTATION-DESIGN.md`: make `OrderService.transition`
the only status writer; add `populate_existing` to its locking read
(closes the stale-after-lock class, mirroring the codebase's own
`lock_sku_row` pattern); move the cancel release-decision inside the lock;
endpoints keep endpoint-level inventory hooks and the middleware stays the
single committer; CRUD action helpers retire. Estimated product file
scope: services/order_service.py, api/v1/orders.py,
api/v1/client/orders.py, crud/order.py (+ test follow-ups). Adjudication
items separated as current-behavior / approved-contract / recommendation /
CTO-decides: (A) confirm ledger posting, (B) DRAFT-cancel + VOIDED
reachability, (C) paid-cancel boundary with a data-driven prior-paid==0
guard, (D) notification timing. Payments remain exclusively on
CanonicalPaymentService; no new refund/cash event/second SKU guard.

## 5. KNOWN_REDS (product defects, assertions kept as-is)

| ID | Test | Evidence |
|---|---|---|
| R1 | test_race_cancel_cancel_must_match_sequential_history | both cancels accepted (200+200); no sequential history matches |
| R2 | test_race_confirm_then_cancel_last_writer_orphans_reservation | cancelled order keeps `reserved` reservations (orphaned inventory) |
| R3 | test_preloaded_session_transition_uses_stale_state_current_defect | transition validates stale identity-map state after FOR UPDATE; overwrote committed CANCELLED with PAID |
| R4 | test_race_pay_committed_then_cancel_overwrites_current_defect | cancelled + completed payment + settlement ledger; no sequential history matches; no refund path |

## 6. UNCOVERED_PATHS

- Tencent VPS PG channel (blocked: connection details not in discoverable records).
- BC-01/02/04 approved originals; business baseline v0.60 verification (待取证).
- CTO original directive document (only the ZCode supplement was available).
- Browser/E2E surfaces; frontend state rendering; reporting/bootstrap suites.
- Governance structural-gate accounting for the new `backend/tests/order_state_d1/` additions (governed prefix) — deliberately left for Codex-L; no protocol delta/waiver/inventory was touched.
- The 4 REDs' fixes (this round's ceiling is evidence + design only).

## 7. Command log (argv → rc → summary; full records in evidence/)

| argv (sanitized) | time (UTC+8) | rc | summary |
|---|---|---|---|
| git fetch origin --prune | 09:33 | 0 | refs updated |
| git branch codex/order-state-authority-d1-2026-09-15 1ee75d9f… + worktree add | 09:35 | 0 | HEAD at BASE |
| handoffctl init … L0 CONTRACT_FROZEN … | 09:36 | 0 | six-file task registered |
| docker run order-state-d1-pg16 (postgres:16-alpine :17761) | 09:43 | 0 | task PG ready |
| docker run order-state-d1-redis (:17763) | 09:52 | 0 | PONG |
| alembic upgrade head (as osd1_migrator; +CREATEROLE after 011) | 09:5x | 0 | head=038 |
| pytest tests/test_dc12r1_s3_s1…::TestHappyPathPreserved (smoke) | 09:5x | 0 | 2 passed (after ownership handoff; earlier env iterations recorded in session transcript) |
| pytest tests/order_state_d1/test_matrix_1… (iterative dev runs) | 10:0x | 1→0 | fixture/decimal/bind fixes; final 6 passed |
| pytest tests/order_state_d1/test_matrix_2… | 10:07–10:12 | 1 | R1/R2 RED confirmed; race1 GREEN; gate-design bug fixed en route |
| pytest tests/order_state_d1/test_matrix_3… | 10:2x | 1 | positive control GREEN; R3 RED (DID NOT RAISE) |
| pytest tests/order_state_d1/test_matrix_4… | 10:3x | 0 | 4 passed (incl. oracle negative control) |
| pytest tests/order_state_d1/test_matrix_5… | 10:3x | 0 | 4 passed (bare-seed positive control) |
| pytest tests/order_state_d1/test_matrix_6… | 10:4x | 1 | sequential controls GREEN; R4 RED |
| pytest tests/order_state_d1/ (full, run1/run2/run3) | 10:27–11:10 | 1 | final: 26 tests, 22 passed, 4 failed |
| detect-secrets scan <19 staged files> | 11:3x | 0 | 0 findings |
| detect-secrets scan <canary> (same shape) | 11:36 | 0 | 1 finding — canary VALID |
| encoding check (19 files) | 11:37 | 0 | strict UTF-8, no BOM, no CR |
| git diff --check / --cached --check | 11:37 | 0 | clean |
| gitnexus analyze --skip-agents-md | 09:2x | 0 | 32,081 nodes / 68,227 edges |
| gitnexus detect_changes (eval-server; staged/unstaged/compare) | 11:3x | 0 | "No changes detected" — new-files-only delta |

Handoff `commands.tsv` carries the sanitized categories/rc; this report's
table is the author's consolidated log.

## 8. Environment & cleanup

- Task containers order-state-d1-pg16 / order-state-d1-redis: left RUNNING
  for Codex-L review reproduction (throwaway, task-owned; no shared
  resources touched). Delete with `docker rm -f order-state-d1-pg16
  order-state-d1-redis` after review.
- Scratch: /home/ivy/Documents/Codex/scratch/MPANGO-ORDER-STATE-AUTHORITY-D1/
  (venv from frozen requirements.txt, logs) — outside the repo.
- Worktree/branch: local, single ordinary commit, NOT pushed (per contract).

## 9. Handback

AUTHOR_ORDER_STATE_D1_READY_FOR_CODEXL_REVIEW_ONLY. Requested next gate:
Codex-L review of (1) the four REDs' acceptance-test framing, (2) the
implementation design and its adjudication items, (3) the handoffctl
executor-whitelist digest change, (4) the governance accounting path for
the governed-prefix test additions.
