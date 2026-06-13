Directive-ID: u3d-post-merge-parser-probe-r2-2026-06-13
Mode: PARSER_ONLY
Priority: HIGH
Created: 2026-06-13
Status: pending
Target branch: product-dev-recovered
Target-Commit: fb35d473fa782e93632458b9b7ebbea0254fdaa6
Validation-Scope: Parser-only runner probe R2 for U3-D post-merge validation on product-dev-recovered
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-06-13_u3d_post_merge_parser_probe_r2.md

# U3-D Post-Merge Parser Probe R2

Objective:
Verify that the GitHub Actions self-hosted runner can pick up a new CTO directive,
parse the required branch/commit and validation sections, generate a report, and
push that report to `reports/lubuntu-validation` after reports-branch clone retry
hardening.

This is a parser-only probe. It must not execute product validation yet. If this
passes, CTO may issue a separate `VALIDATION_GATE` directive for Leo to run the
actual U3-D post-merge validation commands.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `fb35d473fa782e93632458b9b7ebbea0254fdaa6`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Frontend U3-D focused tests:
   `cd ../frontend && pnpm exec vitest run src/tests/SKUImportModal.test.tsx src/tests/SKUListPage.test.tsx`
2. Frontend production build:
   `cd ../frontend && pnpm run build`
3. Backend U3 import regression from `backend`:
   `poetry run pytest tests/test_u3b1_contract_foundation.py tests/test_u3b2_preview_validate.py tests/test_u3c_import_apply.py -q --tb=short`
4. Scope audit from repository root:
   `git -C .. diff --name-status fb35d473fa782e93632458b9b7ebbea0254fdaa6^..fb35d473fa782e93632458b9b7ebbea0254fdaa6`

Expected evidence:
- PARSER_PREFLIGHT_COUNT: 5
- PARSER_VALIDATION_COUNT: 4
- PARSER_TOTAL_COUNT: 9
- Leo Invoked: false
- Product Code Modified: no.
- Product Branch Pushed: no.
- Commit Hash: `fb35d473fa782e93632458b9b7ebbea0254fdaa6`.

Hard rules:
- Do not invoke Leo in this parser-only probe.
- Do not run product validation commands in this parser-only probe.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write reports manually; run_directive.sh writes the report.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- Mode must be `PARSER_ONLY`.
- Leo Invoked must be `false`.
- PARSER_PREFLIGHT_COUNT must be `5`.
- PARSER_VALIDATION_COUNT must be `4`.
- PARSER_TOTAL_COUNT must be `9`.
