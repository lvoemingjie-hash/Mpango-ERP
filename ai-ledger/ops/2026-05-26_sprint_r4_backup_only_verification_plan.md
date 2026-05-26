# Sprint R-4 Backup-Only Verification Plan

**Date**: 2026-05-26
**Scope**: Prove a safe, recoverable database backup path without printing secrets
**Branch**: ops/sprint-r2-vps-script-recovery-2026-05-25
**R-3B-R1 HEAD**: `b65a91c docs(ops): Sprint R-3B-R1 evidence corrections`
**Status**: PLAN -- R-4R corrected, awaiting CTO/user approval before execution

## 1. Purpose

Before any cleanup or deployment can proceed, we must prove that a complete, verifiable database backup can be created on the India VPS. This plan defines the backup method, verification steps, and safety constraints. **No backup will be executed until CTO/user separately approves R-4B execution.**

## 2. Backup Method

### 2.1 Recommended: docker exec with login shell (sh -lc)

pg_dump must connect to the running PostgreSQL process inside the existing container. The correct approach is `docker exec` with a login shell to ensure PATH is set:

```bash
set -euo pipefail

BACKUP_TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/root/mpango-backups"
BACKUP_FILE="${BACKUP_DIR}/mpango_erp_${BACKUP_TS}.sql.gz"

mkdir -p "${BACKUP_DIR}"

test -f "${BACKUP_FILE}" && { echo "ERROR: ${BACKUP_FILE} already exists. Aborting."; exit 1; }

docker exec mpango_prod_postgres sh -lc 'command -v pg_dump && pg_dump --version' \
  || { echo "ERROR: pg_dump not found inside container."; exit 1; }

docker exec mpango_prod_postgres sh -lc 'pg_dump -U mpango -d mpango_erp --clean --if-exists' \
  | gzip -c > "${BACKUP_FILE}"

test -f "${BACKUP_FILE}" || { echo "ERROR: Backup file not created."; exit 1; }
```

**Why this method**:
- Connects to the running PostgreSQL process via the existing container.
- `sh -lc` loads login profile to set PATH correctly for pg_dump.
- `--clean --if-exists` makes the dump restorable with `psql < dump.sql`.
- Piped through `gzip -c` to stdout, written to file on host.
- Pre-checks `command -v pg_dump` before attempting dump.
- Collision guard: `test -f` ensures no overwrite.

### 2.2 Why NOT docker run --volumes-from (ANTI-PATTERN -- do not use)

`docker run --volumes-from mpango_prod_postgres postgres:15-alpine pg_dump` is **NOT a valid backup method**:

- pg_dump requires a **running PostgreSQL server** to connect to. Mounting the data volume does not provide a database connection.
- `--volumes-from` defaults to **read-write**, NOT read-only. The claim "read-only by default" was incorrect and dangerous.
- Mounting an online database's data volume to another container risks corruption.
- This method is listed here only as an anti-pattern to avoid.

## 3. Backup File Path and Naming

- **Directory**: `/root/mpango-backups/` (new directory, created by the plan)
- **Filename pattern**: `mpango_erp_YYYYMMDD_HHMMSS.sql.gz`
- **Example**: `mpango_erp_20260526_143000.sql.gz`

**Note**: R-4B execution will create this directory and files on the VPS. This requires CTO/user separate approval.

## 4. Avoiding Overwriting Old Backups

- Each backup uses a unique timestamp in the filename.
- Pre-flight check: `test -f "${BACKUP_FILE}"` -- if file exists, abort immediately.
- Never use a fixed filename like `latest.sql.gz`.
- Keep at least the 2 most recent backups; manual cleanup only with CTO approval.

## 5. SHA256 Verification

After backup creation, compute and record the hash:

```bash
sha256sum "${BACKUP_FILE}" > "${BACKUP_FILE}.sha256"
cat "${BACKUP_FILE}.sha256"
```

This produces output like:
```
a1b2c3d4e5f6...  /root/mpango-backups/mpango_erp_20260526_143000.sql.gz
```

The hash file will be recorded in this ledger after execution.

## 6. Verifying Dump is Readable

After creating the backup, verify it is a valid gzip containing SQL:

```bash
gzip -t "${BACKUP_FILE}" && echo "gzip OK" || { echo "gzip FAILED"; exit 1; }
zcat "${BACKUP_FILE}" | head -20
```

**Important**: `head -20` will show only the pg_dump header comments (version, dump date, database name). It will NOT show any data rows, user data, or secrets. If the first 20 lines contain unexpected content, STOP and report.

## 7. File Size Recording

```bash
ls -lh "${BACKUP_FILE}"
```

Record the file size in the post-execution ledger.

## 8. How to Avoid Printing Secrets

- **Never `cat .env` or `cat .env.prod`**: The backup script does not read any env files.
- **Never `printenv`**: No environment variable printing.
- **pg_dump does not dump credentials**: It dumps schema + data, not postgres user passwords or .env contents.
- **The dump may contain application data**: Never print the full dump contents. Only `head -20` for header verification.
- **The sha256 file is safe to record**: It contains only a hash and filename.

## 9. Disk Space Check Before Backup

Before executing, verify available disk:

```bash
df -h /root
```

Requirement: at least 200MB free (database is ~66.8MB, compressed will be smaller, but leave headroom).

## 10. Hard Restrictions

- **No cleanup**: No docker stop/rm/rmi/volume rm/network rm/system prune.
- **No deployment**: No docker compose up, git pull, or alembic.
- **No .env reading**: No cat/printenv of any env files.
- **No dump contents printing**: Only `head -20` of the compressed dump header.
- **No image cleanup**: Do NOT `docker image prune` the 21 dangling images. Exact image-id listing and dry-run required first if cleanup is ever needed.
- **sing-box protection**: sing-box on port 443 must not be disturbed. Do not stop, remove, or modify any non-Mpango container/process.
- **No git pull**: No code changes on VPS.
- **No alembic**: No migration execution.

## 11. Stop Conditions

Operations MUST STOP and report to CTO if:
- Disk space is less than 200MB free.
- `command -v pg_dump` fails inside the container.
- pg_dump fails (exit code non-zero).
- gzip -t verification fails.
- The backup file already exists (collision).
- Any unexpected error from docker commands.
- sing-box process is not running on port 443 (it should be left alone).

## 12. CTO Approval Gate

- [ ] CTO/user approves creation of `/root/mpango-backups/` directory on VPS
- [ ] CTO/user approves pg_dump via `docker exec mpango_prod_postgres sh -lc` method
- [ ] CTO/user confirms backup file may be created on VPS disk

**This plan is not executable until all three checkboxes above are confirmed by CTO/user.**

## 13. Post-Execution Deliverable (for R-4B)

After execution, this file will be updated with:
- Backup file path and filename
- File size
- SHA256 hash
- gzip -t verification result
- `head -20` header output (sanitized)
- Confirmation: no cleanup, no deployment, no secrets read, no dump contents printed

## 14. R-4R Corrections

- **P1 Fixed**: Removed `docker run --volumes-from` as recommended method. Added as anti-pattern in section 2.2 with explanation of why it is wrong (pg_dump needs running server, volumes-from defaults to read-write, risks corruption).
- **P1 Fixed**: Corrected `--volumes-from` "read-only by default" claim. It is NOT read-only by default; requires explicit `:ro` flag.
- **New recommended method**: `docker exec mpango_prod_postgres sh -lc 'pg_dump ...'` connects to the running PostgreSQL process correctly.
- **Added**: `set -euo pipefail`, `test -f` collision guard, `command -v pg_dump` pre-check, `gzip -t` verification, file size recording.
- **Status**: Plan corrected. No backup executed. Awaiting CTO review of R-4R before push.
