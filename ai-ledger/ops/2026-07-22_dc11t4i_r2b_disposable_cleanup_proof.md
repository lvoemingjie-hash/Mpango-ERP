# DC-11T4I-R2B Disposable TEST001 Cleanup and Migration-035 Proof

## Verdict

PASS_FOR_CTO_DC11T4I_R2B_CONTROLLED_CLEANUP

## Scope

| Item | Evidence |
| --- | --- |
| Branch | `ops/dc11t4i-r2b-disposable-cleanup-proof-2026-07-22` |
| R2A checkpoint | `eb79cb040376431a870895771907cafd72f01fdf` |
| Product target for proof runner | `1be053e0ad362df66b2e153e8317d6a559eed61a` |
| Production safe baseline | `303dc179e94527668f4f1d2145fab74be0f48751` |
| Changed repo files | This ledger only |
| Product code / migration changes | None |
| Production data mutation | None |
| Full production dump transfer | None |

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
- Required reporting roles were pre-created as non-login roles before restore.

## Restore Evidence

| Check | Result |
| --- | --- |
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
| Non-target tenant schema count | `10` |
| Non-target tenant table fingerprints | `190` |
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

## Regression Tests

All tests ran in disposable containers from source `1be053e0ad362df66b2e153e8317d6a559eed61a`, on the isolated proof network with no public DB port and no production network/volume attachment.

| Bundle | Result |
| --- | --- |
| DC-11T4H integrity | `13 passed, 2 warnings` |
| Finance receivables | `40 passed, 1 warning` |
| Payment/order/ledger regressions incl. DC-11D | `111 passed, 1 xfailed, 3 warnings` |
| Migration/bootstrap regressions | `48 passed, 3 skipped, 5 xfailed, 14 warnings` |

Existing skipped/xfail outcomes were from the target checkpoint test suite; this branch did not add skips, xfails, deselection or assertion weakening.

## GitNexus

- Indexed target used for impact context: `_dc11t4h_controlled_promotion_2026-07-22` at `1be053e0ad362df66b2e153e8317d6a559eed61a`.
- `context(name="upgrade", file_path="backend/alembic/versions/035_receivable_collection_integrity.py")`: found migration 035 `upgrade` at lines 42-52 and its downstream helper calls.
- `impact(target="upgrade", direction="upstream", includeTests=true, maxDepth=2)`: `LOW` risk, `0` direct callers, `0` affected processes, `0` affected modules.
- `detect_changes(scope="all")` on `_dc11t4i_r2b_disposable_cleanup_proof_2026-07-22`: `changed_count=0`, `affected_count=0`, `risk_level=none`; the ledger-only diff mapped to no code symbols or execution flows.

## Hygiene Gates

| Gate | Result |
| --- | --- |
| `git diff --cached --check` | `PASS` |
| `pre-commit run --files ai-ledger/ops/2026-07-22_dc11t4i_r2b_disposable_cleanup_proof.md` | `PASS` |
| `detect-secrets scan ai-ledger/ops/2026-07-22_dc11t4i_r2b_disposable_cleanup_proof.md --no-verify` | `PASS`, `0` findings |

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
