# DC-12R1-MVP-L1-PW1-R2-R2-V2 — Full Browser Independent Final Report

**Date**: 2026-08-15
**Verdict**: STOP_AND_REPORT_CTO
**Reason**: HTTP 429 rate limiting prevents full 162-node test execution in single invocation

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Tests Collected | 162 |
| Passed | 80 |
| Failed | 82 |
| Skipped | 0 |
| Flaky | 0 |
| Errors | 0 |
| Blocked | 0 |
| Accounting Gap | 0 |

**Root Cause**: Backend rate limiter (100 req/min per IP) exceeded by test suite executing from same localhost IP (127.0.0.1).

---

## Phase Results

### Phase 1: Proof Gate ✅ PASS

| Check | Result |
|-------|--------|
| SHA d2e7e44 (product baseline) | ✅ Valid commit |
| SHA 9f5d677 (candidate source) | ✅ Valid commit |
| SHA d787c58 (canonical harness) | ✅ Valid commit |
| Candidate branch exists | ✅ zcode/dc12r1-mvp-l1-pw1-r2-auth-session-closure-2026-08-14 |
| Ancestry verified | ✅ Candidate is descendant of baseline |
| Candidate worktree clean | ✅ Detached HEAD at 9f5d677 |
| Backend byte match | ✅ Candidate backend matches baseline |
| Backend health live | ✅ 200 OK |
| Backend health ready | ✅ 200 OK |
| Frontend on port 5174 | ✅ 200 OK |
| MPANGO_ENV=staging | ✅ Confirmed |
| JwtAuthStrategy | ✅ Real JWT tokens returned |

### Phase 2: Harness Integrity ✅ PASS

| Check | Result |
|-------|--------|
| Harness SHA d787c58 | ✅ 38 files bit-identical |
| 162 nodes collected | ✅ 54 desktop + 54 tablet + 54 mobile |
| baseURL changed to 5174 | ✅ Only allowed config change |
| No test modifications | ✅ Source matches d787c58 |

### Phase 3: Auth Pre-Gate ✅ PASS (9/9)

| Test | Result |
|------|--------|
| W1 single-tenant login | ✅ Login API 200, auto select-tenant 200 |
| W2 multi-tenant login | ✅ Independent tenant verified |
| RA multi-tenant login | ✅ 2 available tenants in workspace |
| RB retailer portal login | ✅ Client auth API 200, lands on /client |
| RA retailer portal at W1 | ✅ Lands on /client |
| Wrong password 401 | ✅ API 401, stays on /login |
| Wrong password retailer 401 | ✅ API 401, stays on portal |
| /select-workspace redirect | ✅ Redirects to /login |
| Logout clears session | ✅ mpango-auth cleared |

### Phase 4: Full PW1 ❌ STOP (82/162 failed)

| Project | Passed | Failed | Rate |
|---------|--------|--------|------|
| desktop | 54 | 0 | 100% |
| tablet | 13 | 41 | 24% |
| mobile | 13 | 41 | 24% |
| **Total** | **80** | **82** | **49%** |

**All 82 failures are HTTP 429 (rate limit exceeded)**, not product defects.

### Phase 5: Financial And Isolation ⏸️ BLOCKED

Not reached due to Phase 4 failure.

### Phase 6: Evidence Reconciliation ⏸️ BLOCKED

Not reached due to Phase 4 failure.

### Phase 7: Quality And Residue ⏸️ BLOCKED

Not reached due to Phase 4 failure.

---

## Rate Limiting Analysis

### Configuration
- **Rate Limit**: 100 requests per minute per IP
- **Window**: 60 seconds (fixed window)
- **Anonymous Limit**: 100 req/min (IP-based)
- **Authenticated Limit**: 1000 req/min (tenant+user-based)

### Impact
- All 162 tests execute from same localhost IP (127.0.0.1)
- Login requests (before authentication) use IP-based limit
- Estimated 200+ login requests across all tests
- Rate limit exceeded after ~100 requests

### Recommendation
1. **Increase rate limit for testing**: Set `DEFAULT_IP_LIMIT=1000` for test environment
2. **Or implement rate limit bypass**: Add test-only bypass flag
3. **Or run tests sequentially**: Split into multiple invocations with Redis flush between

---

## Test Identities

| Role | Email | Tenant | Notes |
|------|-------|--------|-------|
| W1 | pw1r1.w1.r1@pw1r1.dev | Single-tenant | Wholesaler admin |
| W2 | pw1r1.w2.r1@pw1r1.dev | Single-tenant | Wholesaler admin |
| RA | pw1r1.ra.r1@pw1r1.dev | Multi-tenant | Retailer (2 tenants) |
| RB | pw1r1.rb.r1@pw1r1.dev | Single-tenant | Retailer (1 tenant) |

---

## Environment

| Component | Value |
|-----------|-------|
| Backend URL | http://127.0.0.1:8000 |
| Frontend URL | http://127.0.0.1:5174 |
| MPANGO_ENV | staging |
| Auth Strategy | JwtAuthStrategy |
| PostgreSQL | 127.0.0.1:15432 |
| Redis | 127.0.0.1:16379 |
| Backend PID | 38732 |
| Frontend PID | 26036 |

---

## Artifacts

- **Results JSON**: `test-reports/evidence/pw1-r2-r2-v2/results.json`
- **Reconciliation JSON**: `test-reports/evidence/pw1-r2-r2-v2/reconciliation.json`
- **Findings CSV**: `test-reports/evidence/pw1-r2-r2-v2/findings.csv`
- **Test Results**: `test-reports/results.json`
- **JUnit XML**: `test-reports/junit.xml`
- **Traces**: `test-results/*/trace.zip` (on failure)

---

## Verdict

**STOP_AND_REPORT_CTO**

The test suite cannot complete all 162 nodes in a single invocation due to backend rate limiting (100 req/min per IP). This is an infrastructure constraint, not a product defect. The product itself is functional - all 9 auth matrix tests passed, and 80 of 162 tests passed before rate limiting was triggered.

**Recommended Actions**:
1. Increase rate limit for test environment
2. Or implement rate limit bypass for automated testing
3. Or re-run with Redis flush between phases

---

**Report Generated**: 2026-08-15T00:30:00Z
**Report Version**: 1.0
**Classification**: Internal - Test Evidence
