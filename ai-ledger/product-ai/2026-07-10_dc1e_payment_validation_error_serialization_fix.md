# 2026-07-10 DC-1E Payment Validation Error Serialization Fix

## Scope

- Branch: `opencode/dc1e-payment-validation-error-serialization-fix-2026-07-10`
- Base: `origin/product-dev-recovered` at `3d302222c2700b8f2adbb2d2339732f5255278fd`
- Area: backend global validation exception handling and payment-route regression coverage
- Out of scope: migrations, frontend, deployment, payment/order business logic, ledger semantics, RBAC changes

## Finding

Invalid canonical payment requests can include non-JSON-native values in FastAPI/Pydantic validation error payloads. In the observed DC-1E case, the validation detail included `Decimal` values, which caused response serialization to fail with `TypeError: Object of type Decimal is not JSON serializable` and turned a client validation problem into a 500.

## Fix

- Added `fastapi.encoders.jsonable_encoder` at the global validation error response boundary in `backend/core/error_codes.py`.
- Encoded validation errors before structured logging.
- Encoded the final validation error response content before returning `JSONResponse`.
- Preserved existing status code, error code, and response shape.
- Did not change payment, order, ledger, RBAC, migration, or frontend behavior.

## Regression Coverage

- Added `backend/tests/test_dc1e_validation_error_serialization.py`.
- Route-level regression covers `POST /api/v1/orders/{order_id}/pay?request=test` with invalid payment payload `{"amount": -1, "method": "cash"}` and asserts a JSON 4xx validation response, not a 500.
- Handler-level regression covers nested `Decimal`, `UUID`, and timezone-aware `datetime` values inside `RequestValidationError` details.
- The route test asserts the Decimal serialization exception and traceback text are not exposed in the response.

## GitNexus Impact

- Ran `npx gitnexus analyze` before editing.
- Ran `npx gitnexus impact validation_exception_handler --repo "s6i-backend-full-pytest-infra-alignment-2026-07-05" --depth 3 --include-tests`.
- Reported risk: `LOW`; impacted count: `0`.
- Treated the change as global exception-handler risk despite the low graph impact because all request validation errors pass through this handler.

## Validation Evidence

- `poetry run pytest tests/test_dc1e_validation_error_serialization.py -q`
- Result: `2 passed`
- `poetry run pytest tests/test_phase5_order_payment.py tests/test_s5d5_payment_ledger_runtime_invariant.py tests/test_s5d6_multi_partial_payment_state_machine.py -q`
- Result after disposable Postgres bootstrap: `60 passed, 1 xfailed, 123 warnings`
- `poetry run pytest tests/test_route_authorization_policy.py tests/test_auth_regressions.py -q`
- Result: `36 passed, 4 warnings`

## Local DB Bootstrap Notes

- Started a disposable Postgres 16 container on `127.0.0.1:55448` for DB-backed runtime regressions.
- Initial DB-backed run failed before test execution because no local Postgres host was resolvable.
- `DATABASE_URL=postgresql+asyncpg://...` was rejected by settings validation; reran with standard `postgresql://...`, letting the test harness convert to async internally.
- Applied existing migrations through `016_add_returned_status` with `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, and test-only `REPORTING_USER_PASSWORD`.
- Full `alembic upgrade head` remained blocked by an unrelated existing `017_retailer_prices` asyncpg parameter typing error.
- For validation only, added the existing `018_platform_p0_lifecycle` `public.wholesalers.status` column to the disposable DB so S5D5/S5D6 fixtures could run. No repository migration or product schema file was changed.

## Verdict

DC-1E is fixed at the global validation error serialization boundary. The canonical invalid payment route now returns a JSON validation response instead of failing with Decimal serialization and leaking a 500 path.
