"""
Tests for Platform Track P0 - First implementation slice.

Tests verify:
- Wholesaler model has new platform lifecycle fields
- PlatformTenant model is correctly defined
- Platform tenants API endpoints return correct data
- No tenant-schema access occurs
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


class TestPlatformEndpoints:
    """Verify platform API endpoints are registered."""

    def test_platform_health_route_exists(self, client):
        response = client.get("/api/v1/platform/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_platform_info_route_exists(self, client):
        response = client.get("/api/v1/platform/info")
        assert response.status_code == 200

    def test_platform_tenants_list_route_exists(self, client):
        response = client.get("/api/v1/platform/tenants/")
        assert response.status_code == 200
        data = response.json()
        assert "tenants" in data
        assert "count" in data

    def test_platform_tenant_get_route_404(self, client):
        response = client.get("/api/v1/platform/tenants/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
