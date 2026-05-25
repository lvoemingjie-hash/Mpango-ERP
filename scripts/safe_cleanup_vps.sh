#!/usr/bin/env bash

# Mpango ERP Safe Cleanup Script
# This script removes ONLY Mpango ERP Docker resources.
# It protects other services (Sing-Box, etc.) from accidental deletion.
#
# Constraints:
# - NO file system deletion (no rm -rf)
# - NO `docker system prune`
# - Default mode is --dry-run
# - ONLY matches resources via Docker Compose label 'com.docker.compose.project=mpango'
#   or name prefix '^mpango[-_]' as fallback
# - Images: label match ONLY (no name fallback) to protect shared base images
# - Volumes are NOT deleted unless explicitly forced with --delete-volumes
# - Requires confirmation AFTER showing exact targets

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

DRY_RUN=true
DELETE_VOLUMES=false

function show_help() {
    echo -e "${GREEN}Mpango ERP Safe Cleanup Script${NC}"
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help           Show this help message"
    echo "  --apply              Execute the cleanup (default is dry-run)"
    echo "  --delete-volumes     Also delete volumes (Requires backup verified + CTO approval)"
    echo ""
    echo -e "${YELLOW}Prerequisites before --apply:${NC}"
    echo "- VPS inventory snapshot completed"
    echo "- Database backup verified off-host"
    echo "- CTO explicit approval obtained"
    echo ""
    echo -e "${YELLOW}Stop Conditions:${NC}"
    echo "- If you are unsure about the resources being deleted, STOP."
    echo "- If volume deletion is required but not CTO approved, STOP."
    echo "- If co-hosted services (e.g., Sing-Box) appear in targets, STOP."
}

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -h|--help) show_help; exit 0 ;;
        --apply) DRY_RUN=false ;;
        --delete-volumes) DELETE_VOLUMES=true ;;
        *) echo -e "${RED}Unknown parameter passed: $1${NC}"; show_help; exit 1 ;;
    esac
    shift
done

echo -e "${YELLOW}==============================================${NC}"
echo -e "${YELLOW}       Mpango ERP Safe Cleanup Script         ${NC}"
echo -e "${YELLOW}==============================================${NC}"

if [ "$DRY_RUN" = true ]; then
    echo -e "${GREEN}Mode: DRY RUN (No changes will be made)${NC}"
fi

# ---------- DISCOVERY PHASE ----------
# All resources are discovered FIRST, then exact targets are displayed,
# and ONLY THEN does the user confirm (if --apply).

echo -e "\n${GREEN}=== DISCOVERY PHASE ===${NC}"

# --- Containers ---
echo -e "\n${GREEN}Finding Mpango containers...${NC}"
CONTAINER_IDS_LABEL=$(docker ps -a --filter "label=com.docker.compose.project=mpango" -q 2>/dev/null || true)
CONTAINER_IDS_NAME=$(docker ps -a --filter "name=^mpango[-_]" -q 2>/dev/null || true)
CONTAINER_IDS=$(echo -e "${CONTAINER_IDS_LABEL}\n${CONTAINER_IDS_NAME}" | sort -u | grep -v '^$' || true)

if [ -z "$CONTAINER_IDS" ]; then
    echo "  No Mpango containers found."
    CONTAINER_COUNT=0
else
    CONTAINER_COUNT=$(echo "$CONTAINER_IDS" | wc -l)
    echo "  Containers found: ${CONTAINER_COUNT}"
    echo ""
    for cid in $CONTAINER_IDS; do
        c_name=$(docker inspect --format '{{.Name}}' "$cid" 2>/dev/null | sed 's/^\///' || echo "unknown")
        c_status=$(docker inspect --format '{{.State.Status}}' "$cid" 2>/dev/null || echo "unknown")
        c_label="label"
        if echo "$CONTAINER_IDS_NAME" | grep -q "$cid" 2>/dev/null; then
            if ! echo "$CONTAINER_IDS_LABEL" | grep -q "$cid" 2>/dev/null; then
                c_label="name-fallback"
            fi
        fi
        echo "  ID: ${cid}  Name: ${c_name}  Status: ${c_status}  Matched: ${c_label}"
    done
fi

# --- Networks ---
echo -e "\n${GREEN}Finding Mpango networks...${NC}"
NETWORK_IDS_LABEL=$(docker network ls --filter "label=com.docker.compose.project=mpango" -q 2>/dev/null || true)
NETWORK_IDS_NAME=$(docker network ls --filter "name=^mpango[-_]" -q 2>/dev/null || true)
NETWORK_IDS=$(echo -e "${NETWORK_IDS_LABEL}\n${NETWORK_IDS_NAME}" | sort -u | grep -v '^$' || true)

if [ -z "$NETWORK_IDS" ]; then
    echo "  No Mpango networks found."
    NETWORK_COUNT=0
else
    NETWORK_COUNT=$(echo "$NETWORK_IDS" | wc -l)
    echo "  Networks found: ${NETWORK_COUNT}"
    echo ""
    for nid in $NETWORK_IDS; do
        n_name=$(docker network inspect --format '{{.Name}}' "$nid" 2>/dev/null || echo "unknown")
        n_label="label"
        if echo "$NETWORK_IDS_NAME" | grep -q "$nid" 2>/dev/null; then
            if ! echo "$NETWORK_IDS_LABEL" | grep -q "$nid" 2>/dev/null; then
                n_label="name-fallback"
            fi
        fi
        echo "  ID: ${nid}  Name: ${n_name}  Matched: ${n_label}"
    done
fi

# --- Images (label ONLY, no name fallback) ---
echo -e "\n${GREEN}Finding Mpango images (label match only)...${NC}"
IMAGE_IDS=$(docker images --filter "label=com.docker.compose.project=mpango" -q 2>/dev/null || true)

if [ -z "$IMAGE_IDS" ]; then
    echo "  No Mpango images found via label."
    IMAGE_COUNT=0
else
    IMAGE_COUNT=$(echo "$IMAGE_IDS" | wc -l)
    echo "  Images found: ${IMAGE_COUNT}"
    echo ""
    for iid in $IMAGE_IDS; do
        i_repo=$(docker inspect --format '{{index .RepoTags 0}}' "$iid" 2>/dev/null || echo "unknown")
        echo "  Repository:Tag: ${i_repo}  ID: ${iid}  Matched: label"
    done
fi

# --- Volumes ---
if [ "$DELETE_VOLUMES" = true ]; then
    echo -e "\n${GREEN}Finding Mpango volumes...${NC}"
    VOLUME_NAMES_LABEL=$(docker volume ls --filter "label=com.docker.compose.project=mpango" --format '{{.Name}}' 2>/dev/null || true)
    VOLUME_NAMES_NAME=$(docker volume ls --filter "name=^mpango[-_]" --format '{{.Name}}' 2>/dev/null || true)
    VOLUME_NAMES=$(echo -e "${VOLUME_NAMES_LABEL}\n${VOLUME_NAMES_NAME}" | sort -u | grep -v '^$' || true)

    if [ -z "$VOLUME_NAMES" ]; then
        echo "  No Mpango volumes found."
        VOLUME_COUNT=0
    else
        VOLUME_COUNT=$(echo "$VOLUME_NAMES" | wc -l)
        echo "  Volumes found: ${VOLUME_COUNT}"
        echo ""
        for vname in $VOLUME_NAMES; do
            v_driver=$(docker volume inspect --format '{{.Driver}}' "$vname" 2>/dev/null || echo "unknown")
            v_label="label"
            if echo "$VOLUME_NAMES_NAME" | grep -q "$vname" 2>/dev/null; then
                if ! echo "$VOLUME_NAMES_LABEL" | grep -q "$vname" 2>/dev/null; then
                    v_label="name-fallback"
                fi
            fi
            echo "  Name: ${vname}  Driver: ${v_driver}  Matched: ${v_label}"
        done
    fi
else
    VOLUME_COUNT=0
    echo -e "\n${YELLOW}Skipping volume discovery (use --delete-volumes if CTO approved).${NC}"
fi

# ---------- CONFIRMATION PHASE (only when --apply) ----------

if [ "$DRY_RUN" = false ]; then
    echo -e "\n${RED}==============================================${NC}"
    echo -e "${RED}         APPLY MODE — EXACT TARGETS          ${NC}"
    echo -e "${RED}==============================================${NC}"
    echo ""
    echo "  Containers to stop & remove: ${CONTAINER_COUNT}"
    echo "  Networks to remove:          ${NETWORK_COUNT}"
    echo "  Images to remove:            ${IMAGE_COUNT}"
    if [ "$DELETE_VOLUMES" = true ]; then
        echo "  Volumes to remove:           ${VOLUME_COUNT}"
    else
        echo "  Volumes to remove:           0 (skipped)"
    fi
    echo ""

    if [ "$DELETE_VOLUMES" = true ]; then
        echo -e "${RED}WARNING: Volume deletion is enabled.${NC}"
        read -p "Type 'I have CTO approval' to confirm volume deletion: " vol_confirm
        if [ "$vol_confirm" != "I have CTO approval" ]; then
            echo "Volume deletion aborted."
            exit 1
        fi
    fi

    read -p "Review the exact targets above. Type 'yes' to proceed with cleanup: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Cleanup aborted."
        exit 0
    fi

    # ---------- EXECUTION PHASE ----------

    if [ -n "$CONTAINER_IDS" ]; then
        echo -e "\n${GREEN}Stopping and removing containers...${NC}"
        echo "$CONTAINER_IDS" | xargs -r docker stop
        echo "$CONTAINER_IDS" | xargs -r docker rm
        echo -e "${GREEN}Containers removed.${NC}"
    fi

    if [ -n "$NETWORK_IDS" ]; then
        echo -e "\n${GREEN}Removing networks...${NC}"
        echo "$NETWORK_IDS" | xargs -r docker network rm
        echo -e "${GREEN}Networks removed.${NC}"
    fi

    if [ -n "$IMAGE_IDS" ]; then
        echo -e "\n${GREEN}Removing images...${NC}"
        echo "$IMAGE_IDS" | xargs -r docker rmi -f
        echo -e "${GREEN}Images removed.${NC}"
    fi

    if [ "$DELETE_VOLUMES" = true ] && [ -n "$VOLUME_NAMES" ]; then
        echo -e "\n${GREEN}Removing volumes...${NC}"
        echo "$VOLUME_NAMES" | xargs -r docker volume rm
        echo -e "${GREEN}Volumes removed.${NC}"
    fi
fi

# ---------- SUMMARY ----------

echo -e "\n${GREEN}==============================================${NC}"
echo -e "${GREEN}       Cleanup Summary                        ${NC}"
echo -e "${GREEN}==============================================${NC}"
echo "  Containers: ${CONTAINER_COUNT}"
echo "  Networks:   ${NETWORK_COUNT}"
echo "  Images:     ${IMAGE_COUNT}"
if [ "$DELETE_VOLUMES" = true ]; then
    echo "  Volumes:    ${VOLUME_COUNT}"
else
    echo "  Volumes:    0 (skipped)"
fi
echo ""
echo "Other services touched: 0"

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}This was a DRY RUN. Use --apply to execute.${NC}"
fi
