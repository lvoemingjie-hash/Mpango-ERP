# V4 cleanup record (completed — past tense, actual results)

- Backend uvicorn process: terminated via taskkill (PID list from netstat :8000);
  verified stopped — `curl http://127.0.0.1:8000/health` no longer responds.
- Frontend vite dev server: terminated via taskkill (PID list from netstat :5173);
  verified stopped — `curl http://localhost:5173/` no longer responds.
- Containers removed with `docker rm -f h2a_v4_pg16 h2a_v4_redis7`;
  `docker ps -a --filter name=h2a_v4 -q` returned 0.
- Volumes: the stack used container-local anonymous volumes on fresh containers and no
  host mounts; removed with the containers — `docker volume ls -q | grep -c h2a_v4` = 0.
- Networks: none created (default bridge only) — `docker network ls -q --filter
  name=h2a_v4` returned 0.
- Task ports released: `netstat` LISTEN count on 15438/6398/8000/5173 = 0.
- Maildir, env files (SECRET_KEY), generated retailer passwords, provisioned
  credentials and the COMPLETE runtime directory `C:\Users\Jeff0\MPANGO ERP\_h2a_v4_runtime`
  were deleted — `ls` confirms the directory no longer exists.
- Post-cleanup ref verification: candidate bf574cf9 unchanged; Kilo review 573a288d
  unchanged; V3 diagnostic 45b10060 preserved; origin/product-dev-recovered equals
  c5b66d26b83a0cc6170282de1e2fe281e448b2a8 unchanged (see final delivery record).
