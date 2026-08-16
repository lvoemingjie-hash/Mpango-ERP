# DC-12R1-MVP-L1-PW1-R4-B2-V1 — Kilo Final Bounded Harness Review

## Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_B2_V1_KILO_FINAL_REVIEW_AND_B3_AUTHORIZATION**

This is a bounded harness/evidence review only. No product fix, no R4-C execution, and no modification of the reviewed candidate or protected refs was performed.

---

## 1. Proof gate

- Product SHA: `888683ba23c14b48a102289a29f9b7adf674fdaf`
- R4-B SHA: `4f34c17fcf3e09d0f12595fe1d5c2f15b5447711`
- R4-B2 SHA: `ec94682178c3bb1aa0124edc6373a4a2314062b3`
- Branch: `origin/reports/dc12r1-mvp-l1-pw1-r4-b2-opencode-2026-08-16`

Verified in an isolated detached worktree:
- remote branch head == `ec94682178c3bb1aa0124edc6373a4a2314062b3`
- direct parent of `ec946821…` == `4f34c17f…`
- protected product baseline `origin/product-dev-recovered` == `888683ba…`
- product SHA is an ancestor of the candidate
- worktree stayed clean

No drift in the reviewed branch head or protected product baseline was observed during the review.

---

## 2. Exact B2 semantic delta

`git diff 4f34c17..ec94682` shows exactly one semantic harness change in the test source:

```diff
-    const payload = { declared_amount: '150.00', method: 'mobile_money', transfer_reference: 'PW1R1-IDEM-001' };
+    const payload = { declared_amount: '150.00', method: 'transfer', transfer_reference: 'PW1R1-IDEM-001' };
```

Nothing else changed in the test semantics.

### Product files
`git diff --name-only 888683ba..ec94682 -- backend frontend` is empty.

So:
- **backend product files:** unchanged
- **frontend product files:** unchanged
- **product code:** unchanged

This review therefore remains purely about the browser harness/evidence package.

---

## 3. Independent accounting recomputation

I recomputed directly from the committed raw artifacts:
- `pw1r4b2_full_browser.json`
- `pw1r4b2_full_browser_junit.xml`
- `pw1r4b2_findings_full_162.csv`
- `pw1r4b2_test_list_162.json`

### Recomputed counts
- **162 collected**
- **157 passed**
- **5 failed**
- **0 skipped**
- **0 errors**
- **accounting gap = 0**

### Execution model
From `pw1r4b/playwright.config.js`:
- `workers: 1`
- `retries: 0`

The committed console transcript also begins with:
- `Running 162 tests using 1 worker`

So the candidate’s execution-model claim is consistent with the raw artifacts.

---

## 4. F6a / F6b / F5 failure-set truth

### 4.1 F6a three-node green is genuine
Comparing R4-B vs R4-B2 failure sets from the raw CSVs:

Removed failures (B → B2):
- desktop `phase4-retailer.spec.ts:70`
- tablet `phase4-retailer.spec.ts:70`
- mobile `phase4-retailer.spec.ts:70`

No new failures were added.

This proves the three F6a nodes genuinely turned green.

Because the **only** semantic test change is `mobile_money -> transfer`, and no assertions / control flow / early exits were edited, these greens are authentic and attributable to the payload correction alone.

### 4.2 Remaining red set is exact
The independently recomputed B2 failure set is exactly:
- `phase4-retailer.spec.ts:118` ×3 (desktop/tablet/mobile) → **F6b**
- `phase6-responsive.spec.ts:17` ×1 (mobile) → **F5**
- `phase6-responsive.spec.ts:25` ×1 (mobile) → **F5**

No other failures remain.

This matches the required exact residual red set:
- F6b phase4:118 ×3
- F5 phase6:17/:25 ×2

---

## 5. F6b root cause authenticity

### 5.1 Missing amount is real and still present
In the B2 harness, the failing UI double-click test at `phase4-retailer.spec.ts:118`:
- navigates to `/client/orders/{orderId}/declare`
- does **not** fill `#amount`
- immediately clicks submit twice

The product page `frontend/src/pages/client/DeclarePaymentPage.tsx` requires amount in two separate layers:
- HTML input: `id="amount" ... required`
- submit guard: `if (!orderId || !amount) return;`

Therefore the page fails closed before any valid declaration submission can occur.

### 5.2 Runtime behavior consistent with zero declaration creation
The raw machine artifacts show for all three `:118` nodes:
- failure is **only** `Expected: 1 / Received: 0` at the net-new-declarations assertion
- there is **no** `DECLARATION_METHOD_INVALID` backend 400 at `:118` in B2 (those existed at `:70` in R4-B and disappeared in B2)
- the before/after declaration count delta remained zero in all three viewports

Given:
1. no amount was filled,
2. the form has a required amount field,
3. the React submit handler returns early on empty amount,
4. the net-new declaration count remained zero,

this is consistent with the canonical root cause: **0 declaration POSTs were effectively produced by the UI path under test**, because submission was blocked before a valid declaration request could be issued.

That is a harness defect, not a product regression.

---

## 6. B3 one-line fix authenticity review

The suggested B3 correction is:

```ts
await page.fill('#amount', '150.00');
```

### Authenticity constraints
This line is authentic **only if** it is inserted before the first submit click in the `:118` test, i.e. between these existing lines:

```ts
const submit = page.locator('button[type="submit"]').first();
await submit.click({ timeout: 10000 }).catch(() => {}); // first click
```

That means the correct insertion point is immediately after locating `submit`, before the first click.

### What must remain unchanged
The one-line B3 correction must **not** modify any of the following:
- the immediate double-click sequence
- net-new declaration assertion semantics
- POST/idempotency logic
- error collection logic
- downstream expectations

### Net diff constraint
The authentic B3 correction is a **net +1 line** change only.

### False-green risk from `.catch(...)`
The test currently uses:
- `await submit.click(...).catch(() => {});`
- twice

That alone can hide a click error. However, the test still contains the hard postcondition:

```ts
expect(afterCount - beforeCount).toBe(1);
```

This hard net-new declaration assertion is sufficient to prevent a false-green from the swallowed click exception.

So the `.catch(...)` is not, by itself, disqualifying **as long as** the exact net-new declaration assertion remains unchanged.

Conclusion: **B3 single-line authorization is justified and authenticity-safe** if limited to the amount-fill insertion before the first click and nothing else.

---

## 7. No skip/xfail/retry greenwash; no committed secrets/identity files

Verified:
- no `test.skip`, `.only`, retry-masking, or xfail-style harness greenwash patterns in `pw1r4b/`
- `playwright.config.js` sets `retries: 0`
- no committed `pw1r4b/provision/identities.json`
- scoped `detect-secrets` on the harness/review artifact set is clean
- no product code changes were introduced

Note: repository-wide example/placeholder secret strings exist outside the reviewed delta, and `helpers.ts` contains an expected reference to a **non-committed** `provision/identities.json`. That does not violate this task’s constraints.

---

## 8. Quality

- scoped `detect-secrets`: **clean**
- mojibake / UTF-8 scan on the B2 delta: **0** replacement-character hits
- findings accounting gap: **0**

---

## Final conclusion

This review confirms:
- SHA / parent / branch integrity
- B2 changed only the authorized declaration-method literal
- backend/frontend product files are untouched
- machine accounting is genuinely `162 = 157 passed + 5 failed`, `0 skipped`, `1 worker`, `retries=0`
- the three F6a nodes genuinely turned green
- the remaining red set is exactly F6b×3 + F5×2
- F6b is a real canonical harness defect caused by the missing amount fill, not by product behavior
- the proposed B3 one-line fix is authenticity-safe **and authorized** if inserted before the first submit click with no other edits

**Final verdict: `PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_B2_V1_KILO_FINAL_REVIEW_AND_B3_AUTHORIZATION`**
