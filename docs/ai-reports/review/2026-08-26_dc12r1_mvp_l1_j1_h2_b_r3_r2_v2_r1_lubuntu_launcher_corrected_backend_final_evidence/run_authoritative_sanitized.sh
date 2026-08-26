#!/bin/bash
# Task-private authoritative runner — B1-R3-R2-V2-R1 launcher correction.
# NOT committed to any product branch. Fail-closed before pytest collection.
set -u
TASK=/home/ivy/MPANGO/r3r2r1_task
EV=$TASK/evidence
mkdir -p "$EV"

# --- construct DATABASE_URL in-process (values from task-private file) ---
PG_PW="<redacted-from-task-private-file>"
: "${PG_PW:?PG password missing}"
export DATABASE_URL="postgresql://r3r2tester:${PG_PW}@127.0.0.1:15603/test_r3r2r1_auth"
export REDIS_URL="redis://127.0.0.1:16603/0"
export PW1R3_TEST_REDIS_URL="redis://127.0.0.1:16603/15"
export MPANGO_ENV=test
export MPANGO_ALLOW_TEMP_DB_CREATE=1
export MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1
export MPANGO_TEMP_DB_ALLOWED_PORTS=15603
export REPORTING_USER_PASSWORD="R3R2R1authPlaceholder1!"
export PYTHONDONTWRITEBYTECODE=1
export J1H2B_EXPECTED_HOST=127.0.0.1
export J1H2B_EXPECTED_PORT=15603
export J1H2B_EXPECTED_DATABASE=test_r3r2r1_auth
export J1H2B_EXPECTED_REDIS_PORT=16603
export J1H2B_SESSION_PROOF_PATH="$EV/launcher_env_proof_pytest_session.json"

# --- mandated correction: derive TEST_DATABASE_URL AFTER DATABASE_URL exists, in this process ---
: "${DATABASE_URL:?DATABASE_URL missing or empty}"
export TEST_DATABASE_URL="${DATABASE_URL}"
: "${TEST_DATABASE_URL:?TEST_DATABASE_URL missing or empty}"

# --- sanitized pre-exec proof inside THIS shell's environment (before exec) ---
"$TASK/venv/bin/python" - <<'EOF'
import json, os, sys
from urllib.parse import urlparse
db = os.environ.get("DATABASE_URL", "")
tdb = os.environ.get("TEST_DATABASE_URL", "")
def parse(url):
    p = urlparse(url if "//" in url else "//" + url)
    return {"host": p.hostname or "", "port": str(p.port or ""), "database": (p.path or "").lstrip("/")}
pdb, ptdb = parse(db), parse(tdb)
pr0, pr15 = parse(os.environ.get("REDIS_URL","")), parse(os.environ.get("PW1R3_TEST_REDIS_URL",""))
proof = {
  "phase": "pre_exec",
  "pid": os.getpid(),
  "DATABASE_URL_nonempty": bool(db),
  "TEST_DATABASE_URL_set": "TEST_DATABASE_URL" in os.environ,
  "TEST_DATABASE_URL_nonempty": bool(tdb),
  "equals_DATABASE_URL": tdb == db and bool(tdb),
  "expected_host": ptdb["host"] == "127.0.0.1",
  "expected_port": ptdb["port"] == "15603",
  "expected_database": ptdb["database"] == "test_r3r2r1_auth",
  "parsed_host": ptdb["host"], "parsed_port": ptdb["port"], "parsed_database": ptdb["database"],
  "REDIS_URL_nonempty": bool(os.environ.get("REDIS_URL")),
  "PW1R3_TEST_REDIS_URL_nonempty": bool(os.environ.get("PW1R3_TEST_REDIS_URL")),
  "redis_ports_match_expected": pr0["port"] == "16603" and pr15["port"] == "16603",
  "no_26379_in_urls": all("26379" not in (os.environ.get(v) or "") for v in ("DATABASE_URL","TEST_DATABASE_URL","REDIS_URL","PW1R3_TEST_REDIS_URL"))
}
with open("/home/ivy/MPANGO/r3r2r1_task/evidence/launcher_env_proof_pre_exec.json","w") as f:
    json.dump(proof, f, indent=2)
required = ["DATABASE_URL_nonempty","TEST_DATABASE_URL_set","TEST_DATABASE_URL_nonempty","equals_DATABASE_URL",
            "expected_host","expected_port","expected_database","REDIS_URL_nonempty",
            "PW1R3_TEST_REDIS_URL_nonempty","redis_ports_match_expected","no_26379_in_urls"]
if not all(proof[k] for k in required):
    print("ENV PROBE FAILED PRE-EXEC:", json.dumps(proof), file=sys.stderr)
    sys.exit(9)
print("PRE-EXEC ENV PROOF: ALL TRUE")
EOF
RC=$?
[ $RC -eq 0 ] || { echo "VOID_ENVIRONMENT_PRECHECK: pre-exec proof failed (rc=$RC); exiting before pytest collection"; exit 9; }

# --- single authoritative run; exec so pytest inherits THIS exact environment ---
cd /home/ivy/MPANGO/dc12r1-r3r2r1-backend-wt/backend
export PYTHONPATH="/home/ivy/MPANGO/r3r2r1_task${PYTHONPATH:+:$PYTHONPATH}"
exec /home/ivy/MPANGO/r3r2r1_task/venv/bin/python -m pytest -p j1h2b_r3r2r1_envprobe -p no:cacheprovider tests \
  --junitxml="$EV/full_junit.xml"
