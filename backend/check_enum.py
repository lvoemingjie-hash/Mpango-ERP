import asyncio
import os
if "DATABASE_URL" not in os.environ:
    raise RuntimeError("DATABASE_URL environment variable must be set")
if "SECRET_KEY" not in os.environ:
    raise RuntimeError("SECRET_KEY environment variable must be set")

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
