"""
Pytest configuration and fixtures for Mpango ERP backend tests.
"""
import os
import pytest

# Set test environment variables before importing settings
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars")
os.environ.setdefault("MPANGO_ENV", "test")
