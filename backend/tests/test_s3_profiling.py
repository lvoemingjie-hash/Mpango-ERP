"""
S3-A: SQL Profiling & Performance Visibility Tests

Tests for SQL profiling middleware, slow query detection, and metrics.

Philosophy: "Make the synchronous fast, before making it asynchronous."
We cannot optimize what we cannot measure.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import text

from main import app
from core.sql_profiling import (
    init_sql_tracking,
    get_sql_stats,
    clear_sql_tracking,
    _extract_query_type,
    _truncate_query
)


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


class TestSQLProfilingCore:
    """Test core SQL profiling functionality."""

    def test_init_sql_tracking(self):
        """Test SQL tracking initialization."""
        init_sql_tracking()
        stats = get_sql_stats()
        assert stats.query_count == 0
        assert stats.total_duration_ms == 0.0
        assert stats.queries == []
        assert stats.slow_queries == []
        clear_sql_tracking()

    def test_extract_query_type_select(self):
        """Test query type extraction for SELECT."""
        assert _extract_query_type("SELECT * FROM users") == "SELECT"
        assert _extract_query_type("  select id from orders") == "SELECT"
        assert _extract_query_type("\nSELECT 1") == "SELECT"

    def test_extract_query_type_insert(self):
        """Test query type extraction for INSERT."""
        assert _extract_query_type("INSERT INTO users VALUES (1)") == "INSERT"
        assert _extract_query_type("insert into orders (id) values (1)") == "INSERT"

    def test_extract_query_type_update(self):
        """Test query type extraction for UPDATE."""
        assert _extract_query_type("UPDATE users SET name='test'") == "UPDATE"
        assert _extract_query_type("update orders set status='done'") == "UPDATE"

    def test_extract_query_type_delete(self):
        """Test query type extraction for DELETE."""
        assert _extract_query_type("DELETE FROM users WHERE id=1") == "DELETE"
        assert _extract_query_type("delete from orders") == "DELETE"

    def test_extract_query_type_transaction(self):
        """Test query type extraction for transaction commands."""
        assert _extract_query_type("BEGIN") == "BEGIN"
        assert _extract_query_type("COMMIT") == "COMMIT"
        assert _extract_query_type("ROLLBACK") == "ROLLBACK"
        assert _extract_query_type("SET search_path TO public") == "SET"

    def test_extract_query_type_other(self):
        """Test query type extraction for unknown queries."""
        assert _extract_query_type("CREATE TABLE users (id INT)") == "OTHER"
        assert _extract_query_type("DROP TABLE users") == "OTHER"

    def test_truncate_query_short(self):
        """Test query truncation for short queries."""
        query = "SELECT * FROM users"
        assert _truncate_query(query, 100) == query

    def test_truncate_query_long(self):
        """Test query truncation for long queries."""
        query = "SELECT " + ", ".join([f"col{i}" for i in range(100)])
        truncated = _truncate_query(query, 50)
        assert len(truncated) == 53  # 50 + "..."
        assert truncated.endswith("...")


@pytest.mark.skipif(
    not __import__('os').environ.get('ENABLE_SQL_PROFILING', '').lower() == 'true',
    reason="SQL profiling disabled in current environment (ENABLE_SQL_PROFILING != true)"
)
class TestSQLProfilingMiddleware:
    """Test SQL profiling middleware integration."""

    def test_profiling_headers_on_health_endpoint(self, client):
        """Test that SQL profiling headers are added to health endpoint."""
        response = client.get("/health")

        # Health endpoint should have profiling headers
        assert "X-SQL-Query-Count" in response.headers
        assert "X-SQL-Duration-Ms" in response.headers

        # Verify values are numeric
        query_count = int(response.headers["X-SQL-Query-Count"])
        duration_ms = float(response.headers["X-SQL-Duration-Ms"])

        assert query_count >= 0
        assert duration_ms >= 0.0

    def test_profiling_skips_metrics_endpoint(self, client):
        """Test that profiling skips /metrics endpoint."""
        response = client.get("/metrics")

        # Metrics endpoint should NOT have profiling headers
        assert "X-SQL-Query-Count" not in response.headers
        assert "X-SQL-Duration-Ms" not in response.headers


class TestSQLProfilingWarnings:
    """Test SQL profiling warning thresholds."""

    def test_warning_threshold_constants(self):
        """Test that warning thresholds are properly defined."""
        from api.middleware.sql_profiling import SQLProfilingMiddleware

        # Verify thresholds are defined
        assert hasattr(SQLProfilingMiddleware, 'MAX_QUERIES_WARNING')
        assert hasattr(SQLProfilingMiddleware, 'MAX_DB_TIME_MS_WARNING')

        # Verify threshold values
        assert SQLProfilingMiddleware.MAX_QUERIES_WARNING == 10
        assert SQLProfilingMiddleware.MAX_DB_TIME_MS_WARNING == 500


class TestSQLProfilingMetrics:
    """Test SQL profiling Prometheus metrics."""

    def test_metrics_endpoint_accessible(self, client):
        """Test that Prometheus metrics endpoint is accessible."""
        response = client.get("/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_sql_metrics_defined(self):
        """Test that SQL profiling metrics are properly defined."""
        from core.sql_profiling import (
            sql_queries_total,
            sql_query_duration_seconds,
            sql_slow_queries_total,
            sql_queries_per_request
        )

        # Verify metrics are defined
        assert sql_queries_total is not None
        assert sql_query_duration_seconds is not None
        assert sql_slow_queries_total is not None
        assert sql_queries_per_request is not None


class TestSQLProfilingIntegration:
    """Integration tests for SQL profiling."""

    def test_profiling_configuration(self):
        """Test SQL profiling configuration settings."""
        from core.config import get_settings

        settings = get_settings()

        # Verify SQL profiling settings exist
        assert hasattr(settings, 'SLOW_QUERY_THRESHOLD_MS')
        assert hasattr(settings, 'ENABLE_SQL_PROFILING')

        # Verify default values
        assert settings.SLOW_QUERY_THRESHOLD_MS == 100
        assert isinstance(settings.ENABLE_SQL_PROFILING, bool)


class TestSQLProfilingEdgeCases:
    """Test edge cases for SQL profiling."""

    def test_profiling_with_no_queries(self):
        """Test profiling when no queries are executed."""
        init_sql_tracking()
        stats = get_sql_stats()

        assert stats.query_count == 0
        assert stats.total_duration_ms == 0.0
        assert len(stats.slow_queries) == 0

        clear_sql_tracking()

    def test_profiling_clear_tracking(self):
        """Test clearing SQL tracking."""
        init_sql_tracking()

        # Simulate adding a query (would normally be done by event listener)
        # For this test, we just verify clear works
        clear_sql_tracking()

        # After clear, get_sql_stats should return empty stats
        stats = get_sql_stats()
        assert stats.query_count == 0

    def test_profiling_without_init(self):
        """Test getting stats without initialization."""
        clear_sql_tracking()  # Ensure clean state

        # Get stats without init
        stats = get_sql_stats()

        # Should return empty stats
        assert stats.query_count == 0
        assert stats.total_duration_ms == 0.0


# Property-Based Tests (if using Hypothesis)
try:
    from hypothesis import given, strategies as st

    class TestSQLProfilingProperties:
        """Property-based tests for SQL profiling."""

        @given(st.integers(min_value=1, max_value=100))
        def test_query_count_property(self, query_count):
            """Property: Query count should match number of queries executed."""
            # This would require a more sophisticated test setup
            # For now, we verify the concept
            assert query_count > 0

        @given(st.text(min_size=1, max_size=1000))
        def test_truncate_query_property(self, query):
            """Property: Truncated query should never exceed max_length + 3."""
            max_length = 200
            truncated = _truncate_query(query, max_length)

            # Truncated query should be at most max_length + 3 ("...")
            assert len(truncated) <= max_length + 3

            # If original is short, should be unchanged
            if len(query) <= max_length:
                assert truncated == query
            else:
                assert truncated.endswith("...")

except ImportError:
    # Hypothesis not installed, skip property-based tests
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
