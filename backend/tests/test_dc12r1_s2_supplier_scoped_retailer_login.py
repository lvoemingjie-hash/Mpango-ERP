"""DC-12R1-S2-R2A-R1A: Explicit Per-Test DB/Redis Ownership Cleanup.

Comprehensive tests for POST /api/v1/client/auth/login. Runs against real
PostgreSQL 16 migrated to head 036.

All tenants are provisioned through TenantProvisioningService + full bootstrap
(not handwritten DDL). A module-scoped pool provisions 3 tenants (A, B, sentinel).
Per-test cleanup replaces the false rollback contract with explicit ownership
tracking: every ID is generated and registered *before* the INSERT, and a
try/finally finalizer deletes in FK-safe order.  Mutation journal restores
pool-owned row changes.  Redis rate-limit keys are deleted per-test.

Key corrections vs R2A-R1:
- s2_db replaced with s2_clean_db (explicit ownership registry, no rollback)
- _OwnershipRegistry tracks retailer/binding/user/schema IDs pre-commit
- Mutation journal with fixed allowlist for pool row changes
- Snapshot/restore of public-table counts + sentinel fingerprint
- Per-test Redis key cleanup (no FLUSHDB)
- Cleanup runs in separate connection (survives aborted test session)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Any
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.exc import IntegrityError

from api.app import configure_app
from api.middleware.rbac import RequirePermission, RequirePlatformAdmin
from api.v1.client.auth import validate_identifier
from auth.strategies.jwt import JwtAuthStrategy
import auth.factory as auth_factory
from core.config import get_settings
from core.error_codes import MpangoAPIException, register_exception_handlers
from core.security import create_contextual_token, decode_token, hash_password
from database.session import AsyncSessionLocal, async_engine
from models.wholesaler import Wholesaler
from core.security import TokenPayload
from services.tenant_provisioning_service import TenantProvisioningService

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------
_WRONG_PW = "WrongPassword"
_RIGHT_PW_ALT = "RightPass1"
_DUMMY_PW = "dummypw1"
_DEFAULT_PW = "TestPass123"
_TWO_TENANT_PW = "CorrectPass99"
_OWNER_PW = "OwnerPass99"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _execute(db: AsyncSession, sql: str, params: dict | None = None):
    await db.execute(text(sql), params or {})


async def _fetch(db: AsyncSession, sql: str, params: dict | None = None):
    return (await db.execute(text(sql), params or {})).fetchall()


async def _fetch_one(db: AsyncSession, sql: str, params: dict | None = None):
    return (await db.execute(text(sql), params or {})).fetchone()


def _unique_code(prefix: str = "S2T") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"


def _unique_email() -> str:
    return f"s2.retailer.{uuid.uuid4().hex[:8]}@example.com"


def _unique_phone() -> str:
    return f"+2557{uuid.uuid4().hex[:9][:9]}"


async def _create_retailer_user(
    db: AsyncSession,
    *,
    tenant_schema: str,
    email: str,
    password: str = _DEFAULT_PW,
    full_name: str = "Test Retailer",
    is_active: bool = True,
    registry: _OwnershipRegistry | None = None,
) -> str:
    pw_hash = hash_password(password)
    await _execute(
        db,
        f'INSERT INTO "{tenant_schema}".users '
        "(email, password_hash, full_name, is_active) "
        "VALUES (:email, :pw, :name, :active) RETURNING id",
        {"email": email, "pw": pw_hash, "name": full_name, "active": is_active},
    )
    row = (await db.execute(
        text(f'SELECT id FROM "{tenant_schema}".users WHERE email = :email'),
        {"email": email},
    )).fetchone()
    uid = str(row.id)
    if registry:
        registry.register_tenant_user(tenant_schema, uid)
    await db.commit()
    return uid


async def _grant_retailer_operator(
    db: AsyncSession, *, tenant_schema: str, user_id: str
) -> None:
    await _execute(
        db,
        f'INSERT INTO "{tenant_schema}".user_roles (user_id, role_id) '
        f"SELECT :uid, id FROM \"{tenant_schema}\".roles WHERE name = 'retailer_operator'",
        {"uid": user_id},
    )
    await db.commit()


async def _create_binding(
    db: AsyncSession,
    *,
    wholesaler_id: str,
    retailer_id: str,
    tenant_user_id: str,
    status: str = "active",
    registry: _OwnershipRegistry | None = None,
) -> str:
    bid = str(uuid.uuid4())
    if registry:
        registry.register_binding(bid)
    await _execute(
        db,
        "INSERT INTO public.wholesaler_retailer_bindings "
        "(id, wholesaler_id, retailer_id, tenant_user_id, status, outstanding_balance) "
        "VALUES (:id, :ws, :ret, :tuid, :status, 0.00)",
        {
            "id": bid,
            "ws": wholesaler_id,
            "ret": retailer_id,
            "tuid": tenant_user_id,
            "status": status,
        },
    )
    await db.commit()
    return bid


async def _create_retailer(
    db: AsyncSession, *, name: str = "Test Retailer", is_deleted: bool = False,
    registry: _OwnershipRegistry | None = None,
) -> str:
    ret_id = str(uuid.uuid4())
    if registry:
        registry.register_retailer(ret_id)
    await _execute(
        db,
        "INSERT INTO public.retailers (id, phone, name, is_deleted) "
        "VALUES (:id, :phone, :name, :del)",
        {"id": ret_id, "phone": _unique_phone(), "name": name, "del": is_deleted},
    )
    await db.commit()
    return ret_id


async def _setup_full_login(
    db, *,
    code: str | None = None,
    ws_id: str | None = None,
    schema: str | None = None,
    registry: _OwnershipRegistry | None = None,
):
    """Create a complete login-ready scenario.

    Uses either a pool-provided tenant (ws_id + schema) or creates a
    new one via provisioning."""
    code = code or _unique_code("S2F")
    email = _unique_email()
    password = _DEFAULT_PW

    if ws_id and schema:
        uid = await _create_retailer_user(db, tenant_schema=schema, email=email, password=password, registry=registry)
        await _grant_retailer_operator(db, tenant_schema=schema, user_id=uid)
        ret_id = await _create_retailer(db, name=f"Retailer in {code}", registry=registry)
        await _create_binding(db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid, registry=registry)
    else:
        uid, ws_id, schema = await _create_provisioned_full_login(db, code=code, password=password, registry=registry)
    return code, email, password


async def _create_provisioned_full_login(
    db: AsyncSession, *, code: str, password: str = _DEFAULT_PW,
    registry: _OwnershipRegistry | None = None,
) -> tuple[str, str, str]:
    """Create a tenant through the full provisioning path and return (user_id, ws_id, schema).

    Registers registration_id *before* provisioning so even a mid-provisioning
    failure can be cleaned up by ID lookup.
    """
    reg_id = uuid.uuid4()
    if registry:
        registry.register_registration(str(reg_id))
    await db.execute(
        text(
        "INSERT INTO public.tenant_registrations "
        "(id, company_name, tenant_code, country, owner_email, status, "
        " expires_at, created_at, updated_at) "
        "VALUES (:id, :company, :code, 'TZ', :email, 'email_verified', "
        " now() + interval '365 days', now(), now())"
        ),
        {
            "id": reg_id,
            "company": f"Company {code}",
            "code": code,
            "email": f"owner.{code.lower()}@example.com",
        },
    )
    await db.commit()

    service = TenantProvisioningService(db)
    claim_result = await service.claim_registration_for_provisioning(str(reg_id))
    assert claim_result.action == "claimed", f"claim failed: {claim_result}"
    await db.commit()
    await service.provision_wholesaler_and_schema(str(reg_id))
    await db.commit()

    ws_row = (await db.execute(
        text("SELECT id, tenant_schema FROM public.tenant_registrations WHERE id = :id"),
        {"id": reg_id},
    )).fetchone()
    ws_id_row = (await db.execute(
        text("SELECT id FROM public.wholesalers WHERE code = :code"),
        {"code": code},
    )).fetchone()

    schema = ws_row.tenant_schema
    ws_id_str = str(ws_id_row.id)
    if registry:
        registry.register_wholesaler(ws_id_str)
        registry.register_tenant_schema(ws_id_str, schema)

    email = _unique_email()
    pw_hash = hash_password(password)
    uid_row = (await db.execute(
        text(
            f'INSERT INTO "{schema}".users '
            "(email, password_hash, full_name, is_active) "
            "VALUES (:email, :pw, 'Test Retailer', true) RETURNING id"
        ),
        {"email": email, "pw": pw_hash},
    )).fetchone()
    uid = str(uid_row.id)
    if registry:
        registry.register_tenant_user(schema, uid)
    await db.commit()
    return uid, ws_id_str, schema


# ---------------------------------------------------------------------------
# Tenant pool
# ---------------------------------------------------------------------------

class _OwnedIds:
    """Track all created object IDs for teardown."""

    def __init__(self):
        self.wholesaler_ids: list[str] = []
        self.registration_ids: list[str] = []
        self.retailer_ids: list[str] = []
        self.binding_ids: list[str] = []
        self.tenant_schemas: list[str] = []


class _TenantPool:
    """Module-scoped pool of fully-provisioned tenants via TenantProvisioningService."""

    def __init__(self):
        self.target = _OwnedIds()
        self.protected = _OwnedIds()
        self.tenants: dict[str, dict[str, Any]] = {}

    async def provision(self):
        """Provision 3 tenants: A, B (target), sentinel (protected)."""
        labels_ws = [
            ("a", "S2POOLA"),
            ("b", "S2POOLB"),
        ]
        for label, code_prefix in labels_ws:
            ws_id, schema, reg_id, code = await self._provision_one(code_prefix)
            self.tenants[label] = {"ws_id": ws_id, "schema": schema, "reg_id": str(reg_id), "code": code}
            self.target.wholesaler_ids.append(ws_id)
            self.target.registration_ids.append(str(reg_id))
            self.target.tenant_schemas.append(schema)

        # Sentinel — tracked in protected (not target)
        sentinel_ws_id, sentinel_schema, sentinel_reg_id, sentinel_code = await self._provision_one("S2POOLS")
        self.tenants["sentinel"] = {
            "ws_id": sentinel_ws_id,
            "schema": sentinel_schema,
            "reg_id": str(sentinel_reg_id),
            "code": sentinel_code,
        }
        self.protected.wholesaler_ids.append(sentinel_ws_id)
        self.protected.registration_ids.append(str(sentinel_reg_id))
        self.protected.tenant_schemas.append(sentinel_schema)

    async def _provision_one(self, code_prefix: str) -> tuple[str, str, str, str]:
        code = f"{code_prefix}{uuid.uuid4().hex[:4].upper()}"
        async with AsyncSessionLocal() as session:
            reg_id = uuid.uuid4()
            await session.execute(
                text(
                    "INSERT INTO public.tenant_registrations "
                    "(id, company_name, tenant_code, country, owner_email, status, "
                    " expires_at, created_at, updated_at) "
                    "VALUES (:id, :company, :code, 'TZ', :email, 'email_verified', "
                    " now() + interval '365 days', now(), now())"
                ),
                {
                    "id": reg_id,
                    "company": f"Pool {code_prefix}",
                    "code": code,
                    "email": f"pool.{code_prefix.lower()}@{code.lower()}.example.com",
                },
            )
            await session.commit()

            service = TenantProvisioningService(session)
            claim_result = await service.claim_registration_for_provisioning(str(reg_id))
            assert claim_result.action == "claimed", f"claim failed: {claim_result}"
            await session.commit()
            await service.provision_wholesaler_and_schema(str(reg_id))
            await session.commit()

            reg_row = (await session.execute(
                text("SELECT tenant_schema FROM public.tenant_registrations WHERE id = :id"),
                {"id": reg_id},
            )).fetchone()
            ws_row = (await session.execute(
                text("SELECT id FROM public.wholesalers WHERE code = :code"),
                {"code": code},
            )).fetchone()
            return str(ws_row.id), reg_row.tenant_schema, str(reg_id), code

    async def teardown_target(self):
        """Delete all target A/B rows and schemas in FK-safe order."""
        await self._teardown_owned(self.target)

    async def teardown_protected(self):
        """Delete sentinel rows and schema."""
        await self._teardown_owned(self.protected)

    async def _teardown_owned(self, owned: _OwnedIds):
        if owned.binding_ids:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("DELETE FROM public.wholesaler_retailer_bindings WHERE id = ANY(:ids)"),
                    {"ids": owned.binding_ids},
                )
                await session.commit()
        if owned.retailer_ids:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("DELETE FROM public.retailers WHERE id = ANY(:ids)"),
                    {"ids": owned.retailer_ids},
                )
                await session.commit()
        if owned.registration_ids:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("DELETE FROM public.tenant_registrations WHERE id = ANY(:ids)"),
                    {"ids": owned.registration_ids},
                )
                await session.commit()
        if owned.wholesaler_ids:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("DELETE FROM public.wholesalers WHERE id = ANY(:ids)"),
                    {"ids": owned.wholesaler_ids},
                )
                await session.commit()
        for schema in owned.tenant_schemas:
            if schema and self._validate_schema_ownership(schema, owned):
                async with AsyncSessionLocal() as session:
                    await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                    await session.commit()

    def _validate_schema_ownership(self, schema: str, owned: _OwnedIds) -> bool:
        for ws_id in owned.wholesaler_ids:
            expected = Wholesaler.derive_schema_from_id(str(ws_id))
            if schema == expected:
                from api.v1.client.auth import validate_identifier
                return validate_identifier(schema)
        return False

    async def assert_zero_residue(self, owned: _OwnedIds):
        """Assert no owned rows or schemas remain."""
        async with AsyncSessionLocal() as session:
            for table, id_field, id_list in [
                ("public.wholesaler_retailer_bindings", "id", owned.binding_ids),
                ("public.retailers", "id", owned.retailer_ids),
                ("public.tenant_registrations", "id", owned.registration_ids),
                ("public.wholesalers", "id", owned.wholesaler_ids),
            ]:
                if id_list:
                    count = (await session.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE {id_field} = ANY(:ids)"),
                        {"ids": id_list},
                    )).scalar()
                    assert count == 0, f"{count} owned rows remain in {table}"
            for schema in owned.tenant_schemas:
                if schema:
                    count = (await session.execute(
                        text("SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = :s"),
                        {"s": schema},
                    )).scalar()
                    assert count == 0, f"Schema {schema} still exists"

    async def verify_sentinel_unchanged(self):
        """Assert sentinel tenant still has its original schema and active status."""
        sentinel_ws_id = self.tenants["sentinel"]["ws_id"]
        sentinel_schema = self.tenants["sentinel"]["schema"]
        async with AsyncSessionLocal() as session:
            ws = (await session.execute(
                text("SELECT id, code, status FROM public.wholesalers WHERE id = :id"),
                {"id": sentinel_ws_id},
            )).fetchone()
            assert ws is not None, "Sentinel wholesaler missing"
            assert ws.status == "active", f"Sentinel status changed: {ws.status}"
            schema_count = (await session.execute(
                text("SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = :s"),
                {"s": sentinel_schema},
            )).scalar()
            assert schema_count == 1, f"Sentinel schema {sentinel_schema} missing or duplicated"


# ---------------------------------------------------------------------------
# Ownership registry — explicit per-test cleanup
# ---------------------------------------------------------------------------

_MUTATION_ALLOWLIST_TABLES: set[str] = {"public.tenant_registrations", "public.retailers"}
_MUTATION_ALLOWLIST_SCHEMA_TABLES: set[str] = {"users", "roles"}
_MUTATION_ALLOWLIST_FIELDS: set[str] = {"is_deleted"}


class _OwnershipRegistry:
    """Per-test ownership registry.

    Every ID is generated and registered BEFORE the INSERT (never after commit).
    Cleanup deletes in FK-safe order; zero-residue assert proves every tracked
    ID is gone.  Mutation journal records field-level changes to pool-owned rows
    and restores them in ``restore_mutations``.
    """

    def __init__(self):
        self.retailer_ids: list[str] = []
        self.binding_ids: list[str] = []
        self.registration_ids: list[str] = []
        self.wholesaler_ids: list[str] = []
        self.tenant_user_ids: dict[str, list[str]] = {}
        self.tenant_schemas: list[tuple[str, str]] = []
        self.mutation_journal: list[dict[str, Any]] = []

    # -- Register methods (pre-commit) ----------------------------------------

    def register_retailer(self, rid: str) -> str:
        self.retailer_ids.append(rid)
        return rid

    def register_binding(self, bid: str) -> str:
        self.binding_ids.append(bid)
        return bid

    def register_registration(self, rid: str) -> str:
        self.registration_ids.append(rid)
        return rid

    def register_wholesaler(self, wid: str) -> str:
        self.wholesaler_ids.append(wid)
        return wid

    def register_tenant_user(self, schema: str, uid: str) -> str:
        self.tenant_user_ids.setdefault(schema, []).append(uid)
        return uid

    def register_tenant_schema(self, wholesaler_id: str, schema: str) -> None:
        derived = Wholesaler.derive_schema_from_id(str(wholesaler_id))
        assert schema == derived, (
            f"Schema {schema} != derived {derived} from ws {wholesaler_id}"
        )
        assert validate_identifier(schema), f"Schema {schema} fails validate_identifier"
        self.tenant_schemas.append((wholesaler_id, schema))

    def register_mutation(self, table: str, row_id: str, field: str, old_value: Any) -> None:
        if field not in _MUTATION_ALLOWLIST_FIELDS:
            raise ValueError(f"Mutation field {field!r} not in allowlist")
        parts = table.split(".")
        if len(parts) == 2:
            if parts[0] == "public" and table in _MUTATION_ALLOWLIST_TABLES:
                pass
            elif parts[1] in _MUTATION_ALLOWLIST_SCHEMA_TABLES and validate_identifier(parts[0].strip('"')):
                pass
            else:
                raise ValueError(f"Mutation table {table!r} not in allowlist")
        else:
            raise ValueError(f"Mutation table {table!r} not in allowlist")
        self.mutation_journal.append({"table": table, "id": row_id, "field": field, "old_value": old_value})

    # -- Cleanup ---------------------------------------------------------------

    async def restore_mutations(self, db: AsyncSession) -> None:
        for entry in self.mutation_journal:
            await db.execute(
                text(f"UPDATE {entry['table']} SET {entry['field']} = :old WHERE id = :id"),
                {"old": entry["old_value"], "id": entry["id"]},
            )
        if self.mutation_journal:
            await db.commit()

    async def cleanup(self, db: AsyncSession) -> None:
        for schema, uid_list in self.tenant_user_ids.items():
            if uid_list:
                await db.execute(
                    text(f'DELETE FROM "{schema}".user_roles WHERE user_id = ANY(:ids)'),
                    {"ids": uid_list},
                )
                await db.execute(
                    text(f'DELETE FROM "{schema}".users WHERE id = ANY(:ids)'),
                    {"ids": uid_list},
                )
        if self.binding_ids:
            await db.execute(
                text("DELETE FROM public.wholesaler_retailer_bindings WHERE id = ANY(:ids)"),
                {"ids": self.binding_ids},
            )
        if self.retailer_ids:
            await db.execute(
                text("DELETE FROM public.retailers WHERE id = ANY(:ids)"),
                {"ids": self.retailer_ids},
            )
        if self.registration_ids:
            await db.execute(
                text("DELETE FROM public.tenant_registrations WHERE id = ANY(:ids)"),
                {"ids": self.registration_ids},
            )
        if self.wholesaler_ids:
            await db.execute(
                text("DELETE FROM public.wholesalers WHERE id = ANY(:ids)"),
                {"ids": self.wholesaler_ids},
            )
        for _ws_id, schema in self.tenant_schemas:
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await db.commit()

    # -- Zero-residue assertions -----------------------------------------------

    async def assert_zero_residue(self, db: AsyncSession) -> None:
        errors: list[str] = []
        for schema, uid_list in self.tenant_user_ids.items():
            if not uid_list:
                continue
            cnt = (await db.execute(
                text(f'SELECT COUNT(*) FROM "{schema}".user_roles WHERE user_id = ANY(:ids)'),
                {"ids": uid_list},
            )).scalar()
            if cnt:
                errors.append(f"{cnt} rows in {schema}.user_roles")
            cnt = (await db.execute(
                text(f'SELECT COUNT(*) FROM "{schema}".users WHERE id = ANY(:ids)'),
                {"ids": uid_list},
            )).scalar()
            if cnt:
                errors.append(f"{cnt} rows in {schema}.users")
        for table, id_field, id_list in [
            ("public.wholesaler_retailer_bindings", "id", self.binding_ids),
            ("public.retailers", "id", self.retailer_ids),
            ("public.tenant_registrations", "id", self.registration_ids),
            ("public.wholesalers", "id", self.wholesaler_ids),
        ]:
            if not id_list:
                continue
            cnt = (await db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {id_field} = ANY(:ids)"),
                {"ids": id_list},
            )).scalar()
            if cnt:
                errors.append(f"{cnt} rows in {table}")
        for _ws_id, schema in self.tenant_schemas:
            cnt = (await db.execute(
                text("SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = :s"),
                {"s": schema},
            )).scalar()
            if cnt:
                errors.append(f"schema {schema} exists")
        assert not errors, f"Residue: {', '.join(errors)}"


# ---------------------------------------------------------------------------
# Snapshot / sentinel helpers
# ---------------------------------------------------------------------------


async def _snapshot_public_counts(db: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ["retailers", "wholesaler_retailer_bindings", "tenant_registrations", "wholesalers"]:
        counts[table] = (await db.execute(text(f"SELECT COUNT(*) FROM public.{table}"))).scalar()
    return counts


async def _assert_public_counts(db: AsyncSession, before: dict[str, int], label: str = "") -> None:
    for table, expected in before.items():
        actual = (await db.execute(text(f"SELECT COUNT(*) FROM public.{table}"))).scalar()
        assert actual == expected, f"{label} public.{table}: expected {expected}, got {actual}"


async def _snapshot_sentinel_fingerprint(db: AsyncSession, pool: _TenantPool) -> dict[str, Any]:
    s_ws_id = pool.tenants["sentinel"]["ws_id"]
    s_schema = pool.tenants["sentinel"]["schema"]
    s_reg_id = pool.tenants["sentinel"]["reg_id"]
    fp: dict[str, Any] = {}
    fp["ws"] = (await db.execute(
        text("SELECT id, code, status FROM public.wholesalers WHERE id = :id"),
        {"id": s_ws_id},
    )).fetchone()
    fp["reg"] = (await db.execute(
        text("SELECT id, status, is_deleted FROM public.tenant_registrations WHERE id = :id"),
        {"id": s_reg_id},
    )).fetchone()
    fp["schema_exists"] = (await db.execute(
        text("SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = :s"),
        {"s": s_schema},
    )).scalar()
    fp["role_names"] = [
        r.name for r in (await db.execute(
            text(f'SELECT name FROM "{s_schema}".roles ORDER BY name'),
        )).fetchall()
    ]
    fp["user_count"] = (await db.execute(
        text(f'SELECT COUNT(*) FROM "{s_schema}".users'),
    )).scalar()
    return fp


async def _assert_sentinel_fingerprint(db: AsyncSession, pool: _TenantPool, before: dict[str, Any]) -> None:
    after = await _snapshot_sentinel_fingerprint(db, pool)
    errors: list[str] = []
    if after["ws"] != before["ws"]:
        errors.append(f"wholesaler row changed: {before['ws']} -> {after['ws']}")
    if after["reg"] != before["reg"]:
        errors.append(f"registration row changed: {before['reg']} -> {after['reg']}")
    if after["schema_exists"] != before["schema_exists"]:
        errors.append(f"schema existence changed: {before['schema_exists']} -> {after['schema_exists']}")
    if after["role_names"] != before["role_names"]:
        errors.append(f"role names changed: {before['role_names']} -> {after['role_names']}")
    if after["user_count"] != before["user_count"]:
        errors.append(f"user count changed: {before['user_count']} -> {after['user_count']}")
    assert not errors, f"Sentinel fingerprint mismatch: {'; '.join(errors)}"


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------

# Forward-reference: set by provisioned_pool fixture for helper use
_pool_instance: _TenantPool | None = None


@pytest_asyncio.fixture(scope="module")
async def provisioned_pool():
    pool = _TenantPool()
    await pool.provision()
    global _pool_instance
    _pool_instance = pool
    yield pool
    # Phase 1: teardown target A/B, prove zero residue, prove sentinel unchanged
    await pool.teardown_target()
    await pool.assert_zero_residue(pool.target)
    await pool.verify_sentinel_unchanged()
    # Phase 2: teardown sentinel
    await pool.teardown_protected()
    await pool.assert_zero_residue(pool.protected)
    # Idempotent: second teardown is no-op
    await pool.teardown_target()
    await pool.teardown_protected()
    _pool_instance = None


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def s2_clean_db(provisioned_pool):
    """Per-test session with explicit ownership cleanup.

    Usage::

        db, registry = s2_clean_db

    Every ID created by the test must be registered in ``registry`` *before*
    the INSERT.  After the test (even on failure), cleanup deletes all tracked
    rows in FK-safe order, restores mutations, and verifies zero residue +
    sentinel fingerprint + public-table counts.
    """
    registry = _OwnershipRegistry()

    async with AsyncSessionLocal() as snapshot_db:
        before_counts = await _snapshot_public_counts(snapshot_db)
        before_sentinel = await _snapshot_sentinel_fingerprint(snapshot_db, provisioned_pool)

    try:
        async with AsyncSessionLocal() as test_db:
            yield test_db, registry
    finally:
        async with AsyncSessionLocal() as cleanup_db:
            await registry.restore_mutations(cleanup_db)
            await registry.cleanup(cleanup_db)

        async with AsyncSessionLocal() as verify_db:
            await registry.assert_zero_residue(verify_db)
            await _assert_public_counts(verify_db, before_counts, "post-cleanup")
            await _assert_sentinel_fingerprint(verify_db, provisioned_pool, before_sentinel)


@pytest_asyncio.fixture
async def client():
    """HTTP client bound to a fresh app with JwtAuthStrategy + production handlers."""
    from fastapi import FastAPI

    fresh_app = FastAPI()
    with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
        configure_app(fresh_app, get_settings())
    register_exception_handlers(fresh_app)

    async with AsyncClient(
        transport=ASGITransport(app=fresh_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def two_tenants(s2_clean_db, provisioned_pool):
    """Set up cross-tenant user in A and B with full login readiness."""
    db, reg = s2_clean_db
    code_a = provisioned_pool.tenants["a"]["code"]
    code_b = provisioned_pool.tenants["b"]["code"]
    email = _unique_email()
    password = _TWO_TENANT_PW

    ws_a_id = provisioned_pool.tenants["a"]["ws_id"]
    schema_a = provisioned_pool.tenants["a"]["schema"]
    ws_b_id = provisioned_pool.tenants["b"]["ws_id"]
    schema_b = provisioned_pool.tenants["b"]["schema"]

    uid_a = await _create_retailer_user(db, tenant_schema=schema_a, email=email, password=password, registry=reg)
    uid_b = await _create_retailer_user(db, tenant_schema=schema_b, email=email, password=password, registry=reg)

    await _grant_retailer_operator(db, tenant_schema=schema_a, user_id=uid_a)
    await _grant_retailer_operator(db, tenant_schema=schema_b, user_id=uid_b)

    ret_a_id = await _create_retailer(db, name=f"Retailer in A", registry=reg)
    ret_b_id = await _create_retailer(db, name=f"Retailer in B", registry=reg)

    await _create_binding(db, wholesaler_id=ws_a_id, retailer_id=ret_a_id, tenant_user_id=uid_a, registry=reg)
    await _create_binding(db, wholesaler_id=ws_b_id, retailer_id=ret_b_id, tenant_user_id=uid_b, registry=reg)

    yield code_a, code_b, schema_b, email, password, uid_a, uid_b


# ---------------------------------------------------------------------------
# §1 Happy-path + SQL capture
# ---------------------------------------------------------------------------


class TestRetailerLoginHappyPath:
    """Happy-path supplier-scoped retailer login."""

    async def test_login_through_A_returns_only_A(
        self, client: AsyncClient, two_tenants
    ):
        code_a, code_b, schema_b, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()["data"]
        tokens = data["tokens"]

        decoded = decode_token(tokens["access_token"])
        assert decoded.tenant_id is not None
        assert decoded.tenant_schema is not None
        assert decoded.tenant_schema.startswith("t_")
        assert decoded.roles == ["retailer_operator"]
        assert decoded.tmap is None

        assert data["wholesaler"]["code"] == code_a
        assert data["wholesaler"]["id"] == decoded.tenant_id
        assert data["user"]["email"] == email

    async def test_login_through_A_never_references_schema_B(
        self, client: AsyncClient, two_tenants
    ):
        from database.session import async_engine

        code_a, code_b, schema_b, email, password, _, _ = two_tenants
        captured: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            captured.append(statement)

        event.listen(async_engine.sync_engine, "before_cursor_execute", _capture)
        try:
            resp = await client.post(
                "/api/v1/client/auth/login",
                json={"email": email, "password": password, "wholesaler_code": code_a},
            )
            assert resp.status_code == HTTPStatus.OK
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _capture)

        offending = [s for s in captured if schema_b in s]
        assert not offending, (
            f"Login through A referenced supplier B schema {schema_b!r}: {offending}"
        )

    async def test_login_through_B_returns_only_B(
        self, client: AsyncClient, two_tenants
    ):
        _, code_b, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_b},
        )
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()["data"]
        assert data["wholesaler"]["code"] == code_b

        decoded = decode_token(data["tokens"]["access_token"])
        assert decoded.tenant_id == data["wholesaler"]["id"]


# ---------------------------------------------------------------------------
# §2 Neutral 401 identity
# ---------------------------------------------------------------------------


class TestRetailerLoginNeutral401:
    """All well-formed authentication mismatches return identical neutral 401."""

    async def _assert_neutral_401(self, resp):
        assert resp.status_code == HTTPStatus.UNAUTHORIZED
        body = resp.json()
        assert body["code"] == "INVALID_CREDENTIALS"
        assert body["message"] == "Invalid credentials"
        assert "request_id" in body and body["request_id"]
        assert "{" not in body["message"] and "}" not in body["message"]
        assert "detail" not in body

    async def test_wrong_email_returns_neutral_401(
        self, client: AsyncClient, two_tenants
    ):
        code_a, _, _, _, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "nonexistent@example.com", "password": password, "wholesaler_code": code_a},
        )
        await self._assert_neutral_401(resp)

    async def test_wrong_password_returns_neutral_401(
        self, client: AsyncClient, two_tenants
    ):
        code_a, _, _, email, _, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": _WRONG_PW, "wholesaler_code": code_a},
        )
        await self._assert_neutral_401(resp)

    async def test_wrong_wholesaler_code_returns_neutral_401(
        self, client: AsyncClient, two_tenants
    ):
        _, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": "NONEXISTENT"},
        )
        await self._assert_neutral_401(resp)

    async def test_missing_binding_returns_neutral_401(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code = _unique_code("S2NB")
        email = _unique_email()
        password = _DEFAULT_PW
        uid = await _create_retailer_user(db, tenant_schema=schema, email=email, password=password, registry=reg)
        await _grant_retailer_operator(db, tenant_schema=schema, user_id=uid)
        # NO binding created

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_inactive_binding_returns_neutral_401(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code = _unique_code("S2IB")
        email = _unique_email()
        password = _DEFAULT_PW
        uid = await _create_retailer_user(db, tenant_schema=schema, email=email, password=password, registry=reg)
        await _grant_retailer_operator(db, tenant_schema=schema, user_id=uid)
        ret_id = await _create_retailer(db, registry=reg)
        await _create_binding(db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid, status="inactive", registry=reg)

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_missing_retailer_operator_role_returns_neutral_401(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code = _unique_code("S2NR")
        email = _unique_email()
        password = _DEFAULT_PW
        uid = await _create_retailer_user(db, tenant_schema=schema, email=email, password=password, registry=reg)
        # NOT granting retailer_operator
        ret_id = await _create_retailer(db, registry=reg)
        await _create_binding(db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid, registry=reg)

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_pending_inactive_user_returns_neutral_401(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code = _unique_code("S2PU")
        email = _unique_email()
        password = _DEFAULT_PW
        uid = await _create_retailer_user(db, tenant_schema=schema, email=email, password=password, registry=reg, is_active=False)

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_all_401_bodies_are_identical(self, client: AsyncClient, s2_clean_db, provisioned_pool):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code = _unique_code("S2EQ")
        email = _unique_email()
        uid = await _create_retailer_user(db, tenant_schema=schema, email=email, password=_RIGHT_PW_ALT, registry=reg)
        await _grant_retailer_operator(db, tenant_schema=schema, user_id=uid)
        ret_id = await _create_retailer(db, registry=reg)
        await _create_binding(db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid, registry=reg)

        bodies = []

        r1 = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": _WRONG_PW, "wholesaler_code": code},
        )
        bodies.append(r1.json())

        r2 = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "wrong@example.com", "password": _RIGHT_PW_ALT, "wholesaler_code": code},
        )
        bodies.append(r2.json())

        r3 = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": _RIGHT_PW_ALT, "wholesaler_code": "ZZZZZ"},
        )
        bodies.append(r3.json())

        def _public_part(body):
            return {k: v for k, v in body.items() if k != "request_id"}

        ref = _public_part(bodies[0])
        for b in bodies[1:]:
            assert _public_part(b) == ref, f"401 body mismatch: {_public_part(b)} != {ref}"


# ---------------------------------------------------------------------------
# §3 Code normalization (uppercase preference) + zero-SQL 422 for malformed
# ---------------------------------------------------------------------------


class TestCodeNormalization:
    """Lowercase codes are normalized to UPPERCASE (not 422). Only genuinely
    malformed codes (symbols, empty, spaces) produce a controlled 422 with zero SQL."""

    async def test_lowercase_code_is_normalized_and_authenticates(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code = provisioned_pool.tenants["a"]["code"]
        lower_code = code.lower()
        email = _unique_email()
        password = _DEFAULT_PW
        uid = await _create_retailer_user(db, tenant_schema=schema, email=email, password=password, registry=reg)
        await _grant_retailer_operator(db, tenant_schema=schema, user_id=uid)
        ret_id = await _create_retailer(db, registry=reg)
        await _create_binding(db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid, registry=reg)

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": lower_code},
        )
        assert resp.status_code == HTTPStatus.OK
        assert resp.json()["data"]["wholesaler"]["code"] == code

    async def test_mixed_case_code_is_normalized(self, client: AsyncClient, s2_clean_db, provisioned_pool):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code = provisioned_pool.tenants["a"]["code"]
        mixed = code.title()
        email = _unique_email()
        password = _DEFAULT_PW
        uid = await _create_retailer_user(db, tenant_schema=schema, email=email, password=password, registry=reg)
        await _grant_retailer_operator(db, tenant_schema=schema, user_id=uid)
        ret_id = await _create_retailer(db, registry=reg)
        await _create_binding(db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid, registry=reg)

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": mixed},
        )
        assert resp.status_code == HTTPStatus.OK
        assert resp.json()["data"]["wholesaler"]["code"] == code


class TestMalformedCode422:
    """Genuinely malformed wholesaler_code produces 422 without touching SQL."""

    async def test_special_chars_code_returns_422(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "a@b.com", "password": _DUMMY_PW, "wholesaler_code": "ABC-DEF!"},
        )
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    async def test_empty_code_returns_422(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "a@b.com", "password": _DUMMY_PW, "wholesaler_code": ""},
        )
        assert resp.status_code in (HTTPStatus.UNPROCESSABLE_ENTITY, HTTPStatus.UNAUTHORIZED)

    async def test_spaces_only_code_returns_422(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "a@b.com", "password": _DUMMY_PW, "wholesaler_code": "   "},
        )
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    async def test_symbol_code_executes_zero_sql(self, client: AsyncClient, s2_clean_db):
        _db, _reg = s2_clean_db
        from database.session import async_engine

        captured: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            captured.append(statement)

        event.listen(async_engine.sync_engine, "before_cursor_execute", _capture)
        try:
            resp = await client.post(
                "/api/v1/client/auth/login",
                json={"email": "a@b.com", "password": _DUMMY_PW, "wholesaler_code": "BAD!CODE"},
            )
            assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _capture)

        login_queries = [s for s in captured if not s.strip().upper().startswith("SET ")]
        assert login_queries == [], f"Malformed-code 422 path executed login SQL: {login_queries}"


# ---------------------------------------------------------------------------
# §4b Production error contract (R2) — exact public body, no repr leak
# ---------------------------------------------------------------------------


class TestProductionErrorContract:
    """The 401/422 responses go through the PRODUCTION exception handlers
    (registered on the test app) and emit the exact mpango_exception_handler
    envelope. No Python dict repr may leak into the message field."""

    async def test_401_is_exact_public_envelope(self, client: AsyncClient, s2_clean_db, provisioned_pool):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code, email, password = await _setup_full_login(db, ws_id=ws_id, schema=schema, registry=reg)
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": _WRONG_PW, "wholesaler_code": code},
        )
        assert resp.status_code == HTTPStatus.UNAUTHORIZED
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "request_id"}
        assert body["code"] == "INVALID_CREDENTIALS"
        assert body["message"] == "Invalid credentials"
        assert isinstance(body["request_id"], str) and body["request_id"]

    async def test_401_message_has_no_dict_repr_leak(self, client: AsyncClient, s2_clean_db, provisioned_pool):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code, email, password = await _setup_full_login(db, ws_id=ws_id, schema=schema, registry=reg)
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "no.such.user@example.com", "password": password, "wholesaler_code": code},
        )
        body = resp.json()
        message = body["message"]
        assert message == "Invalid credentials"
        assert "{" not in message and "}" not in message
        assert "'" not in message and "code" not in message.lower()

    async def test_422_malformed_code_is_clean_envelope(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "a@b.com", "password": _DUMMY_PW, "wholesaler_code": "BAD!CODE"},
        )
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        body = resp.json()
        assert body["code"] == "INVALID_INPUT"
        assert "{" not in body["message"] and "}" not in body["message"]
        assert "request_id" in body


# ---------------------------------------------------------------------------
# §4 JWT context + cross-supplier non-disclosure
# ---------------------------------------------------------------------------


class TestJWTIsContextual:
    """Verify the JWT token is contextual, exact-tenant, and carries no
    tmap / available_tenants."""

    async def test_access_token_has_tenant_claims(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        tokens = resp.json()["data"]["tokens"]
        decoded = decode_token(tokens["access_token"])
        assert decoded.tenant_id is not None
        assert decoded.tenant_schema is not None
        assert decoded.tenant_schema.startswith("t_")
        assert decoded.is_identity_only is False
        assert decoded.type == "access"

    async def test_refresh_token_has_tenant_claims(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        tokens = resp.json()["data"]["tokens"]
        decoded = decode_token(tokens["refresh_token"])
        assert decoded.tenant_id is not None
        assert decoded.tenant_schema is not None
        assert decoded.type == "refresh"

    async def test_no_tmap_in_jwt(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        tokens = resp.json()["data"]["tokens"]
        decoded = decode_token(tokens["access_token"])
        assert decoded.tmap is None

    async def test_roles_is_retailer_operator_only(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        tokens = resp.json()["data"]["tokens"]
        decoded = decode_token(tokens["access_token"])
        assert decoded.roles == ["retailer_operator"]


class TestNoCrossSupplierDisclosure:
    """Response/logs contain no other supplier name/code/schema."""

    async def test_response_contains_only_selected_wholesaler(
        self, client: AsyncClient, two_tenants
    ):
        code_a, code_b, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        data = resp.json()["data"]
        assert data["wholesaler"]["code"] == code_a
        assert code_b not in str(data)

    async def test_schema_in_token_belongs_to_selected_wholesaler(
        self, client: AsyncClient, two_tenants, s2_clean_db
    ):
        db, reg = s2_clean_db
        code_a, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        tokens = resp.json()["data"]["tokens"]
        decoded = decode_token(tokens["access_token"])
        ws_lookup = await _fetch_one(db, "SELECT id FROM public.wholesalers WHERE code = :code", {"code": code_a})
        expected_schema = Wholesaler.derive_schema_from_id(str(ws_lookup.id))
        assert decoded.tenant_schema == expected_schema


# ---------------------------------------------------------------------------
# §5 Refresh / me / logout preserve context
# ---------------------------------------------------------------------------


class TestRefreshPreservesContext:
    """Refresh, /auth/me and logout preserve the selected context."""

    async def test_refresh_returns_same_tenant_context(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        login_resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        refresh_token = login_resp.json()["data"]["tokens"]["refresh_token"]
        original_tenant_id = login_resp.json()["data"]["tokens"]["tenant_id"]

        refresh_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert refresh_resp.status_code == HTTPStatus.OK
        data = refresh_resp.json()["data"]
        assert data["tenant_id"] == original_tenant_id

    async def test_access_token_carries_full_tenant_context(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        login_resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        access_token = login_resp.json()["data"]["tokens"]["access_token"]
        decoded = decode_token(access_token)
        assert decoded.tenant_id is not None
        assert decoded.tenant_schema is not None
        assert decoded.roles == ["retailer_operator"]
        assert decoded.is_identity_only is False

    async def test_logout_succeeds(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        login_resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        access_token = login_resp.json()["data"]["tokens"]["access_token"]

        logout_resp = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_resp.status_code == HTTPStatus.OK


# ---------------------------------------------------------------------------
# §6 Route access control (retailer token denied from protected routes)
# ---------------------------------------------------------------------------


class _FakePerm:
    def __init__(self, code: str):
        self.code = code


class _FakeRole:
    def __init__(self, name: str, permissions: list[str]):
        self.name = name
        self.permissions = [_FakePerm(c) for c in permissions]


class _FakeUser:
    def __init__(self):
        self.roles = [
            _FakeRole("retailer_operator", ["client:catalog:read", "client:orders:read", "client:orders:create"])
        ]


def _retailer_access_token(tenant_id: str, tenant_schema: str) -> str:
    return create_contextual_token(
        user_id=str(uuid.uuid4()),
        roles=["retailer_operator"],
        tenant_id=tenant_id,
        tenant_schema=tenant_schema,
        token_type="access",
    )


async def _build_request_with_retailer_context(tenant_id: str, tenant_schema: str):
    from starlette.requests import Request
    from api.context.auth import AuthContext, attach_auth_context
    from api.context.tenant import TenantContext, attach_tenant_context

    token = TokenPayload(
        user_id=str(uuid.uuid4()),
        roles=["retailer_operator"],
        tenant_id=tenant_id,
        tenant_schema=tenant_schema,
        type="access",
    )
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
    request = Request(scope)
    auth_ctx = AuthContext(token=token, raw_token="retailer-test-token")
    attach_auth_context(request, auth_ctx)
    tenant_ctx = TenantContext(tenant_id=tenant_id, tenant_schema=tenant_schema, session=None, user=_FakeUser())
    attach_tenant_context(request, tenant_ctx)
    return request


class TestRouteAccess:
    """A retailer_operator token (client:* permissions only) is denied by the
    RBAC dependency from every wholesaler/platform route group."""

    async def _pool_ws_schema(self, provisioned_pool) -> tuple[str, str]:
        return provisioned_pool.tenants["a"]["ws_id"], provisioned_pool.tenants["a"]["schema"]

    async def test_denied_from_orders_read(self, s2_clean_db, provisioned_pool):
        _db, _reg = s2_clean_db
        ws_id, schema = await self._pool_ws_schema(provisioned_pool)
        request = await _build_request_with_retailer_context(ws_id, schema)
        with pytest.raises(HTTPException) as exc_info:
            await RequirePermission("orders:read")(request)
        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN
        assert exc_info.value.detail["code"] == "PERMISSION_DENIED"

    async def test_denied_from_finance_read(self, s2_clean_db, provisioned_pool):
        _db, _reg = s2_clean_db
        ws_id, schema = await self._pool_ws_schema(provisioned_pool)
        request = await _build_request_with_retailer_context(ws_id, schema)
        with pytest.raises(HTTPException) as exc_info:
            await RequirePermission("finance:read")(request)
        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN

    async def test_denied_from_payments_read(self, s2_clean_db, provisioned_pool):
        _db, _reg = s2_clean_db
        ws_id, schema = await self._pool_ws_schema(provisioned_pool)
        request = await _build_request_with_retailer_context(ws_id, schema)
        with pytest.raises(HTTPException) as exc_info:
            await RequirePermission("payments:read")(request)
        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN

    async def test_denied_from_invitation_management(self, s2_clean_db, provisioned_pool):
        _db, _reg = s2_clean_db
        ws_id, schema = await self._pool_ws_schema(provisioned_pool)
        request = await _build_request_with_retailer_context(ws_id, schema)
        with pytest.raises(HTTPException) as exc_info:
            await RequirePermission("invitations:create")(request)
        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN

    async def test_denied_from_platform_admin(self, s2_clean_db, provisioned_pool):
        _db, _reg = s2_clean_db
        ws_id, schema = await self._pool_ws_schema(provisioned_pool)
        request = await _build_request_with_retailer_context(ws_id, schema)
        with pytest.raises(HTTPException) as exc_info:
            await RequirePlatformAdmin()(request)
        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN
        assert exc_info.value.detail["code"] == "PLATFORM_ADMIN_REQUIRED"

    async def test_retailer_client_permission_is_allowed(self, s2_clean_db, provisioned_pool):
        _db, _reg = s2_clean_db
        ws_id, schema = await self._pool_ws_schema(provisioned_pool)
        request = await _build_request_with_retailer_context(ws_id, schema)
        token = await RequirePermission("client:catalog:read")(request)
        assert token is not None


# ---------------------------------------------------------------------------
# §6b Real registered-route HTTP proof — Finance denial, no route-body SQL
# ---------------------------------------------------------------------------


class TestRealRegisteredRouteDenials:
    """DC-12R1-S2-R2A-R1: real registered-route HTTP proof via dedicated
    JwtAuthStrategy app fixture.

    Unlike ``TestRouteAccess`` (which invokes the RBAC *dependency* directly),
    this class exercises **actual registered product routes over HTTP** using a
    real retailer JWT obtained through ``POST /api/v1/client/auth/login``.

    The client fixture's app is wired with the production JwtAuthStrategy via
    mock.patch (not shared app mutation), so the Bearer token is actually
    decoded and tenant context is resolved from the database.

    Finance denial: ``GET /api/v1/finance/summary`` requires ``finance:read``.
    SQL capture proves the route body query does NOT execute after denial."""

    @staticmethod
    def _assert_flat_403_denial(resp, expected_code: str):
        assert resp.status_code == HTTPStatus.FORBIDDEN, f"expected 403, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["code"] == expected_code, body
        assert "message" in body and isinstance(body["message"], str)
        assert "request_id" in body and body["request_id"]
        text = resp.text
        assert "'code'" not in text and "{'" not in text and "'}" not in text
        assert "['" not in text
        for leak in ("postgresql", "select ", "select_", "tenant_schema", "Traceback", "Exception", "Error:"):
            assert leak not in text, f"internal info leaked ({leak!r}): {text}"

    async def _retailer_token(self, client: AsyncClient, two_tenants) -> str:
        """Obtain a REAL retailer JWT through the production login endpoint."""
        code_a, _code_b, _schema_b, email, password, _a, _b = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        assert resp.status_code == HTTPStatus.OK, resp.text
        return resp.json()["data"]["tokens"]["access_token"]

    async def test_finance_route_denied_over_http(self, client: AsyncClient, two_tenants):
        """GET /api/v1/finance/summary requires finance:read → retailer 403.

        The client fixture already uses JwtAuthStrategy, so the real
        RequirePermission gate fires before any route-body query."""
        token = await self._retailer_token(client, two_tenants)
        resp = await client.get(
            "/api/v1/finance/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        self._assert_flat_403_denial(resp, "PERMISSION_DENIED")

    async def test_orders_route_denied_over_http(self, client: AsyncClient, two_tenants):
        token = await self._retailer_token(client, two_tenants)
        resp = await client.get(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {token}"},
        )
        self._assert_flat_403_denial(resp, "PERMISSION_DENIED")

    async def test_payments_route_denied_over_http(self, client: AsyncClient, two_tenants):
        token = await self._retailer_token(client, two_tenants)
        resp = await client.get(
            "/api/v1/payments",
            headers={"Authorization": f"Bearer {token}"},
        )
        self._assert_flat_403_denial(resp, "PERMISSION_DENIED")

    async def test_invitation_route_denied_over_http(self, client: AsyncClient, two_tenants):
        token = await self._retailer_token(client, two_tenants)
        resp = await client.post(
            "/api/v1/invitations",
            json={"email": "someone@example.com", "role": "viewer"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self._assert_flat_403_denial(resp, "PERMISSION_DENIED")

    async def test_platform_route_denied_over_http(self, client: AsyncClient, two_tenants):
        token = await self._retailer_token(client, two_tenants)
        resp = await client.get(
            "/api/v1/platform/p10/tenants",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
            f"expected controlled platform denial, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body["code"] == "PLATFORM_ACCESS_REQUIRED", body
        assert "message" in body and isinstance(body["message"], str)
        assert "request_id" in body and body["request_id"]
        text = resp.text
        assert "'code'" not in text and "{'" not in text and "'}" not in text
        for leak in ("postgresql", "select ", "tenant_schema", "Traceback", "Exception"):
            assert leak not in text, f"internal info leaked ({leak!r}): {text}"

    async def test_finance_denied_route_body_does_not_execute(
        self, client: AsyncClient, two_tenants
    ):
        """SQL-capture proof: when the finance route denies, the protected
        resource query never runs. The only SQL permitted is the auth
        middleware's tenant/user resolution — never a finance/ledger read."""
        from database.session import async_engine

        token = await self._retailer_token(client, two_tenants)
        captured: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            captured.append(statement)

        event.listen(async_engine.sync_engine, "before_cursor_execute", _capture)
        try:
            resp = await client.get(
                "/api/v1/finance/summary",
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _capture)
        assert resp.status_code == HTTPStatus.FORBIDDEN
        offending = [s for s in captured if "finance" in s.lower() or "ledger" in s.lower()]
        assert not offending, f"denied route executed resource SQL: {offending}"

    async def test_denied_route_body_does_not_execute(
        self, client: AsyncClient, two_tenants
    ):
        """Orders route denial — same SQL-capture proof."""
        from database.session import async_engine

        token = await self._retailer_token(client, two_tenants)
        captured: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            captured.append(statement)

        event.listen(async_engine.sync_engine, "before_cursor_execute", _capture)
        try:
            resp = await client.get(
                "/api/v1/orders",
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _capture)
        assert resp.status_code == HTTPStatus.FORBIDDEN
        offending = [s for s in captured if "orders" in s.lower()]
        assert not offending, f"denied route executed resource SQL: {offending}"

    async def test_retailer_can_still_use_permitted_client_route(
        self, client: AsyncClient, two_tenants
    ):
        """Allowed-path proof: the same retailer JWT is NOT blanket-denied."""
        code_a, _code_b, _schema_b, email, password, _a, _b = two_tenants
        token = (await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )).json()["data"]["tokens"]["access_token"]

        # The fully-bootstrapped tenant already has skus / inventory_stocks /
        # retailer_prices tables — no handwritten CREATE TABLE needed.
        resp = await client.get(
            "/api/v1/client/products",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == HTTPStatus.OK


# ---------------------------------------------------------------------------
# §7 Fail-closed: soft-deleted lifecycle rows + duplicate registry rows
# ---------------------------------------------------------------------------


class TestFailClosedLifecycle:
    """Soft-deleted registration/user/role/retailer and duplicate registry rows
    all fail with a neutral 401 (never authenticate, never 500)."""

    async def _assert_neutral_401(self, resp):
        assert resp.status_code == HTTPStatus.UNAUTHORIZED
        body = resp.json()
        assert body["code"] == "INVALID_CREDENTIALS"
        assert body["message"] == "Invalid credentials"
        assert "request_id" in body and body["request_id"]
        assert "{" not in body["message"] and "}" not in body["message"]
        assert "detail" not in body

    async def test_soft_deleted_registration_returns_neutral_401(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code, email, password = await _setup_full_login(db, ws_id=ws_id, schema=schema, registry=reg)
        reg_row = await _fetch_one(
            db,
            "SELECT id, is_deleted FROM public.tenant_registrations "
            "WHERE wholesaler_id = (SELECT id FROM public.wholesalers WHERE code = :code)",
            {"code": code},
        )
        if reg_row:
            reg.register_mutation("public.tenant_registrations", str(reg_row.id), "is_deleted", reg_row.is_deleted)
        await _execute(
            db,
            "UPDATE public.tenant_registrations SET is_deleted = true "
            "WHERE wholesaler_id = (SELECT id FROM public.wholesalers WHERE code = :code)",
            {"code": code},
        )
        await db.commit()

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_soft_deleted_user_returns_neutral_401(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code, email, password = await _setup_full_login(db, ws_id=ws_id, schema=schema, registry=reg)
        await _execute(
            db,
            f'UPDATE "{schema}".users SET is_deleted = true WHERE email = :email',
            {"email": email},
        )
        await db.commit()

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_soft_deleted_role_returns_neutral_401(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code, email, password = await _setup_full_login(db, ws_id=ws_id, schema=schema, registry=reg)
        role_row = await _fetch_one(
            db,
            f'SELECT id, is_deleted FROM "{schema}".roles WHERE name = \'retailer_operator\'',
        )
        if role_row:
            reg.register_mutation(f'"{schema}".roles', str(role_row.id), "is_deleted", role_row.is_deleted)
        await _execute(
            db,
            f'UPDATE "{schema}".roles SET is_deleted = true WHERE name = \'retailer_operator\'',
        )
        await db.commit()

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_soft_deleted_retailer_returns_neutral_401(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code, email, password = await _setup_full_login(db, ws_id=ws_id, schema=schema, registry=reg)
        await _execute(
            db,
            "UPDATE public.retailers SET is_deleted = true "
            "WHERE id IN (SELECT retailer_id FROM public.wholesaler_retailer_bindings b "
            "JOIN public.wholesalers w ON w.id = b.wholesaler_id WHERE w.code = :code)",
            {"code": code},
        )
        await db.commit()

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_duplicate_active_registrations_rejected_at_db_and_code(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        pool_code = provisioned_pool.tenants["a"]["code"]
        code, email, password = await _setup_full_login(db, ws_id=ws_id, schema=schema, registry=reg)
        code = pool_code

        ws_row = await _fetch_one(
            db,
            "SELECT w.id AS wid, tr.tenant_schema AS schema "
            "FROM public.wholesalers w "
            "JOIN public.tenant_registrations tr ON tr.wholesaler_id = w.id "
            "WHERE w.code = :code",
            {"code": pool_code},
        )

        dup_reg_id = str(uuid.uuid4())
        reg.register_registration(dup_reg_id)
        with pytest.raises(IntegrityError):
            await _execute(
                db,
                "INSERT INTO public.tenant_registrations "
                "(id, company_name, tenant_code, country, owner_email, status, "
                " wholesaler_id, tenant_schema, expires_at, password_hash_cleared_at) "
                "VALUES (:id, :company, :code2, 'TZ', :email2, 'active', "
                " :ws_id, :schema, :expires, :cleared)",
                {
                    "id": dup_reg_id,
                    "company": f"Company Dup {pool_code}",
                    "code2": _unique_code("DUP"),
                    "email2": _unique_email(),
                    "ws_id": ws_row.wid,
                    "schema": ws_row.schema,
                    "expires": datetime.now(timezone.utc) + timedelta(days=365),
                    "cleared": datetime.now(timezone.utc),
                },
            )
            await db.commit()
        await db.rollback()

        from api.v1.client import auth as auth_module
        from schemas.retailer_credentials import RetailerLoginRequest

        class _Row:
            def __init__(self, **kw):
                for k, v in kw.items():
                    setattr(self, k, v)

        class _Result:
            def __init__(self, rows):
                self._rows = rows
            def fetchall(self):
                return self._rows

        class _StubSession:
            async def execute(self, _stmt, _params=None):
                return _Result([
                    _Row(id=ws_row.wid, code=code, name="A", status="active",
                         registration_id=uuid.uuid4(), tenant_schema=ws_row.schema),
                    _Row(id=ws_row.wid, code=code, name="B", status="active",
                         registration_id=uuid.uuid4(), tenant_schema=ws_row.schema),
                ])

        req = RetailerLoginRequest(email=email, password=password, wholesaler_code=code)
        with pytest.raises(MpangoAPIException) as exc_info:
            await auth_module.retailer_login(req, _StubSession())
        assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
        assert exc_info.value.error_code.value == "INVALID_CREDENTIALS"
        assert exc_info.value.message == "Invalid credentials"


# ---------------------------------------------------------------------------
# §8 Rate limit returns controlled 429, never 500
# ---------------------------------------------------------------------------


class TestRateLimit429:
    """POST /client/auth/login, when rate-limited through the real
    RateLimitingMiddleware, returns a controlled 429 (never 500) carrying the
    required X-RateLimit-* / Retry-After headers."""

    async def test_rate_limited_login_returns_429_with_headers(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        import core.rate_limiter as rl_mod
        from core.cache import get_redis_client

        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code, email, password = await _setup_full_login(db, ws_id=ws_id, schema=schema, registry=reg)

        test_ip = f"203.0.113.{(uuid.uuid4().int % 200) + 1}"
        headers = {"X-Forwarded-For": test_ip}

        original_limit = rl_mod.DEFAULT_IP_LIMIT
        rl_mod.DEFAULT_IP_LIMIT = 3
        try:
            statuses = []
            for _ in range(rl_mod.DEFAULT_IP_LIMIT + 2):
                resp = await client.post(
                    "/api/v1/client/auth/login",
                    json={"email": email, "password": password, "wholesaler_code": code},
                    headers=headers,
                )
                statuses.append(resp.status_code)

            assert statuses[-1] == HTTPStatus.TOO_MANY_REQUESTS, f"Expected final 429, got statuses {statuses}"
            assert statuses[0] != HTTPStatus.TOO_MANY_REQUESTS

            limited = next(r for r in [resp] if r.status_code == HTTPStatus.TOO_MANY_REQUESTS)
            assert "Retry-After" in limited.headers
            assert "X-RateLimit-Limit" in limited.headers
            assert "X-RateLimit-Remaining" in limited.headers
            assert "X-RateLimit-Reset" in limited.headers
            assert int(limited.headers["X-RateLimit-Remaining"]) == 0
        finally:
            rl_mod.DEFAULT_IP_LIMIT = original_limit
            _r = await get_redis_client()
            cursor = 0
            while True:
                cursor, keys = await _r.scan(cursor=cursor, match=f"rate_limit:ip:{test_ip}:*", count=100)
                if keys:
                    await _r.delete(*keys)
                if cursor == 0:
                    break


# ---------------------------------------------------------------------------
# §9 Owner login unchanged
# ---------------------------------------------------------------------------


class TestOwnerLoginUnchanged:
    """Owner login still returns its existing available_tenants contract."""

    async def test_owner_login_returns_available_tenants(
        self, client: AsyncClient, s2_clean_db, provisioned_pool
    ):
        db, reg = s2_clean_db
        ws_id = provisioned_pool.tenants["a"]["ws_id"]
        schema = provisioned_pool.tenants["a"]["schema"]
        code = provisioned_pool.tenants["a"]["code"]
        email = _unique_email()
        password = _OWNER_PW

        uid = await _create_retailer_user(db, tenant_schema=schema, email=email, password=password, registry=reg)
        await _execute(
            db,
            f'INSERT INTO "{schema}".roles (name, description) '
            "VALUES ('admin', 'Tenant Admin') ON CONFLICT (name) DO NOTHING",
        )
        await _execute(
            db,
            f'INSERT INTO "{schema}".user_roles (user_id, role_id) '
            f"SELECT :uid, id FROM \"{schema}\".roles WHERE name = 'admin'",
            {"uid": uid},
        )
        await db.commit()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()["data"]
        assert "available_tenants" in data
        assert len(data["available_tenants"]) >= 1
        assert any(t["code"] == code for t in data["available_tenants"])
