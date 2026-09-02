# Active Work Index

**Snapshot:** 2026-09-02 14:01 +08:00
**Live product branch:** `origin/product-dev-recovered`
**Recorded baseline:** `24a28d76d6d9483d8101f8e0f537c148dc262859`

Use this page instead of scanning hundreds of historical branches. Verify live
refs with `scripts/project-context.ps1 -Refresh` before acting.

## Active product lines

| Alias | Candidate/report | Current classification | Next authorized gate |
|---|---|---|---|
| `CURRENT_PRODUCT_BASELINE` | `24a28d76...` | Merged protected baseline | Remains frozen while candidates are reviewed |
| `ACTIVE_H2C_CANDIDATE` | `e16f39ca...` | Unmerged retailer-recovery/browser-authority candidate | Lubuntu single-stack, single-preflight, single-browser authority |
| `LATEST_H2C_KILO_REPORT` | `446a42a9...` | CTO-accepted Kilo source/test/contract/mutation authenticity; not a browser PASS | Consumed; preserve as immutable evidence |
| `ACTIVE_SKU_CANDIDATE` | `adfcfc82...` | UUID-path closure plus router-oracle test correction after an independent defect finding | Independent review pending |
| `PRICING_R0` | None | Frozen | Wait for separate H2-C and SKU merges |
| `ORDER_PRICE_REORDER` | None | Not started | Wait for pricing contract |

## Branch namespaces

| Prefix | Intended use |
|---|---|
| `product-dev-recovered` | Protected merged product baseline |
| `codex/` | CTO-owned docs, reviews, governance, and bounded implementation |
| `zcode/` | Bounded implementation candidates |
| `codexl/` | Lubuntu/Codex-L implementation candidates |
| `reports/` | Immutable or linearly corrected evidence publications |
| `integration/` | Temporary/rehearsal integration refs; not automatically merged |

Branch age or prefix does not establish approval. The current state and accepted
evidence chain do.

## Evidence navigation rule

For an active line, navigate in this order:

1. candidate branch and exact SHA;
2. candidate ledger for scope and self-assessment;
3. independent Kilo report;
4. independent Lubuntu runtime report;
5. controlled merge report;
6. deployment report.

Stop at the first missing step. Do not jump from candidate self-assessment to
merge or from merge to deployment.

## Historical work

The remote currently contains hundreds of historical refs. They remain evidence
and recovery inputs, but they are not active navigation. No branch deletion is
authorized by this index. A future retention task must first prove reachability,
report references, tags/bundles, and recovery requirements.

## Updating active work

Update this file and `docs/current/state.json` together when:

- a candidate is superseded;
- an independent review changes status;
- a controlled merge moves the protected baseline;
- a line is frozen/unfrozen;
- a deployment becomes current.

Record full SHAs in current state; use aliases here to make them navigable.
