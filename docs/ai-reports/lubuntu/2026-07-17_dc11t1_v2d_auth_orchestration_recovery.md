# DC-11T1-V2D Auth Orchestration and Recovery Classification

Date: 2026-07-17

## Verdict

`PASS_DC11T1_AUTH_ONBOARDING_CLASSIFICATION_COMPLETE`

The final 21 AUTH_ONBOARDING V0 nodes are classified as TEST_INFRASTRUCTURE. Combined with V2A, V2B, and V2C, all 135 AUTH_ONBOARDING nodes now have evidence-backed, gap-zero classifications.

## V2D Classification

| Classification | Count |
| --- | ---: |
| TEST_INFRASTRUCTURE | 21 |
| STALE_TEST_CONTRACT | 0 |
| CURRENT_PRODUCT_DEFECT | 0 |
| ENVIRONMENT_GATED | 0 |
| Total | 21 |

V2D accounting gap: zero.

## Scope

- Product baseline: `7a972d1dca944db3476c405b807ddb5313f5ef95`
- V0 inventory source: `67d2696b1b89cbf1ed6cda686797d395b8ef7801`
- V0 observed result: 9 failed, 12 errors.
- Files:
  - `tests/test_u6k_production_smtp_email_delivery.py`
  - `tests/test_u6l_email_verified_onboarding_orchestration.py`
  - `tests/test_dc3b_credential_recovery_backend.py`
- No product code, tests, migrations, frontend, configuration, dependencies, or lockfiles were changed.

## Fresh Infrastructure Results

Every run used a new PostgreSQL 16 and Redis 7 environment, single Alembic head `034_platform_operators`, and fresh tenant schemas. Disposable containers, networks, and volumes were removed after each run.

| File | V0 nodes | Isolated result | Classification |
| --- | ---: | --- | --- |
| U6K production SMTP | 5 | 5 passed | 5 TEST_INFRASTRUCTURE |
| U6L verified-email orchestration | 7 | 7 passed | 7 TEST_INFRASTRUCTURE |
| DC3B credential recovery | 9 | 15 passed, including all 9 V0 nodes | 9 TEST_INFRASTRUCTURE |

The three-file grouped run collected 27 tests and produced `27 passed, 0 failed, 0 errors`.

## Product Behavior Proven

The green tests cover:

- production SMTP configuration fails closed when incomplete
- successful SMTP signup stores only token hashes
- SMTP send failure rolls back registration and token writes
- duplicate live email remains neutral and sends no extra mail
- verified email provisions tenant and issues one owner setup token
- setup email failure preserves a durable retry anchor
- retry reconciles the same tenant without duplicate rows
- forgot-password is neutral for existing and unknown emails
- reset tokens are hash-only, single-use, expiring, and revocable
- valid reset updates the password while invalid states fail neutrally
- query-string reset tokens are rejected
- all tenant-local copies for the same identity are updated consistently
- login and tenant selection succeed after reset
- public responses expose no internal IDs, raw tokens, or hashes

No current product defect was reproduced in these paths.

## Causal Failure Reproduction

The fresh causal sequence was:

1. initialize the async DB pool
2. run old P21 migration tests that call Alembic directly
3. run U6K, U6L, and DC3B in the same pytest process

Result: 34 collected, 1 passed, 33 failed. The primer passed; all six migration tests and all 27 auth tests failed after the current event loop was removed. The repeated exception was:

`RuntimeError: There is no current event loop in thread 'MainThread'.`

Without that ordering defect, all 27 tests pass together. The R4 9 FAILED plus 12 ERROR split is pytest phase placement; it does not represent two product root causes.

## Full AUTH_ONBOARDING Rollup

| Slice | TEST_INFRASTRUCTURE | STALE_TEST_CONTRACT | CURRENT_PRODUCT_DEFECT | ENVIRONMENT_GATED | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| V2A auth entry U6C-F | 34 | 3 | 0 | 0 | 37 |
| V2B provisioning U6H1-H3 | 26 | 3 | 0 | 0 | 29 |
| V2C credential setup U6I0-I6 | 41 | 7 | 0 | 0 | 48 |
| V2D SMTP/orchestration/recovery | 21 | 0 | 0 | 0 | 21 |
| Total | 122 | 13 | 0 | 0 | 135 |

`122 + 13 + 0 + 0 = 135`; gap = 0.

## Confirmed Code and Test Issues

### Test infrastructure code issue

Migration tests invoke Alembic in-process without preserving the pytest session event loop. Once an async SQLAlchemy pool is bound to that loop, the migration call closes or replaces it. Later async tests reuse loop-bound connections and fail before product assertions.

This is a real repository test-harness defect. It should be fixed through the dedicated DC-11T0 infrastructure branch, not hidden through skips or xfails.

### Stale integrated-contract tests

Thirteen feature-slice tests still assert historical branch file sets, old Alembic heads, absent endpoints, pre-U6-L auth/provisioning boundaries, or the old intermediate onboarding state. These are test-code defects and should be updated narrowly after the domain classification is accepted.

### Product defects

No CURRENT_PRODUCT_DEFECT was reproduced among the 135 AUTH_ONBOARDING V0 nodes. This conclusion applies to this domain and baseline only; it does not close the remaining non-auth V0 inventory or replace deployment runtime testing.

## CTO Decision

1. AUTH_ONBOARDING V0 failure classification is complete and gap-free.
2. Do not block product delivery on these 135 nodes as if they were current product defects.
3. Do not declare the full repository green: merge and validate the deterministic test-infrastructure correction, then update the 13 stale tests without weakening assertions.
4. Continue the remaining BUSINESS_FINANCE and MIGRATION_REPORTING classification before a repository-wide defect verdict.

## Compliance

- No credentials, JWTs, raw tokens, emails, SMTP values, or database URLs are recorded.
- No protected branch was pushed.
- No release tag was created or moved.
- Disposable Docker resources were removed after every run.
