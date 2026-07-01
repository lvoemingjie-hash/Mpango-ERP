"""P22 Controlled Execution v0 -- non-executing backend skeleton (P22-B).

This package implements the P22-B execution skeleton ONLY:

  - GET  /api/v1/platform/p22/execution/catalog                        catalog read
  - POST /api/v1/platform/p22/execution/dry-run                        dry-run validator
  - POST /api/v1/platform/p22/execution/requests                       execution-request recording
  - GET  /api/v1/platform/p22/execution/requests                       execution-request list
  - GET  /api/v1/platform/p22/execution/requests/{execution_request_id} execution-request read

It is NON-EXECUTING. It validates, denies, records (digest-only, redacted), and
audits; it NEVER executes any action, NEVER dispatches a worker, NEVER drains a
queue, NEVER invokes the P16 governed harness, NEVER runs shell / SQL / script,
and NEVER mutates tenant business data, the P17 registry, operational flags,
provisioning, backup, or any payment / billing / product record. Approval is not
execution and durability is not execution. Storage is in-memory, process-local
(storage == "memory") in P22-B.

Aligned to docs/ai/PLATFORM_PRODUCT_P22_CONTROLLED_EXECUTION_V0_CONTRACT.md
(P22-A). P22-C (real execution) is NOT started.
"""
from __future__ import annotations

#: The P22 phase implemented by this package.
P22_PHASE: str = "P22-B-controlled-execution-backend-skeleton"

#: Explicit non-execution marker. P22-B never executes a controlled action.
P22_EXECUTES: bool = False

__all__ = ["P22_PHASE", "P22_EXECUTES"]
