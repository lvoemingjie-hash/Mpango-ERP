# CORRECTION — R8-V2 Verdict RETRACTED/SUPERSEDED_BY_R9

**Date**: 2026-08-11
**Branch**: reports/dc12r1-s3-s2b-i2b-i2b-r8-v2-lubuntu-independent-final-2026-08-11

## Original verdict: RETRACTED

The original R8-V2 report declared:

> PASS_DC12R1_S3_S2B_I2C_I2B_R8_V2_INDEPENDENT_FINAL (269/270 passed, 1 date-boundary failure)

**This verdict is RETRACTED and SUPERSEDED_BY_R9.**

## Failed-node evidence (preserved)

The single failure in R8-V2 was:

- **Test**: `StatementPrintWorkspace.test.tsx > R1 rule 6 — EAT calendar dates > frozen time: the UTC calendar date differs from EAT; eatToday picks EAT`
- **Assertion**: `expected '2026-08-11' to be '2026-08-10'`
- **Root cause**: The test relied on `new Date()` wall-clock time. At verification time (07:06 UTC, 10:06 EAT), both UTC and EAT dates were `2026-08-11`, so the test's expectation that UTC and EAT dates differ could not be satisfied.
- **Node**: `src/tests/StatementPrintWorkspace.test.tsx:878`
- **Expected value**: `2026-08-10` (UTC date when EAT has crossed midnight but UTC has not)
- **Actual value**: `2026-08-11` (wall-clock date at verification time)

## Supersession

R9 (`133ca46b`) closes this defect by using `vi.useFakeTimers()` + `vi.setSystemTime(new Date('2026-08-10T22:30:00Z'))` in both EAT boundary tests, making them deterministic and independent of wall-clock time. The R9-V2 independent verification confirms 270/270 passed, 0 failed.

The R9-V2 report branch supersedes this report:
`reports/dc12r1-s3-s2b-i2c-i2b-r9-v2-lubuntu-independent-final-2026-08-11`

## Backend evidence preserved (unchanged)

R8-V2 backend evidence stands and is reused by R9-V2:
- Stack A: 3285 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors
- Stack B: 3285 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors
