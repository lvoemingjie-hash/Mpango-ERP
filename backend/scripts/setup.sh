#!/bin/bash
# Mpango ERP Setup Script  (H7-R5-R5 — effective-config preflight)
set -Eeuo pipefail

_on_err() {
    local line="$1" status="${2:-1}"
    echo "Setup stopped at line $line (exit status $status). Partial local artifacts may exist." >&2
    exit "$status"
}
trap '_on_err "$LINENO" "$?"' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "Setting up Mpango ERP (root: $REPO_ROOT)"

# ---- docker compose v2 (required for JSON config output) ---------------
COMPOSE=()
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    COMPOSE=(docker compose)
elif command -v docker-compose &> /dev/null && docker-compose version &> /dev/null; then
    if docker-compose config --format json &> /dev/null < /dev/null; then
        COMPOSE=(docker-compose)
    fi
fi
if [ "${#COMPOSE[@]}" -eq 0 ]; then
    echo "Docker Compose v2 is required." >&2; exit 1
fi

# =========================================================================
# PREFLIGHT — validate everything BEFORE any filesystem or service side effect
# =========================================================================

if [ ! -f backend/.env ]; then
    echo "backend/.env not found." >&2; exit 1
fi
if grep -qiE '(^|[^A-Z_])CHANGE_ME|CHANGEME' backend/.env 2>/dev/null; then
    echo "backend/.env contains CHANGE_ME placeholder values." >&2; exit 1
fi
if ! "${COMPOSE[@]}" config --quiet 2>/dev/null; then
    echo "docker-compose configuration is invalid." >&2; exit 1
fi

# Capture rendered Compose config as JSON to a temp file
COMPOSE_JSON_FILE="$(mktemp)"
"${COMPOSE[@]}" config --format json > "$COMPOSE_JSON_FILE" 2>/dev/null || {
    echo "Could not render Compose config as JSON." >&2; rm -f "$COMPOSE_JSON_FILE"; exit 1
}

# Write the preflight parser to a temp file (heredoc avoids inline $(...) issues)
PREFLIGHT_PY="$(mktemp)"
cat > "$PREFLIGHT_PY" <<'H7PREFLIGHT'
import sys, os, json
from urllib.parse import urlparse, unquote

def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)

# ---- read backend/.env (strict stdlib parser) ----
seen = {}
try:
    for lineno, line in enumerate(open("backend/.env"), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            fail(f"malformed .env line {lineno}: no = sign")
        k, v = s.split("=", 1)
        k = k.strip()
        if not k:
            fail(f"malformed .env line {lineno}: empty key")
        if k in seen:
            fail(f"duplicate key in .env: {k}")
        seen[k] = v.strip().strip("'").strip('"')
except FileNotFoundError:
    fail("backend/.env not readable")

file_db = seen.get("DATABASE_URL", "")
file_redis = seen.get("REDIS_URL", "")

# ---- process-env vs file conflict detection ----
proc_db = os.environ.get("DATABASE_URL_PROCESS", "")
proc_redis = os.environ.get("REDIS_URL_PROCESS", "")
if proc_db and proc_db != file_db:
    fail("DATABASE_URL conflict: process env differs from backend/.env")
if proc_redis and proc_redis != file_redis:
    fail("REDIS_URL conflict: process env differs from backend/.env")

if not file_db:
    fail("DATABASE_URL not found in backend/.env")
if not file_redis:
    fail("REDIS_URL not found in backend/.env")

# ---- parse DB URL ----
db_u = urlparse(file_db.replace("postgresql+asyncpg", "postgresql"))
if db_u.scheme != "postgresql":
    fail("DATABASE_URL scheme is not postgresql")
db_user = unquote(db_u.username or "")
db_pass = unquote(db_u.password or "")
db_host = db_u.hostname or ""
db_port = str(db_u.port or 5432)
db_name = db_u.path.lstrip("/") or ""
if not db_user or not db_name:
    fail("DATABASE_URL must have username and database")

# ---- parse Redis URL ----
rd_u = urlparse(file_redis)
rd_host = rd_u.hostname or ""
rd_port = str(rd_u.port or 6379)

# ---- load Compose JSON ----
try:
    cfg = json.load(open(os.environ["COMPOSE_JSON_FILE"]))
except Exception:
    fail("Could not parse Compose JSON")

services = cfg.get("services", {})
if not isinstance(services, dict):
    fail("Compose services is not a dict")

def validate_port_entry(svc_name, target_str, published_str):
    svc = services.get(svc_name)
    if not isinstance(svc, dict):
        fail(f"{svc_name} service is not a dict")
    env = svc.get("environment")
    if not isinstance(env, dict):
        fail(f"{svc_name} environment is not a dict")
    ports = svc.get("ports")
    if not isinstance(ports, list) or len(ports) != 1:
        fail(f"{svc_name} ports must be a list with exactly one entry")
    p = ports[0]
    if not isinstance(p, dict):
        fail(f"{svc_name} port entry is not a dict (string form rejected)")
    if p.get("mode") != "ingress":
        fail(f"{svc_name} mode must be ingress")
    if p.get("protocol") != "tcp":
        fail(f"{svc_name} protocol must be tcp")
    if p.get("host_ip") != "127.0.0.1":
        fail(f"{svc_name} host_ip must be 127.0.0.1")
    if str(p.get("target")) != target_str:
        fail(f"{svc_name} target must be {target_str}")
    if str(p.get("published")) != published_str:
        fail(f"{svc_name} published must be {published_str}")
    return env

pg_env = validate_port_entry("postgres", "5432", db_port)
rd_env = validate_port_entry("redis", "6379", rd_port)

# ---- credential comparison (in-memory only, never printed) ----
if db_user != pg_env.get("POSTGRES_USER", ""):
    fail("DATABASE_URL username does not match Compose POSTGRES_USER")
if db_pass != pg_env.get("POSTGRES_PASSWORD", ""):
    fail("DATABASE_URL password does not match Compose POSTGRES_PASSWORD")
if db_name != pg_env.get("POSTGRES_DB", ""):
    fail("DATABASE_URL database does not match Compose POSTGRES_DB")

# ---- host verification ----
if db_host not in ("localhost", "127.0.0.1", "::1"):
    fail("DATABASE_URL host must be local")
if rd_host not in ("localhost", "127.0.0.1", "::1"):
    fail("REDIS_URL host must be local")

print("OK")
H7PREFLIGHT

# Run the preflight (all secrets stay inside the Python process)
PREFLIGHT_RESULT="$(cd "$REPO_ROOT" \
    && COMPOSE_JSON_FILE="$COMPOSE_JSON_FILE" \
    DATABASE_URL_PROCESS="${DATABASE_URL:-}" \
    REDIS_URL_PROCESS="${REDIS_URL:-}" \
    python "$PREFLIGHT_PY" 2>&1)" || {
    echo "Preflight failed: $PREFLIGHT_RESULT" >&2
    rm -f "$PREFLIGHT_PY" "$COMPOSE_JSON_FILE"
    exit 1
}
rm -f "$PREFLIGHT_PY" "$COMPOSE_JSON_FILE"

if [ "$PREFLIGHT_RESULT" != "OK" ]; then
    echo "Preflight did not return OK." >&2; exit 1
fi
echo "Preflight OK."

# =========================================================================
# SIDE EFFECTS BEGIN HERE
# =========================================================================
mkdir -p logs uploads

if [ ! -f frontend/.env ]; then
    echo "Creating frontend .env"
    echo "VITE_API_URL=http://localhost:8000/api/v1" > frontend/.env
fi

echo "Starting Docker services"
"${COMPOSE[@]}" up -d postgres redis

MAX_ATTEMPTS="${SETUP_TIMEOUT_ATTEMPTS:-30}"
SLEEP_SECS="${SETUP_TIMEOUT_INTERVAL:-2}"

for i in $(seq 1 "$MAX_ATTEMPTS"); do
    if "${COMPOSE[@]}" exec -T postgres sh -ec 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' &> /dev/null; then break; fi
    [ "$i" -eq "$MAX_ATTEMPTS" ] && { echo "PostgreSQL not ready." >&2; exit 1; }
    sleep "$SLEEP_SECS"
done

for i in $(seq 1 "$MAX_ATTEMPTS"); do
    if "${COMPOSE[@]}" exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then break; fi
    [ "$i" -eq "$MAX_ATTEMPTS" ] && { echo "Redis not ready." >&2; exit 1; }
    sleep "$SLEEP_SECS"
done

echo "Installing backend dependencies"
cd "$REPO_ROOT/backend"
pip install -r requirements.txt

# Re-resolve through core.config.settings and assert equality with .env
POSTINSTALL_DB="$(python -c "from core.config import settings; print(settings.DATABASE_URL)" 2>/dev/null)" \
    || { echo "Could not re-resolve DATABASE_URL after pip install." >&2; exit 1; }
_env_recheck="$(python -c "
seen={}
for l in open('.env'):
    s=l.strip()
    if s and not s.startswith('#') and '=' in s:
        k,v=s.split('=',1); seen[k.strip()]=v.strip().strip(chr(39)).strip(chr(34))
print(seen.get('DATABASE_URL',''))
" 2>/dev/null)"
[ "$POSTINSTALL_DB" = "$_env_recheck" ] || {
    echo "DATABASE_URL changed after dependency installation." >&2; exit 1; }

echo "Running public Alembic migration"
alembic upgrade head

echo "Bootstrapping tenant schema"
export DATABASE_URL="$POSTINSTALL_DB"
python scripts/bootstrap_tenant_schema.py "${DEFAULT_TENANT_SCHEMA:-t_dev}"
unset DATABASE_URL

cd "$REPO_ROOT"
echo "Setting up frontend"
cd "$REPO_ROOT/frontend"
if command -v pnpm &> /dev/null; then
    PNPM_BIN="pnpm"
elif command -v corepack &> /dev/null; then
    corepack enable
    PNPM_BIN="pnpm"
else
    echo "pnpm is not installed." >&2; exit 1
fi
"$PNPM_BIN" install --frozen-lockfile

cd "$REPO_ROOT"
echo ""
echo "Setup complete!"
