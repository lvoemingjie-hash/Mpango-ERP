"""
Pytest configuration and fixtures for Mpango ERP backend tests.

S2.5: Uses strong SECRET_KEY for testing to pass security validation.
S5-OPS: Session-scoped event loop and robust async_session fixture to prevent
        "Event loop closed" errors in complex transaction tests (S5-A/S5-B).
"""
import os
import pytest
import pytest_asyncio

# S2.5: Set test environment variables before importing settings
# S8-SEC: Never hardcode real credentials — use env vars or generate test-only values
os.environ.setdefault("DATABASE_URL", os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://mpango:${POSTGRES_PASSWORD}@127.0.0.1:5432/mpango_erp"
))
# Generate a deterministic but non-real test SECRET_KEY (passes 32-char + no-weak-substring validation)
import hashlib as _hashlib
_TEST_SECRET = _hashlib.sha256(b"mpango-test-runner-key-not-for-production").hexdigest()
os.environ.setdefault("SECRET_KEY", _TEST_SECRET)
os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")


import asyncio
from typing import AsyncGenerator
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from database.session import async_engine, AsyncSessionLocal


# ---------------------------------------------------------------------------
# S5-OPS FIX 1: Session-scoped event loop
# ---------------------------------------------------------------------------
# pytest-asyncio creates a new event loop per test by default.  When
# SQLAlchemy's async engine holds connections that outlive that loop the
# engine raises "Event loop is closed".  A session-scoped loop keeps a
# single loop alive for the entire test run so the engine's pool is always
# valid.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for all async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# S5-OPS FIX 2: Robust async_session with search_path re-set after commit
# ---------------------------------------------------------------------------
# Problem: SET LOCAL search_path only lasts until the current transaction
# ends.  Tests that call session.commit() (e.g. test_invariant_violation_
# confirm_zero_total, test_void_vs_cancel_rules) start a new transaction
# and lose the tenant search_path, causing "relation does not exist" errors.
#
# Fix: Use an "after_begin" event listener that automatically re-sets the
# search_path whenever a new transaction begins on the session.
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async database session for tests.

    Uses the test database configured in DATABASE_URL environment variable.
    Each test gets a fresh session that is rolled back after the test.

    For S5-A/S5-B tests: Uses t_test tenant schema for order and ledger tests.

    Guarantees:
    - search_path is set to t_test on EVERY new transaction (survives commit)
    - Session is always rolled back + closed, even on unhandled exceptions
    - Event loop stays alive across the full test suite (session-scoped loop)
    """
    async with AsyncSessionLocal() as session:
        tenant_schema = "t_test"

        # Store tenant info on the session for middleware / helpers
        session.info["tenant_schema"] = tenant_schema

        # Ensure the tenant schema exists (idempotent)
        await session.execute(
            text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"')
        )
        await session.commit()

        # --- search_path helper -------------------------------------------
        async def _set_search_path(sess: AsyncSession) -> None:
            """Set search_path for the current transaction."""
            await sess.execute(
                text(f'SET LOCAL search_path TO "{tenant_schema}", public')
            )

        # Set search_path for the initial transaction
        await _set_search_path(session)

        # S5-OPS: Register a listener so search_path is re-applied after
        # every commit (which starts a new implicit transaction).
        sync_session = session.sync_session

        @event.listens_for(sync_session, "after_begin")
        def _after_begin(sess, transaction, connection):
            """Re-set search_path whenever a new transaction begins."""
            # We schedule the SET LOCAL via the connection so it runs inside
            # the new transaction that just started.
            connection.execute(
                text(f'SET LOCAL search_path TO "{tenant_schema}", public')
            )

        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            # Always rollback to ensure test isolation
            await session.rollback()
        finally:
            # Remove the listener to avoid leaking across tests
            event.remove(sync_session, "after_begin", _after_begin)
            await session.close()
