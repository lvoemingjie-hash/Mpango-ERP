#!/usr/bin/env bash

# Mpango ERP Deployment Script
# This script automates the deployment of Mpango ERP.
#
# Constraints:
# - No secrets, IPs, passwords, or tokens are hardcoded.
# - Checks for .env.prod existence but NEVER prints its contents.
# - Alembic must upgrade head normally (no stamping).
# - DRY_RUN is true by default.

set -euo pipefail

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
DRY_RUN=true
BRANCH="product-dev-recovered"

function show_help() {
    echo -e "${GREEN}Mpango ERP Deployment Script${NC}"
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help           Show this help message"
    echo "  --apply              Execute the actual deployment (requires interactive confirmation)"
    echo "  --branch BRANCH      Specify the branch to deploy (default: product-dev-recovered)"
    echo "  --dry-run            Simulate the deployment process (Default)"
    echo ""
    echo -e "${YELLOW}Stop Conditions:${NC}"
    echo "- If .env.prod is missing (in apply mode), STOP."
    echo "- If git pull fails, STOP."
    echo "- If docker compose build/up fails, STOP."
    echo "- If Alembic migration fails, STOP."
}

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -h|--help) show_help; exit 0 ;;
        --apply) DRY_RUN=false ;;
        --dry-run) DRY_RUN=true ;;
        --branch) BRANCH="$2"; shift ;;
        *) echo -e "${RED}Unknown parameter passed: $1${NC}"; show_help; exit 1 ;;
    esac
    shift
done

echo -e "${YELLOW}==============================================${NC}"
echo -e "${YELLOW}         Mpango ERP Deployment Script         ${NC}"
echo -e "${YELLOW}==============================================${NC}"

if [ "$DRY_RUN" = true ]; then
    echo -e "${GREEN}Mode: DRY RUN (Simulation only)${NC}"
else
    echo -e "${RED}Mode: APPLY (Deployment will be executed)${NC}"
    read -p "Are you sure you want to proceed? Type 'deploy mpango' to continue: " confirm
    if [ "$confirm" != "deploy mpango" ]; then
        echo "Deployment aborted."
        exit 0
    fi
fi

echo -e "\n${GREEN}Step 1: Checking .env.prod...${NC}"
if [ ! -f ".env.prod" ]; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}Warning: .env.prod not found. (It would be required in apply mode)${NC}"
    else
        echo -e "${RED}Error: .env.prod not found in the current directory.${NC}"
        echo "Deployment aborted."
        exit 1
    fi
else
    echo "File .env.prod exists. (Contents hidden for security)"
fi

echo -e "\n${GREEN}Step 2: Updating codebase from branch '${BRANCH}'...${NC}"
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] git fetch origin ${BRANCH}"
    echo "[DRY RUN] git checkout ${BRANCH}"
    echo "[DRY RUN] git pull origin ${BRANCH}"
else
    git fetch origin "${BRANCH}"
    git checkout "${BRANCH}"
    git pull origin "${BRANCH}"
fi

echo -e "\n${GREEN}Step 3: Deploying with Docker Compose...${NC}"
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] docker compose -f docker-compose.prod.yml up -d --build"
else
    docker compose -f docker-compose.prod.yml up -d --build
fi

echo -e "\n${GREEN}Step 4: Running Alembic Migrations...${NC}"
echo -e "${YELLOW}Note: Migrations must run normally (upgrade head). Bypassing is prohibited.${NC}"
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] docker compose -f docker-compose.prod.yml exec backend alembic upgrade head"
else
    docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
fi

echo -e "\n${GREEN}Deployment process completed successfully.${NC}"
if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}This was a DRY RUN. No actual deployment occurred. Use --apply to execute.${NC}"
fi
