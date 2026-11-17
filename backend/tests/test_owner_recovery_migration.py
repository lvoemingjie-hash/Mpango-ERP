"""Real PostgreSQL DDL controls; no business ASGI in the migration process."""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, text, event
from sqlalchemy.exc import IntegrityError


def load_migration():
    p=Path(__file__).parents[1]/'alembic/versions/046_staff_credential_recovery.py'
    spec=importlib.util.spec_from_file_location('recovery_migration_046',p)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('fail_after_create',[False,True])
def test_actual_046_ddl_and_outer_rollback_preserve_existing_tokens(fail_after_create):
    url=os.environ['TEST_MIGRATION_DATABASE_URL'].replace('postgresql+asyncpg://','postgresql://',1)
    engine=create_engine(url)
    with engine.connect() as db:
        before_oid=db.scalar(text("SELECT 'public.staff_credential_recovery_tokens'::regclass::oid"))
        before=db.execute(text('SELECT * FROM public.staff_credential_recovery_tokens ORDER BY id')).all()
        db.rollback();transaction=db.begin();module=load_migration();module.op=Operations(MigrationContext.configure(db));observed=[]
        def inject(connection,cursor,statement,parameters,context,many):
            if fail_after_create and statement.startswith('CREATE UNIQUE INDEX ux_staff_recovery_active'):
                observed.append('AFTER_TABLE_BEFORE_INDEX');raise RuntimeError('SYNTHETIC_RECOVERY_MIGRATION_FAILURE')
        try:
            db.execute(text('DROP TABLE public.staff_credential_recovery_tokens'))
            event.listen(db,'before_cursor_execute',inject)
            if fail_after_create:
                with pytest.raises(RuntimeError,match='SYNTHETIC_RECOVERY_MIGRATION_FAILURE'):module.upgrade()
                assert observed==['AFTER_TABLE_BEFORE_INDEX']
            else:
                module.upgrade()
                assert db.scalar(text("SELECT has_table_privilege('reporting_user','public.staff_credential_recovery_tokens','SELECT')")) is False
                assert db.scalar(text("SELECT has_table_privilege('mpango_app','public.staff_credential_recovery_tokens','DELETE')")) is False
                tenant=db.scalar(text('SELECT id FROM public.wholesalers WHERE is_deleted IS FALSE ORDER BY id LIMIT 1'));assert tenant
                values={'t':tenant,'u':uuid4(),'a':uuid4(),'e':'migration@example.com','h':uuid4().hex*2}
                db.execute(text("INSERT INTO public.staff_credential_recovery_tokens(tenant_id,user_id,initiator_user_id,email,membership_version,target_credential_epoch,token_hash,expires_at) VALUES (:t,:u,:a,:e,1,1,:h,now()+interval '15 minutes')"),values)
                for assignment in ["purpose='setup'",'membership_version=0','target_credential_epoch=0',"expires_at=created_at-interval '1 second'","email='UPPER@EXAMPLE.COM'","used_at=now(),revoked_at=now()"]:
                    with pytest.raises(IntegrityError) as rejected:
                        with db.begin_nested():db.execute(text('UPDATE public.staff_credential_recovery_tokens SET '+assignment))
                    assert rejected.value.orig.pgcode=='23514'
        finally:
            event.remove(db,'before_cursor_execute',inject)
            transaction.rollback()
        assert db.scalar(text("SELECT 'public.staff_credential_recovery_tokens'::regclass::oid"))==before_oid
        assert db.execute(text('SELECT * FROM public.staff_credential_recovery_tokens ORDER BY id')).all()==before
    engine.dispose()
