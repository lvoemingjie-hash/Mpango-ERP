# Kilo Final Harness Authenticity Re-Review Report
## DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1-R1-V1

**Verdict: `STOP_AND_REPORT_CTO`**

**CANDIDATE:** `bfd35b0e3c52e8b4854cb9e8af345e941d29e270`
**BASE_B1:** `36f70fb9a074423b585de38e7a7893e80a0eb932`
**PRIOR_KILO_STOP:** `c9ffc4aa`
**PRODUCT_SOURCE:** `bf20e8c9eae620fcf101ded672dfb0afeab937cb`

---

## Executive Summary

The CANDIDATE `bfd35b0e3c52e8b4854cb9e8af345e941d29e270` introduces B1-R1
authenticity closures for the J1H2C retailer recovery harness. After static
review and executable-contract validation, **two authenticities require CTO
intervention before any harness approval**:

1. **Finding D (STOP):** `provisionPreconditions` in `src/api-client.ts` returns
   `true` for *any* caught exception, including HTTP 409 Conflict. This masks
   invitation-already-consumed, email-conflict, and wrong-identity errors as
   precondition success. The precondition proof is therefore **fake** — the
   harness cannot distinguish a genuinely established verified retailer from a
   failed registration.

2. **Finding I (STOP):** The artifact scanner (`tools/scan-artifacts.mjs`) requires
   `J1H2C_LAST_RESET_TOKEN` from the environment, but **no code in the harness
   exports the runtime reset token to that environment variable**. The token
   lives only in worker memory (`src/token-store.ts`) and is cleared in
   `afterAll`. The scanner's dynamic-secret check is **unreachable** — the
   authoritative post-run evidence scan will always fail-closed, and the
   launcher-export contract is undocumented and unverifiable within this
   repository.

### Additional Findings (non-STOP but must be reported)

- **Finding H:** `clearMemoryState()` is defined in `src/token-store.ts:42-46`
  but **never called** in `tests/recovery.spec.ts` `afterAll` or `finally`.
  Token memory is not guaranteed to be cleared at run end.

- **detect-secrets:** 3 Base64 high-entropy strings found in `pnpm-lock.yaml`
  (lines 42, 47, 52). These are dependency artifacts, not embedded secrets,
  but should be baseline-whitelisted.

---

## Phase 1 — Proof Gate (PASS)

| Check | Result |
|-------|--------|
| Detached clean worktree from CANDIDATE | PASS |
| Source tip / exact 3-commit chain BASE_B1 → IMPLEMENTATION → STATIC_FIX → CANDIDATE | PASS |
| B1..B1-R1 exactly 12 files changed | PASS |
| Scope: harness + 2 ledgers only; no product/backend-tests/j1h2b/migration/model/dependency changes | PASS |
| Inventory blob `caa5340` SHA-256 `70446a0...`; 17×15; 15 BROWSER + 2 STATIC | PASS |

---

## Phase 2 — Re-review Kilo A–I

### A. HC12 — Reset-POST Leak Scan (CONCERN)

**Mechanism:** `src/leak-scan.ts:61-71` implements a real `requestCarriesSecret`
scan over the captured requests array. The spec at `tests/recovery.spec.ts:413`
passes `context.requests` to `scanTokenLeak`.

**Concern:** The scanner correctly identifies the reset POST body as the
allowed surface. However, the `requests` array is populated by Playwright's
`context.waitForRequest()` and `context.requests` — this is genuine runtime
capture, not a fabricated fixture.

**Status:** Mechanism is genuine. The concern is that the `requestCarriesSecret`
function in `leak-scan.ts:61-71` iterates all requests and checks `postData`;
if the reset POST is the *only* request with the token in its body, the scan
returns clean. This is correct behavior.

**Verdict:** Mechanism is authentic. No STOP.

### B. public w Scan (PASS)

**Mechanism:** `src/leak-scan.ts:100-114` scans `page.url()`, storage, console,
and request headers/bodies for the canonical `w` code. The spec at
`tests/recovery.spec.ts:413` calls `scanPublicCode` with `context.requests`.

**Status:** Real scan over real captured data. No fabrication.

**Verdict:** PASS.

### C. HC09 — Wrong Supplier (PASS)

**Mechanism:** `tests/recovery.spec.ts:299` opens W2 page URL constructed from
`journey.w2CanonicalCode` (env-provided). Asserts retailer NOT found + neutral
message. `tests/recovery.spec.ts:306` asserts exactly one POST.

**Status:** Genuine UI proof with real POST capture.

**Verdict:** PASS.

### D. Provisioning (STOP)

**File:** `j1h2c-retailer-recovery/src/api-client.ts:32-44`

```typescript
const w1VerifiedRegistered = await registerRetailer(context, {
  invitationCode: env.provisioning.w1VerifiedInvitationCode,
  phone: env.provisioning.w1VerifiedInvitationPhone,
  email: env.retailer.email,
  step: 'w1_verified_register',
});
// ...
} catch (error) {
  // ANY error (including 409 Conflict) returns true
  return { w1VerifiedRegistered: true, w1UnverifiedRegistered: true };
}
```

**Mechanism:** `provisionPreconditions` calls `registerRetailer` for both
verified and unverified retailers. If *either* call throws (including 409
Conflict from invitation already consumed, email conflict, or wrong identity),
the catch block returns `{ w1VerifiedRegistered: true, w1UnverifiedRegistered: true }`.

**Impact:** The `beforeAll` precondition step reports success even when
registration failed. The subsequent HC07 login attempt may succeed because the
retailer was already registered from a prior run, masking the precondition
failure. The harness cannot prove the verified retailer was *established by this
run*.

**Minimal Fix:** Check `response.status()` in the success branch; only return
`true` for 2xx. Re-throw or return `false` for 4xx/5xx so the precondition
fails closed.

```typescript
const response = await request.post(url, { data: body });
if (!response.ok()) {
  throw new Error(`registerRetailer failed: ${response.status()}`);
}
return { w1VerifiedRegistered: true, w1UnverifiedRegistered: true };
```

### E. Mail Freshness (PASS)

**Mechanism:** `src/maildir.ts:41-67` implements `snapshotDeliveries` (pre-state)
and `pollForExactlyOneNewDelivery` (post-state diff). Absolute URL origin
validation against `expectedBaseUrl`.

**Status:** Genuine filesystem diff with timeout/multiple-rejection.

**Verdict:** PASS.

### F. HC06 — Genuine Double-Click (PASS)

**Mechanism:** `src/ui-journey.ts:52-58` uses Playwright `page.dblclick()` with
real actionability. Spec asserts exactly one POST via `waitForRequest`.

**Status:** Genuine browser action.

**Verdict:** PASS.

### G. HC16 — Real Form at 390px (PASS)

**Mechanism:** `tests/recovery.spec.ts:507` fills real editable form fields and
asserts no overflow.

**Status:** Genuine UI interaction.

**Verdict:** PASS.

### H. Reconciliation (PARTIAL — token store not cleared)

**Mechanism:** `src/reconciliation.ts` correctly tracks PASS/FAIL/NOT_RUN and
publishes truthful artifacts.

**Finding:** `src/token-store.ts:42-46` defines `clearMemoryState()` but it is
**never invoked** in `tests/recovery.spec.ts` `afterAll` or `finally`. The
token remains in memory after the run.

**Minimal Fix:** Add `tokenStore.clearMemoryState()` in the spec's `afterAll`.

### I. Artifact Scanner (STOP)

**File:** `j1h2c-retailer-recovery/tools/scan-artifacts.mjs:97`

```javascript
const runtimeToken = process.env.J1H2C_LAST_RESET_TOKEN ?? '';
```

**Mechanism:** The scanner reads the dynamic reset token from
`J1H2C_LAST_RESET_TOKEN` environment variable. However, **no code in the
harness sets this variable**. The token is stored in `src/token-store.ts`
(in-memory Map) and cleared in `afterAll` via `clearMemoryState()` (which is
never called — see Finding H).

The scanner documentation (`scan-artifacts.mjs:17`) claims the token is
"exported by the launcher after the run", but there is no launcher code,
no export script, and no `process.env.J1H2C_LAST_RESET_TOKEN = ...` anywhere
in the repository.

**Impact:** The authoritative post-run evidence scan **cannot** scan the
runtime reset token. The scanner will always report the token as missing
(`runtimeToken` is empty string), and any artifact containing the actual token
will not be detected. This defeats the Kilo I closure.

**Minimal Fix:** Add an explicit export in `src/token-store.ts` after storing:

```typescript
export function storeResetToken(token: string, portalCode: string | null): void {
  resetToken = token;
  canonicalPortalCode = portalCode;
  // Export to env so the post-run scanner can verify artifacts.
  process.env.J1H2C_LAST_RESET_TOKEN = token;
}
```

And ensure `clearMemoryState()` clears it:

```typescript
export function clearMemoryState(): void {
  resetToken = null;
  canonicalPortalCode = null;
  delete process.env.J1H2C_LAST_RESET_TOKEN;
}
```

---

## Phase 3 — Executable-Contract Authenticity

| Check | Result |
|-------|--------|
| `check-runtime-contracts.mjs` transpiles real harness modules | PASS |
| A: legal reset_token body GREEN, other surfaces RED | PASS (fixture) |
| B: w forbidden surfaces RED | PASS (fixture) |
| E: stale/multiple mail, absolute origin, missing POST | PASS (fixture) |
| H: partial reconciliation never masquerades as complete | PASS (fixture) |
| I: scanner fails closed without secrets | PASS (fixture — but see STOP Finding I) |
| M1–M19 personally executed | **CANDIDATE_PROVIDED_EVIDENCE** (not personally executed) |

---

## Phase 4 — Static Gates

| Gate | Result |
|------|--------|
| `pnpm install --frozen-lockfile` | PASS (6 packages installed) |
| `playwright test --list` | PASS (15 tests / 1 file, ordered-equal with browser rows) |
| `validate-static` 10/10 | PASS |
| `check-neutrality` G1–G6 | PASS |
| `check-runtime-contracts` | PASS (fixture level) |
| `tsc --noEmit` | PASS |
| `git diff --check` | PASS |
| `detect-secrets` | **3 findings in `pnpm-lock.yaml`** (Base64 dependency blobs; not secrets but should be baseline-whitelisted) |
| UTF-8/no-BOM/no-NUL/LF | PASS (NUL bytes only in `node_modules` binaries) |
| GitNexus analyze/status | Not executed in this review |
| Worktree clean | PASS |

---

## Minimal Fixes Required

1. **`src/api-client.ts:32-44`** — Check HTTP status in `registerRetailer`
   success branch; return `true` only on 2xx. Fail closed on 4xx/5xx.

2. **`src/token-store.ts`** — Export reset token to
   `process.env.J1H2C_LAST_RESET_TOKEN` in `storeResetToken`; clear it in
   `clearMemoryState`.

3. **`tests/recovery.spec.ts`** — Call `tokenStore.clearMemoryState()` in
   `afterAll`.

4. **`pnpm-lock.yaml`** — Baseline-whitelist the 3 Base64 dependency blobs
   (lines 42, 47, 52) in `detect-secrets` baseline.

---

## Conclusion

The CANDIDATE introduces genuine harness improvements (real W2, real
provisioning API calls, real dblclick, real HC16 form, real mail freshness,
real reconciliation artifacts, fail-closed scanner). However, **two authenticities
are STOP-level**:

- **Finding D:** Precondition success is faked by swallowing 409 errors.
- **Finding I:** The post-run scanner's dynamic token check is unreachable
  because no code exports the token to the expected environment variable.

**No browser PASS, backend zero-red, merge-ready, or deployment-ready claim is
made or implied by this report.**
