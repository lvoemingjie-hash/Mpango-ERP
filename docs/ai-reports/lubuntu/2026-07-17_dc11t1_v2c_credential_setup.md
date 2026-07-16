# DC-11T1-V2C Credential Setup Classification

Date: 2026-07-17

## Verdict

`PASS_DC11T1_V2C_CLASSIFICATION_COMPLETE`

The 48 V0 U6I0-I6 credential-setup failures are fully classified:

| Classification | Count |
| --- | ---: |
| TEST_INFRASTRUCTURE | 41 |
| STALE_TEST_CONTRACT | 7 |
| CURRENT_PRODUCT_DEFECT | 0 |
| ENVIRONMENT_GATED | 0 |
| Total | 48 |

Accounting gap: zero.

## Scope

- Product baseline: `7a972d1dca944db3476c405b807ddb5313f5ef95`
- V0 inventory source: `67d2696b1b89cbf1ed6cda686797d395b8ef7801`
- V0 result: 25 failed, 23 errors.
- Files: U6I0 through U6I6 owner credential setup contract, schema, issue, consume, first-admin/RBAC, endpoint, and closeout tests.
- No source code, tests, migrations, frontend, configuration, dependencies, or lockfiles were changed.

## Fresh Infrastructure

Each file and the grouped matrix ran with a new disposable PostgreSQL 16 and Redis 7 environment. Alembic current/head was the single `034_platform_operators` head. The gate bootstrapped fresh `t_test` and `t_dev` schemas and verified cleanup of containers, volumes, and networks.

## Independent Results

| File | V0 nodes | Fresh isolated result | V0 classification |
| --- | ---: | --- | --- |
| U6I0 contract | 3 | 6 passed, 3 stale failures | 3 STALE_TEST_CONTRACT |
| U6I1 schema | 2 | 5 passed, 2 stale failures | 2 STALE_TEST_CONTRACT |
| U6I2 token issue | 14 | 13 passed, 1 stale failure | 13 TEST_INFRASTRUCTURE, 1 STALE_TEST_CONTRACT |
| U6I3 token consume | 12 | 12 passed | 12 TEST_INFRASTRUCTURE |
| U6I4 first admin/RBAC | 6 | 9 passed, including all 6 V0 nodes | 6 TEST_INFRASTRUCTURE |
| U6I5 public endpoint | 10 | 10 passed | 10 TEST_INFRASTRUCTURE |
| U6I6 closeout | 1 | 1 stale failure after successful provisioning | 1 STALE_TEST_CONTRACT |

The seven-file grouped run collected 62 tests and produced `55 passed, 7 failed, 0 errors`. The failed set was identical to the seven stale contracts. All 41 V0 nodes classified as TEST_INFRASTRUCTURE passed together.

The passing behavior covers:

- eligibility checks and hash-only setup-token issuance
- expired, used, revoked, and duplicate-token behavior
- one-time token consumption and password hashing
- first tenant admin, role, permission, and mapping creation
- idempotent retry without duplicate RBAC rows
- setup-credential endpoint success and neutral invalid-token failure
- replay resistance and query-string rejection
- no raw setup-token or password-hash disclosure

## Full-Suite Failure Mechanism

R4 reports the first U6I2 and U6I3 database nodes with:

`Future attached to a different loop`

A fresh causal run used this order:

1. initialize the async pool through one persistence test
2. invoke the old P21 migration tests that call Alembic directly
3. run U6I0-I6 in the same pytest process

Result: 69 collected, 12 passed, 57 failed. All async U6I2-I6 tests failed with:

`RuntimeError: There is no current event loop in thread 'MainThread'.`

Static contract tests remained executable. Without the polluted order, all current credential behavior tests pass. The 41 current-behavior V0 nodes are therefore TEST_INFRASTRUCTURE, not product defects.

## Stale Contract Evidence

### Branch-scope gates

These nodes assert the exact changed-file set of their original U6I0 or U6I1 feature branch:

- `test_branch_changes_only_contract_doc_and_static_test`
- `test_no_runtime_code_files_changed_in_contract_branch`
- `test_branch_changes_only_allowed_schema_foundation_files`

They are feature-branch CI gates and are not meaningful on the integrated product baseline.

### Endpoint-absence gates

These nodes require the owner setup endpoint/service not to exist:

- `test_contract_locks_public_endpoint_disclosure_boundary`
- `test_no_public_endpoint_or_query_string_token_support`

The endpoint is intentionally implemented at `api/v1/auth.py` lines 651-655. Current tests prove body-only token transport and reject query-string setup tokens. The absence assertions predate U6I5.

### Historical Alembic head

`test_alembic_head_is_owner_credential_setup_tokens` pins head `028_owner_credential_setup_tokens`. The integrated baseline has the single head `034_platform_operators`; migration 028 remains in the chain.

### Pre-orchestration state machine

The U6I6 closeout node expects verify-email to leave registration status at `email_verified`. Its own fresh run proves the current backend successfully provisions the tenant and returns `active`. U6-L intentionally moved provisioning into the verify-email orchestration. The old intermediate-state assertion is stale.

## Accounting

| File | TEST_INFRASTRUCTURE | STALE_TEST_CONTRACT | Total |
| --- | ---: | ---: | ---: |
| U6I0 | 0 | 3 | 3 |
| U6I1 | 0 | 2 | 2 |
| U6I2 | 13 | 1 | 14 |
| U6I3 | 12 | 0 | 12 |
| U6I4 | 6 | 0 | 6 |
| U6I5 | 10 | 0 | 10 |
| U6I6 | 0 | 1 | 1 |
| Total | 41 | 7 | 48 |

`41 + 7 + 0 + 0 = 48`; gap = 0.

The companion CSV preserves every exact V0 node ID. No node was normalized, skipped, hidden, or converted to xfail.

## CTO Decision

1. No CURRENT_PRODUCT_DEFECT is confirmed in the owner credential setup slice.
2. The seven stale gates should be updated narrowly to current integrated contracts after classification; no batch skip or xfail is acceptable.
3. The Alembic/event-loop problem remains a real test-harness defect and belongs to DC-11T0 infrastructure correction.
4. Proceed to U6K/U6L SMTP and orchestration, then DC3B credential recovery, before issuing an AUTH_ONBOARDING-wide defect verdict.

## Compliance

- No credentials, JWTs, raw tokens, emails, SMTP values, or database URLs are recorded.
- No protected branch was pushed.
- No release tag was created or moved.
- Disposable Docker resources were removed after every run.
