#!/bin/bash
cd /root/mpango-erp
docker compose -f docker-compose.prod.yml exec -T postgres psql -U mpango -d mpango_erp <<'SQL'
SELECT schemaname, viewname FROM pg_views WHERE schemaname LIKE 't_%';
SELECT schemaname, matviewname FROM pg_matviews WHERE schemaname LIKE 't_%';
SQL
