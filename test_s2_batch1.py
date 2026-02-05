"""
Test script for S2 Batch 1 implementation.

Tests:
1. S2-1: Config validation and fail-fast behavior
2. S2-4: Health check endpoints
"""
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))


def test_config_validation():
    """Test S2-1: Config validation."""
    print("\n" + "="*60)
    print("TEST 1: S2-1 Config Validation")
    print("="*60)
    
    # Test 1: Valid test environment config
    print("\n1.1 Testing valid test environment config...")
    os.environ['MPANGO_ENV'] = 'test'
    os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@localhost:5432/mpango_dev'
    os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
    os.environ['SECRET_KEY'] = 'dev-secret-key-change-me-but-at-least-32-chars-long'
    
    try:
        from core.config import validate_startup_config
        settings = validate_startup_config()
        print(f"✅ PASS: Test environment config validated")
        print(f"   Environment: {settings.MPANGO_ENV}")
        print(f"   Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")
        print(f"   Redis: {settings.REDIS_URL}")
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False
    
    # Test 2: Production with default secrets (should fail)
    print("\n1.2 Testing production with default secrets (should fail)...")
    os.environ['MPANGO_ENV'] = 'production'
    os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@localhost:5432/mpango_dev'
    
    try:
        # Clear cache
        from core.config import get_settings
        get_settings.cache_clear()
        
        settings = validate_startup_config()
        print(f"❌ FAIL: Should have raised ValueError for default DATABASE_URL in production")
        return False
    except ValueError as e:
        if "Production mode requires non-default DATABASE_URL" in str(e):
            print(f"✅ PASS: Correctly rejected default DATABASE_URL in production")
            print(f"   Error: {e}")
        else:
            print(f"❌ FAIL: Wrong error message: {e}")
            return False
    except Exception as e:
        print(f"❌ FAIL: Unexpected error: {e}")
        return False
    
    # Test 3: Invalid MPANGO_ENV (should fail)
    print("\n1.3 Testing invalid MPANGO_ENV (should fail)...")
    os.environ['MPANGO_ENV'] = 'invalid'
    
    try:
        get_settings.cache_clear()
        settings = validate_startup_config()
        print(f"❌ FAIL: Should have raised ValueError for invalid MPANGO_ENV")
        return False
    except ValueError as e:
        if "MPANGO_ENV must be 'production' or 'test'" in str(e):
            print(f"✅ PASS: Correctly rejected invalid MPANGO_ENV")
            print(f"   Error: {e}")
        else:
            print(f"❌ FAIL: Wrong error message: {e}")
            return False
    except Exception as e:
        print(f"❌ FAIL: Unexpected error: {e}")
        return False
    
    # Test 4: SECRET_KEY too short (should fail)
    print("\n1.4 Testing SECRET_KEY too short (should fail)...")
    os.environ['MPANGO_ENV'] = 'test'
    os.environ['SECRET_KEY'] = 'short'
    
    try:
        get_settings.cache_clear()
        settings = validate_startup_config()
        print(f"❌ FAIL: Should have raised ValueError for short SECRET_KEY")
        return False
    except ValueError as e:
        if "SECRET_KEY must be at least 32 characters" in str(e):
            print(f"✅ PASS: Correctly rejected short SECRET_KEY")
            print(f"   Error: {e}")
        else:
            print(f"❌ FAIL: Wrong error message: {e}")
            return False
    except Exception as e:
        print(f"❌ FAIL: Unexpected error: {e}")
        return False
    
    print("\n✅ All S2-1 config validation tests passed!")
    return True


def test_health_endpoints():
    """Test S2-4: Health check endpoints."""
    print("\n" + "="*60)
    print("TEST 2: S2-4 Health Check Endpoints")
    print("="*60)
    
    # Reset environment for valid config
    os.environ['MPANGO_ENV'] = 'test'
    os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@localhost:5432/mpango_dev'
    os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
    os.environ['SECRET_KEY'] = 'dev-secret-key-change-me-but-at-least-32-chars-long'
    
    print("\n2.1 Testing health check endpoint structure...")
    try:
        from api.v1.health import liveness_probe, readiness_probe
        print(f"✅ PASS: Health check endpoints imported successfully")
        print(f"   - liveness_probe: {liveness_probe}")
        print(f"   - readiness_probe: {readiness_probe}")
    except Exception as e:
        print(f"❌ FAIL: Could not import health endpoints: {e}")
        return False
    
    print("\n2.2 Testing liveness probe...")
    try:
        import asyncio
        result = asyncio.run(liveness_probe())
        print(f"✅ PASS: Liveness probe returned successfully")
        print(f"   Status: {result.status}")
        print(f"   Service: {result.service}")
    except Exception as e:
        print(f"❌ FAIL: Liveness probe failed: {e}")
        return False
    
    print("\n✅ All S2-4 health check tests passed!")
    print("   Note: Full readiness probe test requires running DB and Redis")
    return True


if __name__ == "__main__":
    print("\n" + "="*60)
    print("S2 BATCH 1 IMPLEMENTATION TEST SUITE")
    print("="*60)
    
    success = True
    
    # Run tests
    if not test_config_validation():
        success = False
    
    if not test_health_endpoints():
        success = False
    
    # Summary
    print("\n" + "="*60)
    if success:
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("\nS2 Batch 1 implementation is working correctly!")
        print("\nNext steps:")
        print("1. Install redis package: poetry add redis")
        print("2. Start the application: poetry run uvicorn main:app --reload")
        print("3. Test endpoints:")
        print("   - GET http://localhost:8000/healthz")
        print("   - GET http://localhost:8000/readyz")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        print("="*60)
        sys.exit(1)
