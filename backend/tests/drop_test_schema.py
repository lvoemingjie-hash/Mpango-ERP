import asyncio
import os
import sys
from pathlib import Path

# S8-SEC: Never hardcode real credentials — use env vars or generate test-only values
import hashlib as _hashlib
os.environ.setdefault("DATABASE_URL", os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://mpango:${POSTGRES_PASSWORD}@127.0.0.1:5432/mpango_erp"
))
_TEST_SECRET = _hashlib.sha256(b"mpango-test-runner-key-not-for-production").hexdigest()
os.environ.setdefault("SECRET_KEY", _TEST_SECRET)

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from database.session import async_engine

async def drop():
    async with async_engine.begin() as conn:
        await conn.execute(text('DROP SCHEMA IF EXISTS t_test CASCADE'))
        print('✓ Dropped t_test schema')

asyncio.run(drop())
