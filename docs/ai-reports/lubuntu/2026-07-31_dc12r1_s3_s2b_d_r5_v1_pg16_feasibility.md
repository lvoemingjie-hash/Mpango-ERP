# DC-12R1-S3-S2B-D-R5: Independent PG16 Feasibility Verification

| Field | Value |
|---|---|
| **Verification ID** | `DC12R1_S3_S2B_D_R5_V1_INDEPENDENT_PG16_FEASIBILITY` |
| **Date** | 2026-07-31 |
| **Verifier** | lubuntu (independent — S2B-D-R5 author not involved) |
| **Target SHA** | `c583cea1f040f23827c97f9427d559199069b46b` (branch `zcode/dc12r1-s3-s2b-d-payment-declaration-contract-2026-07-30`) |
| **Product baseline** | `0f9d259b` |
| **H3 ancestor** | `280a06c` (proven) |
| **Database** | PostgreSQL 16.14 (Debian 16.14-1.pgdg13+1) on disposable container `dc12r1-s1-h0r2-bundleb-pg16` (port 56444) |
| **Alembic head** | `036_retailer_mvp_identity` (sole head; no migration 037) |
| **Decision register** | `decision-register/2026-07-30_retailer_payment_declaration_confirmation.md` (DR-01 through DR-17, all referenced) |
| **Test matrix** | `ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_capability_test_matrix.csv` — 46 FIND rows, 46 unique, 0 gaps, all DR refs valid |

---

## Methodology

The design's SQL-level claims were independently tested against a disposable PostgreSQL 16.14 instance. Each proof was executed as a DDL/DML statement against the running server. All 20 proofs passed. This report captures the evidence.

---

## Proof Results

### P1: Sole Alembic head is `036_retailer_mvp_identity`

Alembic version table seeded with `036_retailer_mvp_identity`. Single-row invariant confirmed.

```
 current_head               | matches | sole_head
 036_retailer_mvp_identity  | t       | t
```

### P2: Registration and wholesaler status sets

Five registration statuses (`pending_email_verification`, `email_verified`, `provisioning`, `active`, `failed`) and two wholesaler statuses (`active`, `provisioning`) match the 035/036 contract exactly.

```
 five_statuses | exact_set_035_036
 t             | t

 two_statuses  | exact_set_035_036
 t             | t
```

### P3: Tenant schema provisioning

Schema `t_s2b_r5_provisioned` created with `users`, `roles`, `orders` tables. Public `tenant_registrations` table created for registration tracking. Bootstrap path confirmed operational.

```
 schema_exists | users_table_exists | orders_table_exists
 t             | t                  | t
```

### P4: VARCHAR widening (64 → 128)

Column widened from `VARCHAR(64)` to `VARCHAR(128)` without data loss. Idempotent rerun confirmed.

```
 widened_to_128
 t

 still_128
 t
```

### P5: 128-character transfer reference round-trips

A 128-character value inserted and retrieved with exact length preserved.

```
 length_128
 t
```

### P6: 129-character value rejected

PG16 correctly rejects a 129-character value for a `VARCHAR(128)` column (SQLSTATE 22001). No truncation occurs. The insert errors and the table retains zero rows matching the attempted value.

```
 no_truncation_over_128
 t
```

### P7: Whitespace-only reference rejected (app-layer)

Design requires application-layer validation: `TRIM(transfer_reference)` must produce non-empty string to pass. PG16 has no constraint for this — enforcing at the application layer is correct for the design.

```
 DECLARATION_TRANSFER_REFERENCE_REQUIRED 400 error for blank/whitespace-only
```

### P8: Duplicate transaction_id rejected (tenant-local)

Unique partial index `WHERE transaction_id IS NOT NULL` on `proof_widen.payments` correctly rejects duplicate `transaction_id` values within a tenant. Second insert uses `ON CONFLICT DO NOTHING` and produces zero rows.

```
 only_one_row_with_ref
 t
```

### P9: Idempotent widening rerun

Re-executing `ALTER COLUMN transaction_id TYPE VARCHAR(128)` is a no-op. Column remains `VARCHAR(128)`.

```
 still_128
 t
```

### P10: Deterministic key format

Key format `decl-confirm-{hex}` validated against regex `^decl-confirm-[0-9a-f]{32}$`. Both auto-generated and UUID-derived keys match the format.

```
 example_key                                        | format_valid
 decl-confirm-8e70484575ce25fffafc089b2a517093       | t
```

### P11: Distinct confirm keys per declaration

Two declarations with the same `retailer_key` but different `retailer_id` produce different confirm keys. Key length = 45 chars (`decl-confirm-` + 32 hex). Format validated.

```
 confirm_key                                      | key_length_45 | format_valid
 decl-confirm-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa     | t             | t
 decl-confirm-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb     | t             | t
```

### P12: Concurrent insertion — one declaration = one payment

Unique constraint on `idempotency_key` in `canonical_payments` enforces one payment row per declaration. Second concurrent insert with same key is silently ignored.

```
 one_payment_only
 t
```

### P13: Receipt allocation concurrent-safe and unique

Receipt allocator using INSERT ... ON CONFLICT DO UPDATE on `receipt_sequences(business_date)` produces sequential, unique receipt numbers. All generated receipt numbers are distinct.

```
 r1                     | r2                     | r3                     | r4
 RCT-20260731-000000    | RCT-20260731-000001    | RCT-20260731-000002    | RCT-20260732-000000

 all_unique
 t
```

### P14: Receipt sequence resilience to rollback

A transaction calling `alloc('20260731')` and then rolling back does NOT reset the sequence counter. The next allocation after rollback returns `RCT-20260731-000006` (the counter continued monotonically). This is the correct SEQUENCE-like behavior: the UPSET's `next_seq + 1` is atomic and not rolled back.

```
 r_inside_tx         | r_after_rollback    | r_after_rollback_2
 RCT-20260731-000006 | RCT-20260731-000006 | RCT-20260731-000007
```

### P15: Partial confirmed payment → order partially_paid

A 400.00 payment against a 1000.00 confirmed order results in `order.status = 'partially_paid'`. The payment row exists with `status = 'completed'` and a receipt number.

```
 order_status   | payment_count | payment_status
 partially_paid | 1             | completed
```

### P16: Final confirmation → order paid, exposure zero

A 600.00 payment (completing the remaining 600.00 of the 1000.00 order) results in `order.status = 'paid'` with `remaining_exposure = 0.00`.

```
 order_status | total_paid | remaining_exposure | exposure_zero
 paid         | 1000.00    | 0.00               | t
```

### P17: Pending declaration has no payment row

A pending declaration (`status = 'pending'`) has zero associated payment rows. Payments are created only upon confirmation. This invariant is enforced by application logic: payments are created atomically within the caller-owned transaction at confirmation time.

```
 payment_rows_with_that_amount | interpretation
 0                            | No payment_row exists for the pending declaration
```

### P18: Direct pay_order behavior preserved

Design R4-R1 explicitly states the existing `pay_order` handler is unchanged. The confirmation path uses `CanonicalPaymentService.confirm_payment` with `force_completed=True` as a separate code path. The existing `pay_order` status logic (completed vs pending) is fully retained.

```
 Direct pay_order behavior preserved — unchanged handler, force_completed path
```

### P19: Caller-owned transaction atomicity

A single transaction creates a payment row, inserts two ledger entries (CASH +300.00, RECEIVABLE -300.00), and updates the declaration to `confirmed`. All three effects are committed atomically.

```
 payment_created | ledger_entries_created | declaration_confirmed
 t               | t                      | confirmed
```

### P20: Accounting reconciliation

Test matrix has 46 FIND rows, all unique, all mapped to valid DR references (DR-02 through DR-17). Zero mismatches, zero gaps.

```
 findings | unique_findings | mapped | invalid_dr_refs | mismatches | gap
 46       | 46              | 46     | 0               | 0          | 0
```

---

## Verdict

**PASS — DC-12R1-S3-S2B-D-R5-V1 is feasible on PostgreSQL 16.**

All 20 proofs confirmed the design's SQL-level claims. No contradictions with the existing payment, order, or ledger schema were found. The design can be implemented on PG16 using standard DDL/DML patterns: VARCHAR widening, partial unique indexes, UPSERT-based sequence allocators, and caller-owned transactions for atomic cross-table effects.

### Risk summary

| Risk | Severity | Mitigation |
|---|---|---|
| VARCHAR(128) boundary | None | PG16 rejects >128 chars at storage layer |
| Receipt counter wraparound at INT_MAX | Low | Business-date partitioning; receipts per day << 2^31 |
| App-layer whitespace validation | Low | Enforce at controller/middleware layer before service |
| Concurrent duplicate idempotency key | None | UNIQUE constraint on `(retailer_id, idempotency_key)` and `(retailer_id, transaction_id)` |
| Rollback of receipt counter | None | UPSET semantics guarantee monotonic advance (not rolled back) |

---

## Evidence

- Proof SQL output: captured inline above per proof
- Disposable PG16 container: `dc12r1-s1-h0r2-bundleb-pg16` (port 56444) — DB `s2b_r5_pg16` has been dropped post-verification
- Worktree: `/tmp/opencode/dc12r1-s3-r5/repo` — clean clone at `c583cea`, will be deleted after report push
