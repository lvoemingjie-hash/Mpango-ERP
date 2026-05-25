# Sprint R-3A Candidate VPS Connectivity Probe

**Date**: 2026-05-26
**Scope**: Minimal read-only SSH connectivity probe to candidate VPS
**Branch**: ops/sprint-r2-vps-script-recovery-2026-05-25

## 1. Probe Command

```
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no root@143.110.177.2 "hostname; date; uname -a"
```

## 2. Result

**SSH Status**: SUCCESS (exit code 0, no password prompt, no host key blocking)

**Sanitized stdout**:

```
ubuntu-s-1vcpu-1gb-blr1-01
Mon May 25 23:11:33 UTC 2026
Linux ubuntu-s-1vcpu-1gb-blr1-01 5.15.0-113-generic #123-Ubuntu SMP Mon Jun 10 08:16:17 UTC 2024 x86_64 x86_64 x86_64 GNU/Linux
```

**Sanitized stderr**: (none)

## 3. Host Identity Assessment

| Field | Value |
|-------|-------|
| Hostname | `ubuntu-s-1vcpu-1gb-blr1-01` |
| Region indicator | `blr1` = Bangalore, India (DigitalOcean) |
| Instance type | `1vcpu-1gb` (smallest droplet) |
| OS | Ubuntu, kernel 5.15.0-113-generic |
| Architecture | x86_64 |
| Current time | Mon May 25 23:11:33 UTC 2026 |

**Assessment**: This host matches the historical Mpango VPS profile:
- DigitalOcean Bangalore region (India) -- consistent with "India VPS".
- Hostname pattern `ubuntu-s-1vcpu-1gb-blr1-01` matches the naming convention from `docs/README_VPS_DEPLOY.md` target `143.110.177.2`.
- No suspicious indicators in the output.

**Verdict**: This appears to be the expected Mpango candidate VPS. CTO should confirm before proceeding to full R-3 inventory.

## 4. Confirmation

- **No cleanup**: No destructive Docker or filesystem commands were executed.
- **No deployment**: No git pull, docker compose up, or alembic commands were executed.
- **No secrets read**: No .env, .env.prod, passwords, or tokens were accessed.
- **No remote file changes**: Only read-only commands (`hostname`, `date`, `uname -a`) were executed.
- **No scripts executed**: Neither `safe_cleanup_vps.sh` nor `deploy_vps.sh` was run on the VPS.

## 5. Next Steps

- Awaiting CTO confirmation that `143.110.177.2` / `ubuntu-s-1vcpu-1gb-blr1-01` is the approved India VPS target.
- If confirmed, proceed to full R-3 inventory as defined in `ai-ledger/ops/2026-05-26_sprint_r3_vps_inventory_only.md`.
