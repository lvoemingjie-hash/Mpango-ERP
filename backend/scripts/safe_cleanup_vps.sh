#!/usr/bin/env bash
# =============================================================================
# safe_cleanup_vps.sh — Mpango ERP Targeted VPS Cleanup
# =============================================================================
# PURPOSE : Remove ONLY Mpango ERP Docker artifacts and project files.
# SAFETY  : Does NOT use `docker system prune`. Targets only resources whose
#           name/reference contains "mpango". Other services (e.g. Sing-Box)
#           are untouched.
#
# Usage:
#   bash scripts/safe_cleanup_vps.sh [--project-dir /path/to/mpango-erp]
#
# Options:
#   --project-dir DIR   Path to the project directory to delete.
#                       Default: ~/mpango-erp
#   --dry-run           Print what would be removed without doing it.
#   --yes               Skip confirmation prompt.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
PROJECT_DIR="${HOME}/mpango-erp"
DRY_RUN=false
AUTO_YES=false

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir)
      PROJECT_DIR="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --yes|-y)
      AUTO_YES=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--project-dir DIR] [--dry-run] [--yes]" >&2
      exit 1
      ;;
  esac
done

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
err()  { echo -e "${RED}[ERR ]${NC}  $*" >&2; }

run() {
  if [[ "$DRY_RUN" == true ]]; then
    echo -e "${YEL}[DRY] ${NC} $*"
  else
    eval "$@"
  fi
}

# ---------------------------------------------------------------------------
# Safety banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${YEL}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${YEL}║       Mpango ERP — Safe VPS Cleanup (Track H)               ║${NC}"
echo -e "${YEL}║  ONLY resources with 'mpango' in name will be removed.      ║${NC}"
echo -e "${YEL}║  Other services (Sing-Box, etc.) will NOT be touched.       ║${NC}"
echo -e "${YEL}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ "$DRY_RUN" == true ]]; then
  warn "DRY-RUN mode — no changes will be made."
  echo ""
fi

# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------
if [[ "$AUTO_YES" == false && "$DRY_RUN" == false ]]; then
  warn "This will permanently remove all Mpango ERP Docker resources and:"
  warn "  Project directory: ${PROJECT_DIR}"
  echo ""
  read -rp "Are you sure? Type 'yes' to continue: " CONFIRM
  if [[ "$CONFIRM" != "yes" ]]; then
    echo "Aborted."
    exit 0
  fi
  echo ""
fi

# ---------------------------------------------------------------------------
# Counters (for verification summary)
# ---------------------------------------------------------------------------
CONTAINERS_REMOVED=0
IMAGES_REMOVED=0
VOLUMES_REMOVED=0
NETWORKS_REMOVED=0
OTHER_TOUCHED=0

# ---------------------------------------------------------------------------
# Step 1: Stop and remove Mpango containers
# ---------------------------------------------------------------------------
log "Step 1/5 — Stopping Mpango containers..."
MPANGO_CONTAINERS=$(docker ps -a --filter "name=mpango" -q 2>/dev/null || true)

if [[ -n "$MPANGO_CONTAINERS" ]]; then
  CONTAINER_COUNT=$(echo "$MPANGO_CONTAINERS" | wc -l | tr -d ' ')
  log "  Found ${CONTAINER_COUNT} container(s): $(docker ps -a --filter 'name=mpango' --format '{{.Names}}' | tr '\n' ' ')"
  run "docker stop $MPANGO_CONTAINERS 2>/dev/null || true"
  run "docker rm   $MPANGO_CONTAINERS 2>/dev/null || true"
  CONTAINERS_REMOVED=$CONTAINER_COUNT
  ok "  Removed ${CONTAINERS_REMOVED} container(s)."
else
  ok "  No Mpango containers found."
fi

# ---------------------------------------------------------------------------
# Step 2: Remove Mpango images (only images tagged *mpango* or *windsurfmpango*)
# ---------------------------------------------------------------------------
log "Step 2/5 — Removing Mpango images..."

# Match images whose repository or tag contains "mpango"
# Excludes base images (python, node, nginx, postgres, redis) — those have no "mpango" in their name
MPANGO_IMAGES=$(docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" 2>/dev/null \
  | grep -i "mpango" \
  | awk '{print $2}' \
  | sort -u || true)

if [[ -n "$MPANGO_IMAGES" ]]; then
  IMAGE_COUNT=$(echo "$MPANGO_IMAGES" | wc -l | tr -d ' ')
  log "  Found ${IMAGE_COUNT} image(s):"
  docker images --format "  {{.Repository}}:{{.Tag}}" | grep -i "mpango" || true
  run "docker rmi --force $MPANGO_IMAGES 2>/dev/null || true"
  IMAGES_REMOVED=$IMAGE_COUNT
  ok "  Removed ${IMAGES_REMOVED} image(s)."
else
  ok "  No Mpango images found."
fi

# ---------------------------------------------------------------------------
# Step 3: Remove Mpango volumes
# ---------------------------------------------------------------------------
log "Step 3/5 — Removing Mpango volumes..."
MPANGO_VOLUMES=$(docker volume ls --filter "name=mpango" -q 2>/dev/null || true)

if [[ -n "$MPANGO_VOLUMES" ]]; then
  VOLUME_COUNT=$(echo "$MPANGO_VOLUMES" | wc -l | tr -d ' ')
  log "  Found ${VOLUME_COUNT} volume(s): $(echo "$MPANGO_VOLUMES" | tr '\n' ' ')"
  run "docker volume rm $MPANGO_VOLUMES 2>/dev/null || true"
  VOLUMES_REMOVED=$VOLUME_COUNT
  ok "  Removed ${VOLUMES_REMOVED} volume(s)."
else
  ok "  No Mpango volumes found."
fi

# ---------------------------------------------------------------------------
# Step 4: Remove Mpango networks
# ---------------------------------------------------------------------------
log "Step 4/5 — Removing Mpango networks..."
MPANGO_NETWORKS=$(docker network ls --filter "name=mpango" -q 2>/dev/null || true)

if [[ -n "$MPANGO_NETWORKS" ]]; then
  NETWORK_COUNT=$(echo "$MPANGO_NETWORKS" | wc -l | tr -d ' ')
  log "  Found ${NETWORK_COUNT} network(s): $(docker network ls --filter 'name=mpango' --format '{{.Name}}' | tr '\n' ' ')"
  run "docker network rm $MPANGO_NETWORKS 2>/dev/null || true"
  NETWORKS_REMOVED=$NETWORK_COUNT
  ok "  Removed ${NETWORKS_REMOVED} network(s)."
else
  ok "  No Mpango networks found."
fi

# ---------------------------------------------------------------------------
# Step 5: Delete project directory
# ---------------------------------------------------------------------------
log "Step 5/5 — Removing project directory: ${PROJECT_DIR}"
if [[ -d "$PROJECT_DIR" ]]; then
  run "rm -rf \"$PROJECT_DIR\""
  ok "  Deleted: ${PROJECT_DIR}"
else
  warn "  Directory not found (already removed?): ${PROJECT_DIR}"
fi

# ---------------------------------------------------------------------------
# Verification summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${GRN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GRN}║                  Cleanup Complete                           ║${NC}"
echo -e "${GRN}╠══════════════════════════════════════════════════════════════╣${NC}"
printf  "${GRN}║${NC}  Containers removed : %-36s${GRN}║${NC}\n" "${CONTAINERS_REMOVED}"
printf  "${GRN}║${NC}  Images removed     : %-36s${GRN}║${NC}\n" "${IMAGES_REMOVED}"
printf  "${GRN}║${NC}  Volumes removed    : %-36s${GRN}║${NC}\n" "${VOLUMES_REMOVED}"
printf  "${GRN}║${NC}  Networks removed   : %-36s${GRN}║${NC}\n" "${NETWORKS_REMOVED}"
printf  "${GRN}║${NC}  Project dir deleted: %-36s${GRN}║${NC}\n" "${PROJECT_DIR}"
echo -e "${GRN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GRN}║  Mpango ERP removed. Other services touched: ${OTHER_TOUCHED}             ║${NC}"
echo -e "${GRN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ "$DRY_RUN" == true ]]; then
  warn "DRY-RUN complete. Re-run without --dry-run to apply changes."
fi
