# Sprint R-4 Backup-Only Verification Plan

**Date**: 2026-05-26
**Scope**: Prove a safe, recoverable database backup path without printing secrets
**Branch**: ops/sprint-r2-vps-script-recovery-2026-05-25
**R-3B-R1 HEAD**: `b65a91c docs(ops): Sprint R-3B-R1 evidence corrections`
**Status**: PLAN -- awaiting CTO/user approval before execution

## 1. Purpose

Before any cleanup or deployment can proceed, we must prove that a complete, verifiable database backup can be created on the India VPS. This plan defines the backup method, verification steps, and safety constraints. **No backup will be executed until CTO/user separately approves R-4B execution.**

## 2. Backup Method

### 2.1 pg_dump via docker run (Recommended)

Since `docker exec mpango_prod_postgres pg_dump` had PATH issues (per R-3B-R1), we use a fresh container mounting the same volume:

```bash
BACKUP_TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/root/mpango-backups"
BACKUP_FILE="${BACKUP_DIR}/mpango_erp_${BACKUP_TS}.sql.gz"

mkdir -p ${BACKUP_DIR}

docker run --rm \
  --volumes-from mpango_prod_postgres \
  -v ${BACKUP_DIR}:${BACKUP_DIR} \
  postgres:15-alpine \
  pg_dump -U mpango -d mpango_erp --clean --if-exists \
  | gzip > ${BACKUP_FILE}
```

**Why this method**:
- Uses the same postgres:15-alpine image already on VPS (274MB, no download needed).
- `--volumes-from` mounts the postgres data volume read-only by default.
- `--clean --if-exists` makes the dump restorable with `psql < dump.sql`.
- Piped through `gzip` to save disk (database is ~66.8MB, compressed will be much smaller).

### 2.2 Fallback: docker exec with full PATH

```bash
docker exec mpango_prod_postgres sh -lc \
  'pg_dump -U mpango -d mpango_erp --clean --if-exists' \
  | gzip > ${BACKUP_FILE}
```

Uses `sh -lc` to load login profile, which should set PATH correctly for pg_dump.

## 3. Backup File Path and Naming

- **Directory**: `/root/mpango-backups/` (new directory, created by the plan)
- **Filename pattern**: `mpango_erp_YYYYMMDD_HHMMSS.sql.gz`
- **Example**: `mpango_erp_20260526_143000.sql.gz`

## 4. Avoiding Overwriting Old Backups

- Each backup uses a unique timestamp in the filename.
- Before writing, check if file already exists: `test -f ${BACKUP_FILE} && echo "FILE EXISTS, aborting" && exit 1`
- Never use a fixed filename like `latest.sql.gz`.
- Keep at least the 2 most recent backups; manual cleanup only with CTO approval.

## 5. SHA256 Verification

After backup creation, compute and record the hash:

```bash
sha256sum ${BACKUP_FILE} > ${BACKUP_FILE}.sha256
cat ${BACKUP_FILE}.sha256
```

This produces output like:
```
a1b2c3d4e5f6...  /root/mpango-backups/mpango_erp_20260526_143000.sql.gz
```

The hash file will be recorded in this ledger after execution.

## 6. Verifying Dump is Readable

After creating the backup, verify it is a valid gzip containing SQL:

```bash
gzip -t ${BACKUP_FILE} && echo "gzip OK"
zcat ${BACKUP_FILE} | head -20
```

**Important**: `head -20` will show only the pg_dump header comments (version, dump date, database name). It will NOT show any data rows, user data, or secrets. If the first 20 lines contain unexpected content, STOP and report.

## 7. How to Avoid Printing Secrets

- **Never `cat .env` or `cat .env.prod`**: The backup script does not read any env files.
- **Never `printenv`**: No environment variable printing.
- **pg_dump does not dump credentials**: It dumps schema + data, not postgres user passwords or .env contents.
- **The dump may contain application data**: Never print the full dump contents. Only `head -20` for header verification.
- **The sha256 file is safe to record**: It contains only a hash and filename.

## 8. Disk Space Check Before Backup

Before executing, verify available disk:

```bash
df -h /root
```

Requirement: at least 200MB free (database is ~66.8MB, compressed will be smaller, but leave headroom).

## 9. Hard Restrictions

- **No cleanup**: No docker stop/rm/rmi/volume rm/network rm/system prune.
- **No deployment**: No docker compose up, git pull, or alembic.
- **No .env reading**: No cat/printenv of any env files.
- **No dump contents printing**: Only `head -20` of the compressed dump header.
- **No image cleanup**: Do NOT `docker image prune` the 21 dangling images. Exact image-id listing and dry-run required first if cleanup is ever needed.
- **sing-box protection**: sing-box on port 443 must not be disturbed. Do not stop, remove, or modify any non-Mpango container/process.
- **No git pull**: No code changes on VPS.
- **No alembic**: No migration execution.

## 10. Stop Conditions

Operations MUST STOP and report to CTO if:
- Disk space is less than 200MB free.
- pg_dump fails (exit code non-zero).
- gzip verification fails.
- The backup file already exists (collision).
- Any unexpected error from docker commands.
- sing-box process is not running on port 443 (it should be left alone).

## 11. CTO Approval Gate

- [ ] CTO/user approves creation of `/root/mpango-backups/` directory on VPS
- [ ] CTO/user approves pg_dump execution method
- [ ] CTO/user confirms backup file may be created on VPS disk

**This plan is not executable until all three checkboxes above are confirmed by CTO/user.**

## 12. Post-Execution Deliverable (for R-4B)

After execution, this file will be updated with:
- Backup file path and filename
- File size
- SHA256 hash
- gzip verification result
- `head -20` header output (sanitized)
- Confirmation: no cleanup, no deployment, no secrets read, no dump contents printed
