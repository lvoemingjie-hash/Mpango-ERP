# P18-E Controlled Action Request Queue -- Ledger

**Date:** 2026-06-24
**Branch:** `codex/platform-p18e-action-request-queue-2026-06-24`
**Base:** P18-D branch tip `e2343c4`.
**Report path:** `ai-ledger/platform/2026-06-24_p18e_action_request_queue.md`.

**Statement:** Request queue only. This phase exposes the current in-memory P18
controlled-action request store as a platform operator queue. It does not execute
any controlled action, does not mutate tenant lifecycle, operational flags,
registry, provisioning, backup, or tenant business data, and does not add
migrations or persistent storage.

**Scope:** Backend schema/service/route for `GET /api/v1/platform/p18/actions/requests`;
frontend service/types/page rendering for the queue; backend and frontend tests.

**Safety:** Queue items reuse already-redacted `ActionRequestResponse` objects.
Raw action_type, reason, idempotency_key, requested_state, correlation_id, and
metadata values are not exposed. The queue response carries `executed=false` and
`storage=memory`.

**Risk:** MEDIUM / platform-runtime additive, contained to P18. No product
business paths, auth/RBAC rewrite, migrations, payment/billing, or product branch
changes.

**Modified files:** `backend/api/v1/platform/p18/schemas.py`,
`backend/api/v1/platform/p18/services.py`, `backend/api/v1/platform/p18/routes.py`,
`backend/tests/test_platform_p18_controlled_actions.py`,
`frontend/src/types/platformControlledActions.ts`, `frontend/src/services/platformApi.ts`,
`frontend/src/pages/platform/PlatformControlledActionsPage.tsx`,
`frontend/src/pages/platform/__tests__/PlatformControlledActionsPage.test.tsx`, and this ledger.

**Tests:** Backend P18/P18-D: 64 passed. Frontend P18 page: 9 passed. Backend
regression P10 + P17 + P15: 208 passed.

**Checks:** `git diff --check` PASS before commit on the working tree. Non-ASCII
added-line scan: 0 hits. detect-secrets scan on changed files: clean. Forbidden
path audit: P18 platform files plus platform ledger only; no migrations, auth/RBAC
rewrite, product business paths, payment/billing paths, or product branch paths.

**GitNexus:** Pending final post-commit analyze/detect_changes. Expected risk is
MEDIUM/HIGH platform-runtime additive, contained to P18 request queue.

**Blockers:** None known before final post-commit gate.
