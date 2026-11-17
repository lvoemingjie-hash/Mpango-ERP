"""Mailbox recovery without employment or authorization changes."""
import sqlalchemy as sa
from alembic import op

revision = '046_staff_credential_recovery'
down_revision = '045_owner_staff_recovery'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    current, session, owner = bind.execute(sa.text(
        'SELECT current_user,session_user,pg_get_userbyid(proowner) FROM pg_proc '
        "WHERE oid='public.prevent_ledger_modification()'::regprocedure")).one()
    if current != session or current != owner or current == 'mpango_app':
        raise RuntimeError('STAFF_RECOVERY_MIGRATION_AUTHORITY_REQUIRED')
    bind.execute(sa.text("""CREATE TABLE public.staff_credential_recovery_tokens (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES public.wholesalers(id) ON DELETE RESTRICT,
        user_id UUID NOT NULL, initiator_user_id UUID NOT NULL,
        email VARCHAR(255) NOT NULL,
        membership_version BIGINT NOT NULL CHECK (membership_version>0),
        target_credential_epoch BIGINT NOT NULL CHECK (target_credential_epoch>0),
        token_hash VARCHAR(128) NOT NULL UNIQUE,
        purpose VARCHAR(32) NOT NULL DEFAULT 'staff_credential_recovery'
            CHECK (purpose='staff_credential_recovery'),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), expires_at TIMESTAMPTZ NOT NULL,
        used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ,
        CHECK (used_at IS NULL OR revoked_at IS NULL),
        CHECK (expires_at>created_at),
        CHECK (email=lower(btrim(email)) AND email NOT LIKE '% %')
    )"""))
    bind.execute(sa.text('CREATE UNIQUE INDEX ux_staff_recovery_active '
        'ON public.staff_credential_recovery_tokens(tenant_id,user_id) '
        'WHERE used_at IS NULL AND revoked_at IS NULL'))
    bind.execute(sa.text('REVOKE ALL ON public.staff_credential_recovery_tokens FROM PUBLIC, reporting_user, reporting_role'))
    bind.execute(sa.text('GRANT SELECT, INSERT, UPDATE ON public.staff_credential_recovery_tokens TO mpango_app'))
    bind.execute(sa.text('REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER '
        'ON public.staff_credential_recovery_tokens FROM mpango_app'))


def downgrade():
    raise RuntimeError('046 is forward-only: preserve recovery and revocation history')
