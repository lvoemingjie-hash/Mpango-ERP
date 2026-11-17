"""Credential generations only; recovery issuance/consumption is not opened."""
import re
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = "045_owner_staff_recovery"
down_revision = "044_inventory_adjustment_approval"
branch_labels = None
depends_on = None

# Keep independent tenant bootstrap byte-equivalent; no runtime imports here.
TENANT_DDL = (
    """ALTER TABLE {q}.users ADD COLUMN credential_epoch BIGINT NOT NULL DEFAULT 1
       CONSTRAINT ck_users_credential_epoch CHECK (credential_epoch>0)""",
    """CREATE FUNCTION {q}.advance_credential_epoch() RETURNS trigger LANGUAGE plpgsql
       SET search_path=pg_catalog AS $epoch$
       BEGIN
         IF TG_OP='INSERT' THEN NEW.credential_epoch := 1;
         ELSIF ROW(NEW.password_hash,NEW.email,NEW.is_active,NEW.is_deleted)
             IS DISTINCT FROM ROW(OLD.password_hash,OLD.email,OLD.is_active,OLD.is_deleted)
         THEN NEW.credential_epoch := OLD.credential_epoch+1;
         ELSE NEW.credential_epoch := OLD.credential_epoch;
         END IF;
         RETURN NEW;
       END; $epoch$""",
    """CREATE TRIGGER credential_epoch_monotonic BEFORE INSERT OR UPDATE ON {q}.users
       FOR EACH ROW EXECUTE FUNCTION {q}.advance_credential_epoch()""",
)


def _targets(bind):
    """Account for existing users, including the two supported legacy schemas.

    UUID tenants require the authoritative registration binding. The existing
    development/supply schemas t_dev/t_test never acquire an Owner mapping or
    tenant authority here; they only receive the same users column/guard.
    """
    rows = bind.execute(sa.text(
        "SELECT tr.tenant_schema,tr.wholesaler_id,tr.status,w.status AS ws_status "
        "FROM public.tenant_registrations tr JOIN public.wholesalers w ON w.id=tr.wholesaler_id "
        "WHERE tr.is_deleted IS FALSE AND w.is_deleted IS FALSE ORDER BY tr.tenant_schema"
    )).mappings().all()
    registered = {}
    for row in rows:
        schema = row["tenant_schema"]
        if (not schema or schema != "t_" + UUID(str(row["wholesaler_id"])).hex
                or schema in registered
                or row["status"] not in {"pending_email_verification", "email_verified", "provisioning", "active", "failed"}
                or row["ws_status"] not in {"active", "provisioning", "suspended", "deactivated"}):
            raise RuntimeError("CREDENTIAL_EPOCH_TENANT_REGISTRY_MISMATCH")
        registered[schema] = row
    objects = bind.execute(sa.text(
        "SELECT n.nspname AS schema,c.relkind::text AS relkind,pg_get_userbyid(n.nspowner) AS schema_owner,"
        "pg_get_userbyid(c.relowner) AS table_owner FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relname='users' AND n.nspname LIKE 't\\_%' ESCAPE '\\' ORDER BY n.nspname"
    )).mappings().all()
    targets = []
    for row in objects:
        schema = row["schema"]
        if (not re.fullmatch(r"t_[0-9a-f]{32}|t_dev|t_test", schema)
                or (schema not in {"t_dev", "t_test"} and schema not in registered)
                or row["relkind"] != "r" or row["schema_owner"] != "mpango_app"
                or row["table_owner"] != "mpango_app"):
            raise RuntimeError("CREDENTIAL_EPOCH_TENANT_OBJECT_MISMATCH")
        targets.append(schema)
    for schema, row in registered.items():
        if schema not in targets and (row["status"] == "active" or row["ws_status"] != "provisioning"):
            raise RuntimeError("CREDENTIAL_EPOCH_TENANT_USERS_MISSING")
    return targets


def upgrade():
    bind = op.get_bind()
    current, session, owner = bind.execute(sa.text(
        "SELECT current_user,session_user,pg_get_userbyid(proowner) FROM pg_proc "
        "WHERE oid='public.prevent_ledger_modification()'::regprocedure"
    )).one()
    if current != session or current != owner or current == "mpango_app":
        raise RuntimeError("CREDENTIAL_EPOCH_MIGRATION_AUTHORITY_REQUIRED")
    # Validate the complete target set before performing any tenant DDL.
    targets = _targets(bind)
    for schema in targets:
        present = bind.execute(sa.text(
            "SELECT EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:s "
            "AND c.relname='users' AND a.attname='credential_epoch' AND NOT a.attisdropped) "
            "OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname=:s AND p.proname='advance_credential_epoch')"
        ), {"s": schema}).scalar_one()
        if present:
            raise RuntimeError("CREDENTIAL_EPOCH_UNEXPECTED_EXISTING_OBJECT")
    for schema in targets:
        entry = bind.execute(sa.text("SELECT current_user")).scalar_one()
        savepoint = bind.begin_nested()
        try:
            bind.execute(sa.text("SET ROLE mpango_app"))
            for statement in TENANT_DDL:
                bind.execute(sa.text(statement.format(q='"' + schema + '"')))
            bind.execute(sa.text("RESET ROLE"))
            if bind.execute(sa.text("SELECT current_user")).scalar_one() != entry:
                raise RuntimeError("CREDENTIAL_EPOCH_MIGRATION_IDENTITY_DRIFT")
            savepoint.commit()
        except BaseException:
            savepoint.rollback()
            bind.execute(sa.text("RESET ROLE"))
            if bind.execute(sa.text("SELECT current_user")).scalar_one() != entry:
                bind.invalidate()
            raise


def downgrade():
    raise RuntimeError("045 is forward-only: retain credential generations; never reaccept old sessions")
