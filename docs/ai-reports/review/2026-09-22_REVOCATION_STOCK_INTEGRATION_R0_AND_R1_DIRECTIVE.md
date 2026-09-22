# Revocation / Stock Integration R0 and Bounded R1 Directive

Date: 2026-09-22
Owner: CTO / Codex
Authorization: Jeff's instruction to continue pre-MVP delivery work.
Verification tier: V1, pinned-source and Git reconciliation only.
Result: SOURCE_RECONCILIATION_COMPLETE__BOUNDED_R1_REQUIRED
Claim ceiling: six historical repairs are not yet integrated into the current
Order R2 / DB-authority candidate. No current runtime verdict is issued.

## 1. Identity and documentation promotion receipt

| Input | Frozen identity |
| --- | --- |
| Integration base | `5c93763ded903cc4e903d67997f1528d09ddc4b8` |
| Integration tree | `e6444326ac2c023b610fc1d796b595439fcf0c22` |
| Integration target ref | `codex/order-state-r2-e1-source-revision-f1-f3-20260919` |
| Historical repair candidate | `a516d2b3257f782ce068e71e8730c05541f08931` |
| Historical repair tree | `6a412568cd2c50fcf1d92103d989603a5b819e60` |
| Historical repair comparison base | `1485c3f5b59e45357462e40975537cbf3932d3b0` |
| R0 report branch | `codex/revocation-stock-integration-r0-20260922` |

`git fetch --all --prune` completed before promotion/reconciliation. The main
user worktree was not modified. This report is prepared in a separate linked
worktree directly on the integration base.

The previously prepared documentation-only successor was promoted by normal
push to `product-dev-recovered` under the current authorization:

- Before: `bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f`.
- After: `57df5334f35130b6dc58e4bf5f3893a91bfc8a07`.
- Exact change: `docs/ai/PROJECT.md`; no product source changes.
- The successor's sole parent is the before commit; normal push exited 0.
- Fresh fetch and `git ls-remote origin refs/heads/product-dev-recovered`
  both confirmed the after commit.
- The separate candidate-side documentation mirror `0665294a` was NOT used
  for this promotion: it would carry unrelated product history into the target.
- The integrated product ref remains at `5c93763d`; updating project status
  does not merge that product line into `product-dev-recovered`.

## 2. Source findings

### F1 / P1: current tenant access lacks the historical revocation checks

At the integration base, `backend/api/context/tenant.py:80`
(`resolve_tenant_context`) checks existence and `is_active`, but not
`is_deleted`, and does not check the current public wholesaler state.
`backend/crud/user.py:126` (`get_user_with_permissions`) selects by user id
without a soft-delete predicate. The relevant legacy checks are therefore
absent, rather than merely hidden behind a different commit ancestry.

Legacy `a516d2b3` adds the explicit user soft-delete check and
`assert_tenant_active`, reading the current non-deleted active wholesaler.
This R0 makes no new HTTP/runtime failure claim.

### F2 / P1: contextual refresh lacks current subject/tenant revalidation

At `backend/api/v1/auth.py:450`, `refresh_token` decodes the signed token and
checks its type, but its contextual branch (line 507) immediately reissues
tokens from existing claims. The legacy `_validate_contextual_refresh_subject`
is absent. Reintroduce validation before either token is constructed, while
preserving identity-only refresh behavior and existing signature/type checks.

Scope precision: in the legacy implementation, the refresh subject lookup uses
the database-derived tenant schema. Ordinary `resolve_tenant_context` still
opens the token-claimed schema before its tenant-state check. Do not describe
the historical fix as universal database-derived schema routing or complete
cross-tenant isolation. Any broader routing change requires its own bounded
design and tests, not an implicit addition to this port.

### F3 / P1: manual-adjustment lock does not refresh the identity map

At `backend/services/inventory_service.py:456`, `adjust_stock` first loads a
stock entity, then issues `SELECT FOR UPDATE` without `populate_existing`.
The historical repair adds `.execution_options(populate_existing=True)` to
that lock query. Other current inventory paths already use fresh-load locks;
their presence does not repair this particular query.

The integrated file also contains newer catalog/sellable-unit identity,
active-catalog checks, reservation, fulfillment and return logic. A whole-file
replacement or wholesale legacy-branch merge would risk regressing that work.
Port the narrow adjustment-query repair, retaining all newer semantics.

### F4 / P1: historical test infrastructure is not directly compatible

The integration base does not contain `mpango_invariants_r0_support.py` or the
three legacy invariants test modules. It does contain
`test_pw1r3_rate_limit_context.py`, whose synthetic user fixture lacks the
public active wholesaler row required by the added access check.

The support file at `a516d2b3`:

- Freezes migration head `037_payment_declarations_schema`, not current 039.
- Runs migrations with the same `DATABASE_URL` as application tests.
- Requires its URL user/database to equal container `POSTGRES_USER/POSTGRES_DB`.
- Seeds `SKU` without `catalog_product_id`; the current model requires a
  non-null catalog-product foreign key (`backend/models/sku.py:33`).

These assumptions conflict with the accepted role-separated provisioning
contract and current SKU identity. Adapt only task-owned test infrastructure;
never weaken the product bootstrap authority checks or silently substitute 037.

## 3. Reproducible source identity

Values below are Git blob object IDs, NOT content SHA-256 hashes.

| Path | Integration-base blob | Historical-repair blob |
| --- | --- | --- |
| `backend/api/context/tenant.py` | `1919d37580e842e0648dac2985bca13f56bbf42d` | `7f5506936f109be77e529c5d82b02ef9f8d2b13c` |
| `backend/api/v1/auth.py` | `290c4caae64ce0b38cf549af5216044d557af166` | `962918f6cd865cb8ead0fd3b751955c57ee7bb6b` |
| `backend/services/inventory_service.py` | `c97bde551ec615f3cd6d2137444ea22483cf9570` | `242faec965b77f4a51c0b8d53d2daafcb2e7f73d` |

Historical support blob: `4bf3fd041ac1286aa0d43a33b7d948bdb7e90685`.
Reproduction requires only the frozen Git objects:

```sh
git merge-base --is-ancestor a516d2b3 5c93763d
# expected rc=1; ancestry alone is not the finding
git diff a516d2b3 5c93763d -- backend/api/context/tenant.py backend/api/v1/auth.py backend/services/inventory_service.py
git diff --name-status 1485c3f5 a516d2b3
git show a516d2b3:backend/tests/mpango_invariants_r0_support.py
git show 5c93763d:backend/models/sku.py
git show 5c93763d:backend/crud/user.py
git ls-tree -r --name-only 5c93763d backend/tests
```

GitNexus query was attempted for the auth/refresh/stock concepts. It returned
no execution processes and included historical scratch-path matches; it was
not treated as a candidate-bound impact proof. Findings above come from pinned
blobs and direct source/caller inspection. Before R1 symbol edits, refresh the
candidate index and run upstream impact on each touched symbol. Authentication
and inventory integrity are high-risk surfaces regardless of an empty graph.

## 4. Next work: REVOCATION-STOCK-INTEGRATION-R1

Owner: CTO/Codex implementation; fresh Kilo context for independent V3 review.
Base: exact integrated candidate `5c93763ded903cc4e903d67997f1528d09ddc4b8`.
Use a new isolated `codex/` branch. No wholesale legacy merge. R0 itself makes
no product edits and has not dispatched or completed R1.

Authorized product paths (three):

1. `backend/api/context/tenant.py`.
2. `backend/api/v1/auth.py`.
3. `backend/services/inventory_service.py`.

Bounded test/support paths (five):

1. `backend/tests/mpango_invariants_r0_support.py` (import/adapt from frozen source).
2. `backend/tests/test_mpango_mvp_invariants_r0_revocation.py`.
3. `backend/tests/test_mpango_mvp_invariants_r0_concurrency.py`.
4. `backend/tests/test_mpango_invariants_r0_r1_guards.py`.
5. `backend/tests/test_pw1r3_rate_limit_context.py` (minimal fixture adaptation).

Reports belong under `docs/ai-reports/review/`; sanitized machine evidence may
use its task-specific subdirectory. Do not edit migrations, bootstrap,
provisioner, Compose, reporting-session/gate, pricing, order/payment/return
state rules, frontend, deployment scripts, baseline or allowlists.

Implementation requirements:

- Restore the two access revocation and three contextual-refresh rejection
  behaviors plus the stock lock refresh. Preserve neutral 401s, zero issued
  token material on rejection and active-user positive controls.
- Preserve the integrated SKU/catalog links, order credit holds, public
  constraints, financial writes and commit-before-notification behavior.
- Separate task-owned administrator/migration preparation from runtime tests.
  Use real accepted provisioning and head `039_order_credit_holds`; runtime
  must not gain migration authority, public CREATE or admin credentials.
- Replace the support fixture's single-role/container-user equivalence with
  explicit task cluster/database/role binding. Preparation may create only
  its task-owned resources. Tests must not run migrations as the app role.
- Seed valid catalog-product/SKU/stock identities and exact public tenant rows.
  Cleanup must restore shared role/credential state or avoid mutating it;
  exact task-identity teardown failures remain visible, never swallowed.
- Keep real JwtAuthStrategy (`staging`), task-exclusive PG16 and Redis, and
  runtime/test environment files isolated. Reuse no prior test DB or credentials.

## 5. Acceptance map and stop rules

| Rule | Required real-path evidence |
| --- | --- |
| Soft-deleted tenant user | Existing contextual access returns 401; active control succeeds |
| Suspended/deleted tenant | Current DB state denies contextual access; no stale-token bypass |
| Nonexistent refresh principal | Real HTTP refresh returns 401 and no new token fields |
| Soft-deleted refresh principal | Same, with valid signature/type controls retained |
| Suspended tenant refresh | Same; DB-derived lookup, missing scope handled without false 500 |
| Concurrent manual adjustment | Independent sessions/barriers force stale preloads; 10+7+5=22; raw movement multiplicity and chain conserved |
| Integration regression | Current Order O27 and DB-authority D22 selections plus affected auth/SKU tests; fresh collection and exact outcome reconciliation |

Historical 51-pass is reference evidence only. Collect the adapted suite anew;
do not force a count by dropping unexpected nodes. Keep the known duplicate
concurrent-return RED explicitly excluded only under its documented legacy
boundary, never silently marked fixed. Cross-tenant cache isolation, logout,
password-reset session invalidation and identity-only refresh remain open.

Author preparation may be iterative and must preserve failures. Before an
independent frozen run, prove env/URL/role/head/ports, call actual candidate
temporary-DB guards when applicable, and validate node arguments with the same
interpreter, cwd and environment. Persist invocation/return code and unmodified
JUnit. A formal failure stops that envelope; no undisclosed retries/reordering.

Use semantic reversions of the revocation checks and lock refresh against green
controls to show decisive REDs, then byte-exact restoration. Infrastructure or
syntax failures are not mutation detection. Keep financial before/after
snapshots complete and prove exact cleanup. Do not start another general
runner framework or a broad suite merely to repair preparation machinery.

Final R1 acceptance requires independent V3 on the new candidate, not transfer
of legacy PASS. Protected product-source promotion and deployment remain
separate gates. If extra product paths are necessary, stop and amend this
bounded scope before editing them.

## 6. Delivery ordering and current limits

Immediate next implementation is the missing revocation/stock integration.
Pricing/ordering business-rule-to-test mapping can proceed as document work,
but new production behavior waits for the integration gate and its own scope.
Previously confirmed P01-P05 decisions must not be reopened merely because
the project overview was stale. No new business answer is required from Jeff
to perform this R1 work.

Production deployment remains blocked on the separately tracked deployment
scripts, production topology replacement, image pinning and release evidence.
This report is not a claim of MVP completion, full-suite green or deployment.

TESTS_RUN_THIS_ROUND=NONE
FULL_SUITE_RESULT=NOT_RUN_THIS_ROUND
FORMAL_RUNTIME_ENVELOPE=NOT_RUN_THIS_ROUND
PRODUCT_SOURCE_EDITS=0
DOCS_ONLY_PRODUCT_DEV_PROMOTION=COMPLETED
PRODUCT_SOURCE_MERGE_AUTHORIZED=NO
DEPLOYMENT_AUTHORIZED=NO
PRICING_AND_FURTHER_ORDERING_IMPLEMENTATION_AUTHORIZED=NO
NEXT_GATE=REVOCATION_STOCK_INTEGRATION_R1_AUTHOR_IMPLEMENTATION
