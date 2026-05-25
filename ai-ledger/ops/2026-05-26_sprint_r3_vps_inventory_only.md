# Sprint R-3 VPS Inventory-Only Plan

**Date**: 2026-05-26
**Scope**: SSH read-only inventory of India VPS
**Branch**: ops/sprint-r2-vps-script-recovery-2026-05-25
**R-2T Final HEAD**: `1e77a19 docs(ops): fix stale HEAD ref in R-2T validation results`
**Status**: PLAN -- awaiting CTO separate approval to connect

## 1. Purpose
Gather a complete, read-only snapshot of the India VPS state to inform safe deployment planning. No changes will be made to the VPS during this sprint.

## 2. Scope
This sprint covers ONLY the following read-only commands, executed via SSH:

### 2.1 OS & System
- `cat /etc/os-release` -- OS version and architecture
- `uname -a` -- kernel info
- `df -h` -- disk usage
- `free -h` -- memory
- `uptime` -- system uptime

### 2.2 Docker & Compose
- `docker version` -- Docker daemon and client version
- `docker compose version` -- Compose plugin availability
- `docker info` -- daemon status, storage driver, security options

### 2.3 Running State
- `docker ps -a --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"` -- all containers
- `docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}"` -- all images
- `docker volume ls` -- all volumes
- `docker network ls --format "table {{.ID}}\t{{.Name}}\t{{.Driver}}"` -- all networks

### 2.4 Mpango-Specific State
- Check for existing Mpango project directory (e.g., `~/mpango-erp` or similar)
- If found: `git -C <dir> log -1 --oneline` -- current deployed commit
- If found: `git -C <dir> remote -v` -- remote URL
- Check for `.env.prod` or `.env` existence (DO NOT read or print contents)
- Check for `docker-compose.prod.yml` or similar compose files

### 2.5 Ports & Services
- `ss -tuln` or `netstat -tuln` -- listening ports
- Identify non-Mpango services (e.g., Sing-Box, nginx) that must not be disturbed

### 2.6 Backup Feasibility
- `df -h` -- available disk for pg_dump backup
- Check if `pg_dump` or `docker exec postgres pg_dump` is feasible
- Estimate backup size from `docker exec postgres psql -c 'SELECT pg_database_size(...)'` (if database exists)

## 3. Hard Restrictions
- **No cleanup**: No `docker stop`, `docker rm`, `docker rmi`, `docker volume rm`, `docker network rm`.
- **No deployment**: No `docker compose up`, no `git pull`, no `alembic`.
- **No destructive commands**: No `docker system prune`, no `rm -rf`.
- **No secrets**: Do not read, print, or commit `.env`, `.env.prod`, passwords, tokens, or SSH keys.
- **No configuration changes**: Do not modify any files on the VPS.
- **CTO approval required**: This plan MUST NOT be executed unless CTO separately and explicitly approves the SSH connection and inventory scope.

## 4. Stop Conditions
Operations MUST STOP and report to CTO if:
- SSH connection fails or prompts for password (key-based auth only).
- Any command returns unexpected destructive prompts.
- Non-Mpango services appear at risk.
- Disk space is critically low (less than 1GB free).
- Any sign of active data corruption or container crash loops.
- The VPS is not the expected India target (IP mismatch).

## 5. Deliverable
After inventory collection, this file will be updated with:
- Complete inventory results (inline, not "see below").
- Risk assessment based on current VPS state.
- Recommendations for R-4 (safe cleanup rehearsal) if applicable.
- Confirmation: no cleanup, no deployment, no secrets read.

## 6. CTO Approval Gate
- [ ] CTO approves SSH connection to India VPS
- [ ] CTO approves inventory command scope
- [ ] CTO confirms target IP/host

**This plan is not executable until all three checkboxes above are confirmed by CTO.**
