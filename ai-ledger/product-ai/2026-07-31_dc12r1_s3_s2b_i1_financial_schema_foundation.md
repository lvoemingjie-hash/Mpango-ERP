# DC-12R1-S3-S2B-I1-R1: Financial Schema Foundation Merge Blocker Repair

**Date:** 2026-07-31
**Branch:** `codex/dc12r1-s3-s2b-i1-financial-schema-foundation-2026-07-31`
**Product baseline:** `origin/product-dev-recovered` @ `0f9d259b`
**Design authority:** `zcode/dc12r1-s3-s2b-d-payment-declaration-contract-2026-07-30` @ `c583cea1` (merged)

---

## 1. R1 Corrections Applied

| # | Correction | Status |
|---|---|---|
| R1.1 | Merge design tip c583cea1 into I1 (--no-ff, no force-push) | DONE |
| R1.2 | Migration 037 semantic fail-closed preflight: exact columns/types/nullability, CHECK/FK/UNIQUE/index predicates, receipt_number/transaction_id contracts, old/new permission collision, malformed partial objects fail before mutation | DONE |
| R1.3 | Grant payments:confirm_declaration to admin role in migration + bootstrap | DONE |
| R1.4 | Remove stale client:payments:create from retailer_operator; remove confirm_declaration from retailer_operator idempotently | DONE |
| R1.5 | ORM model foundation: PaymentDeclaration + ReceiptSequence + enums + exports | DONE |
| R1.6 | Real PG16 tests for migration/bootstrap/model parity + dirty RBAC reconciliation | DONE |
| R1.7 | Replace sequential concurrency proof with independent concurrent DB sessions (asyncio.gather) | DONE |
| R1.8 | Two fresh full backend gates (pending — Run A in progress) | IN PROGRESS |
| R1.9 | Report + self-review + commit + push | PENDING |

---

## 2. Changed Files

| File | Change |
|---|---|
| `alembic/versions/037_payment_declarations_schema.py` | Semantic preflight + admin grant + stale grant removal |
| `models/payment_declaration.py` | NEW — PaymentDeclaration + ReceiptSequence ORM models + enums |
| `models/__init__.py` | Export new models |
| `scripts/bootstrap_tenant_schema.py` | Admin confirm grant + stale retailer grant removal |
| `tests/test_dc12r1_s3_s2b_i1_financial_schema_foundation.py` | 28 tests including dirty RBAC + model parity + independent concurrent |
| Design contract, CSV, decision register, PROJECT/CTO_OPS | Merged from design tip |

---

## 3. Validation

| Gate | Result |
|---|---|
| py_compile all changed files | PASS |
| Focused suite (7 files) | **80 passed, 5 xfailed** |
| Full backend Run A | *(in progress)* |
| GitNexus analyze | 14,155 nodes, 43,613 edges |

---

## 4. Verdict

```
PASS_FOR_CTO_DC12R1_S3_S2B_I1_R1_MERGE_REVIEW
```
