# DC-1D Final RC Runtime Recheck

- **Date**: 2026-07-09
- **Task ID**: DC-1D (Final Release Candidate Runtime Recheck)
- **Target commit (intended)**: `3d302222c2700b8f2adbb2d2339732f5255278fd`
- **Target branch**: `origin/product-dev-recovered`
- **Ops branch**: `ops/dc1d-final-rc-runtime-recheck-2026-07-09`
- **Prepared by**: Codex agent
- **Verdict**: `STOP_AND_REPORT_CTO`

## 0. Headline

DC-1D is a **production VPS runtime recheck**. Its core steps (exact checkout on the VPS,
DB backup, rebuild/redeploy, container/endpoint/Alembic verification, U6/product/platform
smoke, VPS log scan) all require interactive shell access to the production host
`1.14.247.12` as user `ubuntu`.

**The Codex agent does not have working SSH access to the production VPS.** All candidate
SSH keys were rejected (Permission denied). Therefore the runtime recheck could not be
executed, and per the task hard rules ("If blocked, STOP_AND_REPORT_CTO") this report is a
controlled halt, not a failure of the target baseline.

No production action was taken. No code, migration, frontend, package, or lockfile was
changed. No DB backup, restore, redeploy, or smoke was attempted. Nothing was pushed except
this ops branch.

## 1. Target Reachability (repo side, verified)

These repo-side facts were verified and are in order; the block is purely VPS access.

| Check | Result |
|---|---|
| `git fetch origin` | OK |
| Target commit resolves | OK -- `3d302222c2700b8f2adbb2d2339732f5255278fd` is a commit |
| Target == `origin/product-dev-recovered` tip | OK -- identical (`3d302222...`) |
| Target commit subject | `docs(dc1c-r2): enforce ASCII rollback runbook evidence` |
| DC-1C rollback runbook present in repo | OK -- `ai-ledger/ops/2026-07-09_dc1c_rollback_runbook_confirmation.md` |
| DC-1B evidence pack present (predecessor) | OK -- `ai-ledger/release/2026-07-09_dc1b_release_candidate_evidence_pack.md` |

Note: the target tip `3d302222` is docs-only relative to the DC-1B baseline (`9bb2b309`).
The runtime baseline proven by DC-1A was at `9bb2b309`; `3d302222` adds only the
DC-1C-R2 runbook ASCII cleanup on top, so no runtime-behavior change is expected between
the DC-1A baseline and this target. That expectation is, however, exactly what DC-1D was
supposed to re-prove on the VPS -- and that proof could not be obtained here.

## 2. Block Detail: VPS SSH Access

All attempts used read-only commands only (`echo`/`whoami`). No production state was
touched during probing.

| Attempt | User / Key | Result |
|---|---|---|
| default | `ubuntu` (no `-i`) | Permission denied (publickey,password) |
| `-i id_ed25519` | ubuntu | Permission denied (publickey,password) |
| `-i id_ed25519_do` | ubuntu | Permission denied (publickey,password) |
| `-i id_rsa` | ubuntu | Permission denied (publickey,password) |
| alternate users | `root`, `jeff0`, `jeff`, `admin` | denied/unreachable |

Findings:
- An SSH client is available (`/usr/bin/ssh`).
- The target host `1.14.247.12` is present in `~/.ssh/known_hosts`.
- The local `~/.ssh/config` defines a `mpango-vps` host, but it maps to a **different** IP
  (`143.110.177.2`, user `root`, key `id_ed25519_do`) -- not the DC-1D target host.
- No SSH agent is running; no additional identities are available.

## 3. Step-by-Step Status

| Step | Required | Status | Notes |
|---|---|---|---|
| 1. VPS exact checkout to `3d302222` | VPS shell | **BLOCKED** | No SSH access |
| 2. DB backup (record path/size/SHA256 prefix) | VPS shell | **BLOCKED** | -- |
| 3. Rebuild/redeploy via docker compose | VPS shell | **BLOCKED** | -- |
| 4. 5/5 containers healthy | VPS shell | **BLOCKED** | -- |
| 5. Endpoints `/health/live`, `/health/ready`, `/openapi.json`, `/`, `/docs` | VPS shell | **BLOCKED** | -- |
| 6. Alembic heads/current = `030_platform_backup_status_source` | VPS shell | **BLOCKED** | -- |
| 7. U6 onboarding smoke | VPS shell | **BLOCKED** | -- |
| 8. Product smoke (SKUs, intake, orders, canonical pay, legacy pay 409, inventory) | VPS shell | **BLOCKED** | -- |
| 9. Platform smoke (health/info/status, tenant-token block, no TenantContextMissing, no 500) | VPS shell | **BLOCKED** | -- |
| 10. Rollback spot check (no restore) | repo + VPS | **PARTIAL** | See Section 5 |
| 11. Log scan (no new tracebacks/500 bursts, no secret/token leakage) | VPS shell | **BLOCKED** | -- |
| 12. Report verdict | -- | **STOP_AND_REPORT_CTO** | This report |
| 13. Commit ledger only | local | OK | This file only |
| 14. Push ops branch only | local | OK | Only `ops/dc1d-...` pushed |

## 4. Rollback Spot Check (Step 10, partial -- repo-side only)

Step 10 is the only step with a repo-side component; that portion was completed. The
VPS-side components ("Confirm DC-1A backup exists", "Confirm docker compose config parses")
were already verified on the VPS by the CTO in DC-1C-R1 and are cited, not re-verified here.

| Sub-check | Source | Result |
|---|---|---|
| DC-1A backup artifact documented | DC-1A report + DC-1C-R1 runbook | path `/home/ubuntu/.secure-backups/mpango_erp_dc1a_20260709-210407.sql`, size 309,157 bytes, SHA256 prefix `b512815d80ccdb47` -- **documented**, not re-verified on VPS (no access) |
| DC-1C runbook exists in repo | `git ls-tree origin/product-dev-recovered` | OK -- `ai-ledger/ops/2026-07-09_dc1c_rollback_runbook_confirmation.md` present at the target commit |
| docker compose config parses | DC-1C-R1 (VPS) | Documented as exit_code=0 valid in DC-1C-R1; locally the file references VPS-only env vars (e.g. `MPANGO_ENV`) so a local parse is not meaningful -- must be re-confirmed on VPS |

No restore was performed (hard rule respected).

## 5. Rollback Readiness

Not re-verified. DC-1C-R1 confirmed rollback readiness at the prior baseline `9bb2b309`.
Because DC-1D could not reach the VPS, rollback readiness at the current target `3d302222`
is **not independently confirmed by this run**. The DC-1C runbook steps remain applicable
(change only the checkout SHA from `9bb2b309` to `3d302222` if rolling back to this target).

## 6. Secrets Handling

No secrets, JWTs, raw tokens, SMTP passwords, DB passwords, `.env` content, or backup
content were printed or recorded in this report. SSH private-key material was never
displayed; only key **filenames** and the SSH server's rejection responses are referenced.

## 7. What Was NOT Done (hard-rule compliance)

- `product-dev-recovered` was NOT pushed.
- No product/platform code, migration, frontend, package, or lockfile was edited.
- No rollback restore was run.
- No tenant/admin/RBAC was manually created.
- No redeploy was attempted.
- No DB backup was taken (could not reach VPS).

## 8. Verdict

**STOP_AND_REPORT_CTO**

Reason: the Codex agent lacks SSH access to the production VPS (`1.14.247.12`), so the
DC-1D runtime recheck cannot be executed by this agent. All repo-side preconditions are met
(target commit is the `origin/product-dev-recovered` tip; DC-1C runbook and DC-1B evidence
pack are present). The remaining work requires either (a) CTO execution of the DC-1D steps
on the VPS, or (b) provisioning VPS SSH access for the agent.

## 9. Branch and Push Confirmation

- Ops branch: `ops/dc1d-final-rc-runtime-recheck-2026-07-09` (docs-only).
- `product-dev-recovered` was NOT pushed.
- `platform-dev` was NOT pushed.
- This report is the only file committed. Built in a dedicated worktree off
  `origin/product-dev-recovered @ 3d302222` so the main worktree's in-flight merge was not
  disturbed.
