# CTO Revocation / Stock R1 Candidate Review

Date: 2026-09-22
Tier: V1 independent source and published-artifact review; no runtime rerun.
RESULT=NEED_CHANGES__AUTHOR_HANDOFF_AND_TOPOLOGY_NOT_READY_FOR_FRESH_KILO_V3

## Verified identity and retained results

- Product/test candidate: 7d95eaa2146019bdf7212006565358d91d87546d.
- Tree: b2b666e38154040076a741b76b20162749de5336.
- Parent: 95c044ec2e729addff101002cb2c2fc615847708; base: 5c93763ded903cc4e903d67997f1528d09ddc4b8.
- Cumulative candidate diff is exactly the authorized eight source/test paths.
- Tenant/auth blobs equal the historical repair blobs; inventory delta is
  exactly one populate_existing option. No wholesale inventory replacement.
- Published branch tip at review time is 9c300b5af7c1bfc19a77c375cbd3df93618be29b,
  a report-only successor of the candidate. It is not the tested candidate.
- Author worktree currently has untracked _task_tmp/. The staged/tracked
  candidate comparison is clean; no claim of current whole-worktree cleanliness
  is made by this review. That directory was not inspected for private values.
- The author JUnit files parse successfully: focused 83 = 82 pass + 1 fail;
  main regression 315 = 290 pass + 16 skip + 9 error; isolated s4d = 9 pass.
- Published focused-node results and mutation log tails support the six repair
  outcomes. This is artifact verification, not an independent runtime PASS.

## F1 / P1: D22 regression coverage is absent, not a superset

The report's section 6 describes an equivalent full superset. Independent
comparison of original nodeids against junit_regression.xml finds:

| Partition | Passed | Skipped | Not collected |
| --- | ---: | ---: | ---: |
| O27 | 27 | 0 | 0 |
| D22 | 0 | 7 | 15 |

The seven skipped nodes are the 039 non-finite migration preflight and six
combined authority lifecycle/ownership nodes. All fifteen readiness-gate
nodes were not collected. The later accepted R2G-E1-R1 D JUnit has the same
22-node set and independently confirms this coverage gap.

CTO recovered the historical frozen lists; do not ask the author to invent
them. Adjacent historical-nodes-O.txt and historical-nodes-D.txt are copied
from verified bundle commit cb05410cd7f88a2125e92bb74111a4cac18ec563:

- report/nodes-O.txt Git blob OID: bc84c18019bfefa4a4740f6b241ca21f9f5b1bfb.
- report/nodes-D.txt Git blob OID: b2bbc42fb6a2e45e6366307caf806f3ec9d449f7.
- Source bundle: r1r7r2r1r1-v3-targeted-closure-kilo-report.bundle, verified
  locally and fetched without checking out or changing the author's tree.
- The later R2G-E1-R1 execution XML used for set cross-check is the local
  order_r2_r2g_e1_kilo_r1_pass_evidence_20260922/junit-D.xml.gz.

These files recover historical reference selections, not a claim that they
are the exact byte order of every later envelope. A new independent run must
collect and freeze its own exact order before execution, without silently
dropping, reordering after failure, or weakening nodes.

## F2 / P1: distinct regression topologies cannot erase errors

Report section 6's aggregate "299 PASS + 16 SKIP + 0 FAIL/ERROR" is not the
result of the primary envelope. That envelope has nine setup errors. A
separate database with changed function ownership yielded nine passes but
does not validate those tests under the accepted DB-authority topology.

Keep both outcomes, commands, topology differences and original JUnit.
Append a correction withdrawing the aggregate zero-error claim. The
unchanged s4d fixture source supports an inherited-harness hypothesis, but
the package does not provide a same-environment BASE-versus-candidate run
that establishes the report's full PRE_EXISTING classification.

Do not repair shared s4d conftest or transfer public object ownership in the
main integration topology. Its isolated result remains diagnostic only.
Independent validation may compare BASE/candidate if classification remains
needed; it must not turn diagnostic success into production-topology proof.

## F3 / P1: preparation conflates administrator and migration authority

Author preflight explicitly says migration identity equals container
POSTGRES_USER. Support lines 405-416 and 531-534 enforce that binding. This
is not evidence for administrator != migration authority != application
runtime in the accepted setup contract. Reporting identity is additional,
not a substitute for a separate administrator. Live migration role
attributes proving least privilege are not published in this package.

Within the already authorized support/guard files, adapt task preparation
to consume the accepted product provisioning contract and bind distinct
administrator, migration and app identities to the same task cluster and
application DB. Verify live role attributes; migration must not be the
container bootstrap administrator, and app must retain its current
non-privileged/no-membership/no-public-CREATE contract. Do not modify product
bootstrap, provisioner, migrations, Compose or readiness gate.

Avoid another provisioning framework: use the existing product preparation
sequence, with narrowly adapted checks and explicit stage credentials.
Record any resulting successor SHA and rerun only affected author tests
and missing bounded regressions; no full-runtime restart is ordered here.

## F4 / MVP release blocker: cache diagnostic proves cross-tenant response

The focused JUnit's sole failure is
test_r1_red_diagnostic_sku_list_cache_not_tenant_scoped. It reports tenant B
receiving tenant A's SKU id under identical query parameters. Candidate
backend/api/v1/skus.py:40-55 has a cache key without tenant identity.

This is not introduced by the three repaired product files, and this order
does NOT authorize its repair. It does block a general tenant-isolation or
MVP release claim. Preserve it as a separate known-failing diagnostic; do
not hide it with xfail, disable Redis, weaken assertions or call the full
83-node run green. A later CTO-owned cache-isolation implementation scope
is required before MVP exposure.

The legacy duplicate-return node's observed PASS is retained as an
observation, not an independent closure or a repair attributed to this port.

## F5 / P2: publication count and binding gap

The current manifest has 22 entries, not the stated 23. All 22 content
SHA-256 and byte counts independently match their files. cleanup_record.json
is present but unbound; manifest.json itself is also outside its own list
(self-exclusion is correct). Bind cleanup with an append-only corrected
manifest or separate sidecar; retain the old manifest and explain supersession.
Do not regenerate tests for this packaging correction.

M3's log contains six failed nodes: five mutation witnesses plus the
baseline cache failure. The report distinguishes them; preserve that
distinction in machine declarations instead of claiming five total failures.
The published mutation logs alone do not independently prove every asserted
pre/post blob restoration. Supply existing commands/restoration records if
available, otherwise mark that part author-asserted for Kilo to reproduce.

## Bounded next instruction to Zcode-W

1. Freeze the existing candidate and preserve all original artifacts.
2. Append the corrections for F1/F2/F5; reference the supplied node lists.
3. Correct only the test-support topology binding described in F3, with
   impact analysis before symbol edits and normal successor commits.
4. Demonstrate affected tests under accepted role separation; explicitly
   opt in to the D22 temporary-DB tests and pre-check source DB name/port.
   O27 already maps to PASS in this package; do not rerun it solely to fix
   documentation. A new source successor still needs impact-based regression.
5. Keep primary and diagnostic envelopes separate. If a test needs broader
   source changes, stop and request a bounded scope amendment, not elevated
   runtime grants. Do not broaden into cache, pricing or ordering here.
6. Finalize report/evidence, scan all published/decompressed material, then
   generate and verify the exact inventory. Record candidate vs report tip.
   Do not claim all files are clean while untracked task files remain;
   classify private task artifacts without publishing their contents.
7. Return to CTO candidate freeze. Fresh Kilo V3 is not unlocked yet.

No PG/Redis tests, container changes, product edits or deployment were
performed during this CTO review. The report and recovered selections are
the only new files. Source acceptance is bounded; final release is not granted.

MERGE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
PRICING_AND_FURTHER_ORDERING_IMPLEMENTATION_AUTHORIZED=NO
NEXT_GATE=CTO_REVOCATION_STOCK_R1_CORRECTED_CANDIDATE_FREEZE
