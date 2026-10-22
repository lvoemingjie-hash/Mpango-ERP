"""Native task-owned M1 fixtures; no external task-root imports or fake auth."""
import os
from pathlib import Path
import secrets

import pytest_asyncio
from sqlalchemy import text

from tests.test_inventory_manual_adjustment_safety import StockWorld


class StaffWorld(StockWorld):
    async def add_user(self, *, active=True):
        from core.security import hash_password
        email=secrets.token_hex(8)+'@example.com'
        async with self.session() as db:
            user=await db.scalar(text(f'INSERT INTO "{self.schema}".users (email,password_hash,is_active) VALUES (:e,:p,:a) RETURNING id'),
                {'e':email,'p':hash_password(secrets.token_urlsafe(32)),'a':active})
        return user,email


@pytest_asyncio.fixture
async def staff_world():
    from tests.mpango_invariants_r0_support import verify_task_database_ownership_sync
    verify_task_database_ownership_sync()
    world=StaffWorld()
    try:
        yield await world.initialize()
    finally:
        if hasattr(world,'engine'): await world.engine.dispose()
