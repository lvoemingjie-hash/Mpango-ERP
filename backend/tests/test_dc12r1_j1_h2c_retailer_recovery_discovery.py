"""DC-12R1-MVP-L1-J1-H2-C-R1 + R1-R1: retailer recovery discovery backend contract.

R1 (BASE 8ad346e5) proved the H2-C backend half but left test residue: the
two database tests provisioned real identities through the official S1
lifecycle and committed them (wholesaler/retailer/binding/invitation/token
plus two derived tenant schemas); the shared s1_db fixture cleans public
tables only BEFORE each test with LIKE-prefix deletes and never drops
schemas nor runs after the final test.

R1-R1 (this revision) closes two gaps:

  1. Canonical neutrality RUNTIME proof (HC07-HC10): the four outcome
     states are exercised through the REAL ASGI endpoint
     POST /api/v1/client/auth/forgot-password against REAL PostgreSQL,
     provisioned via the formal retailer lifecycle. All four responses
     assert status 200, the exact key set success/data/message/timestamp,
     success is True, data == {}, message exactly
     NEUTRAL_RETAILER_CREDENTIAL_MESSAGE, and a present parseable string
     timestamp; with ONLY the timestamp value replaced by a sentinel the
     four objects are key-for-key equal. No raw-byte equality, no
     response-duration equality, and no timing side-channel closure is
     claimed. Side effects: only HC07 issues exactly one token and one
     email; HC08-HC10 produce zero tokens and zero emails.

  2. Bounded test-residue closure: every identity created by this module
     is registered (exact ids + exact schema names) and removed by a
     finalizer that ALWAYS runs (test success or failure) on a FRESH
     connection in FK-safe order (setup/reset tokens -> binding ->
     invitation -> retailer -> wholesaler -> DROP of the exact schema
     name), with no LIKE/prefix/wildcard/full-table deletion/global
     reset/DROP DATABASE. A SECOND fresh connection then proves every
     registered identity and schema is gone. Teardown failures raise
     without masking a failing test body (pytest reports both). The
     module's final test re-proves zero residue for the whole module.

Mutation anchors (each must go RED when the hygiene regresses):
  C1  removing the finalizer cleanup -> module residue proof RED.
  C2  cleaning public rows without dropping the exact schema -> schema
      zero-proof RED.
  C3  dropping schemas without cleaning public identities -> public-row
      zero-proof RED.
  C4  changing the neutral message or adding a response key -> the
      canonical equality assertion RED.

The pre-existing full-suite 4/0/29 hygiene debt is untouched and remains
owned by the full-suite lineage; this module cleans only its OWN exact
identities.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from api.app import app
from api.dependencies import get_db_session
from api.v1.client.auth import NEUTRAL_RETAILER_CREDENTIAL_MESSAGE
from services.email_delivery import (
    clear_dev_email_deliveries,
    get_dev_retailer_email_deliveries,
)
from services.onboarding_service import build_retailer_reset_link
from services.retailer_provisioning_service import RetailerProvisioningService

# Shared PURE helpers from the S1 suite (unchanged): _make_tenant creates a
# wholesaler + derived tenant schema with RBAC tables; _create_invitation
# inserts an invitation row. The shared s1_db FIXTURE is intentionally NOT
# consumed by this module (see docstring: residue closure).
from tests.test_dc12r1_s1_retailer_identity import (  # noqa: F401
    _create_invitation,
    _make_tenant,
)

pytestmark = pytest.mark.asyncio

FORGOT_URL = "/api/v1/client/auth/forgot-password"


# ---------------------------------------------------------------------------
# Identity registry + exact-id cleanup (R1-R1)
# ---------------------------------------------------------------------------

class _Registry:
    """Exact identities created by ONE test (and mirrored module-wide)."""

    def __init__(self) -> None:
        self.setup_token_ids: list[str] = []
        self.reset_token_ids: list[str] = []
        self.binding_ids: list[str] = []
        self.invitation_ids: list[str] = []
        self.retailer_ids: list[str] = []
        self.wholesaler_ids: list[str] = []
        self.schemas: list[str] = []


_MODULE_REGISTRY = _Registry()

_FK_ORDER_TABLES = (
    ("retailer_credential_setup_tokens", "setup_token_ids"),
    ("retailer_password_reset_tokens", "reset_token_ids"),
    ("wholesaler_retailer_bindings", "binding_ids"),
    ("invitations", "invitation_ids"),
    ("retailers", "retailer_ids"),
    ("wholesalers", "wholesaler_ids"),
)


@asynccontextmanager
async def _fresh_session():
    """A FRESH engine/connection mirroring the production public-schema
    dependency semantics (database.session.get_db sets
    session.info["tenant_schema"] = "public"), never the pooled default."""
    import os

    url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            session.info["tenant_schema"] = "public"
            yield session
    finally:
        await engine.dispose()


async def _retailer_id_by_email(email: str) -> str:
    async with _fresh_session() as db:
        return str(
            (
                await db.execute(
                    text("SELECT id FROM public.retailers WHERE email = :exact"),
                    {"exact": email},
                )
            ).scalar_one()
        )


async def _sweep_tokens(registry: _Registry, retailer_id: str) -> None:
    """Register every token row for one EXACT retailer id (exact FK id)."""
    async with _fresh_session() as db:
        for table, attr in (
            ("retailer_credential_setup_tokens", "setup_token_ids"),
            ("retailer_password_reset_tokens", "reset_token_ids"),
        ):
            rows = (
                await db.execute(
                    text(f"SELECT id FROM public.{table} WHERE retailer_id = :rid"),
                    {"rid": retailer_id},
                )
            ).fetchall()
            getattr(registry, attr).extend(str(r[0]) for r in rows)


async def _cleanup_exact(registry: _Registry) -> None:
    """FK-safe, EXACT-id cleanup + exact-schema DROP on a fresh connection."""
    async with _fresh_session() as db:
        for table, attr in _FK_ORDER_TABLES:
            for exact_id in getattr(registry, attr):
                await db.execute(
                    text(f"DELETE FROM public.{table} WHERE id = :exact"),
                    {"exact": exact_id},
                )
        await db.commit()
    for schema in registry.schemas:
        async with _fresh_session() as db:
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await db.commit()


async def _prove_zero(registry: _Registry) -> None:
    """SECOND fresh connection: every exact identity and schema is gone."""
    problems: list[str] = []
    async with _fresh_session() as db:
        for table, attr in _FK_ORDER_TABLES:
            for exact_id in getattr(registry, attr):
                count = (
                    await db.execute(
                        text(f"SELECT count(*) FROM public.{table} WHERE id = :exact"),
                        {"exact": exact_id},
                    )
                ).scalar_one()
                if count:
                    problems.append(f"{table}:{exact_id} still present")
        for schema in registry.schemas:
            count = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM information_schema.schemata "
                        "WHERE schema_name = :exact"
                    ),
                    {"exact": schema},
                )
            ).scalar_one()
            if count:
                problems.append(f"schema:{schema} still present")
    assert not problems, "residue zero-proof failed: " + "; ".join(problems)


@pytest.fixture
async def h2c_registry():
    """Registry + ALWAYS-RUN finalizer (test success or failure alike).

    Teardown failures raise (pytest reports them alongside, never instead
    of, a failing test body) so cleanup errors can never mask original
    failures.
    """
    registry = _Registry()
    yield registry
    # Mirror into the module registry BEFORE cleanup so the module-level
    # residue proof re-verifies these exact identities independently.
    for attr in (
        "setup_token_ids",
        "reset_token_ids",
        "binding_ids",
        "invitation_ids",
        "retailer_ids",
        "wholesaler_ids",
        "schemas",
    ):
        getattr(_MODULE_REGISTRY, attr).extend(getattr(registry, attr))
    # Finalizer: exact cleanup, then an independent zero-proof. Both run
    # even when the test body failed; failures here surface as teardown
    # errors WITHOUT replacing the original test failure.
    await _cleanup_exact(registry)
    await _prove_zero(registry)


# ---------------------------------------------------------------------------
# Provisioning through the FORMAL retailer lifecycle (exact registration)
# ---------------------------------------------------------------------------

async def _register_ws_and_schema(db: AsyncSession, registry: _Registry, code: str) -> tuple[str, str]:
    ws_id, schema = await _make_tenant(db, code=code)
    registry.wholesaler_ids.append(str(ws_id))
    registry.schemas.append(schema)
    return str(ws_id), schema


async def _register_invitation(db: AsyncSession, registry: _Registry, ws_id: str, phone: str) -> str:
    code = await _create_invitation(db, wholesaler_id=ws_id, phone=phone)
    inv_id = (
        await db.execute(
            text("SELECT id FROM public.invitations WHERE code = :exact"),
            {"exact": code},
        )
    ).scalar_one()
    registry.invitation_ids.append(str(inv_id))
    return code


async def _register_retailer(db: AsyncSession, registry: _Registry, ws_id: str, code: str, phone: str, email: str) -> str:
    svc = RetailerProvisioningService(db)
    await svc.register_with_invitation(invitation_code=code, phone=phone, email=email)
    await db.commit()
    retailer_id = (
        await db.execute(
            text("SELECT id FROM public.retailers WHERE email = :exact"),
            {"exact": email},
        )
    ).scalar_one()
    registry.retailer_ids.append(str(retailer_id))
    binding_id = (
        await db.execute(
            text(
                "SELECT id FROM public.wholesaler_retailer_bindings "
                "WHERE wholesaler_id = :w AND retailer_id = :r"
            ),
            {"w": ws_id, "r": retailer_id},
        )
    ).scalar_one()
    registry.binding_ids.append(str(binding_id))
    await _sweep_tokens(registry, str(retailer_id))
    return str(retailer_id)


async def _established_retailer(registry: _Registry, *, code: str) -> tuple[str, str, str]:
    """Official lifecycle: tenant -> invitation -> register -> setup password."""
    async with _fresh_session() as db:
        ws_id, _schema = await _register_ws_and_schema(db, registry, code)
        phone = "+15552901"
        email = f"h2c-{uuid.uuid4().hex[:8]}@example.com"
        invitation = await _register_invitation(db, registry, ws_id, phone)
        retailer_id = await _register_retailer(db, registry, ws_id, invitation, phone, email)
        svc = RetailerProvisioningService(db)
        await svc.consume_setup_token(
            get_dev_retailer_email_deliveries(email)[0].token, "OldPass1!"
        )
        await db.commit()
        await _sweep_tokens(registry, retailer_id)
        canonical = (
            await db.execute(
                text("SELECT code FROM public.wholesalers WHERE id = :exact"),
                {"exact": ws_id},
            )
        ).scalar_one()
    return email, ws_id, canonical


# ---------------------------------------------------------------------------
# Unit contract: build_retailer_reset_link shapes (legacy + H2-C, R1 kept)
# ---------------------------------------------------------------------------

async def test_reset_link_legacy_shape_unchanged_without_code():
    """No wholesaler_code -> EXACT legacy shape (M4 anchor: old links valid)."""
    token = "raw-reset-token-1"
    link = build_retailer_reset_link(token)
    assert link == "/retailer/reset-password#resetToken=raw-reset-token-1"
    assert "?" not in link
    assert "w=" not in link


async def test_reset_link_with_canonical_code_keeps_fragment_only():
    """HC11: w joins resetToken in the FRAGMENT; never a query param."""
    link = build_retailer_reset_link("tok 1", wholesaler_code="H2CAB01")
    assert link.startswith("/retailer/reset-password#resetToken=")
    assert link.endswith("&w=H2CAB01")
    assert "?" not in link
    head, fragment = link.split("#", 1)
    assert head == "/retailer/reset-password"
    assert fragment.startswith("resetToken=tok%201&")


# ---------------------------------------------------------------------------
# Integration: email carries the DB-canonical code (HC17, R1 kept; now
# residue-closed through the registry fixture instead of s1_db)
# ---------------------------------------------------------------------------

async def test_forgot_password_email_carries_db_canonical_uppercase_code(h2c_registry):
    """HC17 + M5 anchor: lowercase caller input -> email w is the CANONICAL
    DB code (uppercase), never the caller's raw casing. M4 anchor: w present."""
    email, _ws_id, canonical = await _established_retailer(
        h2c_registry, code=f"S1T{uuid.uuid4().hex[:5].upper()}"
    )
    assert canonical == canonical.upper()

    clear_dev_email_deliveries()
    async with _fresh_session() as db:
        svc = RetailerProvisioningService(db)
        issued = await svc.request_password_reset(
            email=email, wholesaler_code=canonical.lower()
        )
        await db.commit()
    assert issued is True

    deliveries = get_dev_retailer_email_deliveries(email)
    assert len(deliveries) == 1
    link = deliveries[0].link
    assert link.startswith("/retailer/reset-password#resetToken=")
    assert f"&w={canonical}" in link
    assert "?" not in link
    assert f"&w={canonical.lower()}" not in link
    assert "resetToken" not in link.split("#", 1)[0]
    await _sweep_tokens(h2c_registry, await _retailer_id_by_email(email))


async def test_forgot_password_email_w_matches_case_insensitive_lookup(h2c_registry):
    """The case-insensitive DB match still finds the retailer for a mixed-case
    caller code, and the delivered link w equals the canonical code exactly."""
    email, _ws_id, canonical = await _established_retailer(
        h2c_registry, code=f"S1T{uuid.uuid4().hex[:5].upper()}"
    )
    clear_dev_email_deliveries()
    async with _fresh_session() as db:
        svc = RetailerProvisioningService(db)
        mixed = canonical[0] + canonical[1:].lower()
        issued = await svc.request_password_reset(email=email, wholesaler_code=mixed)
        await db.commit()
    assert issued is True
    link = get_dev_retailer_email_deliveries(email)[0].link
    assert f"&w={canonical}" in link
    await _sweep_tokens(h2c_registry, await _retailer_id_by_email(email))


# ---------------------------------------------------------------------------
# HC07-HC10: canonical neutrality through the REAL ASGI endpoint
# ---------------------------------------------------------------------------

def _assert_canonical_neutral_body(body: dict) -> None:
    assert set(body.keys()) == {"success", "data", "message", "timestamp"}, body.keys()
    assert body["success"] is True
    assert body["data"] == {}
    assert body["message"] == NEUTRAL_RETAILER_CREDENTIAL_MESSAGE
    ts = body["timestamp"]
    assert isinstance(ts, str) and ts, "timestamp must be a non-empty string"
    datetime.fromisoformat(ts.replace("Z", "+00:00"))  # parseable


def _sentinel(body: dict) -> dict:
    canon = dict(body)
    canon["timestamp"] = "<SENTINEL>"  # ONLY the timestamp value is replaced
    return canon


def _real_client() -> AsyncClient:
    """Per-request session override mirroring the production dependency."""

    async def _override():
        async with _fresh_session() as session:
            await session.execute(text("SET search_path TO public"))
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _code_for_wholesaler(ws_id: str) -> str:
    async with _fresh_session() as db:
        return (
            await db.execute(
                text("SELECT code FROM public.wholesalers WHERE id = :exact"),
                {"exact": ws_id},
            )
        ).scalar_one()


async def test_hc07_hc10_canonical_neutrality_real_http(h2c_registry):
    """Four real-HTTP states, canonical response equality with timestamp
    sentinel, and exact side-effect accounting."""
    # HC07 supply: established (verified + password) retailer, correct code.
    email7, _ws7, canonical7 = await _established_retailer(
        h2c_registry, code=f"S1T{uuid.uuid4().hex[:5].upper()}"
    )
    # HC10 supply: same lifecycle but the setup token is NOT consumed, so
    # email stays unverified for this retailer+supplier pair.
    async with _fresh_session() as db:
        ws10, _schema10 = await _register_ws_and_schema(
            db, h2c_registry, f"S1T{uuid.uuid4().hex[:5].upper()}"
        )
        phone10 = "+15552902"
        email10 = f"h2c-{uuid.uuid4().hex[:8]}@example.com"
        invitation10 = await _register_invitation(db, h2c_registry, ws10, phone10)
        await _register_retailer(db, h2c_registry, ws10, invitation10, phone10, email10)
        canonical10 = await _code_for_wholesaler(ws10)

    clear_dev_email_deliveries()
    try:
        async with _real_client() as client:
            r7 = await client.post(
                FORGOT_URL, json={"email": email7, "wholesaler_code": canonical7}
            )
            r8 = await client.post(
                FORGOT_URL,
                json={
                    "email": f"ghost-{uuid.uuid4().hex[:8]}@example.com",
                    "wholesaler_code": canonical7,
                },
            )
            r9 = await client.post(
                FORGOT_URL,
                json={
                    "email": email7,
                    "wholesaler_code": f"WRONG{uuid.uuid4().hex[:6].upper()}",
                },
            )
            r10 = await client.post(
                FORGOT_URL,
                json={"email": email10, "wholesaler_code": canonical10},
            )
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    bodies = {}
    for label, response in (("HC07", r7), ("HC08", r8), ("HC09", r9), ("HC10", r10)):
        assert response.status_code == 200, (label, response.status_code, response.text)
        body = response.json()
        _assert_canonical_neutral_body(body)
        bodies[label] = body

    # Canonical equality: ONLY the timestamp value is replaced by a sentinel;
    # no raw-byte or duration equality is claimed.
    s7, s8, s9, s10 = (_sentinel(bodies[k]) for k in ("HC07", "HC08", "HC09", "HC10"))
    assert s7 == s8 == s9 == s10

    # Side effects: exactly ONE token + ONE email for HC07; zero for the rest.
    async with _fresh_session() as db:
        tokens7 = (
            await db.execute(
                text(
                    "SELECT id FROM public.retailer_password_reset_tokens "
                    "WHERE retailer_id = (SELECT id FROM public.retailers WHERE email = :e)"
                ),
                {"e": email7},
            )
        ).fetchall()
        tokens10 = (
            await db.execute(
                text(
                    "SELECT id FROM public.retailer_password_reset_tokens "
                    "WHERE retailer_id = (SELECT id FROM public.retailers WHERE email = :e)"
                ),
                {"e": email10},
            )
        ).fetchall()
    assert len(tokens7) == 1
    assert len(tokens10) == 0
    h2c_registry.reset_token_ids.extend(str(r[0]) for r in tokens7)
    deliveries = get_dev_retailer_email_deliveries()
    assert len([d for d in deliveries if d.to_email == email7.lower()]) == 1
    assert len([d for d in deliveries if d.to_email == email10.lower()]) == 0


# ---------------------------------------------------------------------------
# Module residue proof (C1/C2/C3 anchor) — MUST remain the final test.
# ---------------------------------------------------------------------------

async def test_module_residue_zero():
    """Fresh connection: every identity/schema this module created is gone.

    RED under C1 (no cleanup), C2 (rows cleaned but schema kept), and
    C3 (schema dropped but public rows kept).
    """
    await _prove_zero(_MODULE_REGISTRY)
