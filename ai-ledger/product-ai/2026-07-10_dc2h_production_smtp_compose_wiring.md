# DC-2H Production SMTP Compose Wiring

## Scope

- Wire the U6-K production SMTP environment keys into `docker-compose.prod.yml`.
- Keep all SMTP values as environment-variable references only.
- Make the production compose path fail closed if SMTP wiring is incomplete.
- Add a static regression test for the compose wiring.
- Do not change backend SMTP logic, auth, onboarding flow, migrations, frontend, VPS, or deployment state.

## Files Changed

- `docker-compose.prod.yml`
- `backend/tests/test_dc2h_production_smtp_compose_wiring.py`
- `ai-ledger/product-ai/2026-07-10_dc2h_production_smtp_compose_wiring.md`

## Implementation Notes

- Added explicit backend environment forwarding for:
  - `EMAIL_PROVIDER`
  - `EMAIL_DELIVERY_MODE`
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USER`
  - `SMTP_PASSWORD`
  - `EMAIL_FROM`
  - `SMTP_STARTTLS`
  - `SMTP_USE_TLS`
- Every SMTP value in `docker-compose.prod.yml` now uses a `${VARIABLE:?VARIABLE must be set}` reference.
- `SMTP_PASSWORD` has no default and no literal value.
- The wiring is compose-only. No SMTP host, user, mailbox, password, port credential, token, or provider literal is committed.

## Validation Results

- `poetry run pytest tests/test_dc2h_production_smtp_compose_wiring.py -q`: `3 passed`.
- `docker compose -f docker-compose.prod.yml --env-file <temporary placeholder env> config -q`: passed with a secrets-free placeholder env outside the repo.
- fail-closed compose evidence with missing `SMTP_PASSWORD`: passed; `docker compose ... config -q` failed with `required variable SMTP_PASSWORD is missing a value: SMTP_PASSWORD must be set`.
- `git diff --check`: passed.
- ASCII/mojibake scans: passed on added diff lines; no mojibake matches in modified files. The compose file still contains two pre-existing non-ASCII em dashes in unchanged comments.
- `poetry run pre-commit run --config ..\.pre-commit-config.yaml --files ..\docker-compose.prod.yml tests\test_dc2h_production_smtp_compose_wiring.py ..\ai-ledger\product-ai\2026-07-10_dc2h_production_smtp_compose_wiring.md`: passed, including `detect-secrets`.
- `npx gitnexus analyze`: already up to date.
- `npx gitnexus status`: indexed commit `e022f21`, current commit `e022f21`, status up to date.

## Verdict

`PASS_FOR_CTO_REVIEW`
