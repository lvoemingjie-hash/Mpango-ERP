"""P20 Durable Approval Governance -- backend package.

Safe, contract-backed package. Opens durable approval requests, lists and reads
them, and records per-checker approve / reject DECISIONS under a maker-checker,
quorum-based dual-control policy. No controlled action is ever executed, no
tenant state is ever mutated, and no P17 registry / lifecycle / flag /
provisioning / backup / tenant business data is ever touched. Approval is NOT
execution and durability is NOT execution: a quorum-met approval resolves to
``approved_execution_blocked`` and ``execution_allowed`` is always false.

P21-D-D runtime storage gate: durable approvals default to the P21 durable
storage backend through the readiness gate; an explicit in-memory backend
remains for test/dev only. No migration is added by this package (the durable
tables come from migration 020, P21-C1).

Aligned to docs/ai/PLATFORM_PRODUCT_P20_DURABLE_APPROVAL_GOVERNANCE_CONTRACT.md
(P20-A).
"""
