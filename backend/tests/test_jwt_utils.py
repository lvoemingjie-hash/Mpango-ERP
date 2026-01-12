"""
Unit tests for JWT utilities.
Tests token creation, validation, and expiration.

Feature: identity-security
Properties: P1 (Token Integrity), P2 (Token Expiration), P7 (Token Type Separation)
"""
import pytest
from datetime import timedelta, datetime
from jose import jwt

from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    TokenPayload,
    InvalidTokenError,
    ExpiredTokenError
)
from core.config import get_settings


def test_create_access_token_returns_valid_jwt():
    """Test that create_access_token returns a valid JWT string."""
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    tenant_id = "223e4567-e89b-12d3-a456-426614174000"
    tenant_schema = "t_abc123"
    
    token = create_access_token(user_id, tenant_id, tenant_schema)
    
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Verify it's a valid JWT by decoding
    settings = get_settings()
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["user_id"] == user_id
    assert payload["tenant_id"] == tenant_id
    assert payload["tenant_schema"] == tenant_schema
    assert payload["type"] == "access"


def test_create_refresh_token_returns_valid_jwt():
    """Test that create_refresh_token returns a valid JWT string."""
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    tenant_id = "223e4567-e89b-12d3-a456-426614174000"
    tenant_schema = "t_abc123"
    
    token = create_refresh_token(user_id, tenant_id, tenant_schema)
    
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Verify it's a valid JWT by decoding
    settings = get_settings()
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["user_id"] == user_id
    assert payload["tenant_id"] == tenant_id
    assert payload["tenant_schema"] == tenant_schema
    assert payload["type"] == "refresh"


def test_decode_token_with_valid_token():
    """Test that decode_token successfully decodes a valid token."""
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    tenant_id = "223e4567-e89b-12d3-a456-426614174000"
    tenant_schema = "t_abc123"
    
    token = create_access_token(user_id, tenant_id, tenant_schema)
    payload = decode_token(token)
    
    assert isinstance(payload, TokenPayload)
    assert payload.user_id == user_id
    assert payload.tenant_id == tenant_id
    assert payload.tenant_schema == tenant_schema
    assert payload.type == "access"


def test_decode_token_raises_expired_token_error():
    """
    Test that decode_token raises ExpiredTokenError for expired token.
    Property P2: Token Expiration
    """
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    tenant_id = "223e4567-e89b-12d3-a456-426614174000"
    tenant_schema = "t_abc123"
    
    # Create token that expired 1 second ago
    token = create_access_token(
        user_id, tenant_id, tenant_schema,
        expires_delta=timedelta(seconds=-1)
    )
    
    with pytest.raises(ExpiredTokenError):
        decode_token(token)


def test_decode_token_raises_invalid_token_error():
    """Test that decode_token raises InvalidTokenError for bad signature."""
    # Create a token with wrong signature
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMTIzIn0.invalid_signature"
    
    with pytest.raises(InvalidTokenError):
        decode_token(invalid_token)


def test_token_type_validation_access():
    """
    Test that access tokens have type='access'.
    Property P7: Token Type Separation
    """
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    tenant_id = "223e4567-e89b-12d3-a456-426614174000"
    tenant_schema = "t_abc123"
    
    token = create_access_token(user_id, tenant_id, tenant_schema)
    payload = decode_token(token)
    
    assert payload.type == "access"


def test_token_type_validation_refresh():
    """
    Test that refresh tokens have type='refresh'.
    Property P7: Token Type Separation
    """
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    tenant_id = "223e4567-e89b-12d3-a456-426614174000"
    tenant_schema = "t_abc123"
    
    token = create_refresh_token(user_id, tenant_id, tenant_schema)
    payload = decode_token(token)
    
    assert payload.type == "refresh"


def test_token_roundtrip_integrity():
    """
    Test that token creation and decoding preserves all claims.
    Property P1: Token Integrity
    """
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    tenant_id = "223e4567-e89b-12d3-a456-426614174000"
    tenant_schema = "t_abc123def456"
    
    # Test access token
    access_token = create_access_token(user_id, tenant_id, tenant_schema)
    access_payload = decode_token(access_token)
    
    assert access_payload.user_id == user_id
    assert access_payload.tenant_id == tenant_id
    assert access_payload.tenant_schema == tenant_schema
    assert access_payload.type == "access"
    
    # Test refresh token
    refresh_token = create_refresh_token(user_id, tenant_id, tenant_schema)
    refresh_payload = decode_token(refresh_token)
    
    assert refresh_payload.user_id == user_id
    assert refresh_payload.tenant_id == tenant_id
    assert refresh_payload.tenant_schema == tenant_schema
    assert refresh_payload.type == "refresh"
