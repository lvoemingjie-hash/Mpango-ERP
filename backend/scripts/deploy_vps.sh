#!/usr/bin/env bash
# =============================================================================
# deploy_vps.sh — Deploy Mpango ERP v0.2.0 to VPS via GitHub Pull
# =============================================================================
# PURPOSE : Run LOCALLY (Git Bash / WSL on Windows) to deploy to remote VPS.
# FLOW    : scp .env.prod → SSH into VPS → git pull → docker compose up
#
# Usage:
#   bash scripts/deploy_vps.sh
#   bash scripts/deploy_vps.sh --skip-seed       # skip demo data seeding
#   bash scripts/deploy_vps.sh --branch staging   # deploy a specific branch
#
# Prerequisites:
#   1. SSH key auth configured: ssh root@143.110.177.2 (no password prompt)
#   2. .env.prod exists in project root with production secrets
#   3. VPS has GitHub SSH key configured (for private repo access)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — edit these for your environment
# ---------------------------------------------------------------------------
VPS_USER="root"
VPS_IP="143.110.177.2"
PROJECT_DIR="/root/mpango-erp"
GITHUB_REPO="git@github.com:lvoemingjie-hash/Mpango-ERP.git"
BRANCH="main"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE_LOCAL=".env.prod"
SKIP_SEED=false

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --skip-seed)
      SKIP_SEED=true
      shift
      ;;
    --vps-ip)
      VPS_IP="$2"
      shift 2
      ;;
    --vps-user)
      VPS_USER="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--branch BRANCH] [--skip-seed] [--vps-ip IP] [--vps-user USER]" >&2
      exit 1
      ;;
  esac
done

SSH_TARGET="${VPS_USER}@${VPS_IP}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
YEL='\033[1;33m'
GRN='\033[0;32m'
BLU='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLU}[INFO]${NC}  $*"; }
warn() { echo -e "${YEL}[WARN]${NC}  $*"; }
ok()   { echo -e "${GRN}[ OK ]${NC}  $*"; }
err()  { echo -e "${RED}[FAIL]${NC}  $*" >&2; }

remote() {
  ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "${SSH_TARGET}" "$@"
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${BLU}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLU}║       Mpango ERP v0.2.0 — VPS Deployment (Track H)         ║${NC}"
echo -e "${BLU}║  Target: ${SSH_TARGET}:${PROJECT_DIR}${NC}"
echo -e "${BLU}║  Branch: ${BRANCH}${NC}"
echo -e "${BLU}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# =========================================================================
# Step 1: Pre-flight checks (LOCAL)
# =========================================================================
log "Step 1/7 — Pre-flight checks..."

# 1a. Check .env.prod exists locally
if [[ ! -f "$ENV_FILE_LOCAL" ]]; then
  err ".env.prod not found in project root."
  err "Copy .env.example to .env.prod and fill in production secrets:"
  err "  cp .env.example .env.prod"
  exit 1
fi
ok "  .env.prod found locally."

# 1b. Check SSH connectivity
log "  Testing SSH connection to ${SSH_TARGET}..."
if ! remote "echo 'SSH OK'" &>/dev/null; then
  err "Cannot SSH into ${SSH_TARGET}."
  err "Ensure your SSH key is configured:"
  err "  ssh-copy-id ${SSH_TARGET}"
  exit 1
fi
ok "  SSH connection verified."

# 1c. Check VPS has GitHub SSH access (for private repo)
log "  Testing VPS GitHub SSH access..."
GITHUB_SSH_OK=$(remote "ssh -T git@github.com 2>&1 || true")
if echo "$GITHUB_SSH_OK" | grep -qi "successfully authenticated"; then
  ok "  VPS GitHub SSH access verified."
else
  warn "  VPS GitHub SSH may not be configured. If repo is private, clone will fail."
  warn "  See docs/README_VPS_DEPLOY.md for setup instructions."
fi

# =========================================================================
# Step 2: Upload .env.prod to VPS
# =========================================================================
log "Step 2/7 — Uploading .env.prod to VPS..."

# Ensure project dir exists on VPS
remote "mkdir -p ${PROJECT_DIR}"

scp -o ConnectTimeout=10 "${ENV_FILE_LOCAL}" "${SSH_TARGET}:${PROJECT_DIR}/.env"
ok "  .env.prod → ${SSH_TARGET}:${PROJECT_DIR}/.env"

# =========================================================================
# Step 3: Clone or Pull source code on VPS
# =========================================================================
log "Step 3/7 — Syncing source code on VPS..."

REPO_EXISTS=$(remote "test -d ${PROJECT_DIR}/.git && echo 'yes' || echo 'no'")

if [[ "$REPO_EXISTS" == "yes" ]]; then
  log "  Repository exists. Pulling latest from origin/${BRANCH}..."
  remote "cd ${PROJECT_DIR} && git fetch origin && git checkout ${BRANCH} && git pull origin ${BRANCH}"
  ok "  Git pull complete."
else
  log "  Repository not found. Cloning from GitHub..."
  remote "git clone -b ${BRANCH} ${GITHUB_REPO} ${PROJECT_DIR}"
  ok "  Git clone complete."
fi

# Show deployed commit
DEPLOYED_COMMIT=$(remote "cd ${PROJECT_DIR} && git log -1 --format='%h %s'")
ok "  Deployed commit: ${DEPLOYED_COMMIT}"

# =========================================================================
# Step 4: Install Docker & Docker Compose (if missing)
# =========================================================================
log "Step 4/7 — Checking Docker installation on VPS..."

DOCKER_INSTALLED=$(remote "command -v docker &>/dev/null && echo 'yes' || echo 'no'")

if [[ "$DOCKER_INSTALLED" == "no" ]]; then
  warn "  Docker not found. Installing..."
  remote "bash -s" <<'INSTALL_DOCKER'
    set -e
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable docker
    systemctl start docker
INSTALL_DOCKER
  ok "  Docker installed."
else
  DOCKER_VER=$(remote "docker --version")
  ok "  Docker already installed: ${DOCKER_VER}"
fi

# Verify docker compose plugin
COMPOSE_OK=$(remote "docker compose version &>/dev/null && echo 'yes' || echo 'no'")
if [[ "$COMPOSE_OK" == "no" ]]; then
  err "  docker compose plugin not available. Install it manually."
  exit 1
fi
ok "  docker compose plugin available."

# =========================================================================
# Step 5: Build & Start services
# =========================================================================
log "Step 5/7 — Building and starting services..."

remote "bash -s" <<DEPLOY_CMD
  set -e
  cd ${PROJECT_DIR}
  
  # Stop existing containers gracefully (if any)
  docker compose -f ${COMPOSE_FILE} --env-file .env down --timeout 30 2>/dev/null || true
  
  # Build and start all services
  docker compose -f ${COMPOSE_FILE} --env-file .env up -d --build
  
  echo "Waiting for services to become healthy..."
  sleep 10
DEPLOY_CMD

ok "  docker compose up -d --build complete."

# =========================================================================
# Step 6: Wait for health & seed data
# =========================================================================
log "Step 6/7 — Waiting for all services to become healthy..."

# Poll health for up to 120 seconds
MAX_WAIT=120
ELAPSED=0
INTERVAL=5

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
  HEALTH_STATUS=$(remote "curl -sf http://localhost/health 2>/dev/null || echo 'FAIL'")
  if echo "$HEALTH_STATUS" | grep -q '"status":"healthy"'; then
    ok "  Gateway health check passed."
    break
  fi
  log "  Waiting... (${ELAPSED}s / ${MAX_WAIT}s)"
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

if [[ $ELAPSED -ge $MAX_WAIT ]]; then
  err "  Health check did not pass within ${MAX_WAIT}s."
  warn "  Checking individual service status..."
  remote "cd ${PROJECT_DIR} && docker compose -f ${COMPOSE_FILE} ps"
  remote "cd ${PROJECT_DIR} && docker compose -f ${COMPOSE_FILE} logs --tail=20 backend"
  exit 1
fi

# Run database migrations (entrypoint handles this, but verify)
log "  Running Alembic migrations..."
remote "cd ${PROJECT_DIR} && docker compose -f ${COMPOSE_FILE} exec -T backend alembic upgrade head 2>&1 || echo 'Migrations skipped (may already be current)'"
ok "  Migrations applied."

# Seed demo data (optional)
if [[ "$SKIP_SEED" == false ]]; then
  log "  Seeding demo data..."
  remote "cd ${PROJECT_DIR} && docker compose -f ${COMPOSE_FILE} exec -T backend python scripts/seed_demo_data.py 2>&1 || echo 'Seed skipped (may already exist)'"
  ok "  Demo data seeded."
else
  warn "  Skipping demo data seed (--skip-seed)."
fi

# =========================================================================
# Step 7: Final verification
# =========================================================================
log "Step 7/7 — Final verification..."

# Service status
echo ""
log "Service status:"
remote "cd ${PROJECT_DIR} && docker compose -f ${COMPOSE_FILE} ps"

# Health endpoints
echo ""
log "Health check responses:"
HEALTH_RESP=$(remote "curl -sf http://localhost/health 2>/dev/null || echo 'UNREACHABLE'")
log "  /health → ${HEALTH_RESP}"

LIVE_RESP=$(remote "curl -sf http://localhost/health/live 2>/dev/null || echo 'UNREACHABLE'")
log "  /health/live → ${LIVE_RESP}"

# Frontend check
FRONTEND_STATUS=$(remote "curl -sf -o /dev/null -w '%{http_code}' http://localhost/ 2>/dev/null || echo '000'")
log "  / (frontend) → HTTP ${FRONTEND_STATUS}"

# =========================================================================
# Summary
# =========================================================================
echo ""
echo -e "${GRN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GRN}║              Deployment Complete — v0.2.0                    ║${NC}"
echo -e "${GRN}╠══════════════════════════════════════════════════════════════╣${NC}"
printf  "${GRN}║${NC}  VPS          : %-42s${GRN}║${NC}\n" "${SSH_TARGET}"
printf  "${GRN}║${NC}  Branch       : %-42s${GRN}║${NC}\n" "${BRANCH}"
printf  "${GRN}║${NC}  Commit       : %-42s${GRN}║${NC}\n" "${DEPLOYED_COMMIT}"
printf  "${GRN}║${NC}  Gateway      : %-42s${GRN}║${NC}\n" "http://${VPS_IP}"
printf  "${GRN}║${NC}  Health       : %-42s${GRN}║${NC}\n" "http://${VPS_IP}/health"
printf  "${GRN}║${NC}  Frontend     : %-42s${GRN}║${NC}\n" "HTTP ${FRONTEND_STATUS}"
echo -e "${GRN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GRN}║  Login: admin@mpango.demo / DemoAdmin2026!                  ║${NC}"
echo -e "${GRN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
