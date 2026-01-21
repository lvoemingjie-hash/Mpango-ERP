#!/bin/bash
# Mpango ERP - VPS Security Remediation Script
# Run this on your VPS to fix public exposure of Postgres/Redis

set -e

echo "========================================"
echo "Mpango VPS Security Remediation"
echo "========================================"
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Stop and remove existing containers (preserve volumes)
cleanup_containers() {
    log_info "Stopping and removing old containers..."

    # Common container name patterns
    CONTAINERS=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -Ei 'mpango|postgres|redis|backend' || true)

    if [ -z "$CONTAINERS" ]; then
        log_warn "No mpango containers found to clean up"
    else
        echo "$CONTAINERS" | while read -r name; do
            if [ -n "$name" ]; then
                log_info "Stopping: $name"
                docker stop "$name" 2>/dev/null || true
                log_info "Removing: $name"
                docker rm "$name" 2>/dev/null || true
            fi
        done
    fi
}

# Create compose.yaml without public port bindings
create_compose() {
    log_info "Creating compose.yaml with internal networking only..."

    COMPOSE_DIR="/opt/mpango"
    mkdir -p "$COMPOSE_DIR"

    cat > "$COMPOSE_DIR/compose.yaml" << 'EOF'
services:
  postgres:
    image: postgres:15-alpine
    container_name: mpango_postgres
    environment:
      POSTGRES_USER: mpango
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: mpango
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - mpango_network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mpango"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: mpango_redis
    command: redis-server --requireapp ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - mpango_network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    image: windsurfmpangoerp-backend:latest
    container_name: mpango_backend
    environment:
      DATABASE_URL: postgresql+psycopg2://mpango:${POSTGRES_PASSWORD}@postgres/mpango
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
    volumes:
      - backend_logs:/app/logs
    networks:
      - mpango_network
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/ready"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  mpango_network:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  backend_logs:
EOF

    log_info "Created $COMPOSE_DIR/compose.yaml"
}

# Load environment from prod.env
load_env() {
    ENV_FILE="/opt/mpango/secrets/prod.env"
    if [ -f "$ENV_FILE" ]; then
        log_info "Loading environment from $ENV_FILE"
        set -a
        source "$ENV_FILE"
        set +a
    else
        log_warn "No prod.env found at $ENV_FILE"
    fi
}

# Main execution
main() {
    echo "This script will:"
    echo "  1. Stop and remove old containers (preserves volumes)"
    echo "  2. Create new compose.yaml without public port bindings"
    echo "  3. Start services with internal networking only"
    echo ""
    read -p "Continue? (y/N): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Aborted"
        exit 0
    fi

    cleanup_containers
    load_env
    create_compose

    log_info "Starting services..."
    cd /opt/mpango
    docker compose up -d

    log_info "Verifying no public ports..."
    SS_OUTPUT=$(sudo ss -lntp 2>/dev/null | grep -E ':5432|:6379' || true)
    if [ -z "$SS_OUTPUT" ]; then
        check_pass "Postgres and Redis are NOT publicly accessible"
    else
        log_warn "Ports still listening - review manually"
    fi

    log_info "Checking container connectivity..."
    sleep 5
    docker exec -it mpango_backend sh -lc 'nc -zv postgres 5432; nc -zv redis 6379' 2>/dev/null || \
        log_warn "Connectivity check failed - containers may need more time to start"

    log_info "Remediation complete!"
    log_info "Backend should be accessible on port 8000 (configure reverse proxy as needed)"
}

main "$@"
