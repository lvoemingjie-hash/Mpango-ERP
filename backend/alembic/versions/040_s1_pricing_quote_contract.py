"""S1 nullable preparation fields and durable DRAFT intent constraints.

No base price or historical currency is inferred. Existing financial and
inventory rows are untouched. Tenant DDL uses the existing SET-only migration
capability with a savepoint protecting both handshake and body failures.
"""
from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa

revision = '040_s1_pricing_quote_contract'
down_revision = '039_order_credit_holds'
branch_labels = None
depends_on = None

S1_DDL = (
    'ALTER TABLE {q}.skus ADD COLUMN base_price NUMERIC(12,2), ADD COLUMN pricing_revision INTEGER NOT NULL DEFAULT 0, ADD COLUMN display_label VARCHAR(32)',
    'ALTER TABLE {q}.skus ADD CONSTRAINT ck_skus_base_price_positive CHECK (base_price IS NULL OR base_price > 0), ADD CONSTRAINT ck_skus_pricing_revision CHECK (pricing_revision >= 0)',
    'ALTER TABLE {q}.orders ADD COLUMN country_snapshot VARCHAR(2), ADD COLUMN currency_snapshot VARCHAR(3), ADD COLUMN registration_snapshot_id UUID, ADD COLUMN creation_operation VARCHAR(32), ADD COLUMN creation_key_digest VARCHAR(64), ADD COLUMN creation_fingerprint VARCHAR(64), ADD COLUMN quote_seen JSONB, ADD COLUMN quote_resolved JSONB, ADD COLUMN replaces_order_id UUID REFERENCES {q}.orders(id) ON DELETE RESTRICT',
    "ALTER TABLE {q}.orders ADD CONSTRAINT ck_orders_s1_currency CHECK (currency_snapshot IS NULL OR currency_snapshot IN ('KES','UGX')), ADD CONSTRAINT ck_orders_creation_intent CHECK ((creation_key_digest IS NULL AND creation_fingerprint IS NULL AND creation_operation IS NULL) OR (creation_key_digest IS NOT NULL AND creation_fingerprint IS NOT NULL AND creation_operation IS NOT NULL AND created_by IS NOT NULL AND currency_snapshot IS NOT NULL))",
    'CREATE UNIQUE INDEX ux_orders_creation_intent ON {q}.orders (wholesaler_id, retailer_id, created_by, creation_operation, creation_key_digest) WHERE creation_key_digest IS NOT NULL',
    'CREATE UNIQUE INDEX ux_orders_replacement ON {q}.orders (replaces_order_id) WHERE replaces_order_id IS NOT NULL',
    'ALTER TABLE {q}.order_items ADD COLUMN package_quantity_snapshot NUMERIC(12,3), ADD COLUMN display_label_snapshot VARCHAR(32)',
)


def _tenant_window(bind, schema, body):
    entry, session_user = bind.execute(sa.text('SELECT current_user,session_user')).one()
    if entry != session_user:
        raise RuntimeError('S1_MIGRATION_ENTRY_IDENTITY_DRIFT')
    can_create = bind.execute(sa.text('SELECT has_schema_privilege(current_user, :s, \'CREATE\')'),
                              {'s': schema}).scalar_one()
    if not can_create and not bind.execute(sa.text(
            "SELECT pg_has_role(current_user, 'mpango_app', 'SET')")).scalar_one():
        raise RuntimeError('S1_TENANT_DDL_AUTHORITY_REQUIRED')
    savepoint = bind.begin_nested()
    try:
        if not can_create:
            bind.execute(sa.text('SET ROLE mpango_app'))
            if bind.execute(sa.text('SELECT current_user')).scalar_one() != 'mpango_app':
                raise RuntimeError('S1_TENANT_DDL_HANDSHAKE_FAILED')
        body()
        if not can_create:
            bind.execute(sa.text('RESET ROLE'))
        if bind.execute(sa.text('SELECT current_user')).scalar_one() != entry:
            raise RuntimeError('S1_TENANT_DDL_IDENTITY_DRIFT')
        savepoint.commit()
    except BaseException:
        try:
            savepoint.rollback()
            if not can_create:
                bind.execute(sa.text('RESET ROLE'))
            if bind.execute(sa.text('SELECT current_user')).scalar_one() != entry:
                raise RuntimeError('S1_TENANT_DDL_IDENTITY_DRIFT')
        except BaseException:
            bind.invalidate()
            raise RuntimeError('S1_TENANT_DDL_CONNECTION_DISCARDED')
        raise


def upgrade():
    bind = op.get_bind()
    current, session_user, guard_owner = bind.execute(sa.text(
        "SELECT current_user,session_user,pg_get_userbyid(proowner) "
        "FROM pg_proc WHERE oid='public.prevent_ledger_modification()'::regprocedure"
    )).one()
    if current != session_user or current != guard_owner or current == 'mpango_app':
        raise RuntimeError('S1_MIGRATION_AUTHORITY_REQUIRED')
    rows = bind.execute(sa.text(
        "SELECT tr.tenant_schema, tr.wholesaler_id, tr.status, w.status AS ws_status "
        "FROM public.tenant_registrations tr JOIN public.wholesalers w ON w.id=tr.wholesaler_id "
        "WHERE tr.is_deleted IS FALSE AND w.is_deleted IS FALSE ORDER BY tr.tenant_schema"
    )).mappings().all()
    schemas = []
    for row in rows:
        schema = row['tenant_schema']
        if (not schema or not re.fullmatch(r't_[0-9a-f]{32}', schema)
                or schema != 't_' + str(row['wholesaler_id']).replace('-', '')
                or row['status'] not in {'pending_email_verification', 'email_verified', 'provisioning', 'active', 'failed'}
                or row['ws_status'] not in {'active', 'provisioning'}):
            raise RuntimeError('S1_TENANT_REGISTRY_MISMATCH')
        if schema in schemas:
            raise RuntimeError('S1_TENANT_REGISTRY_AMBIGUOUS')
        schemas.append(schema)
    # All read-only checks precede the first DDL; Alembic owns the enclosing
    # transaction and rolls back every tenant if any later statement fails.
    for schema in schemas:
        owner = bind.execute(sa.text(
            'SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=:s'), {'s': schema}).scalar()
        if owner != 'mpango_app':
            raise RuntimeError('S1_TENANT_OWNER_MISMATCH')
        def preflight(schema=schema):
            for table in ('skus', 'orders', 'order_items'):
                exists = bind.execute(sa.text('SELECT to_regclass(:name)'),
                                      {'name': f'{schema}.{table}'}).scalar()
                if exists is None:
                    raise RuntimeError('S1_PREDECESSOR_TABLE_MISSING')
            columns = bind.execute(sa.text(
                "SELECT a.attname FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:s "
                "AND c.relname='skus' AND a.attnum>0 AND NOT a.attisdropped"
            ), {'s': schema}).scalars().all()
            if 'base_price' in columns or 'pricing_revision' in columns:
                raise RuntimeError('S1_PREDECESSOR_SCHEMA_ALREADY_MODIFIED')
        _tenant_window(bind, schema, preflight)
    for schema in schemas:
        def ddl(schema=schema):
            for statement in S1_DDL:
                bind.execute(sa.text(statement.format(q='"' + schema + '"')))
        _tenant_window(bind, schema, ddl)


def downgrade():
    raise RuntimeError('040 is forward-only: currency/consent/intent snapshots require a backup for rollback')
