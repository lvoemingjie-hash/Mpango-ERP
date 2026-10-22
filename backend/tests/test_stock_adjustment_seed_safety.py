import pytest
from scripts.seed_demo_data import _admit_fresh_task_demo_target


async def test_actual_owned_fresh_demo_admission_then_occupied_rejection(tmp_path,monkeypatch):
    """Only the task's existing PG cluster; never execute the actual demo seeder."""
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys
    from uuid import uuid4
    import psycopg2
    from psycopg2 import sql
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from tests.mpango_invariants_r0_support import verify_task_database_ownership_sync
    verify_task_database_ownership_sync()
    admin=os.environ['MPANGO_INVARIANTS_R0_ADMIN_DATABASE_URL']
    migrate=make_url(os.environ['MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL'])
    app=make_url(os.environ['TEST_DATABASE_URL'])
    database='test_m2_seed_admission_'+uuid4().hex
    connection=psycopg2.connect(admin);connection.autocommit=True
    engine=None
    record={'database':database,'same_verified_cluster':True,'actual_seed_executed':False,'calls':[]}
    root=Path(os.environ['STAFF_M1_PRIVATE_DIR'])
    receipt=root/(database+'.json')
    def save():receipt.write_text(json.dumps(record,indent=2)+'\n');os.chmod(receipt,0o600)
    save()
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(database),sql.Identifier(migrate.username)))
    save()
    try:
        mu=migrate.set(database=database).render_as_string(hide_password=False)
        au=app.set(database=database).render_as_string(hide_password=False)
        env={**os.environ,'DATABASE_URL':mu,'MPANGO_DB_ADMIN_URL':admin,'MPANGO_DB_MIGRATE_URL':mu,'MPANGO_DB_APP_URL':au}
        for label,argv in [('migrate',[sys.executable,'-B','-m','alembic','upgrade','044_inventory_adjustment_approval']),
                           ('grants',[sys.executable,'-B','scripts/provision_runtime_db_roles.py','--apply-grants'])]:
            result=subprocess.run(argv,cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,timeout=90)
            for stream,data in [('stdout',result.stdout),('stderr',result.stderr)]:
                path=root/(database+'-'+label+'.'+stream);path.write_bytes(data);os.chmod(path,0o600)
            record['calls'].append({'label':label,'argv':argv,'rc':result.returncode});save()
            assert result.returncode==0,'M2_SEED_ADMISSION_PREPARATION'
        cid=os.environ['MPANGO_INVARIANTS_R0_PG_CONTAINER']
        info=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
        manifest=tmp_path/'fresh-demo-task.json'
        manifest.write_text(json.dumps({'container_id':cid,'task':info['Config']['Labels']['mpango.task'],
            'owner':info['Config']['Labels']['mpango.owner'],'database':database}));manifest.chmod(0o600)
        monkeypatch.setenv('MPANGO_ENV','test');monkeypatch.setenv('MPANGO_FRESH_DEMO_TASK_MANIFEST',str(manifest))
        monkeypatch.setenv('DATABASE_URL',au)
        engine=create_async_engine(au.replace('postgresql://','postgresql+asyncpg://',1),poolclass=NullPool)
        async with engine.begin() as db:
            await _admit_fresh_task_demo_target(db)
            assert await db.scalar(text('SELECT count(*) FROM public.wholesalers'))==0
            await db.execute(text("INSERT INTO public.wholesalers(code,name) VALUES (:c,'Occupied seed admission')"),{'c':'SEED'+uuid4().hex[:12]})
        with pytest.raises(RuntimeError,match='FRESH_TASK_DEMO_TARGET_REQUIRED'):
            async with engine.begin() as db:await _admit_fresh_task_demo_target(db)
        async with engine.connect() as db:assert await db.scalar(text('SELECT count(*) FROM public.wholesalers'))==1
        record['fresh_admission']='PASS';record['occupied_zero_write_refusal']='PASS';save()
    finally:
        if engine is not None:await engine.dispose()
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s',(database,))
            assert cursor.fetchone()==(migrate.username,)
            cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))
        connection.close();record['dropped_exact_owned_database']=True;save()


@pytest.mark.parametrize('profile',['production','staging','test','dev'])
async def test_unknown_or_existing_seed_target_is_never_admitted(monkeypatch,profile):
    monkeypatch.setenv('MPANGO_ENV',profile)
    monkeypatch.delenv('MPANGO_FRESH_DEMO_TASK_MANIFEST',raising=False)
    class NoDatabase:
        async def scalar(self,*a,**k):raise AssertionError('UNKNOWN_SEED_TARGET_REACHED_DATABASE')
    with pytest.raises(RuntimeError,match='FRESH_TASK_DEMO_TARGET_REQUIRED'):
        await _admit_fresh_task_demo_target(NoDatabase())
