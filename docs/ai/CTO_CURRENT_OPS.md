# CTO Current Ops / 当前作战摘要

**Last updated:** 2026-07-30
**Owner:** Codex acting as CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Accepted product baseline:** `44ec07ffd92c601957b78fb7909514360232e3eb`
**Current migration head:** `036_retailer_mvp_identity`
**Delivery state:** Pre-pilot MVP hardening; not approved for customer delivery
**Active slice:** `DC-12R1-S3-S2` read-only retailer payment/finance visibility

This is the short operating picture for every Mpango agent. Read
`docs/ai/PROJECT.md` for full status and roadmap. Detailed evidence belongs in
`ai-ledger/`.

本文件只记录当前事实、当前任务、责任人和停止条件，不替代 PRD、决策记录或详细测试报告。

## Current Truth / 当前事实

- The only active product baseline is
  `origin/product-dev-recovered@44ec07ffd92c601957b78fb7909514360232e3eb`.
- `origin/main` remains
  `134ea59e02204842e55ebe36f721f44df5a33737`.
- `origin/platform-dev` remains
  `12c5ee557876498240b1a36cc850d030d7bd8293`.
- Every task must fetch and verify its assigned SHA before editing.
- The Windows default workspace is dirty. Controlled work uses a clean isolated
  worktree.
- A merged SHA is not a deployed SHA.
- The wholesaler is the primary customer. Retailer capabilities support a
  wholesaler-private sales channel, not a comparison marketplace.

## Closed / 已闭环

- Core tenant isolation, payment, ledger, receivable, reporting, export, and
  structured-error boundaries are merged and regression-covered.
- Credential links are absolute fragment URLs; query-string token delivery is
  rejected.
- Retailer S1 identity, invitation, credential setup/reset, verified email,
  authoritative binding mapping, and migration `036` are merged.
- Retailer S2 supplier-scoped login is merged: one portal, one contextual JWT,
  no `available_tenants`, neutral authentication failure.
- H0/H1/H2 boundaries are merged: correct 429 handling, terminal verification
  tokens, and safe structured HTTP error serialization.
- Retailer S3-S1 catalog/order hardening is merged:
  - server-derived supplier and retailer identity;
  - mandatory dual-key order scope;
  - wrong supplier/retailer and malformed-ID fail-closed behavior;
  - exact client-route and permission inventory;
  - canonical seeder/bootstrap RBAC reconciliation.

## Latest Evidence / 最新证据

Authoritative S3-S1 source:
`280c2b027c2fae7373d9168d4fc3d07e7f4806b1`.

Two independent fresh PostgreSQL 16/Redis 7 full backend gates:

| Metric | Run A | Run B |
|---|---:|---:|
| Collected | 3086 | 3086 |
| Passed | 3023 | 3023 |
| Skipped | 48 | 48 |
| XFailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |

Frontend: `15` files and `142` tests passed; production build passed.

The source was merged as `44ec07ffd92c601957b78fb7909514360232e3eb`.
Post-merge: Alembic reached sole head `036`; focused backend result was
`234 passed, 5 xfailed`; frontend remained `142 passed` with a successful build.

## Not Closed / 未闭环

- Retailer payment history and finance balance are not yet available in the
  client workspace.
- Retailer branded/responsive workspace and browser continuity are incomplete.
- The latest product baseline is not proven on the intended overseas HTTPS
  customer origin.
- Real mailbox invitation, setup, reset, login, order, and finance journeys are
  not closed on the latest deployment.
- Formal DB-OPS, monitoring, backup/restore policy, retention, access, and
  incident runbooks are incomplete.
- Dedicated platform-operator login/JWT/guard/frontend lifecycle is incomplete.
- Tenant branding and customer/operator manuals are incomplete.

## Frozen Decision / 冻结决策

`client:payments:create` is **future-gated**. It is not permission to add a
retailer payment-submission route.

Until a separate CTO-approved financial contract exists:

- retailer finance is read-only;
- retailers cannot settle payments, mutate ledgers, or alter receivables;
- no `/api/v1/client/payments` write method may exist;
- no generic wholesaler payment/finance endpoint may be exposed to retailers;
- all displayed balances are server-authoritative and relationship-scoped.

## Active Task / 当前任务

### DC-12R1-S3-S2 - Read-Only Payment and Finance Visibility

**Primary implementer:** local Codex CLI

**Independent source reviewer:** Zcode

**Independent runtime validator:** Lubuntu Codex

Required delivery:

1. `GET /api/v1/client/payments` returns only the active supplier-retailer
   relationship's payment history.
2. `GET /api/v1/client/finance/balance` returns a server-authoritative balance
   and exposure summary.
3. Repository/query predicates require both `wholesaler_id` and `retailer_id`;
   invalid identity fails before financial SQL.
4. Frontend adds read-only payment history and balance views inside the existing
   client workspace.
5. Exact route inventory proves there is no client payment mutation route.
6. A/B supplier isolation, pagination, empty state, inactive/deleted binding,
   missing permission, malformed ID, and generic-route denial are tested.
7. Existing wholesaler finance/payment behavior remains unchanged.

Forbidden:

- payment submission, settlement, ledger mutation, or receivable mutation;
- request-body/query authority for wholesaler or retailer identity;
- cross-supplier aggregation or comparison;
- client-side recomputation presented as the financial source of truth;
- migration, permission, or deployment expansion without an explicit stop and
  CTO review.

Acceptance:

- focused backend tests pass in natural and reverse order;
- affected finance/payment/route/RBAC regressions pass;
- two fresh full backend gates have identical totals and zero failures/errors;
- frontend Vitest and production build pass;
- no skip, xfail, deselection, rerun, or assertion weakening;
- independent review confirms zero financial write path.

## Ordered Work / 下一步顺序

1. **S3-S2:** read-only relationship payment and finance visibility.
2. **Independent S3-S2 review and merge gate.**
3. **S3-S3:** supplier branding, responsive workspace, portal continuity, and
   browser component closure.
4. **S4:** overseas HTTPS, real mailbox, real browser, two-wholesaler isolation,
   exact-SHA deployment, rollback, and sanitized runtime closure.
5. **DB-OPS:** access, backup/restore, retention, monitoring, migration,
   incident, and AI-agent runbooks.
6. **Tenant identity and manuals:** legal profile, logo, dual branding,
   wholesaler/retailer/operator documentation.
7. **Pilot then AI-native:** one or two supported wholesalers first; governed
   read-only AI and approval-bound actions later.

## Release Gates / 当前交付门禁

No customer-delivery verdict until:

- the latest product SHA is deployed to the intended non-mainland HTTPS origin;
- Alembic reaches sole head `036_retailer_mvp_identity`;
- fresh wholesaler and retailer credential journeys work through a real mailbox;
- supplier-scoped catalog, order, read-only payment, and balance journeys pass
  on desktop and mobile;
- cross-supplier negative reads and writes are rejected;
- finance, payment, ledger, and receivable invariants remain green;
- backup and restore evidence exists for the target environment;
- logs and public responses expose no token, credential, database URL, stack
  trace, or raw internal exception;
- customer manuals and operator runbooks match the deployed behavior.

## Stop Conditions / 停止条件

Stop and report to the CTO when:

- the fetched baseline differs from the assigned SHA;
- any client financial write route appears;
- any identity is accepted from request data instead of server context;
- a cross-supplier result, unexplained 500, financial invariant failure, or
  secret exposure occurs;
- a task changes migration, permission registry, platform auth, deployment, or
  protected refs outside scope;
- tests pass only through skip, xfail, deselection, rerun, assertion weakening,
  schema repair inside a read-only gate, or reused dirty infrastructure;
- branch, changed files, test totals, cleanup, and remote equality cannot be
  proven.

## Update Protocol / 更新规则

Update this file after every meaningful merge, deployment, blocker, release
gate, or phase transition. Keep it short and current. Move full status to
`PROJECT.md`, durable strategy to `PROJECT_MEMORY.md`, and evidence to
`ai-ledger/`.
