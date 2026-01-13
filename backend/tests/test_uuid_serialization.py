"""
Property-based tests for UUID serialization.

Feature: backend-skeleton, Property 6: UUID Serialization
Validates: Requirements 5.4

For any UUID field in a Pydantic response schema, it SHALL serialize to a
string representation in JSON responses.
"""
import json
import uuid
from datetime import datetime

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import BaseModel

from schemas.user import UserRead, RoleRead
from schemas.auth import TokenData, CurrentUserData
from schemas.order import Order, OrderItem


class TestUUIDSerialization:
    """Property tests for UUID serialization to strings."""
    
    @given(
        user_id=st.uuids(),
        email=st.emails(),
        full_name=st.text(min_size=1, max_size=100) | st.none()
    )
    @settings(max_examples=20)  # Reduced from 100 for faster execution
    def test_user_read_serializes_uuid_as_string(
        self,
        user_id: uuid.UUID,
        email: str,
        full_name: str | None
    ):
        """
        Property 6.1: UserRead serializes UUID id field as string.
        
        For any UUID, when serialized in UserRead, it must be a string.
        """
        user = UserRead(
            id=str(user_id),
            email=email,
            full_name=full_name,
            is_active=True,
            roles=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Serialize to JSON
        json_str = user.model_dump_json()
        data = json.loads(json_str)
        
        # Verify id is a string in JSON
        assert isinstance(data['id'], str), \
            f"UUID field 'id' must serialize as string, got {type(data['id'])}"
        
        # Verify it's a valid UUID string
        try:
            uuid.UUID(data['id'])
        except ValueError:
            pytest.fail(f"Serialized id '{data['id']}' is not a valid UUID string")
    
    @given(
        order_id=st.uuids(),
        retailer_id=st.uuids(),
        total=st.decimals(min_value=0, max_value=999999, places=2)
    )
    @settings(max_examples=20)  # Reduced from 100 for faster execution
    def test_order_serializes_uuids_as_strings(
        self,
        order_id: uuid.UUID,
        retailer_id: uuid.UUID,
        total: float
    ):
        """
        Property 6.2: Order serializes all UUID fields as strings.
        
        For any Order with UUID fields, all UUIDs must serialize as strings.
        """
        from models.order import OrderStatus
        
        order = Order(
            id=str(order_id),
            retailer_id=str(retailer_id),
            retailer_name="Test Retailer",
            status=OrderStatus.PENDING,
            total_amount=total,
            items=[],
            notes=None,
            created_by=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Serialize to JSON
        json_str = order.model_dump_json()
        data = json.loads(json_str)
        
        # Verify all UUID fields are strings
        assert isinstance(data['id'], str), \
            "Order.id must serialize as string"
        assert isinstance(data['retailer_id'], str), \
            "Order.retailer_id must serialize as string"
        
        # Verify they're valid UUID strings
        uuid.UUID(data['id'])
        uuid.UUID(data['retailer_id'])
    
    @given(
        user_id=st.uuids(),
        tenant_id=st.uuids()
    )
    @settings(max_examples=20)  # Reduced from 100 for faster execution
    def test_token_data_serializes_uuids_as_strings(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID
    ):
        """
        Property 6.3: TokenData serializes UUID fields as strings.
        
        JWT token data must have UUIDs as strings for JSON compatibility.
        """
        token_data = TokenData(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            token_type="bearer",
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            tenant_schema=f"t_{str(tenant_id).replace('-', '')}"
        )
        
        # Serialize to JSON
        json_str = token_data.model_dump_json()
        data = json.loads(json_str)
        
        # Verify UUID fields are strings
        assert isinstance(data['user_id'], str), \
            "TokenData.user_id must serialize as string"
        assert isinstance(data['tenant_id'], str), \
            "TokenData.tenant_id must serialize as string"
        
        # Verify they're valid UUID strings
        uuid.UUID(data['user_id'])
        uuid.UUID(data['tenant_id'])
    
    def test_uuid_field_type_annotation_is_string(self):
        """
        Property 6.4: UUID fields in response schemas are annotated as str.
        
        This ensures Pydantic knows to serialize them as strings.
        """
        # Check UserRead
        assert UserRead.model_fields['id'].annotation == str, \
            "UserRead.id should be annotated as str"
        
        # Check Order
        assert Order.model_fields['id'].annotation == str, \
            "Order.id should be annotated as str"
        assert Order.model_fields['retailer_id'].annotation == str, \
            "Order.retailer_id should be annotated as str"
        
        # Check TokenData
        assert TokenData.model_fields['user_id'].annotation == str, \
            "TokenData.user_id should be annotated as str"
        assert TokenData.model_fields['tenant_id'].annotation == str, \
            "TokenData.tenant_id should be annotated as str"


class TestUUIDRoundTrip:
    """Test UUID round-trip serialization/deserialization."""
    
    @given(st.uuids())
    @settings(max_examples=20)  # Reduced from 100 for faster execution
    def test_uuid_round_trip_through_schema(self, test_uuid: uuid.UUID):
        """
        Property: UUID can round-trip through schema serialization.
        
        UUID -> str -> JSON -> str -> UUID should preserve the value.
        """
        # Create schema with UUID
        user = UserRead(
            id=str(test_uuid),
            email="test@example.com",
            full_name="Test User",
            is_active=True,
            roles=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Serialize to JSON and back
        json_str = user.model_dump_json()
        data = json.loads(json_str)
        
        # Deserialize back to schema
        user_restored = UserRead.model_validate(data)
        
        # Verify UUID is preserved
        assert user_restored.id == str(test_uuid), \
            "UUID should be preserved through serialization round-trip"
        
        # Verify we can convert back to UUID
        restored_uuid = uuid.UUID(user_restored.id)
        assert restored_uuid == test_uuid, \
            "UUID value should be identical after round-trip"
