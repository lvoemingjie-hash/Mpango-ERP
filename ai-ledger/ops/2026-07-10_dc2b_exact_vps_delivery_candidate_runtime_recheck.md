# DC-2B Exact VPS Delivery Candidate Runtime Recheck

| Field | Value |
|---|---|
| Date | 2026-07-10 |
| Verdict | STOP_AND_REPORT_CTO |
| Source branch rechecked | `product-dev-recovered` |
| Source SHA rechecked | `e022f2156c62a849959bd0ae545c463505dae3d6` |
| Report branch | `ops/dc2b-exact-vps-delivery-runtime-recheck-2026-07-10` |
| Protected branch push | NOT PERFORMED |

---

## Executive Summary

This task did **not** proceed to VPS checkout, backup, compose validation, deploy, onboarding, or tenant runtime proof.

Reason: SSH access was established, but the target VPS deployment tree at `/opt/mpango-erp` is **tracked-dirty**. The required preflight stop condition triggered before any fetch, checkout, backup, compose validation, deploy, onboarding, or runtime mutation.

No product code, test, migration, config, compose file, database row, tenant, admin, role, permission, schema, SKU, payment, or ledger data was changed on the target runtime.

---

## Branch Context Before Any Commit

### Observed source runtime candidate

| Item | Value |
|---|---|
| Branch | `product-dev-recovered` |
| HEAD | `e022f2156c62a849959bd0ae545c463505dae3d6` |
| Merge base vs `origin/product-dev-recovered` | `e022f2156c62a849959bd0ae545c463505dae3d6` |
| Intended runtime target branch | `origin/product-dev-recovered` |

### Commit branch used for this report only

| Item | Value |
|---|---|
| Branch | `ops/dc2b-exact-vps-delivery-runtime-recheck-2026-07-10` |
| Base commit | `e022f2156c62a849959bd0ae545c463505dae3d6` |
| Scope | docs-only blocker fix + stop report |

---

## Required Blocker Fix

### `ai-ledger/index_BACKUP_646.md`

Resolved the tracked merge markers explicitly:

- removed `<<<<<<<`, `=======`, `>>>>>>>`
- kept the newer `Last Updated` date: `2026-02-18`
- preserved both intended sections:
  - `QA & Test`
  - `CTO Reviews & Analysis`

This fix is docs-only and does not touch product runtime code or deployment config.

---

## VPS Access Check

Latest deployment ledgers point to:

| Item | Value |
|---|---|
| VPS | `1.14.247.12` |
| User from latest rollback/provenance ledgers | `ubuntu` |
| Project path | `/opt/mpango-erp` |

### Access attempts

All commands were run in non-interactive batch mode to avoid secret prompts in logs.

| Attempt | Result |
|---|---|
| `ssh` with operator-provided password to `ubuntu@1.14.247.12` | SUCCESS |

### Observed VPS repo state before any mutation

| Item | Value |
|---|---|
| Remote | `origin https://github.com/lvoemingjie-hash/Mpango-ERP.git` |
| Current branch | `product-dev-recovered` |
| Current HEAD on VPS | `bce3dcfc72b459a6a5ca429874ae3cb6be794b88` |
| Tracked status | `M docker-compose.prod.yml` |

### Consequence

Because the deploy tree is tracked-dirty, DC-2B stopped **before** these mandatory mutating steps could be executed:

1. `git fetch origin`
2. `git checkout -B product-dev-recovered origin/product-dev-recovered`
3. repo-external DB backup creation on the VPS
4. `docker compose -f docker-compose.prod.yml --env-file .env.prod config`
5. Alembic head/current verification on the VPS
6. `docker compose ... up -d --build` on the VPS
7. all onboarding/business/runtime proofs A/B/C

The stop condition matched the CTO directive exactly: if `docker-compose.prod.yml` or any tracked file is dirty, stop and do not overwrite or reset.

---

## Local Gate Results on Exact Source SHA

These were rechecked locally against `product-dev-recovered @ e022f21`.

| Gate | Result |
|---|---|
| `git rev-parse HEAD` | `e022f2156c62a849959bd0ae545c463505dae3d6` |
| `git status --short` tracked files | clean; only untracked local artifacts present |
| `git ls-files -u` | empty |
| `git diff --cached --check` | empty |
| `pytest tests/test_platform_audit_api.py tests/test_platform_stats_api.py` | `59 passed` |
| `pnpm --ignore-workspace exec vitest run ...` | `30 passed / 4 files` |
| `npx gitnexus analyze` | success |
| `npx gitnexus status` | `Indexed commit: e022f21`, `Current commit: e022f21`, `up-to-date` |

### Merge-marker gate note

The exact command requested by CTO,

```bash
git grep --cached -n -E "^(<<<<<<<|=======|>>>>>>>)"
```

can report false positives on historical ledger files that begin with long pytest separator lines such as `====================` because `=======` is a prefix match in that regex.

After the `index_BACKUP_646.md` fix:

- no real tracked merge markers remained in `ai-ledger/index_BACKUP_646.md`
- `git ls-files -u` was empty
- `git diff --cached --check` was clean

This branch therefore contains **zero actual unresolved merge markers**.

---

## Runtime Proof Status

### Core Proof A: real new-customer onboarding

Status: **NOT RUN**

Reason: VPS preflight stopped on tracked-dirty deploy tree.

### Core Proof B: real new-tenant business loop

Status: **NOT RUN**

Reason: Proof A was not reachable after preflight stop.

### Core Proof C: security + platform boundary

Status: **NOT RUN ON VPS**

Reason: target runtime was accessible for read-only inspection only; deploy/recheck was blocked by preflight stop.

---

## Secrets Handling

- No password printed.
- No JWT printed.
- No email verification or setup token printed.
- No SMTP / DB credential printed.
- No backup content printed.
- No protected branch push performed.

---

## Stop Reason

This run is blocked by a tracked-dirty deployment tree on the target VPS.

The exact runtime candidate SHA is known and locally rechecked, and SSH access to `1.14.247.12` works with the operator-provided credential. However, `/opt/mpango-erp` currently contains a tracked modification to `docker-compose.prod.yml`, so DC-2B cannot legally fetch, checkout, backup, compose-validate, deploy, or proceed to onboarding/runtime proof until CTO clears or explains that drift.

---

## Verdict

**STOP_AND_REPORT_CTO**
