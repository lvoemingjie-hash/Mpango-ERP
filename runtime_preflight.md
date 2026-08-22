# Runtime Preflight

- Candidate SHA: bf574cf9b061f7897eb68cbe92a82ce1201e49f0
- Candidate parent: 78f88875
- Protected baseline: c5b66d26b83a0cc6170282de1e2fe281e448b2a8 (ancestor verified)
- Kilo review: 573a288d346fb78b26ccd0636028148c0f39ecad
- Backend: main:app on port 8091 (MPANGO_ENV=staging)
- Frontend: SPA on port 3091
- PostgreSQL: 16.15 on port 15438 (fresh, task-owned)
- Redis: 7-alpine on port 16381 (fresh, task-owned)
- Alembic head: 037_payment_declarations_schema
- Workers: 1 (sequential)
- Retries: 0
- Browser: chromium (Playwright 1.62.0)
- No prior identities, database, maildir, or J1-R0 volume reused
