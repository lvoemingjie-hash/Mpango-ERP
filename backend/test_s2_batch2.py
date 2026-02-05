"""
Test script for S2 Batch 2 implementation.

Tests:
1. S2-2: Structured logging with context injection
2. S2-6: Error codes and exception handling
3. S2-3: Prometheus metrics
"""
import os
import sys

# Set test environment
os.environ['MPANGO_ENV'] = 'test'
os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@localhost:5432/mpango_dev'
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
os.environ['SECRET_KEY'] = 'dev-secret-key-change-me-but-at-least-32-chars-long'

print("\n" + "="*60)
print("S2 BATCH 2 IMPLEMENTATION TEST SUITE")
print("="*60)


def test_structured_logging():
    """Test S2-2: Structured logging."""
    print("\n" + "="*60)
    print("TEST 1: S2-2 Structured Logging")
    print("="*60)
    
    try:
        from core.structured_logging import (
            setup_structured_logging,
            set_request_context,
            clear_request_context,
            get_logger
        )
        
        # Setup logging
        setup_structured_logging(level="INFO")
        print("✅ Structured logging setup successful")
        
        # Get logger
        logger = get_logger(__name__)
        print("✅ Logger created")
        
        # Set context
        set_request_context(
            request_id="test-request-123",
            tenant_schema="t_test",
            user_id="user-456",
            route="/api/v1/test",
            method="POST"
        )
        print("✅ Request context set")
        
        # Log message (should include context automatically)
        logger.info("Test log message", extra={"test_field": "test_value"})
        print("✅ Log message with context")
        
        # Clear context
        clear_request_context()
        print("✅ Request context cleared")
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_codes():
    """Test S2-6: Error codes."""
    print("\n" + "="*60)
    print("TEST 2: S2-6 Central Error Codes")
    print("="*60)
    
    try:
        from core.error_codes import (
            ErrorCode,
            MpangoAPIException,
            create_error_response
        )
        
        # Test error code enum
        assert ErrorCode.UNAUTHORIZED == "UNAUTHORIZED"
        assert ErrorCode.PAYMENT_IDEMPOTENCY_CONFLICT == "PAYMENT_IDEMPOTENCY_CONFLICT"
        print("✅ Error code enum works")
        
        # Test custom exception
        exc = MpangoAPIException(
            error_code=ErrorCode.PAYMENT_IDEMPOTENCY_CONFLICT,
            message="Test error message",
            status_code=409,
            details={"key": "value"}
        )
        assert exc.error_code == ErrorCode.PAYMENT_IDEMPOTENCY_CONFLICT
        assert exc.status_code == 409
        print("✅ MpangoAPIException works")
        
        # Test error response format
        response = create_error_response(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Validation failed",
            status_code=422,
            request_id="test-123",
            details={"field": "email"}
        )
        assert response["code"] == "VALIDATION_ERROR"
        assert response["message"] == "Validation failed"
        assert response["request_id"] == "test-123"
        assert response["details"]["field"] == "email"
        print("✅ Error response format correct")
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_prometheus_metrics():
    """Test S2-3: Prometheus metrics."""
    print("\n" + "="*60)
    print("TEST 3: S2-3 Prometheus Metrics")
    print("="*60)
    
    try:
        from core.prometheus_metrics import (
            http_requests_total,
            http_request_duration_seconds,
            http_requests_in_progress,
            db_transactions_total,
            idempotency_conflicts_total,
            record_db_transaction,
            record_idempotency_conflict,
            get_metrics
        )
        
        # Test metrics exist
        assert http_requests_total is not None
        assert http_request_duration_seconds is not None
        assert http_requests_in_progress is not None
        print("✅ HTTP metrics defined")
        
        assert db_transactions_total is not None
        assert idempotency_conflicts_total is not None
        print("✅ Business metrics defined")
        
        # Test recording metrics
        record_db_transaction(tenant="t_test", operation="insert", status="success")
        print("✅ DB transaction recorded")
        
        record_idempotency_conflict(tenant="t_test", endpoint="/api/v1/payments")
        print("✅ Idempotency conflict recorded")
        
        # Test metrics export
        metrics_data = get_metrics()
        assert isinstance(metrics_data, bytes)
        assert b"db_transactions_total" in metrics_data
        print("✅ Metrics export works")
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_middleware_imports():
    """Test middleware imports."""
    print("\n" + "="*60)
    print("TEST 4: Middleware Imports")
    print("="*60)
    
    try:
        from api.middleware.request_logging import RequestLoggingMiddleware
        print("✅ RequestLoggingMiddleware imported")
        
        from core.prometheus_metrics import PrometheusMetricsMiddleware
        print("✅ PrometheusMetricsMiddleware imported")
        
        from api.middleware.auth import AuthenticationMiddleware
        print("✅ AuthenticationMiddleware imported")
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = True
    
    # Run tests
    if not test_structured_logging():
        success = False
    
    if not test_error_codes():
        success = False
    
    if not test_prometheus_metrics():
        success = False
    
    if not test_middleware_imports():
        success = False
    
    # Summary
    print("\n" + "="*60)
    if success:
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("\nS2 Batch 2 implementation is working correctly!")
        print("\nNext steps:")
        print("1. Start the application: poetry run uvicorn main:app --reload")
        print("2. Test endpoints:")
        print("   - GET http://localhost:8000/metrics (Prometheus metrics)")
        print("   - POST http://localhost:8000/api/v1/orders (Check logs)")
        print("3. Verify structured logs in console output")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        print("="*60)
        sys.exit(1)
