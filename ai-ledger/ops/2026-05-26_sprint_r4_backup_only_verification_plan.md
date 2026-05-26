# Sprint R-4 Backup-Only Verification Plan

**Date**: 2026-05-26
**Scope**: Prove a safe, recoverable database backup path without printing secrets
**Branch**: ops/sprint-r2-vps-script-recovery-2026-05-25
**R-3B-R1 HEAD**: `b65a91c docs(ops): Sprint R-3B-R1 evidence corrections`
**Status**: PLAN -- R-4T corrected, awaiting CTO/user approval before execution

## 1. Purpose

Before any cleanup or deployment can proceed, we must prove that a complete, verifiable database backup can be created on the India VPS. This plan defines the backup method, verification steps, and safety constraints. **No backup will be executed until CTO/user separately approves R-4B execution.**

## 2. Backup Method

### 2.1 Recommended: docker exec with login shell (sh -lc)

pg_dump must connect to the running PostgreSQL process inside the existing container. The correct approach is `docker exec` with a login shell to ensure PATH is set:

```bash
set -euo pipefail
umask 077

BACKUP_TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/root/mpango-backups"
BACKUP_FILE="${BACKUP_DIR}/mpango_erp_${BACKUP_TS}.sql.gz"
BACKUP_TMP="${BACKUP_FILE}.tmp"

trap 'rm -f "${BACKUP_TMP}"' EXIT

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

test -f "${BACKUP_FILE}" && { echo "ERROR: ${BACKUP_FILE} already exists. Aborting."; exit 1; }

docker exec mpango_prod_postgres sh -lc 'command -v pg_dump && pg_dump --version' \
  || { echo "ERROR: pg_dump not found inside container."; exit 1; }

docker exec mpango_prod_postgres sh -lc 'pg_dump -U mpango -d mpango_erp --clean --if-exists' \
  | gzip -c > "${BACKUP_TMP}"

gzip -t "${BACKUP_TMP}" || { echo "ERROR: gzip verification failed on temp file. Aborting."; exit 1; }

mv "${BACKUP_TMP}" "${BACKUP_FILE}"

trap - EXIT

chmod 600 "${BACKUP_FILE}"
sha256sum "${BACKUP_FILE}" > "${BACKUP_FILE}.sha256"
chmod 600 "${BACKUP_FILE}.sha256"
ls -lh "${BACKUP_FILE}"
```

**Why this method**:
- Connects to the running PostgreSQL process via the existing container.
- `sh -lc` loads login profile to set PATH correctly for pg_dump.
- `--clean --if-exists` makes the dump restorable with `psql < dump.sql`.
- Piped through `gzip -c` to stdout, written to temp file on host.
- Pre-checks `command -v pg_dump` before attempting dump.
- Collision guard: `test -f` ensures no overwrite.
- **Atomic write**: Writes to `.tmp` first; only promoted to final filename after `gzip -t` passes. Prevents half-failed backups from appearing valid.
- **trap cleanup**: If the script exits early (error, signal), the `.tmp` file is automatically removed.
- **Permission hardening**: `umask 077` ensures new files are owner-only. Directory `chmod 700` and file `chmod 600` enforce strict access even if umask was overridden. Backup contains real business data and must not be readable by other users.

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
```

To preview the dump header without triggering SIGPIPE under `set -euo pipefail`, use `awk` instead of `head`:

```bash
set +o pipefail
zcat "${BACKUP_FILE}" | awk 'NR<=20 {print}'
set -o pipefail
```

**Why `awk` instead of `head`**: Under `set -euo pipefail`, `head -20` closes its input after 20 lines, causing `zcat` to receive SIGPIPE and exit non-zero, which would trigger a false failure. `awk 'NR<=20 {print}'` reads the entire stream without early close, avoiding this issue.

## 7. File Size Recording

```bash
ls -lh "${BACKUP_FILE}"
```

Record the file size in the post-execution ledger.

## 8. How to Avoid Printing Secrets

- **Never `cat .env` or `cat .env.prod`**: The backup script does not read any env files.
- **Never `printenv`**: No environment variable printing.
- **pg_dump does not dump credentials**: It dumps schema + data, not postgres user passwords or .env contents.
- **The dump may contain application data**: Never print the full dump contents. Only the first 20 header lines via `awk 'NR<=20 {print}'` for verification.
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
- **No dump contents printing**: Only the first 20 header lines via `awk 'NR<=20 {print}'` of the compressed dump header.
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
- First 20 header lines via `awk 'NR<=20 {print}'` (sanitized)
- Confirmation: no cleanup, no deployment, no secrets read, no dump contents printed

## 14. R-4R Corrections

- **P1 Fixed**: Removed `docker run --volumes-from` as recommended method. Added as anti-pattern in section 2.2 with explanation of why it is wrong (pg_dump needs running server, volumes-from defaults to read-write, risks corruption).
- **P1 Fixed**: Corrected `--volumes-from` "read-only by default" claim. It is NOT read-only by default; requires explicit `:ro` flag.
- **New recommended method**: `docker exec mpango_prod_postgres sh -lc 'pg_dump ...'` connects to the running PostgreSQL process correctly.
- **Added**: `set -euo pipefail`, `test -f` collision guard, `command -v pg_dump` pre-check, `gzip -t` verification, file size recording.
- **Status**: Plan corrected. No backup executed. Awaiting CTO review of R-4R before push.

## 15. R-4S Corrections

- **P1 Fixed**: Backup now writes to `${BACKUP_FILE}.tmp` first, then `gzip -t` verifies integrity before `mv` to final filename. Prevents half-failed backups from appearing valid.
- **P1 Fixed**: Added `trap 'rm -f "${BACKUP_TMP}"' EXIT` to auto-cleanup temp file on early exit or signal. `trap - EXIT` clears trap after successful promotion.
- **P2 Fixed**: Header preview changed from `zcat | head -20` to `zcat | awk 'NR<=20 {print}'` with `set +o pipefail` guard. Avoids SIGPIPE false failure under `set -euo pipefail`.
- **Added**: `sha256sum` and `ls -lh` now integrated into the main backup script (section 2.1), executed only on the final promoted file.
- **Status**: R-4S plan correction only. No backup executed. No VPS connection. No push. Awaiting CTO approval.

## 16. R-4T Corrections

- **P1 Fixed**: Added `umask 077` after `set -euo pipefail`. Ensures all new files are owner-only by default.
- **P1 Fixed**: Added `chmod 700 "${BACKUP_DIR}"` after `mkdir -p`. Backup directory is strictly owner-accessible.
- **P1 Fixed**: Added `chmod 600 "${BACKUP_FILE}"` and `chmod 600 "${BACKUP_FILE}.sha256"` after creation. Even if umask was overridden, files are locked to owner-only. Backup contains real business data and must not leak.
- **P2 Fixed**: All residual `head -20` references in Hard Restrictions, Secrets, and Post-Execution Deliverable sections replaced with `awk 'NR<=20 {print}'` or descriptive text. No `head` command remains anywhere in the document except the anti-pattern explanation in section 6.
- **Status**: R-4T plan correction only. No backup executed. No VPS connection. No push. Awaiting CTO approval.

## 17. R-4B Execution Results

**Execution Date**: 2026-05-27 06:38 UTC
**Status**: BACKUP SUCCESSFUL

### Backup File

| Field | Value |
|-------|-------|
| Path | `/root/mpango-backups/mpango_erp_20260527_063830.sql.gz` |
| Size | 10,967 bytes (11K) |
| SHA256 | `d2c4aebeda4dc4f28ff50e97d109d69e69b90735d048faa5008964ccfc9383df` |
| gzip -t | PASS |
| pg_dump version | 15.15 |
| Database | mpango_erp on PostgreSQL 15.15 |

### Permission Verification

```
drwx------ 2 root root 4096 May 26 22:39 /root/mpango-backups
-rw------- 1 root root 10967 May 26 22:38 mpango_erp_20260527_063830.sql.gz
-rw------- 1 root root   121 May 26 22:39 mpango_erp_20260527_063830.sql.gz.sha256
```

- Directory: `700` (drwx------) -- PASS
- Backup file: `600` (-rw-------) -- PASS
- SHA256 file: `600` (-rw-------) -- PASS

### Header Preview (first 20 lines via awk)

```
--
-- PostgreSQL database dump
--
\restrict [REDACTED]
-- Dumped from database version 15.15
-- Dumped by pg_dump version 15.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;
```

**Redaction note**: The `\restrict` line contains a pg_dump internal token. It is not a user secret but has been redacted in this report as a precaution.

### Execution Steps Completed

1. `mkdir -p /root/mpango-backups && chmod 700` -- PASS
2. `df -h /root` -- 6.1G available -- PASS
3. `docker exec mpango_prod_postgres sh -lc 'command -v pg_dump && pg_dump --version'` -- pg_dump 15.15 found -- PASS
4. `pg_dump | gzip -c > .tmp` -- DUMP_EXIT=0 -- PASS
5. `gzip -t .tmp` -- PASS
6. `mv .tmp .sql.gz` -- PASS
7. `chmod 600 .sql.gz` -- PASS
8. `sha256sum > .sha256 && chmod 600 .sha256` -- PASS
9. Header preview via `awk 'NR<=20'` -- PASS (valid SQL dump header)

### Confirmation

- **No cleanup**: No docker stop/rm/rmi/volume rm/network rm/system prune executed.
- **No deployment**: No docker compose up, git pull, or alembic executed.
- **No secrets read**: No .env contents, passwords, or tokens accessed.
- **No dump contents printed**: Only first 20 header lines via awk preview.
- **sing-box untouched**: Port 443 service not disturbed.
- **No docker image prune**: 21 dangling images remain untouched.
