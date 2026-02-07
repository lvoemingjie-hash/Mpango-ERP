"""
S3-A Part 4: Test endpoint for SQL profiling verification.

This endpoint deliberately executes multiple SQL queries to test profiling.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_db

router = APIRouter()


@router.get("/profiling-test")
async def profiling_test_endpoint(
    query_count: int = 5,
    session: AsyncSession = Depends(get_db)
):
    """
    S3-A Part 4: Test endpoint that executes multiple SQL queries.
    
    Args:
        query_count: Number of queries to execute (default: 5)
        session: Database session
    
    Returns:
        dict: Query execution summary
    """
    results = []
    
    for i in range(query_count):
        # Execute a simple SELECT query
        result = await session.execute(text("SELECT 1 as test_value"))
        row = result.fetchone()
        results.append({"query_num": i + 1, "result": row[0] if row else None})
    
    return {
        "message": f"Executed {query_count} SQL queries",
        "results": results,
        "note": "Check X-SQL-Query-Count and X-SQL-Duration-Ms response headers"
    }


@router.get("/profiling-test-slow")
async def profiling_test_slow_endpoint(
    delay_ms: int = 150,
    session: AsyncSession = Depends(get_db)
):
    """
    S3-A Part 4: Test endpoint that executes a slow SQL query.
    
    Args:
        delay_ms: Delay in milliseconds (default: 150ms, above 100ms threshold)
        session: Database session
    
    Returns:
        dict: Query execution summary
    """
    # Execute a query with pg_sleep to simulate slow query
    delay_seconds = delay_ms / 1000.0
    result = await session.execute(
        text(f"SELECT pg_sleep({delay_seconds}), 1 as test_value")
    )
    row = result.fetchone()
    
    return {
        "message": f"Executed slow query ({delay_ms}ms)",
        "result": row[1] if row else None,
        "note": "This should trigger a slow query warning in logs"
    }

