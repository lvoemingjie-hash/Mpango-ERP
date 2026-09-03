# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R5-R2-M0-R2 - Two-Stage Controlled Merge-Readiness Rehearsal

AUTHORIZATION_ID: CTO-AUTH-DC12R1-H2C-R6-R5-R2-M0-R2-2026-09-03
EXECUTOR: Windows Zcode
DATE: 2026-09-03
VERIFICATION_TIER: V3_MERGE_CRITICAL_TWO_STAGE_REHEARSAL
CLAIM_CEILING: CONTROLLED_MERGE_READINESS_REHEARSAL_ONLY

VERDICT: PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R5_R2_M0_R2_TWO_STAGE_CONTROLLED_MERGE_READINESS_REHEARSAL

## 1. Nature of this rehearsal

This is a rehearsal only. It proves that TARGET (24a28d76) merges SOURCE (ddba2d3e) cleanly and
that the merged tree passes every gate authorized for local execution. It grants NO formal merge
approval and NO deployment approval. Nothing was merged into any product branch; nothing was
deployed; no product branch was pushed.

GITNEXUS_RISK=CRITICAL_CTO_ACCEPTED_BY_D1. The CRITICAL blast-radius classification was
adjudicated by D1 (1 DIRECT_BEHAVIOR_CHANGE family: request_password_reset; 11
FILE_LEVEL_OR_TRANSITIVE_ONLY; 9 HARNESS_CONTROL_PLANE_ONLY in the preserved 21-item list) and is
explicitly accepted by the CTO for this rehearsal. The R1 ordering conflict
(profile_dirty_vs_head when browser-authority is run against an uncommitted merge whose harness
is newly added) is SUPERSEDED by this CTO-authorized two-stage model: precommit-safe gates run
against the uncommitted merge; the committed-object authority gate (check:browser-authority) runs
only after the temporary local merge commit exists.

## 2. Temporary local merge object (never pushed, will be deleted in Phase 8)

- Temporary merge SHA: a248ef18801cfc6df8358ab90b73cae8dad63440 (local branch
  tmp/dc12r1-m0r2-two-stage-rehearsal-20260903 only)
- Parents: parent1 = 24a28d76d6d9483d8101f8e0f537c148dc262859 (TARGET), parent2 =
  ddba2d3eda847f2c15a0f057b5f7ff2f598f38d0 (SOURCE)
- Merge tree: 29a1c39a0b0f8f3e620c4feb4ee6dccb84448d9b == SOURCE tree == PRECOMMIT_INDEX_TREE
- Hook result: normal hooks ran (no --no-verify). hook_created_paths=0, hook_rewritten_blobs=0
  (tree equality is the proof), working_tree_clean=true after commit.

## 3. Two-stage gate results

Stage A - precommit gates (uncommitted merge, HEAD=TARGET):
- GitNexus: fresh TARGET index (indexed commit 24a28d7 == HEAD, up-to-date); staged
  detect_changes executed EXACTLY ONCE: changed_files=72 (expected 72), changed_symbols=365
  (expected 365), risk_level=critical (expected critical), affected_count=31 - the identical
  id+name process set as the R1 run; every process classified inside the D1-accepted families:
  3 DIRECT (proc_70, proc_71, proc_205 - request_password_reset family), 19
  FILE_LEVEL_OR_TRANSITIVE_ONLY (signup/onboarding and provisioning attribution), 9
  HARNESS_CONTROL_PLANE_ONLY. No new family, no new direct product behavior, no unclassifiable
  process.
- pnpm install --frozen-lockfile: GREEN
- pnpm run test:list: GREEN - 15 tests / 1 file, frozen order (HC01-HC16)
- pnpm run validate:static: GREEN - STATIC GATE PASSED (16/16 steps)
- pnpm run check:neutrality: GREEN - G1-G6
- pnpm run check:runtime-contracts: GREEN - A/B/E/C/H/I + B1-R3 truth + B1-R3-R1 + B1-R4 loader
- pnpm run typecheck: GREEN (tsc --noEmit, exit 0)
- git diff --cached --check: GREEN (exit 0)
- detect-secrets (read-only, hook as configured with .secrets.baseline): Passed on the 72 staged
  merge paths; baseline SHA-256 before == after ==
  f49c86223abc95af12d0f6c60938050a68a84e332a94a444800cd93450bd16bf.
  Executor disclosures: (1) an initial `detect-secrets scan --baseline` invocation REWROTE the
  baseline file; it was immediately restored via git and proven byte-identical (SHA above)
  before proceeding; (2) a separate `pre-commit run detect-secrets --all-files` diagnostic
  surfaced findings only in PRE-EXISTING repository files (docs/ledger/workflows/scripts), ZERO
  of the 72 merge-delta paths - pre-existing repo state, out of R2 scope, no repair attempted.
- Encoding sweep (INDEX blobs = committed bytes, all 72 paths): strict UTF-8, no BOM, no NUL,
  no CR, no U+FFFD, LF-only. Note: working-tree copies of 37 product paths showed CRLF purely
  from Windows core.autocrlf=true checkout; the harness paths are protected by their
  .gitattributes (text=auto eol=lf). The committed blobs are LF and byte-identical to SOURCE.
- check:browser-authority intentionally NOT run in this stage (committed-profile proof cannot be
  valid while HEAD is TARGET).

Stage B - committed-object authority gate (temporary merge committed, HEAD=a248ef18):
- pnpm run check:browser-authority: GREEN - BROWSER-AUTHORITY CONTROL-PLANE CONTRACTS PASSED
  (S0 + G + R1-R51, direct-process authority boundary, single canonical repo identity,
  case-insensitive GIT_* sanitization, real fixed Playwright child at the frozen execution root
  + exact-401 lifecycle preflight + runner-owned host gate + runtime-truth psql/Alembic/Redis
  probes with sanitized full-RED persistence). profile working bytes == HEAD committed blob; no
  profile_dirty_vs_head.
- Invariants after the gate: HEAD == a248ef18..., HEAD tree == 29a1c39a... == SOURCE tree,
  working tree clean (0 entries).

## 4. Evidence reuse (no reruns; byte identity proven)

BACKEND_FULL_SUITE_RESULT=REUSED_BY_BYTE_IDENTITY_NOT_RERUN
- Source evidence: ef33a882 (3784-node backend authority ZERO-RED), bound to base 86f41b93.
- Byte identity re-proven this rehearsal: 86f41b93:backend == ddba2d3e:backend ==
  a248ef18:backend == b2fc919beeaf33fb53ecfce15507570bc73b9530. Frontend likewise:
  4526d782de7e77caa39e5c84767be34aa4fb3ebe across all three commits.

BROWSER_RUNTIME_RESULT=REUSED_AUTHORITATIVE_EVIDENCE_NOT_RERUN
- Source evidence: da6bf9e7 (Lubuntu V4_INDEPENDENT_LINUX_BROWSER_RUNTIME_AUTHORITY, 15 browser
  PASS + 2 static PASS, junit 15/0/0/0). da6bf9e7^ == ddba2d3e; the executed tree is the SOURCE
  tree (29a1c39a) which is exactly the temporary merge tree. No Playwright/PG/Redis was executed
  in this rehearsal.

KILO_SOURCE_TEST_AUTHENTICITY=3db164dd
- 3db164dd^ == ddba2d3e (SOURCE). Kilo bounded delta review artifacts (review.md, findings.csv)
  bind the same candidate; its contract-suite runs (S0+G+R1-R51) and 7/7 RED mutations with
  byte-identical restores were executed against these harness bytes.

## 5. Changed/added tests and code-path-to-test matrix

TEST_FILES_ADDED:
- backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py (11 nodes)
- frontend/src/tests/RetailerPasswordRecoveryDiscovery.test.tsx (16 nodes)
- j1h2c-retailer-recovery/tests/recovery.spec.ts (15 browser journey nodes; harness)

TEST_FILES_MODIFIED (tests only, additive):
- frontend/src/tests/Dc12r1S2RetailerPortal.test.tsx (+2 nodes)
- frontend/src/tests/PublicPasswordRecoveryInterceptor.test.tsx (+1 node)
- frontend/src/tests/RetailerCredentialPages.test.tsx (+3 nodes)

TEST_NODES_ADDED_OR_CHANGED: 11 backend + 16 frontend (new file) + 6 frontend (modified files)
+ 15 harness browser nodes = 48 added/changed test nodes; 0 removed.

CODE_PATH_TO_TEST_MATRIX (direct behavior change and accepted families):
1. request_password_reset success path (canonical w in reset email link; backend):
   test_forgot_password_email_carries_db_canonical_uppercase_code,
   test_forgot_password_email_w_matches_case_insensitive_lookup (backend, real DB + real email
   capture); end-to-end by Lubuntu browser journey HC03-HC07 (real SMTP transport).
2. build_retailer_reset_link fragment contract (w in fragment, never query; legacy 2-arg shape
   unchanged): test_reset_link_legacy_shape_unchanged_without_code,
   test_reset_link_with_canonical_code_keeps_fragment_only (backend).
3. _find_verified_retailer_for_wholesaler canonical return + case-insensitive match: covered by
   the same backend integration tests above (single caller, reset flow only).
4. ClientLoginPage recovery entry (valid/normalized/invalid portal):
   RetailerPasswordRecoveryDiscovery HC01 x2, HC02 x2; Dc12r1S2RetailerPortal +2; browser HC01,
   HC02.
5. RetailerForgotPasswordPage (new page: render, bounded container, client-side validation,
   single POST on double click, neutral transport failure): HC03-HC06, HC04b, M3; browser HC03,
   HC04, HC05, HC06.
6. RetailerResetPasswordPage success path (w pre-scrub read, validated ^[A-Z0-9]+$, in-memory
   only, CTA to /retail/login?w=, legacy neutral guidance): HC12, HC13, HC14, HC14b, HC15, HC16;
   RetailerCredentialPages +3; PublicPasswordRecoveryInterceptor +1; browser HC12-HC16.
7. AppRouter route addition: exercised by every page-level mount test and browser navigation.
8. Harness control plane (35 new files): Kilo-reviewed; browser-authority contracts S0+G+R1-R51
   GREEN at Stage B; 15/15 browser + 2/2 static independently executed by Lubuntu.

NEGATIVE_AND_FAILURE_PATHS: neutral-404 unknown account; unverified retailer neutrality; wrong
supplier neutral; legacy link (no w) neutral guidance with no portal CTA; malformed/missing w;
forged token neutral failure; transport failure neutral copy; zero POST on invalid email /
invalid portal; exactly-one POST on double click; backend failure windows fw1-fw5 (commit
sentinel, unregistered ids, canonical assertion failure, override-installed request failure,
cleanup failure) + module global state zero; reset link never leaks token into query part.

UNCOVERED_NEW_PATHS: NONE. Every product path added or modified by the 72-path delta is covered
by at least one automated test node at one of the three evidence tiers. The only uncovered
surface would be runtime PG/Redis/browser execution, which is deliberately NOT rerun here and is
covered by the reused byte-identical evidence above.

## 6. Authorizations honored

- Backend full suite NOT rerun; PG/Redis NOT executed; Playwright browser NOT executed.
- No product-branch push, no amend/rebase/force-push, no source edits, no test repair, no gate
  bypass. The temporary merge commit exists only on the task-private local branch and will be
  deleted in Phase 8. Only this report branch is pushed.
- detect_changes was executed exactly once in this rehearsal; its result was not rerun to obtain
  a preferable count.

REMOTE_ENFORCEMENT_NOT_VERIFIED=true

## 7. Verdict

PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R5_R2_M0_R2_TWO_STAGE_CONTROLLED_MERGE_READINESS_REHEARSAL

This verdict is a merge-readiness rehearsal result only. It is NOT a formal merge approval and
NOT a deployment approval. The decision to actually merge SOURCE into product-dev-recovered
remains with the CTO.
