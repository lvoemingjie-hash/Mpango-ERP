# Platform Harness Index

- **Branch:** codex/platform-p3a-governed-harness-index-2026-05-28
- **Commit:** 34cee19
- **Generated output path:** ai-ledger/platform/2026-05-28_p3a_platform_harness_index.md

## Harness Scripts

| # | Script | Test |
|---|--------|------|
| 1 | `scripts/platform_agent_artifact_collector.py` | `scripts/test_platform_agent_artifact_collector.py` |
| 2 | `scripts/platform_agent_mission_gate.py` | `scripts/test_platform_agent_mission_gate.py` |
| 3 | `scripts/platform_agent_preflight.py` | `scripts/test_platform_agent_preflight.py` |
| 4 | `scripts/platform_agent_run_bundle_gate.py` | `scripts/test_platform_agent_run_bundle_gate.py` |
| 5 | `scripts/platform_agent_timeout_watchdog.py` | `scripts/test_platform_agent_timeout_watchdog.py` |
| 6 | `scripts/platform_batch_review_packet.py` | `scripts/test_platform_batch_review_packet.py` |
| 7 | `scripts/platform_directive_gate.py` | `scripts/test_platform_directive_gate.py` |
| 8 | `scripts/platform_harness_index.py` | `scripts/test_platform_harness_index.py` |
| 9 | `scripts/platform_mission_worker_bridge.py` | `scripts/test_platform_mission_worker_bridge.py` |
| 10 | `scripts/platform_opencode_worker_gate.py` | `scripts/test_platform_opencode_worker_gate.py` |
| 11 | `scripts/platform_remote_runner_packet.py` | `scripts/test_platform_remote_runner_packet.py` |
| 12 | `scripts/platform_run_evidence_bundle.py` | `scripts/test_platform_run_evidence_bundle.py` |
| 13 | `scripts/platform_run_packet_gate.py` | `scripts/test_platform_run_packet_gate.py` |
| 14 | `scripts/platform_runner_gate.py` | `scripts/test_platform_runner_gate.py` |
| 15 | `scripts/platform_task_execution_bridge.py` | `scripts/test_platform_task_execution_bridge.py` |
| 16 | `scripts/platform_toolchain_gate.py` | `scripts/test_platform_toolchain_gate.py` |

## Platform Ledgers

- `ai-ledger/platform/2026-04-07_clawd_code_auto_boot_check.md`
- `ai-ledger/platform/2026-04-07_opencode_auto_boot_check.md`
- `ai-ledger/platform/2026-04-07_p0_first_implementation_slice.md`
- `ai-ledger/platform/2026-04-07_p0_information_model_draft.md`
- `ai-ledger/platform/2026-04-07_p0_next_slice_proposal.md`
- `ai-ledger/platform/2026-04-07_p0_platform_routing_scaffold.md`
- `ai-ledger/platform/2026-04-07_track_p0_readiness_confirmation.md`
- `ai-ledger/platform/2026-04-09_p0_audit_logs_implementation.md`
- `ai-ledger/platform/2026-04-09_p0_next_slice_proposal_v2.md`
- `ai-ledger/platform/2026-04-09_p0_operational_reporting.md`
- `ai-ledger/platform/2026-04-09_permanent_operating_rules.md`
- `ai-ledger/platform/2026-04-14_p0_audit_activity_enhancement.md`
- `ai-ledger/platform/2026-05-07_goose_platform_takeover_alignment.md`
- `ai-ledger/platform/2026-05-07_governance_doc_reconciliation.md`
- `ai-ledger/platform/2026-05-20_group1_shared_memory_sync.md`
- `ai-ledger/platform/2026-05-20_p1a_agent_preflight_gate.md`
- `ai-ledger/platform/2026-05-21_p1b_runner_preflight_wiring.md`
- `ai-ledger/platform/2026-05-21_p1c_runner_directive_contract.md`
- `ai-ledger/platform/2026-05-26_p1d_agent_toolchain_gate.md`
- `ai-ledger/platform/2026-05-26_p1e_agent_run_packet_standardization.md`
- `ai-ledger/platform/2026-05-26_p1f_agent_task_execution_bridge.md`
- `ai-ledger/platform/2026-05-26_p1g_batch_review_packet.md`
- `ai-ledger/platform/2026-05-26_p1h_agent_timeout_watchdog.md`
- `ai-ledger/platform/2026-05-26_p1i_agent_artifact_allowlist_collector.md`
- `ai-ledger/platform/2026-05-26_p1j_agent_run_bundle_gate.md`
- `ai-ledger/platform/2026-05-26_p1k_opencode_worker_mission_gate.md`
- `ai-ledger/platform/2026-05-26_p1l_batch_readiness_hijk.md`
- `ai-ledger/platform/2026-05-27_p2a_agent_mission_contract_gate.md`
- `ai-ledger/platform/2026-05-28_p2b_mission_to_worker_bridge.md`
- `ai-ledger/platform/2026-05-28_p2c_run_evidence_bundle.md`
- `ai-ledger/platform/2026-05-28_p2d_remote_runner_handoff_packet.md`
- `ai-ledger/platform/2026-05-28_p2e_batch_readiness_bcd.md`
- `ai-ledger/platform/2026-05-28_p3a_governed_harness_index_mission.md`
- `ai-ledger/platform/2026-05-28_p3a_platform_harness_index.md`
- `ai-ledger/platform/20260427-platform-handoff-skill.md`
- `ai-ledger/platform/20260428-fix-project-md-gap.md`

## Summary

- **Harness scripts:** 16
- **Ledgers:** 36
- **Missing tests:** 0

## Report Fields

- **Branch:** codex/platform-p3a-governed-harness-index-2026-05-28
- **Commit:** 34cee19
- **Modified files:** scripts/platform_harness_index.py, scripts/test_platform_harness_index.py, ai-ledger/platform/2026-05-28_p3a_platform_harness_index.md
- **Tests:** 16 / 16 paired
- **Report path:** ai-ledger/platform/2026-05-28_p3a_platform_harness_index.md
- **Risk:** MEDIUM

## P3-A Execution Evidence

- **Phase name:** P3-A First Governed Platform Task Trial - Platform Harness Index
- **Base:** origin/platform-dev fbb23a75b5ce8c2beeee358a9f0c8da8de73128e
- **Worker:** opencode via `scripts/platform_mission_worker_bridge.py`
- **Worker result:** PARTIAL; `platform_opencode_worker_gate.py` timed out at 900 seconds with exit 124 before writing `ai-ledger/platform/2026-05-28_p3a_opencode_result.json`
- **Worker changed files before CTO completion:** `scripts/platform_harness_index.py`, `scripts/test_platform_harness_index.py`, local raw events file
- **Raw events policy:** `ai-ledger/platform/2026-05-28_p3a_opencode_events.jsonl` was not committed because the repository detect-secrets hook flagged high-entropy opencode session/snapshot identifiers
- **CTO completion:** reviewed generated files, normalized index paths to `/`, generated this harness index, and wrote explicit partial-result JSON
- **Scope:** platform harness only; no backend, frontend, product runtime, auth, RBAC, tenancy, migration, payment, `.github`, `.claude`, or `docs/ai` edits

## Verification Evidence

- `python scripts/test_platform_harness_index.py`: PASS, 34 tests
- `python scripts/platform_harness_index.py --repo . --output ai-ledger/platform/2026-05-28_p3a_platform_harness_index.md`: PASS, 16 harness scripts, 36 ledgers, 0 missing tests
- Full branch verification and GitNexus results are recorded in the final CTO report for this isolated branch
