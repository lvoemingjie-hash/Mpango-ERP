"""PW1-R4-A probe 2: H5 mechanism on the PRODUCTION engine.

Production AsyncSessionLocal (pool_size=1) + get_tenant_db cycles, with DDL
on tenant A's table arriving from a second connection (the production shape:
tenant-B provisioning/migration DDL invalidating plans pooled for tenant A).
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, r"C:\Users\Jeff0\pw1_r2_worktree\backend")
os.environ.setdefault("MPANGO_ENV", "test")
os.environ["DATABASE_URL"] = "postgresql://mpango_tester:tester_pw_25440@127.0.0.1:25440/test_pw1r4a"
os.environ["DB_POOL_SIZE"] = "1"
os.environ["DB_MAX_OVERFLOW"] = "0"

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from database.session import AsyncSessionLocal, async_engine, get_tenant_db


async def q(tenant: str, sql: str, params: dict | None = None):
    out = None
    async for session in get_tenant_db(tenant):
        result = await session.execute(text(sql), params or {})
        out = result.scalar()
    return out


async def main():
    a = f"t_r4a_a_{uuid.uuid4().hex[:8]}"
    b = f"t_r4a_b_{uuid.uuid4().hex[:8]}"
    print(f"A={a} B={b} | pool size:", async_engine.pool.size())

    async with AsyncSessionLocal() as s:
        for sch, seed in ((a, 111), (b, 222)):
            await s.execute(text(f'CREATE SCHEMA "{sch}"'))
            await s.execute(text(f'CREATE TABLE "{sch}".probe (id int, val int)'))
            await s.execute(text(f'INSERT INTO "{sch}".probe VALUES (1, :v)'), {"v": seed})
        await s.commit()

    ddl_engine = create_async_engine(
        os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=1,
    )

    sql = 'SELECT val FROM probe WHERE id = :i'
    try:
        # Warm both tenants' plans on the PRODUCTION pooled connection.
        print("A1:", await q(a, sql, {"i": 1}))
        print("B1:", await q(b, sql, {"i": 1}))

        # Production-shaped DDL: a tenant reconcile/migration ALTERs tenant A's
        # table from its own connection while the shared pool holds A's plan.
        async with ddl_engine.connect() as c:
            await c.execute(text(f'ALTER TABLE "{a}".probe ALTER COLUMN val TYPE bigint'))
            await c.commit()
        print("DDL applied (A.val int -> bigint)")

        # A2 must now hit the invalidated cached plan.
        try:
            print("A2:", await q(a, sql, {"i": 1}))
            print("A2 SUCCEEDED (no error)")
        except Exception as e:
            chain = []
            cur = e
            while cur:
                chain.append(type(cur).__module__ + "." + type(cur).__name__)
                cur = cur.__cause__ or cur.__context__
            print("A2 ERROR:", " -> ".join(chain)[:400])

        # B leg after the DDL storm.
        try:
            print("B2:", await q(b, sql, {"i": 1}))
        except Exception as e:
            print("B2 ERROR:", type(e).__name__)
    finally:
        async with AsyncSessionLocal() as s:
            for sch in (a, b):
                await s.execute(text(f'DROP SCHEMA IF EXISTS "{sch}" CASCADE'))
            await s.commit()
        await async_engine.dispose()
        await ddl_engine.dispose()


asyncio.run(main())
