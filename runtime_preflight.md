# V3 runtime preflight

- Candidate checkout: bf574cf9 (git tree 83eb1b09c6eea7145b3d5069323ee2ffb54cc63d), tracked files clean.
- Fresh task stack: h2a_v3_pg16 (postgres:16-alpine, 127.0.0.1:15438) + h2a_v3_redis7 (redis:7-alpine, 127.0.0.1:6398), new containers, empty volumes.
- Fresh DB test_h2a_v3 (owner tester); Alembic upgraded base -> 037_payment_declarations_schema (DC-2M2 preflight OK).
- Backend: candidate main:app via uvicorn 127.0.0.1:8000, MPANGO_ENV=staging (real JWT); /health 200 healthy.
- Frontend: candidate vite dev server 127.0.0.1:5173 (/api proxied to 8000); HTTP 200.
- Playwright: @playwright/test 1.59.1 + chromium headless shell v1217 installed locally for this task.
- Pre-gates: (a) auth matrix W1/W2 API login + permissions (invitations:create, retailers:deactivate) verified;
  (b) collected node list: 18 nodes (J01..J18), zero skip/only annotations;
  (c) source-integrity hash recorded before runtime.
- Mail sink: in-process dev sink dumped by the task-owned launcher to the task maildir every 500 ms
  (launcher and maildir are NOT committed; hard rule 3).
