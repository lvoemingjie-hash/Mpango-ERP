# DC-2B-R2 Exact VPS Runtime Recheck After Approved Compose Restore

Date: 2026-07-12
Ops branch: `ops/dc2b-r2-exact-vps-runtime-recheck-2026-07-12`
Target: `origin/product-dev-recovered @ 1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`
VPS: `1.14.247.12`
Project dir: `/opt/mpango-erp`

## Scope

Runtime recheck was resumed after CTO approved discarding only the local tracked `docker-compose.prod.yml` drift because DC-2B-R1 classified it as `A. MATCHES_PRODUCTIZED_DC2H`.

Allowed destructive action performed:

- `git restore -- docker-compose.prod.yml`

No `git reset --hard`, untracked cleanup, deployment, compose apply, Alembic check, smoke test, schema proof, or log scan was performed after the backup hard stop.

## Preflight And Approved Restore

Initial tracked dirty preflight confirmed the only tracked dirty file was `docker-compose.prod.yml`.

Approved restore result:

```text
PRECHECK_ONLY_DOCKER_COMPOSE
TRACKED_CLEAN_AFTER_RESTORE
```

Tracked status after restore: clean.

## Exact Checkout

The VPS branch was checked out to the exact target ref:

- Branch: `product-dev-recovered`
- HEAD after checkout: `1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`
- Target match: yes
- Tracked status after checkout: clean

## Backup

Backup did not complete successfully. This is a hard stop condition.

Sanitized failure:

```text
pg_dump: connection failed because role "root" does not exist
```

No valid backup path, size, or SHA256 prefix was recorded because the backup command failed before producing valid backup evidence.

## Not Performed After Hard Stop

- `docker compose -f docker-compose.prod.yml --env-file .env.prod config -q`
- `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`
- Container health verification
- Alembic heads/current verification
- Core health smoke
- Auth/onboarding smoke
- Product/runtime smoke
- DC-2M2 schema proof
- Backend log scan

## Secret Handling

- `.env.prod` contents were not printed.
- No DB password, SMTP password, JWT, token, or backup contents were printed.
- No secret-bearing logs were printed.

## Final Verdict

`STOP_AND_REPORT_CTO`

Reason: backup hard stop. The database backup failed before deployment validation could begin.
