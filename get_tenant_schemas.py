#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from database.session import AsyncSessionLocal
from sqlalchemy import text

async def get_tenant_schemas():
    async with AsyncSessionLocal() as db:
        # Get wholesaler info with their schemas
        result = await db.execute(text("""
            SELECT code, name, id 
            FROM public.wholesalers 
            ORDER BY code
        """))
        
        print('Tenant mapping:')
        for row in result:
            code, name, tenant_id = row
            # Calculate schema name using the same logic as the model
            schema_name = f"t_{str(tenant_id).replace('-', '')}"
            print(f'  {code} ({name}): {schema_name}')
            
            # Check if tables exist in this schema
            table_result = await db.execute(text(f"""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = '{schema_name}'
                ORDER BY table_name
            """))
            
            tables = [t[0] for t in table_result.fetchall()]
            if tables:
                print(f'    Tables: {", ".join(tables)}')
            else:
                print(f'    No tables found')

asyncio.run(get_tenant_schemas())