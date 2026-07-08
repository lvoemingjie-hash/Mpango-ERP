$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:MPANGO_ENV = "production"
# All secrets below are THROWAWAY test-only values for the disposable smoke stack.
$env:DATABASE_URL = "postgresql://mpango:p25ec_throwaway_pw@localhost:5433/mpango_erp"  # pragma: allowlist secret
$env:REDIS_URL = "redis://localhost:6379/1"
$env:SECRET_KEY = "pHFmxXthWP58Gng5AILZ6yyw4GhIVTbf6wUJ2S8RQyU"  # pragma: allowlist secret
$env:PLATFORM_OPERATOR_SECRET = "test-operator-secret"  # pragma: allowlist secret
$env:PLATFORM_TEST_OVERRIDE_SECRET = "test-platform-override-secret"  # pragma: allowlist secret
$env:ENABLE_METRICS = "false"
$env:ENABLE_SQL_PROFILING = "false"
Set-Location "c:\Users\Jeff0\MPANGO ERP\_p25ed_2026-07-08\backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000
