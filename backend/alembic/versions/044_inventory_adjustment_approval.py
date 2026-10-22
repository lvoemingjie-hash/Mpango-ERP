"""Single-level inventory approval; no historical Owner inference."""
import re
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = '044_inventory_adjustment_approval'
down_revision = '043_staff_authority_and_credentials'
branch_labels = None
depends_on = None

TENANT_DDL = (
    """ALTER TABLE {q}.staff_authority
       ADD COLUMN policy_version BIGINT NOT NULL DEFAULT 1 CHECK (policy_version>0),
       ADD COLUMN owner_direct_enabled BOOLEAN NOT NULL DEFAULT true""",
    """ALTER TABLE {q}.inventory_stocks ADD COLUMN stock_revision BIGINT NOT NULL DEFAULT 1
       CONSTRAINT ck_stock_revision CHECK (stock_revision>0)""",
    """CREATE TABLE {q}.inventory_adjustment_approvers (
       user_id UUID PRIMARY KEY REFERENCES {q}.users(id) ON DELETE RESTRICT)""",
    """CREATE TABLE {q}.inventory_adjustment_requests (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       requester_id UUID NOT NULL REFERENCES {q}.users(id) ON DELETE RESTRICT,
       sellable_unit_id UUID NOT NULL REFERENCES {q}.skus(id) ON DELETE RESTRICT,
       stock_id UUID NOT NULL REFERENCES {q}.inventory_stocks(id) ON DELETE RESTRICT,
       payload JSONB NOT NULL, delta NUMERIC(12,2) NOT NULL,
       policy_version BIGINT NOT NULL CHECK (policy_version>0),
       create_key_digest VARCHAR(64) NOT NULL, create_fingerprint VARCHAR(64) NOT NULL,
       version BIGINT NOT NULL DEFAULT 1 CHECK (version>0),
       status VARCHAR(24) NOT NULL DEFAULT 'pending',
       decision_actor_id UUID REFERENCES {q}.users(id) ON DELETE RESTRICT,
       decision_key_digest VARCHAR(64), decision_fingerprint VARCHAR(64),
       result JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), decided_at TIMESTAMPTZ,
       CONSTRAINT uq_adjustment_request_key UNIQUE(requester_id,create_key_digest),
       CONSTRAINT ck_adjustment_delta CHECK (delta <> 0 AND delta > '-Infinity'::numeric AND delta < 'Infinity'::numeric),
       CONSTRAINT ck_adjustment_state CHECK (
           (status='pending' AND version=1 AND decision_actor_id IS NULL AND decided_at IS NULL
            AND decision_key_digest IS NULL AND decision_fingerprint IS NULL AND result IS NULL) OR
           (status IN ('approved_applied','rejected','withdrawn','applied_direct') AND version=2
            AND decision_actor_id IS NOT NULL AND decided_at IS NOT NULL
            AND decision_key_digest IS NOT NULL AND decision_fingerprint IS NOT NULL AND result IS NOT NULL)),
       CONSTRAINT ck_adjustment_no_self_approval CHECK (status <> 'approved_applied' OR decision_actor_id <> requester_id),
       CONSTRAINT ck_adjustment_direct_actor CHECK (status <> 'applied_direct' OR decision_actor_id=requester_id))""",
    """ALTER TABLE {q}.inventory_movements ADD COLUMN manual_adjustment_id UUID
       CONSTRAINT fk_movement_manual_adjustment REFERENCES {q}.inventory_adjustment_requests(id) ON DELETE RESTRICT,
       ADD CONSTRAINT uq_movement_manual_adjustment UNIQUE(manual_adjustment_id)""",
    """CREATE FUNCTION {q}.advance_stock_revision() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $m2$
       BEGIN
         IF TG_OP='INSERT' THEN NEW.stock_revision := 1;
         ELSIF ROW(NEW.quantity_on_hand,NEW.quantity_reserved,NEW.is_deleted)
             IS DISTINCT FROM ROW(OLD.quantity_on_hand,OLD.quantity_reserved,OLD.is_deleted)
         THEN NEW.stock_revision := OLD.stock_revision+1;
         ELSE NEW.stock_revision := OLD.stock_revision;
         END IF;
         RETURN NEW;
       END; $m2$""",
    """CREATE TRIGGER stock_revision_monotonic BEFORE INSERT OR UPDATE ON {q}.inventory_stocks
       FOR EACH ROW EXECUTE FUNCTION {q}.advance_stock_revision()""",
    """CREATE FUNCTION {q}.protect_adjustment_request() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $m2$
       BEGIN
         IF TG_OP='DELETE' THEN RAISE EXCEPTION 'ADJUSTMENT_IMMUTABLE'; END IF;
         IF OLD.status <> 'pending' OR NEW.status='pending' OR
           ROW(NEW.id,NEW.requester_id,NEW.sellable_unit_id,NEW.stock_id,NEW.payload,NEW.delta,
               NEW.policy_version,NEW.create_key_digest,NEW.create_fingerprint,NEW.created_at)
           IS DISTINCT FROM
           ROW(OLD.id,OLD.requester_id,OLD.sellable_unit_id,OLD.stock_id,OLD.payload,OLD.delta,
               OLD.policy_version,OLD.create_key_digest,OLD.create_fingerprint,OLD.created_at)
         THEN RAISE EXCEPTION 'ADJUSTMENT_IMMUTABLE'; END IF;
         RETURN NEW;
       END; $m2$""",
    """CREATE TRIGGER adjustment_request_immutable BEFORE UPDATE OR DELETE ON {q}.inventory_adjustment_requests
       FOR EACH ROW EXECUTE FUNCTION {q}.protect_adjustment_request()""",
    """CREATE FUNCTION {q}.protect_manual_movement() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $m2$
       BEGIN
         IF OLD.manual_adjustment_id IS NOT NULL THEN RAISE EXCEPTION 'MANUAL_MOVEMENT_IMMUTABLE'; END IF;
         IF TG_OP='UPDATE' AND NEW.manual_adjustment_id IS NOT NULL THEN RAISE EXCEPTION 'MANUAL_MOVEMENT_IMMUTABLE'; END IF;
         IF TG_OP='DELETE' THEN RETURN OLD; END IF;
         RETURN NEW;
       END; $m2$""",
    """CREATE TRIGGER manual_movement_immutable BEFORE UPDATE OR DELETE ON {q}.inventory_movements
       FOR EACH ROW EXECUTE FUNCTION {q}.protect_manual_movement()""",
    """INSERT INTO {q}.inventory_adjustment_approvers(user_id)
       SELECT owner_user_id FROM {q}.staff_authority WHERE state='verified'""",
)


def upgrade():
    bind = op.get_bind()
    current, session, owner = bind.execute(sa.text(
        "SELECT current_user,session_user,pg_get_userbyid(proowner) FROM pg_proc "
        "WHERE oid='public.prevent_ledger_modification()'::regprocedure")).one()
    if current != session or current != owner or current == 'mpango_app':
        raise RuntimeError('ADJUSTMENT_MIGRATION_AUTHORITY_REQUIRED')
    rows = bind.execute(sa.text(
        "SELECT tr.id,tr.tenant_schema,tr.wholesaler_id,tr.status,w.status AS ws_status "
        "FROM public.tenant_registrations tr JOIN public.wholesalers w ON w.id=tr.wholesaler_id "
        "WHERE tr.is_deleted IS FALSE AND w.is_deleted IS FALSE ORDER BY tr.tenant_schema")).mappings().all()
    seen = set()
    for row in rows:
        schema = row['tenant_schema']
        if (not schema or not re.fullmatch(r't_[0-9a-f]{32}', schema)
                or schema != 't_' + UUID(str(row['wholesaler_id'])).hex or schema in seen
                or row['status'] not in {'pending_email_verification','email_verified','provisioning','active','failed'}
                or row['ws_status'] not in {'active','provisioning'}):
            raise RuntimeError('ADJUSTMENT_TENANT_REGISTRY_MISMATCH')
        seen.add(schema)
        if bind.execute(sa.text('SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=:s'),
                        {'s': schema}).scalar() != 'mpango_app':
            raise RuntimeError('ADJUSTMENT_TENANT_OWNER_MISMATCH')
    for row in rows:
        q = '"' + row['tenant_schema'] + '"'
        entry = bind.execute(sa.text('SELECT current_user')).scalar_one()
        savepoint = bind.begin_nested()
        try:
            bind.execute(sa.text('SET ROLE mpango_app'))
            authority = bind.execute(sa.text(f'SELECT * FROM {q}.staff_authority WHERE singleton=1 FOR UPDATE')).mappings().one()
            if authority['state'] == 'verified':
                valid = bind.execute(sa.text(
                    f"SELECT count(*) FROM {q}.users u WHERE u.id=:u AND u.is_active IS TRUE AND u.is_deleted IS FALSE "
                    "AND NOT EXISTS (SELECT 1 FROM public.wholesaler_retailer_bindings b "
                    "WHERE b.wholesaler_id=:t AND b.tenant_user_id=u.id)"),
                    {'u': authority['owner_user_id'], 't': row['wholesaler_id']}).scalar_one()
                if (valid != 1 or authority['tenant_id'] != row['wholesaler_id']
                        or authority['registration_id'] != row['id']):
                    raise RuntimeError('OWNER_MAPPING_REQUIRED')
            for statement in TENANT_DDL:
                bind.execute(sa.text(statement.format(q=q)))
            for code in ('inventory:adjustments:request','inventory:adjustments:read','inventory:adjustments:approve'):
                bind.execute(sa.text(f'INSERT INTO {q}.permissions(code,description) VALUES (:c,:description) ON CONFLICT(code) DO NOTHING'), {'c':code,'description':code})
            # Only the managed warehouse template gets request/read by default.
            bind.execute(sa.text(
                f"INSERT INTO {q}.role_permissions(role_id,permission_id) SELECT t.role_id,p.id "
                f"FROM {q}.staff_role_templates t CROSS JOIN {q}.permissions p "
                "WHERE t.template_key='warehouse' AND p.code IN ('inventory:adjustments:request','inventory:adjustments:read') "
                "AND p.is_deleted IS FALSE ON CONFLICT DO NOTHING"))
            bind.execute(sa.text('RESET ROLE'))
            if bind.execute(sa.text('SELECT current_user')).scalar_one() != entry:
                raise RuntimeError('ADJUSTMENT_MIGRATION_IDENTITY_DRIFT')
            savepoint.commit()
        except BaseException:
            savepoint.rollback()
            bind.execute(sa.text('RESET ROLE'))
            if bind.execute(sa.text('SELECT current_user')).scalar_one() != entry:
                bind.invalidate()
            raise


def downgrade():
    raise RuntimeError('044 is forward-only: retain approval, stock revision, movement and audit history')
