"""
Unit tests for password utilities.
Tests password hashing and verification using bcrypt.

Feature: identity-security
Property: P6 (Password Security)
"""
import pytest

from core.security import hash_password, verify_password


def test_hash_password_produces_different_hash_each_time():
    """
    Test that hash_password produces different hash each call due to salt.
    Property P6: Password Security
    """
    password = "my_secure_password_123"
    
    hash1 = hash_password(password)
    hash2 = hash_password(password)
    
    # Hashes should be different due to random salt
    assert hash1 != hash2
    
    # But both should verify correctly
    assert verify_password(password, hash1)
    assert verify_password(password, hash2)


def test_verify_password_returns_true_for_correct_password():
    """
    Test that verify_password returns True for correct password.
    Property P6: Password Security
    """
    password = "correct_password_456"
    hashed = hash_password(password)
    
    assert verify_password(password, hashed) is True


def test_verify_password_returns_false_for_wrong_password():
    """
    Test that verify_password returns False for wrong password.
    Property P6: Password Security
    """
    correct_password = "correct_password_789"
    wrong_password = "wrong_password_000"
    
    hashed = hash_password(correct_password)
    
    assert verify_password(wrong_password, hashed) is False


def test_password_hash_roundtrip():
    """
    Test that hashing then verifying preserves password correctness.
    Property P6: Password Security - roundtrip property
    
    Note: bcrypt has a 72-byte limit, so we test passwords within that limit.
    """
    passwords = [
        "simple",
        "with spaces and special chars!@#$%",
        "unicode_password_测试",
        "P@ssw0rd!",
        "123456789",
        "a" * 71  # Just under bcrypt's 72-byte limit
    ]
    
    for password in passwords:
        hashed = hash_password(password)
        assert verify_password(password, hashed), f"Failed for password: {password}"
        assert not verify_password(password + "x", hashed), f"False positive for: {password}"
