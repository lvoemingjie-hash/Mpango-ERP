"""S5 Deployment Verification Script - Run after migrations."""
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# S8-SEC: Never hardcode credentials — read from environment
DB_URL = os.environ.get("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")
if not DB_URL:
    raise RuntimeError("DATABASE_URL environment variable must be set")

async def verify():
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # 1. Check sys_jobs in public schema
        result = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'sys_jobs'"
        ))
        row = result.fetchone()
        if row:
            print("✅ public.sys_jobs EXISTS")
        else:
            print("❌ public.sys_jobs MISSING")

        # 2. List all tenant schemas
        result = await conn.execute(text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%' ORDER BY schema_name"
        ))
        schemas = [r[0] for r in result.fetchall()]
        print(f"\n📋 Tenant schemas found: {schemas if schemas else '(none)'}")

        # 3. Check ledger_entries in each tenant schema
        for schema in schemas:
            result = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema = '{schema}' AND table_name = 'ledger_entries'"
            ))
            row = result.fetchone()
            if row:
                print(f"✅ {schema}.ledger_entries EXISTS")
            else:
                print(f"⚠️  {schema}.ledger_entries MISSING (needs tenant migration)")

        # 4. Check alembic version
        result = await conn.execute(text(
            "SELECT version_num FROM public.alembic_version"
        ))
        row = result.fetchone()
        print(f"\n📌 Alembic version: {row[0] if row else 'UNKNOWN'}")

        # 5. Check sys_jobs indexes
        result = await conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'sys_jobs' AND schemaname = 'public'"
        ))
        indexes = [r[0] for r in result.fetchall()]
        print(f"📌 sys_jobs indexes: {indexes}")

    await engine.dispose()
    print("\n✅ Verification complete")

asyncio.run(verify())
