# Lubuntu Independent Final Runtime Verification — DC-12R1-S3-S2B-I2C-I2B-R9-V2

**Date**: 2026-08-11  
**Executor**: Lubuntu host `ivy-20149` (Linux 7.0.0-28-generic x86_64, Ubuntu 24.04)  
**Candidate**: `133ca46be0c664be0118365dfcef85ce76e60379`  
**Parent**: `f6ac69ee01cc4d30f2a34f1ef2030fd70f2e518f`  
**Baseline**: `d45b5020b122b13c407a1c9204b18e587f9803fc`  
**Delta**: 2 files (test file + product ledger only; no backend, no production frontend)

---

## 1. Candidate SHA equality proof

```
$ git -C /tmp/opencode/r9-verify rev-parse HEAD
133ca46be0c664be0118365dfcef85ce76e60379
$ git -C /tmp/opencode/r9-verify show --stat 133ca46b | head -5
commit 133ca46be0c664be0118365dfcef85ce76e60379
Author: ivy <ivy@ivy-20149>
Date:   Sun Aug 10 23:15:31 2026 +0000

    test(EAT): deterministic fake-timer EAT boundary tests (R9-V2 closure)
```

## 2. R9 delta (parent..candidate)

```
$ git diff --name-only f6ac69ee..133ca46b
frontend/src/tests/StatementPrintWorkspace.test.tsx
ai-ledger/product-ai/2026-08-10_dc12r1_s3_s2b_i2c_i2b_contract_d_statement.md
```

Exactly 2 files. No backend file touched. No production frontend file touched.

## 3. Byte-identical tree proofs

```
$ git diff f6ac69ee..133ca46b -- backend/ | wc -l
0

$ git diff f6ac69ee..133ca46b -- frontend/src ':!frontend/src/tests/' | wc -l
0
```

Backend tree: **identical** to parent.  
Production frontend tree (excluding tests): **identical** to parent.

## 4. Kilo AI review

**Branch**: `reports/dc12r1-i2c-i2b-r9-v1-kilo-review-2026-08-11`  
**SHA**: `a56078c6687f38d6a55ebe4dfd38e01d61f84ec3`  
**Status**: ✅ PASS — 10/10 findings all PASS

## 5. R8-V2 retraction

**Old R8-V2 branch**: `reports/dc12r1-s3-s2b-i2b-i2b-r8-v2-lubuntu-independent-final-2026-08-11`  
**Correction commit**: `ed67c4d`  
**Old verdict**: `PASS_DC12R1_S3_S2B_I2C_I2B_R8_V2_INDEPENDENT_FINAL (269/270)`  
**New verdict**: **RETRACTED / SUPERSEDED_BY_R9**

The single failure in R8-V2 (date-boundary test) was a wall-clock timing artifact, not a product defect. R9 closes it with deterministic fake timers.

---

## 6. P2 Runtime Gates — Frontend

### 6.1 EAT boundary tests ×5 consecutive (3/3 each)

```
=== EAT run 1/5 ===
 Tests  3 passed | 40 skipped (43)
=== timer-leakage check: Header.test ===
 Tests  1 passed (1)
=== EAT run 2/5 ===
 Tests  3 passed | 40 skipped (43)
=== timer-leakage check: Header.test ===
 Tests  1 passed (1)
=== EAT run 3/5 ===
 Tests  3 passed | 40 skipped (43)
=== timer-leakage check: Header.test ===
 Tests  1 passed (1)
=== EAT run 4/5 ===
 Tests  3 passed | 40 skipped (43)
=== timer-leakage check: Header.test ===
 Tests  1 passed (1)
=== EAT run 5/5 ===
 Tests  3 passed | 40 skipped (43)
=== timer-leakage check: Header.test ===
 Tests  1 passed (1)
```

**Result**: ✅ 5×3/3 passed, 0 failures, 5×1/1 timer-leakage checks passed.

### 6.2 Assertion values — unchanged

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| UTC frozen date | `2026-08-10` | `2026-08-10` | ✅ |
| EAT frozen date | `2026-08-11` | `2026-08-11` | ✅ |
| EAT month range | `2026-08-01..2026-08-11` | `2026-08-01..2026-08-11` | ✅ |
| Default range | `2026-08-01..2026-08-11` | `2026-08-01..2026-08-11` | ✅ |
| Print href | `?from=2026-08-01&to=2026-08-10` | `?from=2026-08-01&to=2026-08-10` | ✅ |
| Date.now spy | none | none | ✅ |
| Skip/todo/weaken | none | none | ✅ |

### 6.3 Full vitest suite

```
 Test Files  20 passed (20)
      Tests  270 passed (270)
```

**Result**: ✅ 270/270 passed, 0 failed, 0 errors.

### 6.4 Production build

```
✓ built in 11.21s
EXIT=0
```

**Result**: ✅ Build succeeded, exit 0.

---

## 7. P2 Runtime Gates — Backend (Evidence Reuse)

R9 changed no backend file (byte-identical to parent). R8-V2 backend evidence is reused.

| Metric | Stack A | Stack B |
|--------|---------|---------|
| Passed | 3285 | 3285 |
| Skipped | 48 | 48 |
| xfailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |
| Exit code | 0 | 0 |
| Duration | 1716.46s | 1714.15s |

JUnit generator comparison: `exit 0, gap=0`.

**Reuse validity**: R9 delta is exactly 2 files — neither backend nor production frontend. Backend tree is byte-identical to parent f6ac69ee. Reuse is valid.

---

## 8. P3 Evidence Quality Checks

### 8.1 No Date.now spy

```
$ grep -n "vi.spyOn(Date" frontend/src/tests/StatementPrintWorkspace.test.tsx
CLEAN: no vi.spyOn(Date)
```

### 8.2 No skip/todo/conditional weakening

```
$ grep -n "\.skip\|\.todo\|xit(\|xdescribe" frontend/src/tests/StatementPrintWorkspace.test.tsx
CLEAN: no skip/todo/weaken
```

### 8.3 Timer-leakage evidence

After every EAT ×5 run and every StatementPrint ×3 run, `Header.test.tsx` (a non-fake-timer test) was run and confirmed 1/1 passed. No timer leakage detected.

---

## 9. Final verdict

### PASS_DC12R1_S3_S2B_I2C_I2B_R9_V2_INDEPENDENT_FINAL

| Gate | Result |
|------|--------|
| EAT boundary tests ×5 | ✅ 3/3 ×5 |
| Timer-leakage checks | ✅ 5×1/1 + 3×1/1 |
| Full vitest | ✅ 270/270 |
| Build | ✅ exit 0 |
| Backend evidence reuse | ✅ 3285/3285/15/0/0 |
| Assertion values | ✅ unchanged |
| Kilo review | ✅ 10/10 PASS |
| R8-V2 retraction | ✅ SUPERSEDED_BY_R9 |

**PASS_DC12R1_S3_S2B_I2C_I2B_R9_V2_INDEPENDENT_FINAL (270/270 passed, 0 failed)**

---

## 10. Branches

| Branch | Status |
|--------|--------|
| `reports/dc12r1-i2c-i2b-r9-v1-kilo-review-2026-08-11` | Kilo review (10/10 PASS) |
| `reports/dc12r1-s3-s2b-i2b-i2b-r8-v2-lubuntu-independent-final-2026-08-11` | RETRACTED/SUPERSEDED_BY_R9 |
| `reports/dc12r1-s3-s2b-i2c-i2b-r9-v2-lubuntu-independent-final-2026-08-11` | **This report** |
