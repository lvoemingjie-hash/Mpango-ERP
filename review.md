# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R5-R2-M1 - Formal Controlled Merge Report

AUTHORIZATION_ID: CTO-AUTH-DC12R1-H2C-R6-R5-R2-M1-CONTROLLED-MERGE-2026-09-04
EXECUTOR: Windows Zcode
DATE: 2026-09-04
VERIFICATION_TIER: V3_FORMAL_CONTROLLED_MERGE
CLAIM_CEILING: CONTROLLED_MERGE_ONLY

VERDICT: PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R5_R2_M1_CONTROLLED_MERGE

REMOTE_PUSH_SUCCEEDED=true
REMOTE_ENFORCEMENT_NOT_VERIFIED=true

## 1. Merge identity

- Branch merged into: product-dev-recovered (protected product branch)
- Pushed as: normal push (no force, no force-with-lease, no amend, no rebase)
- Merge commit (MERGE_SHA): bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f
- parent1: 24a28d76d6d9483d8101f8e0f537c148dc262859 (TARGET)
- parent2: ddba2d3eda847f2c15a0f057b5f7ff2f598f38d0 (SOURCE)
- Merge tree: 29a1c39a0b0f8f3e620c4feb4ee6dccb84448d9b == SOURCE tree ==
  PRECOMMIT_INDEX_TREE (proven before and after commit)
- Commit message records: authorization ID, TARGET, SOURCE, KILO, LUBUNTU, M0-R2 report,
  accepted CRITICAL risk, CLAIM_CEILING.
- Ancestry after push: TARGET is an ancestor of MERGE_SHA; SOURCE is an ancestor of MERGE_SHA
  (both verified on the fetched remote ref).

## 2. 72-path inventory (TARGET..SOURCE, unchanged across M0/R1/R2/M1)

Exactly 72 paths: 64 added / 8 modified / 0 deleted / 0 renamed.
- ledger (ai-ledger/product-ai): 24 added
- harness (j1h2c-retailer-recovery): 35 added
- backend product (services): 2 modified; backend test: 1 added
- frontend product (pages/router): 2 added + 2 modified; frontend tests: 1 added + 3 modified
- docs/test-plans: 2 added
Byte identity: staged path set == TARGET..SOURCE name-status inventory;
git diff --cached SOURCE empty; merge tree == SOURCE tree.

## 3. Gate record

Precommit stage (uncommitted merge, fresh TARGET index 24a28d7 up-to-date):
- GitNexus staged detect_changes executed EXACTLY ONCE: changed_files=72 (expected 72),
  changed_symbols=365 (expected 365), risk_level=critical (expected critical),
  affected_count=21. The 21-flow NAME SET is exactly the D1-adjudicated accepted set;
  classification by flow name: 1 DIRECT (Request_password_reset -> RetailerProvisioningError)
  + 11 FILE_LEVEL_OR_TRANSITIVE_ONLY + 9 HARNESS_CONTROL_PLANE_ONLY. This run exhibited the
  registered nondeterminism in its volatile numeric id prefixes (proc_207_verify_email_token /
  proc_206_request_password_res vs proc_206/proc_205 in prior runs) - flow names identical.
  Not rerun. GITNEXUS_RISK=CRITICAL_CTO_ACCEPTED_BY_D1.
- pnpm install --frozen-lockfile GREEN; test:list 15 tests / 1 file GREEN; validate:static
  16/16 GREEN; check:neutrality G1-G6 GREEN; check:runtime-contracts GREEN; typecheck exit 0;
  git diff --cached --check exit 0.
- Read-only detect-secrets on all 72 staged paths: Passed; baseline SHA-256 before == after ==
  f49c86223abc95af12d0f6c60938050a68a84e332a94a444800cd93450bd16bf.
- Encoding on INDEX blobs (all 72): strict UTF-8, no BOM, no NUL, no CR, no U+FFFD, LF-only.
  (Working-tree CRLF on 37 product paths is a Windows autocrlf checkout artifact; harness paths
  are protected by .gitattributes text=auto eol=lf. Committed blobs are LF.)
- Full pre-commit hook set (trailing-whitespace, end-of-file-fixer, check-yaml,
  check-added-large-files, detect-secrets) Passed against the staged file set before commit.
- check:browser-authority intentionally not run before commit.

Formal merge commit: created with normal hooks (no --no-verify). parent1==TARGET,
parent2==SOURCE, merge_tree==PRECOMMIT_INDEX_TREE==SOURCE_TREE, hook_created_paths=0,
hook_rewritten_blobs=0, worktree clean after commit.

Post-commit stage (committed merge object, before push):
- check:browser-authority: BROWSER-AUTHORITY CONTROL-PLANE CONTRACTS PASSED
  (S0 + G + R1-R51, direct-process authority boundary, single canonical repo identity,
  case-insensitive GIT_* sanitization, real fixed Playwright child + exact-401 lifecycle
  preflight + runner-owned host gate + runtime-truth psql/Alembic/Redis probes with sanitized
  full-RED persistence).
- Re-runs on the committed object: test:list 15/1 GREEN; validate:static 16/16 GREEN;
  neutrality G1-G6 GREEN; runtime-contracts GREEN; typecheck exit 0;
  git diff --check HEAD^1..HEAD exit 0.
- Merge tree == SOURCE_TREE reconfirmed; worktree clean.
- Backend/frontend tree identity: HEAD:backend == 86f41b93:backend ==
  b2fc919beeaf33fb53ecfce15507570bc73b9530; HEAD:frontend == 86f41b93:frontend ==
  4526d782de7e77caa39e5c84767be34aa4fb3ebe.

## 4. Evidence reuse (no reruns)

BACKEND_FULL_SUITE_RESULT=REUSED_BY_BYTE_IDENTITY_NOT_RERUN - ef33a882 (3784-node ZERO-RED
backend authority) bound to base 86f41b93; byte identity to the merge proven above.
BROWSER_RUNTIME_RESULT=REUSED_AUTHORITATIVE_EVIDENCE_NOT_RERUN - da6bf9e7
(V4_INDEPENDENT_LINUX_BROWSER_RUNTIME_AUTHORITY, 15 browser + 2 static PASS, junit 15/0/0/0);
da6bf9e7^ == SOURCE; executed tree == SOURCE tree == merge tree.
KILO_SOURCE_TEST_AUTHENTICITY=3db164dd - 3db164dd^ == SOURCE; bounded delta review with
S0+G+R1-R51 contract suite and 7/7 RED mutations (byte-identical restores) binds the same
harness bytes.
M0-R2 two-stage rehearsal: ba65ecf668fdfafae503287f0924fb193c4664d6, parent == SOURCE,
PASS verdict - superseded only as rehearsal, its proofs carry into this merge.
No backend full-suite, PG, Redis, or Playwright was executed in M1.

## 5. Tests

TEST_FILES_ADDED_OR_MODIFIED:
- Added: backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py (11 nodes);
  frontend/src/tests/RetailerPasswordRecoveryDiscovery.test.tsx (16 nodes);
  j1h2c-retailer-recovery/tests/recovery.spec.ts (15 browser journey nodes, harness).
- Modified (additive): frontend/src/tests/Dc12r1S2RetailerPortal.test.tsx (+2);
  frontend/src/tests/PublicPasswordRecoveryInterceptor.test.tsx (+1);
  frontend/src/tests/RetailerCredentialPages.test.tsx (+3).

TEST_NODES_ADDED_OR_CHANGED: 48 (11 backend + 16 frontend new + 6 frontend modified + 15
harness browser); 0 removed.

CODE_PATH_TO_TEST_MATRIX:
1. request_password_reset success path (DB-canonical w into reset-email link):
   test_forgot_password_email_carries_db_canonical_uppercase_code,
   test_forgot_password_email_w_matches_case_insensitive_lookup; end-to-end by Lubuntu
   browser HC03-HC07 over real SMTP transport (reused evidence).
2. build_retailer_reset_link fragment contract (w in fragment only; legacy 2-arg shape
   unchanged): test_reset_link_legacy_shape_unchanged_without_code,
   test_reset_link_with_canonical_code_keeps_fragment_only.
3. _find_verified_retailer_for_wholesaler canonical return, case-insensitive match (single
   caller, reset flow only per D1): covered by the same backend integration nodes.
4. ClientLoginPage recovery discovery entry: HC01 x2, HC02 x2 (new file) + 2 nodes
   (Dc12r1S2RetailerPortal) + browser HC01/HC02.
5. RetailerForgotPasswordPage (new): HC03-HC06, HC04b, M3 + browser HC03-HC06.
6. RetailerResetPasswordPage success path (pre-scrub w read, ^[A-Z0-9]+$ validation,
   in-memory only, /retail/login?w= CTA, legacy neutral guidance): HC12-HC16 + 4 additive
   nodes in modified files + browser HC12-HC16.
7. AppRouter /retailer/forgot-password route: exercised by page mounts and browser navigation.
8. Harness control plane (35 new files): browser-authority S0+G+R1-R51 GREEN on the merged
   committed object; 15/15 + 2/2 independently executed by Lubuntu (reused).

NEGATIVE_AND_FAILURE_PATHS: unknown account neutral; unverified retailer neutral; wrong
supplier neutral; legacy link neutral guidance without portal CTA; malformed/missing w; forged
token neutral failure; transport failure neutral copy; zero POST on invalid email/portal;
exactly-one POST on double click; backend failure windows fw1-fw5; module global state zero;
reset token never in query part.

UNCOVERED_NEW_PATHS: NONE within the 72-path delta at the authorized gate tiers. Runtime
PG/Redis/browser execution is deliberately not rerun; covered by the reused byte-identical
evidence above.

## 6. Scope and non-claims

- REMOTE_PUSH_SUCCEEDED=true: origin/product-dev-recovered == MERGE_SHA verified after fetch.
- REMOTE_ENFORCEMENT_NOT_VERIFIED=true: branch protection / enforcement of the remote was NOT
  verified by this task and is not claimed.
- Kilo/Lubuntu/SOURCE/M0-R2 refs unchanged through the merge (verified post-push).
- No deployment was performed. This report grants no deployment approval.
- Integration worktree/branch/index cleanup occurs in Phase 8; no remote integration ref exists.
