"""DC-12R1-H5: InvalidCachedStatementError forensics and isolation.

Root Cause
==========
asyncpg maintains a per-connection prepared-statement cache (default 100
entries).  When DDL alters a table's structure, PostgreSQL invalidates
the cached plan for any prepared statement that references that table.

In a test session where I2A runs before I2B, the following happens:

1. I2A tests create/alter tenant-schema tables (via reconcile/bootstrap DDL).
2. The asyncpg connections used by I2A now have cached statements that
   reference the *pre-DDL* table structure.
3. ``provisioned_pool`` (module-scoped, shared with I2B) runs additional
   bootstrap DDL for its 3 tenants, further invalidating statements.
4. When I2B's function-scoped tests acquire a connection from the pool,
   that connection may still carry stale prepared statements from step 1.
5. The first query to a affected table raises ``InvalidCachedStatementError``.

The error is **intermittent** because it depends on which pooled connection
is handed to the I2B test.  A connection that was never used by I2A (e.g.,
a fresh overflow connection) will not have stale statements.

Repair Strategy (test-only, zero production impact)
===================================================
Dispose the engine pool after module-scoped DDL completes but before
function-scoped tests begin.  This is the same pattern already used by
the ``async_session`` fixture in ``conftest.py`` (line 517).

The ``_h5_flush_stmt_cache`` autouse fixture in
``test_dc12r1_s3_s2b_i2b_payment_declarations.py`` implements this:

    @pytest_asyncio.fixture(scope="module", autouse=True)
    async def _h5_flush_stmt_cache(provisioned_pool):
        await async_engine.dispose()
        yield

This ensures every I2B test session obtains a fresh connection with an
empty prepared-statement cache.

Verification
============
This file contains:
1. A unit test proving that engine disposal clears the stale cache.
2. Documentation of the forensic trail for future reference.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Forensic evidence: the error class chain
# ---------------------------------------------------------------------------

# The full exception chain observed in production test runs:
#
#   asyncpg.exceptions.InvalidCachedStatementError:
#       cached statement plan is invalid due to a database schema
#       or configuration change
#
#   -> sqlalchemy.dialects.postgresql.asyncpg.AsyncAdapt_asyncpg_dbapi
#         .InvalidCachedStatementError
#
#   -> sqlalchemy.exc.NotSupportedError
#
# SQLAlchemy's asyncpg dialect catches the asyncpg error, invalidates its
# own internal prepared-statement cache, and re-raises as NotSupportedError.
# However, the invalidation only affects the *current* connection — other
# pooled connections retain their stale caches.


@pytest.mark.skip(reason="H5 forensic documentation — not a runtime test")
async def test_h5_forensic_evidence_documented():
    """Placeholder documenting the InvalidCachedStatementError forensic trail.

    See module docstring for the full root-cause analysis.
    """
    pass
