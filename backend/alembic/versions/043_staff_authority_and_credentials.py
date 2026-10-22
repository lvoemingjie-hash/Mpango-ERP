"""M1 exact Owner authority; never infer or activate a historical Owner."""
import re
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = '043_staff_authority_and_credentials'
down_revision = '042_order_negotiation_proposals'
branch_labels = None
depends_on = None

TENANT_DDL = (
    '''CREATE TABLE {q}.staff_authority (
        singleton INTEGER PRIMARY KEY DEFAULT 1 CONSTRAINT ck_staff_authority_singleton CHECK (singleton=1),
        tenant_id UUID, registration_id UUID,
        owner_user_id UUID UNIQUE REFERENCES {q}.users(id) ON DELETE RESTRICT,
        state VARCHAR(16) NOT NULL DEFAULT 'unmapped', source VARCHAR(32), evidence_digest VARCHAR(64),
        authz_revision BIGINT NOT NULL DEFAULT 1 CONSTRAINT ck_staff_authority_revision CHECK (authz_revision>0),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_staff_authority_shape CHECK (
            (state='unmapped' AND owner_user_id IS NULL AND source IS NULL AND evidence_digest IS NULL) OR
            (state='verified' AND owner_user_id IS NOT NULL AND tenant_id IS NOT NULL AND registration_id IS NOT NULL
             AND source IS NOT NULL AND evidence_digest IS NOT NULL
             AND source IN ('owner_setup','approved_mapping') AND evidence_digest ~ '^[0-9a-f]{{64}}$'))
    )''',
    '''CREATE TABLE {q}.staff_role_templates (
        template_key VARCHAR(16) PRIMARY KEY CONSTRAINT ck_staff_template_key CHECK (template_key IN ('warehouse','sales','finance')),
        role_id UUID NOT NULL UNIQUE REFERENCES {q}.roles(id) ON DELETE RESTRICT,
        version BIGINT NOT NULL DEFAULT 1 CONSTRAINT ck_staff_template_version CHECK (version>0)
    )''',
    '''CREATE TABLE {q}.staff_memberships (
        user_id UUID PRIMARY KEY REFERENCES {q}.users(id) ON DELETE RESTRICT,
        template_key VARCHAR(16) NOT NULL REFERENCES {q}.staff_role_templates(template_key) ON DELETE RESTRICT,
        credential_state VARCHAR(16) NOT NULL DEFAULT 'pending' CONSTRAINT ck_staff_membership_state CHECK (credential_state IN ('pending','ready')),
        employment_state VARCHAR(16) NOT NULL DEFAULT 'invited' CONSTRAINT ck_staff_employment_state CHECK (employment_state IN ('invited','active','disabled')),
        version BIGINT NOT NULL DEFAULT 1 CONSTRAINT ck_staff_membership_version CHECK (version>0),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_staff_ready_active CHECK (employment_state<>'active' OR credential_state='ready')
    )''',
    '''CREATE FUNCTION {q}.protect_staff_owner() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $m1$
    BEGIN
        IF TG_OP='DELETE' OR (OLD.state='verified' AND
            ROW(NEW.owner_user_id,NEW.tenant_id,NEW.registration_id,NEW.state,NEW.source,NEW.evidence_digest)
            IS DISTINCT FROM ROW(OLD.owner_user_id,OLD.tenant_id,OLD.registration_id,OLD.state,OLD.source,OLD.evidence_digest)) THEN
            RAISE EXCEPTION 'OWNER_PROTECTED';
        END IF;
        RETURN NEW;
    END; $m1$''',
    '''CREATE TRIGGER staff_owner_immutable BEFORE UPDATE OR DELETE ON {q}.staff_authority
       FOR EACH ROW EXECUTE FUNCTION {q}.protect_staff_owner()''',
)

PUBLIC_DDL = (
    '''CREATE TABLE public.staff_credential_setup_tokens (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES public.wholesalers(id) ON DELETE RESTRICT,
        user_id UUID NOT NULL, email VARCHAR(255) NOT NULL,
        membership_version BIGINT NOT NULL CONSTRAINT ck_staff_token_version CHECK (membership_version>0),
        token_hash VARCHAR(128) NOT NULL UNIQUE, purpose VARCHAR(32) NOT NULL DEFAULT 'staff_credential_setup',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), expires_at TIMESTAMPTZ NOT NULL,
        used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ,
        CONSTRAINT ck_staff_token_purpose CHECK (purpose='staff_credential_setup'),
        CONSTRAINT ck_staff_token_terminal CHECK (used_at IS NULL OR revoked_at IS NULL),
        CONSTRAINT ck_staff_token_expiry CHECK (expires_at>created_at),
        CONSTRAINT ck_staff_token_email CHECK (email=lower(btrim(email)) AND email NOT LIKE '% %')
    )''',
    '''CREATE UNIQUE INDEX ux_staff_token_active ON public.staff_credential_setup_tokens(tenant_id,user_id)
       WHERE used_at IS NULL AND revoked_at IS NULL''',
    '''CREATE TABLE public.staff_stock_audit_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES public.wholesalers(id) ON DELETE RESTRICT,
        actor_id UUID NOT NULL, event_type VARCHAR(48) NOT NULL, subject_id UUID,
        details JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )''',
    '''CREATE FUNCTION public.prevent_staff_audit_rewrite() RETURNS trigger
       LANGUAGE plpgsql SET search_path=pg_catalog AS $m1$
       BEGIN RAISE EXCEPTION 'STAFF_AUDIT_IMMUTABLE'; END; $m1$''',
    '''CREATE TRIGGER staff_audit_immutable BEFORE UPDATE OR DELETE ON public.staff_stock_audit_events
       FOR EACH ROW EXECUTE FUNCTION public.prevent_staff_audit_rewrite()''',
    'REVOKE ALL ON public.staff_stock_audit_events FROM PUBLIC',
    'GRANT SELECT, INSERT ON public.staff_stock_audit_events TO mpango_app',
    'REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.staff_stock_audit_events FROM mpango_app',
)


def _tenant_window(bind, body):
    entry, session = bind.execute(sa.text('SELECT current_user,session_user')).one()
    if entry != session or not bind.execute(sa.text("SELECT pg_has_role(current_user,'mpango_app','SET')")).scalar_one():
        raise RuntimeError('STAFF_MIGRATION_AUTHORITY_REQUIRED')
    savepoint = bind.begin_nested()
    try:
        bind.execute(sa.text('SET ROLE mpango_app'))
        body()
        bind.execute(sa.text('RESET ROLE'))
        if bind.execute(sa.text('SELECT current_user')).scalar_one() != entry:
            raise RuntimeError('STAFF_MIGRATION_IDENTITY_DRIFT')
        savepoint.commit()
    except BaseException:
        try:
            savepoint.rollback()
            bind.execute(sa.text('RESET ROLE'))
            if bind.execute(sa.text('SELECT current_user')).scalar_one() != entry:
                raise RuntimeError('STAFF_MIGRATION_IDENTITY_DRIFT')
        except BaseException:
            bind.invalidate()
            raise RuntimeError('STAFF_MIGRATION_CONNECTION_DISCARDED') from None
        raise


def upgrade():
    bind = op.get_bind()
    current, session, owner = bind.execute(sa.text(
        'SELECT current_user,session_user,pg_get_userbyid(proowner) FROM pg_proc '
        "WHERE oid='public.prevent_ledger_modification()'::regprocedure")).one()
    if current != session or current != owner or current == 'mpango_app':
        raise RuntimeError('STAFF_MIGRATION_AUTHORITY_REQUIRED')
    rows = bind.execute(sa.text(
        'SELECT tr.id,tr.tenant_schema,tr.wholesaler_id,tr.status,w.status AS ws_status '
        'FROM public.tenant_registrations tr JOIN public.wholesalers w ON w.id=tr.wholesaler_id '
        'WHERE tr.is_deleted IS FALSE AND w.is_deleted IS FALSE ORDER BY tr.tenant_schema')).mappings().all()
    seen = set()
    for row in rows:
        schema = row['tenant_schema']
        if (not schema or not re.fullmatch(r't_[0-9a-f]{32}', schema)
                or schema != 't_' + UUID(str(row['wholesaler_id'])).hex or schema in seen
                or row['status'] not in {'pending_email_verification','email_verified','provisioning','active','failed'}
                or row['ws_status'] not in {'active','provisioning'}):
            raise RuntimeError('STAFF_TENANT_REGISTRY_MISMATCH')
        seen.add(schema)
        if bind.execute(sa.text('SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=:s'),
                        {'s': schema}).scalar() != 'mpango_app':
            raise RuntimeError('STAFF_TENANT_OWNER_MISMATCH')
        for name in ('staff_authority','staff_role_templates','staff_memberships'):
            # Inspect the catalog without requiring USAGE on app-owned schemas.
            # Tenant DDL itself remains inside the explicit SET ROLE window.
            if bind.execute(sa.text(
                'SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace '
                'WHERE n.nspname=:schema AND c.relname=:name)'),
                {'schema':schema,'name':name}).scalar_one():
                raise RuntimeError('STAFF_PREDECESSOR_ALREADY_MODIFIED')
    for statement in PUBLIC_DDL:
        bind.execute(sa.text(statement))
    for row in rows:
        q = '"' + row['tenant_schema'] + '"'
        def install():
            for statement in TENANT_DDL:
                bind.execute(sa.text(statement.format(q=q)))
            bind.execute(sa.text(f'INSERT INTO {q}.staff_authority (tenant_id,registration_id) VALUES (:t,:r)'),
                         {'t': row['wholesaler_id'], 'r': row['id']})
            for action in ('confirm','ship','cancel','return'):
                code = 'orders:' + action
                bind.execute(sa.text(f'INSERT INTO {q}.permissions (code,description) VALUES (:code,:description) ON CONFLICT (code) DO NOTHING'), {'code': code,'description':code})
                bind.execute(sa.text(
                    f'INSERT INTO {q}.role_permissions (role_id,permission_id) '
                    f'SELECT DISTINCT r.id,new.id FROM {q}.roles r JOIN {q}.role_permissions rp ON rp.role_id=r.id '
                    f'JOIN {q}.permissions old ON old.id=rp.permission_id CROSS JOIN {q}.permissions new '
                    "WHERE old.code='orders:update' AND old.is_deleted IS FALSE AND r.is_deleted IS FALSE "
                    'AND new.code=:code AND new.is_deleted IS FALSE ON CONFLICT DO NOTHING'), {'code': code})
        _tenant_window(bind, install)


def downgrade():
    raise RuntimeError('043 is forward-only: preserve Owner, employment, credential and audit history; disable new writes instead')
