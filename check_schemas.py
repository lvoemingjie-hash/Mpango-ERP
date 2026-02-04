#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from database.session import AsyncSessionLocal
from sqlalchemy import text

async def check_schemas():
    async with AsyncSessionLocal() as db:
        # Check public schema
        result = await db.execute(text('SELECT code, name FROM public.wholesalers'))
        print('Tenants in public schema:')
        for row in result:
            print(f'  {row[0]}: {row[1]}')

        # Check if tenant schemas exist
        result = await db.execute(text("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name LIKE 't_%'
        """))
        print('\nTenant schemas:')
        for row in result:
            print(f'  {row[0]}')

        # Check if tables exist in a tenant schema
        result = await db.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 't_7465a81cc3f94fb3b0e6674cbc22c829'
        """))
        print('\nTables in TEST_A schema:')
        for row in result:
            print(f'  {row[0]}')

asyncio.run(check_schemas())
