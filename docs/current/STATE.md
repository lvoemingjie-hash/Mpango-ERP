# Current State

**Snapshot:** 2026-09-02 13:03 +08:00
**Machine source:** [`state.json`](state.json)
**Canonical product branch:** `origin/product-dev-recovered`

This page is a navigation snapshot, not an authority to ignore live Git refs.
Run `pwsh -File scripts/project-context.ps1 -Refresh` before starting work.

## Merged product baseline

- SHA: `24a28d76d6d9483d8101f8e0f537c148dc262859`
- Alembic head: `037_payment_declarations_schema`
- State: pre-pilot hardening; not customer-delivery approved
- Contains: the accepted product lineage through H2-B and the merged HE2 R3+A1
  authority governance, plus the CT2 current-truth documentation merge
- Does not contain: H2-C retailer recovery, migration `038`, the three-layer SKU
  implementation, PRICING-R0, or deployment evidence

## Active work

| Track | Current candidate | Evidence status | Next gate |
|---|---|---|---|
| H2-C retailer recovery | `e16f39ca...` | Kilo reports bounded PASS at `446a42a9...`; CTO acceptance pending | CTO review, then one Lubuntu authority run |
| SKU catalog identity | `adfcfc82...` | Fix line plus router-oracle test correction; independent re-review pending | Independent review of the exact fix and test lineage |
| PRICING-R0 | None | Frozen | Wait for separate H2-C and SKU merges |
| Order-price / reorder | None | Not started | Wait for pricing contract |

These lines are independent. A PASS or failure on one line does not upgrade or
downgrade evidence on the other.

## Known release blockers

1. H2-C is not merged and lacks accepted fresh browser authority evidence.
2. SKU is not merged; the protected baseline still uses the flat tenant SKU model.
3. Release validator retains known auth-critical and commerce-critical tuple debt.
4. Remote branch protection/enforcement is not treated as verified by a successful push.
5. No customer deployment, VPS/HTTPS, real-device, real-mailbox, alert-delivery,
   backup-restore drill, or rollback-drill acceptance is current.
6. Prometheus has scrape configuration, but the merged baseline has no alert rules
   or Alertmanager target.

## Contract navigation status

- Canonical contract index: [`docs/contracts/README.md`](../contracts/README.md).
- RBAC contract entry: [`docs/contracts/rbac_matrix.md`](../contracts/rbac_matrix.md).
- `docs/RBAC_MATRIX_v0.2.0.md` is a retained superseded snapshot, not the
  current authority and not approved for deletion.
- A current-state or architecture summary never retires an omitted contract.
  Authority changes require explicit predecessor/successor links.

## Updating this page

Update `state.json` and this page only in a bounded current-truth task. Record:

- live remote SHA verification time;
- accepted evidence tier and claim ceiling;
- whether a candidate is merged, merely reviewed, or only reported;
- the exact next gate;
- any superseded status without rewriting historical reports.
- contract links affected by the status change, including superseded predecessors.
- active candidate/review remote refs and their exact expected SHAs.

Do not copy a SHA here solely because it is the newest remote commit.
