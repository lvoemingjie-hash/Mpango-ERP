# Track H — VPS Safe Cleanup Report

**Date**: 2026-02-18 23:33 (UTC+08:00)  
**Engineer**: Senior DevOps Engineer  
**Scope**: VPS Safe Cleanup — remove ONLY Mpango ERP artifacts  
**Safety Mandate**: Protect other services (Sing-Box, etc.) from accidental deletion

---

## Objective

Create a **targeted cleanup script** that removes ONLY Mpango ERP Docker resources without using `docker system prune`, ensuring co-hosted services (Sing-Box, etc.) remain untouched.

---

## Safety Constraints (Track H Mandate)

| Constraint | Implementation |
|------------|----------------|
| **NO `docker system prune`** | Script uses targeted filters only |
| **Container filter** | `docker ps -a --filter "name=mpango"` |
| **Image filter** | `docker images` + `grep mpango` (excludes base images) |
| **Volume filter** | `docker volume ls --filter "name=mpango"` |
| **Network filter** | `docker network ls --filter "name=mpango"` |
| **Verification** | Prints "Other services touched: 0" on success |

---

## Script Features

### `scripts/safe_cleanup_vps.sh`

**Capabilities:**
1. **Stop & remove containers** — filters by `name=mpango`
2. **Remove images** — only images with `mpango` in repository/tag (python/node/nginx/postgres/redis base images untouched)
3. **Remove volumes** — filters by `name=mpango`
4. **Remove networks** — filters by `name=mpango`
5. **Delete project directory** — default `~/mpango-erp`, configurable via `--project-dir`

**Safety Features:**
- `--dry-run` mode — preview changes without applying
- `--yes` flag — skip confirmation for automation
- Interactive confirmation — requires typing "yes" by default
- Colored output — INFO/WARN/OK/ERR for clarity
- Exit code tracking — `set -euo pipefail`

**Usage Examples:**
```bash
# Preview what would be removed
bash scripts/safe_cleanup_vps.sh --dry-run

# Standard cleanup with confirmation
bash scripts/safe_cleanup_vps.sh

# Automated cleanup (CI/CD)
bash scripts/safe_cleanup_vps.sh --yes --project-dir /opt/mpango-erp
```

---

## Verification Output

Script prints structured summary:
```
╔══════════════════════════════════════════════════════════════╗
║                  Cleanup Complete                           ║
╠══════════════════════════════════════════════════════════════╣
║  Containers removed : 5                                     ║
║  Images removed     : 2                                     ║
║  Volumes removed    : 2                                     ║
║  Networks removed   : 1                                     ║
║  Project dir deleted: /home/user/mpango-erp                 ║
╠══════════════════════════════════════════════════════════════╣
║  Mpango ERP removed. Other services touched: 0              ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Files Created

| File | Purpose |
|------|---------|
| `scripts/safe_cleanup_vps.sh` | VPS-safe targeted cleanup script |

---

## Recommendations

1. **Test `--dry-run` first** on production VPS before actual cleanup
2. **Backup data** — `postgres_data` and `redis_data` volumes will be deleted
3. **Document other services** — keep a list of non-Mpango containers for verification
4. **Monitor after cleanup** — check `docker ps -a` to confirm no unintended removals
