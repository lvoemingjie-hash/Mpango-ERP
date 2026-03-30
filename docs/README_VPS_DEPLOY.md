# Mpango ERP — VPS Deployment Guide

**Version**: v0.2.0
**Target**: Ubuntu 22.04 VPS (143.110.177.2)
**Method**: Local script → SSH → GitHub Pull → Docker Compose

---

## Prerequisites

| Requirement | How to verify |
|-------------|---------------|
| Git Bash (Windows) | `git --version` in Git Bash |
| SSH key to VPS | `ssh root@143.110.177.2` (no password prompt) |
| GitHub SSH key on VPS | See [Setup GitHub SSH on VPS](#1-setup-github-ssh-key-on-vps) below |
| `.env.prod` in project root | `ls .env.prod` |

---

## Quick Start

```bash
# 1. Create production env file (one-time)
cp .env.example .env.prod
# Edit .env.prod with production secrets (real passwords, SECRET_KEY, etc.)

# 2. Deploy
bash scripts/deploy_vps.sh

# 3. Verify
curl http://143.110.177.2/health
```

---

## Setup Instructions

### 1. Setup GitHub SSH Key on VPS

The VPS needs its own SSH key to pull from the private GitHub repository.

```bash
# SSH into VPS
ssh root@143.110.177.2

# Generate a deploy key (no passphrase)
ssh-keygen -t ed25519 -C "mpango-vps-deploy" -f ~/.ssh/github_deploy -N ""

# Add to SSH config
cat >> ~/.ssh/config << 'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
EOF

chmod 600 ~/.ssh/config

# Print the public key
cat ~/.ssh/github_deploy.pub
```

Then add the public key to GitHub:

1. Go to **https://github.com/lvoemingjie-hash/Mpango-ERP/settings/keys**
2. Click **"Add deploy key"**
3. Title: `mpango-vps-deploy`
4. Paste the public key
5. Check **"Allow write access"** (optional, read-only is fine for pulls)
6. Click **"Add key"**

Verify on VPS:

```bash
ssh -T git@github.com
# Expected: "Hi lvoemingjie-hash! You've successfully authenticated..."
```

### 2. Setup SSH Key from Windows to VPS

If you haven't configured SSH key auth from your local machine to the VPS:

```powershell
# In PowerShell (Windows)
# Generate key if you don't have one
ssh-keygen -t ed25519 -C "jeff-windows"

# Copy public key to VPS
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@143.110.177.2 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

# Verify
ssh root@143.110.177.2 "echo 'SSH OK'"
```

### 3. Create `.env.prod`

```bash
cp .env.example .env.prod
```

Edit `.env.prod` with **real production values**:

```ini
# CRITICAL — change ALL of these from defaults
POSTGRES_USER=mpango
POSTGRES_PASSWORD=<STRONG_RANDOM_PASSWORD>
POSTGRES_DB=mpango_erp
SECRET_KEY=<GENERATE_WITH: python -c "import secrets; print(secrets.token_urlsafe(64))">
REPORTING_USER_PASSWORD=<STRONG_RANDOM_PASSWORD>
MPANGO_ENV=production

# Keep these as-is unless you have specific requirements
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
REDIS_URL=redis://redis:6379/0
LOG_LEVEL=INFO
VITE_API_URL=http://143.110.177.2
```

> ⚠️ **Never commit `.env.prod`** — it is already in `.gitignore`.

---

## Running the Deploy Script

### From Git Bash (Windows)

```bash
# Standard deploy (builds, starts, seeds demo data)
bash scripts/deploy_vps.sh

# Deploy without seeding demo data
bash scripts/deploy_vps.sh --skip-seed

# Deploy a specific branch
bash scripts/deploy_vps.sh --branch staging

# Deploy to a different VPS
bash scripts/deploy_vps.sh --vps-ip 10.0.0.5 --vps-user deploy
```

### What the script does

| Step | Action |
|------|--------|
| 1 | Checks `.env.prod` exists locally and SSH connectivity |
| 2 | Uploads `.env.prod` → VPS `~/mpango-erp/.env` via `scp` |
| 3 | `git pull` (or `git clone` on first deploy) on VPS |
| 4 | Installs Docker + Compose plugin if missing |
| 5 | `docker compose up -d --build` |
| 6 | Waits for health check, runs migrations + seeds demo data |
| 7 | Prints verification summary with all endpoints |

---

## Post-Deployment

### Verify services

```bash
# From local machine
curl http://143.110.177.2/health
curl http://143.110.177.2/health/live

# Open in browser
# http://143.110.177.2
# Login: admin@mpango.demo / DemoAdmin2026!
```

### Check logs on VPS

```bash
ssh root@143.110.177.2

cd ~/mpango-erp

# All services
docker compose -f docker-compose.prod.yml logs --tail=50

# Specific service
docker compose -f docker-compose.prod.yml logs --tail=50 backend
docker compose -f docker-compose.prod.yml logs --tail=50 gateway
```

### Restart services

```bash
ssh root@143.110.177.2
cd ~/mpango-erp
docker compose -f docker-compose.prod.yml restart
```

### Clean up (safe — Mpango only)

```bash
# Upload and run the safe cleanup script
scp scripts/safe_cleanup_vps.sh root@143.110.177.2:~/
ssh root@143.110.177.2 "bash ~/safe_cleanup_vps.sh --project-dir ~/mpango-erp"
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Permission denied (publickey)` on SSH | Run `ssh-copy-id root@143.110.177.2` |
| `Permission denied` on GitHub clone | Setup deploy key (see Step 1 above) |
| `.env.prod not found` | `cp .env.example .env.prod` and fill in secrets |
| Health check timeout | Check `docker compose logs backend` for errors |
| Port 80 in use | Another service (nginx/apache) is using port 80. Stop it or change `GATEWAY_PORT` in `.env.prod` |
| Frontend shows blank page | Check `docker compose logs frontend` — likely a build error |
| Database connection refused | Check `docker compose logs postgres` — likely wrong credentials |

---

## Architecture on VPS

```
Internet → :80 → [gateway (nginx)] → /api/*  → [backend :8000]
                                    → /*      → [frontend :80]

                  [backend] → [postgres :5432]
                            → [redis :6379]
```

All services run in Docker containers on the `mpango_network` bridge network.
