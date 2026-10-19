"""Immutable tenant proposals; no existing order, money or media row is rewritten."""
import re
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = '042_order_negotiation_proposals'
down_revision = '041_catalog_product_main_image'
branch_labels = None
depends_on = None

PROPOSAL_DDL = (
    '''CREATE TABLE {q}.order_negotiation_proposals (
        id UUID CONSTRAINT order_negotiation_proposals_pkey PRIMARY KEY,
        source_order_id UUID NOT NULL CONSTRAINT fk_negotiation_source REFERENCES {q}.orders(id) ON DELETE RESTRICT,
        wholesaler_id UUID NOT NULL, retailer_id UUID NOT NULL, created_by UUID NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), version INTEGER NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL, digest VARCHAR(64) NOT NULL,
        status VARCHAR(16) NOT NULL, decided_by UUID, decided_at TIMESTAMPTZ,
        accepted_order_id UUID CONSTRAINT fk_negotiation_accepted REFERENCES {q}.orders(id) ON DELETE RESTRICT,
        accept_key_digest VARCHAR(64), accepted_intent_digest VARCHAR(64),
        CONSTRAINT uq_negotiation_source_version UNIQUE (source_order_id,version),
        CONSTRAINT uq_negotiation_accepted_order UNIQUE (accepted_order_id),
        CONSTRAINT ck_negotiation_version CHECK (version > 0),
        CONSTRAINT ck_negotiation_status CHECK (status IN ('pending','accepted','rejected','withdrawn')),
        CONSTRAINT ck_negotiation_decision_shape CHECK (
            (status='pending' AND decided_by IS NULL AND decided_at IS NULL AND accepted_order_id IS NULL
                AND accept_key_digest IS NULL AND accepted_intent_digest IS NULL) OR
            (status IN ('rejected','withdrawn') AND decided_by IS NOT NULL AND decided_at IS NOT NULL
                AND accepted_order_id IS NULL AND accept_key_digest IS NULL AND accepted_intent_digest IS NULL) OR
            (status='accepted' AND decided_by IS NOT NULL AND decided_at IS NOT NULL AND accepted_order_id IS NOT NULL
                AND accept_key_digest IS NOT NULL AND accepted_intent_digest IS NOT NULL))
    )''',
    "CREATE UNIQUE INDEX ux_negotiation_pending_source ON {q}.order_negotiation_proposals (source_order_id) WHERE status='pending'",
    'CREATE UNIQUE INDEX ux_negotiation_accept_key ON {q}.order_negotiation_proposals (wholesaler_id,retailer_id,decided_by,accept_key_digest) WHERE accept_key_digest IS NOT NULL',
    '''CREATE FUNCTION {q}.prevent_negotiation_rewrite() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog AS $s3$
    BEGIN
        IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'NEGOTIATION_HISTORY_IMMUTABLE';
        END IF;
        IF OLD.status <> 'pending' OR NEW.status='pending' OR
            ROW(NEW.id,NEW.source_order_id,NEW.wholesaler_id,NEW.retailer_id,NEW.created_by,
                NEW.created_at,NEW.version,NEW.expires_at,NEW.payload,NEW.digest) IS DISTINCT FROM
            ROW(OLD.id,OLD.source_order_id,OLD.wholesaler_id,OLD.retailer_id,OLD.created_by,
                OLD.created_at,OLD.version,OLD.expires_at,OLD.payload,OLD.digest) THEN
            RAISE EXCEPTION 'NEGOTIATION_HISTORY_IMMUTABLE';
        END IF;
        RETURN NEW;
    END;
    $s3$''',
    '''CREATE TRIGGER negotiation_history_immutable BEFORE UPDATE OR DELETE
       ON {q}.order_negotiation_proposals FOR EACH ROW EXECUTE FUNCTION {q}.prevent_negotiation_rewrite()''',
)


def _tenant_window(bind, body):
    entry, session = bind.execute(sa.text('SELECT current_user, session_user')).one()
    if entry != session or not bind.execute(sa.text(
            "SELECT pg_has_role(current_user, 'mpango_app', 'SET')")).scalar_one():
        raise RuntimeError('NEGOTIATION_MIGRATION_AUTHORITY_REQUIRED')
    savepoint = bind.begin_nested()
    try:
        bind.execute(sa.text('SET ROLE mpango_app'))
        if bind.execute(sa.text('SELECT current_user')).scalar_one() != 'mpango_app':
            raise RuntimeError('NEGOTIATION_MIGRATION_IDENTITY_DRIFT')
        body()
        bind.execute(sa.text('RESET ROLE'))
        if bind.execute(sa.text('SELECT current_user')).scalar_one() != entry:
            raise RuntimeError('NEGOTIATION_MIGRATION_IDENTITY_DRIFT')
        savepoint.commit()
    except BaseException:
        try:
            savepoint.rollback()
            bind.execute(sa.text('RESET ROLE'))
            if bind.execute(sa.text('SELECT current_user')).scalar_one() != entry:
                raise RuntimeError('NEGOTIATION_MIGRATION_IDENTITY_DRIFT')
        except BaseException:
            bind.invalidate()
            raise RuntimeError('NEGOTIATION_MIGRATION_CONNECTION_DISCARDED')
        raise


def upgrade():
    bind = op.get_bind()
    current, session, owner = bind.execute(sa.text(
        'SELECT current_user,session_user,pg_get_userbyid(proowner) FROM pg_proc '
        "WHERE oid='public.prevent_ledger_modification()'::regprocedure")).one()
    if current != session or current != owner or current == 'mpango_app':
        raise RuntimeError('NEGOTIATION_MIGRATION_AUTHORITY_REQUIRED')
    rows = bind.execute(sa.text(
        'SELECT tr.tenant_schema,tr.wholesaler_id,tr.status,w.status AS ws_status '
        'FROM public.tenant_registrations tr JOIN public.wholesalers w ON w.id=tr.wholesaler_id '
        'WHERE tr.is_deleted IS FALSE AND w.is_deleted IS FALSE ORDER BY tr.tenant_schema')).mappings().all()
    schemas = []
    for row in rows:
        schema = row['tenant_schema']
        if (not schema or not re.fullmatch(r't_[0-9a-f]{32}', schema)
                or schema != 't_' + UUID(str(row['wholesaler_id'])).hex
                or row['status'] not in {'pending_email_verification', 'email_verified', 'provisioning', 'active', 'failed'}
                or row['ws_status'] not in {'active', 'provisioning'} or schema in schemas):
            raise RuntimeError('NEGOTIATION_TENANT_REGISTRY_MISMATCH')
        schemas.append(schema)
    for schema in schemas:
        if bind.execute(sa.text('SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=:s'),
                        {'s': schema}).scalar() != 'mpango_app':
            raise RuntimeError('NEGOTIATION_TENANT_OWNER_MISMATCH')
        predecessor = bind.execute(sa.text(
            'SELECT c.oid,c.relkind::text AS relkind,pg_get_userbyid(c.relowner) AS owner '
            'FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace '
            "WHERE n.nspname=:s AND c.relname='orders'"), {'s': schema}).mappings().one_or_none()
        if (predecessor is None or predecessor['relkind'] != 'r' or predecessor['owner'] != 'mpango_app'
                or not bind.execute(sa.text(
                    'SELECT EXISTS (SELECT 1 FROM pg_attribute a JOIN pg_constraint k ON k.conrelid=a.attrelid '
                    "AND k.contype='p' WHERE a.attrelid=:oid AND a.attname='id' AND NOT a.attisdropped "
                    "AND a.attnotnull AND a.atttypid='uuid'::regtype AND k.conkey=ARRAY[a.attnum])"),
                    {'oid': predecessor['oid']}).scalar_one()):
            raise RuntimeError('NEGOTIATION_PREDECESSOR_MALFORMED')
        if bind.execute(sa.text(
            'SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace '
            "WHERE n.nspname=:s AND c.relname='order_negotiation_proposals')"), {'s': schema}).scalar_one():
            raise RuntimeError('NEGOTIATION_PREDECESSOR_ALREADY_MODIFIED')
    for schema in schemas:
        def install(schema=schema):
            for ddl in PROPOSAL_DDL:
                bind.execute(sa.text(ddl.format(q='"' + schema + '"')))
        _tenant_window(bind, install)


def downgrade():
    raise RuntimeError('042 is forward-only: restore a paired backup to preserve commercial proposal and consent history')
