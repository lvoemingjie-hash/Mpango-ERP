# Mpango ERP Project Status

**Last updated:** 2026-09-22
**Status owner:** CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Protected product branch tip:** `bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f` (live fetch on 2026-09-22; it is an ancestor of the reviewed integration candidate and has not been moved by the Order R2 integration work)
**Current reviewed integration candidate:** `5c93763ded903cc4e903d67997f1528d09ddc4b8` (tree `e6444326ac2c023b610fc1d796b595439fcf0c22`)
**Published candidate branch:** `origin/codex/order-r2-dbauth-r2g-e1-final-candidate-20260922`
**Order R2 + DB-authority integration branch:** `origin/codex/order-state-r2-e1-source-revision-f1-f3-20260919@5c93763d`
**Integration result:** `PASS_EXACT_FAST_FORWARD` - the target moved from `2df6a3bf` to `5c93763d` with 40 linear commits, zero merge commits, no content rewrite, and a report-only receipt at `origin/reports/order-r2-dbauth-r2g-e1-ff-merge-receipt-20260922@66b396e0`
**Composite verification result:** `PASS_FOR_CTO_ORDER_R2_DB_AUTHORITY_R2G_E1_FINAL_COMPOSITE_V3_RECONCILIATION`
**Separate revocation/stock candidate:** `a516d2b3257f782ce068e71e8730c05541f08931` (tree `6a412568cd2c50fcf1d92103d989603a5b819e60`) passed its bounded independent V3 line but is not an ancestor of `5c93763d`; integration is still a deliberate gate
**Current reviewed candidate database head:** `039_order_credit_holds` (migration `038_catalog_identity_vertical_slice` is its parent)
**Deployment status:** NOT AUTHORIZED; no production or customer environment is claimed
**Delivery state:** Pre-pilot MVP hardening; not yet approved for customer delivery

This file is the continuously maintained source of truth for product status,
accepted capabilities, delivery blockers, and ordered work. Detailed execution
evidence belongs in `ai-ledger/`. Durable product philosophy belongs in
`docs/ai/PROJECT_MEMORY.md` and `decision-register/`.

## 1. Executive Summary

Mpango is beyond prototype stage. The wholesaler ERP, tenant isolation,
financial invariants, credential lifecycle, retailer identity, supplier-scoped
retailer login, stable catalog/SKU identity, order-state authority, per-order
credit holds, read-only retailer finance visibility, and the payment-declaration
maker-checker loop are materially implemented.

The reviewed integration candidate now combines Order R2 with the hardened
tenant-bootstrap and database-authority topology. The runtime application uses a
zero-write entrypoint, a read-only readiness gate, explicit runtime/reporting
database URLs, and a five-stage setup path owned by separate authority roles.
The target integration branch was fast-forwarded exactly to the reviewed
candidate after the final composite V3 reconciliation.

The current product is still pre-pilot. The reviewed integration candidate has
not been promoted to `product-dev-recovered`, deployed, or accepted by a
customer. Final workspace polish, the real-mailbox browser journey, customer
HTTPS deployment, the formal DB-OPS package, tenant branding, current manuals,
and named human support coverage are not all closed.

Current engineering truth:

- The wholesaler remains the primary customer and value owner.
- A retailer operates inside one selected wholesaler relationship at a time.
- Mpango does not expose a cross-supplier comparison workspace.
- Retailer catalog, negotiated price, orders, payments, and balances are scoped
  by the contextual JWT, active binding, and tenant schema.
- Retailer finance reads remain server-authoritative and relationship-scoped.
  A retailer may submit a non-authoritative payment declaration, but no client
  route can settle it, mutate a ledger, or alter receivables; only cashier
  confirmation may enter the canonical payment transaction.
- A merged SHA is not a deployed SHA. Runtime delivery requires exact-SHA
  deployment evidence.
- Pricing and downstream ordering semantics remain contract-gated. The next
  authorized step is a business-contract and acceptance-test mapping, not
  product implementation.

## 2. Product Position

### Primary value owner

The wholesaler is the primary customer and future payer. Mpango helps a
wholesaler operate orders, inventory, payments, receivables, reporting, staff
permissions, and a private downstream retailer channel.

### Retailer role

The retailer is an invited operational participant. Retailer UX reduces order
friction and improves wholesaler throughput and retention; it must not turn
Mpango into a retailer-facing price-comparison marketplace.

A retailer may have independent relationships with multiple wholesalers, but:

- each relationship has a private catalog, negotiated price, order, payment,
  receivable, and operational context;
- one wholesaler cannot read another wholesaler's data;
- retailer login selects one supplier portal and receives one contextual JWT;
- the product does not generate a cross-supplier comparison view;
- Mpango cannot prevent a human from manually sharing information they already
  know, but it must not aggregate or disclose that information for them.

The positioning decision is recorded in
`decision-register/2026-07-23_wholesaler-private-channel-positioning.md`.

### Platform operator role

Platform operators maintain service health, tenant lifecycle, support,
backups, restores, incidents, and controlled operations. They are not ordinary
tenant users. Early pilot customers may be manually onboarded and supported;
subscription billing is outside the current MVP.

## 3. Branch and Environment Map

| Item | Current truth |
|---|---|
| Protected product baseline | `origin/product-dev-recovered@bd2373cb`; this branch was not moved by the Order R2 + DB-authority integration |
| Reviewed integration candidate | `5c93763d`, tree `e6444326`; final composite V3 reconciliation accepted the candidate |
| Integrated contract branch | `origin/codex/order-state-r2-e1-source-revision-f1-f3-20260919@5c93763d`; strict fast-forward receipt `66b396e0` |
| Separate revocation/stock candidate | `origin/zcode/mpango-mvp-invariants-r1-auth-stock-fix-2026-09-08@a516d2b3`; independently verified but not contained in `5c93763d` |
| Protected-tip rule | Every new task fetches live remote refs, states which baseline it uses, and starts in a clean isolated worktree. A task must not silently equate the reviewed integration branch with `product-dev-recovered` or a deployed environment |
| Main | `origin/main@134ea59e`, not promoted |
| Platform historical branch | `origin/platform-dev@12c5ee55`, not the active product baseline |
| Alembic head | Reviewed integration candidate head `039_order_credit_holds`; parent chain includes `038_catalog_identity_vertical_slice` -> `037_payment_declarations_schema` |
| Windows default workspace | Dirty; read-only for controlled work |
| Controlled work | Clean isolated worktrees only |
| Tencent mainland VPS | Development, validation, or disaster-recovery role |
| Customer MVP hosting | Non-mainland HTTPS environment remains to be selected and closed |

Every runtime task must verify the deployed SHA independently. Do not infer
deployment state from a merged branch.

## 4. Capability Status

| Area | Status | Current truth |
|---|---|---|
| Tenant isolation | Strong foundation; revocation candidate separately verified | Schema-per-tenant, validated identifiers, contextual JWTs, and binding guards are integrated. Candidate `a516d2b3` independently verifies active-user/active-tenant revalidation but is not an ancestor of `5c93763d`; identity-only refresh, logout, and password-reset session invalidation remain open |
| Tenant bootstrap and DB authority | Integrated candidate independently verified | Migration authority owns shared database objects; runtime bootstrap is fail-closed, public-DDL-free, and runs only after the five-stage setup and read-only verification contract |
| Wholesaler authentication | Implemented | Login, tenant selection, setup/reset, and terminal-token handling |
| Wholesaler credential recovery H2-B | Merged and browser-verified | Forgot/reset password chain, anonymous reset 401 no-redirect, multi-replica reset atomicity, and role-assignment `MissingGreenlet` closure merged at `436d61e2` |
| Credential email links | Source complete; runtime pending | Absolute fragment links and query rejection are merged |
| Users and RBAC | Implemented | Tenant roles exist; retailer permissions are isolated as `client:*` |
| Orders | R2 authority integrated and V3 reconciled | Locked-fresh state transitions, per-order credit holds, cancel/collection checks, and canonical payment/declaration interaction are represented through migration `039`; pricing extensions remain closed |
| Payments | Financially hardened | Canonical methods, idempotency, replay, partial payment, and ledger invariants |
| Receivables | Financially hardened | Non-negative exposure and collection semantics protected by migration `035` |
| Inventory and catalog | Stable SKU identity integrated; stock fix separate | Migration `038`, catalog-product/SKU separation, package identity guards, and public API provisioning are integrated. Concurrent stock-update protection was independently verified on separate candidate `a516d2b3` and is not in `5c93763d`; duplicate-return and cross-tenant cache isolation remain open |
| Reporting and exports | Implemented | Supported provisioning and sanitized worker/runtime boundaries |
| Retailer identity S1 | Merged | Invitation, setup/reset, verified email, authoritative mapping, migration `036` |
| Retailer private login S2 | Merged | One supplier portal, one contextual JWT, no `available_tenants` |
| Retailer workspace S3-S1 | Merged | Catalog/order ownership hardening and exact route/RBAC contracts |
| Retailer finance S3-S2 | Merged | Read-only payment history and server-authoritative relationship balance |
| Retailer payment declaration schema foundation | Merged | Migration `037` provides declarations, receipt sequences, and receipt numbers |
| Canonical payment transaction extraction I2A | Merged | `CanonicalPaymentService` owns the reusable mutation core; direct pay behavior is preserved and invalid amounts fail before DB access |
| Payment declaration and cashier confirmation I2B | Merged | Retailer declaration remains non-authoritative; cashier confirm/reject is supplier-scoped; confirmation uses the canonical atomic payment path and allocates a receipt |
| Printable business records | Backend and browser A-D merged | Read-only order, declaration, eligible receipt, and relationship-statement print data plus browser-print UI are available |
| H7 setup and dependency reconciliation | Merged and independently verified | Native setup ran twice on Lubuntu; cross-host focused gates and post-merge evidence are zero-red |
| HE2 authority governance | R3+A1 merged and independently verified | Backend CWD/temp-DB inputs and profile-bound Alembic head/parent are checked by runner and child; invalid environments VOID before product execution |
| Combined runtime topology | Composite V3 accepted on `5c93763d` | Zero-write entrypoint, read-only readiness, explicit public-frontend/reporting URL wiring, reporting-role read-only checks, five-stage setup, S `243/21`, O `27/27`, and D `22/22` evidence reconciled; this is composite evidence, not one uninterrupted full-suite run |
| Local deployment and browser rehearsal | Automated browser gate closed | Fresh-runtime Playwright evidence passed `162/162` for source `f51c109`, merged as `a29f8db0`; human acceptance remains and no VPS delivery is claimed |
| Retailer workspace closure | Responsive shell and credential closure merged; next contract gate active | Mobile navigation, overflow, and the H2-A/H2-B credential lineage are closed; pricing/ordering semantics now require a refreshed contract and acceptance-test map before implementation |
| Retailer end-to-end S4 | Partially closed | Local real-JWT browser matrix is green; real mailbox and deployed HTTPS journey on the latest SHA remain |
| Platform operator schema | Foundation merged | Migration `034` tables exist |
| Platform operator runtime | Incomplete | Dedicated login/JWT/guard/frontend lifecycle remains |
| DB operations | Partial | Evidence exists, but one approved access/backup/restore/monitoring package remains |
| Tenant branding | Not implemented | Legal profile, logo, dual branding, and controlled configuration remain |
| User manuals | Incomplete | Wholesaler, retailer, and operator guidance must match deployed behavior |
| AI-native operations | Planned | Requires trustworthy data, permissions, approvals, audit, and rollback first |

## 5. Accepted Engineering Milestones

### 2026-09-22 Order R2 + DB-authority integrated candidate

The reviewed candidate `5c93763d` (tree `e6444326`) is the accepted integration
line for Order R2, catalog/SKU identity, tenant bootstrap, database authority,
runtime readiness, reporting access, and their test-trust closures. The frozen
Order E1 contract target was moved from `2df6a3bf` to `5c93763d` by strict
fast-forward only; receipt commit `66b396e0` records the before/after refs,
40-commit linear range, zero merge commits, tree identity, fsck, diff-check, and
clean-worktree proof.

The final result is a composite V3 acceptance, not a claim that one uninterrupted
envelope ran every gate on the final test-only successor. Accepted evidence
includes the combined runtime S partition (`243 passed / 21 skipped`), O
partition (`27/27`), final D partition (`22/22`), five reporting-identity
conservation scenarios, zero product drift across the late test-only successors,
and independent source/falsification reviews. Full-suite and browser runtime were
not rerun in the final closure round.

This milestone closes the integration line. It does not promote
`product-dev-recovered`, authorize deployment, or authorize pricing and new
ordering implementation.

### DC-10 and DC-11 foundation

- Export worker tenant-context restoration and sanitized errors.
- Canonical payment-method integrity.
- Finance and receivable scope protection.
- Payment replay, concurrency, idempotency, partial-payment, and ledger safety.
- Receivable collection integrity in migration `035`.
- Reporting/bootstrap test-contract repair.
- Deterministic backend gate on fresh PostgreSQL and Redis.
- Platform operator schema foundation in migration `034`.

### DC-12 customer-entry and retailer workspace

- Wholesaler-private-channel product positioning.
- Absolute fragment-based credential links and query-token rejection.
- Retailer identity, invitation, credentials, role, and mapping foundation in
  migration `036`.
- Supplier-scoped retailer login and private portal context.
- Structured public error contract and rate-limit 429 boundary.
- Catalog/order dual-key hardening and exact client route allowlist.
- Read-only retailer payment history and authoritative relationship balance.
- Non-authoritative retailer payment declarations with idempotent replay.
- Supplier-scoped cashier confirmation/rejection through the canonical payment
  transaction, including atomic receipt allocation and retailer-visible status.
- Read-only, server-authoritative print-data Contracts A-C for orders,
  declarations, and eligible confirmed receipts.
- Browser-printable retailer and supplier views for Contracts A-C, including
  response-authoritative cashier receipt navigation and route-boundary tests.

### DC-12R1-H4 post-merge test-contract forensics and repair

Forensic investigation identified two latent test-contract defects masked by
event-loop state leakage from a prior session:

- H4-R1: four `asyncio.run` calls in the I1 real-Alembic upgrade test bypassed
  the session-scoped event loop and corrupted pool isolation. Replaced with
  `run_coroutine` and added a dedicated regression suite.
- H4-R2: three `run_alembic_upgrade(config, "head")` calls in the S1-R5
  migration preflight test over-upgraded past the contract pin revision `036`,
  masking rollback semantics. Replaced with `REV_036` and removed two stale
  sole-head assertions.
- H4-R2-R1: evidence-ledger correction adding CTO GitNexus cross-environment
  confirmation.

Full suite after H4 repair: `3116 passed`, `48 skipped`, `15 xfailed`,
zero red, zero errors (two identical runs on independent stacks).

### DC-12R1-S3-S2B-I2C-I1 printable records backend

Merged as `e923fd8567637ecc87b40d775caa8860b10821a0`.

Delivered:

- six read-only supplier and retailer routes for order, declaration, and
  receipt print data;
- server-authoritative money, status, and UTC/EAT display fields;
- fail-closed receipt eligibility across declaration, payment, order, and
  active relationship binding;
- no client-calculated financial fields and no print-path mutation.

I2C-I1 deliberately excludes browser print UI, Contract D relationship
statements, events/outbox, SMS/WhatsApp delivery, migration `038`, and
deployment. Lubuntu independently validated the exact source in a full clone:
two fresh-stack backend gates each reported `3216 passed`, `48 skipped`,
`15 xfailed`, zero failures, and zero errors.

### DC-12R1-S3-S2B-I2C-I2 printable workspace

Merged as `0dc245114ec7442ebb1dea16e9332d95ddb3a6fe`.

Delivered:

- browser-printable retailer and supplier order, declaration, and eligible
  receipt views consuming only the read-only Contracts A-C;
- string-only financial display without client-side numeric conversion or
  recomputation;
- static retailer/supplier route ownership, neutral print errors, and no
  financial mutation from printing;
- response-authoritative cashier confirmation-to-receipt navigation through
  the real application router.

Kilo independently closed the final source/test-authenticity review at
`d1e5f518`. Lubuntu independently validated source invariants, eight mutation
checks, `63` focused tests, `223` full frontend tests, and a successful build at
report `12460e0c`. Post-merge checks repeated the `63` focused tests, full
frontend suite, production build, secrets, pre-commit, and GitNexus gates.

### DC-12R1-S3-S2B-I2C-I2B Contract D relationship statement

Merged as `adcc7f281c661897ad050a8278686375b611edb5` from approved source
`133ca46be0c664be0118365dfcef85ce76e60379` after Kilo review `a56078c6`
and Lubuntu independent verification `b652b683`.

Delivered:

- read-only supplier and retailer relationship statements over an inclusive
  date range;
- one server-authoritative opening and closing balance computed from immutable
  receivable ledger movements;
- independent `movements[]` and canonical `settled_payments[]` lists, with no
  inferred receipt-to-ledger association;
- fail-closed ownership, ledger-scope, arithmetic, reconciliation, date-range,
  and line-cap boundaries;
- browser-print rendering with string-safe money display and zero financial
  mutation.

Two independent fresh PostgreSQL 16 and Redis 7 full-backend gates each
reported `3285 passed`, `48 skipped`, `15 xfailed`, zero failures, and zero
errors. The final frontend gate reported `270 passed` and a successful
production build.

### DC-12R1-MVP-L1-PW1-R4-C1-R1 responsive MainLayout closure

Merged as `a29f8db02365737c64d0d8d442e8ef48a8a19d6d` from approved source
`f51c10943b5d1a67569d681e66a6d56e728860b4`. The merge has parents
`9067e38f` and `f51c109`; its tree is byte-identical to the reviewed source.

Delivered:

- responsive wholesaler MainLayout without mobile horizontal-overflow masking;
- mobile off-canvas navigation with pointer-click, Escape, backdrop, route
  close, and focus restoration;
- a mobile-reachable logout path using the existing auth-store action;
- visible-first-landmark DOM ordering compatible with the frozen browser
  harness;
- desktop fixed sidebar behavior preserved at `lg+`.

Accepted evidence: Kilo source review `5cff172a`, OpenCode fresh-runtime
browser package `0e1c7ed8`, Kilo evidence review `b0b1ff4f`, and controlled
merge report `046fe7de`. The authoritative browser run used one worker, zero
retries, and passed `162/162` nodes after Auth `27/27`, drawer `25/25`, and
stability `10/10` pre-gates. Three non-blocking observations remain recorded:
desktop focus order changed, desktop exposes two equivalent Logout controls,
and the mobile drawer declares `aria-modal` while the external hamburger stays
interactive.

### DC-12R1-MVP-L1-J1-H2-B password recovery and test-hygiene closure

Merged as `436d61e2dfed88a9469e4572615b98b9c4a7aed4` from approved source
`25626f4d9245a9b15cce92300fcdff8a5eb95de9`. The merge has parents `6e9470a1`
and `25626f4d`; its tree is byte-identical to the reviewed source.

Delivered:

- the wholesaler forgot/reset password chain closed end to end, including the
  standalone `j1h2b-forgot-reset` neutrality harness;
- anonymous reset 401 responses no longer wrongly redirect to the login page;
- multi-replica password-reset token consumption is atomic and deterministic;
- the user role assignment `MissingGreenlet` async serialization defect is
  closed with a pinned regression suite;
- associated test-residue attribution and temporary-database teardown/stability
  fixes close the lineage's test-hygiene debt.

Accepted evidence: Kilo source review `d6289a6b`, authoritative backend
`90f96e3f` (3773 collected / 3710 passed / 48 skipped / 15 xfailed, zero red),
authoritative browser E1 `04134016` (24/24 browser nodes PASS, 29-node
inventory reconciliation gap=0), and controlled merge report `c400b7c5`.
At that milestone, the retained debt was full-suite post-state 4/0/29
test-hygiene residue, `RT0 = BLOCKED_BY_H2_C`,
`REMOTE_ENFORCEMENT_NOT_VERIFIED`, and no deployment/VPS/real-device
acceptance. H2-C was subsequently integrated; the line remains here only as
historical evidence context.

### DC-12R1-MVP-L1-HE2-ET1-R3+A1 authority governance closure

Merged as `d9dc2e4130ea87a57d433dfadeb2f2736576fac6` from approved source
`483b8ab01dae41d52404ebfe197e205a16d56e85`. The merge has parents
`cdb39e96` and `483b8ab0`; its tree is byte-identical to the reviewed source.

Delivered:

- canonical backend CWD, `MPANGO_ENV`, safe test-database name, host and
  temp-DB port allowlist checks before authority;
- independent runner and pytest-child rechecks with drift-to-VOID behavior;
- protected profile bytes as the sole Alembic head/parent authority, with no
  CLI or environment override;
- exact revision and declared-parent lineage validation, rejecting multi-head,
  wrong-parent, prefix-similar and whitespace variants;
- separate H2-C (`037`) and future SKU-M1 (`038 -> 037`) authority profiles.

Accepted evidence: Kilo `db87f0d3` independently ran 186/186 governance tests
and 102 RED / 9 GREEN mutation controls. Lubuntu `6fb1e31e` used fresh
PostgreSQL 16 and Redis 7, passed core 8/8 and Redis 7/7, and proved 17/17
negative controls VOID with zero authority-command launches. Merge report:
`1017be0c`. Product migration `038` and SKU implementation are not included.

## 6. Latest Validation Snapshot

The current reviewed integration tree is `e6444326` at candidate `5c93763d`.
The final composite V3 reconciliation binds the accepted runtime product bytes
to the final test-trust successor and closes the Order R2 + DB-authority line.
The contract target was then fast-forwarded exactly to that commit; receipt
`66b396e0` records local, tracking, and remote equality plus tree identity.

Accepted current evidence:

- S partition: `243 passed`, `21 skipped`, zero failures/errors;
- Order partition: `27/27`;
- DB-authority partition: `22/22` in the frozen original order;
- five reporting-identity conservation scenarios, including body and restore
  failure paths, with task-role residue zero after normal teardown or rescue;
- entrypoint refusal before setup, five-stage setup to exact head `039`, runtime
  readiness before Uvicorn, health/auth checks, and read-only reporting identity;
- final critical product blobs unchanged across the late fixture/test-only
  corrections.

`FULL_SUITE_RESULT` and `BROWSER_RUNTIME` were not rerun in the final closure
round. This evidence does not prove deployment, protected-branch promotion,
real-mailbox HTTPS delivery, or customer readiness.

### Retained historical validation

The H2-B product tree `436d61e2` remains an accepted ancestor. Its merge tree
equals source `25626f4d`. The authoritative backend gate reported 3773
collected, 3710 passed, 48 skipped, 15 xfailed, zero red. The authoritative
browser gate reported 24/24 browser nodes PASS with the 29-node inventory
reconciliation gap=0 (24 browser + 5 non-browser). This proves the merged
source tree for the password-recovery lineage. It does not prove deployment,
VPS networking, HTTPS, real-device acceptance, or customer readiness. At that
time, retained debt was 4/0/29 test-hygiene residue (external attribution;
module replay restores 0/0/0), `RT0 = BLOCKED_BY_H2_C`, and
`REMOTE_ENFORCEMENT_NOT_VERIFIED`. H2-C was subsequently integrated.

At the R4-C1-R1 merge, the reviewed product tree was `a29f8db0`. Its merge
tree equals source `f51c109`. The accepted local browser evidence used fresh
PostgreSQL 16 and Redis 7 data, real staging JWT authentication,
lifecycle-provisioned W1/W2/RA/
RB identities, Alembic head `037`, and the frozen seven-file Playwright harness.
The result was `162 passed`, zero failures, zero skips, one worker, and zero
retries; JSON, JUnit, the 162-row CSV, and the committed SHA-256 manifest
reconciled with accounting gap zero. This proves the automated local browser
journeys for that merged source. It does not prove human usability,
real-mailbox delivery, VPS networking, HTTPS, or customer readiness.

Contract D source `133ca46b` passed Kilo adversarial source/test-authenticity
review and Lubuntu independent runtime verification. The independent gate
proved the focused Contract D and generator bundle in both orders, the accepted
`192`-node financial regression bundle on two stacks, two identical full
backend runs at `3285 passed`, `48 skipped`, `15 xfailed`, zero failures and
zero errors, `270` full frontend tests, and a successful production build. The
reviewed tree was merged as `adcc7f28`; post-merge compile, generator/CSV,
frontend, build, secrets, pre-commit, and GitNexus gates passed.

Earlier financial-runtime evidence remains accepted:

I2B-R5-R1 validation ran twice on independent fresh PostgreSQL 16 and Redis 7
stacks after the final test-evidence integrity correction:

| Metric | Run A | Run B |
|---|---:|---:|
| Passed | 3180 | 3180 |
| Skipped | 48 | 48 |
| XFailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |

The final source `c65c87cb` was independently runtime-verified by Lubuntu and
independently source-reviewed by OpenCode, then merged with `--no-ff` into
`origin/product-dev-recovered` as:

`753048f029c4eede86fb11857677db57b865900e`

Alembic sole head remains `037_payment_declarations_schema`. The merge tree is
byte-identical to the reviewed source. Focused post-merge evidence includes the
I2A/I2B/H5 bundle at `64 passed` in both orders, lifecycle regressions at
`30 passed`, frontend Vitest at `160 passed`, and a successful production
frontend build. The independent source review recorded five INFO findings,
zero blocking findings, and an accounting gap of zero.

The accepted runtime now proves that declaration submission has zero financial
effect before confirmation; supplier-scoped cashier confirmation/rejection is
available; confirmation enters the existing canonical transaction atomically;
and confirmed payments receive replay-safe receipt numbers.

This proves the merged source tree. It does not prove customer deployment or a
real browser/mailbox journey.

## 7. Current Delivery Blockers

### P1 product journey blockers

1. A non-developer has not yet completed the full wholesaler-to-retailer
   business journey without technical assistance; invitation creation,
   customer pricing initialization, and other first-order friction must be
   measured before feature scope is chosen.
2. The latest SHA has not passed the full invitation/setup/reset/login/order/
   payment/finance journey through a real mailbox and deployed HTTPS runtime.
3. Pricing and downstream ordering rules have not yet been re-frozen against
   the accepted Order R2/SKU/DB-authority candidate. Implementation must wait
   for one business-rule -> task -> acceptance-test contract.

### P1 operational blockers

1. The intended non-mainland customer HTTPS environment is not yet canonical.
2. DB access, backup, restore, monitoring, retention, incident response, and
   safe AI-agent actions are not one approved DB-OPS package.
3. Dedicated platform operator runtime authentication is incomplete.
4. User manuals and operator runbooks do not yet match final deployed behavior.
5. `deploy_vps.sh` and `reset-staging.sh` still carry legacy migration/runtime
   authority assumptions and are outside the accepted five-stage setup contract.
6. Production Compose replacement and PostgreSQL image digest pinning remain
   separately authorized deployment work.
7. The reviewed integration candidate is not yet promoted to
   `product-dev-recovered`; any such promotion requires an explicit identity and
   history gate.

### Tracked known debt (preserved, non-blocking)

1. The final composite conclusion did not rerun the full suite or browser
   runtime on `5c93763d`; it inherits accepted product-byte evidence and adds
   fresh targeted closure evidence.
2. Revocation/stock candidate `a516d2b3` passed its six targeted repairs but is
   a separate line, not an ancestor of `5c93763d`. Its integration remains a
   deliberate decision. Concurrent duplicate-return single economic effect,
   cross-tenant cache isolation, identity-only refresh, logout revocation, and
   password-reset session invalidation remain open.
3. `REMOTE_ENFORCEMENT_NOT_VERIFIED`: remote/server-side enforcement is not
   verified.
4. No production/VPS deployment or real-device acceptance exists for the
   reviewed integration candidate; no customer-ready or release-approved status
   is claimed.
5. External product-number cross-reference/bulk establishment and the explicit
   single-person refund exception are deliberately excluded from the first
   release, not silently missing requirements.

### Important but later

- Subscription and billing automation.
- Multi-warehouse expansion.
- Retailer staff sub-roles such as buyer, inventory clerk, and finance
  reconciler.
- Automated KYC and self-service tenant branding.
- SMS or WhatsApp transaction notification delivery.
- AI-native conversational mutations.
- Internal-first screenshot/screen-recording issue reports, with explicit
  upload/view permissions, retention, access audit, and sensitive-data policy.

## 8. Ordered Work Plan

### Frozen business decisions (Jeff, 2026-09-16)

| Decision | Current truth |
|---|---|
| P01 first-release markets | Kenya and Uganda. Both use `Africa/Nairobi` (EAT, UTC+3, no DST). Money precision is market-specific: KES uses 2 decimal places; UGX uses 0. Discount and rounding rules must consume the currency precision and must never create fractional UGX |
| P02 external product identifiers | Not in the first release. Schedule as a fast follow after the SKU delivery line is stable; a named customer may receive a separately scoped implementation if required |
| P03 single-person refund exception | Not in the first release. Refund maker and approver remain separate people; no generic single-person-mode switch is authorized |
| P04 tenant data retention | Configurable default of one year from tenant termination plus completed handoff. Deletion requires traceable notices, named ownership, escalation for no response, and manual final reconciliation; contract or legal obligations may override the default |
| P05 pilot support ownership | Jeff is the current primary human owner. No real human backup is yet available. AI may monitor and alert but must not be presented as the backup decision-maker or substitute for human account reconciliation |

The proposed screenshot/screen-recording feedback mechanism is a separate
internal-first feature. It is not part of P05 or incident recovery and has no
implementation authorization until access, privacy, retention, and audit rules
are frozen.

### Stage 1: Complete the retailer MVP loop

#### DC-12R1-S3-S1 - catalog and order hardening (completed)

Merged in the product history leading to `44ec07ff`. Catalog/order reads and
writes are supplier-scoped, use authoritative identities, and preserve the
retailer permission boundary.

#### DC-12R1-S3-S2 - read-only retailer finance (completed)

Merged as `0f9d259b4a6c20584721c53b59ba94c510d1970d`.

Delivered:

- read-only `GET /api/v1/client/payments`;
- read-only `GET /api/v1/client/finance/balance`;
- dual-key supplier/retailer predicates;
- server-authoritative Decimal balance;
- status-aware cash labels;
- no payment write, ledger, settlement, or receivable mutation.

#### DC-12R1-S3-S2B-D - payment declaration contract (completed)

This is a design/audit gate before implementation because it introduces a new
financial workflow.

The contract must define:

- a retailer declaration as non-authoritative evidence, not a canonical
  payment;
- cashier confirm/reject as the only transition that may invoke the canonical
  payment write path;
- exact idempotency, concurrency, overpayment, replay, and maker-checker rules;
- immutable status history and rejection reason boundaries;
- retailer-visible pending/confirmed/rejected states;
- confirmed receipt versus unconfirmed declaration terminology;
- printable order, declaration, receipt, and account-statement requirements;
- event hooks for future SMS/WhatsApp without implementing delivery;
- an explicit decision to remove, retain, or replace the currently unused
  `client:payments:create` permission;
- migration requirements, rollback/forward-fix strategy, and an
  implementation/test matrix.

The design gate is complete and approved as the contract input for implementation work.

#### DC-12R1-S3-S2B-I1 - schema foundation (completed)

Merged as `9528cb6de5f668ed09feb7a1eaa9aafaa537987d`.

Delivered:

- migration `037_payment_declarations_schema`;
- declaration, receipt-sequence, and receipt-number schema foundation;
- no frontend/runtime activation.

#### DC-12R1-S3-S2B-I2A - canonical payment transaction extraction (completed)

The existing direct pay-order financial mutation path is now extracted into a
reusable `CanonicalPaymentService` without changing current wholesaler payment
behavior. This stage prepares the declaration-confirmation transaction core
but does not expose declaration routes.

Merged as `b03a3b5c078a3824d333b541ccacf19b668c9f9c`. The final I2A-R3
source passed exact full-suite validation on two independent fresh stacks:
`3134 passed`, `48 skipped`, `15 xfailed`, zero red, zero errors (identical
totals both runs). The canonical service rejects non-positive and non-finite
amounts before any financial read or mutation.

#### DC-12R1-S3-S2B-I2B - declaration runtime and confirmation closure (completed)

Merged as `753048f029c4eede86fb11857677db57b865900e`.

Delivered:

- relationship-scoped retailer declaration submission with stable idempotency;
- zero financial effect before cashier action;
- supplier-scoped cashier confirmation/rejection;
- canonical atomic payment, order, ledger, receivable, and settlement effects;
- rollback-safe, replay-safe confirmed receipt allocation;
- retailer-visible pending, confirmed, and rejected states;
- two identical independent full backend gates at `3180 passed`, `48 skipped`,
  `15 xfailed`, zero failures, and zero errors.

#### DC-12R1-S3-S2B-I2C-I1 - printable records backend (completed)

I2C-I1 merged as `e923fd8567637ecc87b40d775caa8860b10821a0` after independent
full-clone validation. It delivers read-only backend Contracts A-C for supplier
and retailer order, declaration, and receipt print data. Receipt rendering
fails closed unless the declaration, canonical payment, order, and active
binding are consistent and receipt-eligible.

#### DC-12R1-S3-S2B-I2C-I2 - browser-printable workspace (completed)

Merged as `0dc245114ec7442ebb1dea16e9332d95ddb3a6fe` after Kilo source review
and Lubuntu independent runtime verification. It delivers frontend views and
browser-print behavior for the existing read-only Contracts A-C without
recalculating finance or issuing a financial mutation.

This slice excludes Contract D statements, events/outbox, SMS/WhatsApp delivery,
new migrations, dependencies, backend financial changes, and deployment.

#### DC-12R1-S3-S2B-I2C-I2B - Contract D relationship statement (completed)

Merged as `adcc7f281c661897ad050a8278686375b611edb5`. The accepted implementation
provides read-only supplier and retailer relationship statements from immutable
receivable ledger movements, keeps movements and settled payments independent,
retains historical accounting scope, and fails closed instead of rendering a
partial or inconsistent statement.

#### DC-12R1-S3-S2B-I2C-I3 - future notification-event closure (deferred)

This remains outside the current MVP. Transactional outbox storage, event
emission, provider integration, and SMS/WhatsApp delivery require a separate
post-MVP CTO authorization. Existing event-shape decisions do not authorize an
implementation, migration, queue, dispatcher, or financial mutation path.

#### DC-12R1-MVP-L1 - automated local browser rehearsal (completed)

Source `f51c109` passed the frozen `162`-node Playwright matrix on a fresh local
runtime and was merged as `a29f8db0`. The automated gate covers wholesaler and
retailer authentication, catalog/order, payment declaration, isolation,
printing, responsive behavior, and logout paths. It is not a human acceptance,
real-mailbox, VPS, HTTPS, or customer-delivery claim.

#### DC-12R1-MVP-L1-J1 - real business journey friction audit (completed)

The J1 friction-audit lineage is merged through `c5b66d26`, and the
J1-H2-A-R2 credential closure (dual-entry retailer self-join and invitation
closure, Kilo findings F1-F4) is merged as `6e9470a1`. Follow-on journey
observations are folded into the pre-delivery queue below (first-use
onboarding and full business journey / VPS / real-device final acceptance).

#### DC-12R1-MVP-L1-J1-H2-B - password recovery and test-hygiene closure (completed)

Merged and browser-verified as `436d61e2`; see Section 5 for the full record.

#### Pre-delivery execution queue (refreshed 2026-09-22)

The former H2-C/SKU/Order/DB-authority parallel lines have converged in reviewed
candidate `5c93763d`; the contract target fast-forward is complete. The ordered
next work is:

1. `PROJECT-TRUTH-SYNC` - update this source of truth and reconcile the merge
   receipt (this document change).
2. `REVOCATION-STOCK-INTEGRATION-R0` - read-only/source-design gate. Compare
   the three product paths in `a516d2b3` with `5c93763d`, map overlapping auth,
   tenant, inventory, and test semantics, and decide whether to reapply or
   supersede each fix. No cherry-pick or product edit in R0.
3. `REVOCATION-STOCK-INTEGRATION-R1` - only if R0 requires it, create a bounded
   successor on the exact current integration baseline and rerun its V3 gates.
4. `PRICING-AND-ORDERING-CONTRACT-R0` - docs/tests/design only. Freeze the
   authoritative event table, old-contract/RBAC compatibility, business-rule ->
   implementation-task -> acceptance-test mapping, KES/UGX precision, base
   price, customer special price, immutable order-price snapshot, bounded price
   adjustment, retailer confirm/reject/timeout, cancellation/collection effects,
   and reorder price re-resolution. No migration or product code.
5. `BASELINE-PROMOTION-DECISION` - before implementation, CTO must name the
   exact implementation base (`5c93763d` integration line or a separately
   approved promotion into `product-dev-recovered`) and freeze its tree.
6. `PRICING-R1` - only after R0 acceptance, implement SKU base price and one
   retailer-specific price without weakening tenant/RBAC boundaries.
7. `ORDER-PRICE-R1` - implement the approved one-shot order adjustment and
   customer decision lifecycle; preserve immutable accounting snapshots.
8. `REORDER-R1` - create a new draft from history with current-price
   re-resolution; never mutate the historical order.
9. First-use onboarding, human pilot rehearsal, and full business journey.
10. Separate deployment-readiness line: production Compose, deployment scripts,
   image digest pinning, HTTPS, backup/restore, monitoring, and exact-SHA proof.

Queue ordering is project truth, not implementation authorization. Each product
slice still requires its own CTO scope, risk tier, verification tier, frozen
base, and independent acceptance gate.

#### DC-12R1-S3-S3-D - branded workspace and residual UX closure (after J1)

Responsive wholesaler navigation is merged. After J1, define a bounded plan for
remaining relationship-brand context, invitation/pricing usability, financial
state language, empty/error states, and accessibility observations. Reuse
Contracts A-D and existing financial services; do not duplicate print views or
change financial semantics without a separate contract gate.

#### DC-12R1-S4 - end-to-end delivery closure

Deliver fresh migration, real invitation and credential email, browser login,
catalog, order, declaration, cashier confirmation, retailer receipt visibility,
printing, two-wholesaler isolation, and sanitized runtime evidence.

### Stage 2: Establish human-plus-AI DB operations

- Named human and AI-agent responsibility matrix.
- Least-privilege production access and break-glass process.
- Encrypted backup policy, retention, and restore drill.
- Migration preflight, maintenance mode, and rollback decision tree.
- Database health, storage, backup-age, and error monitoring.
- Incident ledger and prohibition on direct business-data edits outside
  approved replayable artifacts.

### Stage 3: Tenant identity, branding, and onboarding UX

- Legal/business profile and controlled operator review.
- Logo validation and safe asset storage.
- Mpango plus tenant dual-brand entry experience.
- Controlled asset replacement and configuration UX.
- Current wholesaler, retailer, and operator manuals.

Manual operator review is acceptable for the first one or two pilot
wholesalers. Automated billing and automated KYC are not pilot prerequisites.

### Stage 4: Non-mainland pilot deployment

- Region selected for Kenyan latency, reliability, support, and legal fit.
- Customer domain, DNS, TLS, backups, monitoring, and alert ownership.
- Exact-SHA deployment and rollback proof.
- One or two controlled wholesaler pilots with named support contacts.

### Stage 5: AI-native operating layer

Start only after reliable operational data and action boundaries exist.
Initial capabilities should be read-only assistance, guided data entry,
anomaly summaries, and approval-required typed actions. No unrestricted SQL,
shell, payment mutation, or tenant impersonation.

The long-term architecture should extend the same private tenant-to-customer
relationship kernel upward to supplier networks and downward to retailer
consumer channels. That is a post-MVP design direction, not authorization to
expand the current product scope or weaken isolation boundaries.

## 9. Role and Ownership Model

| Role | Responsibility |
|---|---|
| CTO/Codex | Architecture, scope, risk, contracts, merge, release verdict, project truth |
| Zcode product line | Bounded product/test corrections and author-side evidence on explicitly authorized paths |
| Codex-L supervisor | Order, SKU, authority, and contract source review; candidate truth and STOP enforcement within allocated capacity |
| Fresh Kilo reviewer | Non-overlapping source, falsification, PG16/runtime, and evidence review; author PASS is never inherited |
| Product coding agent | Other bounded implementation/design slices on isolated branches |
| Independent Lubuntu validator | Fresh DB, full-suite, cross-environment, and browser evidence |
| OPS agent | Deployment, DNS/TLS, backup/restore, monitoring, and runtime evidence |
| Jeff / human owner | Current primary pilot owner; credentials, mailbox, domain, legal data, business decisions, and production authorization |
| Human backup | Not yet staffed; must be named and trained before backup coverage is claimed |
| AI monitoring | Monitoring and alerting only; not a human backup, financial approver, or account-reconciliation authority |
| Wholesaler pilot owner | Business workflow acceptance and operational feedback |

No agent's self-reported PASS is sufficient by itself.

## 10. Non-Negotiables

- No cross-tenant or cross-supplier disclosure.
- No client-supplied wholesaler or retailer authority.
- No payment declaration represented as received or settled.
- No canonical financial mutation outside the approved atomic payment path.
- No negative receivable exposure represented as valid customer debt.
- No query-string credential tokens.
- No silent schema repair inside a read-only validation gate.
- No dirty-worktree merge or deployment.
- No hidden skip, xfail, deselection, or assertion weakening.
- No secrets, credentials, raw exceptions, or private row contents in reports.
- No protected push without explicit human approval.
- No pricing or new ordering product change before
  `PRICING-AND-ORDERING-CONTRACT-R0` is accepted against an exact frozen base.
- No fractional UGX. Currency precision and discount rounding are authoritative
  configuration, not UI formatting.
- No first-release single-person refund exception; maker and approver remain
  separate human identities.
- No claim that the integration target, protected product branch, and deployed
  runtime are the same object unless each ref/SHA is independently proven.
- No migration `038` or `039` acceptance without exact ancestry, single-head
  proof, preflight, rollback/no-partial-mutation evidence, and independent
  authority execution.
- No authority execution after failed CWD/temp-DB/profile/Alembic/PG/Redis or
  runner-child binding preflight.
- No claim that merged code is deployed without exact runtime SHA proof.

## 11. Document Maintenance

Update `docs/ai/CTO_CURRENT_OPS.md` after every meaningful active-task change.
Update this file when the product baseline, migration head, accepted feature
stage, delivery blocker, deployment role, roadmap, or product trust decision
changes.

Do not append raw transcripts. Replace stale status with current facts.
Historical command output belongs in `ai-ledger/`.
