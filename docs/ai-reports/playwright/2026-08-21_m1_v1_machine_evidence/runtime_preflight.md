# M1-V1 Runtime Preflight

- Product: detached worktree at c5b66d26b83a0cc6170282de1e2fe281e448b2a8
  (verified origin/product-dev-recovered == c5b66d26; merge parents
  fc8abdf3 + cbcecbf2; refs recorded, no drift).
- Task-owned runtime, COMPOSE_PROJECT_NAME-equivalent: m1v1pw_2026-08-21.
  Deviation note: the repo docker-compose pins postgres:15 while the task
  mandates PG16, so task-owned `docker run` containers were used instead
  (names m1v1pw_postgres_1 / m1v1pw_redis_1) with fresh empty volumes and
  loopback-only port mappings (15445 pg / 26402 redis). No J1-R0 retained
  volumes, bridge identities or old databases were reused.
- Auth signing material: one task-exclusive random value held in a
  task-private file (never printed, never committed; deleted in cleanup).
- MPANGO_ENV=staging, real JwtAuthStrategy.
- Alembic: upgraded to the single head 037_payment_declarations_schema
  (29 public tables) on the empty database.
- Backend: production entrypoint backend/main.py (registers
  MpangoAPIException handlers before configure_app) on 127.0.0.1:8000.
  Initial launcher mistake (api.app:app, handlers unregistered -> client
  login 500s) was diagnosed and corrected to main:app before any gate run;
  disclosed as infra fix, zero product edits.
- Frontend: vite dev on 127.0.0.1:5173, /api proxy to :8000.
- Health: /health/live 200, /health/ready 200, SPA shell 200,
  proxied passwordless signup 202.
- Task maildir: staging dev_sink exposed only to loopback via a runtime
  route (/__task_mail) added by the task launcher process; the launcher
  lives outside the product worktree and adds zero product source changes.
