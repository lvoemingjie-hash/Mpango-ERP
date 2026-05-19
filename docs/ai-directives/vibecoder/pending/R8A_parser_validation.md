Directive-ID: R8A-parser-validation
Mode: INVENTORY_ONLY
Priority: HIGH
Created: 2026-05-19T09:30:00+08:00
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/R8A_parser_validation.md

Required branch/commit checks:
1. git fetch origin --prune
2. git checkout origin/product-dev-recovered --detach
3. git rev-parse HEAD
4. git status --short
5. git log -1 --oneline

Required validation commands:
1. cd backend && poetry install --no-root 2>&1 | tail -3
2. cd backend && python -c "from app.main import app; print(f'routes={len(app.routes)}')"
3. cd backend && poetry run pytest tests/api/ -q 2>&1 | tail -10
4. cd backend && poetry run pytest tests/test_schema_contract.py -q 2>&1 | tail -10

Expected evidence:
- PREFLIGHT: 5/5
- VALIDATION: 4/4
- TOTAL: 9/9
- APP_IMPORT_SMOKE: route count > 0
- RECEIVABLES_SUITE: passed count
- SCHEMA_CONTRACT: passed count

Hard rules:
- Do NOT modify any tracked files
- Do NOT git push to any branch
- Do NOT skip any validation command
- Parser-only test: Leo must NOT be invoked
