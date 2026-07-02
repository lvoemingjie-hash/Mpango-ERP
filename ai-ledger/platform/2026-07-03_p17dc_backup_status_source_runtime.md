# P17-D-C Backup / Status Source Runtime (migration + ORM + registry read wiring)

**Phase:** P17-D-C Backup / Status Source Runtime (minimal runtime foundation)
**Date:** 2026-07-03
**Branch:** `codex/platform-p17dc-backup-status-source-runtime-2026-07-03`
**Base:** `eb5268c` (`origin/platform-dev` -- the P17-D-A source-contract + P22-E2 discovery
merge). Worktree `_p17dc_2026-07-03`.
**Author:** Codex (Claude worker)
**Status:** Complete; code + tests pass; ready for CTO review. Still no P22 wiring; `backup.check`
stays `source_unknown` / `not_implemented`. P22-E3 not started.

---

## 1. Summary

P17-D-C implements the accepted **P17-D-A** backup / status source contract and the **P17-D-B**
schema + model + test plan as the minimal runtime foundation: ONE additive, public-schema-only
alembic revision (`021`), the ORM read-path models, and the P17 registry `backup_status` READ
wiring. It serves the P17 registry read path ONLY. It does NOT connect P22, does NOT execute
`backup.check`, does NOT perform a real backup / restore / pg_dump, and does NOT read any external
system. The read path is READ-ONLY (writer-only mutations).

The durable source is now real (two public tables + two stored enums + the honesty CHECK
constraints + recency index), and the registry reads it through the existing freshness / redaction
/ degrade-on-failure discipline. A source with no rows reads `unknown` / null + reason (never
healthy); a stale `success` reads `stale`; a read failure degrades to null + reason (never a 500,
never a fabricated success). `backup.check` is unchanged (`source_unknown` / `not_implemented`);
lifting that gate is P22-E3, separately CTO-gated behind the PROVEN, MERGED, TESTED source.

> **Unknown is never healthy, null is never zero, success is never stale, and a backup source is
> never fabricated healthy. Approval is not execution and a table is not an execution.** P17-D-C
> builds the source the registry reads; it runs no backup, no restore, and no `backup.check`.

## 2. Base state of P17-D-B (important)

The P17-D-B schema + model + test PLAN is a docs-only branch (`codex/platform-p17db-...`, tip
`e47c48f`, two commits: the 713-line plan + its ledger) that is **pushed but NOT merged** into
`origin/platform-dev`. The task explicitly instructs P17-D-C to branch from `origin/platform-dev`
(`eb5268c`) and lists the P17-D-B plan under "read first", so P17-D-C is a **code-only**
implementation branch from `eb5268c`: the plan doc was read from its sibling branch as the
authoritative reference and is NOT copied into this branch (it ships via its own branch). The
C0 gate's literal "P17-D-B merged to base" is therefore not satisfied; this ledger records that
state explicitly. If the CTO prefers the plan doc in-tree before/alongside the code, that is a
merge of the P17-D-B doc branch, separate from this code branch.

## 3. Base / Branch / Commit Chain

- **Base SHA:** `eb5268c` (`origin/platform-dev`, the P17-D-A + P22-E2 merge).
- **Worktree:** `MPANGO ERP/_p17dc_2026-07-03`, created from `origin/platform-dev`. Upstream was
  auto-set to `origin/platform-dev` by `git branch <name> <startpoint>` and was **unset**
  (`git branch --unset-upstream`) so a bare `git push` cannot fast-forward `platform-dev`; the
  branch is published with the explicit refspec `git push -u origin <branch>:<branch>` (the
  worktree-push gotcha).
- **Commit chain (base..tip):** `eb5268c` -> `a548f6f` (R0: migration + ORM + registry read wiring
  + tests, 8 files) -> R1 (this ledger only). The R1 tip SHA is reported in the chat report, not
  self-referenced here (this ledger is part of the R1 commit).

`platform-dev` is NOT merged and is NOT the push target. Only the isolated P17-D-C branch carries
these changes and is published to its own remote ref.

## 4. Files (exactly the allowed set + two necessary regression-prevention edits)

| File | Status | Scope |
|---|---|---|
| `backend/alembic/versions/021_platform_backup_status_source.py` | New | Additive public-schema revision: `platform_backup_outcome` (append-only) + `platform_backup_policy`; two stored enums (`platform_backup_job_kind`, `platform_backup_outcome_status` -- excludes derived `stale`/`unknown`); recency index `(tenant_id, job_kind, completed_at DESC NULLS LAST)`; CHECK constraints (success requires `bytes_written > 0`; failed/partial require an allowlisted `failure_reason_code`; `in_progress` <=> `completed_at IS NULL`; bytes only for success/partial; closed-vocabulary failure reason); at-most-one-platform-default via a constant-expression partial unique index. |
| `backend/api/v1/platform/p17/models.py` | New | `PlatformBackupOutcome` / `PlatformBackupPolicy` ORM models (`models.base.Base`, `public` schema, `postgresql.ENUM(create_type=False)` with decode symbols -- the P21 ORM-enum lesson). Deliberately NOT registered in `models/__init__.py` (mirrors the P21 durable-model discipline; avoids autogenerate / `create_all` side effects); the read path imports it directly. |
| `backend/api/v1/platform/p17/services.py` | Modified | `_load_backup_status_map` (best-effort, read-only, returns `None` on read failure to distinguish unavailable from a successful empty read) + `_build_backup_status` (routes through `enforce_backup_freshness` + the 168h restore-test cadence + `redact_failure_reason`; fail-closed to `None` + reason when the source is not `available`) + the `RESTORE_TEST_CADENCE_WINDOW` constant. `_build_registry` replaces `backup_status=None` ONLY when the source reads `available`; otherwise keeps null + the honest reason. |
| `backend/tests/test_platform_p17dc_backup_models.py` | New | 14 unit tests: ORM model metadata vs migration 021 (exact columns, domain PK, types, server defaults, `create_type=False` + decode symbols, no business-table FK, closed vocabularies match `schemas.py`). |
| `backend/tests/test_platform_p17dc_backup_registry_read.py` | New | 26 unit tests (G1-G18 unit-testable cases): fresh/stale success, failed + allowlisted reason, raw-reason redaction, restore-test freshness + cadence override + unknown-until-runner, success-requires-fresh + available, returns-None-when-not-available, loader resolution (tenant-preferred / platform-fallback / latest-completed / read-only / read-failure-None / unknown-per-tenant), registry assembly through the route (fresh / no-outcome-unknown / read-failure-unavailable-no-500), and the no-P22 invariant (`backup.check` still `not_implemented` / `source_unknown`). |
| `backend/tests/test_platform_p17dc_backup_migration.py` | New | 9 integration tests on ephemeral Postgres: additive-only 020<->021, downgrade drops only P17-D-C objects, reupgrade, no tenant-schema leak, upgrade does not create a tenant schema, base revision is 020 before upgrade, CHECK-constraint honesty (G14), policy uniqueness (incl. the constant-expression partial unique for the single NULL row), latest-completed excludes `in_progress` (G17). Upgrade/downgrade upper bound PINNED to `021` (not bare `head`). |
| `backend/tests/test_platform_p21_durable_approval_migration.py` | Modified | **Regression-prevention.** The P21 migration test used a bare `head`; once 021 chains on 020, that changed what its "additions are exactly the durable tables" assertion sees. Pinned its upper bound to `020_durable_approval_store` (`HEAD_REV`) so it exercises 019<->020 in isolation, robust to later migrations and shared-DB ordering. |
| `backend/tests/test_platform_p21_durable_approval_adapter_skeleton.py` | Modified | **Regression-prevention.** `test_no_new_alembic_migration_chained_on_020` was a P21-D development gate asserting 020 had no descendants. Converted to an allowlist (`ALLOWED_DESCENDANTS = {021}`) so it still catches UNAUTHORIZED chaining while accepting the approved 021 follow-on. |
| `ai-ledger/platform/2026-07-03_p17dc_backup_status_source_runtime.md` | New | This ledger. |

No other file is touched. `docs/ai/README.md` is intentionally NOT changed (the D-family
cumulative-state sentence ships with the P17-D-B doc branch; P17-D-C is code-only and keeps the
diff minimal).

## 5. Migration / model / mapping fidelity to P17-D-B

- **Tables** match P17-D-B section 3 exactly (names, columns, Postgres types, nullability,
  defaults, PKs, the recency index, the plain + partial-unique policy uniqueness). The single
  refinement over the plan's literal text: the partial unique for the platform-default row indexes
  a CONSTANT expression (`((1)) WHERE tenant_id IS NULL`) rather than `(tenant_id)`, because
  Postgres treats NULLs as distinct in unique indexes and so `UNIQUE (tenant_id) WHERE tenant_id IS
  NULL` would NOT prevent multiple NULL rows (verified empirically in the ephemeral DB before
  fixing). This is an additive, equivalent realization of the plan's "at most one platform-default
  row" intent, documented in the migration docstring.
- **Stored enums** (`backup_job`/`restore_test_job`; `success`/`partial`/`failed`/`in_progress`)
  deliberately EXCLUDE `stale`/`unknown` -- those are read-time DERIVATIONS the adapter computes
  (a job cannot "be" stale; only a rendered status can).
- **ORM enum decode** supplies the closed value symbols so rows decode (the P21 lesson); values
  are not invented at runtime and `create_type=False` is preserved (no DDL on import).
- **`tenant_id` is a scoped identifier**, never a FK into any tenant business table (verified by
  the model test's `test_no_business_table_references` and the forbidden-path audit).
- **Mapping** follows P17-D-B section 5: tenant-specific outcome preferred, else platform-wide
  fallback, applied independently per `job_kind`; `last_backup_status` routed through
  `enforce_backup_freshness` (24h); `restore_test_status` through the 168h cadence (per-policy
  overridable); `failure_reason_redacted` collapsed by `redact_failure_reason`; `backup_source_status`
  the honest hinge (`available` only when readable AND an applicable outcome exists).

## 6. Tests -- exact commands and results

Shared venv: `MPANGO ERP/windsurf mpango erp/.venv` (Python 3.14, pytest 9). `PYTHONPATH=.`
from `backend/`. Integration tests refuse `mpango_erp` and self-skip without an explicit
ephemeral DB; run against a throwaway `postgres:15` container (`p17dc-dbg`, DB `p17dc_eph`),
never the developer DB. The migration test's `_bootstrap_ephemeral` applies the pgcrypto /
`alembic_version` width / `t_dev` prereqs itself.

```
# Unit (no DB):
PYTHONPATH=. PYTHONIOENCODING=utf-8 python -m pytest \
  tests/test_platform_p17dc_backup_models.py \
  tests/test_platform_p17dc_backup_registry_read.py -q
# -> 40 passed (14 model + 26 registry-read)

PYTHONPATH=. PYTHONIOENCODING=utf-8 python -m pytest tests/test_platform_p17_registry.py -q
# -> 40 passed (existing P17, no regression from the wiring)

# Integration (ephemeral postgres:15; DATABASE_URL in the postgresql:// scheme pointing at the
# throwaway p17dc_eph DB on localhost, throwaway password; alembic env.py converts to +asyncpg):
DATABASE_URL=<postgresql URL to the ephemeral p17dc_eph DB> \
REPORTING_USER_PASSWORD=ephemeral_reporting_pw PYTHONPATH=. PYTHONIOENCODING=utf-8 python \
  -m pytest tests/test_platform_p17dc_backup_migration.py \
            tests/test_platform_p21_durable_approval_migration.py -q
# -> 15 passed (9 P17-D-C + 6 P21 pinned)

# Full platform suite (unit + integration, same ephemeral DB):
... python -m pytest tests/test_platform_p10_contracts.py tests/test_platform_p17_registry.py \
  tests/test_platform_p17dc_backup_models.py tests/test_platform_p17dc_backup_registry_read.py \
  tests/test_platform_p17dc_backup_migration.py tests/test_platform_p18_controlled_actions.py \
  tests/test_platform_p18d_real_registry.py tests/test_platform_p21_durable_approval_models.py \
  tests/test_platform_p21_durable_approval_migration.py \
  tests/test_platform_p21_durable_approval_adapter_skeleton.py \
  tests/test_platform_p21_durable_approval_schema.py \
  tests/test_platform_p21_durable_approval_adapter_implementation.py \
  tests/test_platform_p22_controlled_execution.py \
  tests/test_platform_p22e1_runtime_governed_adapter_seam.py -q
# -> 493 passed
```

Result: **493 platform tests pass** (P10 / P17 / P17-D-C / P18 / P21 / P22), incl. all integration
migration tests on the ephemeral DB. No regressions.

## 7. GitNexus

`npx gitnexus analyze` (this worktree, never indexed before), then `status`, the `impact` CLI, and
`detect_changes` (MCP, driven over stdio JSON-RPC; repo name required because many repos are
indexed globally; `shell=True` + utf-8/errors=replace on Windows).

- **analyze:** ~8,580 nodes | 26,204 edges | ~552 clusters | 300 flows (counts reported as a BAND
  -- node/cluster counts wobble +/-2-3 across fresh rebuilds; edges/flows are stable).
- **status:** up-to-date; indexed commit `a548f6f` == current commit `a548f6f`.
- **detect_changes** (scope `compare`, base_ref `origin/platform-dev`): `changed_count=134`
  symbols across the 8 changed files; `affected_count=4` processes; **risk_level=MEDIUM**. The 4
  affected processes are all PLATFORM durable-approval / registry flows
  (`Create_durable_approval` -> `_utcnow` / `_load_provisioning_map` / `_to_uuid` /
  `_BackupSourceRead`); **0 product business flows** (no orders / payments / invoices / customers /
  inventory / ledger).
- **impact** (`_build_registry`, upstream dependants): P17 routes -> P18 `evaluate_request` ->
  P19/P20 approval services; **0 product** business flow.

Runtime risk is MEDIUM (the P17 read wiring is consumed by P18 `evaluate_request` for the
`backup.check` source resolution), but it is fail-safe: with no writer recording outcomes yet the
source reads empty, so `backup_status` stays null + reason and P18 continues to resolve
`backup.check` to `unavailable` -- unchanged behavior. Affected flows stay platform P17 / P18
registry / source-status only.

## 8. Validation gates

- Targeted P17-D-C tests pass: 14 model + 26 registry-read + 9 migration = 49. PASS.
- Existing P17 tests pass: 40. PASS.
- Relevant P18 / P22 source-status tests pass: included in the 493-pass platform suite. PASS.
- Migration tests on clean ephemeral DB: 15 (9 P17-D-C + 6 P21 pinned). PASS.
- `git diff --check origin/platform-dev..HEAD`: clean (no whitespace / merge markers).
- Non-ASCII scan on the 8 changed files: **0 non-ASCII bytes** (ASCII-only).
- `detect-secrets-hook --baseline <configured baseline>` on the 8 changed files: exit 0 (no new
  secrets). The ledger uses short SHAs and the phrase "configured baseline" to avoid the
  KeywordDetector / 40-char-SHA false positives.
- Forbidden-path audit (programmatic, tracked + untracked): **0 violations**. No P22
  (`seam.py` / `adapters.py` / `routes.py` / `services.py` / tests), no frontend, no P16, no
  product / payment / auth / RBAC, no package / lockfile, no `.github`, no `.claude`, no secrets
  baseline file changed.
- GitNexus analyze + status + detect_changes + impact: above. PASS (platform-only blast radius).

## 9. Explicit statements

- **No P22 wiring.** `backend/api/v1/platform/p22/seam.py`, `adapters.py`, `routes.py`,
  `services.py`, and the P22 tests are unchanged (cited read-only); `backup.check` remains
  `source_unknown` / `not_implemented` (locked by
  `test_p22_backup_check_still_not_implemented`).
- **No backup.check execution.** P17-D-C reads status only; it does not trigger, run, or probe
  `backup.check`.
- **No real backup / restore / pg_dump.** No backup or restore is performed and no script that
  performs one is added or changed; the writer / restore-test runner are separate operational tasks
  not in P17-D-C scope.
- **No frontend.** No frontend file is touched.
- **No P16 change.** No `scripts/platform_worktree_executor.py` or P16 asset is touched.
- **No product business mutation.** No orders / payments / invoices / customers / inventory /
  ledger path is touched; `tenant_id` is a scoped identifier, never a FK into business tables; the
  read path is read-only.
- **No auth / RBAC / session rewrite.** The identity-only `super_admin` guard is unchanged.
- **P22-E3 not started.** P22-E3 may bind `backup.check` to this PROVEN, MERGED, TESTED source
  behind the seam only after CTO acceptance; it is not started here.

## 10. Risk / Blockers / Follow-ons

- **Risk:** MEDIUM (GitNexus). Platform P17/P18 only; fail-safe under an empty source. No product
  impact.
- **Blockers:** none for this branch. Upstream sequencing note: P17-D-B (plan doc) is pushed but
  not merged to `platform-dev`; this code branch implements that plan from `eb5268c` per the task
  instruction (section 2). The two P21 test edits are necessary regression-prevention, documented
  in section 4.
- **Follow-ons (NOT in this branch):** (a) a writer/recorder that records `backup_job` outcome
  rows after `backup_postgres.sh` runs (operational task); (b) a restore-test runner that records
  `restore_test_job` rows; (c) P22-E3 read-only `backup.check` summary probe, behind the seam,
  only after CTO acceptance of this source.
