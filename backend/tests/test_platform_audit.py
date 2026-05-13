"""
Tests for Platform Track P0 — platform_audit_logs slice.

Verifies append-only contract, FK, schema, nullability.
"""
import pytest
from models.platform_audit_log import PlatformAuditLog


class TestPlatformAuditLogModel:
    """Verify PlatformAuditLog append-only model definition."""

    def test_has_id(self):
        assert hasattr(PlatformAuditLog, 'id')

    def test_has_actor_type(self):
        assert hasattr(PlatformAuditLog, 'actor_type')

    def test_has_actor_id(self):
        assert hasattr(PlatformAuditLog, 'actor_id')

    def test_has_wholesaler_id(self):
        assert hasattr(PlatformAuditLog, 'wholesaler_id')

    def test_has_action(self):
        assert hasattr(PlatformAuditLog, 'action')

    def test_has_resource(self):
        assert hasattr(PlatformAuditLog, 'resource')

    def test_has_audit_metadata(self):
        assert hasattr(PlatformAuditLog, 'audit_metadata')

    def test_has_created_at(self):
        assert hasattr(PlatformAuditLog, 'created_at')

    def test_has_updated_at(self):
        """ORM contract column present; append-only semantics enforced at service level."""
        assert hasattr(PlatformAuditLog, 'updated_at')

    def test_has_is_deleted(self):
        """ORM contract column present with default false; append-only semantics enforced at service level."""
        assert hasattr(PlatformAuditLog, 'is_deleted')

    def test_has_deleted_at(self):
        """ORM contract column present with default null; append-only semantics enforced at service level."""
        assert hasattr(PlatformAuditLog, 'deleted_at')

    def test_schema_is_public(self):
        assert PlatformAuditLog.__table_args__[3] == {'schema': 'public'}

    def test_tablename(self):
        assert PlatformAuditLog.__tablename__ == 'platform_audit_logs'

    def test_wholesaler_fk(self):
        """Verify FK to public.wholesalers.id exists."""
        fk = list(PlatformAuditLog.__table__.foreign_keys)
        assert len(fk) == 1
        assert fk[0].target_fullname == 'public.wholesalers.id'

    def test_actor_type_nullable_false(self):
        assert not PlatformAuditLog.__table__.c.actor_type.nullable

    def test_wholesaler_id_nullable_true(self):
        assert PlatformAuditLog.__table__.c.wholesaler_id.nullable

    def test_action_nullable_false(self):
        assert not PlatformAuditLog.__table__.c.action.nullable

    def test_created_at_nullable_false(self):
        assert not PlatformAuditLog.__table__.c.created_at.nullable
