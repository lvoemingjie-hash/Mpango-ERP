# CTO Directive — R7 Evidence Parsing Verification

Directive-ID: dry-run-B2R-R7-evidence-parsing
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-18
Target branch: product-dev-recovered
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-18_dry_run_B2R_R7_evidence_parsing.md

## Objective

Verify v3.4 evidence parsing fix — jq-based text extraction + clean grep.

## Instructions for Leo

Execute these 5 git commands in VALIDATION_TARGET directory:

1. git fetch origin --prune
2. git checkout origin/product-dev-recovered --detach
3. git rev-parse HEAD
4. git status --short
5. git log -1 --oneline

### Evidence Output Format
Output evidence in this exact format:

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

## Acceptance Criteria

- GitHub Actions conclusion = success
- Leo 5/5 commands passed
- fallbackUsed = false
- All evidence fields correctly parsed (no cross-field contamination)
- Final report exists on reports/lubuntu-validation
- Final Gate all checks passed
