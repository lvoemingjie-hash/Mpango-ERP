# Project Log / 项目快速交接说明

**Last updated:** 2026-05-13
**Current product baseline:** `origin/product-dev-recovered` at `030e96449ea9e09559fb777cfb62b8d66a08d92a`
**Promotion status:** Product/platform integration promoted and pushed to `origin/product-dev-recovered`
**Main branch:** `origin/main` remains unchanged at `02d69c00e7aeefdc788a0335a09a6f735b85f07b`

This file is the fast handoff document for new AI threads and newly activated agents.

本文件是新对话、新 AI Agent、新工作线程的快速交接文档。它不是完整审计日志，也不能替代
`ai-ledger/`；它的作用是让 Agent 在几分钟内了解项目当前真实状态、不能触碰的边界、下一步
应该做什么。

## How To Use / 使用方式

Read this after:

1. `docs/ai/README.md`
2. `docs/ai/CTO_COCKPIT.md`
3. `docs/ai/CTO_CONTEXT.md`

Then use this file to orient yourself before opening detailed ledgers or code.

阅读顺序：先读 AI 启动入口和 CTO 上下文，再读本文件。只有当本文件无法回答具体细节时，
再进入 `ai-ledger/` 查完整过程证据。

## Document Roles / 文档分工

- `docs/ai/PROJECT.md`
  Current project status, active branches, accepted slices, blockers, and next moves.
- `docs/ai/PROJECT_MEMORY.md`
  Durable strategic truth, long-lived decisions, product philosophy.
- `docs/ai/AI_TEAM_OPERATING_RULES.md`
  AI team operating discipline, CTO instruction compliance, and reporting requirements.
- `ai-ledger/`
  Detailed implementation/session audit trail.
- `AI_REPORT/`
  Manually collected reports from external or remote agents, especially Lubuntu/Vibecoder.

## Current Strategic Frame / 当前战略框架

- Product first, platform second.
- Primary customer is the wholesaler.
- Retailer workflows exist to improve wholesaler throughput and retention.
- Platform work must support the ERP product line and must not force architecture drift.
- `schema-per-tenant` remains the primary tenancy model.
- AI agents must preserve evidence quality: claims require commands, hashes, test output, and branch state.

中文说明：

- 产品线优先，平台线服务产品线。
- 核心客户是批发商，零售商端能力是为了提升批发商成交、复购和履约效率。
- 平台层不是另起炉灶，而是在不破坏现有 ERP 架构的基础上增加 SaaS 管控能力。
- 租户隔离继续采用 `schema-per-tenant`，不得擅自改成共享表或新租户模型。
- AI 团队必须用证据说话：分支、commit hash、测试结果、环境前提都要写清楚。

## Current Branch Map / 当前分支地图

- `origin/product-dev-recovered`
  当前产品主基线。已完成产品线恢复、平台 P0 集成、Gate 6B/6C 验证、最终晋升和项目交接文档同步。
  当前 HEAD: `030e96449ea9e09559fb777cfb62b8d66a08d92a`.
- `origin/ops/integration-rehearsal-clean-2026-05-08`
  集成彩排候选分支，当前 HEAD: `803634b9b46cdb454c25e89e28170e658601c9de`. 已被合入
  `product-dev-recovered`，保留作审计和回溯。
- `origin/platform-dev`
  平台线历史/并行分支。其已验证平台 P0 基座已经通过 promotion 进入 `product-dev-recovered`。
  后续平台开发必须先从最新 `product-dev-recovered` 对齐，避免再次形成“两张皮”。
- `origin/main`
  尚未晋升，保持不变。不要在未获 CTO 明确批准时推送或合并到 `main`。
- `product-dev-backup`
  历史备份分支。保留作恢复参考，不作为活跃开发主线。

## Promotion Summary / 2026-05-13 晋升结论

The product/platform integration is now promoted to `origin/product-dev-recovered` via:

`2e8e506 merge: promote platform integration into product-dev-recovered`

Key evidence:

- Gate 6B DB-capable targeted tests:
  `127 passed, 1 xfailed, 0 failed, 0 errors`.
- Gate 6C clean migration path:
  `alembic upgrade head` from clean DB succeeded through migration `021`.
- Lubuntu Stage 4D-R anti-gaming evidence:
  `40 passed, 0 failed, 0 skipped, 0 deselected` for schema contract tests at commit `803634b`.
- Merge into `product-dev-recovered` had no conflicts.
- `origin/main` was not changed.

中文结论：

- 双线合并已经完成一次关键闭环。平台线 P0 基座已经不再只是“平台分支上的成果”，而是进入了
  当前产品基线 `product-dev-recovered`。
- 这次合并验证了平台层基础设施可以与产品线共存，不再属于“理论上可合并”。
- 仍然不能把这理解为可以随意双线并行。未来双线开发必须更严格：开工前 fetch，对齐文档，
  明确写范围，避免多个 AI 修改同一片代码。

## Product Line Status / 产品线现状

Accepted before recovery:

- Phase 3 pricing MVP accepted.
- Phase 4 pricing-safe wholesaler order creation accepted.

Recovered and promoted state:

- Phase 5 order/payment loop recovered.
- Auth regressions repaired:
  `select-tenant` and identity-only `/auth/me` restored.
- Payment runtime repaired:
  nested transaction conflict removed from payment creation path.
- Tenant schema lifecycle repaired:
  `bootstrap_tenant_schema.py` now reconciles payments, reporting views/materialized views, and
  `retailer_prices`.
- Schema contract guard added:
  `backend/tests/test_payments_schema_contract.py`.
- Pricing and payment targeted suites passed in DB-capable promotion gate.

中文说明：

- 订单、支付、定价主链已经回到可继续推进的状态。
- `retailer_prices` 缺失问题已经被修复并加了 schema-contract 防线。
- 新租户 bootstrap 现在会补齐 `payments`、reporting、`retailer_prices` 等关键结构，降低“迁移跑过但新租户缺表”的风险。
- 目前产品线下一步不是继续救火，而是进入更有纪律的 MVP 功能推进。

## Platform Line Status / 平台线现状

Platform P0 baseline has been integrated into `product-dev-recovered`.

Accepted platform capabilities now included in the product baseline:

- platform routing scaffold
- platform tenant lifecycle scaffold
- platform audit log boundary
- platform operational reporting stats
- audit time-range filtering and activity summary enhancement
- platform handoff skill and governance docs

Platform constraints remain:

- No auth rewrite.
- No tenancy rewrite.
- No billing engine unless explicitly approved.
- No tenant-schema migration in platform-only work.
- Platform tables live in `public` schema with `platform_` prefix.
- Platform references `wholesalers.id`; it must not duplicate tenant identity.

中文说明：

- 平台线基座已经平稳并入产品基线，但平台线仍然必须保持 proposal-first。
- 下一阶段平台工作可以继续做只读管控、审计、状态面板等低风险增量。
- 暂不进入计费系统、订阅系统、租户生命周期写操作，除非 CTO 单独批准。

## Validation Snapshot / 验证快照

Latest reliable validation evidence:

- `2e8e506` final promotion commit pushed to `origin/product-dev-recovered`.
- `030e964` project handoff document sync pushed after promotion.
- Gate 6B:
  - schema contract: `40 passed`
  - pricing: `34 passed`
  - payments/order: `53 passed, 1 xfailed`
- Gate 6C:
  - clean DB migration `001 -> 021` passed with no `alembic stamp`
  - targeted tests: `127 passed, 1 xfailed, 0 failed`
- Lubuntu post-promotion sync:
  - remote sync confirmed at `2e8e506`
  - local checkout succeeded
  - validation limited by Lubuntu DB availability in the final sync report

Known caveat:

- Do not claim full product-wide 100% validation yet.
- Some environments without PostgreSQL will show skips/errors for live DB tests.
- Full backend regression is still desirable before any future `main` promotion.

## Current Risks / 当前风险

- Windows main workspace is dirty and must not be used as a promotion execution environment.
- Temporary promotion worktrees were cleaned after archiving manual evidence, but main workspace still needs a separate sync plan.
- Full backend regression has not yet been declared universally green across every environment.
- Known `xfailed` test remains in the payment/order suite; do not report it as normal pass.
- Deployment prerequisites must be respected:
  - `database/init.sql`
  - `PYTHONIOENCODING=utf-8` on Windows
  - `REPORTING_USER_PASSWORD`
  - reachable PostgreSQL/Redis for live DB tests

中文说明：

- 当前最大工程风险不是 `retailer_prices`，而是工作区治理和环境一致性。
- Windows 主工作区仍然很脏，不允许直接切换或重置。
- 后续任何正式合并都必须继续使用 clean worktree。
- 测试报告必须区分：通过、跳过、预期失败、环境失败，不能把环境失败包装成通过。

## AI Team Operating Discipline / AI 团队纪律

All agents must:

- Fetch and verify remote state before starting.
- Read `docs/ai/PROJECT.md` before implementation.
- Preserve branch boundaries.
- Use clean worktrees for risky merge/promotion work.
- Never push without explicit CTO approval.
- Never use `git reset --hard` without explicit human approval.
- Never hide skips, xfails, or environment errors.
- Report exact commit hashes, branch names, and test counts.
- Add CTO Instruction Compliance Check before requesting review.

中文说明：

- 不允许“感觉完成”。必须证明完成。
- 不允许“为了通过而跳过测试”。
- 不允许在脏工作区做晋升、合并、清理。
- 不允许多个 AI 在不同机器上各自维护一套不同的项目文档。
- 阶段性成果必须更新项目说明文档，并确保远程可见。

## Future Plan / 未来规划

### Near-term product plan

1. Stabilize the promoted `product-dev-recovered` baseline across machines.
2. Sync Windows and Lubuntu to the promoted baseline.
3. Resolve Windows main workspace governance separately, without destructive cleanup.
4. Resume Phase 6 credit payment MVP with the minimal safe accounting model:
   - full-credit sale only
   - no split tender
   - no partial credit
   - clean order only
   - outstanding balance increases correctly
   - order lifecycle closes safely

### Near-term platform plan

1. Continue only proposal-first slices.
2. Prefer read-only platform capabilities before write workflows.
3. Keep platform governance docs and handoff skill aligned with `product-dev-recovered`.
4. Do not start billing/subscription/quota enforcement without CTO approval.

### Validation and harness plan

1. Keep schema-contract tests as a permanent guardrail.
2. Add DB-capable nightly validation once the Lubuntu/remote environment is stable.
3. Add Playwright/E2E only after backend baseline is stable.
4. Treat skips and xfails as tracked engineering debt, not invisible success.
5. Before any future promotion to `main`, run:
   - targeted gate tests
   - clean migration path validation
   - DB-capable full or critical regression
   - anti-gaming evidence for any surprising pass

## Next Expected Action / 下一步安排

Immediate next actions:

1. Sync all active agents to `origin/product-dev-recovered@030e964`.
2. Do not use the dirty Windows main workspace for new development until its state is reviewed.
3. Start new product work from a clean branch/worktree based on `origin/product-dev-recovered`.
4. If continuing product MVP, next feature is Phase 6 credit payment minimal safe model.
5. If continuing platform work, next slice must start with a proposal and boundary check.

Recommended branch/worktree rule:

- New product work:
  branch from `origin/product-dev-recovered`.
- New platform work:
  branch from `origin/product-dev-recovered` unless CTO explicitly asks to resume `platform-dev`.
- Validation/promotion work:
  always use a clean temporary worktree.

## Current Non-Negotiables / 当前红线

- Do not change `schema-per-tenant`.
- Do not push to `main` without CTO approval.
- Do not delete historical backup branches without explicit human approval.
- Do not treat skipped live DB tests as passed.
- Do not report route-level or live validation unless the tests actually ran.
- Do not use dirty worktrees for merge/promotion.
- Do not allow platform work to force product architecture drift.
- Do not start billing or subscription engines without explicit approval.
- Do not let `PROJECT.md` drift behind the actual accepted branch/blocker state.

## What A New Agent Should Preserve / 新 Agent 必须继承什么

- `product-dev-recovered@030e964` is the current accepted product baseline.
- Platform P0 has been integrated into the product baseline.
- `main` is not yet the active promoted branch.
- The wholesaler-first product hierarchy remains the guiding product truth.
- Phase 3 pricing and Phase 4 pricing-safe order creation remain accepted baselines.
- Phase 5 order/payment recovery is complete enough to continue MVP work.
- Phase 6 credit payment must start with the minimal safe model, not a full accounting redesign.
- Clean worktree discipline is mandatory.
- Live DB test evidence must not be faked by skip/deselect.

## Update Rule / 更新规则

Update this file when any of the following changes:

- active branch strategy
- accepted phase/slice status
- current blocker list
- project-wide next action
- promotion status
- cross-machine sync state
- AI team operating discipline

Keep entries concise.
Do not turn this into a raw transcript or a duplicate of `ai-ledger/`.
