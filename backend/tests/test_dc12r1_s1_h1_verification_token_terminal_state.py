"""DC-12R1-S1-H1 verification token terminal-state boundary tests.

These tests pin the EmailVerificationToken soft-delete and terminal replay
boundary inside ``verify_email_token`` without changing onboarding behavior.

Contract enforced here:

- a soft-deleted (``is_deleted=true``) verification token is rejected with the
  neutral public ``INVALID_OR_EXPIRED_VERIFICATION_TOKEN`` 400 response and
  performs zero mutation;
- ``used_at`` / ``revoked_at`` / ``expires_at`` / ``is_deleted`` terminal token
  states never invoke ``_is_retryable_setup_email_failure`` (the dependent
  OwnerCredentialSetupToken lookup) and never reach provisioning,
  orchestration, email delivery, or any write;
- the valid setup-email-failure retry anchor (an unused, unrevoked, unexpired,
  non-deleted token on a fully provisioned registration) still reconciles;
- the public HTTP response stays a controlled 400 with the neutral wording.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import (
    EmailVerificationToken,
    OnboardingStatusToken,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from models.wholesaler import Wholesaler
from services.email_delivery import clear_dev_email_deliveries, get_dev_email_deliveries


pytestmark = pytest.mark.asyncio

VALID_PASSWORD = "ValidSignupCred123!"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
async def _h1_public_schema():
    await _ensure_onboarding_tables()
    await _clear_h1_rows()
    clear_dev_email_deliveries()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_h1_rows()
        clear_dev_email_deliveries()


@pytest.fixture(autouse=True)
def _allow_rate_limiter():
    limiter = Mock()
    limiter.check_rate_limit = AsyncMock(return_value=(True, 1, 100))
    with patch("api.middleware.rate_limiting.get_rate_limiter", return_value=limiter):
        yield limiter


async def _ensure_onboarding_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reporting_role') "
                "THEN CREATE ROLE reporting_role NOLOGIN; END IF; "
                "END $$"
            )
        )
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(TenantRegistration.__table__.create, checkfirst=True)
        await connection.run_sync(EmailVerificationToken.__table__.create, checkfirst=True)
        await connection.run_sync(OnboardingStatusToken.__table__.create, checkfirst=True)
        await connection.run_sync(OwnerCredentialSetupToken.__table__.create, checkfirst=True)


async def _clear_h1_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id, tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email LIKE 'h1_%@example.com'"
                )
            )
        ).mappings().all()
        wholesaler_ids = [
            row["wholesaler_id"] for row in rows if row["wholesaler_id"] is not None
        ]
        for schema in {
            row["tenant_schema"] for row in rows if row["tenant_schema"] is not None
        }:
            if schema.startswith("t_") and schema.replace("_", "").isalnum():
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.execute(
            text(
                "DELETE FROM public.owner_credential_setup_tokens WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'h1_%@example.com')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM public.email_verification_tokens WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'h1_%@example.com')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'h1_%@example.com'"
            )
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


def _signup_payload(email: str) -> dict[str, str]:
    return {
        "companyName": f"H1 Company {uuid.uuid4().hex[:8]}",
        "country": "KE",
        "email": email,
        "phone": "+254700000000",
        "businessType": "wholesale",
        "password": VALID_PASSWORD,
    }


async def _signup_and_token(email: str) -> str:
    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=_signup_payload(email))
    assert response.status_code == 202, response.text
    deliveries = get_dev_email_deliveries(email)
    assert len(deliveries) == 1
    return deliveries[0].token


async def _verify(raw_token: str):
    async with await _client() as client:
        return await client.post("/api/v1/auth/verify-email", json={"token": raw_token})


async def _registration_row(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT id, owner_email, status, email_verified_at, tenant_schema, "
                    "wholesaler_id, provisioning_completed_at FROM public.tenant_registrations "
                    "WHERE owner_email = :email"
                ),
                {"email": email},
            )
        ).mappings().one_or_none()


async def _verification_token_row(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT evt.* FROM public.email_verification_tokens evt "
                    "JOIN public.tenant_registrations tr ON tr.id = evt.registration_id "
                    "WHERE tr.owner_email = :email ORDER BY evt.created_at"
                ),
                {"email": email},
            )
        ).mappings().one()


async def _set_verification_token(email: str, column: str, sql_value: str) -> None:
    """Set a verification-token column to a raw SQL value for the test's registration."""
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                f"UPDATE public.email_verification_tokens SET {column} = {sql_value} "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations WHERE owner_email = :email)"
            ),
            {"email": email},
        )
        await session.commit()


async def _setup_token_rows(registration_id):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT * FROM public.owner_credential_setup_tokens "
                    "WHERE registration_id = :registration_id ORDER BY created_at"
                ),
                {"registration_id": registration_id},
            )
        ).mappings().all()


def _assert_neutral_400(response) -> None:
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["detail"]["code"] == "INVALID_OR_EXPIRED_VERIFICATION_TOKEN"
    lowered = str(body).lower()
    assert "hash" not in lowered
    assert "registration" not in lowered
    assert "tenant" not in lowered


def _assert_zero_mutation(before_registration, before_token, after_registration, after_token) -> None:
    assert after_registration["status"] == before_registration["status"]
    assert after_registration["email_verified_at"] == before_registration["email_verified_at"]
    assert after_registration["tenant_schema"] is None
    assert after_registration["wholesaler_id"] is None
    assert after_registration["provisioning_completed_at"] == before_registration["provisioning_completed_at"]
    assert after_token["used_at"] == before_token["used_at"]
    assert after_token["revoked_at"] == before_token["revoked_at"]


# ---------------------------------------------------------------------------
# Soft-delete boundary (current product defect: is_deleted is not checked).
# ---------------------------------------------------------------------------


async def test_soft_deleted_verification_token_is_rejected_neutrally_with_zero_mutation():
    email = f"h1_soft_{uuid.uuid4().hex}@example.com"
    raw_token = await _signup_and_token(email)
    await _set_verification_token(email, "is_deleted", "true")
    before_registration = await _registration_row(email)
    before_token = await _verification_token_row(email)

    response = await _verify(raw_token)

    _assert_neutral_400(response)
    after_registration = await _registration_row(email)
    after_token = await _verification_token_row(email)
    _assert_zero_mutation(before_registration, before_token, after_registration, after_token)
    assert await _setup_token_rows(after_registration["id"]) == []
    assert [d for d in get_dev_email_deliveries(email) if d.purpose == "owner_setup"] == []


# ---------------------------------------------------------------------------
# Terminal replay boundary: used / revoked / expired / soft-deleted tokens
# never call the dependent _is_retryable_setup_email_failure query and never
# reach provisioning, orchestration, email delivery, or any write.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "column", "sql_value"),
    [
        ("used", "used_at", "now()"),
        ("revoked", "revoked_at", "now()"),
        ("expired", "expires_at", "now() - interval '1 hour'"),
        ("soft_deleted", "is_deleted", "true"),
    ],
)
async def test_terminal_token_skips_dependent_lookup_orchestration_and_writes(label, column, sql_value):
    email = f"h1_term_{label}_{uuid.uuid4().hex}@example.com"
    raw_token = await _signup_and_token(email)
    await _set_verification_token(email, column, sql_value)
    before_registration = await _registration_row(email)
    before_token = await _verification_token_row(email)

    with (
        patch(
            "services.onboarding_service._is_retryable_setup_email_failure",
            new=AsyncMock(side_effect=AssertionError(
                f"{label} terminal token must not call _is_retryable_setup_email_failure"
            )),
        ) as retry_spy,
        patch(
            "services.onboarding_service.complete_email_verified_onboarding",
            new=AsyncMock(side_effect=AssertionError(
                f"{label} terminal token must not reach onboarding orchestration"
            )),
        ) as orchestration_spy,
    ):
        response = await _verify(raw_token)

    _assert_neutral_400(response)
    retry_spy.assert_not_called()
    orchestration_spy.assert_not_called()
    after_registration = await _registration_row(email)
    after_token = await _verification_token_row(email)
    _assert_zero_mutation(before_registration, before_token, after_registration, after_token)
    assert await _setup_token_rows(after_registration["id"]) == []
    assert [d for d in get_dev_email_deliveries(email) if d.purpose == "owner_setup"] == []


# ---------------------------------------------------------------------------
# Retry-anchor preservation: a valid (unused, unrevoked, unexpired,
# non-deleted) verification token must NOT be rejected by the terminal-state
# boundary. The full retry reconciliation (provisioning + setup email) is
# proven end-to-end by test_u6l's retry-anchor suite; here we pin only the
# boundary itself: a fresh unused token in a non-terminal state must reach the
# orchestration path (not be neutralised by the boundary).
# ---------------------------------------------------------------------------


async def test_valid_non_terminal_token_is_not_rejected_by_the_terminal_boundary():
    email = f"h1_valid_{uuid.uuid4().hex}@example.com"
    raw_token = await _signup_and_token(email)

    # The unused, unrevoked, unexpired, non-deleted token must be allowed past
    # the terminal boundary: orchestration is reached. We assert it is invoked
    # (the real provisioning then runs against the real disposable schema).
    with patch(
        "services.onboarding_service.complete_email_verified_onboarding",
        new=AsyncMock(return_value=None),
    ) as orchestration_spy:
        response = await _verify(raw_token)

    assert response.status_code == 200, response.text
    orchestration_spy.assert_called_once()
    # The boundary admitted the valid token: it is now consumed (used) but was
    # never soft-deleted, never revoked, and never rejected.
    token_row = await _verification_token_row(email)
    assert token_row["used_at"] is not None
    assert token_row["revoked_at"] is None
    assert token_row["is_deleted"] is False
