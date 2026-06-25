"""P20 Durable Approval Governance -- backend skeleton (P20-B).

Safe, contract-backed package. Opens durable approval requests, lists and reads
them, and records per-checker approve / reject DECISIONS under a maker-checker,
quorum-based dual-control policy -- all in process-local memory. No controlled
action is ever executed, no tenant state is ever mutated, and no P17 registry /
lifecycle / flag / provisioning / backup / tenant business data is ever touched.
Approval is NOT execution and durability is NOT execution: a quorum-met approval
resolves to ``approved_execution_blocked`` and ``execution_allowed`` is always
false. There is intentionally no database table and no migration.

Aligned to docs/ai/PLATFORM_PRODUCT_P20_DURABLE_APPROVAL_GOVERNANCE_CONTRACT.md
(P20-A).
"""
