"""
Property-based tests for schema security requirements.

Feature: backend-skeleton, Property 5: Password Hash Exclusion
Validates: Requirements 5.3

For any Pydantic Read/Response schema, the password_hash field SHALL NOT be present,
ensuring sensitive data is never exposed in API responses.
"""
import inspect
from typing import get_type_hints, get_origin, get_args

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import BaseModel

# Import all schema modules
from schemas import user, auth, order, common


def get_all_pydantic_models() -> list[type[BaseModel]]:
    """Get all Pydantic model classes from schema modules."""
    models = []
    
    for module in [user, auth, order, common]:
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and 
                issubclass(obj, BaseModel) and 
                obj is not BaseModel):
                models.append(obj)
    
    return models


def is_read_or_response_schema(model: type[BaseModel]) -> bool:
    """
    Check if a schema is a Read or Response schema.
    
    These schemas are returned to clients and must not contain password_hash.
    """
    name = model.__name__
    return (
        'Read' in name or 
        'Response' in name or 
        name.endswith('Data')  # e.g., CurrentUserData
    )


class TestPasswordHashExclusion:
    """Property tests for password_hash exclusion from response schemas."""
    
    def test_no_read_schema_contains_password_hash(self):
        """
        Property 5: No Read/Response schema contains password_hash field.
        
        This is a critical security requirement - password hashes must never
        be exposed in API responses.
        
        Validates: Requirement 5.3
        """
        models = get_all_pydantic_models()
        read_models = [m for m in models if is_read_or_response_schema(m)]
        
        assert len(read_models) > 0, "No Read/Response schemas found to test"
        
        for model in read_models:
            fields = model.model_fields.keys()
            assert 'password_hash' not in fields, \
                f"{model.__name__} must not contain 'password_hash' field"
            
            # Also check for common password field variations
            forbidden_fields = {'password_hash', 'passwordHash', 'hashed_password'}
            found_forbidden = forbidden_fields & set(fields)
            assert not found_forbidden, \
                f"{model.__name__} contains forbidden password fields: {found_forbidden}"
    
    def test_user_read_schema_specifically_excludes_password(self):
        """
        Property 5.1: UserRead schema specifically must not have password_hash.
        
        This is the most critical schema as it's the primary user data response.
        """
        from schemas.user import UserRead
        
        fields = UserRead.model_fields.keys()
        assert 'password_hash' not in fields, \
            "UserRead must not contain password_hash"
        assert 'password' not in fields, \
            "UserRead must not contain password"
    
    def test_current_user_data_excludes_password(self):
        """
        Property 5.2: CurrentUserData (from /auth/me) must not have password_hash.
        """
        from schemas.auth import CurrentUserData
        
        fields = CurrentUserData.model_fields.keys()
        assert 'password_hash' not in fields, \
            "CurrentUserData must not contain password_hash"
        assert 'password' not in fields, \
            "CurrentUserData must not contain password"
    
    @given(st.sampled_from([
        'UserRead', 'UserResponse', 'UserListResponse',
        'CurrentUserData', 'CurrentUserResponse',
        'RoleRead', 'RoleListResponse'
    ]))
    @settings(max_examples=20)  # Reduced from 100 for faster execution
    def test_common_response_schemas_exclude_password(self, schema_name: str):
        """
        Property 5.3: All common response schemas exclude password fields.
        
        Uses property-based testing to verify across multiple schema types.
        """
        # Get the schema class
        if schema_name.startswith('User') or schema_name == 'RoleRead':
            from schemas import user as schema_module
        elif schema_name.startswith('Current'):
            from schemas import auth as schema_module
        elif schema_name.startswith('Role'):
            from schemas import user as schema_module
        else:
            pytest.skip(f"Unknown schema: {schema_name}")
            return
        
        schema_class = getattr(schema_module, schema_name, None)
        if schema_class is None:
            pytest.skip(f"Schema not found: {schema_name}")
            return
        
        fields = schema_class.model_fields.keys()
        assert 'password_hash' not in fields, \
            f"{schema_name} must not contain password_hash"
        assert 'password' not in fields, \
            f"{schema_name} must not contain password"


class TestCreateSchemasSeparation:
    """Test that Create schemas are separate from Read schemas."""
    
    def test_user_create_has_password_field(self):
        """
        UserCreateRequest should have password field (not password_hash).
        
        This ensures we accept passwords on creation but never return them.
        """
        from schemas.user import UserCreateRequest
        
        fields = UserCreateRequest.model_fields.keys()
        assert 'password' in fields, \
            "UserCreateRequest must have password field for input"
        assert 'password_hash' not in fields, \
            "UserCreateRequest should use 'password', not 'password_hash'"
    
    def test_create_and_read_schemas_are_different(self):
        """
        Property: Create and Read schemas must be different classes.
        
        This ensures proper separation of input and output data.
        """
        from schemas.user import UserCreateRequest, UserRead
        
        assert UserCreateRequest is not UserRead, \
            "Create and Read schemas must be different classes"
        
        create_fields = set(UserCreateRequest.model_fields.keys())
        read_fields = set(UserRead.model_fields.keys())
        
        # Read should have fields Create doesn't (id, timestamps)
        assert 'id' in read_fields and 'id' not in create_fields
        assert 'created_at' in read_fields and 'created_at' not in create_fields
