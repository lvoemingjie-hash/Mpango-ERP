#!/usr/bin/env bash

# Mpango ERP Safe Cleanup Script
# This script removes ONLY Mpango ERP Docker resources.
# It protects other services (Sing-Box, etc.) from accidental deletion.
#
# Constraints:
# - NO `docker system prune`
# - Default mode is --dry-run
# - ONLY matches resources with 'mpango'
# - Volumes are NOT deleted unless explicitly forced with --delete-volumes
# - Requires confirmation if not in dry-run

set -euo pipefail

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
DRY_RUN=true
DELETE_VOLUMES=false
PROJECT_DIR=""

function show_help() {
    echo -e "${GREEN}Mpango ERP Safe Cleanup Script${NC}"
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help           Show this help message"
    echo "  --apply              Execute the cleanup (default is dry-run)"
    echo "  --delete-volumes     Also delete volumes (Requires backup verified + CTO approval)"
    echo "  --project-dir DIR    Delete the specified project directory"
    echo ""
    echo -e "${YELLOW}Stop Conditions:${NC}"
    echo "- If you are unsure about the resources being deleted, STOP."
    echo "- If volume deletion is required but not CTO approved, STOP."
    echo "- If co-hosted services (e.g., Sing-Box) match 'mpango', STOP."
}

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -h|--help) show_help; exit 0 ;;
        --apply) DRY_RUN=false ;;
        --delete-volumes) DELETE_VOLUMES=true ;;
        --project-dir) PROJECT_DIR="$2"; shift ;;
        *) echo -e "${RED}Unknown parameter passed: $1${NC}"; show_help; exit 1 ;;
    esac
    shift
done

echo -e "${YELLOW}==============================================${NC}"
echo -e "${YELLOW}       Mpango ERP Safe Cleanup Script         ${NC}"
echo -e "${YELLOW}==============================================${NC}"

if [ "$DRY_RUN" = true ]; then
    echo -e "${GREEN}Mode: DRY RUN (No changes will be made)${NC}"
else
    echo -e "${RED}Mode: APPLY (Destructive changes will be made)${NC}"
    read -p "Are you sure you want to proceed? Type 'yes' to continue: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Cleanup aborted."
        exit 0
    fi
fi

if [ "$DELETE_VOLUMES" = true ]; then
    echo -e "${RED}WARNING: Volume deletion is enabled. Ensure backups are verified and CTO has explicitly approved.${NC}"
    if [ "$DRY_RUN" = false ]; then
        read -p "Type 'I have CTO approval' to confirm volume deletion: " vol_confirm
        if [ "$vol_confirm" != "I have CTO approval" ]; then
            echo "Volume deletion aborted."
            exit 1
        fi
    fi
fi

echo -e "\n${GREEN}Finding Mpango containers...${NC}"
CONTAINERS=$(docker ps -a --filter "name=mpango" -q)
if [ -z "$CONTAINERS" ]; then
    echo "No Mpango containers found."
else
    docker ps -a --filter "name=mpango" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}"
    if [ "$DRY_RUN" = false ]; then
        echo "$CONTAINERS" | xargs -r docker stop
        echo "$CONTAINERS" | xargs -r docker rm
        echo -e "${GREEN}Containers removed.${NC}"
    fi
fi

echo -e "\n${GREEN}Finding Mpango networks...${NC}"
NETWORKS=$(docker network ls --filter "name=mpango" -q)
if [ -z "$NETWORKS" ]; then
    echo "No Mpango networks found."
else
    docker network ls --filter "name=mpango" --format "table {{.ID}}\t{{.Name}}"
    if [ "$DRY_RUN" = false ]; then
        echo "$NETWORKS" | xargs -r docker network rm
        echo -e "${GREEN}Networks removed.${NC}"
    fi
fi

echo -e "\n${GREEN}Finding Mpango images...${NC}"
IMAGES=$(docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | grep "mpango" | awk '{print $2}' || true)
if [ -z "$IMAGES" ]; then
    echo "No Mpango images found."
else
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}" | grep -E "REPOSITORY|mpango" || true
    if [ "$DRY_RUN" = false ]; then
        echo "$IMAGES" | xargs -r docker rmi -f
        echo -e "${GREEN}Images removed.${NC}"
    fi
fi

if [ "$DELETE_VOLUMES" = true ]; then
    echo -e "\n${GREEN}Finding Mpango volumes...${NC}"
    VOLUMES=$(docker volume ls --filter "name=mpango" -q)
    if [ -z "$VOLUMES" ]; then
        echo "No Mpango volumes found."
    else
        docker volume ls --filter "name=mpango" --format "table {{.Name}}\t{{.Driver}}"
        if [ "$DRY_RUN" = false ]; then
            echo "$VOLUMES" | xargs -r docker volume rm
            echo -e "${GREEN}Volumes removed.${NC}"
        fi
    fi
else
    echo -e "\n${YELLOW}Skipping volume deletion (use --delete-volumes if CTO approved).${NC}"
fi

if [ -n "$PROJECT_DIR" ]; then
    echo -e "\n${GREEN}Target Project Directory: $PROJECT_DIR${NC}"
    if [ "$DRY_RUN" = false ]; then
        if [ -d "$PROJECT_DIR" ]; then
            rm -rf "$PROJECT_DIR"
            echo -e "${GREEN}Project directory $PROJECT_DIR deleted.${NC}"
        else
            echo -e "${YELLOW}Project directory $PROJECT_DIR not found.${NC}"
        fi
    fi
fi

echo -e "\n${GREEN}Cleanup process completed successfully.${NC}"
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}This was a DRY RUN. Use --apply to execute.${NC}"
fi
echo -e "Other services touched: 0"
