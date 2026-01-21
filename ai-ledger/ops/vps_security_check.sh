#!/bin/bash
# Mpango ERP - VPS Security Check Script
# Run this on your VPS to check for public exposure of Postgres/Redis

set -e

echo "========================================"
echo "Mpango VPS Security Check"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
check_fail() { echo -e "${RED}[FAIL]${NC} $1"; }
check_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo "=== Step 1: List all containers ==="
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
echo ""

echo "=== Step 2: Check for public exposure on ports 5432 (Postgres) and 6379 (Redis) ==="
echo "Checking with ss command..."
SS_OUTPUT=$(sudo ss -lntp 2>/dev/null | grep -E ':5432|:6379' || true)

if [ -z "$SS_OUTPUT" ]; then
    check_pass "No public listening on 5432/6379"
else
    echo "$SS_OUTPUT"
    if echo "$SS_OUTPUT" | grep -qE '0\.0\.0\.0:|:::'; then
        check_fail "CRITICAL: Ports are bound to 0.0.0.0 (publicly accessible)"
    else
        check_pass "Ports bound to localhost only"
    fi
fi
echo ""

echo "=== Step 3: Find backend containers ==="
BACKEND_CONTAINERS=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -Ei 'backend|api|server' || true)

if [ -z "$BACKEND_CONTAINERS" ]; then
    echo "No backend containers found"
else
    echo "Backend containers found:"
    echo "$BACKEND_CONTAINERS"
    echo ""

    echo "=== Step 4: Check backend environment variables for DB/Redis config ==="
    for CONTAINER in $BACKEND_CONTAINERS; do
        echo "--- Container: $CONTAINER ---"
        docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER" 2>/dev/null | grep -Ei 'POSTGRES|PG|DATABASE|DB_|REDIS' || echo "No DB/Redis env vars found"
        echo ""
    done
fi

echo "=== Step 5: Check compose files for port bindings ==="
for f in /opt/mpango/compose.yaml /opt/mpango/docker-compose.yml /opt/mpango/app/docker-compose.yml /opt/mpango/app/compose.yaml; do
    if [ -f "$f" ]; then
        echo "Found: $f"
        if grep -qE '5432|6379' "$f"; then
            if grep -qE 'ports:' "$f"; then
                check_warn "Port bindings found in $f - review for public exposure"
            fi
        fi
    fi
done
echo ""

echo "========================================"
echo "Security Check Complete"
echo "========================================"
