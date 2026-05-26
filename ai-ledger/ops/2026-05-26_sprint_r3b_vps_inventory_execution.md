# Sprint R-3B Read-Only VPS Inventory Execution Plan

**Date**: 2026-05-26
**Scope**: Read-only SSH inventory of candidate India VPS
**Branch**: ops/sprint-r2-vps-script-recovery-2026-05-25
**R-3A Probe HEAD**: `0ece7c9 docs(ops): add Sprint R-3A candidate VPS connectivity probe report`
**Status**: PLAN -- awaiting CTO/user approval before execution

## 1. Target

| Field | Value |
|-------|-------|
| User | root |
| Host | 143.110.177.2 |
| Hostname (observed) | ubuntu-s-1vcpu-1gb-blr1-01 |
| Region | blr1 / Bangalore |
| SSH auth | Key-based (BatchMode=yes) |

## 2. SSH Configuration

- **BatchMode=yes**: Disables password prompts; fails immediately if key auth unavailable.
- **ConnectTimeout=10**: 10-second connection timeout.
- **NO StrictHostKeyChecking=no**: Host key will be checked. If unknown, the command will fail and report the host key fingerprint for CTO manual review.
- Before execution, check local known_hosts: `ssh-keygen -F 143.110.177.2`

## 3. Exact Command List (Read-Only)

All commands will be executed as a single SSH invocation:

```
ssh -o BatchMode=yes -o ConnectTimeout=10 root@143.110.177.2 "COMMAND1; COMMAND2; ..."
```

Or as separate invocations grouped by category. Each command below is strictly read-only.

### 3.1 OS & System

```bash
cat /etc/os-release
uname -a
df -h
free -h
uptime
```

### 3.2 Docker & Compose

```bash
docker version
docker compose version
docker info
```

### 3.3 Running State

```bash
docker ps -a --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}"
docker volume ls
docker network ls --format "table {{.ID}}\t{{.Name}}\t{{.Driver}}"
```

### 3.4 Mpango-Specific State

```bash
ls -la ~/mpango-erp 2>/dev/null || echo "NO ~/mpango-erp directory"
git -C ~/mpango-erp log -1 --oneline 2>/dev/null || echo "NO git repo in ~/mpango-erp"
git -C ~/mpango-erp remote -v 2>/dev/null || echo "NO git remote"
test -f ~/mpango-erp/.env.prod && echo ".env.prod EXISTS (contents not read)" || echo ".env.prod NOT FOUND"
test -f ~/mpango-erp/.env && echo ".env EXISTS (contents not read)" || echo ".env NOT FOUND"
ls ~/mpango-erp/docker-compose.prod.yml 2>/dev/null || echo "NO docker-compose.prod.yml"
ls ~/mpango-erp/docker-compose.yml 2>/dev/null || echo "NO docker-compose.yml"
```

### 3.5 Ports & Services

```bash
ss -tuln
```

### 3.6 Backup Feasibility

```bash
df -h /var/lib/docker
docker exec mpango_postgres pg_dump --version 2>/dev/null || echo "NO pg_dump available or postgres not running"
docker exec mpango_postgres psql -U mpango -c "SELECT pg_size_pretty(pg_database_size('mpango_erp'));" 2>/dev/null || echo "CANNOT query database size"
```

## 4. Redaction Rules

- **git remote output**: If the remote URL contains embedded credentials or tokens, the report will redact credentials before writing. # pragma: allowlist secret
- **.env files**: Only existence will be tested. Contents will NEVER be read, printed, or committed.
- **docker info**: May contain paths and runtime details; all output is safe to record.

## 5. Hard Restrictions

- **No docker stop/rm/rmi/volume rm/network rm**
- **No docker compose up**
- **No git pull**
- **No alembic**
- **No file writes on VPS** (no `touch`, `echo >`, `tee`, `cp`, `mv`, etc.)
- **No secrets reading** (no `cat .env`, `env`, `printenv`, etc.)
- **No StrictHostKeyChecking=no** -- host key will be verified

## 6. Stop Conditions

Operations MUST STOP and report to CTO if:
- SSH fails (connection refused, timeout, auth failure).
- Host key is unknown and BatchMode prevents interactive acceptance.
- Any command output is unexpected or suspicious.
- Non-Mpango services appear at risk.
- Disk space is critically low (less than 1GB free on any critical mount).
- Container crash loops detected.
- The host identity does not match `ubuntu-s-1vcpu-1gb-blr1-01`.

## 7. Deliverable

After execution, this file will be updated with:
- Complete inventory results (inline).
- Host key status (known/unknown).
- Risk assessment.
- Recommendations for next steps.
- Confirmation: no cleanup, no deployment, no secrets read, no file writes.

## 8. CTO Approval Gate

- [ ] CTO/user approves SSH connection for full inventory
- [ ] CTO/user confirms target host `143.110.177.2`
- [ ] CTO/user approves command list scope

**This plan is not executable until all three checkboxes above are confirmed by CTO/user.**
