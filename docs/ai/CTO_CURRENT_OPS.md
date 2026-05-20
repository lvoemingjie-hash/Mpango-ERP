# CTO Current Ops / 当前作战摘要

**Last updated:** 2026-05-16
**Owner:** Codex acting as CTO
**Purpose:** Give every AI agent a short, current, evidence-aware operating picture before touching code.

本文件是 Mpango ERP 的“当前态势图”。它不是完整历史，不替代 `ai-ledger/`，也不是新的产品需求文档。它的作用是让 Codex、Claude Code、Leo、Goose、OpenCode、CodeBuddy 或其他 agent 在几分钟内知道：

- 项目现在真实处于什么状态。
- 当前最重要的目标是什么。
- 哪些边界不能碰。
- 哪些证据可信。
- 下一步应该怎么做。

If this file conflicts with contracts or decision records, pause and reconcile through repository docs before coding.

## Read Order / 启动阅读顺序

For new AI work, read in this order:

1. `docs/ai/README.md`
2. `docs/ai/CTO_CURRENT_OPS.md`
3. `docs/ai/PROJECT.md`
4. `docs/ai/PROJECT_MEMORY.md`
5. `docs/ai/AI_TEAM_OPERATING_RULES.md`
6. Relevant `ai-ledger/` entries only when exact evidence or history is needed

原则：先读当前态势，再查长期记忆，最后才进入详细审计账本。不要一上来吞完整历史聊天或完整 ledger。

## Memory Model / 记忆分层

Mpango AI team uses five memory layers:

- **Constitution layer:** non-negotiable rules such as tenant isolation, no unauthorized push, evidence-first reporting, no destructive git cleanup without approval.
- **Current ops layer:** this file. It captures current baseline, active work, risks, and next actions.
- **Project memory layer:** durable strategic truths in `PROJECT_MEMORY.md`.
- **Ledger evidence layer:** detailed action trail in `ai-ledger/`; use for audit, dispute resolution, or exact command reconstruction.
- **External validation layer:** Leo/Vibecoder/GitHub Actions reports; useful evidence, but not self-approving.

中文原则：

- 不靠长聊天维持项目记忆。
- 不让 agent 每次读取几十 MB 背景材料。
- 当前任务只给“作战包”，详细历史按需索引。
- 所有关键状态必须落在仓库文档或 ledger 中，不能只存在对话里。

## Current Baseline / 当前基线

Canonical product baseline:

- Branch: `origin/product-dev-recovered`
- Current promoted commit: `f70cf332e507fee5ab5e11c09e0aa34de987b4a3`
- Commit message: `merge: promote phase6 receivables closeout`
- Meaning: Phase 6 credit payment semantics, receivables read-side work, and platform integration closeout have been promoted into the current product baseline.

Main branch:

- `origin/main` remains behind the active product baseline.
- Do not promote to `main` without a separate CTO-approved release gate.

Dirty workspace warning:

- `C:\Users\Jeff0\MPANGO ERP\windsurf mpango erp` is not suitable for promotion or controlled sprint work right now.
- Use clean worktrees for implementation, validation, merge rehearsal, and documentation updates.

Current clean documentation baseline used for this update:

- `C:\Users\Jeff0\MPANGO ERP\phase6-closeout-promotion-2026-05-15`
- Branch: `product-dev-recovered`
- HEAD: `f70cf332e507fee5ab5e11c09e0aa34de987b4a3`

## Accepted Evidence / 已接受证据

Latest local ledger evidence for Phase 6 closeout:

- `ai-ledger/product-ai/2026-05-15_phase6_receivables_closeout_promotion.md`
- Receivables service/API: `38 passed, 0 failed, 0 skipped`
- Phase 5/6 payment regression: `53 passed, 1 xfailed, 0 failed, 0 skipped`
- DB schema contract: `40 passed, 0 failed, 0 skipped`

Phase 6.3A accepted scope:

- Receivables API contract stabilization.
- Frontend-readiness guardrails.
- Read-only receivables visibility.
- No accounting rewrite.

Promotion evidence caveat:

- Do not claim product-wide 100% validation from targeted suites.
- A known `xfailed` payment/order test is acceptable only when explicitly reported as `xfailed`.
- DB-capable tests with unexplained skips must not be reported as PASS.

## Current Product Direction / 当前产品方向

Immediate objective:

- Finish the MVP loop for real wholesaler usability.

Current product thesis:

- Wholesaler is the primary customer.
- Retailer-facing features exist to increase wholesaler throughput, repeat purchases, and payment recovery.
- Credit sales are MVP-relevant, but must stay inside a minimal safe accounting model.

Current Phase 6 meaning:

- Credit payment is not a cash receipt.
- A credit sale can close the order lifecycle while preserving accounts receivable.
- Later repayment must reduce receivables and increase cash through controlled payment paths.
- No split-tender or partial-credit semantics may be introduced casually.

## Active Sprint / 当前冲刺

Sprint name:

- MVP Sprint A: credit sales / receivables / repayment usability loop.

Active worktree:

- `C:\Users\Jeff0\MPANGO ERP\mvp-sprint-credit-loop-2026-05-15`

Active branch:

- `codex/mvp-sprint-credit-loop-2026-05-15`

Base:

- `origin/product-dev-recovered` at `f70cf332e507fee5ab5e11c09e0aa34de987b4a3`

Current sprint state:

- Worktree is clean.
- Frontend dependencies are present in this worktree after CTO-controlled `pnpm install --frozen-lockfile --ignore-scripts`.
- Backend tests can reuse an existing Poetry virtualenv instead of reinstalling dependencies.

Primary sprint slice:

- Improve `frontend/src/pages/finance/FinancePage.tsx` into a clearer wholesaler accounts receivable dashboard.
- Use existing backend endpoints via `frontend/src/services/financeService.ts`.
- Prefer safe navigation to existing `/orders` repayment flow rather than duplicating payment modal behavior inside finance.
- Do not rewrite backend accounting, auth, tenancy, permissions, migrations, or ledger logic.

Success standard for Sprint A:

- The wholesaler can clearly see outstanding receivables, overdue risk, cash/revenue summary, order balance, paid amount, and next action.
- Build/type checks pass.
- Relevant backend targeted suites remain green or blocked only by explicitly classified environment issues.
- Ledger records exact branch, commit, changed files, commands, results, and gaps.

## Dependency Policy / 依赖策略

Default rule:

- Reuse first.
- Diagnose second.
- Install only after CTO/user approval.

Frontend:

- This repo uses `pnpm-lock.yaml`.
- Do not run `npm install` for frontend dependencies.
- If dependency preparation is required, use:

```powershell
pnpm install --frozen-lockfile --ignore-scripts
```

- Prefer CTO-controlled dependency preparation before Claude or another coding agent starts.
- `node_modules/` is local to each worktree and should remain ignored.

Backend:

- Poetry uses global virtualenvs under:

```text
C:\Users\Jeff0\AppData\Local\pypoetry\Cache\virtualenvs
```

- Current reusable Python for backend targeted tests:

```text
C:\Users\Jeff0\AppData\Local\pypoetry\Cache\virtualenvs\mpango-erp-backend-WPJOVxVi-py3.12\Scripts\python.exe
```

- Prefer this interpreter for short targeted tests in clean worktrees when lockfile compatibility is unchanged.
- Do not run `poetry install` unless CTO/user approves.

Environment variables:

- Use `MPANGO_ENV=test` for backend test/import smoke.
- Generate a secure test `SECRET_KEY`; do not use weak substrings such as `secret` or `123456`.
- DB-capable tests require reachable PostgreSQL/Redis and correct DB credentials.

## Agent Roles / AI 团队分工

Codex CTO:

- Owns direction, scope, risk control, review, and final decision.
- Runs impact analysis and validation checks where appropriate.
- Creates small executable directives for other agents.
- Stops long-running or drifting agents.
- Updates this current ops file after meaningful phase changes.

Claude Code:

- Primary product-line coding executor.
- Should receive small tasks sized for 5-10 minutes.
- Must not install dependencies unless explicitly approved.
- Must not commit or push unless explicitly instructed.
- Must leave exact evidence and ledger notes.

Leo headless runner:

- DB-capable and cross-environment validation on Lubuntu via GitHub Actions.
- Should run from directives and produce reports under `reports/lubuntu-validation`.
- Must collect skip reasons; unexplained DB skips downgrade verdict.
- Does not approve product changes by itself.

Vibecoder:

- Human-facing Lubuntu coordinator and skill/report workflow maintainer.
- Should not be used as the long-running headless executor when Leo can run the gate.
- Can help inspect runner health, directive workflow, and report delivery.

Goose / OpenCode:

- Platform or OPS support agents when explicitly assigned.
- Must use clean worktrees and bounded scopes.
- Must not drift platform docs away from product baseline.

CodeBuddy / SWE-style agents:

- Auxiliary executors or reviewers for bounded tasks.
- Must follow the same evidence and no-push discipline.

## Harness Rules / 执行护栏

Small-task rule:

- Break work into 5-10 minute agent tasks.
- If an agent runs longer than expected, inspect process state, git status, and diff.
- Do not wait indefinitely for a stuck agent.

Before coding:

- Confirm branch and worktree.
- Confirm dependency state.
- Confirm no unrelated dirty files will be swept into the task.
- Run GitNexus impact before editing indexed functions/classes/methods.

During coding:

- Stay inside assigned files.
- Avoid broad refactors.
- Do not change auth, RBAC, tenancy, migrations, payment semantics, or ledger semantics unless the task explicitly requires CTO escalation.

Before review:

- Run relevant targeted tests/builds.
- Run `git status --short`.
- Run `git diff --name-only`.
- Add or update ledger for meaningful implementation.
- Separate code failures, environment failures, test-data failures, and branch-sync failures.

## Current Validation Commands / 当前推荐验证命令

Frontend from `frontend/`:

```powershell
pnpm run build
pnpm run lint
```

Backend from `backend/`, using the reusable Python interpreter:

```powershell
$env:MPANGO_ENV='test'
$env:SECRET_KEY='<secure-generated-test-key>'
C:\Users\Jeff0\AppData\Local\pypoetry\Cache\virtualenvs\mpango-erp-backend-WPJOVxVi-py3.12\Scripts\python.exe -m pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short
C:\Users\Jeff0\AppData\Local\pypoetry\Cache\virtualenvs\mpango-erp-backend-WPJOVxVi-py3.12\Scripts\python.exe -m pytest tests/test_phase5_order_payment.py -q --tb=short
```

Repo checks:

```powershell
git status --short
git diff --name-only
```

## Current Risks / 当前风险

- Long context can pollute agent judgment; use this file as the current task memory gate.
- Dirty default workspace must not be used for controlled sprint execution.
- Frontend dependency command drift is dangerous; `npm install` is not the default path for this repo.
- Backend Poetry envs are path-hashed; do not assume a new worktree automatically has an env.
- Targeted tests are not full MVP acceptance.
- DB-capable validation reports must account for skipped tests.
- Any change to credit/payment/ledger semantics can cause accounting regressions and requires CTO review.

## Next Actions / 下一步

1. Use Claude Code for the small frontend Sprint A task:
   - Target: `frontend/src/pages/finance/FinancePage.tsx`
   - Scope: receivables dashboard usability
   - No dependency install
   - No backend semantics change
   - No commit/push

2. Codex CTO reviews Claude diff:
   - Check file scope.
   - Check business semantics.
   - Run build/lint/targeted tests.
   - Add missing ledger polish if needed.

3. If local checks pass:
   - Commit only intended files.
   - Push feature branch only with approval.
   - Trigger Leo DB-capable validation if backend/API contracts are touched or if promotion evidence is required.

4. After Sprint A:
   - Update this file.
   - Update `PROJECT.md` if baseline, branch ownership, accepted scope, or next task changes.
   - Keep detailed evidence in `ai-ledger/`.

## Update Protocol / 更新规则

Update this file when any of these change:

- Current product baseline commit.
- Active sprint branch or worktree.
- Agent role assignment.
- Dependency reuse path.
- Validation gate results.
- Current blockers or next actions.
- Any rule needed to prevent repeated AI failure.

Keep this file concise. If a detail becomes long, move it to `PROJECT.md`, `PROJECT_MEMORY.md`, or `ai-ledger/`, then link to it here.
