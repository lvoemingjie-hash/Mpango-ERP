# R4 Protocol Correction — Semantic Neutrality Canonicalization (B1-R3)

Effective date: 2026-08-25. Parent harness: `cb35207969fc1b0c8d8488ac65d75e47fedc3f23`
(B1-R2). This document is the authoritative record that the original
raw-byte neutrality equality for F3/F4/F5 is **SUPERSEDED**. Everything else
in the frozen protocol (`132cf7ed` lineage) is unchanged.

## Evidence chain that motivated the correction

- V2 STOP `3fb185be25b51ae4554c58e8c06c795673c058dd` — launcher provisioning
  input defect (special-use `.invalid` identity domain correctly rejected by
  the product); unrelated to neutrality, retained as history.
- V3 STOP `888fd2072afd77d54881e834c592a4b0f587b271` — F4 first-red with
  `first differing field: bodySha256`. Diagnosis (offline, code-level): the
  public neutral envelope `ForgotPasswordResponse` carries a per-request
  top-level `timestamp` (`schemas/auth_signup.py` default
  `datetime.utcnow`; constructed per call in `api/v1/auth.py`). Two
  semantically identical envelopes are never byte-identical.

## CTO ruling (2026-08-25) — recorded, not re-litigated

1. The V3 F4 raw response difference was real.
2. The difference came solely from the platform-generic, per-request
   top-level `timestamp`.
3. That value is not derived from account existence and is not an account
   enumeration signal.
4. The original contract — full raw JSON byte equality across distinct
   requests — was therefore OVER-CONSTRAINED.
5. Deleting, fixing or altering the product `timestamp` is PROHIBITED.
6. This task may modify only `j1h2b-forgot-reset/**`; product paths stay
   byte-identical to `8c462170804322d3f73803d8991c00879582e232`.

## The superseding neutrality contract (F3/F4/F5)

Implemented by `src/neutrality-core.ts` (the real canonicalizer) and
exercised browser-side via `src/neutrality.ts`; executable without a browser
by `tools/check-neutrality.mjs` (validator step 7).

1. F3, F4 and F5 HTTP status must all be exactly 200.
2. The JSON top-level key set must be EXACTLY `{success, data, message,
   timestamp}` — no missing key, no extra key.
3. `success` must be identical across the three and be `true`.
4. `data` must be identical across the three and be the empty object.
5. `message` must be identical across the three and equal the existing
   product neutral constant
   (`Password reset result is not disclosed through this endpoint.`).
6. `timestamp` must be present in all three, be a string, and parse as a
   valid time.
7. Only the timestamp **value** may be ignored — field presence, type,
   format and every other field remain enforced. The mechanism is an
   explicit top-level timestamp-to-sentinel substitution followed by stable
   serialization; generic key deleters, regex blacklists and recursive
   field ignoring are BANNED (statically banned in the core module and
   refuted by the executable check's added-key probes).
8. After sentinel substitution, SHA-256 and byte length of the stable
   serialization must be pairwise equal across F3/F4/F5.
9. The visible neutral copy must be identical across F3/F4/F5 (unchanged
   from the original protocol).
10. Any NEW top-level key — including `accountExists`, `eligible`,
    `userId`, `tenant` or `request_id` — MUST fail the tests (RED).
11. No claim of exact response-time equality is made; closing a statistical
    timing side channel is explicitly OUT OF SCOPE of this correction.

## What changed in the harness (this task only)

- `src/neutrality-core.ts` (NEW): dependency-free canonicalizer + pinned
  neutral constant + sentinel + fixed-category errors.
- `src/neutrality.ts`: capture now canonicalizes at interception time; the
  raw body exists only in the route handler's local scope and is released
  immediately; comparison surface re-exports the canonicalizer.
- `tests/forgot-reset.spec.ts`: F4 message text updated to "canonical
  response differs"; **F5 gains the canonical-equality assertion against
  F3** (previously F5 compared only status and visible copy).
- `tools/check-neutrality.mjs` (NEW): executable contract check G1–G6
  (mutation truth gates M1–M4, M6).
- `tools/validate-static.mjs`: step [4] extended with the F3/F4/F5 spec
  contracts (F5 canonical equality presence is enforced — mutation gate
  M5) and the core-module contract surface; NEW step [7] runs the
  executable neutrality check.
- `inventory/...node_inventory.csv`: F3/F4/F5 security_assertion /
  expected_http / notes updated to the canonical contract (columns only —
  node ids, classes, counts and order are unchanged: 24 browser + 5
  non-browser).
- `README.md` / `FROZEN-REPORT.md`: B1-R3 appendix documenting the
  supersession and the new file count.

Unchanged: 24 browser + 5 non-browser = 29 node accounting, node names and
CSV order, the single serial spec, workers=1 / retries=0 / maxFailures=1,
trace/screenshot/video off, R12 application-settle conditions, the
`.gitattributes` LF contract, `package.json` and `pnpm-lock.yaml` (no new
dependencies), and every product path.
