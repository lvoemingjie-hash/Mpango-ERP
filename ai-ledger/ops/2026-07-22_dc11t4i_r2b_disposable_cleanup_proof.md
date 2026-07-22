# DC-11T4I-R2B/R1 Disposable TEST001 Cleanup and Migration-035 Proof

## Verdict

PASS_FOR_CTO_DC11T4I_R2B_R1_REPRODUCIBLE_CLEANUP

## Scope

| Item | Evidence |
| --- | --- |
| Branch | `ops/dc11t4i-r2b-disposable-cleanup-proof-2026-07-22` |
| R2A checkpoint | `eb79cb040376431a870895771907cafd72f01fdf` |
| Approved R2A checkpoint merged | `f386bf0a191b1cc2345de0cc7e5cbae07aff33c0` |
| Product target for proof runner | `1be053e0ad362df66b2e153e8317d6a559eed61a` |
| Production safe baseline | `303dc179e94527668f4f1d2145fab74be0f48751` |
| Cleanup artifact | `ai-ledger/ops/artifacts/2026-07-22_dc11t4i_test001_cleanup.sql` |
| Cleanup artifact SHA256 | `92ea28adb7e0936e5487cf2bf3c810aea546f45881b87017da9988531569b728` |
| Changed repo files | OPS evidence reports and OPS cleanup artifact only |
| Product code / migration changes | None |
| Production data mutation | None |
| Full production dump transfer | None |

## Evidence Lineage

- R1 corrected financial forensics is preserved as `ai-ledger/ops/2026-07-22_dc11t4i_r1_legacy_test_tenant_forensics.md`.
- R2A cleanup design is preserved as `ai-ledger/ops/2026-07-22_dc11t4i_r2a_test001_cleanup_design.md`.
- R2B disposable proof is preserved and updated in `ai-ledger/ops/2026-07-22_dc11t4i_r2b_disposable_cleanup_proof.md`.
- Approved checkpoint `f386bf0a191b1cc2345de0cc7e5cbae07aff33c0` was merged by normal merge commit, with no force-push or history rewrite.

## Production Baseline

- VPS production project was verified on `product-dev-recovered` at `303dc179e94527668f4f1d2145fab74be0f48751`.
- Git tracked state was clean: `PROD_TRACKED_CLEAN=YES`.
- Runtime health was clean: backend, frontend, gateway, postgres and redis were `healthy`; HTTP health check passed.

## Disposable Restore Infrastructure

- Existing VPS-hosted logical backup selected in place: `dc11t4i_20260722T062413Z.sql`.
- Backup metadata recorded only as sanitized metadata: `874700` bytes, SHA256 prefix `b4380a8a8cdb5cfa`, mtime `2026-07-22T06:24:14Z`.
- Disposable PostgreSQL 15 and Redis 7 containers were attached only to a run-scoped Docker bridge network.
- PostgreSQL exposed no host port: `PROOF_DB_PUBLIC_PORTS_BOUND=0`.
- PostgreSQL used a run-scoped disposable Docker volume only: `PROOF_DB_VOLUME_DISPOSABLE=YES`.
- CPU and memory limits were set on disposable containers: `PROOF_RESOURCE_LIMITS_SET=YES`.
- Proof runner source was exactly `1be053e0ad362df66b2e153e8317d6a559eed61a`.
- Required owner and reporting roles were pre-created as non-login roles before restore.

## Restore Evidence

| Check | Result |
| --- | --- |
| Restore prerequisite roles | Owner and reporting roles pre-created as `NOLOGIN` in the disposable cluster |
| Restore exit | `0` |
| Restore errors | `0` |
| Restore warnings | `0` |
| Restored create-table statements | `236` |
| Restored copy statements | `236` |

## Pre-Cleanup Read-Only Evidence

| Invariant | Result |
| --- | --- |
| Authoritative tenant registry query | `tenant_registrations JOIN wholesalers` |
| Authoritative registry rows | `8` |
| Authoritative registry rows for TEST001 | `0` |
| TEST001 wholesaler rows | `1` |
| TEST001 binding rows | `2` |
| TEST001 exclusive retailer rows | `2` |
| Target schema present | `1` |
| Target schema table count | `19` |
| Target schema row total | `299` |
| Non-target tenant schema count | `9` UUID-format tenant schemas, plus the TEST001 target schema |
| Non-target tenant table fingerprints | Captured and compared by digest |
| Non-target binding negatives before migration | `2` |

## Cleanup Contract

- Cleanup used bound UUID parameters for target identity and did not interpolate shell variables inside dollar-quoted PL/pgSQL.
- Cleanup used validated exact tenant schema format: `t_550e8400e29b41d4a716446655440000`.
- Cleanup used safe identifier quoting for the schema drop.
- Cleanup executed in one transaction with an advisory lock and fail-closed ownership/dependency preconditions.
- Cleanup stopped on any tenant registration, platform tenant, audit evidence, password-reset evidence, shared retailer or non-target invitation reference.

## Cleanup Results

| Check | Result |
| --- | --- |
| First cleanup mode | `REMOVED_CONFIRMED_TEST001` |
| Deleted TEST001 wholesalers | `1` |
| Deleted TEST001 exclusive retailers | `2` |
| Deleted TEST001 invitations | `3` |
| Non-target tenant fingerprint match | `YES` |
| Non-target public fingerprint match | `YES` |
| Non-target financial aggregate match | `YES` |
| Non-target binding balance hash match | `YES` |
| Second cleanup mode | `IDEMPOTENT_NOOP` |
| Second cleanup deleted wholesalers | `0` |
| Second cleanup deleted retailers | `0` |
| Second cleanup deleted invitations | `0` |
| Idempotent residual target artifacts | `0` |
| Idempotent non-target fingerprint match | `YES` |

## Reproducible Artifact Contract

- Artifact path: `ai-ledger/ops/artifacts/2026-07-22_dc11t4i_test001_cleanup.sql`.
- Artifact SHA256: `92ea28adb7e0936e5487cf2bf3c810aea546f45881b87017da9988531569b728`.
- The artifact anchors exactly to TEST001 UUID `550e8400-e29b-41d4-a716-446655440000` and schema `t_550e8400e29b41d4a716446655440000`.
- The artifact sets `ON_ERROR_STOP`, acquires `pg_advisory_xact_lock(hashtext('dc11t4i_test001_cleanup'))`, and keeps assertions plus cleanup in one transaction.
- The artifact fails closed on registration, platform tenant, audit, reset-token, shared-retailer, non-target invitation, unknown-FK and count-mismatch evidence.
- The artifact uses no shell substitution inside `DO` blocks; the only operator input is the explicit psql apply flag outside PL/pgSQL.
- The artifact validates the schema identifier and drops only the exact schema with `format('%I', target_schema)`; there is no wildcard schema deletion scan.
- The artifact performs no balance updates or rewrites.
- Default execution rolls back. `COMMIT` requires explicit `-v dc11t4i_apply=1`.
- A second committed invocation returns `IDEMPOTENT_NOOP` with zero TEST001 residuals.

## R2B-R1 Artifact Proof

The artifact was copied to the VPS as a small SQL file only; the full production dump remained on the VPS host. The artifact SHA256 was verified before execution.

| Check | Result |
| --- | --- |
| Artifact SHA256 | `92ea28adb7e0936e5487cf2bf3c810aea546f45881b87017da9988531569b728` |
| Rollback rehearsal exit | `0` |
| Rollback rehearsal transaction | `ROLLBACK` |
| Rollback rehearsal fingerprints | `UNCHANGED` |
| Apply exit | `0` |
| Apply mode | `REMOVED_CONFIRMED_TEST001` |
| Apply transaction | `COMMIT` |
| Apply target residuals | `0` |
| Apply non-target public fingerprint | `MATCH` |
| Apply non-target tenant fingerprint | `MATCH` |
| Second apply exit | `0` |
| Second apply mode | `IDEMPOTENT_NOOP` |
| Second apply target residuals | `0` |
| Second apply non-target fingerprint | `MATCH` |

## Migration 035 Proof

| Check | Result |
| --- | --- |
| Alembic current before upgrade | `034_platform_operators` |
| First `alembic upgrade head` | `PASS` |
| Alembic current after first upgrade | `035_receivable_collection_integrity` |
| Second `alembic upgrade head` running-upgrade count | `0` |
| Alembic heads count | `1` |
| Alembic heads value | `035_receivable_collection_integrity` |
| Negative outstanding balances after migration | `0` |
| Non-negative DB check present | `YES` |
| Target TEST001 schema after migration | `0` |
| Orphan financial references after migration | `0` |
| Paid ordinary collectible invalid count | `0` |
| Over-collected credit orders | `0` |
| Non-target tenant row fingerprint after migration | `MATCH` |
| Public binding row identity after migration | `MATCH` |

R2B-R1 reran the migration proof after executing the committed artifact exactly: first `alembic upgrade head` reached `035_receivable_collection_integrity`; the second `alembic upgrade head` had `0` running-upgrade lines; `current` and `heads` both equaled `035_receivable_collection_integrity`.

## Regression Tests

All tests ran in disposable containers from source `1be053e0ad362df66b2e153e8317d6a559eed61a`, on the isolated proof network with no public DB port and no production network/volume attachment.

| Bundle | Result |
| --- | --- |
| DC-11T4H integrity | `13 passed, 2 warnings` |
| Finance receivables | `40 passed, 1 warning` |
| Payment/order/ledger regressions incl. DC-11D | `111 passed, 1 xfailed, 3 warnings` |
| Migration/bootstrap regressions | `48 passed, 3 skipped, 5 xfailed, 14 warnings` |

Existing skipped/xfail outcomes were from the target checkpoint test suite; this branch did not add skips, xfails, deselection or assertion weakening.

R2B-R1 reran the required focused bundles against fresh disposable test databases in the proof infrastructure:

| Bundle | R2B-R1 Result |
| --- | --- |
| DC-11T4H integrity | `13 passed, 2 warnings` |
| Finance receivables | `40 passed, 1 warning` |

The prior R2B payment/order/ledger and migration/bootstrap bundles are referenced without rerun for R2B-R1 because product code, migrations and test code are unchanged by this branch.

## GitNexus

- Indexed target used for impact context: `_dc11t4h_controlled_promotion_2026-07-22` at `1be053e0ad362df66b2e153e8317d6a559eed61a`.
- `context(name="upgrade", file_path="backend/alembic/versions/035_receivable_collection_integrity.py")`: found migration 035 `upgrade` at lines 42-52 and its downstream helper calls.
- `impact(target="upgrade", direction="upstream", includeTests=true, maxDepth=2)`: `LOW` risk, `0` direct callers, `0` affected processes, `0` affected modules.
- `detect_changes(scope="staged")` on `_dc11t4i_r2b_disposable_cleanup_proof_2026-07-22`: `changed_files=2`, `changed_count=19`, `affected_count=0`, `risk_level=low`; the OPS evidence/artifact diff mapped to no affected execution flows.

## Hygiene Gates

| Gate | Result |
| --- | --- |
| `git diff --check` | `PASS` |
| `git diff --cached --check` | `PASS` |
| `pre-commit run --files` on the R2B report and cleanup SQL artifact | `PASS` |
| `detect-secrets scan` on the R2B report and cleanup SQL artifact | `PASS`, `0` findings |

An earlier all-files pre-commit attempt only exposed pre-existing out-of-scope repository formatting and generated-cache churn. Those hook mutations were reverted before the final scoped gates and are not part of this branch.

## Cleanup Proof

| Disposable artifact class | Remaining |
| --- | --- |
| Proof containers | `0` |
| Proof volumes | `0` |
| Proof networks | `0` |
| Proof temp root | `0` |
| Proof temp script | `0` |
| Test containers | `0` |
| Test volumes | `0` |
| Test networks | `0` |
| Test temp root | `0` |
| Test temp script | `0` |

## Protected Branch Controls

- No deployment was performed.
- No release tags were moved or created.
- No protected branch push was performed.
