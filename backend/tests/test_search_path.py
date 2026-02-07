"""Test that search_path is set correctly in async_session fixture."""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_search_path_is_set(async_session):
    """Verify that search_path is set to t_test."""
    result = await async_session.execute(text("SHOW search_path"))
    search_path = result.scalar()
    print(f"Search path: {search_path}")
    assert "t_test" in search_path
