#!/bin/bash
cd /root/mpango-erp

echo '=== 1. Check reporting_role schema USAGE grants ==='
docker compose -f docker-compose.prod.yml exec -T postgres psql -U mpango -d mpango_erp -c "
SELECT nspname, has_schema_privilege('reporting_role', nspname, 'USAGE') AS has_usage
FROM pg_namespace
WHERE nspname LIKE 't_%';
"

echo '=== 2. Check reporting_role can SELECT from mv_sales_daily ==='
docker compose -f docker-compose.prod.yml exec -T postgres psql -U mpango -d mpango_erp -c "
SELECT has_table_privilege('reporting_role', 't_a0000000000040008000000000000001.mv_sales_daily', 'SELECT') AS can_select_mv;
"

echo '=== 3. Check reporting_user role memberships ==='
docker compose -f docker-compose.prod.yml exec -T postgres psql -U mpango -d mpango_erp -c "
SELECT r.rolname, m.rolname AS member_of
FROM pg_auth_members am
JOIN pg_roles r ON am.member = r.oid
JOIN pg_roles m ON am.roleid = m.oid
WHERE r.rolname = 'reporting_user' OR m.rolname = 'reporting_role';
"

echo '=== 4. Try querying as reporting_user directly ==='
docker compose -f docker-compose.prod.yml exec -T postgres psql -U reporting_user -d mpango_erp -c "
SET search_path TO t_a0000000000040008000000000000001, public;
SELECT * FROM mv_sales_daily LIMIT 1;
"
