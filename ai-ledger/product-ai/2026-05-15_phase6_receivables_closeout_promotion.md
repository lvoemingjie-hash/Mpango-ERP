# Phase 6 Receivables Closeout Promotion

Date: 2026-05-15
Promotion branch: `product-dev-recovered`
Promoted source: `origin/codex/phase6-3a-receivables-contract-2026-05-14`
Source commit: `5df6098f5a6f46bfb77a0ed6d03383d750446f9d`

## Scope

This closeout promotes Phase 6.2 and Phase 6.3A receivables work into the current product baseline.

Included changes:

- Read-only receivables visibility service.
- Finance API receivables endpoints.
- Typed receivables response schemas.
- Contract stabilization tests for frontend readiness.
- Product AI ledgers for Phase 6.2 and Phase 6.3A.

Not included:

- No receivables write path.
- No payment semantics change.
- No migration change.
- No frontend implementation.
- No platform architecture change.

## Remote Validation Evidence

Leo headless DB-capable validation passed on Lubuntu.

- GitHub Actions run: `25903789407`
- Runner: `ivy-20149`
- Report commit: `539aba6`
- Report path after path correction: `docs/ai-reports/lubuntu/2026-05-15_phase6_3a_db_capable_validation.md`
- Report path correction commit: `fd3fcbf`

Remote validation result:

- App smoke: `106` routes loaded.
- Receivables service/API: `38 passed, 0 failed, 0 skipped`.
- Phase 5/6 payment regression: `53 passed, 1 xfailed, 0 failed, 0 skipped`.
- DB schema contract: `40 passed, 0 failed, 0 skipped`.
- Total targeted validation: `131 passed, 1 xfailed, 0 failed, 0 skipped`.

The updated Leo DB-capable skip policy was applied. No skipped DB/live/schema tests remained.

## Local Promotion Evidence

Promotion worktree:

`C:\Users\Jeff0\MPANGO ERP\phase6-closeout-promotion-2026-05-15`

Merge command:

```bash
git merge --no-ff --no-commit origin/codex/phase6-3a-receivables-contract-2026-05-14
```

Merge result:

- Automatic merge completed without conflicts.
- Merge was intentionally held before commit for verification.

Local targeted tests:

```bash
poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short
```

Result:

`38 passed, 0 failed`

```bash
REPORTING_USER_PASSWORD=<redacted> poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

Result:

`53 passed, 1 xfailed, 0 failed`

```bash
MPANGO_ENV=test REPORTING_USER_PASSWORD=<redacted> SECRET_KEY=<redacted> CORS_ORIGINS='["http://localhost:3000"]' DEFAULT_TENANT_SCHEMA=t_dev PYTHONIOENCODING=utf-8 poetry run python -c "from main import app; print(len(app.routes))"
```

Result:

`106`

Local environment notes:

- The first local app-smoke attempt exposed an incomplete Poetry virtualenv created by parallel test execution.
- `poetry install --no-root` restored the declared dependencies, including `pyyaml`.
- Windows stdout required `PYTHONIOENCODING=utf-8` because startup logs include Unicode status markers.
- These were local environment issues, not product code failures.

## CTO Decision

Phase 6 receivables closeout is promotion-ready.

The promoted work is read-only and does not change accounting or payment write semantics. It stabilizes receivables visibility and API response contracts so the frontend can consume receivables data safely in the MVP track.
