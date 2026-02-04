#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from database.session import AsyncSessionLocal
from sqlalchemy import text

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text('SELECT code, name FROM public.wholesalers'))
        print('Existing tenants:')
        for row in result:
            print(f'  {row[0]}: {row[1]}')

asyncio.run(check())
