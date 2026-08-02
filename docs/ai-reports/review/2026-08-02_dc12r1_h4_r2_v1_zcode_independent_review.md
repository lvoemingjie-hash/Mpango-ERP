# DC-12R1-H4-R2-V1 Independent Final Merge Review

**Reviewer**: Local ZCode (independent adversarial source / test-contract / evidence-integrity review)
**Review date**: 2026-08-02
**Report branch**: `reports/dc12r1-h4-r2-v1-zcode-independent-review-2026-08-02`
**Mode**: Independent adversarial source, test-contract and evidence-integrity review. No modification of the target branch.

---

## 1. Verdict

```
PASS_FOR_CTO_DC12R1_H4_R2_V1_FINAL_MERGE_REVIEW
```

The H4 event-loop repair (commit `f031e033`) and the H4-R2 migration-contract
reconciliation (commit `a4176a55`), together with the report-only evidence
reconciliation (commit `90bd3b4b`), are **safe to merge together**. No stop
condition was triggered. The independent review confirms the branch's own
authoritative verdict `PASS_FOR_CTO_DC12R1_H4_R2_R1_MERGE_REVIEW`.

The single runtime gate that could not be re-executed by this reviewer (live
H4 regression + corrected exact-036 node) is **truthfully blocked**, not
substituted: no disposable PostgreSQL 16 / Redis 7 stack with a configured
`TEST_DATABASE_URL` is available in the local ZCode environment, and the
changed tests hard-require a live database. The authoritative Lubuntu
exact-suite evidence (two identical 3116/0/0 runs) is preserved verbatim and
is not replaced by any split or partial run.

---

## 2. Scope & lineage verification

| Item | Expected | Observed | Result |
|---|---|---|---|
| Target branch | `origin/codex/dc12r1-h4-r2-exact-036-contract-reconciliation-2026-08-02` | resolves | PASS |
| Target SHA | `90bd3b4beaed7e5a44196c56307c5507563de07c` | `90bd3b4b...` | PASS |
| Protected baseline | `origin/product-dev-recovered` | `9528cb6d...` | PASS |
| Baseline SHA | `9528cb6de5f668ed09feb7a1eaa9aafaa537987d` | `9528cb6d...` | PASS |
| Baseline is ancestor of target | yes | `git merge-base --is-ancestor` true | PASS |
| Commits ahead of baseline | 3 | `rev-list --count` = 3 | PASS |
| Required chain | `9528cb6d -> f031e033 -> a4176a55 -> 90bd3b4b` | parent links match exactly, linear | PASS |

Per-commit purpose mapping (verified against diff scope):

- `f031e033` — `fix(dc12r1-h4-r1)`: replace asyncio.run with run_coroutine. Touches 1 test file + 1 new test file + 1 ledger.
- `a4176a55` — `fix(dc12r1-h4-r2)`: reconcile stale 036-head contract for 037. Touches 1 test file + 1 ledger.
- `90bd3b4b` — `docs(dc12r1-h4-r2-r1)`: report-only evidence reconciliation. Touches only the R2 ledger markdown.

---

## 3. Changed files (baseline `9528cb6` -> target `90bd3b4`)

```
A  ai-ledger/product-ai/2026-08-02_dc12r1_h4_event_loop_pool_isolation.md
A  ai-ledger/product-ai/2026-08-02_dc12r1_h4_r2_exact_036_migration_contract_reconciliation.md
A  backend/tests/test_dc12r1_h4_event_loop_pool_isolation.py
M  backend/tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py
M  backend/tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py
```

**Exactly 5 files.** All changes are confined to `backend/tests/` and
`ai-ledger/product-ai/`. There are **zero** changes to:

- product/application code
- Alembic migrations (`backend/alembic/` byte-identical baseline->target)
- `alembic.ini`
- configuration files
- dependencies / lockfiles (`pyproject.toml`, `requirements*.txt`, `package.json`, `pnpm-lock.yaml`, etc.)
- frontend code

`git diff --stat 9528cb6 90bd3b4 -- backend/alembic backend/alembic.ini` is empty.

---

## 4. Mandatory source review

### 4.1 H4-R1 event-loop repair (`f031e033`)

**Objective 2 — all four proven `asyncio.run` bootstrap calls replaced.**
The diff removes exactly 4 `asyncio.run(_bootstrap_and_revert_to_036(...))`
calls and adds exactly 4 `run_coroutine(_bootstrap_and_revert_to_036(...))`
calls at the proven sites:

| # | Site | Method / function |
|---|---|---|
| 1 | `_setup_tenant` | `TestRealAlembicUpgradeFailClosed` |
| 2 | `_full_proof` | `TestExactCatalogShapeBypass` |
| 3 | `test_cross_tenant_failure_neither_mutates` | `TestTwoRegisteredTenantsUpgrade` (schema_a) |
| 4 | `test_cross_tenant_failure_neither_mutates` | `TestTwoRegisteredTenantsUpgrade` (schema_b) |

The four local `import asyncio` statements were also removed. Confirmed by
grep: **no `asyncio.run` and no `import asyncio` remain** in the r4_r1 file at
the target SHA.

**Objective 3 — `run_coroutine` itself unchanged.**
`git diff 9528cb6 90bd3b4 -- backend/tests/async_test_utils.py` is empty
(byte-identical). `run_coroutine` is a pre-existing helper introduced in
commit `4c4a684c` (`fix(DC-11T2): restore fail-closed test gates`), well before
the protected baseline. The H4-R1 fix reuses an established, approved helper.

**Objective 4 — no remaining equivalent `asyncio.run` in the affected R4-R1 path.**
`grep asyncio.run` on `90bd3b4:r4_r1_real_alembic_upgrade.py` returns nothing.
The repair is complete; no contamination path remains in the affected file.

The helper is correct: `run_coroutine` calls `_current_or_new_loop()`, which
reuses the policy's current loop (or creates and registers a persistent one),
then `loop.run_until_complete(awaitable)` — it never creates-and-closes a
throwaway loop as `asyncio.run()` does, which was the root cause of the
asyncpg pool contamination (orphaned `Future`s bound to a closed loop).

### 4.2 H4 regression tests (`test_dc12r1_h4_event_loop_pool_isolation.py`, new)

**Objective 5 — genuine exercise of all four required properties.**
7 tests across 3 classes, all with real (non-tautological) assertions:

| Required property | Test | Assertion |
|---|---|---|
| Loop identity | `test_loop_identity_unchanged` | `assert loop_before is loop_after` |
| Loop-open state | `test_loop_still_open` | `assert not loop.is_closed()` |
| Following `async_session` use | `test_select_one_via_global_engine`, `test_select_one_after_engine_dispose`, `test_no_interface_error_on_rollback` | use `AsyncSessionLocal()` (global session factory); assert `== 1`; exercise rollback after dispose |
| Leaked-connection cleanup | `test_no_idle_mpango_connections_after_local_dispose` | `assert leaked == 0` via `pg_stat_activity` count of idle `Mpango ERP` connections |

The `warnings.catch_warnings()`/`simplefilter("ignore", DeprecationWarning)`
block in `_get_current_loop()` only silences the asyncio `get_event_loop`
deprecation noise — it does **not** swallow exceptions or test failures, and
mirrors the exact pattern in the approved baseline helper
`_current_or_new_loop()`.

### 4.3 H4-R2 migration-contract reconciliation (`a4176a55`)

**Objective 6 — exactly three Alembic targets changed from `"head"` to `REV_036`.**
Diff of `test_dc12r1_s1_r5_migration_preflight_exact_catalog.py`:

- 3 removed: `run_alembic_upgrade(config, "head")`
- 3 added:   `run_alembic_upgrade(config, REV_036)`

at the first-failure (inside `pytest.raises`), repaired-upgrade, and
second-upgrade-no-op phases of
`test_actual_alembic_035_to_036_failure_rolls_back_then_repaired_upgrade_noops`.

**Objective 7 — exactly two stale 036-head assertions removed.**
Diff removes exactly 2 `assert _script_heads(config) == [REV_036]` lines (which
were factually wrong after migration 037 became the sole head). **No other
assertions were removed, added, or changed** in the modified files (verified:
`grep '^+.*assert'` on the modified-file diff returns nothing).

**Objective 8 — preserved assertions intact.**
All required assertions remain in the target test function (7 asserts total):

- `assert _current_revision(connection) == REV_035` (before and after first failure)
- `assert exc.value.__class__.__name__ == "PreflightFailure"` (fail-closed)
- `assert after_failure_payload == before_payload` (rollback fingerprint; `R5_ROLLBACK_FINGERPRINT` print preserved)
- `assert _current_revision(connection) == REV_036` (repaired upgrade reaches 036)
- `assert _current_revision(connection) == REV_036` (second upgrade still 036)
- `assert after_noop_payload == before_noop_payload` (second-upgrade no-op fingerprint; `R5_NOOP_FINGERPRINT` print preserved)

**Objective 9 — migration 037 legitimate head and unchanged.**
`backend/alembic/versions/037_payment_declarations_schema.py`:
`revision = "037_payment_declarations_schema"`, `down_revision = "036_retailer_mvp_identity"`,
`branch_labels = None`, `depends_on = None`. Clean linear chain
`034 -> 035 -> 036 -> 037` (single head, no branches). File byte-identical
baseline->target.

**Objective 10 — no skip / xfail / deselect / timeout increase / exception swallowing / assertion weakening.**
Per-pattern scan of all added lines (159 added lines across the three commits)
returns 0 for `skip`, `xfail`, `deselect`, `pytest.mark.skip/xfail`, `except`,
`time.sleep`, `timeout`, `pytest.warns`, `soft_assert`. The single `pass`
hit is a false positive (the word "pass" inside a diff hunk header
`@@ -1046,13 +1045,12 @@`, not a `pass` statement).

---

## 5. Evidence-integrity review

| # | Requirement | Result |
|---|---|---|
| 1 | Two exact runs `3116 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors` | PASS — both runs show identical numbers |
| 2 | Run A and Run B totals identical | PASS — comparison table marks YES for Passed/Failed/Errors/Skipped/Xfailed |
| 3 | Lubuntu GitNexus unavailability explicitly disclosed | PASS — marked `UNAVAILABLE`; "MCP server does not respond (timed out on startup). No substitution attempted." |
| 4 | CTO GitNexus evidence attributed to CTO env + anchored to `a4176a5` | PASS — "CTO review environment", "source SHA `a4176a5`", "not executed by Lubuntu" |
| 5 | Report-only commit `90bd3b4` does not claim new runtime | PASS — touches only the R2 ledger md; explicit "No Full-Suite Rerun Required" section |
| 6 | Old H4-R2 verdict marked corrected/superseded | PASS — "Original H4-R2 Verdict (Corrected/Superseded by R2-R1)"; "was inaccurate" acknowledged |
| 7 | Authoritative verdict `PASS_FOR_CTO_DC12R1_H4_R2_R1_MERGE_REVIEW` | PASS — present as final verdict |

**No evidence misattribution.** The runtime evidence (Run #1/#2, 3116 passed)
is correctly anchored to source SHA `a4176a5` and explicitly states it was
"executed by Lubuntu against `a4176a5`". Commit `90bd3b4` modifies only the
ledger markdown and makes no new runtime-execution claim. The CTO GitNexus
evidence is clearly attributed to the CTO environment. The final ledger is
internally truthful.

The H4-R1 ledger is correspondingly honest: it reported `STOP_AND_REPORT_CTO`
with the single pre-existing RED node (the same s1_r5 test) clearly identified
and root-caused, which H4-R2 then resolved.

---

## 6. Independent gates

| # | Gate | Result | Detail |
|---|---|---|---|
| 1 | `py_compile` changed Python test files | **PASS** | 3/3 files compile (Python 3.12.10) |
| 2 | `git diff --check` | **PASS** | exit 0 baseline->target and per-commit |
| 3 | Scoped `pre-commit` | **PASS** | trailing-whitespace, end-of-files, large-files, detect-secrets all Passed; check-yaml skipped (no yaml in scope) |
| 4 | Scoped `detect-secrets` | **PASS** | 0 findings per file; 0 findings in the 159 added diff lines |
| 5 | GitNexus `analyze`/`status` at target SHA | **PASS** | 14,269 nodes / 44,213 edges / 922 clusters / 300 flows; indexed `90bd3b4`, up-to-date |
| 6 | GitNexus `detect_changes` vs `9528cb6` and vs `f031e033` | **PASS** | vs baseline: 5 files (all test+ledger, 0 product); vs f031e033: 2 files (s1_r5 test + ledger) — matches CTO ledger |
| 7 | GitNexus `impact` on modified test functions | **PASS** | all modified functions (`test_actual_alembic_...`, `_setup_tenant`, `_full_proof`, `test_cross_tenant_failure_neither_mutates`) -> LOW risk, 0 callers, 0 affected |
| 8 | Run H4 regression + corrected exact-036 node in disposable PG16/Redis7 | **BLOCKED (truthful)** | no local PostgreSQL/Redis, no `TEST_DATABASE_URL`; tests hard-require live DB via `_require_test_env()`; **not substituted** for Lubuntu evidence |
| 9 | No split full-suite substitution | **PASS** | authoritative Lubuntu exact-suite (3116/0/0 x2) retained; no partial run claimed |

GitNexus figures match the CTO ledger exactly (14,269 nodes / 44,213 edges /
922 clusters / 300 flows; LOW risk, 0 affected), independently corroborating
the CTO-side evidence.

---

## 7. Stop-condition evaluation

| Stop condition | Triggered? |
|---|---|
| Any product/migration/config/dependency drift | No |
| Any remaining event-loop contamination path in the affected test | No |
| Any weakened fail-closed or fingerprint assertion | No |
| Any report/evidence attribution contradiction | No |
| Any failed/error node caused by the target branch | No |
| Any SHA, ancestry or changed-file mismatch | No |

**No stop condition triggered.**

---

## 8. Required-verity reconciliation

This independent review required the verdict
`PASS_FOR_CTO_DC12R1_H4_R2_V1_FINAL_MERGE_REVIEW`. All mandatory source,
test-contract, evidence-integrity, and independent-gate checks pass (with the
single runtime re-execution gate truthfully blocked and not substituted). The
branch's own authoritative verdict
`PASS_FOR_CTO_DC12R1_H4_R2_R1_MERGE_REVIEW` is corroborated.

---

## 9. Reviewer notes & integrity

- The target source branch was **not modified**. All checks were performed
  against `origin/codex/dc12r1-h4-r2-exact-036-contract-reconciliation-2026-08-02`
  at SHA `90bd3b4` via read-only git inspection and a detached temporary
  worktree that has since been removed.
- GitNexus was indexed against the target SHA in an isolated worktree
  (`zcode_review_worktree`); the worktree and its registry entry were removed
  after analysis. The main repository's `.gitnexus` index was not touched.
- No merge, deploy, I2B initiation, or protected-ref push was performed.
- This report and its findings CSV are the only artifacts added, on an
  isolated `reports/` branch based on the protected baseline `9528cb6`.
