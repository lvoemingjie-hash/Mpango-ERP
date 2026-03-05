# Migration State - v0.2.1-rc1 Deployment

## alembic current
```
016_add_returned_status (head)
```

## alembic history --verbose
```
<full history from 001_initial_schema to 016_add_returned_status>

Key migrations:
- 001_initial_schema: Initial schema - public.wholesalers and tenant tables
- 002_phase_b2_invitation_binding: Phase B2 - invitations, retailers, and wholesaler-retailer bindings
- 003_phase_b3_orders_minimal_closed_loop: Phase B3 - Orders minimal closed loop
- 004_phase_b4_sku_inventory_mvp: Phase B4 - Inventory MVP
- 005_phase_b5_payments_minimal_loop: Phase B5 - Payments minimal loop
- 006_phase_b6_payments_idempotency_key: Phase B6 - Payments idempotency key
- 007_s3_b_index_hygiene: S3-B: Index Hygiene
- 008_s4_b_job_persistence: S4-B: Job Persistence
- 009_s5_b_financial_ledger: S5-B Financial Ledger
- 010_s5_5_ledger_hardening: S5.5-1: Ledger Hardening
- 011_s6_p_reporting_role: S6-P2: Reporting Role & Database Isolation
- 012_s6_1_read_models: S6-1: Financial Read Models
- 013_s6_2_materialize_sales: S6-2: Materialize Sales Daily View
- 014_s7_3_audit_trail: S7-3: BI Access Audit Trail
- 015_s7_4_sys_reports: S7-4-T3: Tenant-Scoped Reports
- 016_add_returned_status: 016: Add 'returned' value to order_status enum
```
