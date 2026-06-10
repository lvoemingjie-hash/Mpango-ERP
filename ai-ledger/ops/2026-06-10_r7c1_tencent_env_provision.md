# R-7C-1 Tencent Env Provision — Safe Secret Regeneration

**Date:** 2026-06-10
**Operator:** opencode
**Target:** Tencent VPS (1.14.247.12) — VM-0-3-ubuntu
**Repo path:** `/opt/mpango-erp`
**Product HEAD:** `b8a31f875241e7ebcfc3cd11be05e993f5050259`
**Final Verdict:** READY_FOR_R7C2_DEPLOY_APPLY

---

## Step 1 — Preflight Snapshot

| Check | Result |
|-------|--------|
| Hostname | VM-0-3-ubuntu |
| Date (UTC) | 2026-06-10 09:33 |
| Kernel | 6.8.0-117-generic x86_64 |
| OS | Ubuntu 24.04.4 LTS |
| HEAD | `b8a31f875241e7ebcfc3cd11be05e993f5050259` ✅ |
| `git status --short` | Empty ✅ |
| `.env.prod` exists | ❌ ENV_MISSING (fresh server) |

---

## Step 2 — Backup Existing `.env.prod`

**Status:** No existing `.env.prod` found — backup skipped.

---

## Step 3 — Secret Generation

All secrets generated using Python `secrets.token_urlsafe()` on the VPS.

| Secret | Length | Weak Word Check | Status |
|--------|--------|-----------------|--------|
| `POSTGRES_PASSWORD` | 64 (min 48) | PASS | ✅ |
| `REPORTING_USER_PASSWORD` | 64 (min 48) | PASS | ✅ |
| `SECRET_KEY` | 86 (min 64) | PASS | ✅ |

**No secret values printed or disclosed at any point.**

---

## Step 4 — Non-Secret Config Values

| Key | Value | Source |
|-----|-------|--------|
| `GATEWAY_PORT` | `80` | MVP deployment — HTTP only |
| `CORS_ORIGINS` | `http://1.14.247.12` | Tencent VPS public IP |
| `VITE_API_URL` | `http://1.14.247.12` | Tencent VPS public IP |
| `MPANGO_ENV` | `production` | Production environment |
| `POSTGRES_USER` | `mpango` | Standard username |
| `POSTGRES_DB` | `mpango_erp` | Standard database name |

**Note:** Using public IP (1.14.247.12) instead of domain name for MVP testing. Jeff/CTO should configure a domain and TLS certificate before production use.

---

## Step 5 — `.env.prod` Atomic Write

| Action | Result |
|--------|--------|
| Write to `.env.prod.tmp` | ✅ |
| `chmod 600` on tmp | ✅ |
| `mv .env.prod.tmp .env.prod` | ✅ (atomic) |
| `chmod 600` on final | ✅ |
| Owner | `ubuntu:ubuntu` (deployment user) |

**Method:** Python script on VPS — secrets never left the server.

---

## Step 6 — Validation Without Disclosure

| Check | Result |
|-------|--------|
| `.env.prod` exists | ✅ |
| File mode | `600` |
| Owner/Group | `ubuntu:ubuntu` |
| File size | ~800 bytes |
| `POSTGRES_USER` | `<REDACTED>` ✅ |
| `POSTGRES_PASSWORD` | `<REDACTED>` ✅ |
| `POSTGRES_DB` | `<REDACTED>` ✅ |
| `SECRET_KEY` | `<REDACTED>` ✅ |
| `REPORTING_USER_PASSWORD` | `<REDACTED>` ✅ |
| `MPANGO_ENV` | `<REDACTED>` ✅ |
| `GATEWAY_PORT` | `<REDACTED>` ✅ |
| `CORS_ORIGINS` | `<REDACTED>` ✅ |
| `VITE_API_URL` | `<REDACTED>` ✅ |
| `REDIS_URL` | `<REDACTED>` ✅ |
| `ALGORITHM` | `<REDACTED>` ✅ |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `<REDACTED>` ✅ |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `<REDACTED>` ✅ |
| `APP_NAME` | `<REDACTED>` ✅ |
| `DEBUG` | `<REDACTED>` ✅ |
| `LOG_LEVEL` | `<REDACTED>` ✅ |
| `DEFAULT_TENANT_SCHEMA` | `<REDACTED>` ✅ |

**Length validations:**
- `POSTGRES_PASSWORD`: 64 chars — PASS (>= 48)
- `REPORTING_USER_PASSWORD`: 64 chars — PASS (>= 48)
- `SECRET_KEY`: 86 chars — PASS (>= 64)

---

## Step 7 — Compose Config Validation

```
docker compose -f docker-compose.prod.yml --env-file .env.prod config
```

| Check | Result |
|-------|--------|
| Exit code | `0` ✅ |
| Config valid | ✅ |
| Output file | Written to `/tmp/mpango-compose-config.txt`, read (redacted), then deleted |

**Warning:** Output file immediately deleted after verification to prevent secret leakage.

---

## Compliance Confirmation

| Requirement | Status |
|-------------|--------|
| No secret printed to output | ✅ |
| No secret written to git | ✅ |
| No `docker compose up` | ✅ |
| No `alembic upgrade` | ✅ |
| No prune/cleanup | ✅ |
| No India VPS connection | ✅ |
| Old `.env.prod` backed up (if existed) | N/A (no old file) |
| Atomic write (tmp + rename) | ✅ |

---

## Final Verdict

**READY_FOR_R7C2_DEPLOY_APPLY**

All env provision steps pass:

1. ✅ Preflight: HEAD at b8a31f8, clean working tree
2. ✅ New `.env.prod` generated with strong random secrets
3. ✅ Secrets generated on VPS — never passed through local/client
4. ✅ All 17 required env keys present and validated
5. ✅ Secret/password lengths verified (all >= minimum)
6. ✅ `docker compose config` — exit code 0 (config valid)
7. ✅ No secrets disclosed, no app started, no migration

**Next:** R-7C-2 — Deploy apply (requires CTO approval)
