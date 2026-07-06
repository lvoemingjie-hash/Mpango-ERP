# P25-A Platform Frontend Customer Readiness Contract

Date: 2026-07-06
Phase: P25-A (contract-only design for the platform frontend customer / operator
readiness layer; the readiness definition, the as-built route inventory, the validation
matrix, the safety boundaries, the evidence plan, the acceptance criteria, and the
counterexamples that bound all later P25 validation work).
Branch: codex/platform-p25a-platform-frontend-customer-readiness-contract-2026-07-06
Base: origin/platform-dev = e5c28ec (P24 incident + runbook closeout: P24-A contract,
P24-B non-executing / non-sending backend skeleton, P24-C frontend console, and P24-D
closeout all merged; P24_INCIDENT_RUNBOOK_CLOSEOUT_READY).
Scope: docs / ledger only. No new feature, no backend runtime code, no frontend runtime
code, no migration, no alembic change, no package or lockfile change, no test code.

This phase defines the platform frontend customer readiness contract only. It does not
implement, execute, approve, flag, dispatch, queue, schedule, deliver, migrate, or merge
anything into platform-dev. It is an isolated, docs-only branch. P25-B is not started.

## 1. Phase inventory

P25-A - platform frontend customer readiness contract (docs-only)
- Source branch: codex/platform-p25a-platform-frontend-customer-readiness-contract-2026-07-06
- Base: origin/platform-dev = e5c28ec
- Report path: ai-ledger/platform/2026-07-06_p25a_platform_frontend_customer_readiness_contract.md
  (this file)
- Scope: docs-only readiness contract over the as-built P10-through-P24 platform frontend
  surface (readiness definition + closed route inventory grounded in AppRouter.tsx /
  Sidebar.tsx + validation matrix + safety boundaries + evidence plan + future P25-B
  validation-harness boundary)
- Risk: LOW (docs-only, no runtime code, no migration, no execution, no flag mutation,
  no approval, no notification delivery, no storage switch, no product merge)
- Status: contract on isolated branch; not merged to platform-dev

## 2. Capability statement

P25-A defines (contract only, no runtime code) the platform frontend customer / operator
readiness layer. P10 through P24 each landed one non-executing / non-sending capability
slice (or, for backup.check only, a single read-only governed action) behind a
contract-first gate, but no phase stitched the routes into a single readiness story.
P25 is that story. It is NOT a new platform capability; it is a validation / readiness
layer over the as-built surface. After P25-A is accepted, a future P25-B may build --
under its own entry gate -- a NON-SHIPPING, NON-MERGING frontend validation / smoke
harness (a Playwright or component-level guard / page test harness with a mocked backend
where no runnable stack exists, scrubbed screenshots, a matrix runner, and a demo script);
any feature implementation, any real defect fix, any auth / RBAC change, any migration,
any execution expansion, and any notification delivery are each reserved for separately
approved phases. P25-A fixes the boundary for:

- Readiness definition: a route is customer / operator ready when it is reachable under
  the identity-only guard, navigable from the sidebar, and renders sane empty / loading /
  error / denied states, leak-safe copy, intact layout (no clipped text, no overlap), and
  consistent console tone across P22 / P23 / P24, and when it does not regress a prior
  display invariant (source_unknown never healthy, backup_check_warning never success, no
  tenant leak, no forbidden execute / approve / flag-mutate / deliver control).
- Route inventory: the CLOSED set of as-built platform routes (19 routes) grounded in
  frontend/src/router/AppRouter.tsx and frontend/src/components/layout/Sidebar.tsx --
  overview / health / registry / support / operations (/platform, /platform/system/health,
  /platform/tenants, /platform/tenants/:tenantId/health, /platform/audit, /platform/registry
  P17, /platform/support P12, /platform/ops/{health,errors,slow-routes,resources,
  noisy-neighbors} P13/P14, /platform/ops/incidents/triage P15), controlled actions /
  approvals / durable approvals (/platform/controlled-actions P18, /platform/approvals P19,
  /platform/durable-approvals P20/P21), controlled execution / backup check
  (/platform/controlled-execution P22; the read-only backup.check governed action is bound
  here per P22-G / P22-E3), operator tasks (/platform/operator-tasks P23), and incident
  closeouts / runbooks (/platform/incident-closeouts P24; the runbook checklist is embedded
  in this page per P24-C -- there is no separate runbook route). Every route is behind the
  PlatformRoute identity-only global super_admin guard (roles includes super_admin AND
  tenant_id is null; tenant-contextual super_admin and non-super_admin are denied).
- Validation matrix: every route is checked against 12 dimensions (route smoke; real login
  smoke where a runnable stack exists and the deny path for tenant-contextual super_admin /
  non-super_admin; Playwright screenshots where feasible; empty state; loading state; error
  state; denied state; sidebar-to-detail-to-form navigation; copy review against the
  never-leaked list; no-overlap / no-clipped-text; frontend console consistency; invariant
  preservation). A matrix cell is pass / skip-with-reason / fail; a silent skip is never
  recorded as a pass.
- Safety boundaries: no new backend capability, no migration, no product branch merge, no
  product business mutation, no auth / RBAC rewrite, no P22 execution expansion, no
  notification delivery, no tenant leak accepted as ready, no source_unknown shown healthy,
  no backup_check_warning shown as success, no audit-history deletion, no AI agent
  execution / auto-approval / auto-close, and no secret / payload leak in evidence.
- Evidence plan: route list, validation matrix result, scrubbed screenshots, commands, test
  counts (with known P17-D-C / P22-E3 date-roll flakes called out), known warnings, demo
  script, and a defect list (defects are RECORDED for a later separately approved fix
  slice, not fixed inline by P25-B).
- Acceptance criteria (25) and counterexamples (22) that bound all later P25 work.

## 3. Safety statement

P25-A is docs-only. It creates one contract markdown, updates the docs/ai/README.md
Platform Product Track read order (entry #25 plus a readiness paragraph), and adds this
ledger. It performs no execution, no approval, no flag mutation, no notification delivery,
no tenant mutation, no product business mutation, no auth / RBAC / session / tenancy
change, no migration, no storage switch, and no merge. It does not push to platform-dev
(the feature branch is pushed with an explicit X:X refspec; origin/platform-dev is left
unchanged at e5c28ec). A route inventory, a validation matrix, and an evidence plan are
planning artifacts only; no harness, screenshot, command, or demo script is produced in
P25-A. P25-B is not started.

## 4. Verification (docs-only branch, all must pass)

Verified on this branch versus origin/platform-dev = e5c28ec:

- git diff --check origin/platform-dev..HEAD (and the working tree): clean (no whitespace
  errors).
- Commit: branch tip (short SHA recorded in the session report; kept out of this file so
  the ledger stays non-self-referential; no 40-char SHA in this file).
- Changed files exactly equal three docs / ledger files:
  - docs/ai/PLATFORM_PRODUCT_P25_FRONTEND_CUSTOMER_READINESS_CONTRACT.md (new)
  - docs/ai/README.md (Platform Product Track read order updated; P25 entry #25 +
    readiness paragraph)
  - ai-ledger/platform/2026-07-06_p25a_platform_frontend_customer_readiness_contract.md
    (new, this file)
- Non-ASCII scan of the three files: 0 hits (pure ASCII; verified byte-wise with a Python
  ordinal check; no section sign, box-drawing, em dash, middot, smart quotes, or arrows).
- detect-secrets (detect-secrets pre-commit hook v1.5.0 against the configured secret
  baseline .secrets.baseline) on the new docs: PASS, exit 0, no new secrets. The configured
  baseline file is not modified (git diff origin/platform-dev -- .secrets.baseline is
  empty). A raw audit scan (no baseline) of the new docs also returns no potential secret
  findings. No 40-char SHAs are present in any new file.
- Forbidden path audit (changed paths under backend/, frontend/, migrations/, alembic/,
  package or lock files, auth / RBAC / session, payment / billing, tenant business code,
  product-dev-recovered/, .github/, .claude/, or the configured secret baseline): 0 hits.
  All changed paths are docs/ai/*.md or ai-ledger/platform/*.md.
- npx gitnexus analyze : graph intact (band recorded in section 5); no execution /
  approval / flag / delivery / frontend-flow affected by a docs-only change.
- GitNexus detect_changes corroborator: the docs-only diff (one contract markdown, one
  README read-order edit, one ledger) touches no code symbols, so the changed-code-symbol
  set and the affected-runtime-flow set are both empty -- the cleanest possible docs-only
  result. (The detect_changes tool is MCP-only and flaky in this environment; where the
  MCP stdio server is unresponsive, `git diff --name-only origin/platform-dev..HEAD` is the
  corroborator: only docs/ai/*.md and ai-ledger/platform/*.md paths appear, so zero code
  symbols and zero runtime flows are affected.)
- Working tree clean after commit.

## 5. GitNexus summary

- P25-A is docs-only: a contract markdown doc, a README read-order edit, and a ledger. No
  runtime symbols, no execution-flow impact, no approval-flow impact, no flag-mutation
  impact, no notification-delivery impact, no frontend-flow impact.
- The change adds documentation only; no backend, frontend, migration, package, auth,
  payment, tenant, product, execution, approval, or notification path is touched.
  GitNexus was re-run after the feature docs were committed; `status` is up-to-date at
  the current P25-A branch tip (the exact repair / validation tip SHA is reported in
  chat only, not embedded here, to keep this ledger non-self-referential). The observed
  analyze counts remain within the documented P24-P25 band -- roughly 9,393-9,466 nodes /
  28,767-28,846 edges / 584-598 clusters / 300 flows. The code graph is unchanged from
  base e5c28ec because markdown is not a code symbol. Flows are stable at 300 (unchanged
  from the P24-D base), and the affected runtime-flow set is empty.

## 6. Forbidden audit summary

P25-A touches none of the following (all verified by the changed-path audit):

- No backend / runtime code path.
- No frontend code path (the route inventory and validation matrix DESCRIBE the as-built
  frontend; no frontend file is added, modified, or deleted in P25-A).
- No migration or alembic change.
- No payment or billing change.
- No package.json, pnpm-lock, package-lock, or yarn.lock change.
- No product-dev-recovered path.
- No auth / RBAC / session rewrite (P25 reuses the P10 / P11 PlatformRoute identity-only
  global super_admin guard unchanged).
- No .github / CI change.
- No .claude change.
- No change to the configured secret baseline.
- No execution path (readiness is validation, not execution; no P22 action is dispatched,
  no allowlist widened, no worker added in P25-A).
- No approval path (no P19 / P20 / P21 approval is decided).
- No flag-mutation path (the P17 incident_active flag is not written; P25 only plans to
  validate that the UI mirrors it honestly).
- No notification-delivery path (notification events stay at P23 delivery_state == recorded;
  P25 wires no channel).
- No product business mutation path (P25 validates platform surfaces only; no order /
  payment / invoice / customer / inventory / ledger record is read or written).
- No merge path (P25-A stays on its feature branch; origin/platform-dev is left unchanged).

## 7. Open risks / non-goals

The following are intentionally not done in P25-A and are NOT P25-A blockers. They are
deferred to P25-B (and later) under their own entry gates, contract-first:

- Non-shipping, non-merging frontend validation / smoke harness (Playwright or
  component-level guard / page tests with a mocked backend where no runnable stack exists;
  scrubbed screenshots; matrix runner; demo script) -- P25-B only; no feature
  implementation, no merge, no push to platform-dev.
- Real defect fixes (a clipped control, an overlap, a missing empty state, a tone
  inconsistency, a display-invariant regression) -- each recorded by P25-B as a defect and
  fixed in a later, separately approved slice; P25-B does not fix inline.
- Real login smoke against a full runnable stack -- P25-B records pass / skip-with-reason /
  fail honestly; where no runnable stack exists, a component-level guard test substitutes.
- Any new platform capability (a new route, task type, closeout state, action, governed
  slice, or notification channel) -- a new contract revision accepted by the CTO and a new
  phase; explicitly NOT a P25 deliverable.
- Any migration / persisted store change -- a separately approved phase.
- Any auth / RBAC / session / tenancy rewrite -- a separately approved contract.
- Any P22 execution expansion (new action, worker dispatch, allowlist widening) -- a
  separately approved phase.
- Any real notification delivery (in-app push, email, webhook) -- a separately approved
  phase; bound by the never-leaked list and the identity-only platform-operator guard.
- Lifting any P25 exclusion (product business path, tenant payload leak accepted as ready,
  source_unknown shown healthy, backup_check_warning shown as success, silent skip recorded
  as pass, evidence with a secret) -- a new contract revision accepted by the CTO and a new
  phase.
- AI Operator Copilot / autonomous readiness sign-off -- no AI execution / approval / flag
  / auto-close power; no AI-specific runtime code in P25-A or P25-B.

## 8. P25-B entry gate

P25-B may implement ONLY a non-shipping, non-merging frontend validation / smoke harness
over the as-built P10-through-P24 surface: a Playwright (or equivalent) harness that logs
in as an identity-only global super_admin (or, where no runnable stack exists, exercises
the PlatformRoute guard and the page components at the unit / component level with a
mocked backend), traverses the section 3 route inventory, captures the section 4 matrix
per route (empty / loading / error / denied / navigation / copy / no-overlap / consistency
/ invariant), and writes the section 6 evidence set. P25-B must not add any new platform
capability, route, task type, closeout state, action, or governed slice; must not add any
migration, alembic change, table, column, index, or seed; must not merge into platform-dev
or product-dev-recovered, or push to platform-dev (the harness branch is pushed with an
explicit X:X refspec); must not mutate any product business record; must not rewrite auth
/ RBAC / session / tenancy or relax the PlatformRoute guard; must not expand P22
execution; must not deliver any notification; must not display source_unknown as healthy or
backup_check_warning as success, or accept such a regression as ready; must not expose
tenant-A data in tenant-B context, or accept such a leak as ready; must not commit a
screenshot or transcript that contains a secret, DSN, token, cookie, auth header, raw
payload, or real tenant business data; must not ship or merge the harness as a product
feature; must not fix a readiness defect inline; and must not record a matrix cell as pass
without an executable command, screenshot, or honest skip-with-reason. Any feature
implementation, any real defect fix, any auth / RBAC change, any migration, any execution
expansion, and any notification delivery are reserved for separately approved phases and
must stay behind the never-leaked list and the identity-only platform-operator guard.
P25-B must begin from this contract and may not change the route inventory, the validation
matrix, the readiness definition, the safety boundaries, the evidence plan, the acceptance
criteria, the counterexamples, or the never-leaked list without a new contract revision
accepted by the CTO.

## 9. Final verdict

P25_A_CONTRACT_READY (docs-only, isolated branch, not merged to platform-dev).

P25-A defines the platform frontend customer / operator readiness contract only. There is
no runtime code, no migration, no execution, no flag mutation, no approval, no notification
delivery, no tenant mutation, no product business mutation, no product branch merge, no
tenant data leak across contexts, no auth / RBAC rewrite, no frontend file change (the
inventory and matrix DESCRIBE the as-built frontend; they do not modify it), no backend,
no AI agent execution / flag-flip / auto-approval / auto-close, no deletion of audit
history, no source_unknown displayed or closed healthy, no backup_check_warning displayed
or closed as success, and no change to the configured secret baseline. P25-B is not
started. P25 is readiness, not a capability: it validates the as-built P10-through-P24
surface is usable, leak-safe, and consistent as a whole; it adds nothing new.
