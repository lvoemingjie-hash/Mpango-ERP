"""
Property-based tests for token and password utilities using Hypothesis.
Tests universal properties across many generated inputs.

Feature: identity-security
Properties: P1 (Token Integrity), P6 (Password Security), P8 (Refresh Preserves Claims)
"""
import pytest
from hypothesis import given, strategies as st, settings
from datetime import timedelta

from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    TokenPayload
)


# Strategy for generating valid UUIDs
uuid_strategy = st.from_regex(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    fullmatch=True
)

# Strategy for generating tenant schema names
tenant_schema_strategy = st.from_regex(
    r'^t_[0-9a-f]{32}$',
    fullmatch=True
)

# Strategy for generating passwords (within bcrypt's 72-byte limit, no NULL bytes)
password_strategy = st.text(
    alphabet=st.characters(
        blacklist_categories=('Cs',),  # Exclude surrogates
        blacklist_characters='\x00'  # Exclude NULL bytes (bcrypt doesn't allow them)
    ),
    min_size=1,
    max_size=71
)


@given(
    user_id=uuid_strategy,
    tenant_id=uuid_strategy,
    tenant_schema=tenant_schema_strategy
)
@settings(max_examples=20)  # Reduced from default 100 for faster execution
def test_property_token_roundtrip_integrity(user_id, tenant_id, tenant_schema):
    """
    Property P1: Token Roundtrip Integrity

    For any valid user_id, tenant_id, and tenant_schema:
    - Creating an access token and decoding it should preserve all claims
    - Creating a refresh token and decoding it should preserve all claims
    """
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


@given(password=password_strategy)
@settings(deadline=None, max_examples=20)  # Reduced examples for faster bcrypt operations
def test_property_password_hash_verify_roundtrip(password):
    """
    Property P6: Password Security - Hash/Verify Roundtrip

    For any password:
    - hash_password(p) then verify_password(p, hash) should return True
    - hash_password(p) then verify_password(p', hash) where p' != p should return False

    Note: bcrypt truncates at 72 bytes, so we ensure wrong password differs in first 70 bytes
    """
    hashed = hash_password(password)

    # Correct password should verify
    assert verify_password(password, hashed) is True

    # Wrong password should not verify
    # Ensure the difference is in the first 70 bytes (well within bcrypt's 72-byte limit)
    if len(password) > 0:
        # Change first character to ensure it's different within bcrypt's limit
        wrong_password = "X" + password[1:] if password[0] != "X" else "Y" + password[1:]
        assert verify_password(wrong_password, hashed) is False


@given(
    user_id=uuid_strategy,
    tenant_id=uuid_strategy,
    tenant_schema=tenant_schema_strategy
)
@settings(max_examples=20)  # Reduced from default 100 for faster execution
def test_property_refresh_preserves_claims(user_id, tenant_id, tenant_schema):
    """
    Property P8: Refresh Preserves Claims

    For any token claims:
    - Creating a refresh token and decoding it should preserve tenant_id and tenant_schema
    - These values should be identical to the original input
    """
    refresh_token = create_refresh_token(user_id, tenant_id, tenant_schema)
    payload = decode_token(refresh_token)

    # Verify claims are preserved
    assert payload.user_id == user_id
    assert payload.tenant_id == tenant_id
    assert payload.tenant_schema == tenant_schema

    # Simulate refresh flow: use decoded payload to create new tokens
    new_access_token = create_access_token(
        payload.user_id,
        payload.tenant_id,
        payload.tenant_schema
    )
    new_refresh_token = create_refresh_token(
        payload.user_id,
        payload.tenant_id,
        payload.tenant_schema
    )

    # Decode new tokens
    new_access_payload = decode_token(new_access_token)
    new_refresh_payload = decode_token(new_refresh_token)

    # Verify claims are still preserved
    assert new_access_payload.user_id == user_id
    assert new_access_payload.tenant_id == tenant_id
    assert new_access_payload.tenant_schema == tenant_schema

    assert new_refresh_payload.user_id == user_id
    assert new_refresh_payload.tenant_id == tenant_id
    assert new_refresh_payload.tenant_schema == tenant_schema


@given(password=password_strategy)
@settings(deadline=None, max_examples=20)  # Reduced examples for faster bcrypt operations
def test_property_password_hash_is_deterministic_for_verification(password):
    """
    Property P6: Password hash verification is consistent

    For any password:
    - Multiple verifications of the same password against the same hash should always return True
    - This tests that verify_password is deterministic
    """
    hashed = hash_password(password)

    # Verify multiple times - should always return True
    for _ in range(5):
        assert verify_password(password, hashed) is True


@given(
    user_id=uuid_strategy,
    tenant_id=uuid_strategy,
    tenant_schema=tenant_schema_strategy
)
@settings(max_examples=20)  # Reduced from default 100 for faster execution
def test_property_token_type_is_preserved(user_id, tenant_id, tenant_schema):
    """
    Property P7: Token Type Separation

    For any token claims:
    - Access tokens always have type="access"
    - Refresh tokens always have type="refresh"
    - Token type is preserved through encode/decode
    """
    access_token = create_access_token(user_id, tenant_id, tenant_schema)
    access_payload = decode_token(access_token)
    assert access_payload.type == "access"

    refresh_token = create_refresh_token(user_id, tenant_id, tenant_schema)
    refresh_payload = decode_token(refresh_token)
    assert refresh_payload.type == "refresh"
