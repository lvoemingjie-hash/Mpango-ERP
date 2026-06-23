# P18-D Real Registry Source Status Integration -- Ledger

**Date:** 2026-06-24
**Branch:** `codex/platform-p18d-real-registry-source-status-2026-06-23`
**Base:** `309ac04` (origin/platform-dev -- P18-B/C controlled actions skeleton R0/R1/R2).
**Commit:** the P18-D commit at branch tip (short SHA in the session report; kept out of
this ledger so it stays non-self-referential).
**Push target:** `origin/codex/platform-p18d-real-registry-source-status-2026-06-23`.
**Report path:** `ai-ledger/platform/2026-06-24_p18d_real_registry_source_status.md`.
**Author:** Codex (Claude worker)

**Statement:** Read-only integration. Wires the P18 resolver to the existing P17 read model.
No action is executed; no registry, lifecycle, flag, provisioning, backup, or tenant data is
changed; no migrations; no persistent queue.

**Scope:** Backend resolver plus tests; frontend page plus tests. Read-only integration; no mutation.

**Summary:** P18-D replaces the P18-B/C resolver stub with a real P17 registry read. The resolver reads `get_tenant_registry` (read-only) and selects, per action type, the source status of the targeted P17 sub-source.

**Action groups:** Lifecycle actions (tenant.pause, tenant.resume, lifecycle.transition) read the lifecycle state status. Flag actions (support_mode on/off, incident flag set/clear) read the operational-flags status. provisioning.recheck reads the provisioning status (unavailable when null). Backup actions read the backup status (unavailable when null).

**Degraded behavior:** Unknown or unavailable sources deny write and write_request actions; only provisioning.recheck and backup.check may take the degraded path. A missing tenant, a null tenant (platform-wide action), or any read error resolves to unknown. The resolver never raises and never mutates. All responses carry executed False.

**Modified files:** backend/api/v1/platform/p18/services.py (real resolver, action groups, helper), backend/tests/test_platform_p18_controlled_actions.py (_make_app registry hook), backend/tests/test_platform_p18d_real_registry.py (new; 12 real-source tests), frontend/src/pages/platform/PlatformControlledActionsPage.tsx (denied vs degraded distinction plus degraded_reason), frontend/src/pages/platform/__tests__/PlatformControlledActionsPage.test.tsx (2 new tests), and this ledger.

**Checks (all PASS):** Base gate (origin/platform-dev tip 309ac04; P18-B/C is an ancestor). git diff --check rc 0 (no whitespace errors). Forbidden-path audit clean: only platform p18 files plus this ledger; no migrations, alembic, config, product-recovered, or business paths; the P18 route handlers are not touched (service-layer only). Non-ASCII scan: 0 hits in every changed file. Pre-commit hooks Passed on all changed files (trailing whitespace, end of file, large files, baseline detect). npx gitnexus analyze PASS.

**Tests (all PASS):** Backend P18 61 passed (49 prior plus 12 new real-source tests in test_platform_p18d_real_registry.py). Backend regression P10 plus P17 plus P15: 208 passed. Frontend P18 page: 8 passed (6 prior plus 2 new). The 12 new backend tests cover lifecycle available and unknown, lifecycle.transition, flag-unavailable denied, provisioning available and null, backup null (degraded read and denied write_request), tenant not found, P17 read error, null tenant, and executed False on every path.

**Risk:** HIGH (platform-runtime) but contained. The change is read-only integration: the resolver reads the existing P17 read model and never mutates. No action executes; unknown is returned on every failure path. Residual HIGH only because the branch touches platform-runtime code (not docs-only).

**GitNexus:** npx gitnexus analyze PASS (graph intact). detect_changes is MCP-only with no CLI in this build; verified equivalently via git diff name-only against origin/platform-dev: only the platform p18 files and this ledger. api_impact N/A: no P18 route handler changed (service-layer resolver only).

**Blockers:** None. Real execution of any controlled action remains blocked unless separately approved; this phase only resolves source status from the real registry read.
