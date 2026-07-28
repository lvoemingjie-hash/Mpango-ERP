# Mpango ERP Project Status / 项目情况

**Last updated:** 2026-07-28
**Status owner:** CTO
**Current product branch:** `origin/product-dev-recovered`
**Accepted product-code commit:** `6d81b4012c136a4655f8aa162fe15ed8854626b7`
**Status-document publication merge:** `1a986bdbb658c0d452b4e4f0d940bbffaa8e38cc`
**Current database head:** `036_retailer_mvp_identity`
**Overall verdict:** Stable engineering foundation; pre-pilot, not yet
customer-delivery complete

This file is the continuously maintained project-wide source of truth for
current status, accepted capabilities, delivery blockers, and next work.

本文件用于回答四个问题：

1. Mpango 现在已经完成了什么？
2. 哪些能力仍然不能对客户宣称已交付？
3. 当前最大的产品和运维风险是什么？
4. 下一步按什么顺序推进？

Detailed execution evidence stays in `ai-ledger/`. Durable product philosophy
stays in `docs/ai/PROJECT_MEMORY.md` and `decision-register/`.

## 1. Executive Summary / 项目总览

Mpango has moved beyond a prototype, but it is still in the pre-pilot hardening
stage. The core wholesaler ERP, financial integrity, tenant isolation,
credential lifecycle, test infrastructure, and the first retailer identity
foundation are materially stronger than the May baseline reflected in the old
project documents.

The product is not yet ready for an honest customer-delivery verdict because
the complete retailer browser journey, latest-SHA HTTPS deployment, real mailbox
credential lifecycle, formal database operations, tenant branding, and current
user documentation are not all closed.

当前可以准确描述为：

- 核心 ERP 与财务地基已经基本稳定。
- 零售商身份与凭据地基已经合并，但零售商完整使用闭环尚未完成。
- 测试体系已经能够在两个独立新数据库上获得确定性全绿。
- 当前最新代码尚未在目标海外 HTTPS 环境完成真实用户交付门禁。
- 平台运维能力有较多基础，但专用平台操作员运行时生命周期和正式 DB-OPS
  体系仍需补齐。

## 2. Product Position / 产品定位

### Primary value owner

The wholesaler is the primary customer and future payer. Mpango helps a
wholesaler run orders, inventory, payments, receivables, reporting, staff
permissions, and a private downstream retailer channel.

### Retailer role

The retailer is an invited operational participant, not the primary product
owner. Retailer UX should reduce ordering friction and improve wholesaler
throughput and retention. Mpango must not become a retailer-facing
cross-supplier price-comparison marketplace.

A retailer may have independent relationships with multiple wholesalers, but:

- each wholesaler's catalog, negotiated price, order, payment, receivable, and
  operational data remains private to that relationship;
- one wholesaler cannot read another wholesaler's data;
- a retailer uses a supplier-scoped portal context rather than receiving a
  system-generated cross-supplier comparison screen;
- Mpango cannot prevent a human from manually sharing information they already
  know, but it must not aggregate or expose that information on their behalf.

The accepted positioning decision is recorded in
`decision-register/2026-07-23_wholesaler-private-channel-positioning.md`.

### Platform operator role

Platform operators maintain service health, tenant lifecycle, support,
backups, restores, incidents, and controlled platform operations. They are not
ordinary tenant users and must not use tenant-local `super_admin` as a
substitute for a dedicated platform identity.

There is currently no subscription or automated billing product. Early pilot
customers will be onboarded and supported manually by Mpango operators.

## 3. Current Branch and Environment Map / 分支与环境

| Item | Current truth |
|---|---|
| Product code baseline | `6d81b401`; fetch `origin/product-dev-recovered` for the exact current branch head |
| Main | `origin/main@134ea59e`, not promoted |
| Platform historical branch | `origin/platform-dev@12c5ee55`, not the active product baseline |
| Alembic head | `036_retailer_mvp_identity` |
| Windows default workspace | Dirty; read-only for controlled work |
| Controlled development | Clean isolated worktrees only |
| Tencent mainland VPS | Development, validation, or disaster-recovery role |
| Customer MVP hosting | Non-mainland HTTPS environment still to be provisioned and closed |

The currently deployed VPS SHA must be verified before every runtime task. Do
not infer deployment state from the product branch. A merged SHA is not a
deployed SHA.

## 4. Capability Status / 能力状态

| Area | Status | Current truth |
|---|---|---|
| Tenant isolation | Strong foundation | Schema-per-tenant, validated identifiers and tenant-context guards; cross-tenant negatives remain mandatory |
| Wholesaler authentication | Implemented and hardened | Login, tenant selection, owner setup/reset and terminal token handling exist |
| Credential email links | Source complete, runtime pending | Absolute fragment links and query rejection merged; latest-SHA real HTTPS/mailbox closure pending |
| Users and RBAC | Implemented | Tenant roles and permissions exist; retailer permissions are separated as `client:*` |
| Orders | Implemented and regression-covered | State, payment and ledger paths hardened; browser pilot still required |
| Payments | Financially hardened | Canonical methods, idempotency, replay, duplicate transfer, partial payment and ledger invariants covered |
| Receivables and finance | Financially hardened | Collection semantics, scope and non-negative exposure protected by migration `035` and regressions |
| Inventory and catalog | Core wholesaler capability present | Retailer supplier-scoped presentation remains part of S3 |
| Exports | Implemented and hardened | Worker tenant context and sanitized error boundaries merged |
| Reporting | Implemented | Test contracts now use supported provisioning paths; customer runtime evidence still belongs to deployment gates |
| Retailer identity S1 | Merged | Authoritative mapping, invitation lifecycle, setup/reset, verified email and role foundation in migration `036` |
| Retailer private login S2 | Not started in product code | Supplier-scoped login and single-context token remain the next slice |
| Retailer portal S3 | Incomplete | Catalog/order/payment/finance browser UX and relationship-scoped navigation remain |
| Retailer end-to-end S4 | Not closed | Fresh invitation through real browser and mailbox has not passed on latest deployed SHA |
| Platform operator schema | Foundation merged | Migration `034` tables exist |
| Platform operator runtime | Incomplete | Dedicated login/JWT/guard/frontend lifecycle is not yet a merged end-to-end capability |
| DB operations | Partial evidence, incomplete operating system | Backups, disposable restore proofs and incident work exist; unified policy/runbooks/monitoring/access model remain |
| Tenant branding | Not implemented | Legal profile, business license review, logo, dual branding and configuration UX remain |
| User manuals | Outdated/incomplete | Wholesaler, retailer and operator manuals must be regenerated from deployed behavior |
| AI-native operations | Planned | Must build on governed data, permissions, approval, audit, rollback and operator trust |

## 5. Accepted Engineering Milestones / 已接受里程碑

### DC-10 financial and boundary hardening

- Export worker tenant context restoration.
- Canonical payment-method integrity across API, frontend, database migration,
  and fresh-tenant bootstrap.
- Platform malformed UUID handling and export error sanitization.
- Finance receivable scoping and legacy order-status enum reconciliation.

### DC-11 delivery and test foundation

- Payment replay and concurrency integrity.
- Receivable collection integrity in migration `035`.
- Reporting/bootstrap test-contract repair.
- Tenant-schema teardown safety.
- Deterministic test-infrastructure and full-gate reconciliation.
- Platform operator schema foundation in migration `034`.

### DC-12 product positioning and customer entry

- Wholesaler-private-channel product positioning recorded.
- Absolute, fragment-based credential email links and query-token rejection.
- Retailer identity, invitation, credential and permission foundation in
  migration `036`.
- Rate-limit 429 exception boundary hardening.
- Verification-token terminal-state hardening.
- Portable U6I1 schema/security contract without runtime Git-history
  dependency.

## 6. Latest Validation Snapshot / 最新验证

The authoritative independent full backend gate for the H1/R2-R1 candidate ran
twice on separate fresh PostgreSQL 16 and Redis 7 environments:

| Metric | Run A | Run B |
|---|---:|---:|
| Collected | 2949 | 2949 |
| Passed | 2886 | 2886 |
| Skipped | 48 | 48 |
| XFailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |
| Exit code | 0 | 0 |

Evidence branch:
`reports/dc12r1-s1-h1-r2-r1-v2-independent-full-gate-2026-07-28`
at `843d7a6e275b15ab342ceecf8615e4cfaadfa1bf`.

The candidate was merged into the product baseline as:

`6d81b4012c136a4655f8aa162fe15ed8854626b7`

This proves deterministic backend integrity for that source tree. It does not
prove that the latest source is deployed, that a customer can complete the
journey over HTTPS, or that production operations are complete.

## 7. Current Delivery Blockers / 当前交付阻塞

### P1 product journey blockers

1. Supplier-scoped retailer login is not implemented.
2. Retailer catalog, order, payment and finance UX is not closed as one
   relationship-scoped browser journey.
3. No latest-SHA real-mailbox invitation/setup/reset/login proof exists.
4. No latest-SHA customer-facing HTTPS deployment and browser closure exists.

### P1 operational blockers

1. The intended non-mainland MVP environment, DNS and TLS termination are not
   yet the canonical customer deployment.
2. Database backup, restore, retention, monitoring, operator access and
   incident procedures are not yet one approved DB-OPS operating package.
3. Dedicated platform operator identity and credential lifecycle is not yet
   wired end to end.
4. Current operator and customer manuals do not yet match the final deployed
   behavior.

### Important but later

- Subscription and billing automation.
- Multi-warehouse expansion.
- Retailer staff sub-roles such as buyer, inventory clerk and finance
  reconciler.
- Full tenant branding automation and self-service configuration.
- AI-native conversational actions.

These are valuable, but they must not displace the secure MVP business loop.

## 8. Ordered Work Plan / 下一步工作计划

### Stage 1: Complete the retailer MVP loop

#### DC-12R1-S2 - supplier-scoped retailer authentication

Deliver:

- portal/wholesaler context resolution;
- retailer login that checks only the selected wholesaler schema;
- one context token with no `available_tenants`;
- exact binding and `retailer_operator` checks;
- neutral failure behavior with no supplier disclosure;
- owner-login regression protection.

Exit criteria:

- retailer R with relationships A and B can log into A without seeing B;
- suspended A relationship does not disable B;
- retailer tokens cannot use generic wholesaler or platform routes;
- cross-supplier negative tests pass.

#### DC-12R1-S3 - relationship-scoped retailer workspace

Deliver:

- supplier-branded catalog browsing;
- order creation and history;
- payment recording/history appropriate to the relationship;
- server-authoritative balance and finance visibility;
- no cross-supplier comparison dashboard.

Exit criteria:

- every read/write is derived from the current binding and tenant context;
- all price, order, payment and balance cross-tenant probes fail;
- mobile and desktop browser journeys pass.

#### DC-12R1-S4 - end-to-end delivery closure

Deliver:

- fresh PostgreSQL/Redis and migration `001 -> 036`;
- real invitation email, fragment setup link and password creation;
- supplier-scoped login, catalog, order, payment and finance journey;
- reset-password replay and terminal-token negatives;
- two-wholesaler isolation matrix;
- sanitized logs and public responses.

### Stage 2: Establish human-plus-AI DB operations

Deliver:

- named human and AI-agent responsibility matrix;
- least-privilege production access and break-glass process;
- encrypted backup policy and retention schedule;
- restore drill and recovery-time/recovery-point targets;
- migration preflight, maintenance mode and rollback decision tree;
- database health, storage, replication/backup-age and error monitoring;
- incident ledger, audit evidence and secret-handling rules;
- explicit prohibition on direct business-data edits outside approved,
  replayable artifacts.

Exit criteria:

- a new operator can follow the runbook without hidden chat context;
- backup restore succeeds in a disposable environment;
- production change is reversible or has an approved forward-fix plan;
- every AI action is bounded, reviewed and auditable.

### Stage 3: Tenant identity, branding and onboarding UX

Deliver:

- legal/business name, registration/license data and contact profile;
- logo and brand assets with validation and safe storage;
- Mpango plus tenant dual-brand entry experience;
- operator review/approval for early pilots;
- tenant configuration and controlled asset replacement;
- wholesaler, retailer and operator manuals generated from final behavior.

MVP boundary:

- manual operator review is acceptable for the first one or two wholesalers;
- subscription billing and fully automated KYC are not required for the pilot;
- branding must not weaken security headers, tenant routing or cache isolation.

### Stage 4: Non-mainland pilot deployment

Deliver:

- region selected for Kenyan latency, reliability, support and legal fit;
- customer domain, DNS, TLS, backups, monitoring and alert ownership;
- exact-SHA deployment and rollback proof;
- one or two controlled wholesaler pilots with named support contacts;
- feedback loop for UX, documentation and operational defects.

### Stage 5: AI-native operating layer

Start only after the operational foundation produces trustworthy events and
permissions.

Initial direction:

- conversational read-only assistance;
- guided data entry and workflow suggestions;
- anomaly summaries and operator recommendations;
- approval-required actions through typed, audited tools;
- no unrestricted SQL, shell, payment mutation or tenant impersonation.

AI-native value should come from reliable ERP context and safe action
boundaries, not from placing a chatbot over unstable foundations.

## 9. Role and Ownership Model / 角色责任

| Role | Responsibility |
|---|---|
| CTO/Codex | Architecture, scope, risk, contracts, merge, release verdict and project-state truth |
| Product coding agent | Small S2/S3 implementation slices and exact regression evidence |
| Independent Lubuntu validator | Fresh DB, full-suite, cross-environment and browser evidence |
| OPS agent | Deployment, DNS/TLS, backup/restore, monitoring, runtime health and incident evidence |
| Human owner | Credentials, mailbox, domains, legal/business information and production authorization |
| Wholesaler pilot owner | Business workflow acceptance and named operational feedback |

No agent's self-reported PASS is sufficient by itself. Product changes require
source review plus independent evidence appropriate to their risk.

## 10. Non-Negotiables / 当前红线

- No cross-tenant data exposure.
- No unsupported payment method or hidden financial side effect.
- No negative receivable exposure represented as valid customer debt.
- No query-string credential tokens.
- No silent schema repair inside a read-only validation gate.
- No dirty-worktree merge or deployment.
- No hidden skip, xfail, deselection or assertion weakening.
- No production credential, token, email, database URL or raw exception in
  reports.
- No protected push without explicit human approval.
- No claim that merged code is deployed without exact runtime SHA proof.
- No claim that a schema foundation is a complete runtime capability.

## 11. Document Maintenance / 文档维护

Update `docs/ai/CTO_CURRENT_OPS.md` after every meaningful active-task change.

Update this file whenever any of these changes:

- product baseline or migration head;
- accepted feature stage;
- customer-delivery blocker;
- deployment role or target environment;
- ordered project roadmap;
- major product positioning or trust decision.

Do not append raw transcripts. Replace stale status with current facts and link
to the evidence. Historical command output belongs in `ai-ledger/`, not here.
