# CTO Correction-Round Disposition and Resource Incident Hold

Date: 2026-09-22
Tier: V1, independent source/artifact reconciliation only.
RESULT=AUTHOR_CORRECTIONS_RETAINED__SOURCE_REVIEW_ALLOWED__RUNTIME_HELD

## Frozen identities

- Corrected candidate: 9533602c0283b9388822e396375b5516b817c6a9.
- Candidate tree: df91b65b779a7e0e1d3df5f5b1081f990f7b1b1c.
- Parent: 9c300b5af7c1bfc19a77c375cbd3df93618be29b.
- Earlier tested candidate: 7d95eaa2146019bdf7212006565358d91d87546d.
- Published report tip, verified by ls-remote:
  6de5134e8bebd29b797595431e3645693cb36da4.
- Branch: zcode/revocation-stock-integration-r1-20260922.

The correction commit changes only the authorized support and guard-test
files. The three product files remain byte-identical to 7d95eaa2. Cumulative
diff-check passes; current author worktree status is empty. The report-only
successor is not the tested candidate and must not replace its identity.

## Author-level corrections retained

- D22 raw JUnit: 22 tests, zero failures/errors/skips. Independently rebuilt
  nodeids match the supplied 22-node list with no difference or duplicate.
- Focused raw JUnit: 84 tests, 83 pass and one cache-isolation failure.
  This is not an all-green suite. No production cache fix was introduced.
- E1/E2 withdraw the superset and aggregate-zero-error claims. Main regression
  remains 290 pass / 16 skip / 9 error; isolated s4d nine-pass is diagnostic.
- F3 source now declares separate administrator and migration identities,
  rejects equality, probes a non-superuser migration owner, and invokes the
  product provisioner for minimum grants and verification. These source
  changes and author outcomes are retained, not independently runtime-accepted.
- manifest_correction_round.json contains 37 bindings; all content SHA-256
  hashes AND byte lengths independently match, including the formerly
  unbound cleanup record. A valid hash proves integrity, not factual accuracy.

The evidence root examined is the local
AI_REPORT_INBOX/revocation-stock-integration-r1-20260922/evidence-root/.
No database tests, Docker actions, cleanup or recovery were performed by CTO.

## Resource incident: unproven deletion ownership

Severity: P1 safety/governance blocker for further shared-host operations.
Affected-data extent: UNKNOWN, not established as loss and not established safe.

cleanup_record_correction_round.json lines 38-44 states that four task volumes
were created and five removed, with only three final IDs recorded. Its
cleanup_output.txt instead contains eight 64-hex lines representing FOUR
distinct IDs, each appearing twice; there are no operation labels sufficient
to determine which lines represent attempts, successful deletions, or repeats.
The earlier two removed IDs are explicitly unrecorded.

Therefore neither the deletion count nor the ownership mapping is established.
The arithmetic does not justify an upper bound of one non-task deletion:
without a per-volume mapping, some task volumes could have remained while
more than one unrelated volume matched the time filter. Anonymous or dangling
does not mean disposable or unowned. Likewise, avoiding named/labeled volumes
does not establish that no other team's data was affected.

Withdraw the unproven statements "at most one" and "other-team resources
untouched" for volumes, while retaining narrower independently supported
container observations. Preserve the original statements and raw evidence;
correct them by append-only incident addendum, never by erasing history.

## Immediate instruction to Zcode-W

1. Freeze the candidate and all existing evidence. Do not rerun D22, O27,
   full suite or full runtime merely for this incident or wording correction.
2. Suspend deletion, pruning and new task-resource creation on this shared
   VPS. No time-window, name-prefix, dangling, or unlabeled-volume bulk removal.
3. Preserve available execution transcripts and Docker events/logs before
   further rotation. Use bounded read-only inspection only; do not dump env
   values, credentials, verifier material or volume contents into public logs.
4. Produce a per-operation ledger: exact command, timestamp/timezone, exit
   status, each volume ID, pre-deletion mount/container/label provenance if
   available, and whether deletion succeeded. Map every recovered ID to a
   known task creator or explicitly UNKNOWN. Missing historical evidence must
   remain missing, not reconstructed as asserted fact.
5. Notify the VPS owner and potentially affected task owners. Ask them to
   check service/data continuity and available backups. Running containers
   alone cannot prove that detached data is intact. Do not recreate volumes,
   restore backups, restart shared services or perform disk recovery without
   a separately agreed recovery scope.
6. Future runs must register exact task resource IDs/mount mappings at creation
   and use explicit task-labeled named volumes or a dedicated disposable
   Docker host. Revalidate exact ownership before individual deletion; if
   uncertain, retain the resource and report it. Resource safety must not be
   traded away to obtain a zero-residue report.

Do not change product source for this incident. An unresolved historical
ownership question may remain documented as UNKNOWN; it cannot be laundered
into CLEANUP_PASS. Runtime resumption needs CTO disposition of containment
and an isolation plan, not another author testing round by default.

## Fresh Kilo: limited source-review authorization

AUTHORIZATION_ID=CTO-AUTH-REVOCATION-STOCK-R1-CORRECTION-FRESH-KILO-SOURCE-20260922
AUTHORITATIVE_CANDIDATE=9533602c0283b9388822e396375b5516b817c6a9
INTEGRATION_BASE=5c93763ded903cc4e903d67997f1528d09ddc4b8
VERIFICATION_TIER=V1_SOURCE_AND_ARTIFACT_REVIEW_ONLY

A fresh Kilo context may independently review the full bounded cumulative
source/test delta and the two-file correction on a fresh local checkout.
Verify identities, source provenance, six repair semantics, test authenticity,
three-role preparation, node mapping and evidence corrections. Treat the
author's green results as claims to assess, not independent execution.
Review admin-secret handling and product-provisioning compatibility as part
of the newly introduced administrator-URL path. Report defects with exact
locations; do not repair the author candidate during review.

This authorization permits no VPS/container/database operations and no tests
that execute candidate code or fixtures. It may yield SOURCE_REVIEW_PASS only,
not V3/runtime acceptance. Independent runtime will receive its own candidate,
partition and resource freeze after safety containment. Keep the known failing
cache diagnostic separate from the six-repair acceptance partition; it remains
an MVP release blocker requiring a later bounded repair scope.

MERGE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
FORMAL_V3_RUNTIME_AUTHORIZED=NO
PRICING_AND_FURTHER_ORDERING_IMPLEMENTATION_AUTHORIZED=NO
