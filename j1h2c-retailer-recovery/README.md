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
pnpm run validate:static              # 15/15 steps
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

### B1-R5-R1 — live-binding, terminal-state and audit-ledger truth closure

Over the same control plane, R1 removes every caller self-attestation:

- **Live byte binding** — the protected profile
  (`inventory/browser-authority-profile.json`, reconciled 1:1 with the
  J1H2C_* variables consumed by `src/env.ts`), the task-private contract
  file, the deep-frozen private materialized input and the LIVE
  `git rev-parse HEAD` candidate are all re-read/re-hashed at preflight,
  authorize and launch; any drift lands STOPPED with the true starts count.
- **Terminal-state truth** — INIT, PREFLIGHTED, AUTHORIZED, RUNNING,
  FINISHED, TEST_RED, STOPPED: start sentinel before RUNNING; only
  rc==0 AND complete reconciliation reach FINISHED; a real child failure
  lands TEST_RED (never FINISHED, never VOID); an executor exception
  before an actual start lands STOPPED with starts reverted to truth.
- **Once-only fail-stop** — repeat preflight/authorize/launch persists the
  rejection FIRST, then STOPPED; catching the exception still leaves every
  further surface terminal with starts=0 preserved.
- **Durable audit ledger** — a task-private JSONL sink with
  seq/prev_sha/event_sha hash chain, fsync-per-append, pre-write chain
  re-verification, truncation/tail-rewrite/duplicate-seq fail-closed, a
  mandatory terminal_seal (no seal, no evidence, no PASS), and the same
  values-never firewall.
- **Non-weakenable profile** — caller contracts weaker than the profile are
  refused (`contract_weaker_than_profile`); invented fields are refused
  (`contract_field_unknown_to_profile`); no override path exists.
- Falsification surface extended to R11-R18 (live contract/input/candidate
  drift after authorize, TEST_RED truth, repeat-preflight-then-launch,
  ledger truncation/rewrite/duplicate-seq, per-field profile deletion,
  weakened caller contract), each with exact categories, fresh-instance
  restore re-GREEN and byte-identical file restores.

### B1-R5-R2 — CTO P1 closure (profile override, async child, tamper-proof evidence)

- The production constructor no longer accepts a `profilePath`: the
  protected canonical profile is the only binding source, so a caller
  cannot pair a weaker profile with a weaker contract (R19).
- `launch()` awaits the REAL child outcome — a Promise-returning executor
  settles into FINISHED/TEST_RED after the process ends; async child
  failures are TEST_RED with true starts; synchronous pre-start exceptions
  remain STOPPED with starts=0 (R20).
- `seal()` and `evidence()` force a full on-disk ledger chain
  re-verification FIRST: a record tampered after sealing fails
  `ledger_chain_broken` and can never yield evidence (R21).

### B1-R5-R3 — committed-blob profile binding (dirty-tree closure)

The working-tree profile is only a valid binding source when it EQUALS the
committed blob at the owning repository's live HEAD
(`git cat-file blob HEAD:<relpath>`, argv-array subprocess). The equality is
proven at construction and re-proven at every preflight/authorize/launch
checkpoint; a dirty profile — even paired with a weak contract while HEAD is
unchanged — refuses construction and VOIDs checkpoints with
`profile_dirty_vs_head` (R22).

### B1-R5-R4 — single canonical repository identity (cross-repo closure)

The profile's committed-blob proof and the candidate HEAD resolution share
ONE canonical repository root, derived from the profile's own location. The
caller `repoRoot` must realpath-match that root — a foreign repository
(whatever its HEAD) is refused at construction with `repo_root_mismatch`
(R23) — and every git subprocess runs with all `GIT_*` variables stripped, so
`GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` injections cannot hijack the
profile or candidate identity (R24).

### B1-R5-R4-R1 — case-insensitive GIT_* sanitization

Windows environment blocks are case-insensitive, so filtering only the exact
`GIT_` spelling left `git_dir`/`Git_Work_Tree`-style injections live. The
sanitizer is now case-insensitive (`key.toUpperCase().startsWith('GIT_')`);
R25 proves with a VALID foreign repository — different HEAD, carrying an
identical committed copy of the canonical profile at the same relative path —
that mixed-case injections produce ZERO GIT_* keys in the environment handed
to every git subprocess and cannot substitute the candidate or profile
identity. A case-SENSITIVE filter mutation yields a REAL identity substitution
(the foreign HEAD gets bound, no crash), which R25 reports explicitly.

### B1-R6 — mandatory runner-owned CORS preflight probe

CORS compatibility is now enforced BY the control plane, not by any launcher
check: before preflight is accepted, the runner itself derives the browser
Origin from the BOUND base_url and the target from the BOUND api_base_url,
sends a side-effect-free OPTIONS to `/client/auth/forgot-password` declaring
`POST` + `content-type`, and passes only when the response is 2xx with
`Access-Control-Allow-Origin` EXACTLY equal to the derived Origin. Any
host/scheme/port drift, 4xx/5xx, missing response, timeout, or
missing/wrong allow-origin lands STOPPED before authorize with
launchStarts=0. Omitting the probe, faking a caller `ok=true` check, or
repeating the probe can never bypass it (R26 matrix; evidence carries
categories/booleans/counts only — never URLs or credentials).

### B1-R6-R1 — native CORS transport (ambient fetch substitution closure)

The CORS probe no longer touches `globalThis.fetch` at all: it travels over a
module-private native `node:http`/`node:https` OPTIONS transport with the same
Origin/target/method/headers/timeout/exact-allow-origin criteria. R27 proves —
via a real child process with the ambient fetch poisoned BEFORE the module
import, plus in-process poisoning AFTER it — that an unreachable target really
fails (`cors_probe_no_response`, STOPPED, never PREFLIGHTED/AUTHORIZED,
starts=0), that a correct real server still passes, and that wrong-origin,
HTTP-failure and timeout modes remain fail-closed (their probes share the same
native transport). A transport degraded back to ambient fetch produces a REAL
identity substitution (`BYPASS_ACCEPTED`), which R27 reports as RED.

### B1-R6-R2 - process-isolated CORS probe

The CORS probe no longer runs network I/O in the launcher process. The runner
spawns a fresh `node` child at the canonical helper path with argv-array
discipline, sanitized `NODE_*`/`GIT_*` environment, private stdin input, and a
committed-blob check for the helper bytes. R28 poisons the launcher's
`globalThis.fetch`, `node:http`, and `node:https` bindings, then proves an
unreachable target still fails in the pristine child while a reachable real
server still passes.

### B1-R6-R3/R3-R1 - direct-process authority boundary

Library functional mode is not authority mode. Library-imported `ControlPlane`
instances may exercise materialization, CORS probing, preflight, authorize, and
fake child classification for source tests, but public `authority:true`
elevation is refused and `seal()`/`evidence()` throw
`authority_mode_required`; a fake sync/async executor can reach only a
functional FINISHED/TEST_RED state, never authority evidence.

`tools/browser-authority-entrypoint.mjs` is the only authority evidence path.
It must be started directly as a fresh node process, rejects import/`-e`,
`NODE_OPTIONS`/`NODE_PATH`, any `GIT_*` environment, and dirty critical files
versus HEAD, then executes the full direct chain:
materialize -> process-isolated CORS probe -> preflight -> authorize -> fixed
real child argv -> FINISHED/TEST_RED -> terminal seal -> authority evidence.
The runner mints a module-private Symbol-branded capability only after the
direct command-line/env checks, critical HEAD-blob checks, live candidate
checks, and contract/input/argv/cwd/real-child binding facts are all present.
The capability is never accepted from constructor input, exported objects, env,
argv, or JSON.

### B1-R6-R4 - real Playwright child + runner-owned preflight helper

Two confirmed defects from the prior round are closed:

- `CONFIRMED_DEFECT_1: FIXED_AUTHORITY_CHILD_DOES_NOT_EXECUTE_PLAYWRIGHT` —
  the authority child now REALLY spawns Playwright: it resolves the frozen
  `@playwright/test` CLI from its own install directory (version pinned to
  the frozen lockfile, never PATH/shell/`pnpm exec`/caller paths), spawns it
  as an argv array with `shell: false` and silenced stdio, atomically records
  `playwright_invocation_count = 1` in a create-exclusive marker BEFORE the
  spawn (a second start is refused pre-spawn), awaits the real PID and exit
  without pre-classifying, and maps the 15 materialized values onto the
  EXACT `J1H2C_*` variables of the canonical profile — every other
  `J1H2C_*` spelling and every `NODE_*`/`GIT_*` variable (all letter cases)
  is stripped from the subprocess environment. Sensitive values never enter
  stdout, stderr, or any exception text. The wrapper PID, the Playwright
  PID, the awaited exit and the candidate SHA are cross-bound in the exact
  result payload; `complete = true` requires 15 BROWSER PASS + 2 STATIC
  PASS + gap 0 + PRECONDITION_PASS + fresh artifacts under the unchanged
  candidate + a clean artifact scanner over THIS run's evidence. The child
  never writes PASS artifacts itself.
- `CONFIRMED_DEFECT_2: DIRECT_ENTRYPOINT_PREFLIGHT_USES_CALLER_INDEPENDENT_HARDCODED_TRUE_CHECK`
  — the hardcoded `preflight([{ ok: true, label: 'entrypoint_direct_process' }])`
  is gone. `tools/browser-authority-preflight-helper.mjs` is a
  self-contained, process-isolated helper spawned by the runner (fixed
  module-relative path, committed-blob proof, argv array, sanitized env,
  private stdin). Its checks derive ONLY from the deep-frozen materialized
  values: frontend origin reachable with the real SPA marker; backend
  `/healthz` reachable; maildir exists, is writable and EMPTY; W1/W2
  canonical-format and distinct; owner/unknown/unverified identities
  distinct after normalization; both invitation code/phone pairs present
  and mutually distinct; the forged token reused nowhere; the established
  retailer able to log in through the formal login API; the unverified
  identity still refused. It returns labels, booleans, categories and
  counts only — never a URL, email, password, token or code. Any RED,
  exception, timeout or schema mismatch VOIDs the plane before authorize
  with zero starts; preflight is invocable exactly once and accepts no
  caller input at all (`preflight_input_rejected`).

Post-binding drift of the helper, child, runner, entrypoint or CORS helper
bytes blocks authorize/launch (`authority_module_byte_drift`), on top of the
existing profile/contract/input/candidate live re-binding.

**Task-private execution contract for host-level checks (future Lubuntu
gate).** PG reachability, Redis reachability, Alembic head currency and
authority port ownership are HOST-level checks. They belong to the OUTER
authority preflight that runs in the Lubuntu browser gate, not to this
helper. The interface is fixed and machine-checked: a
`host_preflight` block (`provided_by: 'outer_authority_preflight'`) with
`pg_reachable`, `redis_reachable`, `alembic_head_current`,
`authority_ports_owned` — each `{ ok, category }` — is validated and folded
into the helper verdict; malformed blocks fail closed. The runner never
fabricates host results: runner-driven invocations report
`host_checks_present = 0` transparently.

**Authenticity boundary (honest ceiling).** Source-level closure can prove
internal consistency, freshness, candidate binding and scanner cleanliness;
it cannot prove that a real browser touched a real product. R30-R40
falsify every inconsistent, stale, candidate-mismatched or scanner-dirty
evidence set. Only the separately authorized Lubuntu gate — with the real
PG/Redis/backend/frontend and the outer preflight above — can produce an
authoritative BROWSER PASS verdict. This round claims:
`BROWSER_AUTHORITY_STATUS = NOT_YET_EXECUTABLE`.
