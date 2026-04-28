# Project Overview

This document provides the essential project context that every AI agent needs before doing any work on Mpango ERP.

## What Is Mpango ERP

Mpango ERP is a multi-tenant wholesale-retail ERP system built for the African market. It supports digital operations for Kenyan wholesalers and their retailer networks.

**Version**: 0.2.0
**Repository**: The repository is the operational source of truth.

## Architecture

- **Tenancy model**: Schema-per-tenant (DR-001). Each tenant gets an isolated PostgreSQL schema (`t_xxx`). This is non-negotiable.
- **Backend**: Python / FastAPI / SQLAlchemy / Alembic
- **Frontend**: React / Vite
- **Database**: PostgreSQL with schema-per-tenant isolation
- **Platform layer**: Public-schema tables with `platform_` prefix, extending the SaaS layer without touching tenant schemas

## Current Development Tracks

| Track | Branch | Focus |
|-------|--------|-------|
| Product | `product-dev` | ERP business modules, frontend, retailer portal, mobile web |
| Platform | `platform-dev` | Tenant registry, platform admin, audit, monitoring |

**Authority rule**: Product line and platform line are parallel only in execution, not in authority. Product continuity wins when tradeoffs appear.

## Current Phase

The immediate goal is to make the ERP genuinely usable for real wholesalers while preserving strict tenant isolation and preparing the path to SaaS platform expansion.

### Product Status (v0.2.0)

Core modules are production-ready: authentication (JWT + refresh), RBAC (22+ permissions), order management (full state machine), inventory (SKU + concurrency), payments, finance, dashboard/BI, data export, and audit trail.

### Platform Status

Platform track has completed 7 closed slices: routing scaffold, boundary note, information model, tenant lifecycle scaffold, platform audit logs, operational reporting stats, and audit activity enhancement. All platform API endpoints are read-only (8 endpoints, 55 tests).

## Primary Customer Hierarchy

1. **Primary**: Wholesaler
2. **Secondary**: Invited retailer under wholesaler control
3. **Future**: Supplier workflows upstream, end-customer workflows downstream

## Key Constraints

- Multi-tenancy is a first-order architectural rule
- Platform work extends the SaaS layer without forcing the product core to adapt
- Schema and API changes must follow documented contracts
- Database changes go through Alembic migrations only
- All AI work must be auditable through repo docs, decision records, and ledger entries

## Where To Go Next

After reading this document, follow the read order defined in `docs/ai/README.md`.
