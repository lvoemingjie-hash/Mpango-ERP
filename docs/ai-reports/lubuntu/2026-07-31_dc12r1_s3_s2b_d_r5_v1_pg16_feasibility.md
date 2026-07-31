# DC-12R1-S3-S2B-D-R5-V1-R1: Independent PG16 Feasibility Verification (Corrected Evidence)

| Field | Value |
|---|---|
| **Verification ID** | `DC12R1_S3_S2B_D_R5_V1_R1_INDEPENDENT_PG16_FEASIBILITY` |
| **Date** | 2026-07-31 |
| **Verifier** | lubuntu (independent — S2B-D-R5 author not involved) |
| **Reviewed design SHA** | `c583cea1f040f23827c97f9427d559199069b46b` (branch `zcode/dc12r1-s3-s2b-d-payment-declaration-contract-2026-07-30`) |
| **Product baseline** | `0f9d259b` |
| **H3 ancestor** | `280a06c` (proven) |
| **Database** | PostgreSQL 16.14 (Debian 16.14-1.pgdg13+1) on task-owned disposable container `dc12r1-s3-s2b-d-r5-v1r1-pg16` (host port 56450, container IP 172.17.0.21) |
| **Database name** | `verify_s2b_d_r5_v1r1` (created fresh for this run; dropped after verification) |
| **Alembic head** | `036_retailer_mvp_identity` (sole head; no migration 037) |
| **Decision register** | `decision-register/2026-07-30_retailer_payment_declaration_confirmation.md` (DR-01 through DR-17, all referenced) |
| **Test matrix** | `ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_capability_test_matrix.csv` — 46 FIND rows, 46 unique, 0 gaps, all DR refs valid |

> **R1 correction scope**: This revision replaces the P13/P14 outputs and interpretations
> from V1 (the previous run used a non-exact allocator display offset and incorrectly
> claimed non-rollback/sequence-like behavior). It also expands P19 to the full
> caller-owned atomicity proof with rollback, commit, and replay scenarios.
> All other evidence was re-executed unchanged on the fresh container and is preserved.

---

## Methodology

The design's SQL-level claims were independently tested against a disposable PostgreSQL 16.14 instance in a task-owned container created specifically for this verification (`dc12r1-s3-s2b-d-r5-v1r1-pg16`, host port 56450). Each proof was executed as a DDL/DML statement against the running server. All 20 proofs passed. This report captures the evidence.

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
 rejected_no_truncation
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
 decl-confirm-0207cbcc0816fb053e1138eb73bec36e       | t
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

### P13: Receipt allocator — exact design SQL

The **exact design SQL** was executed:

```sql
INSERT INTO receipt_sequences (business_date, next_seq)
VALUES (:business_date, 1)
ON CONFLICT (business_date) DO UPDATE
SET next_seq = receipt_sequences.next_seq + 1
RETURNING next_seq;
```

Required results (all confirmed):

- First committed receipt for a new date = `RCT-YYYYMMDD-000001` (NOT `...000000`):

```
 first_receipt       | second_receipt      | third_receipt
 RCT-20260731-000001 | RCT-20260731-000002 | RCT-20260731-000003
```

- No `...000000` receipt is allowed: `next_seq` starts at 1 and the first INSERT
  stores `next_seq = 1`, so the first returned value is 1, never 0.

```
 no_zero | one_row_per_date
 t       | t
```

- Concurrent allocations are unique: three parallel psql sessions each allocated
  5 receipts on the same business date; 15/15 receipts were unique and strictly
  sequential with no gaps and no duplicates:

```
 session 1: RCT-20260740-000001 .. RCT-20260740-000005
 session 2: RCT-20260740-000006 .. RCT-20260740-000010
 session 3: RCT-20260740-000011 .. RCT-20260740-000015
```

- Per-date uniqueness confirmed across sequential allocations:

```
 all_unique
 t
```

### P14: Receipt sequence rollback semantics — exact proof

**Correct interpretation (validated by proof):**

- `receipt_sequences` is a **transactional table**, not a PostgreSQL SEQUENCE.
- Its `UPDATE` **rolls back with the payment transaction**.
- A number created only in a rolled-back transaction **may be reused**.
- This is **safe** because no committed payment/receipt owns that number.

Exact proof sequence (fresh business date `20260733`):

| Step | Action | Result |
|---|---|---|
| 1 | Committed counter N | `RCT-20260733-000001` (N=1 committed) |
| 2–3 | `BEGIN`; allocate N+1 | `RCT-20260733-000002` inside the transaction |
| 4 | `ROLLBACK` | counter reverts to 1 (the UPDATE rolled back) |
| 5 | Allocate again | `RCT-20260733-000002` — **N+1 reused**, proving the rolled-back UPDATE did not persist |
| 6 | Commit | counter now 2 (committed) |
| 7 | Next allocation | `RCT-20260733-000003` = N+2 |

```
 step5 re_allocated      | step7 next_after_commit
 RCT-20260733-000002     | RCT-20260733-000003
```

> **Correction note**: The V1 report claimed "the counter is NOT reset on rollback,
> the UPSERT is atomic and not rolled back, giving SEQUENCE-like monotonic semantics."
> That claim is **wrong** and has been removed. The proof above shows the opposite:
> the `ON CONFLICT DO UPDATE` is a normal transactional statement, its row-level effect
> rolls back with the payment transaction, and a number allocated only inside a
> rolled-back transaction **is reused** by a later allocation. This is safe because
> no committed payment or receipt owns that number.

### P15: Partial confirmed payment → order partially_paid

A 400.00 declaration against a 1000.00 confirmed order (retailer binding starts at 1000.00) is confirmed in a caller-owned transaction: payment row created with receipt, declaration set to `confirmed`, order set to `partially_paid`, binding reduced to 600.00.

```
 order_status  | payment_count | decl_status | binding_balance
 partially_paid | 1            | confirmed   | 600.00
```

### P16: Final confirmation → order paid, exposure zero

A 600.00 declaration (completing the order) is confirmed: payment created, order set to `paid`, binding reduced to 0.00. Remaining exposure is 0.00.

```
 order_status | total_paid | remaining_exposure | exposure_zero | binding_balance
 paid         | 1000.00    | 0.00               | t             | 0.00
```

### P17: Pending declaration has no payment row

A pending declaration (`status = 'pending'`, `confirmation_payment_id = NULL`) has zero associated payment rows. Payments are created only upon confirmation, atomically within the caller-owned transaction.

```
 payment_rows | confirmation_payment_null | decl_status
 0            | t                         | pending
```

### P18: Direct pay_order behavior preserved

Design R4-R1 explicitly states the existing `pay_order` handler is unchanged. The confirmation path uses `CanonicalPaymentService.confirm_payment` with `force_completed=True` as a separate code path. The existing `pay_order` status logic (completed vs pending) is fully retained.

```
 Direct pay_order behavior preserved — unchanged handler, force_completed path
```

### P19: Full caller-owned atomicity proof

All effects of a confirmation are performed inside **one transaction**:

1. completed payment row with `receipt_number`;
2. both ledger entries (CASH +500.00, RECEIVABLE −500.00), each referencing the payment ID;
3. order status update (`confirmed` → `paid`) and exposure cleared;
4. `wholesaler_retailer_bindings.outstanding_balance` reduced by the amount;
5. declaration `status = 'confirmed'`;
6. declaration `confirmation_payment_id` set to the payment ID.

**Rollback scenario** — forced failure before commit (RAISE EXCEPTION simulating a crash):

```
 P19-R: after forced failure - zero effects
 payments | ledger_entries | order_status | binding_balance | decl_status | confirmation_null | receipt_counter_unadvanced
 0        | 0              | confirmed    | 500.00          | pending     | t                 | t
```

- payment rows: **0**; ledger entries: **0**; receipt number **absent** (counter for
  that business date did not advance — the in-transaction UPDATE rolled back);
  order unchanged (`confirmed`); binding balance unchanged (500.00); declaration
  still `pending` with `confirmation_payment_id = NULL`.

**Commit scenario** — repeated successfully:

```
 P19-C: commit - effects exactly once
 payments | ledger_entries | distinct_payment_refs | order_status | binding_balance | decl_status
 1        | 2              | 1                     | paid         | 0.00            | confirmed

 P19-C: same payment everywhere
 decl_conf_payment                          | payment_id                                 | ledger_payment_refs                       | same_payment
 88c71abe-f7a7-4288-a6bd-4db15d566280       | 88c71abe-f7a7-4288-a6bd-4db15d566280       | 88c71abe-f7a7-4288-a6bd-4db15d566280       | t
```

- Every effect exists **exactly once**: 1 payment, 2 ledger entries (1 distinct
  payment reference), order `paid`, binding 0.00, declaration `confirmed`.
- The payment ID is the **same** in the payment row, both ledger entries, and
  `confirmation_payment_id`.

**Replay scenario** — re-execution of the confirm operation adds **zero** duplicate
effects (guarded by the declaration still being `pending`; a confirmed declaration
is not re-confirmed):

```
 P19-RP: replay - zero duplicate effects
 payments | ledger_entries | binding_balance | decl_confirmed_count | payments_for_decl
 1        | 2              | 0.00            | 1                    | 1
```

### P20: Accounting reconciliation

Test matrix has 46 FIND rows, all unique, all mapped to valid DR references (DR-02 through DR-17). Zero mismatches, zero gaps.

```
 findings | unique_findings | mapped | invalid_dr_refs | mismatches | gap
 46       | 46              | 46     | 0               | 0          | 0
```

---

## Verdict

**PASS — DC-12R1-S3-S2B-D-R5-V1-R1 is feasible on PostgreSQL 16.**

All 20 proofs confirmed the design's SQL-level claims, including the exact receipt
allocator SQL, the correct transactional rollback semantics of `receipt_sequences`,
and the full caller-owned confirmation transaction. No contradictions with the
existing payment, order, or ledger schema were found.

### Risk summary

| Risk | Severity | Mitigation |
|---|---|---|
| VARCHAR(128) boundary | None | PG16 rejects >128 chars at storage layer |
| Receipt number reuse after rollback | None by design | Numbers allocated only inside a rolled-back transaction belong to no committed payment/receipt; reuse is safe. Concurrency is excluded per business date by the primary key + `ON CONFLICT` atomic increment |
| Receipt counter wraparound at INT_MAX | Low | Business-date partitioning; receipts per day << 2^31 |
| App-layer whitespace validation | Low | Enforce at controller/middleware layer before service |
| Concurrent duplicate idempotency key | None | UNIQUE constraint on `(retailer_id, idempotency_key)` and `(retailer_id, transaction_id)` |
| Confirmation atomicity | None | All effects inside a caller-owned transaction; forced-failure test proved zero partial effects; replay guard proved zero duplicate effects |

---

## Evidence

- Proof SQL output: captured inline above per proof (all executed on the fresh task-owned container)
- Fresh task-owned PG16 container: `dc12r1-s3-s2b-d-r5-v1r1-pg16` (host port 56450, container IP 172.17.0.21, image `postgres:16`, PostgreSQL 16.14 Debian) — created for this verification, DB `verify_s2b_d_r5_v1r1` dropped, container/volume/network removed after the report was finalized
- Worktree: `/tmp/opencode/dc12r1-s3-r5-r1/repo` — clean clone of the reports branch at `24ed772`, deleted after push
- No product code, migration, test, config, or design-branch files were modified
