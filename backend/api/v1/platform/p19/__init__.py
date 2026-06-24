"""P19 Controlled Action Approval Workflow -- backend skeleton (P19-B).

Safe, contract-backed package. Records approval requests, lists the approval
queue, reads a single approval, and records approve / reject DECISIONS only.
No controlled action is ever executed, no tenant state is ever mutated, and no
P17 registry / lifecycle / flag / provisioning / backup / tenant business data
is ever touched. Approval is NOT execution: an approved approval resolves to
``execution_blocked`` and ``execution_allowed`` is always false.

Aligned to docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md (P19-A).
"""
