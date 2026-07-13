"""DC-10F-R1 payment method migration and bootstrap tests."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from models.tenant_onboarding import TenantRegistration
from models.wholesaler import Wholesaler


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_032 = BACKEND_DIR / "alembic" / "versions" / "032_payment_method_integrity.py"
CANONICAL_CONSTRAINT = "ck_payments_method_canonical"


def _database_url() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)


def _engine():
    return create_engine(_database_url(), future=True)


def _schema_name() -> str:
    return f"t_{uuid.uuid4().hex}"


def _qualified(schema: str, relation: str) -> str:
    return f'"{schema}".{relation}'


def _load_migration_032():
    spec = importlib.util.spec_from_file_location("dc10f_migration_032", MIGRATION_032)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration_032(connection, *, tenant_schema: str | None = None) -> None:
    module = _load_migration_032()
    migration_context = MigrationContext.configure(connection)
    operations = Operations(migration_context)
    original_op = module.op
    original_context = module.context
    module.op = operations
    module.context = SimpleNamespace(
        get_x_argument=lambda as_dictionary=True: (
            {"tenant_schema": tenant_schema} if as_dictionary and tenant_schema is not None else {}
        )
    )
    try:
        module.upgrade()
    finally:
        module.op = original_op
        module.context = original_context


def _ensure_public_prerequisites(connection) -> None:
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    connection.execute(
        text(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reporting_role') "
            "THEN CREATE ROLE reporting_role NOLOGIN; END IF; "
            "END $$"
        )
    )
    Wholesaler.__table__.create(connection, checkfirst=True)
    TenantRegistration.__table__.create(connection, checkfirst=True)


def _cleanup(connection, schemas: list[str]) -> None:
    connection.execute(
        text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'dc10f_r1_%@example.com'")
    )
    connection.execute(text("DELETE FROM public.wholesalers WHERE code LIKE 'DC10FR1%'"))
    for schema in schemas:
        assert schema.startswith("t_") and schema.replace("_", "").isalnum()
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def _register_tenant(
    connection,
    schema: str,
    *,
    registration_status: str = "provisioning",
    wholesaler_status: str = "active",
    tenant_schema: str | None = None,
) -> uuid.UUID:
    wholesaler_id = uuid.UUID(schema.removeprefix("t_"))
    connection.execute(
        text(
            "INSERT INTO public.wholesalers (id, code, name, status) "
            "VALUES (:id, :code, :name, :status)"
        ),
        {
            "id": wholesaler_id,
            "code": f"DC10FR1{uuid.uuid4().hex[:8].upper()}",
            "name": "DC10F R1 Test Wholesaler",
            "status": wholesaler_status,
        },
    )
    connection.execute(
        text(
            "INSERT INTO public.tenant_registrations ("
            "id, company_name, country, owner_email, status, email_verified_at, "
            "provisioning_started_at, password_hash_cleared_at, wholesaler_id, "
            "tenant_schema, expires_at"
            ") VALUES ("
            ":id, :company_name, 'KE', :owner_email, :status, now(), now(), now(), "
            ":wholesaler_id, :tenant_schema, now() + interval '1 hour'"
            ")"
        ),
        {
            "id": uuid.uuid4(),
            "company_name": "DC10F R1 Company",
            "owner_email": f"dc10f_r1_{uuid.uuid4().hex}@example.com",
            "status": registration_status,
            "wholesaler_id": wholesaler_id,
            "tenant_schema": tenant_schema or schema,
        },
    )
    return wholesaler_id


def _create_payments_table(
    connection,
    schema: str,
    *,
    constraint_sql: str | None = None,
) -> None:
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    constraint_clause = f", {constraint_sql}" if constraint_sql else ""
    connection.execute(
        text(
            f"""
            CREATE TABLE {_qualified(schema, 'payments')} (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                method VARCHAR(50)
                {constraint_clause}
            )
            """
        )
    )


def _constraint_def(connection, schema: str) -> str | None:
    return connection.execute(
        text(
            "SELECT pg_get_constraintdef(c.oid, true) "
            "FROM pg_constraint c "
            "WHERE c.conrelid = to_regclass(:qualified_table) "
            "AND c.conname = :constraint_name"
        ),
        {
            "qualified_table": _qualified(schema, "payments"),
            "constraint_name": CANONICAL_CONSTRAINT,
        },
    ).scalar()


def _constraint_names(connection, schema: str) -> list[str]:
    return list(
        connection.execute(
            text(
                "SELECT c.conname FROM pg_constraint c "
                "WHERE c.conrelid = to_regclass(:qualified_table) ORDER BY c.conname"
            ),
            {"qualified_table": _qualified(schema, "payments")},
        ).scalars()
    )


def _assert_canonical_constraint(connection, schema: str) -> None:
    constraint_def = _constraint_def(connection, schema)
    assert constraint_def is not None
    assert "cash" in constraint_def
    assert "transfer" in constraint_def
    assert "credit" in constraint_def


def test_fresh_bootstrap_payments_table_has_canonical_method_constraint():
    from scripts.bootstrap_tenant_schema import bootstrap

    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])

        asyncio.run(bootstrap(schema, os.environ["DATABASE_URL"]))

        with engine.begin() as connection:
            _assert_canonical_constraint(connection, schema)
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_registered_existing_tenant_receives_constraint_and_second_run_is_idempotent():
    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _register_tenant(connection, schema)
            _create_payments_table(connection, schema)

            _run_migration_032(connection)
            _assert_canonical_constraint(connection, schema)
            first_constraints = _constraint_names(connection, schema)

            _run_migration_032(connection)
            assert _constraint_names(connection, schema) == first_constraints
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_noncanonical_payment_row_fails_before_constraint_mutation():
    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _register_tenant(connection, schema)
            _create_payments_table(connection, schema)
            connection.execute(text(f"INSERT INTO {_qualified(schema, 'payments')} (method) VALUES ('banana')"))

            with pytest.raises(RuntimeError, match="non-canonical or NULL"):
                _run_migration_032(connection)

            assert CANONICAL_CONSTRAINT not in _constraint_names(connection, schema)
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_wrong_same_name_constraint_fails_closed():
    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _register_tenant(connection, schema)
            _create_payments_table(
                connection,
                schema,
                constraint_sql=f"CONSTRAINT {CANONICAL_CONSTRAINT} CHECK (method IN ('cash'))",
            )

            with pytest.raises(RuntimeError, match="incompatible"):
                _run_migration_032(connection)
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_equivalent_legacy_constraint_is_renamed_without_duplicate():
    schema = _schema_name()
    legacy_name = "legacy_payments_method_canonical"
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _register_tenant(connection, schema)
            _create_payments_table(
                connection,
                schema,
                constraint_sql=(
                    f"CONSTRAINT {legacy_name} "
                    "CHECK (method IN ('cash', 'transfer', 'credit'))"
                ),
            )

            _run_migration_032(connection)

            names = _constraint_names(connection, schema)
            assert CANONICAL_CONSTRAINT in names
            assert legacy_name not in names
            assert names.count(CANONICAL_CONSTRAINT) == 1
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_unregistered_t_schema_is_untouched():
    registered_schema = _schema_name()
    rogue_schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [registered_schema, rogue_schema])
            _register_tenant(connection, registered_schema)
            _create_payments_table(connection, registered_schema)
            _create_payments_table(connection, rogue_schema)

            _run_migration_032(connection)

            _assert_canonical_constraint(connection, registered_schema)
            assert CANONICAL_CONSTRAINT not in _constraint_names(connection, rogue_schema)
            connection.execute(text(f"INSERT INTO {_qualified(rogue_schema, 'payments')} (method) VALUES ('banana')"))
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [registered_schema, rogue_schema])
        engine.dispose()


def test_invalid_registry_schema_fails_closed_before_mutation():
    derived_schema = _schema_name()
    wrong_schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [derived_schema, wrong_schema])
            _register_tenant(connection, derived_schema, tenant_schema=wrong_schema)
            _create_payments_table(connection, wrong_schema)

            with pytest.raises(RuntimeError, match="does not match wholesaler-derived schema"):
                _run_migration_032(connection)

            assert CANONICAL_CONSTRAINT not in _constraint_names(connection, wrong_schema)
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [derived_schema, wrong_schema])
        engine.dispose()


def test_tenant_schema_argument_invalid_identifier_fails_sanitized():
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)

            with pytest.raises(RuntimeError, match="tenant_schema argument: tenant_schema is not a valid") as exc_info:
                _run_migration_032(connection, tenant_schema='t_bad; DROP SCHEMA public;')

            assert "DROP SCHEMA" not in str(exc_info.value)
    finally:
        engine.dispose()


def test_registered_target_missing_payments_table_fails_closed():
    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _register_tenant(connection, schema)
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))

            with pytest.raises(RuntimeError, match="payments: table is missing"):
                _run_migration_032(connection, tenant_schema=schema)
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_canonical_methods_insert_and_banana_insert_fails_after_migration():
    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _register_tenant(connection, schema)
            _create_payments_table(connection, schema)
            _run_migration_032(connection)

            for method in ("cash", "transfer", "credit"):
                connection.execute(
                    text(f"INSERT INTO {_qualified(schema, 'payments')} (method) VALUES (:method)"),
                    {"method": method},
                )

            savepoint = connection.begin_nested()
            with pytest.raises(Exception, match="ck_payments_method_canonical"):
                connection.execute(text(f"INSERT INTO {_qualified(schema, 'payments')} (method) VALUES ('banana')"))
            savepoint.rollback()
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()
