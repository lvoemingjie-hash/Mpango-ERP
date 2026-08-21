"""U6-C signup and email verification token skeleton tests."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from api.v1 import auth as auth_router
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import EmailVerificationToken, OnboardingStatusToken, TenantRegistration
from models.wholesaler import Wholesaler
from schemas.auth_signup import SignupRequest
from services.email_delivery import (
    EmailDeliveryNotConfiguredError,
    clear_dev_email_deliveries,
    get_dev_email_deliveries,
)
from core.config import get_settings
from services.onboarding_service import (
    _hash_optional_value,
    _request_fingerprint_hash_with_password,
    create_signup_registration,
)


pytestmark = pytest.mark.asyncio

VALID_PASSWORD = "ValidSignupCred123!"  # pragma: allowlist secret
LIVE_STATUSES = (
    "pending_email_verification",
    "email_verified",
    "provisioning",
    "active",
    "failed",
)


@pytest.fixture(autouse=True)
async def _u6c_public_schema():
    await _ensure_onboarding_tables()
    await _clear_u6c_rows()
    clear_dev_email_deliveries()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_u6c_rows()
        clear_dev_email_deliveries()


async def _ensure_onboarding_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(TenantRegistration.__table__.create, checkfirst=True)
        await connection.run_sync(EmailVerificationToken.__table__.create, checkfirst=True)
        await connection.run_sync(OnboardingStatusToken.__table__.create, checkfirst=True)


async def _clear_u6c_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "DELETE FROM public.onboarding_status_tokens "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6c_%@example.com')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM public.email_verification_tokens "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6c_%@example.com')"
            )
        )
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6c_%@example.com'")
        )
        await session.commit()


async def _client() -> AsyncClient:
    async def _override_public_db():
        async with AsyncSessionLocal() as session:
            await session.execute(text("SET search_path TO public"))
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_public_db
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://testserver")


def _signup_payload(
    email: str,
    *,
    company_name: str | None = None,
    legacy_password: bool = False,
) -> dict[str, str]:
    """Build a signup payload.

    Default (R1-R1 contract): passwordless, matching new clients.
    ``legacy_password=True`` appends the deprecated password field the way
    pre-R1-R1 clients still send it.
    """
    unique = uuid.uuid4().hex[:8]
    payload: dict[str, str] = {
        "companyName": company_name or f"U6C Company {unique}",
        "country": "KE",
        "email": email,
        "phone": "+254700000000",
        "businessType": "wholesale",
    }
    if legacy_password:
        payload["password"] = VALID_PASSWORD
    return payload


async def _registration_rows(email: str):
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, owner_email, password_hash, status, request_fingerprint_hash, "
                    "idempotency_key_hash FROM public.tenant_registrations "
                    "WHERE owner_email = :email ORDER BY created_at"
                ),
                {"email": email},
            )
        ).mappings().all()
        return rows


async def _active_verification_tokens(registration_id: uuid.UUID):
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT * FROM public.email_verification_tokens "
                    "WHERE registration_id = :registration_id "
                    "AND used_at IS NULL AND revoked_at IS NULL"
                ),
                {"registration_id": registration_id},
            )
        ).mappings().all()
        return rows


async def _verification_token_rows_for_email(email: str):
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT * FROM public.email_verification_tokens "
                    "WHERE sent_to_email = :email"
                ),
                {"email": email},
            )
        ).mappings().all()
        return rows


async def _tenant_schema_names() -> set[str]:
    async with AsyncSessionLocal() as session:
        return set(
            (
                await session.execute(
                    text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 't_%'")
                )
            ).scalars()
        )


async def _rbac_table_inventory() -> set[tuple[str, str]]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT n.nspname, c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relkind = 'r' "
                    "AND c.relname IN ('users', 'roles', 'permissions', 'user_roles', 'role_permissions')"
                )
            )
        ).all()
        return {(schema, table) for schema, table in rows}


async def test_signup_creates_pending_registration_and_one_active_verification_token():
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=_signup_payload(email))

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["registrationId"] is None
    assert body["data"]["status"] == "pending_email_verification"
    assert body["data"]["emailVerificationRequired"] is True
    assert "token" not in str(body).lower()

    rows = await _registration_rows(email)
    assert len(rows) == 1
    registration = rows[0]
    assert registration["owner_email"] == email
    assert registration["status"] == "pending_email_verification"
    # F-A: the signup password no longer exists; nothing may be stored.
    assert registration["password_hash"] is None

    tokens = await _active_verification_tokens(registration["id"])
    assert len(tokens) == 1


async def test_passwordless_signup_is_the_new_client_contract_and_stores_no_hash():
    """F-A: new clients omit password entirely; password_hash must be NULL."""
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    assert "password" not in _signup_payload(email)

    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=_signup_payload(email))

    assert response.status_code == 202, response.text
    registration = (await _registration_rows(email))[0]
    assert registration["password_hash"] is None


async def test_legacy_password_is_accepted_but_never_stored():
    """F-A compatibility: a legacy client may still send a (valid) password;
    it is discarded, never written to password_hash, never a credential."""
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    async with await _client() as client:
        response = await client.post(
            "/api/v1/auth/signup", json=_signup_payload(email, legacy_password=True)
        )

    assert response.status_code == 202, response.text
    registration = (await _registration_rows(email))[0]
    assert registration["password_hash"] is None


async def test_legacy_replay_with_different_password_same_key_is_not_a_conflict():
    """F-A fingerprint truth: password is excluded from the canonical
    fingerprint, so the same idempotency key replayed by a legacy client with
    a different (discarded) password must replay, not 409."""
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    first_payload = _signup_payload(email, legacy_password=True)
    second_payload = dict(first_payload)
    second_payload["password"] = "AnotherLegacyCred456!"  # pragma: allowlist secret
    headers = {"Idempotency-Key": f"u6c-{uuid.uuid4().hex}"}

    async with await _client() as client:
        first = await client.post("/api/v1/auth/signup", json=first_payload, headers=headers)
        second = await client.post("/api/v1/auth/signup", json=second_payload, headers=headers)

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert second.json()["data"] == first.json()["data"]
    assert len(await _registration_rows(email)) == 1


async def test_fingerprint_deterministic_for_passwordless_and_legacy_payloads():
    """F-A: passwordless and legacy-password variants of the same logical
    signup under the SAME idempotency key must replay (identical fingerprint
    because password is excluded), not raise IDEMPOTENCY_CONFLICT."""
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    company = "U6C Fingerprint Co"
    passwordless = _signup_payload(email, company_name=company)
    legacy = _signup_payload(email, company_name=company, legacy_password=True)
    headers = {"Idempotency-Key": f"u6c-{uuid.uuid4().hex}"}

    async with await _client() as client:
        first = await client.post("/api/v1/auth/signup", json=passwordless, headers=headers)
        second = await client.post("/api/v1/auth/signup", json=legacy, headers=headers)

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert second.json()["data"] == first.json()["data"]
    rows = await _registration_rows(email)
    assert len(rows) == 1
    assert rows[0]["password_hash"] is None


async def test_signup_stores_only_token_hash_and_dev_sink_captures_delivery():
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=_signup_payload(email))

    assert response.status_code == 202, response.text
    registration = (await _registration_rows(email))[0]
    tokens = await _active_verification_tokens(registration["id"])
    token_row = tokens[0]

    deliveries = get_dev_email_deliveries(email)
    assert len(deliveries) == 1
    raw_token = deliveries[0].token
    assert raw_token
    assert raw_token in deliveries[0].verification_link
    assert raw_token not in response.text
    assert raw_token not in token_row["token_hash"]
    assert "token" not in set(token_row.keys())
    assert "raw_token" not in set(token_row.keys())
    assert "token_plaintext" not in set(token_row.keys())


async def test_duplicate_same_normalized_email_returns_neutral_success_without_duplicate_live_registration():
    local = f"u6c_{uuid.uuid4().hex}"
    first_email = f"{local}@example.com"
    duplicate_email = f"{local.upper()}@example.com"

    async with await _client() as client:
        first = await client.post("/api/v1/auth/signup", json=_signup_payload(first_email))
        duplicate = await client.post("/api/v1/auth/signup", json=_signup_payload(duplicate_email))

    assert first.status_code == 202, first.text
    assert duplicate.status_code == 202, duplicate.text
    assert duplicate.json()["success"] is True
    assert first.json()["data"] == duplicate.json()["data"]
    assert first.json()["data"]["registrationId"] is None
    assert duplicate.json()["data"]["registrationId"] is None

    rows = await _registration_rows(first_email)
    live_rows = [row for row in rows if row["status"] in LIVE_STATUSES]
    assert len(live_rows) == 1
    assert len(get_dev_email_deliveries(first_email)) == 1


async def test_same_idempotency_key_and_fingerprint_is_safe():
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    payload = _signup_payload(email)
    headers = {"Idempotency-Key": f"u6c-{uuid.uuid4().hex}"}

    async with await _client() as client:
        first = await client.post("/api/v1/auth/signup", json=payload, headers=headers)
        second = await client.post("/api/v1/auth/signup", json=payload, headers=headers)

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json()["data"]["registrationId"] is None
    assert second.json()["data"] == first.json()["data"]

    rows = await _registration_rows(email)
    assert len(rows) == 1
    assert rows[0]["idempotency_key_hash"] is not None
    assert rows[0]["request_fingerprint_hash"] is not None
    assert len(await _active_verification_tokens(rows[0]["id"])) == 1
    assert len(get_dev_email_deliveries(email)) == 1


async def test_idempotent_retry_does_not_expose_changed_internal_status():
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    payload = _signup_payload(email)
    headers = {"Idempotency-Key": f"u6c-{uuid.uuid4().hex}"}

    async with await _client() as client:
        first = await client.post("/api/v1/auth/signup", json=payload, headers=headers)

    rows = await _registration_rows(email)
    assert len(rows) == 1

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "UPDATE public.tenant_registrations "
                "SET status = 'email_verified', email_verified_at = now() "
                "WHERE owner_email = :email"
            ),
            {"email": email},
        )
        await session.commit()

    async with await _client() as client:
        retry = await client.post("/api/v1/auth/signup", json=payload, headers=headers)

    assert first.status_code == 202, first.text
    assert retry.status_code == 202, retry.text
    assert first.json()["data"] == retry.json()["data"]
    assert retry.json()["data"]["status"] == "pending_email_verification"


async def test_production_signup_fails_closed_without_email_provider_and_writes_no_rows():
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    production_settings = SimpleNamespace(
        MPANGO_ENV="production",
        SECRET_KEY="Z9vLk8mN4pQ7rS2tU5wX8yB3cD6fG0hJ",  # pragma: allowlist secret
    )

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        with pytest.raises(EmailDeliveryNotConfiguredError, match="EMAIL_DELIVERY_NOT_CONFIGURED"):
            await create_signup_registration(
                db=session,
                request=SignupRequest(**_signup_payload(email)),
                settings=production_settings,
            )
        await session.rollback()

    assert await _registration_rows(email) == []
    assert await _verification_token_rows_for_email(email) == []
    assert get_dev_email_deliveries(email) == []


async def test_signup_endpoint_returns_503_when_email_delivery_is_unavailable(monkeypatch):
    email = f"u6c_{uuid.uuid4().hex}@example.com"

    async def _raise_delivery_unavailable(**_kwargs):
        raise EmailDeliveryNotConfiguredError("EMAIL_DELIVERY_NOT_CONFIGURED")

    monkeypatch.setattr(auth_router, "create_signup_registration", _raise_delivery_unavailable)

    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=_signup_payload(email))

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "EMAIL_DELIVERY_NOT_CONFIGURED"
    assert await _registration_rows(email) == []
    assert await _verification_token_rows_for_email(email) == []
    assert get_dev_email_deliveries(email) == []


async def test_invalid_email_or_password_returns_validation_error_without_db_writes():
    before = await _registration_rows("u6c_invalid@example.com")
    payload = _signup_payload("not-an-email")
    payload["password"] = "short"  # pragma: allowlist secret

    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=payload)

    assert response.status_code == 422
    after = await _registration_rows("u6c_invalid@example.com")
    assert before == after == []


async def test_legacy_fingerprint_record_replays_under_new_code_without_409():
    """R1-R1 cross-version compatibility (real DB preset).

    A registration row written by the PRE-R1-R1 code stores a fingerprint
    that includes the (now deprecated) password. A legacy client retrying
    the same idempotency key with its original payload must still replay
    under the new code instead of receiving a spurious 409.
    """
    settings = get_settings()
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    key = f"u6c-legacy-{uuid.uuid4().hex}"
    payload = _signup_payload(email, legacy_password=True)

    # Preset the database exactly as the old code would have written it:
    # OLD-format fingerprint (password included) + key hash, NULL password.
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "INSERT INTO public.tenant_registrations "
                "(company_name, country, business_type, phone, owner_email, "
                " password_hash, status, idempotency_key_hash, "
                " request_fingerprint_hash, expires_at) "
                "VALUES (:c, :co, :b, :p, :e, NULL, 'pending_email_verification', "
                " :ikh, :fph, now() + interval '24 hours')"
            ),
            {
                "c": payload["companyName"],
                "co": payload["country"],
                "b": payload["businessType"],
                "p": payload["phone"],
                "e": email,
                "ikh": _hash_optional_value(key, settings),
                "fph": _legacy_fingerprint(payload, email),
            },
        )
        await session.commit()

    async with await _client() as client:
        replay = await client.post(
            "/api/v1/auth/signup", json=payload, headers={"Idempotency-Key": key}
        )

    assert replay.status_code == 202, replay.text
    rows = await _registration_rows(email)
    assert len(rows) == 1  # replayed the preset row; no new registration
    assert rows[0]["password_hash"] is None


async def test_legacy_fingerprint_record_still_409_for_different_payload():
    """A different payload under the same key must still conflict, even in
    the compat path: the legacy fingerprint must actually match."""
    settings = get_settings()
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    key = f"u6c-legacy-{uuid.uuid4().hex}"
    preset = _signup_payload(email, legacy_password=True)
    different = _signup_payload(email, company_name="Different Co Ltd", legacy_password=True)

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "INSERT INTO public.tenant_registrations "
                "(company_name, country, business_type, phone, owner_email, "
                " password_hash, status, idempotency_key_hash, "
                " request_fingerprint_hash, expires_at) "
                "VALUES (:c, :co, :b, :p, :e, NULL, 'pending_email_verification', "
                " :ikh, :fph, now() + interval '24 hours')"
            ),
            {
                "c": preset["companyName"],
                "co": preset["country"],
                "b": preset["businessType"],
                "p": preset["phone"],
                "e": email,
                "ikh": _hash_optional_value(key, settings),
                "fph": _legacy_fingerprint(preset, email),
            },
        )
        await session.commit()

    async with await _client() as client:
        conflict = await client.post(
            "/api/v1/auth/signup", json=different, headers={"Idempotency-Key": key}
        )

    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"


def _legacy_fingerprint(payload: dict, email: str) -> str:
    """The exact pre-R1-R1 canonical fingerprint algorithm (password in)."""
    from schemas.auth_signup import SignupRequest

    request = SignupRequest(**payload)
    return _request_fingerprint_hash_with_password(request, email, get_settings())


async def test_signup_does_not_create_tenant_schema_users_roles_or_rbac():
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    schemas_before = await _tenant_schema_names()
    rbac_before = await _rbac_table_inventory()

    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=_signup_payload(email))

    assert response.status_code == 202, response.text
    assert await _tenant_schema_names() == schemas_before
    assert await _rbac_table_inventory() == rbac_before


async def test_signup_response_has_no_raw_token_and_no_query_string_status_contract():
    email = f"u6c_{uuid.uuid4().hex}@example.com"
    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=_signup_payload(email))

    assert response.status_code == 202, response.text
    body = response.json()
    assert "token" not in body["data"]
    assert "statusToken" not in body["data"]
    assert "query" not in str(body).lower()

    paths = {route.path for route in app.routes}
    assert "/api/v1/onboarding/status" not in paths
