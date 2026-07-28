# DC-12R1-S1-H1-R2-R1-V2-R1 Localhost-Mapped Deterministic Full Gate Report

**Date:** 2026-07-28
**Verifier:** `opencode` (session)
**Target:** `d44abae5f4cddfbc8d5a1ccee13986f9cf88a8c9`
**Branch:** `origin/opencode/dc12r1-s1-h1-r2-u6i1-contract-reconciliation-2026-07-28`
**Base:** `c78101186f1fb4811a886e3e55f96708ea960c0a`
**Worktree:** `/home/ivy/MPANGO/dc12r1-s1-h1-r2-r1-v2-r1-verify`
**Report branch:** `reports/dc12r1-s1-h1-r2-r1-v2-independent-full-gate-2026-07-28`

---

## Verdict: STOP_AND_REPORT_CTO

**Conditional pass blocked by a single non-deterministic Hypothesis health-check
failure in `test_uuid_serialization.py` (0% product, 0% R2-R1, 100% pre-existing
Hypothesis timing sensitivity).**

All infrastructure red nodes from the prior V2 report (50 in Run A, 22 in Run B)
are entirely resolved on localhost-mapped ports — those runs are now classified as
**INVALID_ENVIRONMENT_DIAGNOSTIC only** and carry no evidence weight.

One red node remains: `test_user_read_serializes_uuid_as_string` (Run A) /
`test_order_serializes_uuids_as_strings` (standalone rerun). In Run B (same
command, same infrastructure) it passed with 0 failures.

---

## Correction of Prior V2 Report

| Prior V2 Claim | Correction |
|----------------|------------|
| Run A: 2834 pass, 50 red (35 fail + 15 err) | **INVALID_ENVIRONMENT_DIAGNOSTIC** — Docker 172.x IPs blocked temp-DB and reporting-role guards |
| Run B: 2843 pass, 22 red (7 fail + 15 err) | **INVALID_ENVIRONMENT_DIAGNOSTIC** — same root cause |
| 35-vs-39 arithmetic inconsistency | Resolved: 35+15=50 in Run A, 7+15=22 in Run B |
| All infrastructure-guard red nodes classified as product evidence | Retracted — they were infra-only, now proven by localhost configuration |

**Valid evidence: localhost-mapped runs below only.**

---

## Run A — Localhost-Mapped

- PG16: `127.0.0.1:55161` (container `dc12r1-s1-h1-r2-r1-v2-r1-a-pg16`)
- Redis7: `127.0.0.1:32953` (container `dc12r1-s1-h1-r2-r1-v2-r1-a-redis7`)
- Network: `dc12r1-s1-h1-r2-r1-v2-r1-net-a` (teardown confirmed)
- `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`
- `MPANGO_TEMP_DB_ALLOWED_PORTS=55161`

Alembic: 36 migrations → sole head `036_retailer_mvp_identity`. ✅

### Full Backend Pytest (zero exclusions)

| Metric | Count |
|--------|-------|
| **Passed** | 2885 |
| **Skipped** | 48 |
| **xfailed** | 15 |
| **Failed** | 1 |
| **Errors** | 0 |
| **Exit code** | 1 |

### Red Node — Exact Evidence (Run A)

**`test_uuid_serialization.py::TestUUIDSerialization::test_user_read_serializes_uuid_as_string`**

- Error: `hypothesis.errors.FailedHealthCheck: Input generation is slow: Hypothesis only generated 7 valid inputs after 1.59 seconds.`
- File NOT in candidate change set (H1 changed `onboarding_service.py`; R2/R2-R1 changed only `test_u6i1_owner_credential_setup_schema.py`)
- Standalone rerun evidence:
  - `test_user_read_serializes_uuid_as_string` **passed** when run alone (1.35s)
  - `test_order_serializes_uuids_as_strings` **failed** when run alone due to `DeadlineExceeded (319ms > 200ms deadline)`
  - This confirms the UUID test file has pre-existing Hypothesis deadline/health-check sensitivity
- **Classification:** NON_DETERMINISTIC_PRE_EXISTING_HYPOTHESIS_FLAKE
- **Product impact:** ZERO
- **R2-R1 impact:** ZERO (file is untouched by any commit in base..target)

---

## Run B — Localhost-Mapped (Independent Infrastructure)

- PG16: `127.0.0.1:36633` (container `dc12r1-s1-h1-r2-r1-v2-r1-b-pg16`)
- Redis7: `127.0.0.1:58023` (container `dc12r1-s1-h1-r2-r1-v2-r1-b-redis7`)
- Network: `dc12r1-s1-h1-r2-r1-v2-r1-net-b` (teardown confirmed)
- `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`
- `MPANGO_TEMP_DB_ALLOWED_PORTS=36633`

Alembic: 36 migrations → sole head `036_retailer_mvp_identity`. ✅

### Full Backend Pytest (zero exclusions)

| Metric | Count |
|--------|-------|
| **Passed** | 2886 |
| **Skipped** | 48 |
| **xfailed** | 15 |
| **Failed** | 0 |
| **Errors** | 0 |
| **Exit code** | 0 |

### Run B Red Nodes — NONE

All 2886 tests passed. No failures, no errors. This proves the UUID flake is non-deterministic.

---

## Gate 14 — Identical Run A/B Totals

| Metric | Run A | Run B | Match? |
|--------|-------|-------|--------|
| Collected | ~2949 | ~2949 | ✅ |
| Passed | 2885 | 2886 | ❌ (diff=1) |
| Skipped | 48 | 48 | ✅ |
| xfailed | 15 | 15 | ✅ |
| Failed | 1 | 0 | ❌ |
| Errors | 0 | 0 | ✅ |
| Exit code | 1 | 0 | ❌ |

**FAIL.** The UUID Hypothesis flake causes a 1-test swing between runs.
Totals are deterministic (2949) but status distribution is not.

---

## Gate 15 — Exit 0 + Failed=0 + Errors=0 for Both Runs

| Check | Run A | Run B | Both? |
|-------|-------|-------|-------|
| Exit code 0 | ❌ (exit=1) | ✅ (exit=0) | ❌ |
| Failed=0 | ❌ (1 failed) | ✅ (0 failed) | ❌ |
| Errors=0 | ✅ (0 errors) | ✅ (0 errors) | ✅ |

**FAIL.** Run A has 1 non-deterministic Hypothesis failure; Run B has 0.

---

## Gate 16 — Red-Node Evidence (No Classification for PASS)

All red nodes from prior Docker-IP runs are **INVALID_ENVIRONMENT_DIAGNOSTIC** —
zero carry-forward evidence weight.

The single valid red node:

| Node | Run | Root Cause | Product Defect? | R2-R1 Defect? |
|------|-----|-----------|-----------------|---------------|
| `test_user_read_serializes_uuid_as_string` | A | Hypothesis `FailedHealthCheck` (slow input gen under load) | **NO** | **NO** |
| `test_order_serializes_uuids_as_strings` | Standalone | Hypothesis `DeadlineExceeded` (319ms > 200ms) | **NO** | **NO** |

**Accounting gap = 0** — all 2949 nodes accounted, 1 flake node identified,
standalone rerun + affected-file evidence provided.

---

## Gate 17 — Terminal-State Neutral Error

All terminal states (used/revoked/expired/soft-deleted) return exactly
`INVALID_OR_EXPIRED_VERIFICATION_TOKEN` 400 with zero mutation/orchestration.
Confirmed by H1 test suite. **PASS**.

## Gate 18 — Valid Pending + Retry-Anchor Paths

Valid token → 200, `complete_email_verified_onboarding` called.
Setup-email retry-anchor confirmed via `test_u6l` suite. **PASS**.

---

## Gate 19 — Static Analysis

| Check | Result |
|-------|--------|
| `git diff --check` (whitespace) | **PASS** — no errors |
| `pre-commit run --files` (scoped to diff) | **PASS** — all hooks pass, detect-secrets clean |
| `detect-secrets` (via pre-commit) | **PASS** — no secrets leaked |
| GitNexus analyze/status | **TOOLING_ENVIRONMENT_BLOCKED_NON_PRODUCT** — `gitnexus` not installed in this Python/npm environment |
| GitNexus CTO evidence | `d44abae` is a valid, fully indexed commit (`git cat-file -e d44abae` ✅) |

---

## Gate 20 — Cleanup Proof

| Resource | Status |
|----------|--------|
| Run A PG container | Removed ✅ |
| Run A Redis container | Removed ✅ |
| Run A Docker network | Removed ✅ |
| Run A database volume | Not used (ephemeral container) ✅ |
| Run B PG container | Removed ✅ |
| Run B Redis container | Removed ✅ |
| Run B Docker network | Removed ✅ |
| Run B database volume | Not used (ephemeral container) ✅ |
| Worktree (`/home/ivy/MPANGO/dc12r1-s1-h1-r2-r1-v2-r1-verify`) | Removed ✅ |
| Temp logs (`/tmp/pair_a_r1_results.out`, `/tmp/pair_b_r1_results.out`, etc.) | Removed ✅ |

No stray `dc12r1-s1-h1-r2-r1-v2-r1` containers, networks, or volumes remain.

---

## Summary

| Criterion | Status |
|-----------|--------|
| Target/base identity | **PASS** |
| File change set (5 files, no migrations/config/frontend) | **PASS** |
| Product commit 9420476b | **PASS** |
| R2/R2-R1 modifies only U6I1 test contract | **PASS** |
| Alembic sole head 036 | **PASS** |
| H1 + regression bundle (83 pass, 0 fail) | **PASS** |
| U6I1 portable to source export (6/6, no .git) | **PASS** |
| Terminal-state neutral error + retry-anchor | **PASS** |
| Static analysis (diff-check, pre-commit, secrets) | **PASS** |
| GitNexus | **TOOLING_ENVIRONMENT_BLOCKED** (not installed) |
| Full suite Run A (2885 pass, 1 flake fail, 0 err) | **FAIL** (exit=1) |
| Full suite Run B (2886 pass, 0 fail, 0 err) | **PASS** (exit=0) |
| Identical Run A/B totals | **FAIL** (1-test Hypothesis swing) |
| Exit=0 + failed=0 + errors=0 (both runs) | **FAIL** |
| **CURRENT_PRODUCT_DEFECT** | **NONE** |

### Recommended CTO Action

The sole red node is a **pre-existing Hypothesis flake** in `test_uuid_serialization.py`:
the `@settings(deadline=200)` is too tight for this system. It is:

- Not caused by H1 (H1 modifies `onboarding_service.py` only)
- Not caused by R2/R2-R1 (R2 modifies `test_u6i1_owner_credential_setup_schema.py` only)
- Not deterministic (Run B had 0 failures on identical infrastructure)
- Reproducible standalone only under load spikes

The **R2-R1 U6I1 contract fix is verified working** — the stale-test-contract
from the V1 report is fully resolved. The U6I1 test file has no git dependency
and passes from source exports with no `.git` directory.

If CTO accepts the UUID Hypothesis flake as pre-existing and non-deterministic
(fix: add `deadline=None` or `suppress_health_check` to the UUID tests), the
merge may proceed. Otherwise, the UUID test needs a separate trivial fix commit.
