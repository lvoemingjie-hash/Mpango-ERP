# DC-12R1-MVP-L1-HE2-ET1 — Execution Traps & Fail-Stop Authority Runner

- Date: 2026-08-28 (+08:00); Executor: Zcode
- Task: DC-12R1-MVP-L1-HE2-ET1
- Verification: V1_GOVERNANCE_SOURCE_AND_EXECUTABLE_NEGATIVE_CONTROLS
- Claim ceiling: SOURCE_GATE_PASS_BUT_REMOTE_ENFORCEMENT_NOT_VERIFIED
- Base: 246eb190fc07866f098a380e61ebdc5bd9428a04
- Commit: d1b98a6e7fe2791c09b4e7f5a297ef2e4f2c5038 (then +1 for protocol delta)
- Forbidden: no product/PG/Redis/Playwright/pytest full-suite; no HE2 merge
  config or GitHub required check claim; no H2-C backend or browser PASS claim.

## 1. Hardcoded execution-traps registry (harness-governance/inventory/execution-traps.json)
15 traps, schema/2 with additionalProperties=false, P0/P1 mix all ACTIVE.
Evaluator whitelist in authority_runner.py is the single source of truth
(no shell commands stored anywhere in the registry). Forbidden next phases
gate state-machine progression; stable_exit_code range 10-99 with uniqueness
enforced by the validator structural check.

## 2. Authority runner (harness-governance/validator/authority_runner.py)
Stdlib-only, no shell=True, no concatenated shell strings. State machine
INIT->PREFLIGHT->COLLECT_PROVEN->AUTHORIZED->RUNNING->FINISHED|VOID.
Only the SAME process that completed preflight, exact collection, and the
just-in-time recheck may launch the authority command. Proof binding:
random nonce + candidate SHA + profile SHA + node-manifest SHA + wall-clock
boundary — externally edited JSON cannot resume a run. Failure output: file/
surface/category only (URLs, passwords, tokens, SECRET_KEY, env values
never surfaced).

## 3. Validator integration
- PROTECTED_PATHS extended with the four new artifacts (unwaivable; changes
  require kind=governance protocol delta, recorded as PD-2026-08-28-HE2-ET1
  with base_sha=246eb190).
- _check_execution_traps wired into validate_workspace: RED on registry
  unreadable, profiles unreadable, missing/duplicate trap ids, duplicate
  exit codes, unknown evaluator ids, missing/unparseable negative_control,
  any P0/P1 trap status != ACTIVE, any P0/P1 trap not referenced by any
  authority profile, or any profile referencing an unknown trap.

## 4. Truth fixtures (existing 96 + new 20 = 116 tests)
- tests/test_authority_runner_et1.py: registry health, evaluator whitelist,
  trap VOID behavior, set-drift, empty URL, mixed EOL, lineage confusion,
  packaging mismatch, rolsuper=true negative control (full-run sentinel
  never launched), shell=True absence, non-canonical remote, JIT role
  escalation, forged proof, expired proof, output sanitization, end-to-end
  self-test pass.
- All ET1 mutations + controls added to tests/run_red_mutations.py.
  Total: 51 RED / 9 GREEN. Tree integrity byte-identical before/after.

## 5. Dual autocrlf gate (per task)
- autocrlf=false worktree: CR=0 in execution-traps.json. All gates PASS.
- autocrlf=true worktree: CR=246 in same file (CRLF per .gitattributes
  rule). All gates PASS identically.
- Same self-test, same 51/9 split, same byte-exact tree integrity.
- 116 tests OK in both checkout modes.

## 6. Final gate table
- validator (structural, release): STRUCT=0 PASS, RELEASE=3 BLOCKED
  (pre-existing P0/P1 debt, unchanged by ET1).
- 96 + 20 = 116 unittest tests OK (autocrlf=false + autocrlf=true).
- 51 RED / 9 GREEN mutations (autocrlf=false + autocrlf=true), tree
  byte-identical.
- diff-check, detect-secrets PASS (fixture marker renamed + allowlisted).
- UTF-8/no-BOM/no-NUL/LF verified across the four new artifacts.

## 7. Verdict
**SOURCE_GATE_PASS_BUT_REMOTE_ENFORCEMENT_NOT_VERIFIED**
Push (local==remote) was demonstrated; remote GitHub required-check
configuration is explicitly NOT claimed (deferred to a separate,
authorized step). No product runtime, no PG/Redis/Playwright, no HE2
merge config, no H2-C backend or browser PASS claim.
