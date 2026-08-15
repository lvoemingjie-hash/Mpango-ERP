"""PW1-R4-A probe 3b: fix candidates (SQLAlchemy 2.0.45 asyncpg dialect).
`prepared_statement_cache_size` is passed via connect_args for the asyncpg
dialect's statement-cache (SQLAlchemy's _AsyncAdapt_asyncpg_connection cache),
while asyncpg's own connection-level cache uses `statement_cache_size`.
"""
import asyncio, os, sys, uuid
sys.path.insert(0, r"C:\Users\Jeff0\pw1_r2_worktree\backend")
os.environ.setdefault("MPANGO_ENV", "test")
URL = "postgresql+asyncpg://mpango_tester:tester_pw_25440@127.0.0.1:25440/test_pw1r4a"

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

async def cycle(engine, label):
    a = f"t_fx_a_{uuid.uuid4().hex[:8]}"
    ddl_engine = create_async_engine(URL, pool_size=1)
    sql = 'SELECT val FROM probe WHERE id = :i'
    try:
        async with engine.connect() as c:
            await c.execute(text(f'CREATE SCHEMA "{a}"'))
            await c.execute(text(f'CREATE TABLE "{a}".probe (id int, val int)'))
            await c.execute(text(f'INSERT INTO "{a}".probe VALUES (1, 111)'))
            await c.commit()
        async with AsyncSession(engine) as s:
            s.info["tenant_schema"] = a
            await s.execute(text(f'SET LOCAL search_path TO "{a}", public'))
            r = await s.execute(text(sql), {"i": 1}); v1 = r.scalar()
            await s.commit()
        async with ddl_engine.connect() as c:
            await c.execute(text(f'ALTER TABLE "{a}".probe ALTER COLUMN val TYPE bigint'))
            await c.commit()
        async with AsyncSession(engine) as s:
            s.info["tenant_schema"] = a
            await s.execute(text(f'SET LOCAL search_path TO "{a}", public'))
            r = await s.execute(text(sql), {"i": 1}); v2 = r.scalar()
            await s.commit()
        print(f"[{label}] OK: A1={v1} A2={v2} (RED closed)")
        return True
    except Exception as e:
        chain = []
        cur = e
        while cur:
            chain.append(type(cur).__name__); cur = cur.__cause__ or cur.__context__
        print(f"[{label}] ERROR: {' -> '.join(chain)[:220]}")
        return False
    finally:
        async with ddl_engine.connect() as c:
            await c.execute(text(f'DROP SCHEMA IF EXISTS "{a}" CASCADE'))
            await c.commit()
        await ddl_engine.dispose()

async def main():
    SS = {"server_settings": {"application_name": "r4a_probe", "jit": "off"}}
    # candidate 1: SQLAlchemy asyncpg dialect prepared_statement_cache_size=0 (via connect_args)
    e1 = create_async_engine(URL, pool_size=1,
        connect_args={"prepared_statement_cache_size": 0, **SS})
    await cycle(e1, "prepared_statement_cache_size=0 (dialect connect_args)")
    await e1.dispose()
    # candidate 2: asyncpg statement_cache_size=0 (asyncpg connect kwarg)
    e2 = create_async_engine(URL, pool_size=1,
        connect_args={"statement_cache_size": 0, **SS})
    await cycle(e2, "statement_cache_size=0 (asyncpg kwarg)")
    await e2.dispose()
    # candidate 3: both
    e3 = create_async_engine(URL, pool_size=1,
        connect_args={"prepared_statement_cache_size": 0, "statement_cache_size": 0, **SS})
    await cycle(e3, "both=0")
    await e3.dispose()
    # control: defaults (RED must stay alive)
    e4 = create_async_engine(URL, pool_size=1, connect_args=dict(SS))
    await cycle(e4, "control default (expect RED)")
    await e4.dispose()

asyncio.run(main())
