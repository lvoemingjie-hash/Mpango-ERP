# DC-12R1-MVP-L1-HE2-ET1-R1 — End-to-End Authority Execution and Child-Process Proof Closure

- Date: 2026-08-28 (+08:00); Executor: Zcode
- Task: DC-12R1-MVP-L1-HE2-ET1-R1
- Verification: V1_E2E_AUTHORITY_EXECUTION_AND_CHILD_PROCESS_PROOF
- Claim ceiling: SOURCE_GATE_PASS_BUT_REMOTE_ENFORCEMENT_NOT_VERIFIED
- Base: aaff330e395a1ae555672bd86f183d2fd89cae54
- E1 provenance amendment (DC-12R1-MVP-L1-HE2-ET1-R1-E1, 2026-08-28): the
  KILO_STOP reference previously carried here — 26ed3fac9bfcf573e2a483e954d933228094509a —
  is **INVALID_CROSS_TASK_REFERENCE**: 26ed3fac is the H2-C browser-harness
  Kilo STOP and never belonged to the HE2-ET1 chain; it must not be retained
  as a valid approval basis for anything on this task.
  PRIOR_HE2_ET1_KILO_REVIEW=NONE
  NEXT_GATE=KILO_FINAL_CUMULATIVE_BOUNDED_REVIEW
  No citable prior HE2-ET1 Kilo review exists. See §9 for the amendment
  scope (PROVENANCE_CORRECTION_ONLY; functional bytes and verification
  conclusions of 18abc7a2 unchanged).
- Forbidden: no product source, no real full-suite, no PG/Redis/Playwright
  product stacks, no merge/deploy claims. The gate-scoped throwaway PG
  container (`he2et1r1_pg16`, postgres:16-alpine on 127.0.0.1:15445, trust
  auth, role `et1_gate` rolsuper=f rolcreatedb=t, instance superuser
  `et1_admin` for the superuser RED case) was used ONLY so the role traps
  are proven against a real server, not mocked; it was REMOVED after the
  round (cleanup proof in §7) and MUST NOT be reused by any reviewer —
  a reviewer creates its own fresh throwaway PG from scratch.

## 0. Vertical proof first, delivery second (operator directive)

Per the mid-task directive, the five core-chain proofs were closed BEFORE any
ledger/mutation/report expansion. `.verify_e2e.py` (committed as
`harness-governance/tests/run_e2e_core_chain.py`) reached 8/8 PASS before the
remaining deliverables were written.

## 1. E2E core chain (harness-governance/tests/run_e2e_core_chain.py)

- CASE 1 GREEN: clean pipeline → rc=0, state=FINISHED, sentinel_calls=1,
  collect_child_spawns=1, nonce_match=true, 9/9 nodes, child sha_match
  candidate/profile/manifest all true.
- CASE 2 RED superuser URL → rc=10 (TRAP_PG_ROLE_SUPER), VOID, sentinel 0.
- CASE 3 RED empty TEST_DATABASE_URL → rc=11, VOID, sentinel 0.
- CASE 4 RED MPANGO_ALLOW_TEMP_DB_CREATE=0 → rc=12, VOID, sentinel 0.
- CASE 5 RED `--authority` without `--command` → rc=16, VOID, sentinel 0.
- CASE 6 RED child nonce tamper (child env nonce swapped in-flight; child
  proof then carries the tampered value) → TrapFired nonce_mismatch,
  sentinel 0 — the comparison is child-proof vs runner-minted ORIGINAL,
  never self-compare.
- CASE 7 RED collect node drift (expected manifest subset vs real 9-node
  child set) → TRAP_COLLECT_NODE_SET_DRIFT, sentinel 0.
- CASE 8 RED profile file-byte drift between collect and authorize →
  TRAP_SESSIONSTART_DRIFT profile_drift (18), sentinel 0.

## 2. Forced fixes, all landed in runner v2 (validator/authority_runner.py)

1. `--command` is real argv (argparse REMAINDER, list, no shell, no
   concatenated shell strings); `--authority` without a non-empty command
   fails closed via `require_command` (trap 16, VOID).
2. `collect_proven` spawns ONE real `python -m pytest -p
   tests.pytest_et1_collector --collect-only` child (cwd=harness-governance)
   and takes node IDs only from the child proof; count + uniqueness + exact
   set vs the frozen manifest `inventory/et1-node-manifest.txt`.
3. Plugin `pytest_sessionstart` re-verifies, inside the child: live PG role
   (rolsuper=f, rolcreatedb=t), URL presence, capability flag, nonce,
   candidate/profile/manifest binding presence, required nodes. Fail-closed
   `pytest.exit(2)` before collection.
4. `verify_child_proof` compares the child's nonce with the runner-minted
   original via `secrets.compare_digest`; the ET1 self-compare defect is gone
   (mutation X01 proves the gate detects its reintroduction).
5. candidate_sha = live `git rev-parse HEAD` (40/64-hex accepted);
   profile_sha/manifest_sha = SHA-256 over actual file bytes; the child
   recomputes all three live and the runner requires child sha_match=true
   per binding.
6. `load_explicit_profile` loads `--profile` from an explicit path,
   validates the document against `authority-profiles.schema.json`
   (required/additionalProperties/types/pattern/enum recursion), selects
   `--profile-id`, cross-checks required_traps against the registry, and
   rejects a hardcoded `{"mode":"cli"}` document by name.
7. Lineage from live git refs: parent = `git rev-parse HEAD^`, chain base =
   `git rev-parse --verify <baseline>^{commit}`; `eval_git_lineage` traps on
   confusion; no placeholder SHAs anywhere (the ET1 `"a"*40/"b"*40` CLI
   placeholders are gone).
8. Explicit `ALLOWED_TRANSITIONS` map enforces every jump
   (`_to_state`); any trap transitions to VOID before publish; FINISHED and
   VOID are terminal; after any failure no COLLECT/AUTHORIZED/RUNNING state
   is ever persisted.
9. `run()` launches the command exactly once (already-launched counter
   guard); GREEN → FINISHED with rc=0; a non-zero exit returns the code and
   prints `RUN_VERDICT=TEST_RED_REAL_COMMAND_NONZERO` (state stays FINISHED,
   never VOID-classified).
10. `publish()` writes sanitized preflight + state trace (presence, labels,
    counts, booleans only — never values; mutation X09 proves env leaking is
    detected).

## 3. Plugin (harness-governance/tests/pytest_et1_collector.py)

`sessionstart_gate` (pure, probe-targetable) + `pytest_sessionstart` (writes
the sanitized sessionstart proof, exits 2 on any failed binding) +
`pytest_collection_finish` (recomputes live HEAD and profile/manifest file
bytes via git/subprocess-argv, records sha_match per binding, writes the
proof with real sorted node IDs, exits 1 on drift/empty). Proof carries the
schema marker `harness-governance/pytest_et1_collector/2`, which the runner
requires — a proof not written by this plugin can never authorize (mutation
X04).

## 4. Baseline preservation

- 116 unittest tests OK (`python -m unittest discover -s
  harness-governance/tests -p "test_*.py"`), including all 20 ET1 runner
  tests against the preserved public API (`eval_*` signatures, 3-arg
  `AuthorityRunner`, `proof_valid`, `sentinel_calls`).
- Previous 51 RED / 9 GREEN mutation gate: byte-identical PASS before the
  R1 mutations were added; final gate is 66 RED / 9 GREEN (see §5).

## 5. R1 behavioral mutations (tests/et1_e2e_mutations.py) — 15 RED

Patch-and-probe pattern (N20 style): each mutation weakens the candidate
runner/plugin source; an in-process probe must report the gate WEAKENED
(pristine control + sha256+bytes-exact restore + re-probe guard the
pattern; probes stub only the DB-driver seam and never PG/pytest children):

- X01 restore nonce self-compare → nonce-tamper probe escapes.
- X02 collect actual=expected → node-drift probe escapes.
- X03 `--authority` missing command allowed → require_command probe escapes.
- X04 foreign child-proof origin accepted → plugin-marker probe escapes.
- X05 arbitrary state jump allowed → transition-map probe escapes.
- X06 child sessionstart gate disabled → empty-env gate probe escapes.
- X07 duplicate node IDs accepted → duplicate-reason probe escapes.
- X08 hardcoded cli-mode profile accepted → profile-rejection probe escapes.
- X09 publish leaks env values → sanitized-publish probe escapes.
- X10 sentinel launches more than once → exactly-once probe escapes.
- X11 non-zero exit misclassified VOID → FINISHED-verdict probe escapes.
- X12 manifest file-bytes binding dropped → manifest_drift probe escapes.
- X13 proof expiry check dropped → proof_expired probe escapes.
- X14 candidate SHA not live git → candidate_drift probe escapes.
- X15 deleted child plugin accepted → fail-closed probe escapes.
- E2E-GC01 GREEN control: pristine candidate holds ALL probes.

Final gate: `PASS: all 66 mutations produced the intended RED (48 tamper +
1 mode proof + 2 validator-scope + 15 authority-e2e), 9 controls stayed
GREEN, candidate tree byte-identical`.

## 6. Gate table (autocrlf=false primary worktree)

- runner `--self-test`: OK (registry + evaluator traps + transition map +
  cross-process proof + negative control).
- 116 unittest tests: OK.
- mutation gate: 66 RED / 9 GREEN, TREE INTEGRITY OK.
- validator structural: exit 0 PASS. release: exit 3 BLOCKED (pre-existing
  P0/P1 debt DEBT-AUTH-CRITICAL-TUPLES, DEBT-COMMERCE-CRITICAL-TUPLES,
  DEBT-* real-device — unchanged by this round).
- E2E core chain: 8/8 PASS (§1).
- detect-secrets scan over the five new/changed harness files: NONE.
- GitNexus pre-edit impact: attempted (`gitnexus impact ... --repo
  Mpango-ERP` + `context` fallback) — the local index storage version (42)
  is NEWER than the installed CLI build (40), so graph queries fail closed
  ("Trying to read a database file with a different version"). Not
  re-indexed (would downgrade a shared index). Substituted with a git-level
  consumer census: runner/plugin referenced by test_authority_runner_et1.py
  (API contract preserved), run_red_mutations.py + et1_mutations.py
  (registry-level only), harness_governance_validator.py (protected-path +
  mirrored evaluator whitelist — unchanged), README/ledger/profiles (path
  strings only).

## 7. Dual autocrlf gate

- autocrlf=false (this worktree): CR=0 in every touched text file; all
  gates above PASS.
- autocrlf=true detached checkout: detached worktree re-smudged with
  `core.autocrlf=true` (CR>0 in the text sources), same self-test + 116
  unittest + 66 RED / 9 GREEN + 8/8 E2E executed there; restore to
  autocrlf=false proven byte-identical via `git status` clean + blob
  SHA-256 equality (details in the final-gate transcript).

## 8. Delta + scope

- Protocol delta `PD-2026-08-28-HE2-ET1-R1` (kind=governance,
  base_sha=aaff330e) authorizes: validator/, tests/ (runner v2, plugin v2,
  et1_e2e_mutations.py, run_e2e_core_chain.py, node manifest consumer),
  inventory/et1-node-manifest.txt (frozen 9-node manifest), profile path,
  README.
- Claim ceiling unchanged: SOURCE_GATE_PASS_BUT_REMOTE_ENFORCEMENT_NOT_
  VERIFIED. Nothing here claims GitHub required-check enforcement, merge
  rights, or a product PASS.

## 9. E1 amendment — provenance and reviewer-independence closure (2026-08-28)

Round DC-12R1-MVP-L1-HE2-ET1-R1-E1 (branch
`zcode/dc12r1-mvp-l1-he2-et1-r1-e1-provenance-review-independence-2026-08-28`,
base 18abc7a2, VERIFICATION_TIER V1_METADATA_AND_GOVERNANCE_STRUCTURE,
claim ceiling PROVENANCE_CORRECTION_ONLY) corrects exactly two files:

1. this ledger (`ai-ledger/product-ai/2026-08-28_dc12r1_mvp_l1_he2_et1_r1_
   e2e_authority_execution_closure.md`);
2. `harness-governance/inventory/protocol-deltas.json` (R1 approval_ref now
   cites ONLY the DC-12R1-MVP-L1-HE2-ET1-R1 task directive; the unrelated
   26ed3fac mention is removed; new entry PD-2026-08-28-HE2-ET1-R1-E1
   authorizes this metadata round).

Corrected provenance facts (supersede any contradicting line above only in
the metadata sense — functional content is untouched):

- INVALID_CROSS_TASK_REFERENCE: 26ed3fac9bfcf573e2a483e954d933228094509a
  belongs to the H2-C browser harness Kilo STOP, not to HE2-ET1. It must
  not be retained as a valid approval basis anywhere in this chain.
- PRIOR_HE2_ET1_KILO_REVIEW=NONE
- NEXT_GATE=KILO_FINAL_CUMULATIVE_BOUNDED_REVIEW
- The commit under review is 18abc7a256f451ad7fa013e9d34c87e5442d852d; its
  functional bytes and verification conclusions are UNCHANGED by this
  round. No functional gate (E2E core chain, mutation gate, unittest suite)
  was re-run and no functional claim was upgraded: this round ran only the
  metadata/structure gates (JSON parse, structural validator,
  `git diff --check`, detect-secrets, UTF-8/no-BOM) — see §10.

### Container cleanup proof (reviewer independence)

The author-owned gate container was fully removed so no reviewer can or
will reuse the author's environment; a reviewer MUST create its own fresh
throwaway PG from scratch:

- `docker rm -f -v he2et1r1_pg16` → removed (container AND its anonymous
  volumes).
- `docker ps -a --format {{.Names}} | grep he2et1r1` → 0 remaining
  containers.
- `docker volume ls | grep -ci "et1|15445"` → 0 remaining volumes.
- Port probe `127.0.0.1:15445` → CLOSED (freed).

### Final adjudication

PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R1_E1_PROVENANCE_AND_REVIEW_INDEPENDENCE_CLOSURE

After push with local == remote: STOP. Do not start Kilo; the next gate is
the CTO-directed KILO_FINAL_CUMULATIVE_BOUNDED_REVIEW, which starts from a
clean environment with no citable prior HE2-ET1 Kilo review.

## 10. E1 gate transcript (metadata/structure only)

- `git diff --name-only 18abc7a2` over the E1 commit → exactly the two
  authorized files; `harness-governance/validator/authority_runner.py`,
  `harness-governance/README.md`, `harness-governance/inventory/
  et1-node-manifest.txt`, and every test file are byte-identical to
  18abc7a2 (no functional re-run, no claim upgrade).
- JSON parse: protocol-deltas.json loads (7 entries → 8 with the E1 entry).
- Structural validator: exit 0 PASS (structural), release mode exit 3
  BLOCKED unchanged (pre-existing P0/P1 debt).
- `git diff --check 18abc7a2` → no whitespace/conflict-marker errors.
- detect-secrets over both changed files → none.
- UTF-8 decode + no BOM on both changed files → clean.
