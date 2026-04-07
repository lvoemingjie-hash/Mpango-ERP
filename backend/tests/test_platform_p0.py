"""
Tests for Platform Track P0 - First implementation slice.

Tests verify:
- Wholesaler model has new platform lifecycle fields
- PlatformTenant model is correctly defined
- No tenant-schema access occurs

API endpoint tests require async app fixture setup which is out of scope
for this model-focused first slice. Endpoint correctness is verified via
manual boot check (GATE 6).
"""
import pytest
from models.wholesaler import Wholesaler
from models.platform_tenant import PlatformTenant


class TestWholesalerPlatformFields:
    """Verify new platform lifecycle fields on Wholesaler model."""

    def test_wholesaler_has_status_field(self):
        assert hasattr(Wholesaler, 'status')

    def test_wholesaler_has_provisioned_at_field(self):
        assert hasattr(Wholesaler, 'provisioned_at')

    def test_wholesaler_has_suspended_at_field(self):
        assert hasattr(Wholesaler, 'suspended_at')

    def test_wholesaler_has_suspension_reason_field(self):
        assert hasattr(Wholesaler, 'suspension_reason')

    def test_wholesaler_schema_is_public(self):
        assert Wholesaler.__table_args__[1] == {"schema": "public"}

    def test_wholesaler_status_default(self):
        assert Wholesaler.__table__.c.status.server_default.arg == 'active'


class TestPlatformTenantModel:
    """Verify PlatformTenant model definition."""

    def test_platform_tenant_has_wholesaler_id(self):
        assert hasattr(PlatformTenant, 'wholesaler_id')

    def test_platform_tenant_has_provisioning_status(self):
        assert hasattr(PlatformTenant, 'provisioning_status')

    def test_platform_tenant_has_provisioning_log(self):
        assert hasattr(PlatformTenant, 'provisioning_log')

    def test_platform_tenant_schema_is_public(self):
        assert PlatformTenant.__table_args__[1] == {"schema": "public"}

    def test_platform_tenant_tablename(self):
        assert PlatformTenant.__tablename__ == "platform_tenants"

    def test_platform_tenant_provisioning_default(self):
        assert PlatformTenant.__table__.c.provisioning_status.server_default.arg == 'pending'

    def test_platform_tenant_wholesaler_fk(self):
        """Verify FK to public.wholesalers.id exists."""
        fk = list(PlatformTenant.__table__.foreign_keys)
        assert len(fk) == 1
        assert fk[0].target_fullname == "public.wholesalers.id"
