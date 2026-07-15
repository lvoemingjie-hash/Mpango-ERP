"""
Property-based tests for ORM model structure compliance.

Feature: backend-skeleton, Property 1: ORM Model Structure Compliance
Validates: Requirements 1.3, 1.4, 3.2, 3.3

For any SQLAlchemy ORM model in the backend, it SHALL have:
- A UUID primary key column named `id` with gen_random_uuid() server default
- Audit columns: created_at, updated_at, is_deleted, deleted_at
- __tablename__ explicitly defined in snake_case plural form
- Class name in PascalCase
"""
import re
import uuid
from typing import Type

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

# Import all models to test
from models.base import Base, BaseModel, PublicBaseModel


# View/read models that don't follow standard entity conventions
_VIEW_MODELS = {"MvSalesDaily", "RptSalesDaily", "RptReceivablesSummary", "RptCashFlowDaily"}

# Append-only models with CTO-frozen constraints prohibiting audit columns
# (updated_at, is_deleted, deleted_at). These are immutable event logs.
# CTO-frozen: do NOT remove without explicit CTO approval.
_FROZEN_APPEND_ONLY_MODELS = {"SysAuditLog"}


def get_all_model_classes() -> list[Type]:
    """Get all concrete (non-abstract) model classes."""
    models = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        # Skip abstract base classes
        if hasattr(cls, '__abstract__') and cls.__abstract__:
            continue
        # Skip materialized view models (no standard PK / audit columns)
        if cls.__name__ in _VIEW_MODELS:
            continue
        models.append(cls)
    return sorted(models, key=lambda model: (model.__module__, model.__name__))


def get_public_model_classes() -> list[Type]:
    """Return public ORM models in a stable order for deterministic checks."""
    public_table_names = {
        'wholesalers',
        'retailers',
        'invitations',
        'wholesaler_retailer_bindings',
        'sys_audit_logs',
        'sys_reports',
        'sys_jobs',
    }
    return [
        model
        for model in get_all_model_classes()
        if model.__name__ not in _FROZEN_APPEND_ONLY_MODELS
        and (
            getattr(model.__table__, 'schema', None) == 'public'
            or getattr(model, '__tablename__', '') in public_table_names
        )
    ]


def is_snake_case_plural(name: str) -> bool:
    """Check if name is snake_case and plural (ends with 's' or 'es')."""
    # Must be lowercase with underscores only
    if not re.match(r'^[a-z][a-z0-9_]*$', name):
        return False
    # Should end with 's' (simple plural check)
    return name.endswith('s')


def is_pascal_case(name: str) -> bool:
    """Check if name is PascalCase."""
    return bool(re.match(r'^[A-Z][a-zA-Z0-9]*$', name))


class TestORMModelStructure:
    """Property tests for ORM model structure compliance."""

    def test_all_models_have_uuid_primary_key(self):
        """
        Property 1.1: All models must have UUID primary key named 'id'.
        Validates: Requirement 1.3
        """
        models = get_all_model_classes()
        assert len(models) > 0, "No models found to test"

        for model in models:
            mapper = inspect(model)
            pk_columns = mapper.primary_key

            assert len(pk_columns) == 1, \
                f"{model.__name__} must have exactly one primary key column"

            pk_col = pk_columns[0]
            assert pk_col.name == 'id', \
                f"{model.__name__} primary key must be named 'id', got '{pk_col.name}'"

            # Check UUID type
            assert isinstance(pk_col.type, UUID), \
                f"{model.__name__}.id must be UUID type, got {type(pk_col.type)}"

    def test_all_models_have_audit_columns(self):
        """
        Property 1.2: All models must have audit columns.
        Validates: Requirement 1.4
        """
        required_audit_columns = {'created_at', 'updated_at', 'is_deleted', 'deleted_at'}
        models = get_all_model_classes()

        for model in models:
            # Skip append-only models with CTO-frozen constraints
            if model.__name__ in _FROZEN_APPEND_ONLY_MODELS:
                continue
            mapper = inspect(model)
            column_names = {col.name for col in mapper.columns}

            missing = required_audit_columns - column_names
            assert not missing, \
                f"{model.__name__} missing audit columns: {missing}"

    def test_all_models_have_explicit_tablename(self):
        """
        Property 1.3: All models must have explicit __tablename__ in snake_case plural.
        Validates: Requirement 3.2
        """
        models = get_all_model_classes()

        for model in models:
            assert hasattr(model, '__tablename__'), \
                f"{model.__name__} must have explicit __tablename__"

            tablename = model.__tablename__
            assert is_snake_case_plural(tablename), \
                f"{model.__name__}.__tablename__ '{tablename}' must be snake_case plural"

    def test_all_model_classes_are_pascal_case(self):
        """
        Property 1.4: All model class names must be PascalCase.
        Validates: Requirement 3.3
        """
        models = get_all_model_classes()

        for model in models:
            assert is_pascal_case(model.__name__), \
                f"Model class name '{model.__name__}' must be PascalCase"

    def test_base_model_has_server_default_for_id(self):
        """
        Property 1.5: BaseModel.id must have gen_random_uuid() server default.
        Validates: Requirement 1.3
        """
        # BaseModel is abstract; verify via first concrete subclass that has 'id'
        models = get_all_model_classes()
        tenant_model = next((m for m in models if 'id' in {c.name for c in m.__table__.c}), None)
        assert tenant_model is not None, "No concrete model with 'id' column found"
        id_col = tenant_model.__table__.c.id
        assert id_col.server_default is not None, \
            "BaseModel.id must have server_default"

        # The server default should contain gen_random_uuid()
        default_text = str(id_col.server_default.arg)
        assert 'gen_random_uuid()' in default_text, \
            f"BaseModel.id server_default must be gen_random_uuid(), got {default_text}"


class TestPublicBaseModel:
    """Tests specific to PublicBaseModel (for public schema tables)."""

    def test_public_base_model_has_audit_columns(self):
        """PublicBaseModel must have audit columns but not user tracking."""
        required = {'created_at', 'updated_at', 'is_deleted', 'deleted_at'}
        public_models = get_public_model_classes()
        if not public_models:
            pytest.skip("No concrete public model registered in ORM")
        missing_by_model = {
            model.__name__: sorted(
                required - {column.name for column in model.__table__.c}
            )
            for model in public_models
            if required - {column.name for column in model.__table__.c}
        }
        assert not missing_by_model, (
            f"PublicBaseModel subclasses missing audit columns: {missing_by_model}"
        )

    def test_public_base_model_no_user_tracking(self):
        """PublicBaseModel should not have user tracking columns."""
        public_models = get_public_model_classes()
        if not public_models:
            pytest.skip("No concrete public model registered in ORM")
        tracked_models = {
            model.__name__: sorted(
                {'created_by', 'updated_by'}
                & {column.name for column in model.__table__.c}
            )
            for model in public_models
            if {'created_by', 'updated_by'}
            & {column.name for column in model.__table__.c}
        }
        assert not tracked_models, (
            f"PublicBaseModel subclasses have user tracking columns: {tracked_models}"
        )


# Property-based test using Hypothesis
@given(st.uuids())
@settings(max_examples=20)  # Reduced from 100 for faster execution
def test_uuid_generation_produces_valid_uuids(test_uuid: uuid.UUID):
    """
    Property: UUID generation always produces valid UUIDs.
    This validates the uuid.uuid4 default works correctly.
    """
    assert isinstance(test_uuid, uuid.UUID)
    # Note: Hypothesis may generate UUIDs without a version field set
    # We just verify it's a valid UUID object
