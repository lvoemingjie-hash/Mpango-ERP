"""P21 Durable Approval Store -- runtime substrate (P21-D-B NON-EXECUTING SKELETON).

This package is the first runtime substrate of P21-D. It defines the SQLAlchemy
ORM models for the five merged P21-C1 public durable approval tables and a
NON-EXECUTING adapter skeleton that maps the P20-B in-memory store surface to
those tables. It does NOT become the live store: the running P20-B store stays
in-memory / existing-safe, no P20 route or service is rewired, no migration is
added, and no controlled action is executed. Approval is not execution and
durability is not execution: ``execution_allowed`` stays false, ``executed``
stays false, and ``execution_gate`` stays "blocked".

Scope of this slice (P21-D-B):
  - ``models``  -- ORM model definitions for the five P21-C1 public tables.
  - ``adapter`` -- a non-executing adapter SKELETON exposing the planned surface
    frozen in docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md
    (section 4) and the P21-B storage-adapter interface contract
    (PLATFORM_PRODUCT_P21_DURABLE_APPROVAL_SCHEMA_PLAN.md section 7).

NOT in this slice (deferred to separately CTO-gated runtime slices): the actual
adapter implementation against a live session (P21-D-1) and the runtime storage
cutover / feature flag (P21-D-2). This package adds NO router and is NOT imported
by api.v1.platform.p20 (services / routes) or by api.app.
"""
