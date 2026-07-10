# DC-2B-R1 VPS Compose Drift Forensics

| Field | Value |
|---|---|
| Date | 2026-07-10 |
| Report branch | `ops/dc2b-r1-compose-drift-forensics-2026-07-10` |
| Source target branch | `origin/product-dev-recovered` |
| Source target SHA | `e022f2156c62a849959bd0ae545c463505dae3d6` |
| Verdict | `STOP_AND_REPORT_CTO` |

---

## Scope

This task performed **read-only** forensics on the VPS working-copy drift of `/opt/mpango-erp/docker-compose.prod.yml`.

No deploy, checkout, reset, restore, stash, backup, compose validation, database action, or file modification was performed on the VPS.

---

## VPS Read-Only State

| Item | Value |
|---|---|
| VPS | `1.14.247.12` |
| User | `ubuntu` |
| Project path | `/opt/mpango-erp` |
| Current branch | `product-dev-recovered` |
| Current VPS HEAD | `bce3dcfc72b459a6a5ca429874ae3cb6be794b88` |
| Remote target SHA | `e022f2156c62a849959bd0ae545c463505dae3d6` |

### `git status --short --untracked-files=no`

Observed tracked status:

| Path | Status |
|---|---|
| `docker-compose.prod.yml` | modified |

### Drift uniqueness

Result: **YES** — the only tracked drift observed was `docker-compose.prod.yml`.

---

## File Hashes

| Artifact | SHA256 prefix |
|---|---|
| VPS current working copy `/opt/mpango-erp/docker-compose.prod.yml` | `fb23cbfaa18ca51f` |
| VPS `HEAD:docker-compose.prod.yml` | `7d91a01d9c84213d` |

---

## Sanitized Drift Summary

Raw diff was reviewed indirectly and **not** printed to terminal or report.

### Changed line ranges

| View | Line ranges |
|---|---|
| Current working copy changed lines | `73-82` |
| HEAD-side changed lines | none reported by zero-context diff |

### Change categories

| Category | Line ranges |
|---|---|
| `environment keys` | `73-82` |

### Drift characteristics

| Question | Result |
|---|---|
| Involves `image/build` | NO |
| Involves `ports` | NO |
| Involves `volumes` | NO |
| Involves `networks` | NO |
| Involves `env_file` | NO |
| Involves `environment keys` | YES |
| Involves `healthcheck` | NO |
| Involves `command` | NO |
| Involves `restart` | NO |
| Changes service topology | NO |
| Changes image source | NO |
| Changes mount paths | NO |
| Changes port exposure | NO |
| Changes startup command | NO |
| Diff has whitespace/check issues | NO |

### Security relevance

| Question | Result |
|---|---|
| Suspected credential-bearing or security-relevant drift | YES |

Reason for security relevance:

- the drift is inside tracked `environment` lines
- the changed range sits inside the backend runtime environment block
- that block includes application, multi-tenancy, and observability behavior controls

No secret values were copied into this report.

---

## Classification

Selected classification:

- **C. `UNEXPECTED_OR_SECURITY_RELEVANT_DRIFT`**

Rationale:

- the drift is in a tracked compose file, not an untracked `.env.prod`
- it changes backend `environment` behavior in the compose definition itself
- it is not limited to topology-neutral externalized host overrides
- because the change occurs in runtime control lines, it cannot be auto-reconciled safely

This is **not** classified as `A. ENVIRONMENT_OVERRIDE_ONLY` because the override lives in tracked compose content instead of being isolated to untracked deployment env.

This is **not** classified as `B. INTENDED_REPO_CHANGE_NOT_COMMITTED` because the current evidence is insufficient to prove intent, while the runtime control surface is security-relevant.

---

## Recommendation

### Can DC-2B safely continue to exact checkout now?

- **NO**

### Why not?

- CTO stop condition was explicit: if `docker-compose.prod.yml` or any tracked file is dirty, stop.
- The VPS is not on the requested runtime candidate SHA.
- Reconciling the drift would require a CTO-approved action outside this read-only task.

### Recommended next step

- CTO should inspect and decide whether this compose drift is:
  - a temporary host-local change that must be moved out of tracked compose, or
  - an intended product/runtime change that belongs in Git review, or
  - an unexpected security-relevant mutation that requires incident handling.

Until that decision is made, no exact checkout or deployment step should be executed on this VPS.

---

## Final Verdict

**STOP_AND_REPORT_CTO**
