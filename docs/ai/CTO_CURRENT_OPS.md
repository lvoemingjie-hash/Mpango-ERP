# CTO Current Ops / 当前作战摘要

**Last updated:** 2026-07-28
**Owner:** Codex acting as CTO
**Canonical product branch:** `origin/product-dev-recovered`
**Accepted product-code commit:** `6d81b4012c136a4655f8aa162fe15ed8854626b7`
**Status-document publication merge:** `1a986bdbb658c0d452b4e4f0d940bbffaa8e38cc`
**Current migration head:** `036_retailer_mvp_identity`
**Current delivery state:** Pre-pilot MVP hardening; not yet approved for customer delivery

This is the short, current operating picture for every Mpango agent. Read
`docs/ai/PROJECT.md` for the full project status and roadmap. Use `ai-ledger/`
only for detailed evidence.

本文件只记录当前态势、当前任务和停止条件。它不是完整历史，也不能替代 PRD、决策记录或
详细测试报告。

## Current Truth / 当前事实

- `origin/product-dev-recovered` is the only active product baseline.
- The exact branch head must be fetched and verified before every task. The
  accepted product code is `6d81b401`; later commits may be documentation-only.
- `origin/main` remains unchanged at
  `134ea59e02204842e55ebe36f721f44df5a33737`.
- `origin/platform-dev` remains unchanged at
  `12c5ee557876498240b1a36cc850d030d7bd8293`.
- The Windows default workspace is dirty and must not be used for controlled
  implementation, validation, migration rehearsal, or protected-branch merge.
- All new work starts from a fetched, clean, isolated worktree.
- The primary customer is the wholesaler. Retailer functionality exists to make
  each wholesaler's private sales channel easier to use; Mpango is not a
  cross-supplier price-comparison marketplace.

## What Is Closed / 已闭环

### Product and financial foundation

- Tenant isolation remains schema-per-tenant and JWT-derived.
- Payment methods are restricted to `cash`, `transfer`, and `credit`.
- Payment replay, idempotency, duplicate-transfer, partial-payment, ledger, and
  receivable underflow boundaries are covered by regression tests.
- Receivable collection semantics and database constraints are represented by
  migration `035_receivable_collection_integrity`.
- Legacy order-status enum reconciliation, finance scoping, export worker tenant
  context, malformed platform UUID handling, and public error sanitization have
  been merged.

### Credential and customer-entry foundation

- Customer credential email links are absolute, fragment-based, and reject
  query-string token delivery in product code.
- Retailer S1 identity, invitation, credential setup/reset, authoritative
  `tenant_user_id` mapping, retailer-owned verified email, finite invitation
  lifecycle, and `retailer_operator` permission foundation are merged through
  migration `036_retailer_mvp_identity`.
- Verification-token terminal states now reject used, revoked, expired,
  deleted, or otherwise terminal tokens before dependent orchestration.
- Rate-limit exceptions are converted only at the intended 429 boundary and do
  not mask unrelated application exceptions.

### Deterministic validation

The final independent full backend gate for candidate `d44abae5` ran twice on
independent fresh PostgreSQL 16 and Redis 7 environments:

| Metric | Run A | Run B |
|---|---:|---:|
| Collected | 2949 | 2949 |
| Passed | 2886 | 2886 |
| Skipped | 48 | 48 |
| XFailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |
| Exit code | 0 | 0 |

The reviewed candidate was merged as
`6d81b4012c136a4655f8aa162fe15ed8854626b7`.

## What Is Not Closed / 未闭环

- Retailer S1 is a foundation, not the complete retailer journey.
- Supplier-scoped retailer login and supplier-private workspace selection are
  not implemented. This is the DC-12R1-S2 boundary.
- Retailer catalog, order, payment, and relationship-scoped finance UX are not
  yet proven as one real browser journey. This is DC-12R1-S3/S4 work.
- The latest product baseline is not proven deployed on a customer-facing HTTPS
  environment.
- The Tencent mainland VPS is retained for development, validation, or disaster
  recovery. It is not the intended customer-facing Kenyan MVP origin.
- Real mailbox signup, verification, setup, reset, login, order, payment, and
  finance closure has not been rerun against `6d81b401`.
- Platform operator schema foundation exists, but dedicated platform operator
  login/JWT/guard/frontend lifecycle is not yet merged as a complete runtime
  capability.
- Formal human-plus-AI database operations, restore policy, monitoring,
  retention, and incident runbooks are not yet a complete delivery package.
- Tenant legal identity, logo/branding onboarding, current user manuals, and
  pilot support procedures remain incomplete.

## Active Phase / 当前阶段

**Next product slice:** DC-12R1-S2 supplier-scoped retailer authentication and
private wholesaler portal boundary.

S2 must preserve these rules:

- A retailer signs in through one wholesaler's portal context.
- The issued token contains one wholesaler context only.
- No `available_tenants` or cross-supplier workspace picker is returned.
- No supplier name, price, catalog, order, payment, or balance from another
  relationship is exposed.
- Authentication resolves the retailer through
  `token.user_id -> binding.tenant_user_id -> retailer_id`, never by email after
  authentication.
- Inactive or suspended bindings fail closed without disabling the same
  retailer's independent relationship with another wholesaler.
- Existing wholesaler owner login behavior must not change.

## Ordered Delivery Plan / 下一步顺序

1. **DC-12R1-S2:** supplier-scoped retailer login and authorization boundary.
2. **DC-12R1-S3:** relationship-scoped retailer catalog/order/payment/finance
   UX, with no comparison marketplace behavior.
3. **DC-12R1-S4:** fresh-database, cross-environment, HTTPS, real-mailbox and
   real-browser end-to-end closure.
4. **DB-OPS foundation:** operator access, backup/restore drills, monitoring,
   retention, incident response, and safe AI-agent procedures.
5. **Tenant identity and branding:** legal/business profile, logo, dual-brand
   entry, controlled onboarding review, and tenant configuration UX.
6. **User enablement:** wholesaler manual, retailer manual, platform operator
   runbook, pilot checklist, and support escalation guide.
7. **AI-native layer:** begin only after reliable operational data, permissions,
   approvals, audit, and rollback boundaries are proven.

## Current Release Gates / 当前交付门禁

No customer delivery verdict may be issued until all are true:

- Latest product SHA is deployed to the intended non-mainland HTTPS origin.
- Alembic reaches sole head `036_retailer_mvp_identity`.
- Fresh wholesaler signup and credential lifecycle work through a real mailbox.
- Invited retailer setup, supplier-scoped login, catalog, order, payment, and
  finance journeys pass in browser.
- Cross-wholesaler negative reads and writes are rejected.
- Finance, payment, ledger, and receivable invariants remain green.
- Backup and restore evidence exists for the target environment.
- Runtime logs and public responses contain no tokens, credentials, database
  URLs, stack traces, or raw internal exceptions.
- User-facing manuals and operator runbooks match the deployed behavior.

## Agent Assignment / 角色分工

- **Codex CTO:** scope, contracts, impact analysis, merge decision, project-state
  truth, and final delivery verdict.
- **Product implementation agent:** bounded S2/S3 code slices on isolated
  branches; no protected push.
- **Lubuntu Codex/Leo:** independent PostgreSQL 16/Redis 7 full gates,
  cross-environment and browser validation.
- **OPS agent:** deployment, backup, restore, runtime logs, health, DNS/TLS, and
  reversible operational procedures.
- **Human owner:** credentials, mailbox access, DNS/domain decisions, legal and
  business data, and final production authorization.

## Stop Conditions / 停止条件

Stop and report to the CTO when:

- the fetched product baseline differs from the assigned SHA;
- a task changes tenant isolation, finance semantics, migrations, platform auth,
  or protected refs outside its approved scope;
- any unexplained HTTP 500, cross-tenant result, financial invariant failure, or
  secret exposure occurs;
- tests pass only through skip, xfail, deselection, assertion weakening, schema
  repair inside a read-only gate, or environment reuse;
- an agent cannot prove worktree, branch, changed files, test results, and
  cleanup.

## Update Protocol / 更新规则

Update this file after every meaningful merge, release gate, deployment,
blocker, or phase transition. Keep it short and current. Move durable strategy
to `PROJECT_MEMORY.md`, full status and roadmap to `PROJECT.md`, and detailed
evidence to `ai-ledger/`.
