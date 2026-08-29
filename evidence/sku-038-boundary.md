# 038 evidence boundary — SKU profile verification only

- The candidate contains NO real product migration 038
  (`backend/alembic/versions/` has zero 038 files; verified count=0).
- `AUTHORITY_SKU_M1_BACKEND` verified at the profile level only:
  schema conformance (`expected_alembic_head` required,
  `expected_alembic_parent` optional — both present: 038 successor of
  037), byte binding (profile SHA bound at preflight and re-verified by
  the child; drift after preflight VOIDs with launch count 0 — live
  control N16), and existing fixture behavior (the candidate's own
  alembic-scan/verify fixtures: multi-head, prefix-similar head,
  whitespace head — all held inside the 186/186 truth suite).
- Selecting `AUTHORITY_SKU_M1_BACKEND` on this 037 tree VOIDs at
  PREFLIGHT (rc=13, alembic head drift, sentinel_calls=0): live control
  N11 (`evidence/negctl/N11-sku-on-037.out`).
- **No real SKU-M1 038 product runtime PASS is claimed or implied.**
  The real 038 authority run is reserved for a future round after
  Codex-L freezes an SKU candidate containing the real 038 migration.
