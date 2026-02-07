import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://mpango:MpangoDBV0.1.2@127.0.0.1:5432/mpango_erp")
os.environ.setdefault("SECRET_KEY", "kJ8mN2pQ5rT9vX3zA6bC4dF7gH1jK0lM")

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from database.session import async_engine

async def drop():
    async with async_engine.begin() as conn:
        await conn.execute(text('DROP SCHEMA IF EXISTS t_test CASCADE'))
        print('✓ Dropped t_test schema')

asyncio.run(drop())
