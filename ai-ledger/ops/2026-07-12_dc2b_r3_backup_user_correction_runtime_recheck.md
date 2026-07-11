# DC-2B-R3 Backup User Correction Runtime Recheck

Date: 2026-07-12
Ops branch: `ops/dc2b-r3-backup-user-correction-runtime-recheck-2026-07-12`
Target: `origin/product-dev-recovered @ 1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`
VPS: `1.14.247.12`
Project dir: `/opt/mpango-erp`

## Scope

R3 resumed after R2 stopped because the backup command used the default/root DB role. This run used the Postgres service/container environment to obtain the non-secret DB user and DB name, created a valid backup, then continued until the deploy/container-health hard stop.

No `.env.prod` content, DB password, SMTP password, JWT, full `DATABASE_URL`, backup contents, or raw backend log lines were printed.

## Preflight

- VPS tracked status before backup/deploy: clean
- VPS HEAD: `1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`
- Target match: yes

## Backup

Backup connection source:

- Used the running Postgres compose service/container.
- Used non-secret `POSTGRES_USER` and `POSTGRES_DB` from inside the container.
- Did not print `POSTGRES_PASSWORD` or `.env.prod`.

Backup evidence:

- Path: `/home/ubuntu/.secure-backups/dc2b_r3_20260711T063843Z.sql`
- Size bytes: `396350`
- SHA256 prefix: `6f2759753387`
- Metadata validation: passed; file contained PostgreSQL dump metadata in the header.

## Compose And Deploy

- `docker compose -f docker-compose.prod.yml --env-file .env.prod config -q`: passed
- `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`: failed

Hard stop reason:

```text
dependency failed to start: container mpango_prod_backend is unhealthy
```

Container status after short wait:

```text
mpango_prod_frontend Up About a minute (healthy)
mpango_prod_backend Restarting (1) 1 second ago
mpango_prod_gateway Up 43 hours (healthy)
mpango_prod_postgres Up 7 days (healthy)
mpango_prod_redis Up 7 days (healthy)
```

## Not Performed After Hard Stop

- Alembic heads/current verification
- Core health smoke
- Auth/onboarding smoke
- Product/runtime smoke
- DC-2M2 schema proof

## Sanitized Backend Log Count Summary

Counts only; no raw log lines were printed.

- Decimal serialization traceback count: `0`
- TenantContextMissing count: `0`
- UndefinedTable count: `0`
- retailer_prices DDL-related keyword count: `10`
- mv_sales_daily missing keyword count: `0`
- Secret leak keyword count (`SMTP_PASSWORD`, `DATABASE_URL`, `POSTGRES_PASSWORD`, `JWT`): `0`

## Secret Handling

- `.env.prod` contents were not printed.
- DB password was not printed.
- SMTP password was not printed.
- JWT/token values were not printed.
- Backup contents were not printed.
- Raw backend log lines were not printed.

## Final Verdict

`STOP_AND_REPORT_CTO`

Reason: deployment/container-health hard stop. The backup correction succeeded, but `mpango_prod_backend` became unhealthy/restarting during deploy.
