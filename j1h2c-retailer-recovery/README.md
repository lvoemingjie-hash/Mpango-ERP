# J1H2C — Retailer Password-Recovery Discovery Browser Harness (FROZEN)

DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1 frozen Playwright harness for the
retailer password-recovery discovery protocol.

**Status: HARNESS_FROZEN_AWAITING_KILO_REVIEW.** No browser PASS, backend
zero-red, merge-ready or deployment-ready claim is made by this repository.
The authoritative browser run is a later, separately authorized gate.

## Node accounting — 15 browser + 2 static = 17, gap = 0

| Class | Nodes | Meaning |
|---|---|---|
| BROWSER (15) | HC01–HC10, HC12–HC16 | Playwright-authoritative browser nodes, run in inventory order by the single serial spec |
| STATIC (2) | HC11, HC17 | Runtime email checks verified inside the HC07–HC10 node's flow; accounted separately by the run reconciliation — **never reported as a browser PASS** |

The inventory CSV is the byte-identical copy of
`docs/test-plans/2026-08-26_dc12r1_mvp_l1_j1_h2_c_node_inventory.csv`
(blob `caa5340299eb2396aa93e25468b3d6b1a58f83c4`,
SHA-256 `70446a0ad80a48a6ecfcf683a763c971661c28a8caa7c6021701ec65faf243c8`).

## Frozen configuration contract

- `fullyParallel=false`, `workers=1`, `retries=0`, `maxFailures=1` — one
  serial spec, fail-stop on the first failing node.
- Single spec `tests/recovery.spec.ts`, single serial `describe`.
- `trace/screenshot/video = off` (evidence hygiene).
- No `skip`/`fixme`/`only`, no `waitForTimeout`, no fixed sleeps, no
  `networkidle` waits.
- `playwright test --list` works with **zero** environment variables; the
  fallback host `http://j1h2c.invalid.frozen-harness.local` is intentionally
  unresolvable so an accidental run without env fails closed.

## Environment contract (J1H2C_* variables only)

All credentials are read at RUN time from the environment; none are stored
in this repository. Missing variables fail the run with the VARIABLE NAME
only (values are never echoed).

| Variable | Purpose |
|---|---|
| `J1H2C_BASE_URL` | Retailer frontend origin (task loopback) |
| `J1H2C_API_BASE_URL` | Backend origin (task loopback) |
| `J1H2C_MAILDIR_ROOT` | Task-private maildir root for email deliveries |
| `J1H2C_WHOLESALER_CANONICAL_CODE` | The supplier's canonical (DB, uppercase) code |
| `J1H2C_RETAILER_EMAIL` / `J1H2C_RETAILER_CURRENT_PASSWORD` / `J1H2C_RETAILER_NEW_PASSWORD` | HC07 established-retailer protagonist |
| `J1H2C_UNKNOWN_EMAIL` | HC08 never-registered identity |
| `J1H2C_UNVERIFIED_EMAIL` | HC10 registered-but-unverified identity |

## Runtime design contract (implemented, not run)

1. Successful-auth credentials come only from `J1H2C_*` env vars.
2. Provisioning uses only the formal API lifecycle — no SQL, no ORM, no
   debug endpoints, no hand-rolled password hashing.
3. Forgot/reset journey actions execute through the real rendered UI.
4. The maildir reset token lives in single-process memory only
   (`src/token-store.ts`) — never in logs, JSON, JUnit, CSV, trace or
   screenshots.
5. HC07–HC10 keep only canonical fingerprints (exact key set, pinned
   message, timestamp parsed then sentinel-replaced); raw bodies are
   released immediately.
6. HC06 proves one POST for a double click plus a read-only maildir
   post-proof of exactly one new delivery.
7. HC02/HC05 prove zero recovery POSTs.
8. HC11 verifies fragment-only resetToken + public `w` from the HC07 email.
9. HC17 reuses HC07's lowercase caller input and proves the email carries
   the DB-canonical UPPERCASE code.
10. HC12 scans URL, query, storage, console and network metadata for the
    token; `w` may appear only in contract-allowed locations.
11. HC13 lands on `/retail/login?w=<CANONICAL_CODE>`, never `/login`.
12. HC14 builds a legacy link from a real valid token without `w`; the
    reset still succeeds and shows only the neutral supplier guidance.
13. HC15 forges a token at runtime; failure output never includes it.
14. HC04/HC16 use a 390px SIMULATED viewport (explicitly not a real
    device).

## Static tooling

```
pnpm install --frozen-lockfile
pnpm exec playwright test --list      # exactly 15 tests / 1 file
pnpm run validate:static              # 9/9 steps
pnpm run check:neutrality             # G1-G6 executable contract check
pnpm run typecheck                    # tsc --noEmit
pnpm run scan:artifacts               # post-run evidence scan (after a run)
```

This harness references the j1h2b-forgot-reset harness as a design
precedent only; it shares no runtime dependency with it and modifies
nothing outside `j1h2c-retailer-recovery/`.

## Browser authority control plane (B1-R5 — implemented, NOT run)

The R2 independent round exposed external launcher defects (destructive
merge over `owner_email_label`, unprojected materialized input, unbound
SHAs, repeatable preflights/launches, leaky evidence, shell-built commands).
B1-R5 turns those findings into an in-repository, reviewable, falsifiable
execution control plane that any future authorized browser-authority
launcher MUST drive:

- `inventory/browser-authority-contract.schema.json` — frozen contract
  structure (field labels + env variable names only, never values;
  `launch.max_starts` pinned to 1).
- `tools/browser-authority-runner.mjs` — the state machine: field-by-field
  materialization with strict required-field validation (W1/W2 included),
  owner-label overwrite guard, `from`-captured-before-mutation transitions,
  append-only ledger with a value firewall, once-only preflight (any RED or
  exception = immediate VOID, no rerun/no stack swap/no browser after VOID),
  at-most-once browser launch sentinel, contract/input/argv/candidate SHA
  bindings re-verified at launch, argv-array-only subprocess delegation via
  an injected execFile implementation, and labels/booleans/categories/counts
  evidence.
- `tools/check-browser-authority-contracts.mjs`
  (`pnpm run check:browser-authority`) — REALLY imports the runner and proves
  the canonical GREEN path plus 10 defect classes as exact-category RED
  counterexamples (field overwrite, missing owner label, wrong transition
  `from`, unledgered rejection, continue-after-VOID, second preflight,
  second browser, candidate/input/contract SHA drift, argv drift and
  shell-string argv, sensitive value into the ledger), each followed by a
  fresh-instance restore re-GREEN with identical SHA bindings.
- `tools/validate-static.mjs` step [13] anchors the schema, the runner's
  discipline (no shell, argv arrays) and the checker wiring.

**Status: source closure only.** No browser authority run, no launcher
environment rerun, no product runtime was executed in B1-R5. The
authoritative browser journey remains a later, separately authorized gate
driven THROUGH this control plane.
