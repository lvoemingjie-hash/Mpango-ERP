# Aborted attempts (infrastructure / spec-side defects; zero product-assertion failures)

- attempt1: chromium headless-shell v1217 executable missing (npm package vs npx cache build
  mismatch). J01 never launched; zero journeys executed.
- attempt2: spec typo `randomUUID().hex` (Node crypto UUID is a string). J01-J06 had already
  passed for real; J07 crashed before touching the page; zero assertion failures.
- attempt3: spec test-data defect — J03 restricted the invitation to a fixed phone, so the
  product correctly failed closed on the mismatched registration phone (400 + neutral UI).
  The product behaved correctly; the spec data was wrong.
- attempt4: J15 double-click method — the second sequential click was blocked by the product's
  own submit-lock (button disabled), which is the protection under test. Switched to an
  OS-level dblclick(); passed.

The final run recorded in ../authoritative_playwright.json and ../authoritative_junit.xml is
the single authoritative journey run: 18/18 passed, workers=1, retries=0.
