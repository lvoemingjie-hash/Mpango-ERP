"""
Platform Track P12 -- Support Console API.

Request-scoped diagnostic sessions for platform operators.
Boundaries:
  - No migrations.
  - No persistent session storage (in-memory only).
  - No frontend UI.
  - No auth/RBAC/tenancy/session/payment changes.
  - Reuses P10 guard for identity-only enforcement.
  - Reuses P10 services for diagnostic data gathering.
  - Reuses P10 redact_metadata for data redaction.
  - Creates audit events via platform_audit_service for session lifecycle.
"""
