# Mpango ERP Project Status / 项目情况

**Last updated:** 2026-07-30
**Status owner:** CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Accepted product baseline:** `44ec07ffd92c601957b78fb7909514360232e3eb`
**Current database head:** `036_retailer_mvp_identity`
**Overall verdict:** Stable engineering foundation; pre-pilot, not yet approved
for customer delivery

This file is the continuously maintained project-wide source of truth for
current status, accepted capabilities, delivery blockers, and ordered work.
Detailed execution evidence belongs in `ai-ledger/`. Durable product philosophy
belongs in `docs/ai/PROJECT_MEMORY.md` and `decision-register/`.

本文件回答四个问题：

1. Mpango 当前已经完成了什么？
2. 哪些能力仍不能对客户宣称已经交付？
3. 当前最大的产品与运维风险是什么？
4. 下一步应按什么顺序推进？

## 1. Executive Summary / 项目总览

Mpango is no longer a prototype. Its core wholesaler ERP, tenant isolation,
financial integrity, credential lifecycle, deterministic test infrastructure,
retailer identity, supplier-scoped retailer login, and retailer catalog/order
boundaries are materially implemented and regression-covered.

The product is still pre-pilot. Customer delivery cannot be declared until the
retailer read-only finance experience, branded browser workspace, latest-SHA
HTTPS deployment, real-mailbox credential journey, database operations package,
and current user/operator documentation are closed.

当前可以准确描述为：

- 核心 ERP、租户隔离和财务写入边界已经形成稳定地基。
- 零售商身份、凭据、供应商专属登录、目录和订单边界已经合并。
- 零售商付款提交仍未授权；MVP 下一步只提供关系内只读付款与余额视图。
- 最新合并源码尚未在目标海外 HTTPS 环境完成真实邮箱和浏览器交付门禁。
- 平台与数据库运维已有大量证据，但尚未形成可交接的统一运行体系。

## 2. Product Position / 产品定位

### Primary value owner

The wholesaler is the primary customer and future payer. Mpango helps a
wholesaler operate orders, inventory, payments, receivables, reporting, staff
permissions, and a private downstream retailer channel.

### Retailer role

The retailer is an invited operational participant, not the primary product
owner. Retailer UX should reduce ordering friction and improve wholesaler
throughput and retention. Mpango must not become a retailer-facing
cross-supplier price-comparison marketplace.

A retailer may maintain independent relationships with multiple wholesalers,
but:

- every catalog, negotiated price, order, payment, receivable, and operational
  record remains private to its supplier relationship;
- one wholesaler cannot read another wholesaler's data;
- the retailer enters through a supplier-scoped portal and receives one
  contextual session, not a system-generated cross-supplier comparison view;
- Mpango cannot prevent a person from manually sharing information they already
  know, but the product must not aggregate or expose that information for them.

The accepted decision is recorded in
`decision-register/2026-07-23_wholesaler-private-channel-positioning.md`.

### Platform operator role

Platform operators maintain service health, tenant lifecycle, support,
backups, restores, incidents, and controlled platform operations. They are not
ordinary tenant users and must not use tenant-local `super_admin` as a
substitute for a dedicated platform identity.

There is no subscription or automated billing product yet. The first one or
two pilot wholesalers may be onboarded and supported manually.

## 3. Current Branch and Environment Map / 分支与环境

| Item | Current truth |
|---|---|
| Product baseline | `origin/product-dev-recovered@44ec07ffd92c601957b78fb7909514360232e3eb` |
| Main | `origin/main@134ea59e02204842e55ebe36f721f44df5a33737`, not promoted |
| Platform historical branch | `origin/platform-dev@12c5ee557876498240b1a36cc850d030d7bd8293`, not the active product baseline |
| Alembic head | `036_retailer_mvp_identity`, sole head |
| Windows default workspace | Dirty; read-only for controlled work |
| Controlled engineering | Fetched, clean, isolated worktrees only |
| Tencent mainland VPS | Development, validation, or disaster-recovery role |
| Intended customer hosting | Non-mainland HTTPS environment, still to be provisioned and closed |

Every runtime task must verify the deployed SHA independently. A merged SHA is
not a deployed SHA, and a healthy old deployment is not evidence for the latest
product tree.

## 4. Capability Status / 能力状态

| Area | Status | Current truth |
|---|---|---|
| Tenant isolation | Strong foundation | Schema-per-tenant, validated identifiers, contextual JWTs, binding checks, and cross-tenant negatives |
| Wholesaler authentication | Implemented and hardened | Login, tenant selection, owner setup/reset, rate-limit handling, and terminal token states |
| Credential email links | Source complete, runtime pending | Absolute fragment links and query-token rejection merged; real HTTPS/mailbox closure pending |
| Users and RBAC | Implemented | Canonical registry; `admin` and `retailer_operator` permissions reconciled across migration/bootstrap/seeders |
| Orders | Implemented and hardened | State, inventory, payment, ledger, retailer dual-key scope, malformed-ID and wrong-entity negatives covered |
| Payments | Financially hardened | Canonical methods, idempotency, replay, duplicate transfer, partial payment, and ledger invariants |
| Receivables and finance | Financially hardened | Migration `035`, non-negative exposure, underflow protection, and relationship scope regressions |
| Inventory and catalog | Implemented | Wholesaler operations plus supplier-scoped retailer catalog access |
| Exports | Implemented and hardened | Worker tenant context and sanitized error boundaries |
| Reporting | Implemented | Supported provisioning contracts; customer runtime evidence remains a deployment gate |
| Retailer identity S1 | Merged | Authoritative mapping, invitation lifecycle, setup/reset, verified email, and migration `036` |
| Retailer private login S2 | Merged | One supplier portal, one contextual JWT, no `available_tenants`, neutral failure behavior |
| Retailer catalog/order S3-S1 | Merged | Server-derived identities, mandatory dual-key repository scope, exact route/permission inventory, fail-closed negatives |
| Retailer finance S3-S2 | Next | Read-only relationship payment history and server-authoritative balance; no payment mutation |
| Retailer branded workspace S3-S3 | Pending | Responsive UX, portal continuity, supplier branding, and component/browser closure |
| Retailer end-to-end S4 | Not closed | Fresh invitation through real mailbox and browser on the intended HTTPS deployment |
| Structured HTTP errors | Merged | Dict details serialize safely; malformed details fail closed without repr leakage or accidental 500 |
| Platform operator schema | Foundation merged | Migration `034` tables exist |
| Platform operator runtime | Incomplete | Dedicated login/JWT/guard/frontend lifecycle is not a merged end-to-end capability |
| DB operations | Partial evidence | Backups and restore proofs exist; unified policy, monitoring, access, retention, and incident runbooks remain |
| Tenant branding | Not implemented | Legal profile, business-license review, logo, dual branding, and configuration UX remain |
| User manuals | Outdated/incomplete | Wholesaler, retailer, and operator guides must be regenerated from deployed behavior |
| AI-native operations | Planned | Must rely on governed data, permissions, approval, audit, and rollback |

## 5. Accepted Engineering Milestones / 已接受里程碑

### DC-10 financial and boundary hardening

- Export worker tenant-context restoration.
- Canonical payment-method integrity across API, frontend, migration, and
  fresh-tenant bootstrap.
- Platform malformed UUID handling and export error sanitization.
- Finance receivable scoping and legacy order-status reconciliation.

### DC-11 delivery and test foundation

- Payment replay and concurrency integrity.
- Receivable collection integrity in migration `035`.
- Reporting/bootstrap test-contract repair.
- Tenant-schema teardown safety.
- Deterministic test-infrastructure and full-gate reconciliation.
- Platform operator schema foundation in migration `034`.

### DC-12 customer entry and retailer channel

- Wholesaler-private-channel product positioning.
- Absolute fragment-based credential links and query-token rejection.
- Retailer identity, invitation, credential, and permission foundation in
  migration `036`.
- Rate-limit 429 boundary, verification-token terminal states, and portable
  U6I1 schema/security contracts.
- Structured HTTP error serialization without dict-repr leakage.
- Supplier-scoped retailer login and contextual authorization.
- Retailer catalog/order hardening with mandatory supplier and retailer scope,
  canonical seed permissions, fail-closed malformed identity handling, and
  exact client-route governance.

## 6. Latest Validation Snapshot / 最新验证

### Authoritative S3-S1 candidate gate

The validated source tree was
`280c2b027c2fae7373d9168d4fc3d07e7f4806b1`. Two independent fresh
PostgreSQL 16 and Redis 7 runs used the same command and source SHA:

| Metric | Run A | Run B |
|---|---:|---:|
| Collected | 3086 | 3086 |
| Passed | 3023 | 3023 |
| Skipped | 48 | 48 |
| XFailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |
| Exit code | 0 | 0 |

Frontend evidence on that source:

- `15` Vitest files and `142` tests passed;
- production build passed;
- no backend or frontend exclusions were used.

The candidate was merged with `--no-ff` as
`44ec07ffd92c601957b78fb7909514360232e3eb`.

### Post-merge focused gate

On the exact merge tree:

- Alembic upgraded an empty database to sole head
  `036_retailer_mvp_identity`;
- the 239-test backend integration bundle produced `234 passed, 5 xfailed`,
  with zero failures/errors;
- frontend Vitest remained `142 passed`, and the production build passed;
- GitNexus was rebuilt and reported up to date at `44ec07f`.

This proves source-tree merge integrity. It does not prove customer deployment,
real mailbox delivery, browser acceptance, or production operations.

## 7. Current Delivery Blockers / 当前交付阻塞

### P1 product-journey blockers

1. Retailer relationship-scoped payment history and finance balance are not yet
   available as a read-only browser experience.
2. Retailer branded workspace and mobile/desktop browser continuity are not yet
   closed.
3. No latest-SHA real-mailbox invitation/setup/reset/login proof exists.
4. No latest-SHA customer-facing overseas HTTPS deployment has passed the full
   browser journey.

### P1 operational blockers

1. The intended non-mainland customer environment, DNS, TLS, monitoring, and
   rollback ownership are not yet canonical.
2. Backup, restore, retention, operator access, migration, monitoring, and
   incident procedures are not one approved DB-OPS package.
3. Dedicated platform-operator authentication and authorization are not closed
   end to end.
4. Customer and operator manuals do not match a final deployed build.

### Important but later

- Subscription and billing automation.
- Multi-warehouse expansion.
- Retailer staff sub-roles such as buyer, inventory clerk, and finance
  reconciler.
- Fully automated tenant KYC and branding administration.
- AI-native conversational actions.

These must not displace the secure MVP business loop.

## 8. Frozen Product Decisions / 已冻结决策

### Retailer payment submission

`client:payments:create` remains **future-gated**. It is not approval to expose
a route.

For the current MVP:

- no retailer payment-submission endpoint may be added;
- no retailer may mark a payment settled, mutate ledger entries, or alter
  receivables;
- retailer finance is read-only and server-authoritative;
- any future payment-submission flow requires a separate accounting contract,
  threat model, migration/ledger review, browser confirmation semantics, and
  explicit CTO authorization.

### Supplier privacy

- no cross-supplier workspace picker;
- no comparison dashboard;
- no request-supplied `wholesaler_id` or `retailer_id` authority;
- every client read is derived from the contextual JWT, tenant context, and
  active binding;
- cross-supplier records return controlled denial or non-disclosing not-found
  behavior.

## 9. Ordered Work Plan / 下一步工作计划

### Stage 1: Complete the retailer MVP loop

#### DC-12R1-S3-S2 - read-only payment and finance visibility (next)

Deliver:

- `GET /api/v1/client/payments` for relationship-scoped payment history;
- `GET /api/v1/client/finance/balance` for server-authoritative balance and
  exposure;
- mandatory supplier and retailer predicates at the repository/query layer;
- sanitized pagination and empty states;
- read-only frontend pages and navigation inside the existing client workspace;
- exact route inventory and permission checks.

Forbidden:

- no payment submission or settlement;
- no ledger or receivable mutation;
- no generic wholesaler `/payments` or `/finance` route reuse;
- no request-supplied supplier/retailer authority;
- no cross-supplier aggregation or comparison;
- no client-side financial recomputation presented as authoritative.

Exit criteria:

- A/B supplier isolation passes for list, detail, empty, pagination, and
  malformed-ID cases;
- inactive/deleted binding and missing permission fail before route-body SQL;
- backend affected tests pass in natural and reverse order;
- two independent fresh full backend gates have zero failures/errors;
- frontend Vitest and build pass;
- an independent reviewer confirms no write path was introduced.

Primary implementer: local Codex CLI in a clean isolated worktree.
Independent review: Zcode for source/contract review, then Lubuntu Codex for
fresh PostgreSQL 16/Redis 7 and frontend evidence.

#### DC-12R1-S3-S3 - branded workspace closure

After S3-S2 merge:

- responsive retailer workspace;
- supplier logo/name presentation without cross-supplier leakage;
- portal code continuity across login/logout;
- controlled picker and error feedback;
- mobile/desktop component and browser tests.

#### DC-12R1-S4 - end-to-end delivery closure

After S3-S3:

- fresh PostgreSQL/Redis and migration `001 -> 036`;
- real invitation email, fragment setup link, password creation, and reset;
- supplier-scoped login, catalog, order, read-only payment, and balance journey;
- two-wholesaler isolation matrix;
- sanitized logs and public responses;
- exact-SHA overseas HTTPS deployment and rollback evidence.

### Stage 2: Establish human-plus-AI DB operations

- named responsibility matrix;
- least-privilege production access and break-glass process;
- encrypted backups, retention, restore drills, RPO/RTO targets;
- migration preflight, maintenance mode, and rollback/forward-fix decisions;
- health, storage, backup-age, and error monitoring;
- incident ledger, audit evidence, and secret-handling rules;
- no direct business-data edits outside approved replayable artifacts.

### Stage 3: Tenant identity, branding, and enablement

- legal/business profile and license review;
- logo and brand assets with safe storage;
- Mpango plus tenant dual-brand entry;
- operator review for early pilots;
- wholesaler, retailer, and operator manuals generated from final behavior.

### Stage 4: Pilot and AI-native evolution

- deploy one or two controlled wholesalers in a non-mainland HTTPS region;
- operate with named support and feedback owners;
- begin AI-native read-only assistance and guided actions only after data,
  permissions, approvals, audit, and rollback are trustworthy;
- no unrestricted SQL, shell, payment mutation, or tenant impersonation.

## 10. Role and Ownership Model / 角色责任

| Role | Responsibility |
|---|---|
| CTO/Codex | Architecture, scope, impact, contracts, merge, release verdict, and project truth |
| Local Codex CLI | Primary bounded implementation for the next high-integrity product slice |
| Zcode | Independent source/contract review and adversarial negative-path review |
| Lubuntu Codex | Fresh DB, full-suite, cross-environment, frontend, and browser evidence |
| OPS agent | Deployment, DNS/TLS, backup/restore, monitoring, runtime health, and incident evidence |
| Human owner | Credentials, mailbox, domains, legal/business data, and production authorization |
| Wholesaler pilot owner | Business-workflow acceptance and named feedback |

An agent's self-reported PASS is not sufficient by itself. Product changes need
source review and independent evidence proportionate to risk.

## 11. Non-Negotiables / 当前红线

- No cross-tenant or cross-supplier data exposure.
- No unsupported payment method or hidden financial side effect.
- No negative receivable exposure represented as valid customer debt.
- No retailer payment write path without a separately approved contract.
- No query-string credential tokens.
- No silent schema repair inside a read-only gate.
- No dirty-worktree merge or deployment.
- No hidden skip, xfail, deselection, rerun, or assertion weakening.
- No production credential, token, email, database URL, or raw exception in
  reports.
- No protected push without explicit human approval.
- No claim that merged code is deployed without exact runtime SHA proof.
- No claim that schema or source completion equals customer delivery.

## 12. Document Maintenance / 文档维护

Update `docs/ai/CTO_CURRENT_OPS.md` after every meaningful active-task change.
Update this file when the baseline, migration head, accepted feature stage,
delivery blocker, deployment role, roadmap, or product trust decision changes.

Do not append raw transcripts. Replace stale status with current facts and link
to evidence. Historical command output belongs in `ai-ledger/`.
