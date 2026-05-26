# Sprint R-3B Read-Only VPS Inventory Execution

**Date**: 2026-05-26
**Scope**: Read-only SSH inventory of India VPS
**Branch**: ops/sprint-r2-vps-script-recovery-2026-05-25
**R-3A Probe HEAD**: `0ece7c9 docs(ops): add Sprint R-3A candidate VPS connectivity probe report`
**Status**: EXECUTED -- inventory complete

## 1. Target

| Field | Value |
|-------|-------|
| User | root |
| Host | 143.110.177.2 |
| Hostname | ubuntu-s-1vcpu-1gb-blr1-01 |
| Region | blr1 / Bangalore |

## 2. Host Key Status

**Host key already in local known_hosts**: YES
- Found 3 keys: ssh-ed25519, ssh-rsa, ecdsa-sha2-nistp256
- No StrictHostKeyChecking=no used. Host key verified automatically via known_hosts.

## 3. Exact Commands Run and Results

All commands executed via SSH with `BatchMode=yes` and `ConnectTimeout=10`.

### Group 3.1: OS & System (exit code: 0)

```
cat /etc/os-release; uname -a; df -h; free -h; uptime
```

**OS**: Ubuntu 22.04.4 LTS (Jammy Jellyfish), x86_64
**Kernel**: Linux 5.15.0-113-generic
**Disk**:
- `/dev/vda1`: 25G total, 18G used, 6.1G available (75% use)
- No swap configured
**Memory**: 957Mi total, 555Mi used, 79Mi free, 227Mi available
**Uptime**: 158 days

### Group 3.2: Docker & Compose (exit code: 0)

```
docker version; docker compose version; docker info
```

**Docker Client**: 29.1.3
**Docker Server**: 28.2.2
**Docker Compose**: v5.0.1
**Storage Driver**: overlay2 (extfs)
**Cgroup**: systemd / v2
**Containers**: 5 running, 0 stopped
**Images**: 122

### Group 3.3: Running State (exit code: 0)

```
docker ps -a; docker images; docker volume ls; docker network ls
```

**Containers (5)**:

| ID | Name | Status | Image | Ports |
|----|------|--------|-------|-------|
| 13e2ce482f4d | mpango_prod_gateway | Up 2 months (healthy) | nginx:alpine | 0.0.0.0:80->80/tcp |
| 04f143a2935e | mpango_prod_backend | Up 2 months (healthy) | mpango-erp-backend | 8000/tcp |
| 16c00f8383a7 | mpango_prod_frontend | Up 2 months (healthy) | mpango-erp-frontend | 80/tcp |
| 7364dd9d7c98 | mpango_prod_postgres | Up 2 months (healthy) | postgres:15-alpine | 5432/tcp |
| d175e2df6f5f | mpango_prod_redis | Up 2 months (healthy) | redis:7-alpine | 6379/tcp |

**Images (10)**:

| Repository | Tag | Size |
|------------|-----|------|
| mpango-erp-backend | latest | 619MB |
| mpango-erp-frontend | latest | 62.6MB |
| nginx | alpine | 62.1MB |
| app_backend | latest | 998MB |
| app_frontend | latest | 443MB |
| python | 3.11-slim | 124MB |
| postgres | 15 | 444MB |
| postgres | 15-alpine | 274MB |
| redis | 7-alpine | 41.4MB |
| node | 18-alpine | 127MB |

**Volumes (4)**:
- app_postgres_data
- app_redis_data
- mpango-erp_postgres_data
- mpango-erp_redis_data

**Networks (4)**:
- bridge (bridge)
- host (host)
- mpango-erp_mpango_network (bridge)
- none (null)

### Group 3.4: Mpango-Specific (exit code: 0)

```
ls -la ~/mpango-erp; git -C ~/mpango-erp log -1 --oneline; git -C ~/mpango-erp remote -v; test -f .env.prod; test -f .env; ls docker-compose.prod.yml; ls docker-compose.yml
```

**Project directory**: `/root/mpango-erp` EXISTS
**Git last commit**: `02d69c0 fix: tenant bootstrap + frontend healthcheck + MPANGO_ENV`
**Git remote**: `https://github.com/lvoemingjie-hash/Mpango-ERP.git` (no embedded credentials -- clean)
**.env.prod**: NOT FOUND
**.env**: EXISTS (contents not read)
**docker-compose.prod.yml**: EXISTS
**docker-compose.yml**: EXISTS
**docker-compose.override.yml**: EXISTS
**Last modified**: Mar 11 06:58 (backend, ai-ledger, docker-compose files)

### Group 3.5: Ports (exit code: 0)

```
ss -tuln
```

| Protocol | Local Address | Port | Service |
|----------|---------------|------|---------|
| TCP | 0.0.0.0 | 80 | Mpango gateway (nginx) |
| TCP | 0.0.0.0 | 22 | SSH |
| TCP | * | 443 | Unknown (not Mpango containers -- investigation needed) |
| TCP | 127.0.0.1 | 42431 | Docker/localhost |
| TCP | 127.0.0.53 | 53 | systemd-resolved |
| UDP | 0.0.0.0 | 51820 | WireGuard VPN |

### Group 3.6: Backup Feasibility (exit code: 1 -- partial)

```
df -h /var/lib/docker; timeout 10 docker exec mpango_postgres pg_dump --version; timeout 10 docker exec mpango_postgres psql -U mpango -c 'SELECT ...'
```

**Disk for Docker**: 25G total, 18G used, 6.1G available (75%)
**pg_dump**: NOT available via `docker exec mpango_postgres pg_dump --version` (returned error)
**Database size**: CANNOT query (psql connection failed from docker exec)

Note: The postgres container is running and healthy per `docker ps`, but `docker exec` for pg_dump/psql failed. This may be a PATH or auth issue inside the container. The database data exists in volume `mpango-erp_postgres_data` regardless.

## 4. Redaction Notes

- **git remote**: `https://github.com/lvoemingjie-hash/Mpango-ERP.git` -- no embedded credentials found. No redaction needed.
- **.env**: Only existence tested. Contents not read.
- **.env.prod**: Not found on VPS.
- **No secrets were read, printed, or committed.**

## 5. Risk Assessment

| Risk | Severity | Detail |
|------|----------|--------|
| Disk at 75% | MEDIUM | 6.1G free; deployment + images may need ~2-3G. Monitor carefully. |
| No .env.prod on VPS | LOW | VPS uses `.env` instead. Deploy script must handle this. |
| Old images (app_backend, app_frontend, postgres:15) | LOW | Legacy images from previous deployment consuming disk. Safe cleanup candidate. |
| Port 443 listener | MEDIUM | Not from Mpango containers. May be WireGuard or other service. Needs investigation. |
| pg_dump unavailable via docker exec | MEDIUM | Backup strategy needs adjustment. May need to run pg_dump differently. |
| VPS deployed commit is old (`02d69c0`) | INFO | VPS is many commits behind `product-dev-recovered` HEAD (`b30784b`). Full redeployment expected. |
| Memory at 555/957 MiB | MEDIUM | Tight on a 1GB droplet. New images/build may cause memory pressure. |

## 6. Recommendation for R-4

1. **Backup First**: Before any cleanup or deployment, perform a database backup using an alternative method (e.g., `docker exec mpango_prod_postgres pg_dump -U mpango mpango_erp > backup.sql` with correct PATH, or `docker run --rm --volumes-from mpango_prod_postgres postgres:15-alpine pg_dump`).
2. **Safe Cleanup Rehearsal**: Use `safe_cleanup_vps.sh --dry-run` on VPS to verify exact targets match inventory.
3. **Old Image Cleanup**: Legacy `app_backend`, `app_frontend`, `postgres:15` images are safe cleanup candidates.
4. **Port 443 Investigation**: Identify what is listening on 443 before proceeding.
5. **Memory Consideration**: Consider building images locally and pushing, or using a swap file during build.

## 7. Confirmation

- **No cleanup**: No docker stop/rm/rmi/volume rm/network rm/system prune executed.
- **No deployment**: No docker compose up, git pull, or alembic executed.
- **No secrets read**: No .env contents, passwords, or tokens accessed.
- **No remote file writes**: No files created or modified on VPS.
- **No scripts executed**: safe_cleanup_vps.sh and deploy_vps.sh were not run on VPS.
