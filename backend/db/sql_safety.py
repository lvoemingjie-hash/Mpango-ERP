"""
S8-SEC: SQL Safety Utilities — Identifier Validation for Dynamic SQL.

This module provides a single source of truth for validating SQL identifiers
(schema names, view names, table names) before they are interpolated into
SQL strings via f-strings.

Background:
    PostgreSQL does not support bind parameters for DDL identifiers
    (schema names, table names, view names). When we must use f-string
    interpolation (e.g. SET LOCAL search_path, CREATE SCHEMA, REFRESH
    MATERIALIZED VIEW), we validate the identifier against a strict
    allowlist pattern first.

Usage:
    from db.sql_safety import validate_identifier

    validate_identifier(tenant_schema, "tenant_schema")
    await session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
"""
import re

__all__ = ["validate_identifier", "SAFE_IDENTIFIER_RE"]

# Strict pattern: starts with letter/underscore, then alphanumerics/underscores.
# Max 63 chars (PostgreSQL NAMEDATALEN - 1).
SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def validate_identifier(value: str, label: str = "identifier") -> str:
    """Validate that *value* is a safe SQL identifier.

    Raises ValueError if the value contains anything other than
    ASCII letters, digits, and underscores — preventing SQL injection
    through string-concatenated queries.

    Args:
        value: The identifier string to validate.
        label: Human-readable label for error messages.

    Returns:
        The validated value (unchanged).

    Raises:
        ValueError: If the value does not match the safe pattern.
    """
    if not SAFE_IDENTIFIER_RE.match(value):
        raise ValueError(
            f"Unsafe {label}: {value!r} — must match {SAFE_IDENTIFIER_RE.pattern}"
        )
    return value
