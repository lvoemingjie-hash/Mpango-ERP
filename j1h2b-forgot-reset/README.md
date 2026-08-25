# j1h2b-forgot-reset — Frozen Forgot/Reset Playwright Harness

DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R3 (B1-R3: semantic neutrality
canonicalization closure). Harness lineage: B1 `d123e96d` → B1-R1 `e65e9a7f`
→ B1-R2 `cb352079` → B1-R3 (this freeze). Parent chain root:
`8c462170804322d3f73803d8991c00879582e232`.
Protocol source of truth: commit `132cf7edaac5d6c57ebcdc2465334f4aa465aab2`
(`docs/ai-reports/test-plans/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_browser_protocol.md`
and the node inventory CSV, amended in place by B1-R3 for the F3/F4/F5
neutrality columns — see `R4-NEUTRALITY-PROTOCOL-CORRECTION.md`).

**B1-R3 correction (2026-08-25, CTO-ruled):** the original raw-body byte
equality for F3/F4/F5 is **SUPERSEDED** by semantic canonical equality: the
public neutral envelope carries a platform-generic per-request top-level
`timestamp` (not derived from account existence), so byte equality across
distinct requests was over-constrained (V3 STOP evidence `888fd207`). The
superseding contract ignores ONLY the timestamp VALUE via an explicit
sentinel substitution — presence, type, format, the exact top-level key set
`{success,data,message,timestamp}`, the pinned neutral message constant and
the visible copy all remain enforced, and any NEW top-level key
(accountExists/eligible/userId/tenant/request_id probes) must stay RED.
Product timestamp must NOT be deleted, fixed or modified; product paths are
byte-identical to `8c462170`. Full ruling + evidence chain:
`R4-NEUTRALITY-PROTOCOL-CORRECTION.md`.

**Review status (B1-R2):** the Kilo bounded review PASS over B1-R1 is
recorded as `SUPERSEDED_BY_B1_R2_SETTLE_AND_EOL_PORTABILITY_CLOSURE` — its
own findings showed the R12 generic network-quiet wait
(`waitForLoadState('networkidle')`) is only reliable on runtimes without a
persistent WebSocket/HMR connection, while the frozen protocol targets the
Vite dev host; and its CRLF `HOST_LIMITATION` exposed a missing
harness-local EOL contract. The Lubuntu STOP is retained as the DISCOVERY
SOURCE for both issues. Whether the HMR WebSocket necessarily keeps the
network from going quiet is NOT claimed as measured — it is recorded as a
host-mode-dependent risk, which alone disqualifies a generic network-quiet
wait as a settle condition.

**This harness is FROZEN.** It implements and freezes the test harness only.
It must not start any product runtime (backend/frontend/PG/Redis), must not
execute the authoritative browser journey, must not modify product source,
must not merge or deploy. `--list` and pure static helper checks are the only
permitted executions at freeze time. Next step after freeze: Kilo harness
source/authenticity review; the authoritative browser run is a separate,
later authorization.

## Layout

```
j1h2b-forgot-reset/
  .gitattributes                               harness-local EOL contract: '* text=auto eol=lf' (LF on every host; static-gate verified)
  inventory/2026-08-23_..._node_inventory.csv   protocol copy (B1-R3 amended F3/F4/F5 neutrality columns; node ids/classes/order unchanged)
  inventory/node-registry.json                  29-node reconciliation model (24 browser + 5 non-browser)
  playwright.config.ts                          fullyParallel:false, workers:1, retries:0, maxFailures:1, trace/screenshot/video off
  src/env.ts                                    fail-closed env contract (names-only errors)
  src/assertions.ts                             sanitized assertion discipline
  src/token-store.ts                            in-memory journey state (token never persisted; single serial spec scope)
  src/maildir.ts                                F6 surface: task-private maildir reader (memory only)
  src/api-client.ts                             OFFICIAL-API provisioning ONLY (never journey actions)
  src/neutrality-core.ts                        B1-R3 REAL canonicalizer: exact key set, pinned constant, timestamp sentinel, stable sha (dependency-free)
  src/neutrality.ts                             B1-R3 capture: raw body parsed in handler-local scope only, canonical fingerprint stored
  src/leak-scan.ts                              R12 surfaces (findings = surface:field, values withheld)
  src/ui-journey.ts                             rendered-UI journey steps pinned to product anchors
  tests/forgot-reset.spec.ts                    THE single spec: 24 browser nodes, CSV row order, one serial describe
  tools/validate-static.mjs                     static gate 7/7 (CSV parse, ordered --list equality, serial/fail-stop/single-spec/app-settle/EOL/no-sleep + B1-R3 neutrality spec/core contracts, marker scan, UTF-8, executable neutrality check)
  tools/check-neutrality.mjs                    B1-R3 executable neutrality contract check (G1–G6, mutation gates M1–M4/M6)
  tools/scan-artifacts.mjs                      R13 NON-BROWSER post-run evidence scan
  R4-NEUTRALITY-PROTOCOL-CORRECTION.md          B1-R3 protocol correction: raw-byte equality superseded by semantic canonical equality
```

Tree file count: 25 tracked harness files at B1-R3 (22 at B1-R2; B1-R3 adds
`src/neutrality-core.ts`, `tools/check-neutrality.mjs`,
`R4-NEUTRALITY-PROTOCOL-CORRECTION.md` — no file removed, no dependency
added, `package.json`/`pnpm-lock.yaml` untouched).

## Node accounting (24 / 5 / 29)

- **24 browser-authoritative nodes** (spec titles, exact set):
  F1-D, F1-T, F1-M, F2-D, F2-T, F2-M, F3, F4, F5, R1, R2, R3, R4, R5,
  R7-POLICY, R7-POLICY-M, R8, R8-M, R9, R10, R10-M, R11, R12, M1.
- **5 non-browser nodes — never Playwright tests, never browser PASS**:
  - `F6` PRECONDITION — maildir link acquisition via `src/maildir.ts`, in memory.
  - `R6` PRE_GATE_ONLY — natural expiry is backend pre-gate evidence; UI copy equivalence covered by R5.
  - `M2` PRE_GATE_ONLY — partial-copy rollback needs fault injection; browser run covers only the success fan-out (M1).
  - `R13` POSTCOND — `tools/scan-artifacts.mjs` after the authoritative run.
  - `RT0` PROTOCOL_BLOCKER — status `BLOCKED_BY_H2_C` (retailer discovery layer missing, PB-1). **No API bypass of the missing retailer UI is permitted.**

## Journey chain and ordering (B1-R1: single serial spec, fail-stop)

All 24 browser nodes live in ONE spec file — `tests/forgot-reset.spec.ts` —
inside a single outer describe configured `serial`. Registration order MUST
equal the CSV browser row order (actively enforced by
`tools/validate-static.mjs` via ordered `--list` comparison). `workers=1`
keeps the journey in one worker process; in-process state passes only
between these serial tests via `src/token-store.ts`. `maxFailures: 1`
aborts the whole run on the first failing node — any failure is a STOP, no
cascade, no rerun-to-green. There is NO filename-order dependency and NO
fixed sleep anywhere (waits are bounded conditions; the Playwright
fixed-delay API is banned by the static gate):

1. F1*/F2* discovery and form structure (no journey state).
2. F3 provisions A1 (official lifecycle) and X (official create +
   soft-delete) at point of need, submits forgot for A1 — this mail event is
   the journey token source; its fingerprint is the F4/F5 anchor.
3. R1 reads the F3 mail via the maildir helper (F6 surface), then R1–R5.
4. R7* policy stops, R8 consumes the token (link kept for R11), R8-M runs
   its own fresh UI cycle at 390x844 resetting to the SAME P2.
5. R9/R10/R10-M logins, R11 replay + P2 recheck, R12 surface sweep (after
   the B1-R2 application-settle conditions: exact pathname + empty hash +
   interactable #newPassword — never a generic network-quiet wait).
6. M1 provisions W1/W2 owners + shared identity M via the official API
   (same normalized email, SAME initial password both sides, formal admin
   role both sides, gate: M login exposes EXACTLY {W1,W2}); the journey
   itself (forgot → maildir → reset → dual-context R9/R10) is rendered UI
   only.

## Environment contract (fail closed; names-only errors)

| Variable | Used by |
|---|---|
| `J1H2B_BASE_URL` | frontend origin (all UI navigation; maildir links must share this origin) |
| `J1H2B_API_BASE_URL` | backend origin — OFFICIAL-API provisioning only |
| `J1H2B_MAILDIR_ROOT` | task-private maildir root (F6/R8-M/R12/M1 reads) |
| `J1H2B_SIGNUP_COUNTRY` | 2-letter country for official signups |
| `J1H2B_A1_EMAIL` / `_INITIAL_PASSWORD` / `_NEW_PASSWORD` / `_REPLAY_PASSWORD` / `_COMPANY_NAME` | single-copy journey (F3, R7–R12) |
| `J1H2B_UNKNOWN_EMAIL` | F4 never-registered identity (must differ from all provisioned emails) |
| `J1H2B_INELIGIBLE_EMAIL` / `_TEMP_PASSWORD` | F5 fixture (official create + soft-delete; temp password never authenticates) |
| `J1H2B_W1_OWNER_EMAIL` / `_PASSWORD` / `_COMPANY_NAME`, same for W2 | M1 provisioning |
| `J1H2B_M_EMAIL` / `_FULL_NAME` / `_INITIAL_PASSWORD` / `_NEW_PASSWORD` | M1 shared identity |

No credential is ever hardcoded, logged, echoed, screenshotted or written to
an artifact. Passwords must be ≥8 chars and satisfy distinctness rules
(initial ≠ new, new ≠ replay). Missing variables fail the run before any
journey action.

## Maildir contract for the authoritative run

The run launcher dumps the backend non-production email sink under
`J1H2B_MAILDIR_ROOT`. Each email is a UTF-8 text file (flat or classic
maildir new/cur layout) whose content contains the recipient address and the
fragment-only link (`/reset-password#resetToken=…`, `/verify-email#token=…`,
`/setup-credential#setupToken=…`). The operator must set the backend
`PUBLIC_FRONTEND_URL` to the same origin as `J1H2B_BASE_URL`.

## Sanitization discipline

- `expect()` is used ONLY for pure-DOM checks against fixed product strings.
  Anything that could carry a secret (URL, response body, storage value,
  password) is asserted with `assertSan(condition, "field-level message")`
  so failure output can never contain a value.
- F3/F4/F5 keep `(status, message-constant-field, sha256(canonical), canonicalLength)`
  only — the canonicalization replaces the top-level timestamp VALUE with a
  fixed sentinel inside handler-local scope; the raw response body and the
  timestamp value are never retained (task directive #10; B1-R3).
- R12/R13 findings are `surface:field` pairs only (task directive #14).
- trace/screenshot/video are `off`; R13 additionally bans image/video/trace
  artifacts outright.

## Viewport truth (task directive #16)

The three CSV viewports (1280x800, 768x1024, 390x844) are DESKTOP-simulated
viewport sizes. They are usability-structure proxies only and are never
reported as real-device (phone/tablet) results.

## Frozen gates (freeze-time)

```
pnpm install --frozen-lockfile
npx playwright test --list            # exactly 24 titles, in inventory order
node tools/validate-static.mjs        # 6-step static gate (serial/fail-stop/single-spec/app-settle/EOL/no-sleep contracts)
npx tsc --noEmit                      # TypeScript parse
```

Cross-host EOL note: with the harness-local `.gitattributes`
(`* text=auto eol=lf`) a fresh checkout keeps LF on every host, including
Windows with system `core.autocrlf=true` (verified by a fresh-checkout run
at freeze; see FROZEN-REPORT).

The authoritative single run (later, separately authorized) additionally
produces `artifacts/results.json`, `artifacts/results-junit.xml`, and is
followed by `node tools/scan-artifacts.mjs --artifacts-dir artifacts
--secrets-from-env` (R13) plus the 29-node reconciliation accounting
(gap must be 0). Rerun-to-green is prohibited; any failure is a STOP.

## Prohibitions honored in this harness

No SQL, no direct ORM, no hand-written hashes, no debug endpoints, no
database patching, no hardcoded evidence, no API substitution of
forgot/reset journey actions (API appears ONLY in provisioning preconditions
and the explicitly authorized read-only maildir postcondition of F5), no
skip/fixme/only/conditional pass anywhere.
