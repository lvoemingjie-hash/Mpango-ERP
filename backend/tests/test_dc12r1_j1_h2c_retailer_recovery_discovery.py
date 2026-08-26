"""DC-12R1-MVP-L1-J1-H2-C backend contract — R1 + R1-R1 + R1-R2.

R1 (8ad346e5) proved the H2-C backend half (HC11/HC17 email link shapes).
R1-R1 (d1198f3b) added exact-id registry cleanup and the HC07-HC10 real-ASGI
canonical neutrality proof, but Kilo's bounded delta review
(reports/dc12r1-mvp-l1-j1-h2-c-r1-r1-v1-kilo-bounded-delta-review-2026-08-27,
commit 09a61608) returned STOP with two P1 findings, reproduced on the
unmodified R1-R1 BASE:

  P1-A TEST_HYGIENE_DEFECT (failure window). The R1-R1 finalizer operated
     only on exact IDs already registered by the test body. A body failure
     between a commit and the manual ID registration left committed objects
     outside the registry. Mechanism correction recorded by R1-R2: on this
     schema the token->retailer FKs are ON DELETE CASCADE, so the literal
     "FK violation rolls back cleanup" path does not occur; the
     reproducible defect is SILENT residue — an unregistered committed
     identity (e.g. the retailer row) survives the finalizer with ZERO
     errors raised while the registry-only zero-proof stays green.
  P1-B GLOBAL_TEST_STATE_RESIDUE. The dev retailer email sink is never
     cleared after tests (one HC07 delivery survives an in-process module
     run), and _real_client popped app.dependency_overrides
     unconditionally, destroying any pre-existing foreign override.

R1-R2 (this revision) closes both:

  * STABLE ANCHORS are registered BEFORE the side effects that create the
    objects (exact email/phone up front; wholesaler id + schema name the
    moment they exist; invitation code the moment it exists).
  * The finalizer RE-DISCOVERS every id from the anchors on a fresh
    connection (retailer by exact email/phone; binding by exact
    wholesaler scope and retailer scope; invitation by exact code and
    exact wholesaler scope; setup/reset tokens by exact retailer_id)
    BEFORE the FK-safe exact-id cleanup, deduplicating with anything
    already registered. A body that fails mid-side-effect can therefore
    never strand a committed object. No LIKE/prefix/wildcard/full-table
    delete/global reset/DROP DATABASE anywhere.
  * The cleanup lifecycle is a DIRECTLY TESTABLE async context manager
    (_residue_lifecycle); the pytest fixture only wraps it. Body, hydrate,
    cleanup, and zero-proof failures are each preserved; multiple
    simultaneous failures raise ExceptionGroup/BaseExceptionGroup without
    covering the original body exception. Cleanup is best-effort per step
    (a failing step never aborts the remaining safe steps; failed steps
    are retried once, and even healed transient step failures are reported
    in the cleanup error). All engines/sessions close in finally.
  * GLOBAL STATE: the module fails closed if the dev retailer email sink
    is non-empty at entry; every lifecycle teardown clears the sink in
    finally; dependency overrides are restored to their EXACT previous
    value (never unconditionally popped); _MODULE_STATE anchors are
    initialized at module start and cleared at module end so repeated
    module runs inherit nothing; the final test proves DB objects,
    schemas, email sink, dependency overrides (per-key object identity),
    and idle DB connections are all zero.

Mutation anchors:
  C1 removing the finalizer cleanup -> residue proofs RED.
  C2 cleaning public rows without dropping the exact schemas -> schema
     zero-proof RED.
  C3 dropping schemas without cleaning public identities -> public-row
     zero-proof RED.
  C4 mutating the endpoint's neutral message -> canonical test RED.
  C5 removing the anchor re-discovery (hydration) -> failure-window tests
     RED (committed objects outside the registry leak silently).
  C6 removing the email-sink teardown -> sink zero-proofs RED.
  C7 not restoring the exact dependency override -> FW4 RED.
  C8 dropping the exception aggregation / covering the body exception ->
     FW5 dual-failure proof RED.
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

# Shared PURE helpers from the S1 suite (unchanged). The shared s1_db
# FIXTURE is intentionally NOT consumed by this module.
from tests.test_dc12r1_s1_retailer_identity import (  # noqa: F401
    _create_invitation,
    _make_tenant,
)

pytestmark = pytest.mark.asyncio

FORGOT_URL = "/api/v1/client/auth/forgot-password"


class _SentinelError(RuntimeError):
    """Marker exception for failure-window cut points."""


# ---------------------------------------------------------------------------
# Stable anchors, registries, module state
# ---------------------------------------------------------------------------

class _Anchors:
    """Stable identities registered BEFORE the side effects creating objects."""

    def __init__(self) -> None:
        self.emails: list[str] = []
        self.phones: list[str] = []
        self.invitation_codes: list[str] = []
        self.wholesaler_ids: list[str] = []
        self.schemas: list[str] = []

    def extend_from(self, other: "_Anchors") -> None:
        self.emails.extend(other.emails)
        self.phones.extend(other.phones)
        self.invitation_codes.extend(other.invitation_codes)
        self.wholesaler_ids.extend(other.wholesaler_ids)
        self.schemas.extend(other.schemas)


class _Registry:
    """Per-test anchors plus any exact ids already discovered."""

    def __init__(self) -> None:
        self.anchors = _Anchors()
        self.setup_token_ids: list[str] = []
        self.reset_token_ids: list[str] = []
        self.binding_ids: list[str] = []
        self.invitation_ids: list[str] = []
        self.retailer_ids: list[str] = []


_MODULE_STATE: dict = {"anchors": _Anchors(), "entry_overrides": None, "active": False}

_FK_ORDER_TABLES = (
    ("retailer_credential_setup_tokens", "setup_token_ids"),
    ("retailer_password_reset_tokens", "reset_token_ids"),
    ("wholesaler_retailer_bindings", "binding_ids"),
    ("invitations", "invitation_ids"),
    ("retailers", "retailer_ids"),
    ("wholesalers", "wholesaler_ids"),
)


# ---------------------------------------------------------------------------
# Fresh connections (production public-schema semantics)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _fresh_session():
    """A FRESH engine/connection mirroring the production public-schema
    dependency semantics (database.session.get_db sets
    session.info["tenant_schema"] = "public")."""
    import os

    url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            session.info["tenant_schema"] = "public"
            yield session
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Anchor-based re-discovery (hydration)
# ---------------------------------------------------------------------------

async def _hydrate(anchors: _Anchors) -> dict[str, list[str]]:
    """Re-discover every id from the STABLE ANCHORS on a fresh connection.

    This is authoritative: even if the test body failed after committing an
    object but before registering its id, hydration finds it here. All
    predicates are exact (email/phone/code/id); no LIKE or wildcards.
    """
    ids: dict[str, list[str]] = {attr: [] for _, attr in _FK_ORDER_TABLES}
    async with _fresh_session() as db:
        retailer_ids: list[str] = []
        for email in anchors.emails:
            row = (
                await db.execute(
                    text("SELECT id FROM public.retailers WHERE email = :exact"),
                    {"exact": email},
                )
            ).scalar()
            if row:
                retailer_ids.append(str(row))
        for phone in anchors.phones:
            row = (
                await db.execute(
                    text("SELECT id FROM public.retailers WHERE phone = :exact"),
                    {"exact": phone},
                )
            ).scalar()
            if row and str(row) not in retailer_ids:
                retailer_ids.append(str(row))
        ids["retailer_ids"] = retailer_ids

        binding_ids: list[str] = []
        for ws in anchors.wholesaler_ids:
            rows = (
                await db.execute(
                    text(
                        "SELECT id FROM public.wholesaler_retailer_bindings "
                        "WHERE wholesaler_id = :w"
                    ),
                    {"w": ws},
                )
            ).fetchall()
            binding_ids.extend(str(r[0]) for r in rows)
        for rid in retailer_ids:
            rows = (
                await db.execute(
                    text(
                        "SELECT id FROM public.wholesaler_retailer_bindings "
                        "WHERE retailer_id = :r"
                    ),
                    {"r": rid},
                )
            ).fetchall()
            binding_ids.extend(str(r[0]) for r in rows)
        ids["binding_ids"] = sorted(set(binding_ids))

        invitation_ids: list[str] = []
        for code in anchors.invitation_codes:
            row = (
                await db.execute(
                    text("SELECT id FROM public.invitations WHERE code = :exact"),
                    {"exact": code},
                )
            ).scalar()
            if row:
                invitation_ids.append(str(row))
        for ws in anchors.wholesaler_ids:
            rows = (
                await db.execute(
                    text(
                        "SELECT id FROM public.invitations WHERE wholesaler_id = :w"
                    ),
                    {"w": ws},
                )
            ).fetchall()
            invitation_ids.extend(str(r[0]) for r in rows)
        ids["invitation_ids"] = sorted(set(invitation_ids))

        for rid in retailer_ids:
            for table, attr in (
                ("retailer_credential_setup_tokens", "setup_token_ids"),
                ("retailer_password_reset_tokens", "reset_token_ids"),
            ):
                rows = (
                    await db.execute(
                        text(f"SELECT id FROM public.{table} WHERE retailer_id = :r"),
                        {"r": rid},
                    )
                ).fetchall()
                ids[attr].extend(str(r[0]) for r in rows)
        ids["setup_token_ids"] = sorted(set(ids["setup_token_ids"]))
        ids["reset_token_ids"] = sorted(set(ids["reset_token_ids"]))

        ws_rows = (
            await db.execute(
                text("SELECT id FROM public.wholesalers WHERE id = ANY(:ids)"),
                {"ids": anchors.wholesaler_ids},
            )
        ).fetchall()
        ids["wholesaler_ids"] = sorted(
            {str(r[0]) for r in ws_rows} | set(anchors.wholesaler_ids)
        )
    return ids


def _merge_ids(registry: _Registry, hydrated: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for _, attr in _FK_ORDER_TABLES:
        registered = set(getattr(registry, attr, []))
        merged[attr] = sorted(registered | set(hydrated.get(attr, [])))
    return merged


# ---------------------------------------------------------------------------
# Best-effort exact cleanup + zero-proof
# ---------------------------------------------------------------------------

async def _run_step(table: str, exact_id: str) -> None:
    """One exact-id DELETE step (module-level so tests can force failures)."""
    async with _fresh_session() as db:
        await db.execute(
            text(f"DELETE FROM public.{table} WHERE id = :exact"), {"exact": exact_id}
        )
        await db.commit()


async def _drop_schema_step(schema: str) -> None:
    async with _fresh_session() as db:
        await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await db.commit()


async def _cleanup_exact(anchors: _Anchors, ids: dict[str, list[str]]) -> None:
    """FK-safe, EXACT-id, best-effort cleanup with one retry per failed step.

    A failing step NEVER aborts the remaining safe steps. Failed steps are
    retried once; even healed transient failures are reported (raised as a
    single aggregated cleanup error) so they can never be silently ignored.
    """
    steps: list[tuple[str, str]] = [
        (table, exact_id)
        for table, attr in _FK_ORDER_TABLES
        for exact_id in ids.get(attr, [])
    ]
    failures: list[tuple[str, str, BaseException]] = []
    for table, exact_id in steps:
        try:
            await _run_step(table, exact_id)
        except BaseException as exc:  # noqa: BLE001 - recorded, never swallowed
            failures.append((table, exact_id, exc))
    healed: list[tuple[str, str, BaseException]] = []
    persistent: list[tuple[str, str, BaseException]] = []
    for failure in failures:
        table, exact_id, _exc = failure
        try:
            await _run_step(table, exact_id)
            healed.append(failure)
        except BaseException as exc2:  # noqa: BLE001
            persistent.append((table, exact_id, exc2))
    for schema in anchors.schemas:
        try:
            await _drop_schema_step(schema)
        except BaseException as exc:  # noqa: BLE001
            persistent.append(("schema", schema, exc))
    if healed or persistent:
        detail = "; ".join(
            [f"transient:{t}:{i}:{e!r}" for t, i, e in healed]
            + [f"persistent:{t}:{i}:{e!r}" for t, i, e in persistent]
        )
        raise RuntimeError(f"cleanup step failures: {detail}")


async def _prove_zero(
    anchors: _Anchors, ids: dict[str, list[str]] | None = None
) -> None:
    """SECOND fresh connection: every anchor, id, and schema is gone."""
    problems: list[str] = []
    async with _fresh_session() as db:
        for email in anchors.emails:
            count = (
                await db.execute(
                    text("SELECT count(*) FROM public.retailers WHERE email = :exact"),
                    {"exact": email},
                )
            ).scalar_one()
            if count:
                problems.append(f"retailer email:{email} still present")
        for phone in anchors.phones:
            count = (
                await db.execute(
                    text("SELECT count(*) FROM public.retailers WHERE phone = :exact"),
                    {"exact": phone},
                )
            ).scalar_one()
            if count:
                problems.append(f"retailer phone:{phone} still present")
        for ws in anchors.wholesaler_ids:
            count = (
                await db.execute(
                    text("SELECT count(*) FROM public.wholesalers WHERE id = :exact"),
                    {"exact": ws},
                )
            ).scalar_one()
            if count:
                problems.append(f"wholesaler:{ws} still present")
        for code in anchors.invitation_codes:
            count = (
                await db.execute(
                    text("SELECT count(*) FROM public.invitations WHERE code = :exact"),
                    {"exact": code},
                )
            ).scalar_one()
            if count:
                problems.append(f"invitation:{code} still present")
        for table, attr in _FK_ORDER_TABLES:
            for exact_id in (ids or {}).get(attr, []):
                count = (
                    await db.execute(
                        text(f"SELECT count(*) FROM public.{table} WHERE id = :exact"),
                        {"exact": exact_id},
                    )
                ).scalar_one()
                if count:
                    problems.append(f"{table}:{exact_id} still present")
        for schema in anchors.schemas:
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


# ---------------------------------------------------------------------------
# Dependency override guard (exact-value restore)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _override_guard(key, factory):
    """Install an override, restoring the EXACT previous value on exit.

    Never pops unconditionally: a pre-existing foreign override survives.
    """
    had_key = key in app.dependency_overrides
    previous = app.dependency_overrides.get(key)
    app.dependency_overrides[key] = factory()
    try:
        yield
    finally:
        if had_key:
            app.dependency_overrides[key] = previous
        else:
            app.dependency_overrides.pop(key, None)


# ---------------------------------------------------------------------------
# The residue lifecycle (directly testable async context manager)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _residue_lifecycle(registry: _Registry):
    """Body -> hydrate -> cleanup -> zero-proof, each failure preserved.

    Multiple simultaneous failures raise ExceptionGroup/BaseExceptionGroup
    containing (never covering) the original body exception. The email sink
    is cleared in finally regardless of any earlier failure.
    """
    body_error: BaseException | None = None
    follow_up_errors: list[BaseException] = []
    hydrated: dict[str, list[str]] | None = None
    try:
        yield registry
    except BaseException as exc:
        body_error = exc
    try:
        if _MODULE_STATE.get("active"):
            _MODULE_STATE["anchors"].extend_from(registry.anchors)
    except BaseException as exc:  # noqa: BLE001
        follow_up_errors.append(exc)
    try:
        hydrated = await _hydrate(registry.anchors)
    except BaseException as exc:  # noqa: BLE001
        follow_up_errors.append(exc)
    merged = _merge_ids(registry, hydrated or {})
    try:
        await _cleanup_exact(registry.anchors, merged)
    except BaseException as exc:  # noqa: BLE001
        follow_up_errors.append(exc)
    try:
        await _prove_zero(registry.anchors, merged)
    except BaseException as exc:  # noqa: BLE001
        follow_up_errors.append(exc)
    try:
        clear_dev_email_deliveries()
    except BaseException as exc:  # noqa: BLE001
        follow_up_errors.append(exc)
    all_errors = ([body_error] if body_error is not None else []) + follow_up_errors
    if not all_errors:
        return
    if len(all_errors) == 1 and body_error is not None:
        raise body_error
    if all(isinstance(e, Exception) for e in all_errors):
        raise ExceptionGroup("h2c residue lifecycle failures", all_errors)
    raise BaseExceptionGroup("h2c residue lifecycle failures", all_errors)


# ---------------------------------------------------------------------------
# Module lifecycle + per-test fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
async def _module_lifecycle():
    """Fail closed on a dirty sink; snapshot overrides; init module anchors."""
    if get_dev_retailer_email_deliveries():
        pytest.fail("fail closed: dev retailer email sink is not empty at module entry")
    _MODULE_STATE["entry_overrides"] = dict(app.dependency_overrides)
    _MODULE_STATE["anchors"] = _Anchors()
    _MODULE_STATE["active"] = True
    try:
        yield
    finally:
        # Module end: anchors cleared so repeated runs inherit nothing.
        _MODULE_STATE["active"] = False
        _MODULE_STATE["anchors"] = _Anchors()
        _MODULE_STATE["entry_overrides"] = None


@pytest.fixture
async def h2c_registry():
    registry = _Registry()
    async with _residue_lifecycle(registry):
        yield registry


# ---------------------------------------------------------------------------
# Provisioning through the FORMAL retailer lifecycle (anchors first)
# ---------------------------------------------------------------------------

def _plan_identity(registry: _Registry) -> tuple[str, str]:
    """Choose email/phone and register the anchors BEFORE any side effect."""
    email = f"h2c-{uuid.uuid4().hex[:8]}@example.com"
    phone = f"+1555{uuid.uuid4().hex[:5]}"
    registry.anchors.emails.append(email)
    registry.anchors.phones.append(phone)
    return email, phone


async def _register_ws_and_schema(
    db: AsyncSession, registry: _Registry, code: str
) -> tuple[str, str]:
    ws_id, schema = await _make_tenant(db, code=code)
    registry.anchors.wholesaler_ids.append(str(ws_id))
    registry.anchors.schemas.append(schema)
    return str(ws_id), schema


async def _register_invitation(
    db: AsyncSession, registry: _Registry, ws_id: str, phone: str
) -> str:
    code = await _create_invitation(db, wholesaler_id=ws_id, phone=phone)
    registry.anchors.invitation_codes.append(code)
    inv_id = (
        await db.execute(
            text("SELECT id FROM public.invitations WHERE code = :exact"),
            {"exact": code},
        )
    ).scalar_one()
    registry.invitation_ids.append(str(inv_id))
    return code


async def _register_retailer(
    db: AsyncSession, registry: _Registry, ws_id: str, code: str, phone: str, email: str
) -> str:
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


async def _sweep_tokens(registry: _Registry, retailer_id: str) -> None:
    """Register token rows for one EXACT retailer id (optimization only;
    hydration re-derives authoritatively at teardown)."""
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
            known = set(getattr(registry, attr))
            for r in rows:
                if str(r[0]) not in known:
                    getattr(registry, attr).append(str(r[0]))


async def _established_retailer(registry: _Registry, *, code: str) -> tuple[str, str, str]:
    """Official lifecycle: tenant -> invitation -> register -> setup password."""
    email, phone = _plan_identity(registry)
    async with _fresh_session() as db:
        ws_id, _schema = await _register_ws_and_schema(db, registry, code)
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
# Unit contract: build_retailer_reset_link shapes (legacy + H2-C)
# ---------------------------------------------------------------------------

async def test_reset_link_legacy_shape_unchanged_without_code():
    token = "raw-reset-token-1"
    link = build_retailer_reset_link(token)
    assert link == "/retailer/reset-password#resetToken=raw-reset-token-1"
    assert "?" not in link
    assert "w=" not in link


async def test_reset_link_with_canonical_code_keeps_fragment_only():
    link = build_retailer_reset_link("tok 1", wholesaler_code="H2CAB01")
    assert link.startswith("/retailer/reset-password#resetToken=")
    assert link.endswith("&w=H2CAB01")
    assert "?" not in link
    head, fragment = link.split("#", 1)
    assert head == "/retailer/reset-password"
    assert fragment.startswith("resetToken=tok%201&")


# ---------------------------------------------------------------------------
# Integration: email carries the DB-canonical code (HC17)
# ---------------------------------------------------------------------------

async def test_forgot_password_email_carries_db_canonical_uppercase_code(h2c_registry):
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


async def test_forgot_password_email_w_matches_case_insensitive_lookup(h2c_registry):
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


def _session_override_factory():
    async def _override():
        async with _fresh_session() as session:
            await session.execute(text("SET search_path TO public"))
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


@asynccontextmanager
async def _real_client():
    """Real ASGI client under the exact-value override guard."""
    async with _override_guard(get_db_session, _session_override_factory):
        yield AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _code_for_wholesaler(ws_id: str) -> str:
    async with _fresh_session() as db:
        return (
            await db.execute(
                text("SELECT code FROM public.wholesalers WHERE id = :exact"),
                {"exact": ws_id},
            )
        ).scalar_one()


async def test_hc07_hc10_canonical_neutrality_real_http(h2c_registry):
    # HC07 supply: established (verified + password) retailer, correct code.
    email7, _ws7, canonical7 = await _established_retailer(
        h2c_registry, code=f"S1T{uuid.uuid4().hex[:5].upper()}"
    )
    # HC10 supply: registered but the setup token is NOT consumed, so the
    # email stays unverified for this retailer+supplier pair.
    email10, phone10 = _plan_identity(h2c_registry)
    async with _fresh_session() as db:
        ws10, _schema10 = await _register_ws_and_schema(
            db, h2c_registry, f"S1T{uuid.uuid4().hex[:5].upper()}"
        )
        invitation10 = await _register_invitation(db, h2c_registry, ws10, phone10)
        await _register_retailer(db, h2c_registry, ws10, invitation10, phone10, email10)
        canonical10 = await _code_for_wholesaler(ws10)

    clear_dev_email_deliveries()
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

    bodies = {}
    for label, response in (("HC07", r7), ("HC08", r8), ("HC09", r9), ("HC10", r10)):
        assert response.status_code == 200, (label, response.status_code, response.text)
        body = response.json()
        _assert_canonical_neutral_body(body)
        bodies[label] = body

    s7, s8, s9, s10 = (_sentinel(bodies[k]) for k in ("HC07", "HC08", "HC09", "HC10"))
    assert s7 == s8 == s9 == s10

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
    deliveries = get_dev_retailer_email_deliveries()
    assert len([d for d in deliveries if d.to_email == email7.lower()]) == 1
    assert len([d for d in deliveries if d.to_email == email10.lower()]) == 0


# ---------------------------------------------------------------------------
# Failure-window truth tests (FW1-FW5)
# ---------------------------------------------------------------------------

def _sentinel_preserved(caught: BaseException | None, sentinel: BaseException) -> bool:
    if caught is None:
        return False
    if caught is sentinel or isinstance(caught, type(sentinel)):
        return caught is sentinel
    if isinstance(caught, BaseExceptionGroup):
        return any(e is sentinel for e in caught.exceptions)
    return False


async def _assert_window_outcomes(anchors: _Anchors) -> None:
    """Common post-window proof: DB zero, schema zero, sink zero."""
    await _prove_zero(anchors)
    assert get_dev_retailer_email_deliveries() == [], "email sink must be zero"


async def test_fw1_registration_committed_sentinel_before_sweep():
    """Cut: registration committed, id registration/sweep never ran."""
    registry = _Registry()
    email, phone = _plan_identity(registry)
    sentinel = _SentinelError("FW1")
    caught: BaseException | None = None
    try:
        async with _residue_lifecycle(registry):
            async with _fresh_session() as db:
                ws_id, _schema = await _register_ws_and_schema(
                    db, registry, f"S1T{uuid.uuid4().hex[:5].upper()}"
                )
                invitation = await _register_invitation(db, registry, ws_id, phone)
                svc = RetailerProvisioningService(db)
                await svc.register_with_invitation(
                    invitation_code=invitation, phone=phone, email=email
                )
                await db.commit()
                # CUT: retailer/binding/setup-token ids never registered.
            raise sentinel
    except BaseException as exc:
        caught = exc
    assert _sentinel_preserved(caught, sentinel), f"sentinel not preserved: {caught!r}"
    await _assert_window_outcomes(registry.anchors)


async def test_fw2_token_and_email_created_ids_unregistered():
    """Cut: forgot-password created a token + email, ids never registered."""
    registry = _Registry()
    sentinel = _SentinelError("FW2")
    caught: BaseException | None = None
    try:
        async with _residue_lifecycle(registry):
            email, ws_id, canonical = await _established_retailer(
                registry, code=f"S1T{uuid.uuid4().hex[:5].upper()}"
            )
            async with _fresh_session() as db:
                svc = RetailerProvisioningService(db)
                issued = await svc.request_password_reset(
                    email=email, wholesaler_code=canonical
                )
                await db.commit()
                assert issued is True
            # CUT: the new reset token id was never appended; the email sits
            # in the sink.
            raise sentinel
    except BaseException as exc:
        caught = exc
    assert _sentinel_preserved(caught, sentinel), f"sentinel not preserved: {caught!r}"
    await _assert_window_outcomes(registry.anchors)


async def test_fw3_canonical_assertion_fails_after_side_effects():
    """Cut: HTTP side effects done, canonical assertion fails pre-registration."""
    registry = _Registry()
    email7, _ws7, canonical7 = await _established_retailer(
        registry, code=f"S1T{uuid.uuid4().hex[:5].upper()}"
    )
    caught: BaseException | None = None
    try:
        async with _residue_lifecycle(registry):
            clear_dev_email_deliveries()
            async with _real_client() as client:
                r7 = await client.post(
                    FORGOT_URL, json={"email": email7, "wholesaler_code": canonical7}
                )
                # Canonical assertion failure AFTER the side effect produced
                # a token + sink delivery, BEFORE any id registration.
                assert r7.status_code == 542, "simulated canonical assertion failure"
    except AssertionError:
        caught = AssertionError()
    except BaseException as exc:  # noqa: BLE001
        if any(
            isinstance(e, AssertionError) for e in getattr(exc, "exceptions", ())
        ):
            caught = exc
        else:
            caught = exc
    assert caught is not None, "canonical assertion failure was swallowed"
    await _assert_window_outcomes(registry.anchors)


async def test_fw4_override_installed_request_fails():
    """Cut: dependency override installed, request path fails; a FOREIGN
    override must survive with its exact value restored."""
    registry = _Registry()
    email, phone = _plan_identity(registry)
    sentinel = _SentinelError("FW4")

    async def _foreign_override():
        yield None  # pragma: no cover - placeholder, never executed

    app.dependency_overrides[get_db_session] = _foreign_override
    caught: BaseException | None = None
    try:
        async with _residue_lifecycle(registry):
            async with _fresh_session() as db:
                ws_id, _schema = await _register_ws_and_schema(
                    db, registry, f"S1T{uuid.uuid4().hex[:5].upper()}"
                )
                invitation = await _register_invitation(db, registry, ws_id, phone)
                svc = RetailerProvisioningService(db)
                await svc.register_with_invitation(
                    invitation_code=invitation, phone=phone, email=email
                )
                await db.commit()
            async with _real_client():
                # Simulated mid-request failure while our override is active.
                raise sentinel
    except BaseException as exc:
        caught = exc
    finally:
        assert get_db_session in app.dependency_overrides, "foreign override lost"
        assert (
            app.dependency_overrides[get_db_session] is _foreign_override
        ), "foreign override not restored to its exact value"
        app.dependency_overrides.pop(get_db_session, None)
    assert _sentinel_preserved(caught, sentinel), f"sentinel not preserved: {caught!r}"
    await _assert_window_outcomes(registry.anchors)


async def test_fw5_cleanup_failure_with_body_failure(monkeypatch):
    """Cleanup step fails (transiently, healed by retry) while the body also
    failed: BOTH must be preserved in one ExceptionGroup, and the DB must
    still reach zero."""
    import tests.test_dc12r1_j1_h2c_retailer_recovery_discovery as own_module

    registry = _Registry()
    email, phone = _plan_identity(registry)
    sentinel = _SentinelError("FW5")
    real_run_step = _run_step
    calls = {"n": 0}

    async def _flaky_run_step(table: str, exact_id: str) -> None:
        if table == "wholesalers":
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("FW5 injected transient cleanup failure")
        await real_run_step(table, exact_id)

    monkeypatch.setattr(own_module, "_run_step", _flaky_run_step)
    caught: BaseException | None = None
    try:
        async with _residue_lifecycle(registry):
            async with _fresh_session() as db:
                ws_id, _schema = await _register_ws_and_schema(
                    db, registry, f"S1T{uuid.uuid4().hex[:5].upper()}"
                )
                invitation = await _register_invitation(db, registry, ws_id, phone)
                svc = RetailerProvisioningService(db)
                await svc.register_with_invitation(
                    invitation_code=invitation, phone=phone, email=email
                )
                await db.commit()
            raise sentinel
    except BaseExceptionGroup as group:
        caught = group
    except BaseException as exc:  # noqa: BLE001
        caught = exc
    monkeypatch.undo()
    assert isinstance(caught, BaseExceptionGroup), (
        f"dual failure must surface as ExceptionGroup, got {caught!r}"
    )
    flat = list(caught.exceptions)
    assert any(e is sentinel for e in flat), f"body sentinel not preserved: {flat!r}"
    assert any(
        isinstance(e, RuntimeError) and "FW5 injected" in str(e) for e in flat
    ), f"cleanup failure not preserved: {flat!r}"
    await _assert_window_outcomes(registry.anchors)


# ---------------------------------------------------------------------------
# Module final proof (must remain the LAST test)
# ---------------------------------------------------------------------------

async def test_module_global_state_zero():
    """Full-axis zero: DB anchors/ids, schemas, email sink, dependency
    overrides (per-key identity vs module entry), and idle connections."""
    anchors = _MODULE_STATE["anchors"]
    await _prove_zero(anchors)
    assert get_dev_retailer_email_deliveries() == [], "email sink must be zero"
    entry = _MODULE_STATE.get("entry_overrides")
    assert entry is not None, "module lifecycle fixture not active"
    current = dict(app.dependency_overrides)
    assert set(current.keys()) == set(entry.keys()), (
        f"override key sets differ: {sorted(current)} vs {sorted(entry)}"
    )
    for key, value in entry.items():
        assert current[key] is value, "override value identity drifted"
    async with _fresh_session() as db:
        lingering = (
            await db.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                )
            )
        ).scalar_one()
    assert lingering == 0, f"{lingering} lingering DB connections"
