"""
S3-A: SQL Profiling & Performance Visibility

Provides deep visibility into SQL execution performance per request.
Tracks query count, duration, and identifies slow queries.

Philosophy: "Make the synchronous fast, before making it asynchronous."
We cannot optimize what we cannot measure.
"""
import time
from contextvars import ContextVar
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from sqlalchemy import event
from sqlalchemy.engine import Engine
from prometheus_client import Counter, Histogram

from core.structured_logging import get_logger
from core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()

# S3-A: Context variable to track SQL queries per request
_sql_queries_ctx: ContextVar[Optional[List[Dict]]] = ContextVar('sql_queries', default=None)
_sql_start_time_ctx: ContextVar[Optional[float]] = ContextVar('sql_start_time', default=None)


@dataclass
class SQLQueryStats:
    """Statistics for SQL queries in a request."""
    query_count: int = 0
    total_duration_ms: float = 0.0
    queries: List[Dict] = field(default_factory=list)
    slow_queries: List[Dict] = field(default_factory=list)


# S3-A: Prometheus metrics for SQL performance
sql_queries_total = Counter(
    'sql_queries_total',
    'Total SQL queries executed',
    ['tenant', 'route']
)

sql_query_duration_seconds = Histogram(
    'sql_query_duration_seconds',
    'SQL query duration in seconds',
    ['tenant', 'query_type'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

sql_slow_queries_total = Counter(
    'sql_slow_queries_total',
    'Total slow SQL queries (>100ms)',
    ['tenant', 'query_type']
)

sql_queries_per_request = Histogram(
    'sql_queries_per_request',
    'Number of SQL queries per HTTP request',
    ['tenant', 'route'],
    buckets=(1, 2, 3, 5, 10, 15, 20, 30, 50, 100)
)


def init_sql_tracking() -> None:
    """Initialize SQL query tracking for the current request."""
    _sql_queries_ctx.set([])


def get_sql_stats() -> SQLQueryStats:
    """Get SQL statistics for the current request."""
    queries = _sql_queries_ctx.get() or []
    
    stats = SQLQueryStats()
    stats.query_count = len(queries)
    stats.queries = queries
    
    for query in queries:
        stats.total_duration_ms += query['duration_ms']
        if query['duration_ms'] > settings.SLOW_QUERY_THRESHOLD_MS:
            stats.slow_queries.append(query)
    
    return stats


def clear_sql_tracking() -> None:
    """Clear SQL query tracking for the current request."""
    _sql_queries_ctx.set(None)
    _sql_start_time_ctx.set(None)


def _extract_query_type(statement: str) -> str:
    """Extract query type from SQL statement (SELECT, INSERT, UPDATE, DELETE)."""
    statement_upper = statement.strip().upper()
    
    if statement_upper.startswith('SELECT'):
        return 'SELECT'
    elif statement_upper.startswith('INSERT'):
        return 'INSERT'
    elif statement_upper.startswith('UPDATE'):
        return 'UPDATE'
    elif statement_upper.startswith('DELETE'):
        return 'DELETE'
    elif statement_upper.startswith('SET'):
        return 'SET'
    elif statement_upper.startswith('BEGIN'):
        return 'BEGIN'
    elif statement_upper.startswith('COMMIT'):
        return 'COMMIT'
    elif statement_upper.startswith('ROLLBACK'):
        return 'ROLLBACK'
    else:
        return 'OTHER'


def _truncate_query(query: str, max_length: int = 200) -> str:
    """Truncate long queries for logging."""
    if len(query) <= max_length:
        return query
    return query[:max_length] + "..."


def install_sql_profiling(engine: Engine) -> None:
    """
    S3-A: Install SQL profiling event listeners on SQLAlchemy engine.
    
    Tracks:
    - Query execution time
    - Query count per request
    - Slow queries (>SLOW_QUERY_THRESHOLD_MS)
    
    Args:
        engine: SQLAlchemy engine to instrument
    """
    
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """Record query start time."""
        conn.info.setdefault('query_start_time', []).append(time.time())
    
    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """
        S3-A: Record query execution and log slow queries.
        
        Captures:
        - Query duration
        - Query type (SELECT, INSERT, UPDATE, DELETE)
        - Slow query warnings (>SLOW_QUERY_THRESHOLD_MS)
        """
        # Get query start time
        query_start_times = conn.info.get('query_start_time', [])
        if not query_start_times:
            return
        
        start_time = query_start_times.pop()
        duration_seconds = time.time() - start_time
        duration_ms = duration_seconds * 1000
        
        # Extract query type
        query_type = _extract_query_type(statement)
        
        # Get tenant from connection info (if available)
        tenant = conn.info.get('tenant_schema', 'unknown')
        
        # Record query in request context
        queries = _sql_queries_ctx.get()
        if queries is not None:
            query_info = {
                'statement': _truncate_query(statement),
                'duration_ms': duration_ms,
                'query_type': query_type,
                'tenant': tenant
            }
            queries.append(query_info)
        
        # Record Prometheus metrics
        sql_query_duration_seconds.labels(
            tenant=tenant,
            query_type=query_type
        ).observe(duration_seconds)
        
        # S3-A Part 2: Slow Query Logger
        if duration_ms > settings.SLOW_QUERY_THRESHOLD_MS:
            sql_slow_queries_total.labels(
                tenant=tenant,
                query_type=query_type
            ).inc()
            
            logger.warning(
                f"Slow SQL query detected ({duration_ms:.2f}ms)",
                extra={
                    "duration_ms": duration_ms,
                    "query_type": query_type,
                    "statement": _truncate_query(statement, 500),
                    "tenant": tenant,
                    "threshold_ms": settings.SLOW_QUERY_THRESHOLD_MS
                }
            )
    
    logger.info("SQL profiling event listeners installed", extra={
        "slow_query_threshold_ms": settings.SLOW_QUERY_THRESHOLD_MS
    })

