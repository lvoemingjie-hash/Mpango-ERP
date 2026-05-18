# CTO Directive — R6 Path Isolation Verification

Directive-ID: dry-run-B2R-R6-path-isolation
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-18
Target branch: product-dev-recovered
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-18_dry_run_B2R_R6_path_isolation.md

## Objective

Verify that the R6 path isolation architecture works correctly:

1. **Directive repo (directives/)** is only used for reading directives and staging reports
2. **Validation target (validation-target/)** is where Leo executes git commands
3. Leo does NOT modify the directives repo's git working tree
4. Reports are generated deterministically by run_directive.sh, not by Leo
5. Push step uses absolute paths with fallback
6. Final Gate verifies all required fields

## Instructions for Leo

You are executing a VALIDATION_GATE directive with R6 path isolation.

### Working Directory
- You MUST execute all git commands in the VALIDATION_TARGET directory
- The VALIDATION_TARGET path will be provided by the directive runner
- Do NOT execute git commands in the DIRECTIVE_REPO directory

### Git Commands (5 required)
Execute in order in the VALIDATION_TARGET directory:

1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. `git status --short`
5. `git log -1 --oneline`

### Evidence Output Format
After completing all commands, output evidence in this exact format:

```
=== LEO_EVIDENCE ===
VERDICT: PASS_FOR_CTO_REVIEW
COMMANDS_EXECUTED: 5/5
CMD1_FETCH: PASS
CMD2_CHECKOUT: PASS
CMD3_REVPARSE: <hash>
CMD4_STATUS: clean
CMD5_LOG: <commit message>
PRODUCT_CODE_MODIFIED: no
PRODUCT_BRANCH_PUSHED: no
COMMIT_HASH: <full hash>
LATEST_COMMIT: <commit message>
=== LEO_EVIDENCE_END ===
```

### FORBIDDEN
- Do NOT write any report file
- Do NOT git push to any branch
- Do NOT modify any tracked files
- Do NOT execute git checkout/reset/pull in the directives directory
- Do NOT wait for human input

## Acceptance Criteria

- GitHub Actions conclusion = success
- runner_name = mpango-lubuntu-01 (or ivy-20149)
- Leo 5/5 commands passed
- fallbackUsed = false
- Final report exists on reports/lubuntu-validation
- Final Gate all checks passed
- Product code: 0 modifications
- Product branch: 0 pushes
