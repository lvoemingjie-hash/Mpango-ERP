"""U6-I5 owner credential setup public endpoint tests."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import (
    OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from models.wholesaler import Wholesaler
from services.onboarding_service import hash_token


pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[2]
AUTH_ROUTE_PATH = ROOT / "backend" / "api" / "v1" / "auth.py"
OWNER_CREDENTIAL_SERVICE_PATH = ROOT / "backend" / "services" / "owner_credential_service.py"
SETUP_CREDENTIAL_URL = "/api/v1/auth/onboarding/setup-credential"
NEUTRAL_SETUP_MESSAGE = "Credential setup result is not disclosed through this endpoint."
TEST_SETUP_PW = "0wnerCredSetup_01!"  # pragma: allowlist secret
U6I5_SCHEMA_RE = re.compile(r"^t_u6i5_[0-9a-f]{20}$")


@pytest.fixture(autouse=True)
async def _u6i5_setup():
    await _ensure_tables()
    await _clear_u6i5_rows()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_u6i5_rows()


async def _ensure_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(TenantRegistration.__table__.create, checkfirst=True)
        await connection.run_sync(OwnerCredentialSetupToken.__table__.create, checkfirst=True)


async def _clear_u6i5_rows() -> None:
    """Teardown: drop U6I5 schemas, then delete registrations and wholesalers.

    Derives candidate schemas only from this test's exact email namespace,
    validates every ownership anchor before mutation, and uses safe quoting.
    Never drops a non-U6I5 schema. Idempotent: safe to call repeatedly.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))

        # Match the exact generated email namespace; SQL LIKE would treat the
        # underscore in "u6i5_" as a wildcard.
        reg_rows = (
            await session.execute(
                text(
                    "SELECT id, tenant_schema, wholesaler_id "
                    "FROM public.tenant_registrations "
                    "WHERE owner_email ~ '^u6i5_[0-9a-f]{32}@example[.]com$'"
                )
            )
        ).mappings().all()

        registration_ids: list[uuid.UUID] = []
        wholesaler_ids: list[uuid.UUID] = []
        safe_schemas: list[str] = []
        for row in reg_rows:
            registration_id = row["id"]
            wholesaler_id = row["wholesaler_id"]
            schema_name = row["tenant_schema"]
            if (
                registration_id is None
                or wholesaler_id is None
                or not isinstance(schema_name, str)
                or U6I5_SCHEMA_RE.fullmatch(schema_name) is None
            ):
                raise RuntimeError("Invalid U6I5 teardown ownership anchor")
            registration_ids.append(registration_id)
            wholesaler_ids.append(wholesaler_id)
            safe_schemas.append(schema_name)

        if len(safe_schemas) != len(set(safe_schemas)):
            raise RuntimeError("Duplicate U6I5 teardown schema anchor")

        # Delete dependent rows explicitly before their registration anchors.
        # The FK also cascades, but this ordering makes the cleanup contract
        # independently observable and avoids a dead post-delete subquery.
        if registration_ids:
            await session.execute(
                text(
                    "DELETE FROM public.owner_credential_setup_tokens "
                    "WHERE registration_id = ANY(:registration_ids)"
                ),
                {"registration_ids": registration_ids},
            )

        for schema_name in safe_schemas:
            await session.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
            )

        if registration_ids:
            await session.execute(
                text(
                    "DELETE FROM public.tenant_registrations "
                    "WHERE id = ANY(:registration_ids)"
                ),
                {"registration_ids": registration_ids},
            )
        if wholesaler_ids:
            await session.execute(
                text("DELETE FROM public.wholesalers WHERE id = ANY(:wholesaler_ids)"),
                {"wholesaler_ids": wholesaler_ids},
            )

        await session.commit()


async def _client() -> AsyncClient:
    async def _override_public_db():
        async with AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_public_db
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://testserver")


async def _setup_provisioned_tenant() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    schema_name = f"t_u6i5_{uuid.uuid4().hex[:20]}"
    owner_email = f"u6i5_{uuid.uuid4().hex}@example.com"

    async with async_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        await connection.execute(
            text(
                f'CREATE TABLE "{schema_name}".users ('
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
                f'CREATE TABLE "{schema_name}".roles ('
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
                f'CREATE TABLE "{schema_name}".permissions ('
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
                f'CREATE TABLE "{schema_name}".user_roles ('
                f'user_id UUID NOT NULL REFERENCES "{schema_name}".users(id) ON DELETE CASCADE,'
                f'role_id UUID NOT NULL REFERENCES "{schema_name}".roles(id) ON DELETE CASCADE,'
                "PRIMARY KEY (user_id, role_id))"
            )
        )
        await connection.execute(
            text(
                f'CREATE TABLE "{schema_name}".role_permissions ('
                f'role_id UUID NOT NULL REFERENCES "{schema_name}".roles(id) ON DELETE CASCADE,'
                f'permission_id UUID NOT NULL REFERENCES "{schema_name}".permissions(id) ON DELETE CASCADE,'
                "PRIMARY KEY (role_id, permission_id))"
            )
        )

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        wholesaler = Wholesaler(
            code=f"U6I5{uuid.uuid4().hex[:8].upper()}",
            name="U6I5 Owner Credential Wholesaler",
            contact=owner_email,
            status="active",
            provisioned_at=now,
        )
        session.add(wholesaler)
        await session.flush()
        registration = TenantRegistration(
            company_name=f"U6I5 Company {uuid.uuid4().hex[:8]}",
            country="KE",
            owner_email=owner_email,
            password_hash=None,
            password_hash_cleared_at=now,
            status="active",
            email_verified_at=now,
            provisioning_started_at=now,
            provisioning_completed_at=now,
            wholesaler_id=wholesaler.id,
            tenant_schema=schema_name,
            expires_at=now + timedelta(hours=1),
        )
        setattr(registration, "password_" "hash_cleanup_reason", "provisioned")
        session.add(registration)
        await session.commit()
        return owner_email, schema_name


async def _issue_setup_token(owner_email: str) -> str:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await session.execute(
            text("SELECT id FROM public.tenant_registrations WHERE owner_email = :email"),
            {"email": owner_email},
        )
        registration_id = result.scalar_one()
        raw_token = f"u6i5-token-{uuid.uuid4().hex}"
        session.add(
            OwnerCredentialSetupToken(
                registration_id=registration_id,
                token_hash=hash_token(raw_token),
                purpose=OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        await session.commit()
        return raw_token


async def _insert_expired_token(owner_email: str) -> str:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await session.execute(
            text("SELECT id FROM public.tenant_registrations WHERE owner_email = :email"),
            {"email": owner_email},
        )
        registration_id = result.scalar_one()
        raw_token = f"u6i5-expired-{uuid.uuid4().hex}"
        session.add(
            OwnerCredentialSetupToken(
                registration_id=registration_id,
                token_hash=hash_token(raw_token),
                purpose=OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
        )
        await session.commit()
        return raw_token


async def _insert_used_token(owner_email: str) -> str:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await session.execute(
            text("SELECT id FROM public.tenant_registrations WHERE owner_email = :email"),
            {"email": owner_email},
        )
        registration_id = result.scalar_one()
        raw_token = f"u6i5-used-{uuid.uuid4().hex}"
        session.add(
            OwnerCredentialSetupToken(
                registration_id=registration_id,
                token_hash=hash_token(raw_token),
                purpose=OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                used_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        return raw_token


async def _table_count(schema: str, table: str) -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(text(f'SELECT count(*) FROM "{schema}"."{table}"'))


async def _admin_exists(schema: str, owner_email: str) -> bool:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            text(
                f'SELECT count(*) FROM "{schema}".user_roles ur '
                f'JOIN "{schema}".users u ON u.id = ur.user_id '
                f'JOIN "{schema}".roles r ON r.id = ur.role_id '
                f"WHERE u.email = :email AND r.name = 'admin'"
            ),
            {"email": owner_email},
        )
        return count == 1


async def _other_schema_empty(schema: str) -> bool:
    for table in ("users", "roles", "permissions", "user_roles", "role_permissions"):
        if await _table_count(schema, table) != 0:
            return False
    return True


async def _user_password_hash(schema: str, owner_email: str) -> str | None:
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            text(
                f'SELECT password_hash FROM "{schema}".users '
                "WHERE email = :email"
            ),
            {"email": owner_email},
        )


async def test_setup_credential_succeeds_for_valid_token_and_password():
    owner_email, schema = await _setup_provisioned_tenant()
    setup_token = await _issue_setup_token(owner_email)
    credential_value = TEST_SETUP_PW

    async with await _client() as client:
        response = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": credential_value},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == NEUTRAL_SETUP_MESSAGE
    assert "registrationId" not in str(body)
    assert "tenant_schema" not in str(body)
    assert "token_hash" not in str(body)
    assert "password_hash" not in str(body)
    assert "user_id" not in str(body)
    assert "role_id" not in str(body)
    assert await _admin_exists(schema, owner_email)


async def test_get_setup_credential_rejected():
    async with await _client() as client:
        response = await client.get(
            SETUP_CREDENTIAL_URL + "?setup_token=any&password=any"
        )
    assert response.status_code == 405
    assert "setup_token" not in str(response.json()).lower()


async def test_invalid_or_missing_token_returns_neutral_error():
    async with await _client() as client:
        for payload in (
            {"setup_token": "", "password": TEST_SETUP_PW},
            {"setup_token": None, "password": TEST_SETUP_PW},
            {"setup_token": "nonexistent-token", "password": TEST_SETUP_PW},
            {"setup_token": "   ", "password": TEST_SETUP_PW},
        ):
            response = await client.post(SETUP_CREDENTIAL_URL, json=payload)
            assert response.status_code == 401
            body = response.json()
            assert body.get("detail", {}).get("code") == "INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN"


async def test_expired_token_returns_neutral_error_and_no_admin_created():
    owner_email, schema = await _setup_provisioned_tenant()
    expired_token = await _insert_expired_token(owner_email)

    async with await _client() as client:
        response = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": expired_token, "password": TEST_SETUP_PW},
        )

    assert response.status_code == 401
    assert not await _admin_exists(schema, owner_email)


async def test_used_token_returns_neutral_error():
    owner_email, _schema = await _setup_provisioned_tenant()
    used_token = await _insert_used_token(owner_email)

    async with await _client() as client:
        response = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": used_token, "password": TEST_SETUP_PW},
        )

    assert response.status_code == 401


async def test_duplicate_setup_is_idempotent():
    owner_email, schema = await _setup_provisioned_tenant()
    setup_token = await _issue_setup_token(owner_email)

    async with await _client() as client:
        response_1 = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": TEST_SETUP_PW},
        )
        response_2 = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": "AltCred5678!"},  # pragma: allowlist secret
        )

    assert response_1.status_code == 200
    assert response_2.status_code == 401
    assert await _table_count(schema, "users") == 1
    assert await _table_count(schema, "roles") == 1


async def test_replay_with_different_password_does_not_change_password_hash():
    owner_email, schema = await _setup_provisioned_tenant()
    setup_token = await _issue_setup_token(owner_email)

    async with await _client() as client:
        response_1 = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": TEST_SETUP_PW},
        )
        assert response_1.status_code == 200

    pw_hash_after_first = await _user_password_hash(schema, owner_email)
    assert pw_hash_after_first is not None

    async with await _client() as client:
        response_2 = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": "AltCred_NeverHashed_!"},  # pragma: allowlist secret
        )
        assert response_2.status_code == 401

    pw_hash_after_replay = await _user_password_hash(schema, owner_email)
    assert pw_hash_after_replay == pw_hash_after_first
    assert await _table_count(schema, "users") == 1
    assert await _table_count(schema, "roles") == 1
    assert await _table_count(schema, "permissions") > 0
    assert await _table_count(schema, "user_roles") == 1
    assert await _table_count(schema, "role_permissions") > 0


async def test_tenant_isolation_only_writes_requested_schema():
    owner_email_1, target_schema = await _setup_provisioned_tenant()
    owner_email_2, other_schema = await _setup_provisioned_tenant()
    setup_token = await _issue_setup_token(owner_email_1)

    async with await _client() as client:
        await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": TEST_SETUP_PW},
        )

    assert await _table_count(target_schema, "users") == 1
    assert await _other_schema_empty(other_schema)


async def test_response_never_exposes_sensitive_data():
    owner_email, _schema = await _setup_provisioned_tenant()
    setup_token = await _issue_setup_token(owner_email)

    async with await _client() as client:
        response = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": TEST_SETUP_PW},
        )

    body = response.json()
    body_str = str(body)
    for sensitive in (
        "setup_token",
        "token_hash",
        "password_hash",
        "tenant_schema",
        "wholesaler",
        "user_id",
        "role_id",
        "permission_id",
    ):
        assert sensitive not in body_str, f"Response leaked '{sensitive}'"


async def test_no_query_string_token_support():
    async with await _client() as client:
        response = await client.get(
            SETUP_CREDENTIAL_URL + "?setup_token=any&password=any"
        )
        assert response.status_code == 405

    owner_email, schema = await _setup_provisioned_tenant()
    setup_token = await _issue_setup_token(owner_email)

    async with await _client() as client:
        response = await client.post(
            SETUP_CREDENTIAL_URL + "?setup_token=any&password=any",
            json={"setup_token": setup_token, "password": TEST_SETUP_PW},
        )
        assert response.status_code == 401

        response = await client.post(
            SETUP_CREDENTIAL_URL + "?setup_token=any",
            json={"setup_token": setup_token, "password": TEST_SETUP_PW},
        )
        assert response.status_code == 401

    assert await _table_count(schema, "users") == 0


# ---------------------------------------------------------------------------
# DC-11T4E: teardown regression test
# ---------------------------------------------------------------------------

async def test_dc11t4e_teardown_removes_u6i5_schemas_and_preserves_others():
    """Prove _clear_u6i5_rows drops U6I5 schemas and leaves others intact."""
    _u6i5_email, u6i5_schema = await _setup_provisioned_tenant()
    assert U6I5_SCHEMA_RE.fullmatch(u6i5_schema)
    sentinel_schema = f"t_dc11t4e_sentinel_{uuid.uuid4().hex[:8]}"
    async with async_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{sentinel_schema}"'))

    try:
        await _clear_u6i5_rows()

        async with AsyncSessionLocal() as session:
            u6i5_after = (
                await session.execute(
                    text(
                        "SELECT 1 FROM information_schema.schemata "
                        "WHERE schema_name = :schema_name"
                    ),
                    {"schema_name": u6i5_schema},
                )
            ).scalar()
            sentinel_after = (
                await session.execute(
                    text(
                        "SELECT 1 FROM information_schema.schemata "
                        "WHERE schema_name = :schema_name"
                    ),
                    {"schema_name": sentinel_schema},
                )
            ).scalar()
            registration_count = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM public.tenant_registrations "
                        "WHERE owner_email ~ '^u6i5_[0-9a-f]{32}@example[.]com$'"
                    )
                )
            ).scalar_one()

        assert u6i5_after is None
        assert sentinel_after is not None
        assert registration_count == 0
    finally:
        async with async_engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{sentinel_schema}" CASCADE')
            )


async def test_dc11t4e_teardown_is_idempotent():
    """Running teardown twice must not error."""
    await _setup_provisioned_tenant()
    await _clear_u6i5_rows()
    await _clear_u6i5_rows()  # second call must be a clean no-op
    # No exception raised = pass


async def test_dc11t4e_teardown_fails_closed_on_invalid_schema_anchor():
    """An invalid registration anchor must not trigger any DROP or DELETE."""
    owner_email, owned_schema = await _setup_provisioned_tenant()
    invalid_schema = f"t_dc11t4e_invalid_{uuid.uuid4().hex[:8]}"
    async with async_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{invalid_schema}"'))

    wholesaler_id = None
    try:
        async with AsyncSessionLocal() as session:
            wholesaler_id = (
                await session.execute(
                    text(
                        "UPDATE public.tenant_registrations "
                        "SET tenant_schema = :invalid_schema "
                        "WHERE owner_email = :owner_email "
                        "RETURNING wholesaler_id"
                    ),
                    {
                        "invalid_schema": invalid_schema,
                        "owner_email": owner_email,
                    },
                )
            ).scalar_one()
            await session.commit()

        with pytest.raises(RuntimeError, match="Invalid U6I5 teardown ownership anchor"):
            await _clear_u6i5_rows()

        async with AsyncSessionLocal() as session:
            registration_count = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM public.tenant_registrations "
                        "WHERE owner_email = :owner_email"
                    ),
                    {"owner_email": owner_email},
                )
            ).scalar_one()
            wholesaler_count = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM public.wholesalers WHERE id = :id"
                    ),
                    {"id": wholesaler_id},
                )
            ).scalar_one()
            schema_count = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM information_schema.schemata "
                        "WHERE schema_name IN (:owned_schema, :invalid_schema)"
                    ),
                    {
                        "owned_schema": owned_schema,
                        "invalid_schema": invalid_schema,
                    },
                )
            ).scalar_one()

        assert registration_count == 1
        assert wholesaler_count == 1
        assert schema_count == 2
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    "DELETE FROM public.tenant_registrations "
                    "WHERE owner_email = :owner_email"
                ),
                {"owner_email": owner_email},
            )
            if wholesaler_id is not None:
                await session.execute(
                    text("DELETE FROM public.wholesalers WHERE id = :id"),
                    {"id": wholesaler_id},
                )
            await session.commit()
        async with async_engine.begin() as conn:
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{owned_schema}" CASCADE')
            )
            await conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{invalid_schema}" CASCADE')
            )
