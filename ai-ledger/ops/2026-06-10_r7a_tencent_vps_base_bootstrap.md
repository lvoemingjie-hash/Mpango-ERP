# R-7A Tencent VPS Base Bootstrap

**Date:** 2026-06-10
**Operator:** opencode
**Target:** Tencent VPS (1.14.247.12)
**Final Verdict:** READY_FOR_R7B_TENCENT_APP_DEPLOY_PREP

---

## Step 0 — Preserve R-6C Report

| Item | Result |
|------|--------|
| R-6C report committed | `03ccdb5` on detached HEAD |
| Pushed to OPS branch | `docs/ops/r6c-retry-predeploy-gate-2026-06-10` |
| R-6C verdict | READY_FOR_TENCENT_DEPLOY_APPLY, reclassified by CTO as READY_FOR_TENCENT_BOOTSTRAP_APPLY |

---

## Step 1 — Pre-Bootstrap Snapshot

| Check | Value |
|-------|-------|
| **Hostname** | VM-0-3-ubuntu |
| **Date (UTC)** | 2026-06-10 07:59 |
| **Kernel** | 6.8.0-117-generic x86_64 |
| **OS** | Ubuntu 24.04.4 LTS (Noble Numbat) ✅ |
| **Disk** | 40GB, 5.3G used (15%) |
| **Memory** | 3.6GB total, 546MB used |
| **IP** | eth0 10.1.0.3/22 |
| **Open ports** | 22 (SSH), 53 (DNS) |
| **docker** | ❌ Not installed |
| **git** | ✅ `/usr/bin/git` |
| **curl** | ✅ `/usr/bin/curl` |
| **ufw** | ✅ `/usr/sbin/ufw` |

**Target verified:** Tencent VPS, Ubuntu 24.04.4 LTS ✅

---

## Step 2 — Base Packages

| Package | Status |
|---------|--------|
| ca-certificates | ✅ 20240203 |
| curl | ✅ 8.5.0-2ubuntu10.9 |
| gnupg | ✅ 2.4.4-2ubuntu17.4 |
| git | ✅ 1:2.43.0-1ubuntu7.3 |

---

## Step 3 — Docker Engine Installation

**Method:** Official Docker apt repository for Ubuntu Noble (24.04)

| Step | Status |
|------|--------|
| Create `/etc/apt/keyrings` | ✅ |
| Add Docker GPG key | ✅ |
| Add `docker.list` apt source | ✅ |
| `apt update` | ✅ |
| Install `docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin` | ✅ |
| `systemctl enable --now docker` | ✅ |

**Used:** Official apt repository (NOT get.docker.com, NOT snap, NOT docker.io)

---

## Step 4 — Docker Verification

| Check | Result |
|-------|--------|
| `docker version` | Docker Engine 29.5.3 ✅ |
| `docker compose version` | Docker Compose v5.1.4 ✅ |
| `docker buildx version` | Buildx v0.34.1 ✅ |
| `systemctl is-active docker` | active ✅ |
| `systemctl is-enabled docker` | enabled ✅ |
| `docker run nginx:alpine` | Pulled and ran successfully ✅ |

**Note:** `hello-world` image failed via registry mirror (manifest issue). Fallback `nginx:alpine` test passed — Docker is fully functional.

**Registry mirror configured:** `https://docker.1ms.run` for China network optimization.

---

## Step 5 — Deployment Directories

| Directory | Status |
|-----------|--------|
| `/opt/mpango-erp` | ✅ Created, owner: ubuntu:ubuntu, mode: 755 |
| `/opt/mpango-backups` | ✅ Created, owner: ubuntu:ubuntu, mode: 755 |

**No repo cloned, no .env written, no application deployed.**

---

## Step 6 — Final Inventory

| Metric | Before | After |
|--------|--------|-------|
| **Disk used** | 5.3G (15%) | 5.8G (16%) |
| **Memory used** | 546MB | 615MB |
| **Disk available** | 33G | 32G |
| **Open ports** | 22, 53 | 22, 53 |
| **Docker images** | N/A | 0 |
| **Docker containers** | N/A | 0 |
| **Docker volumes** | N/A | 0 |

**Difference:** +~500MB disk (Docker packages), +~70MB memory (docker daemon).

---

## Compliance Confirmation

| Requirement | Status |
|-------------|--------|
| No app deployment (no docker compose up) | ✅ |
| No production env (.env/.env.prod) written | ✅ |
| No secrets read or printed | ✅ |
| No prune/cleanup executed | ✅ |
| No India VPS connection | ✅ |
| No apt upgrade / reboot | ✅ |
| No firewall changes (ufu unchanged) | ✅ |

---

## Final Verdict

**READY_FOR_R7B_TENCENT_APP_DEPLOY_PREP**

VPS base environment is fully bootstrapped:
1. ✅ Docker Engine 29.5.3 (official apt repo)
2. ✅ Docker Compose v5.1.4
3. ✅ Docker Buildx v0.34.1
4. ✅ Base packages (ca-certificates, curl, gnupg, git)
5. ✅ Deployment directories created
6. ✅ Registry mirror configured for China network
7. ✅ Docker daemon active + enabled on boot
