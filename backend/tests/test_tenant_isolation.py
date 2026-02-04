"""
Property-based tests for tenant schema isolation.

Feature: backend-skeleton, Property 8: Tenant Schema Isolation
Validates: Requirements 6.3

For any database session with a tenant_schema provided, the search_path SHALL be
set to "<tenant_schema>", public ensuring queries resolve to the correct tenant's data.
"""
import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import text

# Note: These tests require a running database and are integration tests
# They are marked with @pytest.mark.integration to allow selective running


def generate_tenant_schema_name() -> st.SearchStrategy[str]:
    """
    Generate valid tenant schema names.
    Format: t_<32_hex_chars> (UUID without dashes)
    """
    return st.builds(
        lambda hex_str: f"t_{hex_str}",
        st.text(
            alphabet="0123456789abcdef",
            min_size=32,
            max_size=32
        )
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestTenantSchemaIsolation:
    """Property tests for tenant schema isolation."""

    @given(tenant_schema=generate_tenant_schema_name())
    @settings(max_examples=20)  # Reduced from 100 for faster execution
    async def test_search_path_set_for_tenant_session(self, tenant_schema: str):
        """
        Property: For any tenant schema, get_tenant_db sets search_path correctly.

        This test verifies that when a tenant_schema is provided, the database
        session has its search_path set to "<tenant_schema>", public.
        """
        from database.session import get_tenant_db

        async for session in get_tenant_db(tenant_schema):
            # Query current search_path
            result = await session.execute(text("SHOW search_path"))
            search_path = result.scalar()

            # Verify tenant schema is first in search_path
            assert tenant_schema in search_path, \
                f"Tenant schema '{tenant_schema}' not in search_path: {search_path}"

            # Verify public is also in search_path
            assert "public" in search_path, \
                f"'public' schema not in search_path: {search_path}"

            # Verify tenant schema comes before public
            tenant_idx = search_path.index(tenant_schema)
            public_idx = search_path.index("public")
            assert tenant_idx < public_idx, \
                f"Tenant schema must come before public in search_path: {search_path}"

    @pytest.mark.asyncio
    async def test_different_tenants_have_isolated_search_paths(self):
        """
        Property: Different tenant sessions have different search_paths.

        This ensures tenant isolation - each session resolves to its own schema.
        """
        from database.session import get_tenant_db

        tenant1 = "t_" + "a" * 32
        tenant2 = "t_" + "b" * 32

        # Get search_path for tenant1
        async for session1 in get_tenant_db(tenant1):
            result1 = await session1.execute(text("SHOW search_path"))
            path1 = result1.scalar()
            assert tenant1 in path1
            assert tenant2 not in path1

        # Get search_path for tenant2
        async for session2 in get_tenant_db(tenant2):
            result2 = await session2.execute(text("SHOW search_path"))
            path2 = result2.scalar()
            assert tenant2 in path2
            assert tenant1 not in path2

    @pytest.mark.asyncio
    async def test_public_session_has_no_tenant_schema(self):
        """
        Property: Public schema sessions should not have tenant schemas in search_path.

        This ensures public operations don't accidentally query tenant data.
        """
        from database.session import get_db

        async for session in get_db():
            result = await session.execute(text("SHOW search_path"))
            search_path = result.scalar()

            # Should not contain any t_* tenant schema patterns
            assert not any(
                part.strip().startswith("t_")
                for part in search_path.split(",")
            ), f"Public session should not have tenant schemas: {search_path}"


class TestTenantSchemaFormat:
    """Unit tests for tenant schema name format validation."""

    @given(st.text(alphabet="0123456789abcdef", min_size=32, max_size=32))
    @settings(max_examples=20)  # Reduced from 100 for faster execution
    def test_tenant_schema_format_is_valid(self, uuid_hex: str):
        """
        Property: All tenant schema names follow format t_<32_hex_chars>.

        Per multi_tenancy_spec.md section 2.2
        """
        from models.wholesaler import Wholesaler

        # Format with dashes to simulate UUID
        uuid_str = f"{uuid_hex[:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-{uuid_hex[16:20]}-{uuid_hex[20:]}"
        schema = Wholesaler.derive_schema_from_id(uuid_str)

        # Verify format
        assert schema.startswith("t_"), \
            f"Schema must start with 't_': {schema}"
        assert len(schema) == 34, \
            f"Schema must be 34 chars (t_ + 32 hex): {schema}"
        assert schema[2:].replace("-", "").isalnum(), \
            f"Schema must contain only alphanumeric after t_: {schema}"
