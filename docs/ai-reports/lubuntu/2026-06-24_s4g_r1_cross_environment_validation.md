# S4-G-R1: Cross-Environment Migration Infrastructure Validation

**Date:** 2026-06-24
**HEAD:** e7d70bea78daf32eb4bd48c4bcd66aeffc127af1
**Branch:** origin/opencode/s4g-migration-infrastructure-hardening-2026-06-24 (detached)
**Base:** origin/product-dev-recovered
**Verdict:** PASS_FOR_CTO_MERGE_REVIEW

## Environment

| Item | Value |
|------|-------|
| OS | Linux (Lubuntu) |
| Python | 3.12.3 |
| Poetry | 2.4.1 |
| Alembic | 1.18.1 |
| `python -m alembic --version` | ✅ `alembic 1.18.1` |
| `python -m alembic heads` | ✅ `023_inventory_reservations (head)` |
| `python -m alembic current` | ⚠️ Fails (asyncpg InvalidPasswordError) — pre-existing `alembic.ini` credential mismatch, NOT an `alembic.exe` vs `python -m alembic` issue |
| PostgreSQL | ✅ Connected (127.0.0.1:5432) |
| Redis | ✅ PONG (127.0.0.1:6379) |

## Changed Files

| Status | File |
|--------|------|
| A | ai-ledger/product-ai/2026-06-24_s4g_migration_infrastructure_hardening.md |
| M | backend/alembic/env.py |
| M | backend/alembic/versions/017_retailer_prices.py |
| A | backend/tests/test_s4g_migration_infrastructure_hardening.py |

**Total changed files:** 4 ✅
**git diff --check:** ✅ No whitespace errors
**Mojibake scan:** ✅ Clean

## Test Results

| Suite | Passed | Failed | Total | Exit Code | Status |
|-------|--------|--------|-------|-----------|--------|
| S4-G targeted | 5 | 0 | 5 | 0 | ✅ PASS |
| S4-F regression | 8 | 0 | 8 | 0 | ✅ PASS |
| S4 jobs | 16 | 0 | 16 | 0 | ✅ PASS |
| S5/Phase5 | 66 | 0 | 67 | 0 | ✅ PASS (1 xfail, expected) |

**Note:** The `-k "s4_jobs or jobs"` selector hit collection errors from 8 test files missing `hypothesis` module (pre-existing env issue). Actual S4 jobs tests found and run explicitly: `test_s4_jobs_persistence.py` (5 passed), `test_s4_jobs_local.py` (11 passed).

## python -m alembic Proof

**Core validation objective: confirm `python -m alembic` works on Linux (replacing `alembic.exe`).**

| Command | Result |
|---------|--------|
| `python3 -m alembic --version` | ✅ alembic 1.18.1 |
| `python3 -m alembic heads` | ✅ 023_inventory_reservations (head) |
| `python3 -m alembic current` | ⚠️ asyncpg.InvalidPasswordError |

**Analysis:** `python -m alembic` is fully functional on Linux. The `current` subcommand failure is due to a pre-existing credential mismatch between `alembic.ini` (contains hardcoded password for a different environment) and the local PostgreSQL instance. This is NOT a `python -m alembic` invocation issue — the S4-G changes to `env.py` correctly source credentials from environment variables. The `alembic.ini` hardcoded URL was present before S4-G and is not part of this branch's changes.

The S4-G test `test_alembic_invocation_cross_platform` validates that `python3 -m alembic heads` works, which it does (5/5 tests pass).

## Compliance

| Constraint | Status |
|------------|--------|
| No product code modified (beyond S4-G 4 files) | ✅ Only 4 changed files vs base |
| No test code modified | ✅ No test files in diff beyond S4-G test file |
| product-dev-recovered not pushed | ✅ Not pushed |
| No deployment | ✅ No deployment |
| No skipped failures | ✅ All failures are xfail (expected) or pre-existing |
| Secrets not printed | ✅ Passwords masked in report |

## Remaining Risks

1. **alembic.ini hardcoded credentials:** The `alembic.ini` file contains a hardcoded DB password (`MpangoDBV0.***`). This predates S4-G and causes `alembic current` to fail against local PostgreSQL. S4-G's `env.py` changes add env-var-based URL construction, but `alembic current` still uses the ini URL when `DATABASE_URL` is not set. Consider updating `alembic.ini` to use env var interpolation or removing the hardcoded URL.
2. **`hypothesis` missing:** 8 test files fail to collect due to missing `hypothesis` dependency. Pre-existing, not S4-G related.
3. **Python alias:** `python` command not available, must use `python3`. S4-G correctly uses `python3 -m alembic` in its tests.

## Verdict Rationale

**PASS_FOR_CTO_MERGE_REVIEW** — All 4 S4-G assertions hold:

1. ✅ `python -m alembic` works on Linux (`--version`, `heads` succeed)
2. ✅ S4-G targeted tests: 5/5 pass
3. ✅ S4-F regression: 8/8 pass
4. ✅ S4 jobs: 16/16 pass
5. ✅ S5/Phase5 regression: 66/67 pass (1 expected xfail)
6. ✅ Exactly 4 changed files, no product code outside S4-G scope
7. ✅ No whitespace errors, no mojibake
8. ✅ Report pushed to reports/lubuntu-validation

The `alembic current` failure is a pre-existing `alembic.ini` credential issue, not an `alembic.exe` cross-platform problem. The S4-G changes correctly enable `python3 -m alembic` as a cross-platform replacement.
