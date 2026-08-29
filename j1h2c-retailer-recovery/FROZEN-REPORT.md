# FROZEN REPORT — J1H2C Retailer Recovery Browser Harness (B1)

- Task: DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1
- Date: 2026-08-27 (+08:00); executor: Zcode
- Verdict: **HARNESS_FROZEN_AWAITING_KILO_H2C_HARNESS_REVIEW**
- Claim ceiling: no browser PASS, no backend zero-red, no merge-ready, no
  deployment-ready.

## Provenance (frozen references)

| Role | SHA |
|---|---|
| BASE (harness branch parent) | `bf20e8c9eae620fcf101ded672dfb0afeab937cb` |
| KILO_REVIEW (R2-R1 bounded delta review, PASS) | `f5fdf187fab88f628a6b2f3aca80d03d3be60054` |
| LUBUNTU_E1 (E1 manifest self-exclusion fix) | `6a62fb19b2973f9565e7bfe93ada133903d693cf` |
| PROTECTED_BASELINE | `2c20d58c88a0a8f5175f4d11041d03b6ca785e06` |

All four verified locally == remote before authoring.

## Frozen artifacts

- Inventory: byte-identical copy of the source CSV
  (`git blob caa5340299eb2396aa93e25468b3d6b1a58f83c4`;
  SHA-256 `70446a0a…faf243c8`). 17 rows x 15 cols; HC01–HC17 ordered
  unique; 15 BROWSER + 2 STATIC execution classes preserved.
- Registry: `inventory/node-registry.json` (15 browser PENDING_AUTHORITATIVE_RUN
  + HC11/HC17 PENDING_RUNTIME_CHECK, never faked as browser PASS).
- Config: single serial spec, fail-stop (maxFailures=1), workers=1,
  retries=0, trace/screenshot/video off, unresolvable fallback host.
- Sources: `src/env.ts` (fail-closed J1H2C_* contract),
  `src/neutrality-core.ts` + `src/neutrality.ts` (canonical fingerprints,
  timestamp sentinel, raw bodies released),
  `src/maildir.ts` (email evidence reader), `src/token-store.ts`
  (single-process memory only), `src/leak-scan.ts` (HC12 multi-surface
  scanner), `src/api-client.ts` (formal-lifecycle provisioning only),
  `src/ui-journey.ts` (real-UI journey actions), `src/reconciliation.ts`
  (15+2=17 gap-0 accounting, nothing pre-written),
  `src/assertions.ts` (field-only failures).
- Spec: `tests/recovery.spec.ts` — 15 browser tests in inventory order
  with explicit per-node contract anchors.
- Tools: `tools/validate-static.mjs` (9 steps),
  `tools/check-neutrality.mjs` (G1–G6 executable contract),
  `tools/scan-artifacts.mjs` (post-run zero-leak scan).

## Static gate results (this freeze)

| Gate | Result |
|---|---|
| `pnpm install --frozen-lockfile` | PASS |
| `playwright test --list` | exactly 15 tests / 1 file, ordered-equal with browser rows |
| `validate:static` | 9/9 steps PASS |
| `check:neutrality` (executable G1–G6) | PASS |
| `tsc --noEmit` | PASS |
| `git diff --check` | clean |
| detect-secrets (scoped pre-commit) | PASS, 0 findings |
| strict UTF-8 / no-BOM / no-NUL / LF | PASS (all harness text files) |
| GitNexus analyze/status | indexed at the branch commit, up-to-date |
| M1–M10 mutation truth gate | each RED on mutation, byte-identical restore (SHA-256), GREEN after restore |
| product tree + j1h2b harness vs BASE | byte-identical (zero diff) |

## Mutation truth gate (static authenticity only)

M1 delete maxFailures; M2 delete serial mode; M3 add a second spec;
M4 swap node order; M5 weaken HC07–HC10 canonical; M6 allow HC02/HC05
POST; M7 weaken token/w leak boundary; M8 delete HC13 canonical portal;
M9 weaken HC14 legacy; M10 delete HC17 DB-canonical-code proof. Each
mutation made the static validator (or executable neutrality check) RED
and was restored to the frozen bytes (SHA-256 equal) before the next
mutation. These are harness static-authenticity evidence ONLY — no
product runtime PASS is claimed.

## Explicit non-claims

- No browser journey was executed; HC01–HC17 remain
  PENDING_AUTHORITATIVE_RUN / PENDING_RUNTIME_CHECK.
- No backend run, no zero-red claim, no Lubuntu claim.
- Not merge-ready, not deployment-ready.
- The 390px checks are simulated viewport checks, not real-device proofs.
