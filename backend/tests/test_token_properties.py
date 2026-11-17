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


# Strategy for generating valid UUIDs — efficient structural generation
# (avoids HealthCheck.too_slow from slow regex backtracking)
uuid_strategy = st.uuids().map(str)

# Generate a real tenant binding, rather than an unrelated schema label.
tenant_binding_strategy = st.uuids().map(lambda value: (str(value), "t_" + value.hex))

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
    tenant=tenant_binding_strategy,
    credential_epoch=st.integers(min_value=1, max_value=9223372036854775807)
)
@settings(max_examples=20)  # Reduced from default 100 for faster execution
def test_property_token_roundtrip_integrity(user_id, tenant, credential_epoch):
    """
    Property P1: Token Roundtrip Integrity

    For any valid user_id, tenant_id, and tenant_schema:
    - Creating an access token and decoding it should preserve all claims
    - Creating a refresh token and decoding it should preserve all claims
    """
    # Test access token
    tenant_id, tenant_schema = tenant
    access_token = create_access_token(user_id, tenant_id, tenant_schema, credential_epoch=credential_epoch)
    access_payload = decode_token(access_token)

    assert access_payload.user_id == user_id
    assert access_payload.tenant_id == tenant_id
    assert access_payload.tenant_schema == tenant_schema
    assert access_payload.type == "access"
    assert access_payload.credential_epoch == credential_epoch

    # Test refresh token
    refresh_token = create_refresh_token(user_id, tenant_id, tenant_schema, credential_epoch=credential_epoch)
    refresh_payload = decode_token(refresh_token)

    assert refresh_payload.user_id == user_id
    assert refresh_payload.tenant_id == tenant_id
    assert refresh_payload.tenant_schema == tenant_schema
    assert refresh_payload.type == "refresh"
    assert refresh_payload.credential_epoch == credential_epoch


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
    tenant=tenant_binding_strategy,
    credential_epoch=st.integers(min_value=1, max_value=9223372036854775807)
)
@settings(max_examples=20)  # Reduced from default 100 for faster execution
def test_property_refresh_preserves_claims(user_id, tenant, credential_epoch):
    """
    Property P8: Refresh Preserves Claims

    For any token claims:
    - Creating a refresh token and decoding it should preserve tenant_id and tenant_schema
    - These values should be identical to the original input
    """
    tenant_id, tenant_schema = tenant
    refresh_token = create_refresh_token(user_id, tenant_id, tenant_schema, credential_epoch=credential_epoch)
    payload = decode_token(refresh_token)

    # Verify claims are preserved
    assert payload.user_id == user_id
    assert payload.tenant_id == tenant_id
    assert payload.tenant_schema == tenant_schema

    # Simulate refresh flow: use decoded payload to create new tokens
    new_access_token = create_access_token(
        payload.user_id,
        payload.tenant_id,
        payload.tenant_schema,
        credential_epoch=payload.credential_epoch,
    )
    new_refresh_token = create_refresh_token(
        payload.user_id,
        payload.tenant_id,
        payload.tenant_schema,
        credential_epoch=payload.credential_epoch,
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
    tenant=tenant_binding_strategy,
    credential_epoch=st.integers(min_value=1, max_value=9223372036854775807)
)
@settings(max_examples=20)  # Reduced from default 100 for faster execution
def test_property_token_type_is_preserved(user_id, tenant, credential_epoch):
    """
    Property P7: Token Type Separation

    For any token claims:
    - Access tokens always have type="access"
    - Refresh tokens always have type="refresh"
    - Token type is preserved through encode/decode
    """
    tenant_id, tenant_schema = tenant
    access_token = create_access_token(user_id, tenant_id, tenant_schema, credential_epoch=credential_epoch)
    access_payload = decode_token(access_token)
    assert access_payload.type == "access"
    assert access_payload.credential_epoch == credential_epoch

    refresh_token = create_refresh_token(user_id, tenant_id, tenant_schema, credential_epoch=credential_epoch)
    refresh_payload = decode_token(refresh_token)
    assert refresh_payload.type == "refresh"
    assert refresh_payload.credential_epoch == credential_epoch
