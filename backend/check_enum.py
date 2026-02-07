import asyncio
import os
os.environ.setdefault("DATABASE_URL", "postgresql://mpango:MpangoDBV0.1.2@127.0.0.1:5432/mpango_erp")
os.environ.setdefault("SECRET_KEY", "kJ8mN2pQ5rT9vX3zA6bC4dF7gH1jK0lM")

from sqlalchemy import text
from database.session import async_engine

async def check():
    async with async_engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT enumlabel FROM pg_enum WHERE enumtypid = 't_test.order_status'::regtype ORDER BY enumsortorder"
        ))
        labels = [row[0] for row in result]
        print(f"Enum values in database: {labels}")

asyncio.run(check())
