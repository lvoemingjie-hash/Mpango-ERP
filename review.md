# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R5-R1-V1 Kilo Bounded Delta Review

Verdict: PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R5_R1_CANDIDATE_KILO_SOURCE_TEST_AUTHENTICITY_APPROVAL

Scope: KILO_SOURCE_TEST_AUTHENTICITY_APPROVAL_ONLY. Verification tier V2_BOUNDED_SOURCE_TEST_AND_FALSIFICATION_AUTHENTICITY. No Lubuntu VM, PostgreSQL, Redis, Alembic, Playwright browser journey, backend full suite, merge, or deployment was started.

- BASE: `e16f39cab7613a32bced21d1f8a5c6be6a54fe18`
- CANDIDATE: `6e96434ff11375d661417b7340dcb37508531f1d` (branch `origin/zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r5-r1-host-authority-2026-09-02`)
- Review worktree: detached clean worktree at `C:\Users\Jeff0\_review_dc12r1_mvp_l1_j1_h2_c_i2_e2_b1_r6_r5_r1_v1_kilo_bounded_review_2026-09-03` (HEAD = CANDIDATE).

## Phase 1 - Proof Gate

- `git fetch --all --prune`: completed (remote `origin`, no drift).
- Remote tip check: `refs/remotes/origin/zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r5-r1-host-authority-2026-09-02 = 6e96434ff11375d661417b7340dcb37508531f1d` = CANDIDATE.
- Parent check: `CANDIDATE^ = e16f39cab7613a32bced21d1f8a5c6be6a54fe18` = BASE.
- `BASE..CANDIDATE`: exactly 1 commit; exactly 9 changed paths:
  1. `ai-ledger/product-ai/2026-09-02_dc12r1_mvp_l1_j1_h2_c_i2_e2_b1_r6_r5_r1_host_authority.md` (A)
  2. `j1h2c-retailer-recovery/README.md` (M)
  3. `j1h2c-retailer-recovery/tools/browser-authority-child.mjs` (M)
  4. `j1h2c-retailer-recovery/tools/browser-authority-entrypoint.mjs` (M)
  5. `j1h2c-retailer-recovery/tools/browser-authority-preflight-helper.mjs` (M)
  6. `j1h2c-retailer-recovery/tools/browser-authority-runner.mjs` (M)
  7. `j1h2c-retailer-recovery/tools/check-browser-authority-contracts.mjs` (M)
  8. `j1h2c-retailer-recovery/tools/host-preflight.mjs` (A)
  9. `j1h2c-retailer-recovery/tools/validate-static.mjs` (M)
- Protected-path zero-change check: product (frontend/backend), database/migrations, profiles, schema, package.json/lockfiles, harness-governance, `.secrets.baseline` - zero occurrences in the change set. Verified.

## Phase 2 - Source Review

1. Runner-owned invocation: `canonicalHostPreflightPath()` derives `tools/host-preflight.mjs` exclusively from the runner's own module location (`fileURLToPath(import.meta.url)`); `#runHostPreflightModule()` executes it via `execFile(process.execPath, [hostPath], ...)` with fixed argv, sanitized (NODE_*/GIT_* stripped) env, private stdin, and a 120 s + 5 s budget. No caller-, env-, or entrypoint-supplied module path exists.
2. Byte authenticity: working bytes are SHA-256 compared against the HEAD committed blob (`git cat-file blob HEAD:<rel>` through `readCommittedBytesGeneric`, GIT_*-stripped env, argv array) before any spawn; mismatch -> `host_preflight_dirty_vs_head` STOPPED.
3. Direct authority policy: `isDirectAuthorityEntrypointProcess()` selects the gate; `parseHostPreflightPayload()` enforces the exact result shape (schema, `provided_by: 'outer_authority_preflight'`, configured flag, transparent-or-configured shapes, ids exactly `PREFLIGHT_HOST_CHECK_IDS` in order, consistent counts, `ok === (red === 0)`); `assertDirectAuthorityHostCoverage()` requires `host_checks_present === 4` (`host_preflight_incomplete` otherwise). Configured-but-empty or forged-marker payloads fail the exact-shape parser.
4. Fail-closed paths, all STOPPED before authorize with `launchStarts` untouched (0): missing configuration / transparent result (`host_preflight_not_configured`), zero checks (`host_preflight_not_configured` / `host_preflight_payload_invalid`), forged or malformed payload (`host_preflight_payload_invalid`), module missing (`host_preflight_module_missing`), dirty bytes (`host_preflight_dirty_vs_head`), crash/kill/timeout/unparseable output (`host_preflight_no_response`), any host RED (folded verdict `ok:false` -> `preflight_red:<category>`). STOPPED-category whitelist prevents generic `preflight_exception` shadowing.
5. spawn discipline on these paths: state machine requires `INIT -> PREFLIGHTED -> AUTHORIZED` before `launch()`; every path above lands STOPPED pre-authorize; contract tests assert `launchStarts === 0`, no finish record, no terminal seal, no sealed evidence JSON line, Playwright `invocation_count = 0`.
6. Owner freshness (R44): `checkOwnerIdentityFresh()` in the preflight helper maps the formal login answer - 401 is the ONLY green; 200 -> `owner_identity_already_established`; 404 -> `owner_identity_lookup_missing`; 422 -> `owner_identity_unprocessable`; 429 -> `owner_identity_rate_limited`; 5xx -> `owner_identity_backend_unavailable`; any other status -> `owner_identity_unexpected_status`. Freshness is provable only through the real HTTP status of the login endpoint.
7. Status-to-RED-category mapping is exact and exhaustive (6 fixed outcomes); no wildcard acceptance; timeout and exception paths fail closed.
8. Caller injection: `preflight(...injected)` with any argument -> rejection record + `preflight_input_rejected` STOPPED; host results enter only via `#runHostPreflightModule()`; the helper independently re-validates the folded host block (fixed ids, exact shape, uniqueness) and the runner re-parses the helper verdict; `preflight_helper_payload_invalid` / `host_preflight_payload_invalid` close all forgery routes observed in tests (committed forged/nonzero/incomplete child variants unreachable, R29).

## Phase 3 - Independent Gates (Kilo-executed, all GREEN)

| Gate | Result |
| --- | --- |
| `pnpm install --frozen-lockfile` | PASS (lockfile up to date, 6 packages) |
| `pnpm run test:list` | PASS - `Total: 15 tests in 1 file`, HC01-HC10 then HC12-HC16, order unchanged |
| `pnpm run validate:static` | PASS - `STATIC GATE PASSED (16/16 steps)` incl. new step 16 (R41-R46 host preflight anchors) |
| `pnpm run check:neutrality` | PASS - G1-G6 all OK |
| `pnpm run check:runtime-contracts` | PASS - A/B/E/C/H/I + B1-R3 truth + B1-R3-R1 + B1-R4 loader |
| `pnpm run check:browser-authority` | PASS - `S0 + G + R1-R46` |
| `pnpm run typecheck` | PASS (exit 0) |
| `git diff --check` | PASS (exit 0) |
| Independent read-only detect-secrets 1.5.0 | PASS - pure scan (no baseline write) of the 3 changed-path roots: 0 findings, 0 new vs baseline; baseline blob untouched |
| Encoding of the 9 committed blobs | PASS - strict UTF-8, no BOM, no NUL, LF-only (byte-level verification of `git cat-file blob` for all 9 files) |
| Candidate tree before == after | PASS - `git status --porcelain` = 0 lines, HEAD = CANDIDATE, `git hash-object --path` == HEAD blob for all 9 changed files |

Evidence class: KILO_INDEPENDENTLY_EXECUTED_EVIDENCE (Windows host; browser-authority checker exercises real node child processes, fixture HTTP servers, and scratch git clones locally; no external runtime required).

## CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS

All in `j1h2c-retailer-recovery/tools/check-browser-authority-contracts.mjs` (changed) plus `validate-static.mjs` step 16:

- R29-R1: direct entrypoint positive control truthfully lands the host-gate VOID; committed forged/nonzero/incomplete child variants unreachable (host gate first; no evidence payload, no seal).
- R43 (unit + real-process): `parsePgBoolean` all display formats and null-on-unparsable; `buildInvitationProbe` + `invitationProbeIsParameterSafe` parameter-safe probe and smuggling refusal; `checkRoleCapabilities` least-privilege matrix and `pg_role_unresolvable`; `checkInvitationAvailability` green/missing/runner-fail; `checkPidOwnership` truncated/stale/owner-mismatch; `runHostPreflight` all-deps-missing (`host_check_missing`), partially-removed, transparent unconfigured mode; REAL module process configured-RED (truncated then stale PID file) with all four ids, fixed categories only, and no sensitive value in stdout/stderr; host blocks fold green/RED through the REAL helper process; ok=false classifies `preflight_red` -> STOPPED spawn=0.
- R44: exact-401 freshness - (a) 401 GREEN into AUTHORIZED + finished flow; (b) 200 RED with exact category `owner_identity_already_established`, STOPPED spawn=0; (c) 404/422/429/500 fixture modes each RED with the exact fixed category, STOPPED spawn=0.
- R45: direct host gate VOIDs - (a) missing host configuration (stderr category exact, void record durable, no finish, no sealed evidence); (b) configured zero-check payload refused by parser; forged hand-off marker refused; zero coverage refused by the direct policy; full coverage accepted; (c) committed module removal -> `host_preflight_module_missing`; (d) committed dirty module bytes -> `host_preflight_dirty_vs_head`.
- R46: end-to-end host gate - (a) REAL module four-check GREEN block accepted by REAL parser, folds green through REAL helper, direct coverage policy accepts; (b) configured all-RED host through a REAL direct entrypoint VOIDs pre-authorize: nonzero exit, `preflight_red` surfaced, no start/finish record, no terminal seal, no sealed evidence line.
- `validate-static.mjs` step 16: anchors for execution root + lifecycle proof + host preflight (HARNESS_ROOT + fixed --config, exact-401 owner freshness, committed-byte proof, exactly-four-checks policy, transparent library mode, semantic booleans, parameter-safe invitations, PID ownership, R41-R46).

## CODE_PATH_TO_TEST_MATRIX

| New/changed code path | Covering tests |
| --- | --- |
| `canonicalHostPreflightPath()` module-relative derivation | R45(c)(d) committed mutation runs; validate-static step 16 |
| `#runHostPreflightModule()` missing module -> `host_preflight_module_missing` | R45(c) |
| `#runHostPreflightModule()` dirty bytes -> `host_preflight_dirty_vs_head` | R45(d) |
| `#runHostPreflightModule()` crash/timeout/unparseable -> `host_preflight_no_response` | R29 committed nonzero/incomplete child variants; R43 real-process RED runs |
| `parseHostPreflightPayload()` exact shape / forged marker / zero-check configured | R45(b); R43 fold payloads re-parsed |
| transparent (unconfigured) result | R43(g) transparent mode; R45(a) direct run VOID `host_preflight_not_configured` |
| configured four-check GREEN fold | R46(a); R43(g)-(h) green fold through REAL helper |
| configured RED fold -> `preflight_red` STOPPED | R46(b); R43(h) |
| `assertDirectAuthorityHostCoverage()` 4-check policy | R45(b) zero refused / full accepted; R46(a) |
| `preflight()` injection rejection -> `preflight_input_rejected` | R26-FAKE; R36 repeat/forged helper |
| helper `host_preflight` block validation (ids/shape/uniqueness) | R46(a); R43(h); R36 forged helper payloads |
| `checkOwnerIdentityFresh()` exact-status mapping | R44(a)(b)(c) |
| host module strict stdin parser + profile-key equality | exercised by every REAL module/child spawn (R43(g), R45, R46); negative parser branches listed under UNCOVERED |
| host module semantic booleans / parameter-safe SQL / PID ownership units | R43 unit block |
| `validate-static` step 16 anchors | validate:static 16/16 |

## NEGATIVE_AND_FAILURE_PATHS

All land STOPPED before authorize with spawn=0 / Playwright invocation=0 and are test-asserted:

- `host_preflight_module_missing` (R45c), `host_preflight_dirty_vs_head` (R45d), `host_preflight_no_response` (R29 variants), `host_preflight_payload_invalid` (R45b forged marker/zero-check; malformed shapes), `host_preflight_not_configured` (R45a; zero checks), `host_preflight_incomplete` (R45b coverage policy), `preflight_red:<host-category>` (R46b, R43h; module RED categories: `pg_unreachable`, `pg_role_unresolvable`, `pg_role_capabilities_invalid`, `pg_invitation_parameterization_invalid`, `pg_invitation_missing`, `redis_unreachable`, `alembic_unresolvable`, `alembic_head_diverged`, `authority_ports_pid_truncated`, `authority_ports_pid_stale`, `authority_ports_owner_mismatch`, `*_descriptor_missing`, `host_check_missing`, `host_check_exception`), `preflight_red:owner_identity_*` (R44b/c: already_established / lookup_missing / unprocessable / rate_limited / backend_unavailable / unexpected_status), `preflight_input_rejected` (R26-FAKE), `preflight_helper_payload_invalid` / `preflight_helper_no_response` (R36), `preflight_helper_dirty_vs_head` (helper byte proof).

## FALSIFICATION_RESULT

Mutations were committed on one-off local temp branches (working tree == temp HEAD, so no dirty-vs-HEAD guard intercepted), then restored to CANDIDATE bytes with hash-object == blob verification and a GREEN gate re-run after each mutation.

- Mutation C (MANDATORY): `browser-authority-preflight-helper.mjs` `checkOwnerIdentityFresh()` degraded to "any non-200 is fresh" (`if (status !== 200) return 'check_green'`). Result: RED, exit 1, 12 failures - ALL inside the R44 block: `R44-owner_login_404/422/429/500: non-401 refused did NOT throw` plus the exact-category and VOID/spawn=0 assertions. Captured precisely by R44's 404/422/429/500 exact status/category assertions; not by dirty-vs-HEAD, anchors, syntax, or unrelated gates. Restore verified byte-identical (`20770fd0c0d0363869cd687ea0e6d186105da97a`), GREEN re-run PASS.
- Mutation A: removed the runner-owned host invocation (`isDirectAuthorityEntrypointProcess()` gate deleted). Result: RED, exit 1, 22 failures starting at `R29-R1: host-gate refusal category exact`, then R45/R46 host-gate assertions. Restore verified (`ed7bce7870aadb2fe09333b7c010ed20c2b88b1a`), GREEN PASS.
- Mutation B: `assertDirectAuthorityHostCoverage()` relaxed to accept zero coverage (`!== 4` -> `> 4`). Result: RED, exit 1, exactly 1 failure: `R45: zero host coverage refused by the direct policy did NOT throw (control plane accepted a defect)`. Restore verified (`ed7bce78...`), GREEN PASS.
- Mutation D: caller injection accepted - `preflight_input_rejected` branch removed and injected caller args folded as the host check block. Result: RED, exit 1, exactly 1 failure: `R26-FAKE: caller ok=true boolean refused threw "preflight_helper_no_response" instead of "preflight_input_rejected"` - the caller-injection-refusal semantic gate. Restore verified (`ed7bce78...`), GREEN PASS.

No mutation produced a false green. No mutation was obscured by an unrelated gate. Temp branches deleted; final tree verified byte-identical to CANDIDATE (9/9 files, `MISMATCH_COUNT=0`, dirty=0).

## UNCOVERED_NEW_PATHS

Not executable within this bounded Windows scope; deferred by design to the Lubuntu host authority gate (out of V2 tier scope):

1. Real-host GREEN of production dependency implementations in `host-preflight.mjs`: `spawnPsql` success against a live PostgreSQL (role capability + invitation availability probes), redis `+PONG` GREEN path, real `alembic heads == current` GREEN, and `ps -p <pid> -ww -o args=` alive-and-token GREEN. Only fixture-RED and injected-double paths run here.
2. `host-preflight.mjs` direct-entrypoint `main()` with a fully GREEN real host (all four production probes green) - not executed; only transparent and all-RED configured runs are proven.
3. Descriptor-missing RED branches (`pg_descriptor_missing`, `redis_descriptor_missing`, `alembic_descriptor_missing`, `authority_ports_descriptor_missing`) are not individually asserted by the checker.
4. The host module's strict stdin parser negative branches (malformed JSON, wrong key set, oversized timeout, values/profile-key mismatch, non-string values -> exit 3) are exercised only implicitly through valid-input spawns; no direct negative-input assertions.
5. The `emit()` value-leak fail-closed guard (exit 3 when a serialized value appears in output) is not directly triggered; R43 asserts the equivalent outcome (no sensitive value in module output) on real RED runs.

None of the above blocks source/test authenticity approval; items 1-2 are exactly what the future Lubuntu host gate owns.

## FULL_SUITE_RESULT=NOT_RUN

Backend/frontend product suites were not executed (bounded tier).

## BROWSER_RUNTIME=NOT_RUN

No Playwright browser journey, no Lubuntu VM, no PG/Redis/Alembic runtime was started (bounded tier).

## Reviewer process incident (contained, no candidate impact)

During the Phase 3 secrets gate, a `detect-secrets scan --baseline .secrets.baseline ...` invocation rewrote the working-tree baseline (tool behavior, reviewer-side). Immediate containment: `git checkout -- .secrets.baseline`, tree restored clean; the gate was re-executed with a pure stdout scan (no baseline flag, output outside the repo): 0 findings in the changed paths, 0 new vs baseline, baseline blob untouched (verified against HEAD blob, LF-only, no BOM/NUL). No secret values were exposed. The candidate itself is unaffected.

## Publication

Report branch `kilo/review/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r5-r1-v1-kilo-bounded-delta-review-2026-09-03` created directly from CANDIDATE `6e96434ff11375d661417b7340dcb37508531f1d`; adds only `review.md` and `findings.csv`. STOP after PASS: no merge, no push automation, no deployment.
