"""
S2.5 Batch B: Security Tests for Data Privacy & Tenant Isolation

Tests for:
1. Sensitive data masking in production errors
2. Log sanitization for sensitive fields
3. Tenant isolation enforcement
"""
import json
import logging
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import Request
from fastapi.testclient import TestClient

from core.structured_logging import (
    sanitize_log_data,
    StructuredJsonFormatter,
    SENSITIVE_FIELD_PATTERNS,
    MASK_VALUE
)
from core.error_codes import generic_exception_handler, ErrorCode
from api.middleware.auth import AuthenticationMiddleware


class TestSensitiveDataMasking:
    """Test that sensitive data is masked in logs and error responses."""
    
    def test_sanitize_simple_password(self):
        """Test that password field is masked."""
        data = {"username": "john", "password": "secret123"}
        sanitized = sanitize_log_data(data)
        
        assert sanitized["username"] == "john"
        assert sanitized["password"] == MASK_VALUE
    
    def test_sanitize_nested_dict(self):
        """Test that nested sensitive fields are masked."""
        data = {
            "user": {
                "name": "john",
                "credentials": {
                    "password": "secret123",
                    "api_key": "abc123"
                }
            }
        }
        sanitized = sanitize_log_data(data)
        
        assert sanitized["user"]["name"] == "john"
        assert sanitized["user"]["credentials"]["password"] == MASK_VALUE
        assert sanitized["user"]["credentials"]["api_key"] == MASK_VALUE
    
    def test_sanitize_list_of_dicts(self):
        """Test that sensitive fields in lists are masked."""
        data = {
            "users": [
                {"name": "john", "token": "token1"},
                {"name": "jane", "secret_key": "secret2"}
            ]
        }
        sanitized = sanitize_log_data(data)
        
        assert sanitized["users"][0]["name"] == "john"
        assert sanitized["users"][0]["token"] == MASK_VALUE
        assert sanitized["users"][1]["name"] == "jane"
        assert sanitized["users"][1]["secret_key"] == MASK_VALUE
    
    def test_sanitize_all_sensitive_patterns(self):
        """Test that all sensitive field patterns are masked."""
        data = {
            "password": "pass123",
            "passwd": "pass456",
            "pwd": "pass789",
            "token": "tok123",
            "access_token": "tok456",
            "refresh_token": "tok789",
            "api_key": "key123",
            "apikey": "key456",
            "secret": "sec123",
            "secret_key": "sec456",
            "client_secret": "sec789",
            "authorization": "auth123",
            "auth": "auth456",
            "credit_card": "1234567890123456",
            "card_number": "9876543210987654",
            "cvv": "123",
            "ccv": "456",
            "ssn": "123-45-6789",
            "social_security": "987-65-4321",
            "private_key": "priv123",
            "priv_key": "priv456"
        }
        sanitized = sanitize_log_data(data)
        
        # All values should be masked
        for key in data.keys():
            assert sanitized[key] == MASK_VALUE, f"Field {key} was not masked"
    
    def test_sanitize_case_insensitive(self):
        """Test that field matching is case-insensitive."""
        data = {
            "PASSWORD": "pass123",
            "Token": "tok123",
            "API_KEY": "key123",
            "Secret_Key": "sec123"
        }
        sanitized = sanitize_log_data(data)
        
        assert sanitized["PASSWORD"] == MASK_VALUE
        assert sanitized["Token"] == MASK_VALUE
        assert sanitized["API_KEY"] == MASK_VALUE
        assert sanitized["Secret_Key"] == MASK_VALUE
    
    def test_sanitize_preserves_non_sensitive(self):
        """Test that non-sensitive fields are not masked."""
        data = {
            "username": "john",
            "email": "john@example.com",
            "age": 30,
            "active": True,
            "metadata": {"key": "value"}
        }
        sanitized = sanitize_log_data(data)
        
        assert sanitized == data  # Should be unchanged
    
    def test_structured_json_formatter_sanitizes_extra_fields(self):
        """Test that StructuredJsonFormatter sanitizes extra fields."""
        formatter = StructuredJsonFormatter()
        
        # Create a log record with sensitive data in extra fields
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )
        # Add sensitive fields as extra attributes
        setattr(record, 'password', "secret123")
        setattr(record, 'api_key', "key123")
        setattr(record, 'username', "john")
        
        formatted = formatter.format(record)
        log_entry = json.loads(formatted)
        
        # Sensitive fields should be masked
        assert log_entry["password"] == MASK_VALUE
        assert log_entry["api_key"] == MASK_VALUE
        # Non-sensitive fields should be preserved
        assert log_entry["username"] == "john"


class TestProductionErrorMasking:
    """Test that production errors don't expose internal details."""
    
    @pytest.mark.asyncio
    async def test_production_error_hides_exception_type(self):
        """Test that production errors don't expose exception types."""
        # Mock request
        request = MagicMock(spec=Request)
        request.state.request_id = "test-request-id"
        
        # Create a test exception
        exc = ValueError("Database connection failed: psycopg2.OperationalError")
        
        # Mock settings to return production
        with patch('core.config.get_settings') as mock_settings:
            mock_settings.return_value.MPANGO_ENV = "production"
            
            response = await generic_exception_handler(request, exc)
            
            # Parse response
            content = json.loads(response.body.decode())
            
            # Should not contain exception type or message
            assert "ValueError" not in content["message"]
            assert "Database connection failed" not in content["message"]
            assert "psycopg2" not in content["message"]
            assert "OperationalError" not in content["message"]
            
            # Should contain generic message
            assert "internal server error" in content["message"].lower()
            assert "contact support" in content["message"].lower()
            
            # Should not have details field in production
            assert content.get("details") is None
    
    @pytest.mark.asyncio
    async def test_production_error_hides_file_paths(self):
        """Test that production errors don't expose file paths."""
        request = MagicMock(spec=Request)
        request.state.request_id = "test-request-id"
        
        exc = RuntimeError("/app/backend/services/payment.py line 42: Division by zero")
        
        with patch('core.config.get_settings') as mock_settings:
            mock_settings.return_value.MPANGO_ENV = "production"
            
            response = await generic_exception_handler(request, exc)
            content = json.loads(response.body.decode())
            
            # Should not contain file paths
            assert "/app/backend" not in content["message"]
            assert "payment.py" not in content["message"]
            assert "line 42" not in content["message"]
    
    @pytest.mark.asyncio
    async def test_non_production_error_shows_details(self):
        """Test that non-production errors show exception details for debugging."""
        request = MagicMock(spec=Request)
        request.state.request_id = "test-request-id"
        
        exc = ValueError("Test error message")
        
        with patch('core.config.get_settings') as mock_settings:
            mock_settings.return_value.MPANGO_ENV = "development"
            
            response = await generic_exception_handler(request, exc)
            content = json.loads(response.body.decode())
            
            # Should contain exception type and message
            assert "ValueError" in content["message"]
            assert "Test error message" in content["message"]
            
            # Should have details field
            assert content.get("details") is not None
            assert content["details"]["exception_type"] == "ValueError"
    
    @pytest.mark.asyncio
    async def test_production_error_includes_request_id(self):
        """Test that production errors include request_id for support."""
        request = MagicMock(spec=Request)
        request.state.request_id = "test-request-123"
        
        exc = Exception("Internal error")
        
        with patch('core.config.get_settings') as mock_settings:
            mock_settings.return_value.MPANGO_ENV = "production"
            
            response = await generic_exception_handler(request, exc)
            content = json.loads(response.body.decode())
            
            # Should include request_id for support tracking
            assert content["request_id"] == "test-request-123"
            assert content["code"] == ErrorCode.INTERNAL_SERVER_ERROR.value


class TestTenantIsolationEnforcement:
    """Test that tenant isolation is strictly enforced."""
    
    @pytest.mark.asyncio
    async def test_missing_tenant_schema_raises_error(self):
        """Test that missing tenant_schema for authenticated request raises error."""
        from api.context.tenant import TenantContext
        from api.context.auth import AuthContext
        from auth.strategy import AuthStrategy
        from core.security import TokenPayload
        
        # Create mock strategy
        mock_strategy = MagicMock(spec=AuthStrategy)
        
        # Mock auth context (authenticated user)
        mock_token = TokenPayload(
            user_id="user-123",
            tenant_id="tenant-123",
            tenant_schema="t_test",
            roles=["retailer"]
        )
        auth_ctx = AuthContext(
            token=mock_token,
            raw_token="fake-jwt-token"
        )
        mock_strategy.authenticate.return_value = auth_ctx
        
        # Mock tenant context with missing tenant_schema
        mock_session = AsyncMock()
        tenant_ctx = TenantContext(
            tenant_id="tenant-123",
            tenant_schema=None,  # Missing!
            session=mock_session,
            user=MagicMock()
        )
        mock_strategy.resolve_tenant_context.return_value = tenant_ctx
        
        # Create middleware
        app = MagicMock()
        middleware = AuthenticationMiddleware(app, strategy=mock_strategy)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        
        # Mock call_next
        async def mock_call_next(req):
            return MagicMock(status_code=200)
        
        # Should raise MpangoAPIException
        from core.error_codes import MpangoAPIException
        with pytest.raises(MpangoAPIException) as exc_info:
            await middleware.dispatch(request, mock_call_next)
        
        assert exc_info.value.error_code == ErrorCode.INTERNAL_SERVER_ERROR
        assert "tenant isolation" in exc_info.value.message.lower()
    
    @pytest.mark.asyncio
    async def test_valid_tenant_schema_passes(self):
        """Test that valid tenant_schema allows request to proceed."""
        from api.context.tenant import TenantContext
        from api.context.auth import AuthContext
        from auth.strategy import AuthStrategy
        from core.security import TokenPayload
        
        # Create mock strategy
        mock_strategy = MagicMock(spec=AuthStrategy)
        
        # Mock auth context
        mock_token = TokenPayload(
            user_id="user-123",
            tenant_id="tenant-123",
            tenant_schema="t_test",
            roles=["retailer"]
        )
        auth_ctx = AuthContext(
            token=mock_token,
            raw_token="fake-jwt-token"
        )
        mock_strategy.authenticate.return_value = auth_ctx
        
        # Mock tenant context with valid tenant_schema
        mock_session = AsyncMock()
        tenant_ctx = TenantContext(
            tenant_id="tenant-123",
            tenant_schema="t_test",  # Valid!
            session=mock_session,
            user=MagicMock()
        )
        mock_strategy.resolve_tenant_context.return_value = tenant_ctx
        
        # Create middleware
        app = MagicMock()
        middleware = AuthenticationMiddleware(app, strategy=mock_strategy)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        
        # Mock call_next
        async def mock_call_next(req):
            response = MagicMock()
            response.status_code = 200
            return response
        
        # Should not raise exception
        response = await middleware.dispatch(request, mock_call_next)
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_unauthenticated_request_skips_tenant_check(self):
        """Test that unauthenticated requests skip tenant isolation check."""
        from auth.strategy import AuthStrategy
        
        # Create mock strategy
        mock_strategy = MagicMock(spec=AuthStrategy)
        
        # Mock no auth context (unauthenticated)
        mock_strategy.authenticate.return_value = None
        
        # Create middleware
        app = MagicMock()
        middleware = AuthenticationMiddleware(app, strategy=mock_strategy)
        
        # Create mock request
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        
        # Mock call_next
        async def mock_call_next(req):
            response = MagicMock()
            response.status_code = 200
            return response
        
        # Should not raise exception (no tenant check for unauthenticated)
        response = await middleware.dispatch(request, mock_call_next)
        assert response.status_code == 200


class TestSecurityRegressionTests:
    """Regression tests to ensure security fixes remain in place."""
    
    def test_sensitive_field_patterns_not_empty(self):
        """Test that sensitive field patterns are defined."""
        assert len(SENSITIVE_FIELD_PATTERNS) > 0
        assert 'password' in SENSITIVE_FIELD_PATTERNS
        assert 'token' in SENSITIVE_FIELD_PATTERNS
        assert 'secret' in SENSITIVE_FIELD_PATTERNS
    
    def test_mask_value_is_not_empty(self):
        """Test that mask value is defined."""
        assert MASK_VALUE == "******"
    
    @pytest.mark.asyncio
    async def test_production_env_check_works(self):
        """Test that production environment check works correctly."""
        request = MagicMock(spec=Request)
        request.state.request_id = "test"
        exc = Exception("test")
        
        # Test production
        with patch('core.config.get_settings') as mock_settings:
            mock_settings.return_value.MPANGO_ENV = "production"
            response = await generic_exception_handler(request, exc)
            content = json.loads(response.body.decode())
            assert "Exception" not in content["message"]
        
        # Test non-production
        with patch('core.config.get_settings') as mock_settings:
            mock_settings.return_value.MPANGO_ENV = "development"
            response = await generic_exception_handler(request, exc)
            content = json.loads(response.body.decode())
            assert "Exception" in content["message"]
