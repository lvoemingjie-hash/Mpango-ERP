# C91 task-only PG16 recovery

This runbook describes the R5 authorized rehearsal, not production automation
or final independent risk acceptance. Use separate task-owned source/target
clusters and private input files. Never reuse a live cluster or its passwords.

## Source preparation

Pin the R4 PostgreSQL 16 image digest. Record exact container ID, volume,
owner/task labels and loopback port immediately on acquisition. Use the existing
`provision_runtime_db_roles.py --provision`, migration `alembic upgrade head`,
`--apply-grants`, and `--verify` in that order. Migration authority is
`mpango_migrate`; application/runtime authority is `mpango_app`. Head is 039.
Runtime tenant provisioning and existing seed functions establish two tenants.
Existing catalog, inventory, order and canonical payment commands generate
nonzero business facts; never insert financial rows directly for expected data.

The frozen rehearsal scenario is: tenant A stock 50, orders 100/100/50, a cash
partial payment 30, credit conversion 100 followed by fulfillment of two units,
and confirmed hold 50. Expected stock is 48, reserved quantity 3, remaining
partial hold 70 and binding cache 220. Tenant B has stock 7 and a draft 50 order.
These expectations must be checked against Decimal facts, not inferred from rc.
In the actual source, partial cash and credit fulfillment did not post ledger
entries. The amended task scenario therefore added a fourth 50 full-cash order
and fulfilled one unit through the existing commands. The amended expected stock
is 47, reserved quantity 3, binding cache still 220, with an additional settled
hold and nonzero balanced ledger. This is a fixture amendment, not a new product
accounting rule or a claim that delivery accounting is fully implemented.

## Export and restore

Pause only this task's writers. Freeze all public and tenant relation row counts,
stable row fingerprints, definitions, owners, ACL, role capabilities and guard
definitions. Export with migration login and `pg_dump --format=custom
--role=mpango_app`; private credentials pass through environment names, not argv.
If a permission coverage failure occurs, preserve it and obtain the explicitly
authorized task-admin fallback without changing normal role privileges.

Prepare target roles and a new empty database only, not migrations to head.
Use new target passwords; never export role password verifiers. A task-only
administrator may run `pg_restore --single-transaction --exit-on-error --dbname`.
Do not use `--no-owner`, `--no-acl` or ignore restore errors. Compare all captured
relations and business vectors before any post-restore writes. Verify the existing
product privilege contract; use `--apply-grants` only when its actual existing
contract is needed and record the before/after difference.

## Positive and negative controls

Using runtime identity and the real application, login/select tenant, read restored
orders, replay the original payment idempotency key without new payment/ledger
effects, reject tenant B read/write of tenant A, and perform a legitimate stock
adjustment with its separately declared expected difference. App must remain
NOSUPERUSER/NOCREATEDB/NOCREATEROLE and unable to create public objects or SET ROLE
to migration authority.

Restore a truncated dump only into a second new empty database. Require nonzero
rc and zero partial user objects after transaction rollback. Change a retained
comparison COPY by one monetary or inventory unit and require named rejection.
Keep the positive restored database intact.

## Evidence and limits

Record native argv, PID, start/end, rc, source candidate and raw/output hashes.
Retain failed attempts without rewriting them. Stop only reverified exact owned
resources; preserve positive volumes, private binary dump and private raw evidence
for CTO. Destroy exact synthetic credential input files after public value/shape
scan; metadata tombstones do not claim physical erasure.

This does not establish production cron, offsite storage, notifications, capacity,
RPO/RTO, global CI safety or merge/deployment authority. R4 results keep their R4
candidate identity; CI/doc-only successors may request reuse by blob equivalence.

The R5 rehearsal paused at catalog comparison under its repeated-cause stop rule.
The real dump and transactional restore succeeded and row fingerprints matched,
but equivalent varchar-array CHECK/index deparser forms were not yet compared
consistently. Runtime post-restore operations and negative restore controls were
not executed. Preserve the raw definitions and restore receipt; do not claim a
completed recovery battery. A read-only normalization probe showed matching PG
parsed filters for the first CHECK. Database-level ACL is not in a non-create
pg_dump and must be restored from the existing product contract, not ad-hoc grants.
