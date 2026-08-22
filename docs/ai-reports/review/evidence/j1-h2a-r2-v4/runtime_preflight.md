# V4 runtime preflight (completed before the frozen run)

- Candidate checkout bf574cf9 (git tree 83eb1b09c6eea7145b3d5069323ee2ffb54cc63d); tracked files clean at pre-gate.
- Fresh task stack: h2a_v4_pg16 (postgres:16-alpine, 127.0.0.1:15438) + h2a_v4_redis7 (redis:7-alpine, 127.0.0.1:6398); new containers, empty volumes.
- Fresh DB test_h2a_v4 (owner tester); Alembic base -> 037_payment_declarations_schema.
- Backend: candidate main:app via uvicorn 127.0.0.1:8000, MPANGO_ENV=staging (real JWT); /health 200 healthy.
- Frontend: candidate vite dev 127.0.0.1:5173 (/api proxied to 8000); HTTP 200.
- Frozen harness: spec blob 9c2e2bf105eea611eac79c6a9d10974258aa181c, config blob
  74dd70171ce1b103af9556fee6f1799a4c3838e5, committed at e2be8825 BEFORE the run;
  disk bytes == committed blob bytes verified immediately BEFORE execution.
- Pre-run gates: auth matrix W1/W2 (admin holds invitations:create + retailers:deactivate);
  collected node list = 19 (J00 credential gate + J01-J18); secrets scan of the harness: 0 hits.
- The @playwright/test runner (1.59.1, chromium headless shell v1217) resolved through an
  untracked, gitignored node_modules junction in the evidence directory; the committed spec
  and config blobs themselves were executed in place without copying or editing.
