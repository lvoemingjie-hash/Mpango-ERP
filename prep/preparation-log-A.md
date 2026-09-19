# Kilo V3 Partition A preparation log
AUTHORIZATION_ID: CTO-AUTH-ORDER-R2-E1-F1-F3-KILO-V3-2026-09-19
started_utc: 2026-09-19T03:01:22Z
container_started: kilo-order-e1-f1f3-pg-a 2026-09-19T03:01:22Z
postgres_ready: kilo-order-e1-f1f3-pg-a
role_bootstrapped: oe1f3_kilo_run (db owner; CREATEROLE; no superuser/createdb/bypassrls)
PREPFAIL_A: alembic upgrade head A
# Kilo V3 Partition A preparation log
AUTHORIZATION_ID: CTO-AUTH-ORDER-R2-E1-F1-F3-KILO-V3-2026-09-19
started_utc: 2026-09-19T03:02:04Z
removing stale kilo-order-e1-f1f3-pg-a from an earlier preparation attempt
container_started: kilo-order-e1-f1f3-pg-a 2026-09-19T03:02:04Z
postgres_ready: kilo-order-e1-f1f3-pg-a
role_bootstrapped: oe1f3_kilo_run (db owner; CREATEROLE; no superuser/createdb/bypassrls)
alembic_head: 039_order_credit_holds
smoke_db_migrated: order_e1_f1f3_kilo_a_smoke
smoke_node_rc: 0
smoke_db_dropped: order_e1_f1f3_kilo_a_smoke
collected_nodes: 28
selected_nodes_A: 27
env_file_written: env-partition-a.sh (mode 0600, values never persisted to evidence)
PREPFAIL_A: preflight JSON A
prep_iteration_note: preflight JSON attempt 1 failed on transient git ls-remote network error (rc=128); environment itself was complete and healthy; rebuilding identity evidence with retries
ls-remote attempt 1 failed; retrying
ls-remote attempt 2 failed; retrying
ls-remote attempt 3 failed; retrying
ls-remote attempt 4 failed; retrying
ls-remote attempt 5 failed; retrying
identity_evidence_written 2026-09-19T03:14:42Z; vps_tip_this_attempt=UNAVAILABLE_THIS_ATTEMPT
PREFLIGHT_A_COMPLETE 2026-09-19T03:14:43Z
