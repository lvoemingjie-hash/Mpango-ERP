function Require-SmokeInput([string]$Name) {
    $v = [Environment]::GetEnvironmentVariable($Name)
    if ($null -eq $v) { Write-Error "SMOKE_INPUT_MISSING: $Name"; exit 1 }
    if ($v -eq "") { Write-Error "SMOKE_INPUT_EMPTY: $Name"; exit 1 }
    if ($v.Trim() -eq "") { Write-Error "SMOKE_INPUT_WHITESPACE: $Name"; exit 1 }
    return $v
}
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:MPANGO_ENV = "production"
# Task-only throwaway inputs are caller-supplied environment variables.
$env:DATABASE_URL = Require-SmokeInput "MPANGO_SMOKE_DATABASE_URL"
$env:REDIS_URL = "redis://localhost:6379/1"
$env:SECRET_KEY = Require-SmokeInput "MPANGO_SMOKE_SECRET_KEY"
$env:PLATFORM_OPERATOR_SECRET = Require-SmokeInput "MPANGO_SMOKE_OPERATOR_SECRET"
$env:PLATFORM_TEST_OVERRIDE_SECRET = Require-SmokeInput "MPANGO_SMOKE_TEST_OVERRIDE_SECRET"
$env:ENABLE_METRICS = "false"
$env:ENABLE_SQL_PROFILING = "false"
Set-Location "c:\Users\Jeff0\MPANGO ERP\_p25ed_2026-07-08\backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000
