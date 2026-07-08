"""P21 Durable Approval Store -- runtime substrate (models + adapter).

This package is the runtime substrate of P21-D. It defines the SQLAlchemy ORM
models for the five merged P21-C1 public durable approval tables and the durable
approval store adapter that reads/writes them. The package contains:
  - ``models``  -- ORM model definitions for the five P21-C1 public tables.
  - ``adapter`` -- the durable approval store adapter: a non-executing skeleton
    (``DurableApprovalStore``, P21-D-B) plus the concrete DB read/write adapter
    (``DurableApprovalStoreAdapter``, P21-D-C).

The concrete adapter is selected by the P20 durable-approval service through the
P21-D-D readiness gate as the durable storage backend (production default); an
explicit in-memory backend is retained for test/dev only. The adapter never
self-elects as the live store and NEVER executes a controlled action. Approval
is not execution and durability is not execution: ``execution_allowed`` stays
false, ``executed`` stays false, and ``execution_gate`` stays "blocked".

This package adds NO router. The durable tables are created by migration 020
(P21-C1); this package adds no migration of its own.
"""
