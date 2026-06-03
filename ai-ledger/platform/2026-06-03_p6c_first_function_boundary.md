# P6-C First Platform Function Implementation Boundary

**Date**: 2026-06-03
**Agent**: claude
**Branch**: codex/platform-p6bcd-first-function-readiness-2026-06-03
**Base**: platform-dev (df709ff)
**Phase**: P6-C

---

## Objective

Define the strict boundary for the first platform function implementation. This document establishes what paths, patterns, and artifacts are allowed for the first real platform function — and what is explicitly forbidden. No implementation code is produced here; this is a boundary specification only.

## Implementation Allowlist

### Allowed Paths (First Function)

| Path Pattern | Purpose | Constraint |
|-------------|---------|------------|
| `scripts/platform_*.py` | New platform harness script | Must have matching `scripts/test_platform_*.py` |
| `scripts/test_platform_*.py` | Test suite for new script | Must achieve 100% pass |
| `ai-ledger/platform/*.md` | Mission and evidence ledgers | Must follow `<date>_<slice>_<type>.md` naming |
| `ai-ledger/platform/*.json` | Mission and result JSON artifacts | Must pass `platform_agent_mission_gate` |
| `ai-ledger/platform/*.jsonl` | Events JSONL artifacts | Must be sanitized (`"redacted": true`) |

### Allowed Function Categories (First Function)

The first platform function MUST fall into one of these categories:

1. **Platform health check** — A script that runs all existing gates and produces a single pass/fail summary with risk assessment.
2. **Platform function registry** — A script that enumerates all platform harness scripts, their test pairings, and phase provenance.
3. **Platform diff auditor** — A script that validates a diff against forbidden paths and allowed patterns before commit.

> The first function is deliberately scoped to a read-only or validation-only operation over the existing harness. It does not modify product code, databases, or external services.

### Allowed Script Patterns

```
platform_<noun>_<verb>.py          # e.g., platform_function_registry.py
platform_<domain>_<action>.py      # e.g., platform_health_check.py
platform_<scope>_<gate>.py         # e.g., platform_diff_auditor.py
```

### Required Script Contract

Every new platform script MUST:

1. Accept `--repo <path>` as the first positional argument.
2. Support `--json` for machine-readable output.
3. Exit 0 on success, non-zero on failure.
4. Have a matching test suite with ≥80% branch coverage.
5. Be registered in the harness index via its ledger artifact.

## Forbidden Paths (Explicit)

These paths are **never** allowed for platform function implementation:

| Path | Reason |
|------|--------|
| `backend/` | Product runtime code |
| `frontend/` | Product runtime code |
| `product-dev-recovered/` | Product runtime code |
| `.github/` | CI/CD infrastructure |
| `.claude/` | Agent configuration |
| `docs/ai/` | Governance documents |
| Any path containing `auth` | Security domain |
| Any path containing `RBAC` | Security domain |
| Any path containing `tenancy` | Security domain |
| Any path containing `migration` | Data domain |
| Any path containing `payment` | Financial domain |
| Any path containing `session` | Security domain |

## Boundary Enforcement

The forbidden path list is enforced by:

1. **`platform_agent_mission_gate.py`** — Validates mission contracts.
2. **`platform_run_packet_gate.py`** — Validates run packets before execution.
3. **`platform_agent_run_bundle_gate.py`** — Validates artifact bundles.
4. **This document (P6-C)** — Defines the allowlist for first-function scope.
5. **Batch readiness ledger (P6-D)** — Confirms compliance at batch level.

## Implementation Sequence

| Step | Action | Gate |
|------|--------|------|
| 1 | Select first function from allowed categories | P6-C boundary check |
| 2 | Create mission JSON with P6-D phase | `platform_agent_mission_gate` |
| 3 | Implement script + test suite | Harness index pairing |
| 4 | Run full platform test suite | 369+ tests all pass |
| 5 | Run forbidden path audit | Zero violations |
| 6 | Run GitNexus analyze + detect_changes | LOW/MEDIUM risk only |
| 7 | Produce evidence artifacts | Result + events + ledger |
| 8 | Batch readiness check | P6-D compliance |

## Risk

LOW. This is a boundary specification document only. No code is produced or executed beyond documentation.
