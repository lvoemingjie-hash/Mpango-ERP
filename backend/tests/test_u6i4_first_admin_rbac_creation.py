"""U6-I4 first tenant admin and RBAC creation service tests."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from core.security import hash_password
from database.session import AsyncSessionLocal, async_engine
from services.owner_credential_service import (
    OWNER_ADMIN_PERMISSION_REGISTRY,
    OwnerCredentialSetupAdminCreationError,
    OwnerCredentialSetupConsumeResult,
    OwnerCredentialSetupService,
)


pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[2]
AUTH_ROUTE_PATH = ROOT / "backend" / "api" / "v1" / "auth.py"
OWNER_CREDENTIAL_SERVICE_PATH = ROOT / "backend" / "services" / "owner_credential_service.py"
TENANT_PROVISIONING_SERVICE_PATH = ROOT / "backend" / "services" / "tenant_provisioning_service.py"
CANONICAL_ADMIN_PERMISSION_CODES = {code for code, _description in OWNER_ADMIN_PERMISSION_REGISTRY}


@pytest.fixture
async def tenant_schemas():
    schemas: list[str] = []
    try:
        yield schemas
    finally:
        async with async_engine.begin() as connection:
            for schema in reversed(schemas):
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


async def _create_tenant_auth_schema(schema: str) -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(
            text(
                f'CREATE TABLE "{schema}".users ('
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                "email VARCHAR(255) NOT NULL UNIQUE,"
                "password_hash VARCHAR(255) NOT NULL,"
                "full_name TEXT,"
                "is_active BOOLEAN NOT NULL DEFAULT true,"
                "created_at TIMESTAMPTZ DEFAULT now(),"
                "updated_at TIMESTAMPTZ DEFAULT now(),"
                "is_deleted BOOLEAN DEFAULT false,"
                "deleted_at TIMESTAMPTZ,"
                "created_by UUID,"
                "updated_by UUID)"
            )
        )
        await connection.execute(
            text(
                f'CREATE TABLE "{schema}".roles ('
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                "name VARCHAR(100) NOT NULL UNIQUE,"
                "description TEXT,"
                "created_at TIMESTAMPTZ DEFAULT now(),"
                "updated_at TIMESTAMPTZ DEFAULT now(),"
                "is_deleted BOOLEAN DEFAULT false,"
                "deleted_at TIMESTAMPTZ,"
                "created_by UUID,"
                "updated_by UUID)"
            )
        )
        await connection.execute(
            text(
                f'CREATE TABLE "{schema}".permissions ('
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                "code VARCHAR(100) NOT NULL UNIQUE,"
                "description TEXT,"
                "created_at TIMESTAMPTZ DEFAULT now(),"
                "updated_at TIMESTAMPTZ DEFAULT now(),"
                "is_deleted BOOLEAN DEFAULT false,"
                "deleted_at TIMESTAMPTZ,"
                "created_by UUID,"
                "updated_by UUID)"
            )
        )
        await connection.execute(
            text(
                f'CREATE TABLE "{schema}".user_roles ('
                f'user_id UUID NOT NULL REFERENCES "{schema}".users(id) ON DELETE CASCADE,'
                f'role_id UUID NOT NULL REFERENCES "{schema}".roles(id) ON DELETE CASCADE,'
                "PRIMARY KEY (user_id, role_id))"
            )
        )
        await connection.execute(
            text(
                f'CREATE TABLE "{schema}".role_permissions ('
                f'role_id UUID NOT NULL REFERENCES "{schema}".roles(id) ON DELETE CASCADE,'
                f'permission_id UUID NOT NULL REFERENCES "{schema}".permissions(id) ON DELETE CASCADE,'
                "PRIMARY KEY (role_id, permission_id))"
            )
        )


def _schema_name() -> str:
    return f't_u6i4_{uuid.uuid4().hex[:20]}'


def _consume_result(
    *,
    tenant_schema: str,
    owner_email: str = "u6i4_owner@example.com",
    password_hash: str | None = None,
) -> OwnerCredentialSetupConsumeResult:
    return OwnerCredentialSetupConsumeResult(
        registration_id=uuid.uuid4(),
        tenant_schema=tenant_schema,
        owner_email=owner_email,
        password_hash=password_hash or hash_password("OwnerSetup123!"),
    )


async def _table_count(schema: str, table: str) -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(text(f'SELECT count(*) FROM "{schema}"."{table}"'))


async def _owner_row(schema: str, owner_email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(f'SELECT id, email, password_hash, is_active FROM "{schema}".users WHERE email = :email'),
                {"email": owner_email},
            )
        ).mappings().one_or_none()


async def _role_row(schema: str, role_name: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(f'SELECT id, name, description FROM "{schema}".roles WHERE name = :name'),
                {"name": role_name},
            )
        ).mappings().one_or_none()


async def _permission_codes(schema: str) -> set[str]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(text(f'SELECT code FROM "{schema}".permissions ORDER BY code'))
        ).scalars().all()
        return set(rows)


async def _admin_permission_codes(schema: str) -> set[str]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    f'SELECT p.code FROM "{schema}".permissions p '
                    f'JOIN "{schema}".role_permissions rp ON rp.permission_id = p.id '
                    f'JOIN "{schema}".roles r ON r.id = rp.role_id '
                    "WHERE r.name = 'admin'"
                )
            )
        ).scalars().all()
        return set(rows)


async def _owner_role_count(schema: str, owner_email: str) -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            text(
                f'SELECT count(*) FROM "{schema}".user_roles ur '
                f'JOIN "{schema}".users u ON u.id = ur.user_id '
                f'JOIN "{schema}".roles r ON r.id = ur.role_id '
                "WHERE u.email = :email AND r.name = 'admin'"
            ),
            {"email": owner_email},
        )


async def _public_wholesaler_count() -> int:
    async with AsyncSessionLocal() as session:
        exists = await session.scalar(text("SELECT to_regclass('public.wholesalers')"))
        if exists is None:
            return 0
        return await session.scalar(text("SELECT count(*) FROM public.wholesalers"))


async def test_create_first_admin_user_role_permissions_and_mappings(tenant_schemas):
    tenant_schema = _schema_name()
    tenant_schemas.append(tenant_schema)
    await _create_tenant_auth_schema(tenant_schema)
    setup = _consume_result(tenant_schema=tenant_schema)
    public_count_before = await _public_wholesaler_count()

    async with AsyncSessionLocal() as session:
        result = await OwnerCredentialSetupService(session).create_first_admin_rbac(setup)
        await session.commit()

    owner = await _owner_row(tenant_schema, setup.owner_email)
    admin_role = await _role_row(tenant_schema, "admin")
    assert result.action == "created"
    assert result.registration_id == setup.registration_id
    assert result.tenant_schema == tenant_schema
    assert result.owner_email == setup.owner_email
    assert result.user_id == owner["id"]
    assert result.role_id == admin_role["id"]
    assert owner["password_hash"] == setup.password_hash
    assert owner["is_active"] is True
    assert admin_role["description"] == "Administrator with full access"
    assert await _permission_codes(tenant_schema) == CANONICAL_ADMIN_PERMISSION_CODES
    assert await _admin_permission_codes(tenant_schema) == CANONICAL_ADMIN_PERMISSION_CODES
    assert await _owner_role_count(tenant_schema, setup.owner_email) == 1
    assert await _public_wholesaler_count() == public_count_before


async def test_first_admin_creation_is_idempotent_without_duplicate_rbac(tenant_schemas):
    tenant_schema = _schema_name()
    tenant_schemas.append(tenant_schema)
    await _create_tenant_auth_schema(tenant_schema)
    setup = _consume_result(tenant_schema=tenant_schema)

    async with AsyncSessionLocal() as session:
        first = await OwnerCredentialSetupService(session).create_first_admin_rbac(setup)
        second = await OwnerCredentialSetupService(session).create_first_admin_rbac(setup)
        await session.commit()

    assert first.action == "created"
    assert second.action == "existing"
    assert first.user_id == second.user_id
    assert first.role_id == second.role_id
    assert await _table_count(tenant_schema, "users") == 1
    assert await _table_count(tenant_schema, "roles") == 1
    assert await _table_count(tenant_schema, "permissions") == len(CANONICAL_ADMIN_PERMISSION_CODES)
    assert await _table_count(tenant_schema, "user_roles") == 1
    assert await _table_count(tenant_schema, "role_permissions") == len(CANONICAL_ADMIN_PERMISSION_CODES)


async def test_reconciles_existing_owner_user_with_provided_hash_and_missing_rbac(tenant_schemas):
    tenant_schema = _schema_name()
    tenant_schemas.append(tenant_schema)
    await _create_tenant_auth_schema(tenant_schema)
    setup = _consume_result(tenant_schema=tenant_schema)
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(f'INSERT INTO "{tenant_schema}".users (email, password_hash, is_active) VALUES (:email, :hash, false)'),
            {"email": setup.owner_email, "hash": hash_password("OldCredential123!")},
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        result = await OwnerCredentialSetupService(session).create_first_admin_rbac(setup)
        await session.commit()

    owner = await _owner_row(tenant_schema, setup.owner_email)
    assert result.action == "existing"
    assert owner["password_hash"] == setup.password_hash
    assert owner["is_active"] is True
    assert await _owner_role_count(tenant_schema, setup.owner_email) == 1
    assert await _admin_permission_codes(tenant_schema) == CANONICAL_ADMIN_PERMISSION_CODES


async def test_cross_tenant_isolation_only_writes_requested_schema(tenant_schemas):
    target_schema = _schema_name()
    other_schema = _schema_name()
    tenant_schemas.extend([target_schema, other_schema])
    await _create_tenant_auth_schema(target_schema)
    await _create_tenant_auth_schema(other_schema)
    setup = _consume_result(tenant_schema=target_schema)

    async with AsyncSessionLocal() as session:
        await OwnerCredentialSetupService(session).create_first_admin_rbac(setup)
        await session.commit()

    assert await _table_count(target_schema, "users") == 1
    assert await _table_count(target_schema, "roles") == 1
    assert await _table_count(target_schema, "permissions") == len(CANONICAL_ADMIN_PERMISSION_CODES)
    assert await _table_count(other_schema, "users") == 0
    assert await _table_count(other_schema, "roles") == 0
    assert await _table_count(other_schema, "permissions") == 0
    assert await _table_count(other_schema, "user_roles") == 0
    assert await _table_count(other_schema, "role_permissions") == 0


@pytest.mark.parametrize(
    "setup",
    [
        _consume_result(tenant_schema=""),
        _consume_result(tenant_schema="missing_schema"),
        _consume_result(tenant_schema="bad-schema-name"),
        _consume_result(tenant_schema="missing_hash", password_hash=""),
    ],
)
async def test_fail_closed_for_missing_absent_invalid_schema_or_missing_hash(setup):
    async with AsyncSessionLocal() as session:
        with pytest.raises(OwnerCredentialSetupAdminCreationError):
            await OwnerCredentialSetupService(session).create_first_admin_rbac(setup)
        await session.rollback()


async def test_no_public_endpoint_placeholder_password_or_provisioning_behavior_change():
    service_source = OWNER_CREDENTIAL_SERVICE_PATH.read_text(encoding="utf-8")
    provisioning_source = TENANT_PROVISIONING_SERVICE_PATH.read_text(encoding="utf-8")
    assert "placeholder" not in service_source.lower()
    assert "random" not in service_source.lower()
    assert "generate_verification_token()" in service_source
    assert "create_first_admin_rbac" not in provisioning_source
