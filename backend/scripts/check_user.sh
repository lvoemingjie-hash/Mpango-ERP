#!/bin/bash
cd /root/mpango-erp
docker compose -f docker-compose.prod.yml exec -T backend psql -U mpango -d mpango_erp -c "SELECT email, is_active FROM public.users WHERE email='admin@mpango.demo';"
