# DC-12R1-MVP-L1-HE2-ET1-R2-R2 — Shared Redis Probe Module-Origin and Cross-Process Byte-Binding Closure

- Date: 2026-08-29 (+08:00); Executor: Zcode
- Task: DC-12R1-MVP-L1-HE2-ET1-R2-R2
- Verification tier: V3_MERGE_CRITICAL_GOVERNANCE_AUTHORITY
- Claim ceiling: CANDIDATE_READY_FOR_KILO_REVIEW_ONLY
- Base: 16ea089b5633b031cf5b133815454f41035223f9
- PRIOR round disposition: the R2-R1 candidate (16ea089b) is marked
  **SUPERSEDED_BY_HE2_ET1_R2_R2_MODULE_ORIGIN_BINDING** — it must not be
  described as Kilo-ready.
- Forbidden: no Kilo start, no merge, no product full-suite, no Playwright,
  no deployment, no rewriting the R2-R1 history branch.

## 1. Confirmed P1 defect

`SHARED_PROBE_MODULE_PRELOAD_INJECTION__AUTHORITY_BYPASS`: both consumers'
`_load_redis_authority()` trusted a fixed `sys.modules` key. With a fake
module planted under `et1_redis_authority`, the REAL runner executed the
fake's `redis_live_check`, an unreachable Redis URL was accepted, and the
probe ended rc=0. The live Redis authority was bypassable by whoever could
preload one import.

## 2. Binding chain now enforced (contract 1–12, all landed)

1. A `sys.modules` entry under the fixed key is NEVER returned: its origin
   is checked against the canonical resolved path first; a foreign origin
   is tamper evidence (`module_preload_detected`) and the entry is evicted.
2. The module is ALWAYS freshly executed from the canonical file's raw
   bytes, on every load, in every consumer.
3. After execution, `__spec__.origin` AND `__file__` must BOTH resolve to
   the exact canonical path; missing spec/loader or any parse failure is
   `module_origin_untrusted`.
4. The runner computes SHA-256 over the shared module's RAW FILE BYTES at
   preflight (`redis_module_raw_digest`) and binds it as the ORIGINAL.
5. The ORIGINAL is bound into the run: it gates preflight, is verified
   again at authorize, and is the reference for all later comparisons.
6. The child independently recomputes the digest from ITS canonical
   resolution inside `pytest_sessionstart` (and again at collection time
   for the proof).
7. The child compares its recomputation against the RUNNER-PROVIDED
   ORIGINAL from `ET1_RUNNER_REDIS_MODULE_SHA` — never a self-comparison —
   and writes its independently recomputed digest into the collect proof.
8. The runner cross-compares the child's reported digest against its own
   ORIGINAL (`module_digest_mismatch`).
9. A just-in-time raw-byte recheck runs immediately before the authority
   launch (`drift_at_launch`), plus one at authorize
   (`drift_at_authorize`).
10. Any origin/path/byte inconsistency lands VOID on disk; the authority
    command is launched ZERO times (sentinel stays 0).
11. Evidence carries ONLY the fixed categories `module_preload_detected /
    module_origin_untrusted / module_bytes_drift / module_digest_missing /
    module_digest_mismatch / drift_at_authorize / drift_at_launch` — never
    paths, URLs, credentials, or environment values.
12. The R2-R1 "runner and child share one module object" cross-process
    claim is RETRACTED in README and code docs and replaced by:
    independently loaded from the same canonical path and bound to the same
    raw-byte SHA-256.

## 3. Truth counterexamples (tests/test_authority_runner_r2r2.py, 10 tests)

- A: preloaded foreign module under the fixed key → detected, evicted, the
  real module executes; a runner binding in that state VOIDs with
  `module_preload_detected`, sentinel 0. Also: the planted fake cannot
  accept an unreachable Redis (`module_preload_detected`, never the fake's
  ok).
- B: REAL child process with `sitecustomize` preloading a fake
  (`PYTHONPATH` injection) → the runner process VOIDs at preflight
  (rc 14, `module_preload_detected`, sentinel 0, VOID published); the child
  runs the same bootstrap and would fail closed identically.
- C: module bytes drift between preflight and the child → child binding
  flags `redis_module:bytes_drift` and recomputes a different digest.
- D: drift between child proof and launch → `drift_at_launch` at RUNNING,
  sentinel 0, command never started.
- E: module `__file__` pointing at another harness file → origin rejected.
- F: missing spec / missing `__file__` → origin untrusted.
- G: child self-reports a forged digest → runner rejects
  (`module_digest_mismatch`); a missing digest is equally rejected.
- H: exact canonical path + exact bytes + fresh PG16/Redis7 → GREEN,
  command exactly once (executed live: RL1 + core chain, §5).

Byte restoration: every case that touches the shared module's bytes
restores them and asserts SHA-256 equality with the snapshot.

## 4. Mutations (tests/et1_r2r2_mutations.py, S221–S228)

S221 key-trust restored · S222 canonical-path validation deleted · S223
runner raw-byte digest deleted · S224 child independent recompute deleted ·
S225 child digest self-compare · S226 runner↔child digest compare deleted ·
S227 pre-launch JIT deleted · S228 launch allowed after drift (self-compare
JIT). Each: patched candidate → probe reports WEAKENED → byte-exact
restore → probe HOLDS again (no PATCH-ANCHOR-ERROR counted as RED; two
stale anchors from the R2-R1 plugin refactor — X06, R215 — were updated to
the current code before the gate ran). Pristine control RS-C01 holds all
eight. Gate total: **84 RED / 9 GREEN**, candidate tree byte-identical.

## 5. Regression + live gates

- 155/155 unittests OK (145 prior + 10 new; the R2-R1 same-object test was
  rewritten to the corrected same-path/same-bytes semantics).
- Mutation gate: 84 RED / 9 GREEN (76 prior preserved + 8 new), tree
  integrity OK.
- runner `--self-test`: OK (now covers preloaded-fake detection and fresh
  canonical load).
- Fresh throwaway PG16 (`he2etr2r2_pg16`, role `r2r2_gate`
  rolsuper=f/rolcreatedb=t) + fresh redis7 (`he2etr2r2_redis7` DB15): live
  redis cases **7/7** (RL1 GREEN full chain rc=0 FINISHED sentinel=1
  collect_spawns=1 — the H case — plus wrong-db, invalid port, DB15
  non-empty, post-preflight disappearance with child fail-closed,
  unreachable, sentinel-reachable) and the 8-case authority core chain
  **8/8**. Runner and child are two REAL processes in every CLI case.
- Dual autocrlf: LF leg all gates; detached CRLF checkout (CR>0) re-ran
  self-test + 155 unittests + 84/9 gate + 7/7 + 8/8 identically; restore
  proven byte-identical (shared tree digest).
- structural validator exit 0; release validator exit 3, attributed ONLY
  to the pre-existing P0/P1 debts (`DEBT-AUTH-CRITICAL-TUPLES`,
  `DEBT-COMMERCE-CRITICAL-TUPLES`).
- `git diff --check` clean; detect-secrets vs baseline: no new findings
  (baseline snapshot-protected); strict UTF-8/no-BOM/no-NUL/no-U+FFFD/
  no-raw-0x97 over all changed files: clean.
- Candidate tree byte-identical before/after every gate run.
- GitNexus: `impact` and `detect_changes` again attempted — `impact` fails
  closed on the known index/CLI storage-version skew (42 vs 40);
  `detect_changes` does not exist in the installed CLI build. Disclosed,
  not silently skipped.

## 6. Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R2_R2_CANDIDATE_READY_FOR_KILO_REVIEW**

STOP. Kilo not started; no merge; R2-R1 history branch untouched.

## 7. Resource cleanup proof

- `docker rm -f -v he2etr2r2_redis7 he2etr2r2_pg16` → both removed with
  anonymous volumes; post-check 0 containers matching, volumes 0.
- Port probes: 127.0.0.1:15450 CLOSED, 127.0.0.1:16383 CLOSED.
- CRLF detached worktree removed; no merge or rehearsal refs created.
