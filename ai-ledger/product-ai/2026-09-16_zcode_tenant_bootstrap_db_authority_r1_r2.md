# ZCode-W R1-R2 — Tenant bootstrap DB authority: first-deployment binding, credential hygiene, public-CREATE precondition

- DATE=2026-09-16
- AUTHORIZATION_ID=CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R2-2026-09-16
- BASE=5ee42a982a9d6132b4557fe4cd9f945334a608f6 (R1-R1 manifest commit)
- EXECUTOR=ZCode-W
- VERIFICATION_TIER=V3_MERGE_CRITICAL_DATA_INTEGRITY_SECURITY
- CLAIM_CEILING=CORRECTED_SOURCE_CANDIDATE_ONLY
- NEXT_GATE=`KILO_TENANT_BOOTSTRAP_DB_AUTHORITY_SOURCE_AND_REAL_PG16_REVIEW`

## Review blockers → fixes

1. **P0 first-provision wrote before refusing**: `_assert_cluster_binding`
   Layer 1 now binds ALL THREE URLs to one frozen endpoint (host:port of
   admin included). Deferred connection is allowed ONLY in two
   catalog-proven shapes — (a) fully fresh first deployment (database and
   both roles absent) or (b) established principals + absent database with
   a LIVE credential probe of both roles against the maintenance database
   before any write. Partial role set, existing database, or failed probe →
   zero-write refusal. Counterexamples: true first-deploy cross-cluster
   (zero additions on BOTH clusters), partial-exists (run-unique role
   names), wrong-password.
2. **P1 credentials in diagnostics**: netloc rendering deleted; only
   host:port and role names are printed. Synthetic-secret proof: the
   harness embeds a random token in every password and scans all 18
   evidence files post-run — `files_containing_secret: 0`. Per-test
   assertions additionally refuse any password/DSN/`@` in CLI output.
   Mutation-run logs mask the token in place while keeping the leak
   location visible.
3. **P1 product bootstrap missed public-CREATE**:
   `_assert_ledger_guard_function_authority` now refuses when the connected
   runtime holds CREATE on schema public — before CREATE SCHEMA, zero
   tenant objects (exact attempted-schema-name check, not prefix scan).

## New semantic mutations (MM1-MM4 retained, all named-RED + byte-identical restore)

- MM5 binding refusal matrix deleted → `test_wrong_password_provision_refused_zero_writes` RED;
- MM6 netloc leak restored → `test_cluster_binding_mismatch_zero_writes` +
  `test_first_deploy_cross_cluster_refused_zero_writes` RED;
- MM7 public-CREATE check deleted → `test_runtime_with_public_create_refused_zero_tenant` +
  `test_bootstrap_script_keeps_fail_closed_precondition_semantics` RED.

Harness hardening found during this round: mutation runs are now ISOLATED
(previous mutation restored before the next is applied — an accumulation
bug let MM6's netloc leak into MM7's run), and mutation logs mask the
synthetic secret.

## Machine results

`ai-ledger/product-ai/evidence/2026-09-16_zcode_tenant_bootstrap_db_authority_r1_r2/`:
two fresh `postgres:16.15` clusters (ids 7686002363049861164 /
7686002379247329321); six scenario suites GREEN; `--verify` rc=0 (intact) /
rc=2 (runtime-owned guard, identity unchanged); 7/7 mutations named-RED
with byte-identical restore (bootstrap
`7d0ac13e...`/grants `82eef0fb...` grouped in report = committed bytes);
post-restore GREEN; synthetic-secret scan 0/18 files; BASE-vs-candidate
bootstrap-heavy regression 104/104 per-node outcomes, deltas=0.

## Scope discipline

Only the two scripts, the V3 suite, the harness and ledger/evidence
changed. No migrations, SKU, SMTP, order, payment, frontend or
docker-entrypoint changes. Successor commit: normal commit from BASE, no
amend/rebase/force; pushed with local==remote proof (see manifest commit).
