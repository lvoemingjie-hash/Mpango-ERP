"""Optional tenant media pointers. No economic row or historical migration is changed."""
import re
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = '041_catalog_product_main_image'
down_revision = '040_s1_pricing_quote_contract'
branch_labels = None
depends_on = None

MEDIA_DDL = '''CREATE TABLE {q}.catalog_product_images (
    product_id UUID CONSTRAINT catalog_product_images_pkey PRIMARY KEY,
    image_revision BIGINT NOT NULL CONSTRAINT ck_product_image_revision CHECK (image_revision >= 1),
    current_version UUID,
    variants JSONB,
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_product_image_product FOREIGN KEY (product_id) REFERENCES {q}.catalog_products(id) ON DELETE RESTRICT,
    CONSTRAINT ck_product_image_shape CHECK ((current_version IS NULL) = (variants IS NULL))
)'''


def _tenant_window(bind, body):
    entry, session = bind.execute(sa.text('SELECT current_user, session_user')).one()
    if entry != session or not bind.execute(sa.text(
            "SELECT pg_has_role(current_user, 'mpango_app', 'SET')")).scalar_one():
        raise RuntimeError('IMAGE_MIGRATION_AUTHORITY_REQUIRED')
    savepoint = bind.begin_nested()
    try:
        bind.execute(sa.text('SET ROLE mpango_app'))
        if bind.execute(sa.text('SELECT current_user')).scalar_one() != 'mpango_app':
            raise RuntimeError('IMAGE_MIGRATION_HANDSHAKE')
        body()
        bind.execute(sa.text('RESET ROLE'))
        if bind.execute(sa.text('SELECT current_user')).scalar_one() != entry:
            raise RuntimeError('IMAGE_MIGRATION_IDENTITY_DRIFT')
        savepoint.commit()
    except BaseException:
        try:
            savepoint.rollback()
            bind.execute(sa.text('RESET ROLE'))
            if bind.execute(sa.text('SELECT current_user')).scalar_one() != entry:
                raise RuntimeError('IMAGE_MIGRATION_IDENTITY_DRIFT')
        except BaseException:
            bind.invalidate()
            raise RuntimeError('IMAGE_MIGRATION_CONNECTION_DISCARDED')
        raise


def upgrade():
    bind = op.get_bind()
    current, session, owner = bind.execute(sa.text(
        "SELECT current_user,session_user,pg_get_userbyid(proowner) FROM pg_proc "
        "WHERE oid='public.prevent_ledger_modification()'::regprocedure")).one()
    if current != session or current != owner or current == 'mpango_app':
        raise RuntimeError('IMAGE_MIGRATION_AUTHORITY_REQUIRED')
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
            raise RuntimeError('IMAGE_TENANT_REGISTRY_MISMATCH')
        schemas.append(schema)
    for schema in schemas:
        if bind.execute(sa.text('SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=:s'), {'s': schema}).scalar() != 'mpango_app':
            raise RuntimeError('IMAGE_TENANT_OWNER_MISMATCH')
        # Qualified regclass resolution checks schema USAGE before SET ROLE.
        # Catalog OIDs let the SET-only migrator validate without new grants.
        predecessor = bind.execute(sa.text(
            "SELECT c.oid,c.relkind::text AS relkind,pg_get_userbyid(c.relowner) AS owner "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=:s AND c.relname='catalog_products'"), {'s': schema}).mappings().one_or_none()
        if predecessor is None:
            raise RuntimeError('IMAGE_PREDECESSOR_MISSING')
        if predecessor['relkind'] != 'r' or predecessor['owner'] != 'mpango_app' or not bind.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a "
            "JOIN pg_catalog.pg_constraint k ON k.conrelid=a.attrelid AND k.contype='p' "
            "WHERE a.attrelid=:oid AND a.attname='id' AND NOT a.attisdropped "
            "AND a.attnotnull AND a.atttypid='uuid'::regtype AND k.conkey=ARRAY[a.attnum])"),
                {'oid': predecessor['oid']}).scalar_one():
            raise RuntimeError('IMAGE_PREDECESSOR_MALFORMED')
        if bind.execute(sa.text(
            'SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n '
            "ON n.oid=c.relnamespace WHERE n.nspname=:s AND c.relname='catalog_product_images')"),
                {'s': schema}).scalar_one():
            raise RuntimeError('IMAGE_PREDECESSOR_ALREADY_MODIFIED')
    for schema in schemas:
        _tenant_window(bind, lambda schema=schema: bind.execute(sa.text(MEDIA_DDL.format(q='"' + schema + '"'))))


def downgrade():
    raise RuntimeError('041 is forward-only: restore a paired DB/media backup to recover image revisions and references')
