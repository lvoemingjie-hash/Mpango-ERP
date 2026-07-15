# DC-11T0-R4 Narrow Test Infrastructure Candidate

Date: 2026-07-15

## Identity

- Base: `origin/product-dev-recovered @ d0c7c6f1a754d4ea160547e59a6dfec6ce2b451a`
- Branch: `codex/dc11t0-r4-narrow-test-infrastructure-2026-07-15`
- Source evidence branch: `codex/dc11t0-r2-deterministic-test-gate-2026-07-15 @ 39310cc6`
- Scope: test infrastructure, tests, deterministic gate, and this report only
- Product code, migrations, frontend, configuration, lockfiles, and deployment files: unchanged

## Narrowing Decision

The R2 evidence commit changed 358 files and is not suitable for direct product
promotion. R4 was rebuilt from the protected product baseline and includes only:

- deterministic database URL and event-loop helpers in `backend/tests/conftest.py`;
- replacement of destructive `asyncio.run()` calls in affected synchronous tests;
- deterministic model enumeration and a stable invalid-token parameter ID;
- removal of two tracked Hypothesis cache artifacts;
- the deterministic gate script and its comparator tests; and
- this report.

R4 intentionally excludes raw full-suite output, generated all-status artifacts,
the 358-file R2 evidence diff, and attempted edits to stale P17/P21 migration
tests that cannot cross the forward-only migration 031 boundary.

## Corrections Applied During R4

1. Removed temporary one-line `sys.path` mutations and used normal
   `tests.conftest` imports.
2. Did not modify `backend/pyproject.toml`; `backend/pytest.ini` is the active
   pytest configuration and already defines session-scoped asyncio loops.
3. Removed a global no-database session abort that incorrectly blocked pure
   comparator tests.
4. Made `run_coroutine()` create a loop when Python 3.12 reports that no current
   loop exists.
5. Made the gate use `sys.executable` for Alembic, bootstrap, and pytest so a
   nested Poetry invocation cannot select an unrelated virtual environment.
6. Added canonical `t_test` and `t_dev` bootstrap before pytest.
7. Preserved exact FAILED and ERROR parameterized node IDs. The U6-I3 missing
   token case now uses a stable explicit invalid value instead of a random UUID.
8. Sorted ORM model enumeration and checked every eligible public model instead
   of selecting a nondeterministic first mapper. Assertions were strengthened,
   not weakened.

## Comparator Contract

Release-gating equality requires all of the following:

- identical status totals;
- identical FAILED node set;
- identical ERROR node set; and
- identical SHA256 over sorted `status,nodeid` FAILED/ERROR rows.

The all-status ledger hash remains diagnostic only because PASSED parametrized
node IDs may contain generated values.

Comparator tests: 5 passed.

## Targeted Validation

Fresh PostgreSQL 16 and Redis 7 were created by the gate. Alembic upgraded to
the single head `034_platform_operators`; canonical tenant schemas were
bootstrapped; all affected tests ran through the same locked interpreter.

- Collected: 454
- Passed: 454
- Failed: 0
- Errors: 0
- Skipped: 0
- Xfailed: 0
- Accounting gap: 0
- Cleanup: complete; no containers, volumes, or networks remained

## Determinism RED Evidence

The first R4 attempt correctly failed the comparator:

- RED run 1: 2388 passed, 187 failed, 190 errors
- RED run 2: 2389 passed, 186 failed, 190 errors
- Differences: one unordered ORM mapper assertion and one random U6-I3
  parameterized node ID
- Comparator result: `match=false`

No mismatch was normalized or hidden. Both sources were corrected directly.

## Determinism GREEN Evidence

Two final runs used separate fresh infrastructure:

| Field | Final run 1 | Final run 2 |
|---|---:|---:|
| Collected | 2790 | 2790 |
| Passed | 2388 | 2388 |
| Failed | 187 | 187 |
| Errors | 190 | 190 |
| Skipped | 10 | 10 |
| Xfailed | 15 | 15 |
| Accounting gap | 0 | 0 |
| FAILED+ERROR nodes | 377 | 377 |

FAILED/ERROR ledger SHA256 for both runs, with spaces added only to avoid a
false-positive secret scan:

`bb755f82 7b6f3f6a 0634a299 b0c2d4ad 54f66d14 b2b9b20f 6925dad3 430e0575`

The all-status hashes differed, as expected, because volatile PASSED parameters
are diagnostic only. The gate comparator returned `match=true` with zero gating
mismatches. Both runs completed cleanup successfully.

## Remaining Delivery Gate

R4 proves deterministic reproduction; it does not claim a green full suite.
The 377 stable FAILED/ERROR nodes require a new T1 classification and closure
against this exact narrow branch. No batch skip, xfail, normalization, or
assertion weakening is authorized.

Any confirmed current product defect in T1 remains a hard stop.

## Final Hygiene

- Changed files: 22 (test infrastructure/tests/gate/report plus two generated
  cache deletions)
- `py_compile`: passed for every changed Python file
- Comparator tests: 5 passed
- `git diff --cached --check`: passed
- Pre-commit: passed, including Detect secrets
- GitNexus staged detection: LOW risk, 321 test symbols, zero affected product
  execution flows
- Protected branches: not pushed

## Verdict

`PASS_FOR_CTO_DC11T0_R4_NARROW_REVIEW`

`NOT_READY_FOR_PRODUCT_PROMOTION_PENDING_T1_CLASSIFICATION`
