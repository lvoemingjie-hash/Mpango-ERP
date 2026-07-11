# DC-2B-R1 VPS Compose Drift Resolution Gate

Date: 2026-07-12
Ops branch: `ops/dc2b-r1-compose-drift-resolution-2026-07-12`
Target: `origin/product-dev-recovered @ 1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`
VPS: `1.14.247.12`
Project dir: `/opt/mpango-erp`

## Scope

Read-only forensics only. No checkout, reset, restore, deploy, backup, compose apply, or `.env.prod` read was performed. No secret values or raw compose values were printed.

## VPS Git State

- VPS branch: `product-dev-recovered`
- VPS HEAD: `bce3dcfc72b459a6a5ca429874ae3cb6be794b88`
- VPS `origin/product-dev-recovered`: `1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`
- Target SHA match: yes
- Tracked status: one dirty tracked file
- Changed file count: `1`
- Changed file: `docker-compose.prod.yml`

Tracked status summary:

```text
 M docker-compose.prod.yml
```

## Redacted Diff Summary

Changed line range from sanitized `git diff --unified=0 -- docker-compose.prod.yml` metadata:

```text
@@ -72,0 +73,10 @@ services:
```

Runtime environment key delta from sanitized diff metadata:

- Added env keys:
  - `EMAIL_PROVIDER`
  - `EMAIL_DELIVERY_MODE`
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USER`
  - `SMTP_PASSWORD`
  - `EMAIL_FROM`
  - `SMTP_STARTTLS`
  - `SMTP_USE_TLS`
- Removed env keys: none
- Non-env changed line count: `1`
- Forbidden categories detected in changed lines: none for `image`, `build`, `ports`, `volumes`, `command`, or `entrypoint`
- Strict secret literal suspect count: `0`

The non-env changed line was not printed by design. It was included only as a count in the redacted metadata and did not match security-relevant deployment categories.

## Working Copy Vs Target Product Compose

Backend service environment key list comparison was performed against:

- VPS working copy: `/opt/mpango-erp/docker-compose.prod.yml`
- Target product file: `origin/product-dev-recovered:docker-compose.prod.yml`

Result:

- Backend env key list equal: yes
- Working-copy extra backend env keys vs target: none
- Working-copy missing backend env keys vs target: none
- Working-copy SMTP key set equals target SMTP key set: yes

Required DC-2H SMTP keys:

| Key | Working copy | Target product file |
| --- | --- | --- |
| `EMAIL_PROVIDER` | present | present |
| `EMAIL_DELIVERY_MODE` | present | present |
| `SMTP_HOST` | present | present |
| `SMTP_PORT` | present | present |
| `SMTP_USER` | present | present |
| `SMTP_PASSWORD` | present | present |
| `EMAIL_FROM` | present | present |
| `SMTP_STARTTLS` | present | present |
| `SMTP_USE_TLS` | present | present |

## Classification

`A. MATCHES_PRODUCTIZED_DC2H`

Reason:

- The VPS dirty compose drift adds the same nine SMTP environment key names now present in the target product compose file.
- The complete backend environment key list in the VPS working copy equals the target product file key list.
- No removed env keys were detected.
- No image/build/ports/volumes/command/entrypoint changes were detected.
- No strict secret literal suspect was detected.

## Recommendation

`PASS_READY_FOR_CTO_APPROVE_VPS_COMPOSE_RESTORE`

Recommendation: CTO can approve discarding/restoring the VPS tracked `docker-compose.prod.yml` working-copy drift before the exact delivery-candidate checkout, because the runtime environment key drift is equivalent to the DC-2H productized compose wiring already merged into `origin/product-dev-recovered @ 1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`.

No restoration was performed in this gate.
