# 2026-07-10 DC-1G Retailer Binding Outstanding Balance Fix

## Scope

- Branch: `opencode/dc1g-retailer-binding-outstanding-balance-fix-2026-07-10`
- Base: `origin/product-dev-recovered` at `bce3dcfc72b459a6a5ca429874ae3cb6be794b88`
- Area: public retailer registration binding creation
- Out of scope: migrations, frontend, deployment, order/payment/ledger semantics, RBAC/auth changes, manual DB repair

## Root Cause

- `backend/models/binding.py` did not map `public.wholesaler_retailer_bindings.outstanding_balance`.
- `backend/alembic/versions/005_phase_b5_payments_minimal_loop.py` adds `outstanding_balance NUMERIC(12, 2) NOT NULL`, backfills through a temporary server default, then removes the server default.
- `backend/repositories/binding_repository.py::BindingRepository.create()` created binding rows without explicitly setting `outstanding_balance`.
- Runtime `POST /api/v1/retailers/register` can therefore attempt to insert a public binding with `NULL` outstanding balance and hit a NOT NULL violation, surfacing as a 500.

## Fix

- Added `outstanding_balance` to `WholesalerRetailerBinding` as `Numeric(12, 2)`, `nullable=False`, with Python default `Decimal("0.00")`.
- Updated `BindingRepository.create()` to explicitly set `outstanding_balance=Decimal("0.00")`.
- Preserved existing status and unique binding semantics.
- No migration added. The DB column already exists in migration `005`.
- No payment, ledger, order, RBAC, auth, frontend, or deploy changes.

## Regression Coverage

- Added `backend/tests/test_dc1g_retailer_registration_binding_balance.py`.
- Repository regression creates a public binding through `BindingRepository.create()` against a DB column with NOT NULL and no server default, then asserts `Decimal("0.00")` and no `IntegrityError`.
- Registration regression creates an invitation and calls `RetailerService.register_with_invitation()`, then asserts the binding is created with `Decimal("0.00")` and the registration path does not raise a 500-producing DB error.
- Tests use explicit system scope for public registration/setup, matching the production registration flow.

## GitNexus Impact

- Ran `npx gitnexus impact WholesalerRetailerBinding --repo "s6i-backend-full-pytest-infra-alignment-2026-07-05" --depth 3 --include-tests` before editing.
- Result: `LOW`, impacted count `11`.
- The fully qualified `BindingRepository.create` target was not found by GitNexus. The model impact graph identified `backend/repositories/binding_repository.py:create` as a direct dependent. A generic `create` query resolved to an unrelated platform function, so it was not used for risk assessment.
- Proceeded because the production change is strictly additive ORM field mapping plus explicit create default.

## Validation Evidence

- `poetry run pytest tests/test_dc1g_retailer_registration_binding_balance.py -q`
- Result: `2 passed, 1 warning`
- `poetry run pytest tests/test_payments_api.py tests/test_phase5_order_payment.py -q`
- Result: `57 passed, 1 xfailed, 58 warnings`
- `poetry run pytest tests/test_route_authorization_policy.py tests/test_auth_regressions.py -q`
- Result: `36 passed, 4 warnings`
- `poetry run python -m py_compile models/binding.py repositories/binding_repository.py`
- Result: passed
- `git diff --check`
- Result: passed with LF-to-CRLF working-copy warnings only

## Verdict

DC-1G is fixed locally. Retailer registration binding creation now sends an explicit zero outstanding balance, closing the DC-1F NOT NULL 500 path without changing payment or ledger semantics.
