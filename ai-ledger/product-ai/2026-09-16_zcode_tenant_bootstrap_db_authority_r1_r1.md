# ZCode-W R1-R1 — Tenant bootstrap DB authority hardening: read-only verify, derived authority, identifier allowlist, cluster binding

- DATE=2026-09-16
- AUTHORIZATION_ID=CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R1-2026-09-16
- BASE=0a16ed707ad898e9924c26b28097148708677af9 (R1 manifest commit)
- EXECUTOR=ZCode-W
- VERIFICATION_TIER=V3_MERGE_CRITICAL_DATA_INTEGRITY_SECURITY
- CLAIM_CEILING=CORRECTED_SOURCE_CANDIDATE_ONLY
- NEXT_GATE=`KILO_TENANT_BOOTSTRAP_DB_AUTHORITY_SOURCE_AND_REAL_PG16_REVIEW`

## Required fixes → what changed

1. **Read-only --verify** (`provision_runtime_db_roles.py`): the R1
   transactional DDL probe is removed; `verify()` is pure catalog. Replace/
   drop capability is proven from ownership + superuser + `pg_has_role`
   (`app_no_replace_path_on_guard`) and `app_no_create_on_public_schema`
   closes the DROP+CREATE substitution path.
2. **Runtime-owned guard counterexample**: new scenario DB
   `v3_verify_wrongown`; harness `--verify` exits rc=2 and
   `test_verify_cli_wrongowner_nonzero_and_read_only` proves OID / owner /
   `pg_get_functiondef` md5 byte-identical across the verify run.
3. **Fallback deleted** (`bootstrap_tenant_schema.py`): the migration
   authority is DERIVED from the live catalog (`pg_database.datdba` of the
   current database); declared `MPANGO_MIGRATION_AUTHORITY_ROLE` must EQUAL
   the derived owner; single-role (runtime == authority) bootstrap is
   explicitly refused; runtime-owned guards are refused with the env
   undeclared.
4. **Separation**: bootstrap precondition and --verify both assert runtime !=
   authority, runtime not superuser, runtime not a member of the authority
   (pg_has_role MEMBER/USAGE — no SET ROLE path), runtime without CREATE on
   schema public.
5. **Identifier allowlist**: `validate_identifier` (`^[a-z_][a-z0-9_]{0,62}$`)
   in every mode before any connection (roles + database), `_ensure_role`
   re-validates, and bootstrap validates the tenant-schema identifier.
   `FORBIDDEN_SQL_FRAGMENTS` documented as grant-minimality policy, not
   injection defense. Injection counterexample (quote + semicolon + comment
   payload in role name AND URL username) refused pre-connection with zero
   writes.
6. **Cluster binding preflight**: `_assert_cluster_binding` — URL
   consistency, live admin binding (superuser + expected current_user +
   cluster id), and the full live triple (one `system_identifier`, same
   database, bound roles) whenever connectable; deferred proof only on the
   very first provision, re-asserted live right after creation. Cross-cluster
   admin URL refused with zero writes on both clusters.

## V3 machine evidence (two fresh PG16 clusters per run)

`ai-ledger/product-ai/evidence/2026-09-16_zcode_tenant_bootstrap_db_authority_r1_r1/`
(README maps every fix to its proof; `harness_report.json` is the
authoritative record; digests in grouped 8-char form).

- Six scenario suites GREEN: full public lifecycle as runtime role (signup →
  mail → verify → setup → login → select-tenant → /auth/me), four original
  negatives fail closed with zero partial tenant, plus the new
  wrong-owner-verify negative.
- Tool `--verify`: rc=0 on the intact database, rc=2 on the runtime-owned
  guard, identity unchanged in both directions.
- Mutations MM1 (commit-type verify restored), MM2 (owner fallback
  restored), MM3 (identifier validation bypassed), MM4 (cluster binding
  bypassed): each went RED on its named semantic assertion; both scripts
  restored byte-identically (sha256 recorded); post-restore v3_ok GREEN.
- MM1 note: the behavioral identity proof stays green under MM1 because
  PostgreSQL refuses CREATE OR REPLACE even for the function's OWNER without
  CREATE on schema public — which the minimum grants never confer. The
  pure-catalog static is MM1's semantic detector; the structural denial is
  an independent second defense (verified experimentally).
- Regression (fix 8): the R1 7-file bootstrap-heavy suite run on BASE
  `0a16ed70` and on the candidate in an IDENTICAL two-role topology —
  104/104 per-node outcomes, deltas=0 (pre-existing failures identical on
  both branches; `regression_base.txt` / `regression_candidate.txt`).

## STOP-condition clearance

All four STOP conditions evaluated and cleared with named evidence (README
table): verify never changes function identity/body (proven + MM1
load-bearing), single-role fallback refused (MM2 load-bearing), cross-cluster
mixing refused with zero writes (MM4 load-bearing), injection counterexample
blocked pre-connection (MM3 load-bearing).

## Operational consequence (documented, not silently changed)

With the fallback removed, the single-role docker-entrypoint topology now
FAILS CLOSED at bootstrap by design; the supported topology is two-role
provisioning via `scripts/provision_runtime_db_roles.py`. Deployment
topology changes remain out of scope per the claim ceiling.

## Scope discipline

Only the two scripts, the V3 suite, the harness, and ledger/evidence
changed. No migrations, SKU, SMTP, order, payment, frontend or
docker-entrypoint changes. Successor commit: normal commit from BASE, no
amend/rebase/force; pushed to origin with local==remote proof (see below).
