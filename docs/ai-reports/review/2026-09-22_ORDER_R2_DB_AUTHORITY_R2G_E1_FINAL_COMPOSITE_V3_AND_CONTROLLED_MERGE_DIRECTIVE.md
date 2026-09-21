# ORDER R2 + DB Authority R2G-E1 Final Composite V3 and Controlled Merge Directive

Date: 2026-09-22

## Current truth

```text
FINAL_CANDIDATE=5c93763ded903cc4e903d67997f1528d09ddc4b8
FINAL_CANDIDATE_TREE=e6444326ac2c023b610fc1d796b595439fcf0c22
PUBLISHED_CANDIDATE_BRANCH=codex/order-r2-dbauth-r2g-e1-final-candidate-20260922
FROZEN_CONTRACT_TARGET=codex/order-state-r2-e1-source-revision-f1-f3-20260919
FROZEN_CONTRACT_TARGET_SHA=2df6a3bfe8a7975b05f882cda19a6ac390b7a978
TARGET_TO_CANDIDATE_COMMITS=40
TARGET_TO_CANDIDATE_MERGE_COMMITS=0
FAST_FORWARD_ELIGIBLE=YES
```

## CTO final disposition

```text
PASS_FOR_CTO_ORDER_R2_DB_AUTHORITY_R2G_E1_FINAL_COMPOSITE_V3_RECONCILIATION
CANDIDATE_PUBLICATION=PASS
TARGET_BRANCH_FREEZE=PASS
CANDIDATE_MERGE_READINESS=READY_FOR_EXACT_FAST_FORWARD
MERGE_AUTHORIZED=YES_EXACT_FAST_FORWARD_ONLY
DEPLOYMENT_AUTHORIZED=NO
PRICING_AND_FURTHER_ORDERING_AUTHORIZED=NO_UNTIL_POST_MERGE_IDENTITY_RECEIPT
```

No open product or test finding blocks the exact frozen candidate. This is a
composite V3 conclusion, not a claim that one uninterrupted runtime envelope ran
every gate on the final commit.

The composite conclusion is valid because later successors changed only the test
trust and fixture layer while preserving the product bytes exercised by the
accepted runtime evidence. The final R2G-E1 Fresh Kilo round then independently
closed the remaining D-partition and reporting-identity conservation surface on
the final candidate.

## Evidence reconciliation

| Evidence layer | Accepted fact | Role in final disposition |
|---|---|---|
| Order R2 E1 independent V3 | Candidate `2df6a3bf`; both authorized partitions passed; F1-F3 source findings closed | Establishes the accepted Order R2 contract base |
| Combined R4 runtime | S `243 passed / 21 skipped`; entrypoint refusal, five-stage setup, backend/readiness/reporting checks passed; O `27/27`; D `21/22` | Establishes runtime behavior for the frozen product bytes and identifies the single D fixture gap |
| Grantor-aware targeted closures | The membership test and fail-closed restore paths were independently falsified and restored; product source remained byte-identical | Converts the R4 D failure from an unresolved test gap into a bounded fixture-trust problem |
| R2G-E1 Fresh Kilo R1 | Formal D `22/22` in original order; roles-present, container-only, both-absent, body-failure, and restore-failure scenarios all conserved the recorded identity after normal teardown or independent rescue; `r2d_probe_%` residue zero | Closes the final D and reporting-identity conservation gap on `5c93763d` |
| Final drift check | From product evidence base `b0278dcc` to final candidate, only three test files changed; critical runtime product blobs remained identical | Allows the accepted runtime evidence to bind to the final candidate without another full runtime envelope |
| Candidate publication | Local, tracking, and `ls-remote` all equal `5c93763d`; complete-history bundle verified; target remained `2df6a3bf` | Makes the exact reviewed object remotely consumable and freezes the merge boundary |

## Accepted limitations

- `FULL_SUITE_RESULT=NOT_RUN_THIS_ROUND`
- `BROWSER_RUNTIME=NOT_RUN_THIS_ROUND`
- The final conclusion composes accepted evidence; it does not relabel earlier
  stopped envelopes as passes.
- The deployment scripts `deploy_vps.sh` and `reset-staging.sh` remain outside the
  accepted runtime contract and remain deployment blockers.
- A production Compose replacement remains a separately authorized task.
- PostgreSQL image digest pinning remains open.
- No deployment or production-data operation is authorized by this document.

## Controlled fast-forward merge authorization

```text
AUTHORIZATION_ID=CTO-AUTH-ORDER-R2-DB-AUTHORITY-R2G-E1-CONTROLLED-FAST-FORWARD-MERGE-2026-09-22
TASK_ID=ORDER_R2_DB_AUTHORITY_R2G_E1_CONTROLLED_FAST_FORWARD_MERGE
CHANGE_CLASS=GIT_IDENTITY_PRESERVING_FAST_FORWARD
RISK_TIER=HIGH
VERIFICATION_TIER=V1_POST_V3_IDENTITY_AND_HISTORY
CLAIM_CEILING=EXACT_FAST_FORWARD_AND_POST_MERGE_IDENTITY_RECEIPT_ONLY
SOURCE_BRANCH=codex/order-r2-dbauth-r2g-e1-final-candidate-20260922
SOURCE_SHA=5c93763ded903cc4e903d67997f1528d09ddc4b8
SOURCE_TREE=e6444326ac2c023b610fc1d796b595439fcf0c22
TARGET_BRANCH=codex/order-state-r2-e1-source-revision-f1-f3-20260919
EXPECTED_TARGET_BEFORE=2df6a3bfe8a7975b05f882cda19a6ac390b7a978
EXPECTED_TARGET_AFTER=5c93763ded903cc4e903d67997f1528d09ddc4b8
EXPECTED_TARGET_TREE_AFTER=e6444326ac2c023b610fc1d796b595439fcf0c22
MERGE_AUTHORIZED=YES_EXACT_FAST_FORWARD_ONLY
FORCE_PUSH_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
```

### Required execution

1. Use a fresh isolated clone or worktree and run `git fetch --all --prune`.
2. Re-read source and target with `git ls-remote`; both must equal the frozen
   values above before any target update.
3. Verify the target is an ancestor of the source, the left/right count is
   `0 40`, and the range contains zero merge commits.
4. Update the target by strict fast-forward only. A direct compare-and-update push
   or local `git merge --ff-only` followed by a normal push is acceptable.
5. Do not create a merge commit, rebase, cherry-pick, amend, squash, resolve a
   conflict, or modify any file.
6. Re-fetch after the push and prove local target, tracking target, and
   `git ls-remote` all equal the expected target-after SHA.
7. Prove the resulting target tree equals the expected candidate tree and run
   `git fsck --full --strict`, `git diff --check`, and a clean-worktree check.
8. Do not rerun product tests solely for this identity-preserving branch move.
   If any object or tree differs, stop; the V3 inheritance no longer applies.

### Stop conditions

Stop without moving the target if any of the following occurs:

- the remote target is no longer `2df6a3bf...`;
- the remote source is not `5c93763d...`;
- the source tree is not `e6444326...`;
- the target is not an ancestor of the source;
- the update would require a force push, merge commit, conflict resolution,
  cherry-pick, rebase, or any content change;
- branch protection or remote policy rejects the normal fast-forward push.

### Required receipt

Publish a report-only receipt recording:

- source and target `ls-remote` values before and after;
- the exact push command and exit code;
- target tree after the update;
- `fsck`, `diff --check`, and clean-worktree results;
- confirmation that the candidate branch remained unchanged;
- `MERGE_RESULT=PASS_EXACT_FAST_FORWARD` or a fail-closed stop result.

Do not add the receipt to the contract target, because that would change the
accepted tree. Add it only to a report branch parented to the candidate.

## Work sequencing after the merge receipt

After `MERGE_RESULT=PASS_EXACT_FAST_FORWARD` is independently reconciled:

1. close the Order R2 + DB-authority integration line;
2. keep deployment closed until its separate blockers are resolved;
3. return to CTO for a new, separately scoped pricing and downstream ordering
   authorization;
4. do not combine pricing or new ordering semantics with deployment repair.

The business decisions already frozen for KE/UG, currency precision, retention,
multi-person refund separation, and first-release exclusions remain inputs to the
next product-planning gate; they are not modified by this merge authorization.
