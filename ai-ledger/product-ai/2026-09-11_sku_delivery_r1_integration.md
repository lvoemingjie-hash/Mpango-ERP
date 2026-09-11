# SKU delivery R1: bounded current-baseline integration

TASK_ID: DC-12R1-MVP-L1-SKU-DELIVERY-R1
EXECUTOR: Codex-L, DELEGATED_CTO_ENGINEERING_LEAD
AUTHORIZATION: Human founder's in-thread 2026-09-11 bounded-disposition authorization while Windows CTO is unavailable. Not a claim of retrospective CTO approval.
BASE: bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f
SKU_INPUT: 50f15dedbded1c6d024e322ac84f857699d624e5
SKU_LINEAGE: c05c5ff1 -> f151f53d -> 3e831384 -> 50f15ded
VERIFICATION_TIER: V3_MERGE_CRITICAL
CLAIM_CEILING: READY_FOR_CTO_CONTROLLED_MERGE_DECISION_ONLY

## Exact new edit scope

- harness-governance/inventory/protocol-deltas.json: append one base-bound integration entry; retain prior records unchanged.
- ai-ledger/product-ai/2026-09-11_sku_delivery_r1_integration.md: this ledger.

All other staged changes are the automatic, conflict-free integration of the frozen SKU input into the frozen mainline. Mainline recovery changes are retained. No additional product behavior change, protected-branch merge, push or deployment is authorized here.

## Prior failure preserved

D1 compared the unmerged SKU tree with advanced mainline and obtained structural rc=1: 14 protected path findings plus a semantic-sync finding for 32 paths. This included mainline-only differences and is not a final integrated-tree result. Its report and HANDOFF remain unchanged. R1 is a new human-authorized round, not a rerun relabeled as success.

## Contract

Retain CatalogProduct -> SKU/SellableUnit -> CatalogOffer interface boundary. Order identity and snapshots, no guessed legacy binding, migration 038 -> 037, inventory initialization, SKU code permanence and tenant isolation remain required. BC-06 separates objective identity-use locking from current-price reprice gating. Do not implement new pricing, payment, order lifecycle or reorder semantics.

The 40 exact delta paths are the intersection of inherited SKU-delta paths with actual integrated changes, plus the three BC-06 paths needing registration. This is accounting for inherited reviewed work, not permission to rewrite authority code or waive tests. Existing release debts are not closed by this entry.

## Verification status at edit time

Git merge-tree and actual no-commit merge both found zero conflicts. Product runtime, full tests, browser and independent review are not yet run on this integrated tree. No runtime PASS or merge readiness is claimed by this ledger. Subsequent evidence belongs in the task-scoped HANDOFF/scratch with immutable failure records.
