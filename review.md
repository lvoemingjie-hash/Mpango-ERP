# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R3-V1 Kilo Bounded Authority Entrypoint Review

**Review Date:** 2026-09-01
**Reviewer:** Kilo, Independent Reviewer
**Base Commit:** `a0991a84eb7f41c575370770133786e023967f2f`
**Candidate Commit:** `854c680e6fab56e6b1f33a00350a155c443eb3e4`
**Verification Tier:** V1_BOUNDED_GOVERNANCE_SOURCE_AND_TEST_AUTHENTICITY
**Claim Ceiling:** AUTHORITY_ENTRYPOINT_SOURCE_AND_TEST_AUTHENTICITY_APPROVAL_ONLY

---

## Executive Summary

This review independently verifies the B1-R6-R3-R1 authority entrypoint implementation.
The candidate adds the only direct-process authority evidence path while keeping
library `ControlPlane` instances non-authority. All authority boundary controls
are verified source-valid, and independent falsification confirms the guards are
effective.

**Verdict: PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R3_V1_KILO_BOUNDED_AUTHORITY_ENTRYPOINT_REVIEW**

---

## Phase 1: Proof Gate

### Verification Results

| Check | Status |
|-------|--------|
| `git fetch --all --prune` | EXECUTED |
| Candidate remote tip == `854c680e...` | VERIFIED |
| `CANDIDATE^ == BASE a0991a84...` | VERIFIED |
| Clean detached worktree created | VERIFIED |
| BASE..CANDIDATE path list | 8 files (3 A, 5 M) |
| Scope: `j1h2c-retailer-recovery/**` + 1 ledger | VERIFIED |
| Backend/frontend/product tree frozen | VERIFIED |
| Migrations/spec/inventory/harness-governance frozen | VERIFIED |
| Dependencies + lockfile frozen | VERIFIED |

### Worktree Record

- **COMMIT:** `854c680e6fab56e6b1f33a00350a155c443eb3e4`
- **TREE:** `694e0d8e2a783a3d910324ee97438e4823a3005a`
- **PARENT:** `a0991a84eb7f41c575370770133786e023967f2f`

### Delta Path List (BASE..CANDIDATE)

```
A  ai-ledger/product-ai/2026-09-01_dc12r1_mvp_l1_j1_h2_c_i2_e2_b1_r6_r3_r1_direct_authority_entrypoint.md
M  j1h2c-retailer-recovery/README.md
A  j1h2c-retailer-recovery/tools/browser-authority-child.mjs
M  j1h2c-retailer-recovery/tools/browser-authority-cors-probe-helper.mjs
A  j1h2c-retailer-recovery/tools/browser-authority-entrypoint.mjs
M  j1h2c-retailer-recovery/tools/browser-authority-runner.mjs
M  j1h2c-retailer-recovery/tools/check-browser-authority-contracts.mjs
M  j1h2c-retailer-recovery/tools/validate-static.mjs
```

**A/M/D Count:** A=3, M=5, D=0

---

## Phase 2: Authority Boundary Review

### Source Verification

| # | Control | Status | Evidence |
|---|---------|--------|----------|
| 1 | Library `ControlPlane` rejects `authority:true` | PASS | runner.mjs:788-790 throws `authority_mode_required` |
| 2 | `seal()`/`evidence()` throw `authority_mode_required` in library mode | PASS | runner.mjs:1380-1382, 1403-1405 |
| 3 | Authority capability is module-private `Symbol` | PASS | runner.mjs:80 `AUTHORITY_CAPABILITY_BRAND` not exported |
| 4 | Only direct-process entrypoint can mint authority | PASS | entrypoint.mjs:64-69, runner.mjs:207-219 |
| 5 | Entrypoint rejects NODE_OPTIONS/NODE_PATH/GIT_* (case-insensitive) | PASS | entrypoint.mjs:96-101 |
| 6 | Canonical repo root + candidate HEAD + committed blob binding | PASS | runner.mjs:417-419, 426-441, 457-468 |
| 7 | Helper + fixed child paths not substitutable | PASS | runner.mjs:128-138 |
| 8 | All subprocesses use argv array, no `shell:true` | PASS | runner.mjs:228, 235, 245, 252, 396-403, 1039-1041, 1282-1284 |
| 9 | CORS helper output exact schema; pass requires all three true | PASS | runner.mjs:283-318 |
| 10 | Authority order: materialize → CORS probe → preflight → authorize → launch → seal → evidence | PASS | entrypoint.mjs:189-206 |
| 11 | Child `rc != 0` or incomplete reconciliation → TEST_RED | PASS | runner.mjs:1307-1355 |
| 12 | Preflight RED/exception → STOP, launch count=0 | PASS | runner.mjs:1110-1147 |
| 13 | Terminal seal/evidence re-verify ledger chain + bindings | PASS | runner.mjs:1379-1394, 1402-1430 |

---

## Phase 3: Independent Falsification

### Checker Execution

| Test | Result |
|------|--------|
| R1-R29-R1 checker (full) | **GREEN** |
| S0 schema + profile + env.ts reconciliation | PASS |
| G deterministic input SHA + deep freeze | PASS |
| R1 owner-label overwrite guard | PASS |
| R2 missing required field | PASS |
| R3 transition from mismatch | PASS |
| R4 post-STOP rejection ledgered | PASS |
| R5 every surface after VOID | PASS |
| R6 second preflight | PASS |
| R7 second browser launch | PASS |
| R8 caller-side SHA mismatch | PASS |
| R9 argv drift + non-array argv | PASS |
| R10 sensitive value into ledger | PASS |
| R11 live contract bytes mutated | PASS |
| R12 materialized input tamper | PASS |
| R13 candidate binds canonical HEAD | PASS |
| R14 child failure → TEST_RED | PASS |
| R15 second preflight then launch | PASS |
| R16 ledger truncation/rewrite/duplicate | PASS |
| R17 each profile field deleted | PASS |
| R18 weaker caller contract | PASS |
| R19 profilePath override ignored | PASS |
| R20 async child outcome truth | PASS |
| R21 tampered ledger verifier | PASS |
| R22 dirty working-tree profile | PASS |
| R23 foreign repoRoot | PASS |
| R24/R25 GIT_* identity injection | PASS |
| R26 mandatory CORS probe matrix | PASS |
| R27 ambient fetch poisoning | PASS |
| R28 launcher http/https poisoning | PASS |
| R29 mutable launcher child forgery | PASS |

### Independent Mutation Tests (KILO_INDEPENDENTLY_EXECUTED_EVIDENCE)

| Test | Result |
|------|--------|
| M1: Library fake sync child cannot seal/evidence | PASS |
| M2: Library fake async child cannot seal/evidence | PASS |
| M3: Import entrypoint rejected | PASS |
| M4: node -e dynamic import rejected | PASS |
| M5: Helper path fixed | PASS |
| M6: Child path fixed | PASS |
| M7: CORS payload ok:true + missing true values rejected | PASS |
| M8: rc=0 incomplete reconciliation → TEST_RED | PASS |
| M9: Public authority:true refused | PASS |
| M10: Authority capability branding (Symbol required) | PASS |
| M11: sealAuthorityEvidence library refusal | PASS |
| M12: Authority guard mutation (this.#authority=false→true) | PASS |

### Mutation Recovery

- Runner source restored byte-identical after mutation test
- SHA-256 of runner.mjs before == after mutation

---

## Phase 4: Frozen Gates

| Gate | Command | Exit Code | Status |
|------|---------|-----------|--------|
| Frozen lockfile | `pnpm install --frozen-lockfile` | 0 | PASS |
| Test list | `pnpm run test:list` | 0 | PASS (15 tests / 1 file, order unchanged) |
| Static validation | `pnpm run validate:static` | 0 | PASS (14/14 steps) |
| Neutrality | `pnpm run check:neutrality` | 0 | PASS (G1-G6) |
| Runtime contracts | `pnpm run check:runtime-contracts` | 0 | PASS |
| Browser authority | `pnpm run check:browser-authority` | 0 | PASS (R1-R29) |
| Typecheck | `pnpm run typecheck` | 0 | PASS |
| Diff check | `git diff --check BASE..CANDIDATE` | 0 | PASS |

### Delta File Encoding

| File | BOM | NUL | CR (committed) | LF-only (committed) |
|------|-----|-----|----------------|---------------------|
| ai-ledger/...entrypoint.md | No | No | No | Yes |
| j1h2c-retailer-recovery/README.md | No | No | No | Yes |
| tools/browser-authority-child.mjs | No | No | No | Yes |
| tools/browser-authority-cors-probe-helper.mjs | No | No | No | Yes |
| tools/browser-authority-entrypoint.mjs | No | No | No | Yes |
| tools/browser-authority-runner.mjs | No | No | No | Yes |
| tools/check-browser-authority-contracts.mjs | No | No | No | Yes |
| tools/validate-static.mjs | No | No | No | Yes |

Note: Working-tree files may show CRLF due to git autocrlf on Windows, but committed blobs are LF-only (verified via `git show` hex dump).

---

## Phase 5: Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R3_V1_KILO_BOUNDED_AUTHORITY_ENTRYPOINT_REVIEW**

### Justification

1. **Authority boundary is source-valid:** The only authority path is the direct-process entrypoint. Library `ControlPlane` instances cannot mint terminal seal or evidence (verified by M1, M2, M9, M10, M11, M12).

2. **No public authority elevation:** `authority:true` is rejected at construction. The module-private `Symbol`-branded capability cannot be forged from caller input (verified by M9, M10).

3. **Import/dynamic-import/`-e` cannot mint authority:** The entrypoint's direct-process detection fails for imported code (verified by M3, M4).

4. **Helper + child paths are fixed:** Derived from the module's own location, not from CLI/env/contract/input (verified by M5, M6).

5. **CORS probe is process-isolated with exact schema:** The helper runs in a fresh child; pass requires `ok=true AND status_2xx=true AND allow_origin_exact=true` (verified by M7, R26-R28).

6. **Preflight RED stops the plane:** Launch count remains 0; no authorize/launch after RED (verified by R6, R15, R26).

7. **Launch is at-most-once:** Second launch is refused (verified by R7).

8. **Ledger integrity is enforced:** Truncation, rewrite, and duplicate-seq fail closed; evidence forces chain re-verification (verified by R16, R21).

9. **Mutation tests confirm guard effectiveness:** The `this.#authority = false` guard is the only thing preventing library seal/evidence; mutating it allows seal, restoring it refuses seal (verified by M12).

10. **All frozen gates pass:** Install, test:list (15/1), static (14/14), neutrality (G1-G6), runtime-contracts, browser-authority (R1-R29), typecheck, diff-check.

---

## Phase 6: Publication

### Report Branch

- **Branch:** `reports/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r3-v1-kilo-bounded-authority-entrypoint-review-2026-09-01`
- **Created from:** candidate `854c680e6fab56e6b1f33a00350a155c443eb3e4`
- **Files added:** `review.md`, `findings.csv`

### Evidence Tags

- `KILO_INDEPENDENTLY_EXECUTED_EVIDENCE`: All mutation tests (M1-M12), checker execution, frozen gates
- `CANDIDATE_PROVIDED_EVIDENCE`: Ledger file, candidate commit message

### Cleanup

- Worktree `C:\Users\Jeff0\dc12r1_r6_r3_v1_wt` will be removed
- Temporary mutation files cleaned up

---

## STOP Conditions Checked

| STOP Condition | Triggered |
|----------------|-----------|
| Public API can obtain authority capability | NO |
| Import/`-e`/env injection can enter authority path | NO |
| Helper/child/candidate identity substitutable | NO |
| Fake child result can produce terminal seal/evidence | NO |
| Preflight RED still allows authorize/launch | NO |
| Launch can exceed once | NO |
| Ledger/critical bytes tampering allows evidence | NO |
| Checker/mutation false green, candidate drift, scope exceed | NO |

---

**Review Complete.**
