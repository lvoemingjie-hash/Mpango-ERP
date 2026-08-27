# DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1-V1 Kilo Final Harness Authenticity Review

**Date:** 2026-08-27 (+08:00)
**Reviewer:** Kilo
**CANDIDATE:** `36f70fb9a074423b585de38e7a7893e80a0eb932`
**BASE:** `bf20e8c9eae620fcf101ded672dfb0afeab937cb`
**Verdict:** `STOP_AND_REPORT_CTO`

---

## 1. Proof Gate Summary

| Check | Result | Evidence |
|---|---|---|
| Detached clean worktree from CANDIDATE | PASS | Worktree created at `36f70fb9`, detached HEAD, clean status |
| Source tip | PASS | `36f70fb9 docs(h2-c-b1): ledger - frozen harness engineering...` |
| Commit chain BASE..CANDIDATE | PASS | 3 commits: IMPLEMENTATION (`6be2b5c6`), STATIC_FIX (`70c662b7`), CANDIDATE (`36f70fb9`) |
| Exactly 25 new files | PASS | 24 under `j1h2c-retailer-recovery/**` + 1 under `ai-ledger/product-ai/` |
| Zero changes outside harness | PASS | No product, test, j1h2b, migration/model/dependency/product lockfile changes |
| Inventory CSV byte-identical to source | PASS | Git blob `caa5340299eb2396aa93e25468b3d6b1a58f83c4`, SHA-256 `70446a0ad80a48a6ecfcf683a763c971661c28a8caa7c6021701ec65faf243c8` |
| 17×15 specs | PASS | 15 BROWSER (HC01–HC10, HC12–HC16) + 2 STATIC (HC11, HC17) = 17 nodes |

---

## 2. Structure and Fail-Stop Summary

| Check | Result | Evidence |
|---|---|---|
| Single spec | PASS | `tests/recovery.spec.ts` only |
| Single serial describe | PASS | `test.describe.configure({ mode: 'serial' })` |
| workers=1, retries=0, maxFailures=1, fullyParallel=false | PASS | `playwright.config.ts` |
| `--list` exactly 15 | PASS | `playwright test --list` → 15 tests in 1 file |
| No skip/fixme/only/sleep/waitForTimeout/networkidle | PASS | Static scan clean |
| trace/screenshot/video off | PASS | `playwright.config.ts` |
| Env missing fail-closed, `--list` env-free | PASS | `src/env.ts` lazy-load in `beforeAll`, `required()` throws on missing |
| 15 browser + 2 static reconciliation no pre-write PASS | PASS | `src/reconciliation.ts` starts PENDING, records only actual passes |

---

## 3. Static Runtime Summary

| Check | Result |
|---|---|
| `pnpm install --frozen-lockfile` | PASS |
| `playwright test --list` | PASS (15 tests) |
| `validate:static` | PASS (9/9 steps) |
| `check:neutrality` (G1–G6) | PASS |
| `tsc --noEmit` | PASS |
| `git diff --check` | PASS (clean) |
| `detect-secrets` | PASS (0 findings in source) |
| UTF-8 / no-BOM / no-NUL / LF | PASS |
| GitNexus analyze/status | PASS (indexed at `36f70fb`, up-to-date) |
| Worktree clean | PASS |

**M1–M10 mutation truth:** Not personally executed by this review. Marked `CANDIDATE_PROVIDED` per verification tier constraints.

---

## 4. Mandatory Adversarial STOP Checks — Verdict: STOP

### A. HC12 reset POST authenticity — DETERMINISTIC FALSE POSITIVE (假红)

- **File / Line:** `src/leak-scan.ts:61-71` (`requestCarriesSecret`), `tests/recovery.spec.ts:283-318` (HC12 test)
- **Mechanism:** `scanForSecretLeak()` scans **all** captured requests, including the reset POST. `requestCarriesSecret()` checks `postData.includes(secret)`. The reset POST body **legitimately** contains the `reset_token` per the contract. The scanner deterministically flags the reset POST as a leak, causing HC12 to always fail.
- **Additional gap:** No verification that exactly one reset POST occurred, and no verification that the POST body contains the required `reset_token` + `new_password` fields.
- **Minimal fix:** Exclude the reset POST from the leak scan, or whitelist the `reset_token` field inside the reset POST body. Add explicit assertions for exactly one reset POST and required body fields.

### B. Public `w` complete leak boundary — INCOMPLETE

- **File / Line:** `src/leak-scan.ts:100-114` (`assertPublicCodeOnlyInAllowedLocations`)
- **Mechanism:** The function only checks the current page URL. It does **not** scan `localStorage`, `sessionStorage`, `console` output, or request URLs/headers/bodies for the public `w` code.
- **Minimal fix:** Extend the public `w` boundary check to cover storage, console, and all network requests.

### C. HC09 genuine wrong-supplier state — FABRICATED STATE (假绿)

- **File / Line:** `tests/recovery.spec.ts:218` (`WRONG${CANONICAL}`), `src/env.ts` (no second-supplier identity)
- **Mechanism:** `WRONG${CANONICAL}` is a fabricated string, not a real second supplier code. The env and provisioning contract contain **no** second supplier identity. The task explicitly says: "若当前 env/供给合同没有第二供应商身份，STOP。"
- **Minimal fix:** Provision a real second supplier code through the formal API or frozen launcher pre-contract, add it to the env with a fail-closed preflight contract, and use it in HC09.

### D. Official provisioning reachability — DEAD CODE (假绿)

- **File / Line:** `src/api-client.ts:31-49` (`provisionRetailerViaLifecycle`)
- **Mechanism:** `api-client.ts` is **never imported** in the test spec. It is dead code. The spec provides no proof that `established`, `unverified`, `unknown`, and `wrong-supplier` states can be deterministically produced by the frozen harness/launcher's official API pre-contract.
- **Minimal fix:** Either integrate `api-client.ts` into the spec's setup/teardown to prove deterministic state production, or remove it if it is not part of the frozen contract.

### E. HC11/HC17 mail freshness — INVALID FRESHNESS PROOF (假绿)

- **File / Line:** `src/maildir.ts:41-67` (`readLatestDelivery`), `tests/recovery.spec.ts:249-279`
- **Mechanism:** `readLatestDelivery()` sorts filenames and takes the latest — no pre-HC07 snapshot, no polling for exactly one new delivery. `parseResetLink()` only checks for `#` in the link; it does not validate pathname or query. HC11 assumes `link.startsWith('/retailer/reset-password#resetToken=')`, which forbids absolute URLs.
- **Minimal fix:** Add a pre-HC07 maildir snapshot, poll until exactly one new delivery appears, validate pathname + fragment + query in the reset link, and remove the `startsWith` assumption.

### F. HC06 genuine user double-click — NON-GENUINE UI (假绿)

- **File / Line:** `src/ui-journey.ts:52-58` (`doubleClickSubmit`)
- **Mechanism:** `doubleClickSubmit()` calls `button.dispatchEvent('click')` twice. This bypasses Playwright's actionability checks and is **not** a genuine user double-click.
- **Minimal fix:** Replace with `page.dblclick()` or Playwright's real mouse double-click action.

### G. HC16 responsive authenticity — INVALID VIEWPORT PROOF (假绿)

- **File / Line:** `tests/recovery.spec.ts:399-403` (HC16 test)
- **Mechanism:** HC16 opens `/retailer/reset-password` **without** a valid token or `w`. This is a neutral invalid page, not the real interactive reset form with valid credentials. The task requires verifying 390px with a valid token+w on the real reset form.
- **Minimal fix:** Replicate HC12/HC13's setup (valid token+w, real reset form) before asserting 390px.

### H. Runtime reconciliation publication — NO ARTIFACT, NO MEMORY CLEAR (假绿)

- **File / Line:** `src/reconciliation.ts` (in-memory only), `tests/recovery.spec.ts:405-407` (`assertComplete` only), `src/token-store.ts:42-46` (`clearMemoryState` unused)
- **Mechanism:**
  1. `clearMemoryState()` is **never** called in `afterAll`/`finally`.
  2. Reconciliation is in-memory only. No independent, auditable artifact is written. `assertComplete()` proves 17-node gap=0 only in-process, not via a persisted artifact.
- **Minimal fix:** Call `clearMemoryState()` in `afterAll`/`finally`. Write a reconciliation artifact (e.g., JSON) proving 17 nodes with gap=0.

### I. Artifact scanner authority — DEFAULT SKIPS SECRET SCAN (假绿)

- **File / Line:** `package.json` (`scan:artifacts` script)
- **Mechanism:** The `scan:artifacts` script is `node tools/scan-artifacts.mjs --artifacts-dir artifacts`, which **does not** include `--secrets-from-env`. The task requires the authoritative command to enable `--secrets-from-env`; the package script/README must not default to skipping runtime secret scanning.
- **Minimal fix:** Change the script to `node tools/scan-artifacts.mjs --secrets-from-env --artifacts-dir artifacts` and update the README accordingly.

---

## 5. Non-Claims Verified

- No browser PASS claimed.
- No backend zero-red claimed.
- No merge-ready claimed.
- No deployment-ready claimed.
- 390px checks are simulated viewport checks, not real-device proofs.

---

## 6. Recommendation

**STOP_AND_REPORT_CTO.** The harness contains 9 authenticity violations (A–I) that produce deterministic false positives (A, B), fabricated test states (C), dead code masking missing provisioning proof (D), invalid freshness proofs (E), non-genuine UI actions (F), invalid viewport proofs (G), missing runtime artifacts and memory cleanup (H), and a scanner configuration that skips required secret verification (I). None of these can be resolved by running the browser; they require source-level corrections before any authoritative run is meaningful.
