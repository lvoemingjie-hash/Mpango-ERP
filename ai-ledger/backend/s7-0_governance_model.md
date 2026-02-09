# S7-0: Governance Baseline — BI Asset Modeling & URN System

**Track**: P7-0 (Governance Baseline)
**Date**: 2026-02-09
**Status**: ✅ COMPLETE
**Author**: Backend AI (Chief Backend Architect)
**Phase**: 7 — Governance & Operations
**Depends On**: Phase 6 (S6-1 → S6-5, all complete)

---

## 1. Objective

Transform Phase 6's implicit reporting objects (views, metrics, endpoints) into
**explicit, addressable governance assets**. This is pure modeling — no enforcement
logic, no middleware, no RBAC checks.

**Before P7-0**: "We have `mv_sales_daily` in the code."
**After P7-0**: "We have `urn:bi:view:sales:mv_sales_daily`, owned by backend-engineering,
classified as near-real-time, registered in the governance manifest."

---

## 2. Architecture

### 2.1 File Structure

```
backend/core/governance/
├── __init__.py          # Package exports
├── models.py            # BIAction, ResourceType, BIDomain, BiUrn, BIAsset, DataFreshness
└── registry.py          # GOVERNANCE_REGISTRY — 18 assets registered
```

### 2.2 Relationship to Semantic Layer

```
┌─────────────────────────────────────────────────────┐
│                  Governance Layer (P7-0)             │
│                                                     │
│  "What does management know exists?"                │
│                                                     │
│  GOVERNANCE_REGISTRY                                │
│  ├── 3 Views    (mv_*, rpt_*)                       │
│  ├── 7 Metrics  (revenue, balance, ...)             │
│  ├── 3 Dashboards (executive, sales, cash flow)     │
│  ├── 3 Reports  (ad-hoc analysis per view)          │
│  └── 2 Export Templates (CSV, XLSX)                 │
│                                                     │
│  BIAsset.semantic_ref ──────────┐                   │
│                                 │                   │
├─────────────────────────────────┼───────────────────┤
│                  Semantic Layer (S6-3)               │
│                                 │                   │
│  "What can the query engine access?"                │
│                                 ▼                   │
│  _REGISTRY                                          │
│  ├── ViewScope.SALES_DAILY → MvSalesDaily           │
│  ├── ViewScope.RECEIVABLES_SUMMARY → RptReceivables │
│  └── ViewScope.CASH_FLOW_DAILY → RptCashFlowDaily   │
│                                                     │
│  ReportMetric → column attribute name               │
│  ReportDimension → column attribute name            │
└─────────────────────────────────────────────────────┘
```

**Key distinction**:
- The **semantic layer** is a *security boundary* (whitelist enforcement).
- The **governance registry** is a *visibility boundary* (asset catalog).
- An asset in the registry that is NOT in the semantic layer is a "planned"
  or "deprecated" asset — visible to management but not queryable.

---

## 3. URN Format

### 3.1 Structure

```
urn:bi:<resource_type>:<domain>:<identifier>
  │  │        │            │          │
  │  │        │            │          └─ unique name (lowercase, a-z0-9_)
  │  │        │            └─ business domain
  │  │        └─ asset classification
  │  └─ namespace (always "bi")
  └─ scheme (always "urn")
```

### 3.2 Resource Types

| Type | Description | Example |
|------|-------------|---------|
| `dashboard` | Composed multi-widget view | `urn:bi:dashboard:executive:executive_summary` |
| `report` | Structured data output (ad-hoc) | `urn:bi:report:sales:adhoc_sales_analysis` |
| `metric` | Single measurable quantity | `urn:bi:metric:finance:outstanding_balance` |
| `view` | Database reporting object (rpt_*/mv_*) | `urn:bi:view:sales:mv_sales_daily` |
| `export_template` | Saved export configuration | `urn:bi:export_template:sales:sales_daily_csv` |

### 3.3 Business Domains

| Domain | Scope |
|--------|-------|
| `finance` | Cash flow, receivables, ledger-derived |
| `sales` | Revenue, transactions, order-derived |
| `operations` | Inventory, procurement (future) |
| `executive` | Cross-domain summaries |

### 3.4 URN Properties

- **Stable**: Same URN across dev/staging/prod environments
- **Human-readable**: Can be used in audit logs and governance reports
- **Parseable**: `BiUrn.parse("urn:bi:view:sales:mv_sales_daily")` returns a typed object
- **Unique**: Registry enforces uniqueness at load time (RuntimeError on duplicates)

---

## 4. Action Taxonomy

BI operations are NOT CRUD. They have specific business semantics:

| Action | Meaning | Maps To (Phase 6) | Cost |
|--------|---------|-------------------|------|
| `VIEW` | Passive dashboard consumption | GET /kpi/summary (Tier 1) | Low |
| `INTERACT` | Active filter/dimension adjustment | GET /charts/*, POST /analyze (Tier 2-3) | Medium |
| `EXPORT` | Async data extraction to file | POST /exports (S6-4) | High |
| `MANAGE` | Create/modify/publish BI assets | Future P7-x | Administrative |

**Privilege hierarchy**: VIEW < INTERACT < EXPORT < MANAGE

This taxonomy is defined as `BIAction` enum. No enforcement logic exists yet —
this is vocabulary only, to be consumed by future RBAC policies.

---

## 5. BIAsset Model

```python
class BIAsset(BaseModel):
    urn: BiUrn                          # Globally unique identifier
    display_name: str                   # Human-readable name
    description: str                    # Business-level description
    owner: str                          # Responsible team/role
    freshness: DataFreshness            # real_time | near_real_time | snapshot
    source_phase: str                   # Which phase created this (e.g., "S6-3")
    semantic_ref: Optional[str]         # Back-reference to semantic layer enum
    tenant_id: Optional[str]            # None = system-wide, set = tenant-scoped
    tags: list[str]                     # Freeform tags for filtering
    created_at: str                     # ISO 8601 registration timestamp
    deprecated: bool                    # Retirement flag
```

**Frozen model**: All instances are immutable (Pydantic `frozen=True`).

**Tenant awareness**: `tenant_id=None` means system-wide (shared across all tenants).
Future phases can register tenant-specific custom reports by setting `tenant_id`.

---

## 6. Registered Assets (18 total)

### Views (3)

| URN | Display Name | Freshness | Phase |
|-----|-------------|-----------|-------|
| `urn:bi:view:sales:mv_sales_daily` | Daily Sales Revenue | Near-real-time | S6-2 |
| `urn:bi:view:finance:rpt_receivables_summary` | Accounts Receivable Summary | Real-time | S6-1 |
| `urn:bi:view:finance:rpt_cash_flow_daily` | Daily Cash Flow | Real-time | S6-1 |

### Metrics (7)

| URN | Display Name | Domain |
|-----|-------------|--------|
| `urn:bi:metric:sales:revenue` | Revenue | Sales |
| `urn:bi:metric:sales:transaction_count` | Transaction Count | Sales |
| `urn:bi:metric:finance:outstanding_balance` | Outstanding Receivables | Finance |
| `urn:bi:metric:finance:receivable_entry_count` | Receivable Entry Count | Finance |
| `urn:bi:metric:finance:net_cash_change` | Net Cash Change | Finance |
| `urn:bi:metric:finance:running_balance` | Running Cash Balance | Finance |
| `urn:bi:metric:finance:cash_transaction_count` | Cash Transaction Count | Finance |

### Dashboards (3)

| URN | Display Name |
|-----|-------------|
| `urn:bi:dashboard:executive:executive_summary` | Executive Summary Dashboard |
| `urn:bi:dashboard:sales:sales_trend` | Sales Revenue Trend |
| `urn:bi:dashboard:finance:cash_flow_trend` | Cash Flow Trend |

### Reports (3)

| URN | Display Name |
|-----|-------------|
| `urn:bi:report:sales:adhoc_sales_analysis` | Ad-hoc Sales Analysis |
| `urn:bi:report:finance:adhoc_receivables_analysis` | Ad-hoc Receivables Analysis |
| `urn:bi:report:finance:adhoc_cash_flow_analysis` | Ad-hoc Cash Flow Analysis |

### Export Templates (2)

| URN | Display Name |
|-----|-------------|
| `urn:bi:export_template:sales:sales_daily_csv` | Sales Daily Export (CSV) |
| `urn:bi:export_template:sales:sales_daily_xlsx` | Sales Daily Export (Excel) |

---

## 7. Constraints Compliance

| Constraint | Status |
|-----------|--------|
| No database changes | ✅ In-memory model only |
| No RBAC / enforcement logic | ✅ Pure data structures |
| No middleware / if-statements | ✅ Models and registry only |
| Type safety (Pydantic) | ✅ All models are Pydantic BaseModel |
| Tenant context reserved | ✅ `BIAsset.tenant_id: Optional[str]` |
| Boot Contract (no frozen file modification) | ✅ New `core/governance/` directory only |

---

## 8. Future Phases

| Phase | What It Adds |
|-------|-------------|
| P7-1 | Policy model: `(Role, BIAsset, BIAction) → Allow/Deny` |
| P7-2 | Enforcement middleware: `@require_bi_permission(asset_urn, action)` |
| P7-3 | Audit trail: log every (user, asset, action, timestamp) |
| P7-4 | Tenant-scoped custom assets: per-tenant dashboards and reports |

---

**Document Status**: ✅ COMPLETE
**Last Updated**: 2026-02-09
