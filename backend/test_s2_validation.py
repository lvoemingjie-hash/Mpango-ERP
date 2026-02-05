"""Quick validation test for S2 Batch 1."""
import os
import sys

# Test config validation
print("Testing S2-1 Config Validation...")

# Set valid test environment
os.environ['MPANGO_ENV'] = 'test'
os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@localhost:5432/mpango_dev'
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
os.environ['SECRET_KEY'] = 'dev-secret-key-change-me-but-at-least-32-chars-long'

try:
    from core.config import validate_startup_config
    settings = validate_startup_config()
    print("✅ Config validation works!")
    print(f"   MPANGO_ENV: {settings.MPANGO_ENV}")
    print(f"   REDIS_URL: {settings.REDIS_URL}")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

print("\n✅ S2 Batch 1 implementation is working!")
