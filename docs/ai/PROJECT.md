# Mpango ERP Project Status

**Last updated:** 2026-08-14
**Status owner:** CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Current reviewed product-code baseline:** `ea9908263d57737e434d7d61e06e5f0ee941aa81` (the accepted DC-12R1-H7 controlled merge; fetch the live protected tip and verify this commit is its ancestor before new controlled work)
**H7 status: MERGED_AND_CLOSED** - controlled merge `ea990826` has parents `a6ef3aac` and `a0a14e4d`, and its tree is identical to the reviewed source. Accepted evidence: Kilo `8b04a92b`, Lubuntu native setup `189852da`, Lubuntu Phase-4 zero-red `4fa13dac`, post-merge H7 bundle 325/325, and GitNexus indexed/current at `ea990826`. This proves the merged source and setup path; it does not claim local or VPS deployment.
**Accepted product code merge:** `adcc7f281c661897ad050a8278686375b611edb5` (the accepted Contract D merge; an ancestor contained in the current tip — it is NOT the current branch tip)
**Current database head:** `037_payment_declarations_schema`
**Delivery state:** Pre-pilot MVP hardening; not yet approved for customer delivery

This file is the continuously maintained source of truth for product status,
accepted capabilities, delivery blockers, and ordered work. Detailed execution
evidence belongs in `ai-ledger/`. Durable product philosophy belongs in
`docs/ai/PROJECT_MEMORY.md` and `decision-register/`.

## 1. Executive Summary

Mpango is beyond prototype stage. The wholesaler ERP, tenant isolation,
financial invariants, credential lifecycle, deterministic test gate, retailer
identity, supplier-scoped retailer login, catalog/order workspace, read-only
retailer finance visibility, and the payment-declaration maker-checker loop are
materially implemented.

The current product is still pre-pilot because final workspace polish, the
real-mailbox browser journey, customer HTTPS deployment, the formal DB-OPS
package, tenant branding, and current user manuals are not all closed.

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
| Product code baseline | `ea990826` is the current reviewed product-code baseline. It descends from `a6ef3aac`, `d796dcb0`, and the accepted product-code merge `adcc7f28`, so it includes I2B, printable Contracts A-D, readiness-debt closure, and H7 setup/dependency reconciliation. The live protected tip may include later docs-only commits and must descend from `ea990826` |
| Protected-tip rule | Every task fetches `origin/product-dev-recovered` live, verifies `ea990826` is its ancestor, and starts from that fetched tip. Do not encode a docs commit as its own "current tip" because the act of committing changes the tip |
| Main | `origin/main@134ea59e`, not promoted |
| Platform historical branch | `origin/platform-dev@12c5ee55`, not the active product baseline |
| Alembic head | `037_payment_declarations_schema` |
| Windows default workspace | Dirty; read-only for controlled work |
| Controlled work | Clean isolated worktrees only |
| Tencent mainland VPS | Development, validation, or disaster-recovery role |
| Customer MVP hosting | Non-mainland HTTPS environment remains to be selected and closed |

Every runtime task must verify the deployed SHA independently. Do not infer
deployment state from a merged branch.

## 4. Capability Status

| Area | Status | Current truth |
|---|---|---|
| Tenant isolation | Strong foundation | Schema-per-tenant, validated identifiers, contextual JWTs, and binding guards |
| Wholesaler authentication | Implemented | Login, tenant selection, setup/reset, and terminal-token handling |
| Credential email links | Source complete; runtime pending | Absolute fragment links and query rejection are merged |
| Users and RBAC | Implemented | Tenant roles exist; retailer permissions are isolated as `client:*` |
| Orders | Implemented and hardened | State, financial, ownership, and cross-retailer boundaries are regression-covered |
| Payments | Financially hardened | Canonical methods, idempotency, replay, partial payment, and ledger invariants |
| Receivables | Financially hardened | Non-negative exposure and collection semantics protected by migration `035` |
| Inventory and catalog | Core capability present | Retailer catalog and order workspace are supplier-scoped |
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
| Local deployment and browser rehearsal | Active delivery gate | Deploy the fetched protected tip after proving it descends from `ea990826`, run Playwright journeys, then perform human acceptance without claiming VPS delivery |
| Retailer workspace closure | Planned after rehearsal | Final responsive and branded workspace UX remains; it is not part of the active deployment gate |
| Retailer end-to-end S4 | Not closed | Real mailbox and browser journey on deployed latest SHA remains |
| Platform operator schema | Foundation merged | Migration `034` tables exist |
| Platform operator runtime | Incomplete | Dedicated login/JWT/guard/frontend lifecycle remains |
| DB operations | Partial | Evidence exists, but one approved access/backup/restore/monitoring package remains |
| Tenant branding | Not implemented | Legal profile, logo, dual branding, and controlled configuration remain |
| User manuals | Incomplete | Wholesaler, retailer, and operator guidance must match deployed behavior |
| AI-native operations | Planned | Requires trustworthy data, permissions, approvals, audit, and rollback first |

## 5. Accepted Engineering Milestones

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

## 6. Latest Validation Snapshot

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

1. The complete retailer workspace is not yet closed on mobile and desktop.
2. The latest SHA has not passed the full invitation/setup/reset/login/order/
   payment/finance journey through a real mailbox and browser.

### P1 operational blockers

1. The intended non-mainland customer HTTPS environment is not yet canonical.
2. DB access, backup, restore, monitoring, retention, incident response, and
   safe AI-agent actions are not one approved DB-OPS package.
3. Dedicated platform operator runtime authentication is incomplete.
4. User manuals and operator runbooks do not yet match final deployed behavior.

### Important but later

- Subscription and billing automation.
- Multi-warehouse expansion.
- Retailer staff sub-roles such as buyer, inventory clerk, and finance
  reconciler.
- Automated KYC and self-service tenant branding.
- SMS or WhatsApp transaction notification delivery.
- AI-native conversational mutations.

## 8. Ordered Work Plan

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

#### DC-12R1-MVP-L1 - local deployment and acceptance rehearsal (active delivery gate)

Deploy the fetched protected tip on a clean local environment, first proving
that it descends from `ea990826`. Verify the runtime SHA, execute Playwright
journeys across wholesaler and retailer roles,
and then perform a human acceptance rehearsal. This stage must not change
financial semantics or expand MVP scope. A successful local rehearsal is not a
VPS or customer-delivery claim.

#### DC-12R1-S3-S3-D - responsive branded workspace closure (planned after rehearsal)

After the MVP rehearsal, audit the existing retailer workspace and define a
bounded implementation plan for responsive navigation, existing relationship-
brand context, clear financial state language, empty/error states, logout
recovery, and focused accessibility tests. It must reuse Contracts A-D and
existing financial services rather than duplicating print views or changing
financial semantics.

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
| Product coding agent | Bounded implementation/design slices on isolated branches |
| Independent Lubuntu validator | Fresh DB, full-suite, cross-environment, and browser evidence |
| OPS agent | Deployment, DNS/TLS, backup/restore, monitoring, and runtime evidence |
| Human owner | Credentials, mailbox, domain, legal data, and production authorization |
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
- No claim that merged code is deployed without exact runtime SHA proof.

## 11. Document Maintenance

Update `docs/ai/CTO_CURRENT_OPS.md` after every meaningful active-task change.
Update this file when the product baseline, migration head, accepted feature
stage, delivery blocker, deployment role, roadmap, or product trust decision
changes.

Do not append raw transcripts. Replace stale status with current facts.
Historical command output belongs in `ai-ledger/`.
