"""DC-11P2 platform operator credential lifecycle tests.

Scope guard: these tests cover service/bootstrap/invite/setup/reset/break-glass
only. Login/JWT/guard integration is intentionally held for DC-11P3.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text

from api.app import app
from api.dependencies import get_platform_db
from core.config import Settings
from core.security import verify_password
from database.session import AsyncSessionLocal, async_engine
from models.platform_audit_log import PlatformAuditLog
from models.platform_operator import (
    PlatformOperator,
    PlatformOperatorRecoveryCredential,
    PlatformOperatorResetToken,
    PlatformOperatorSetupToken,
)
from models.wholesaler import Wholesaler
from services.email_delivery import (
    clear_dev_email_deliveries,
    get_dev_platform_operator_email_deliveries,
)
from services.onboarding_service import hash_token
from services.platform_operator_service import (
    EmailDeliveryNotConfiguredError,
    PlatformOperatorExistsError,
    PlatformOperatorInvalidStateError,
    PlatformOperatorRecoveryInvalidError,
    PlatformOperatorService,
    PlatformOperatorTokenInvalidError,
)


ROOT = Path(__file__).resolve().parents[2]
BASE_REF = "d0c7c6f1a754d4ea160547e59a6dfec6ce2b451a"  # pragma: allowlist secret
SETUP_PASSWORD = "Dc11p2_SetupPw_01!"  # pragma: allowlist secret
RESET_PASSWORD = "Dc11p2_ResetPw_01!"  # pragma: allowlist secret
BREAK_GLASS_CREDENTIAL = "R1OldVaultKey-2026-Alpha!"  # pragma: allowlist secret
REPLACEMENT_RECOVERY_CREDENTIAL = "R1NewVaultKey-2026-Bravo!"  # pragma: allowlist secret
SMTP_FAILURE = "SMTP_FAILURE"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
async def _dc11p2_setup():
    await _ensure_platform_operator_tables()
    await _clear_platform_operator_rows()
    clear_dev_email_deliveries()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_platform_db, None)
        await _clear_platform_operator_rows()
        clear_dev_email_deliveries()


async def _ensure_platform_operator_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(PlatformAuditLog.__table__.create, checkfirst=True)
        await connection.run_sync(PlatformOperator.__table__.create, checkfirst=True)
        await connection.run_sync(PlatformOperatorSetupToken.__table__.create, checkfirst=True)
        await connection.run_sync(PlatformOperatorResetToken.__table__.create, checkfirst=True)
        await connection.run_sync(PlatformOperatorRecoveryCredential.__table__.create, checkfirst=True)


async def _clear_platform_operator_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(text("DELETE FROM public.platform_operator_recovery_credentials"))
        await session.execute(text("DELETE FROM public.platform_operator_reset_tokens"))
        await session.execute(text("DELETE FROM public.platform_operator_setup_tokens"))
        await session.execute(text("DELETE FROM public.platform_audit_logs WHERE action LIKE 'platform_operator.%'"))
        await session.execute(text("DELETE FROM public.platform_operators"))
        await session.commit()


async def _platform_client() -> AsyncClient:
    async def _override_platform_db():
        async with AsyncSessionLocal() as session:
            session.info["tenant_schema"] = "public"
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_platform_db] = _override_platform_db
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://testserver")


async def _operator_by_email(email: str) -> PlatformOperator:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PlatformOperator)
            .where(PlatformOperator.email == email)
            .execution_options(ignore_tenant=True)
        )
        operator = result.scalar_one()
        return operator


async def _platform_counts() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        return {
            "operators": await session.scalar(
                select(func.count(PlatformOperator.id)).execution_options(ignore_tenant=True)
            ),
            "setup_tokens": await session.scalar(
                select(func.count(PlatformOperatorSetupToken.id)).execution_options(ignore_tenant=True)
            ),
            "reset_tokens": await session.scalar(
                select(func.count(PlatformOperatorResetToken.id)).execution_options(ignore_tenant=True)
            ),
            "recovery_credentials": await session.scalar(
                select(func.count(PlatformOperatorRecoveryCredential.id)).execution_options(ignore_tenant=True)
            ),
            "audits": await session.scalar(
                select(func.count(PlatformAuditLog.id))
                .where(PlatformAuditLog.action.like("platform_operator.%"))
                .execution_options(ignore_tenant=True)
            ),
        }


def _production_settings_missing_smtp() -> Settings:
    return Settings(
        MPANGO_ENV="production",
        DATABASE_URL="postgresql://db.invalid:5432/mpango_prod_like",
        REDIS_URL="redis://redis.invalid:6379/0",
        SECRET_KEY="a" * 64,  # pragma: allowlist secret
        EMAIL_PROVIDER="dev_sink",
        EMAIL_DELIVERY_MODE="dev_sink",
    )


def _production_settings_with_smtp() -> Settings:
    return Settings(
        MPANGO_ENV="production",
        DATABASE_URL="postgresql://db.invalid:5432/mpango_prod_like",
        REDIS_URL="redis://redis.invalid:6379/0",
        SECRET_KEY="b" * 64,  # pragma: allowlist secret
        EMAIL_PROVIDER="smtp",
        EMAIL_DELIVERY_MODE="smtp",
        SMTP_HOST="smtp.invalid",
        SMTP_USER="smtp-user",
        SMTP_PASSWORD="x" * 12,  # pragma: allowlist secret
        EMAIL_FROM="noreply@example.com",
    )


@pytest.mark.asyncio
async def test_bootstrap_first_operator_issues_hash_only_setup_token_and_audit():
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        result = await service.bootstrap_first_operator(
            email="Admin@Platform.Example",
            recovery_credential=BREAK_GLASS_CREDENTIAL,
        )
        await session.commit()

    assert result.email == "admin@platform.example"
    assert result.status == "pending_setup"
    deliveries = get_dev_platform_operator_email_deliveries("admin@platform.example")
    assert len(deliveries) == 1
    assert deliveries[0].purpose == "platform_operator_setup"

    async with AsyncSessionLocal() as session:
        operator = (
            await session.execute(select(PlatformOperator).execution_options(ignore_tenant=True))
        ).scalar_one()
        setup_token = (
            await session.execute(select(PlatformOperatorSetupToken).execution_options(ignore_tenant=True))
        ).scalar_one()
        recovery_credential = (
            await session.execute(select(PlatformOperatorRecoveryCredential).execution_options(ignore_tenant=True))
        ).scalar_one()
        audit_actions = (
            await session.execute(select(PlatformAuditLog.action).execution_options(ignore_tenant=True))
        ).scalars().all()

    assert operator.email == "admin@platform.example"
    assert operator.password_hash is None
    assert setup_token.operator_id == operator.id
    assert setup_token.token_hash == hash_token(deliveries[0].token)
    assert deliveries[0].token not in setup_token.token_hash
    assert recovery_credential.operator_id == operator.id
    assert recovery_credential.credential_hash == hash_token(BREAK_GLASS_CREDENTIAL)
    assert BREAK_GLASS_CREDENTIAL not in recovery_credential.credential_hash
    assert "platform_operator.bootstrap" in audit_actions


@pytest.mark.asyncio
async def test_recovery_credential_strength_rejects_blank_and_weak_values():
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        await service.invite_operator(email="weak-recovery@example.com")
        token = get_dev_platform_operator_email_deliveries("weak-recovery@example.com")[0].token
        await service.setup_credential(setup_token=token, password=SETUP_PASSWORD)
        operator = await service.verify_platform_password(
            email="weak-recovery@example.com",
            password=SETUP_PASSWORD,
        )
        for weak_value in ("", "short", "alllowercasebutlongenoughvalue"):
            with pytest.raises(PlatformOperatorRecoveryInvalidError):
                await service.store_recovery_credential(
                    operator_id=operator.id,
                    raw_credential=weak_value,
                )
        await session.rollback()


@pytest.mark.asyncio
async def test_setup_credential_consumes_single_use_token_and_enables_login_helper():
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        await service.invite_operator(email="ops@example.com")
        await session.commit()

    token = get_dev_platform_operator_email_deliveries("ops@example.com")[0].token
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        result = await service.setup_credential(setup_token=token, password=SETUP_PASSWORD)
        await session.commit()

    assert result.status == "active"
    async with AsyncSessionLocal() as session:
        operator = (
            await session.execute(select(PlatformOperator).execution_options(ignore_tenant=True))
        ).scalar_one()
        token_row = (
            await session.execute(select(PlatformOperatorSetupToken).execution_options(ignore_tenant=True))
        ).scalar_one()
        assert operator.status == "active"
        assert operator.password_hash != SETUP_PASSWORD
        assert verify_password(SETUP_PASSWORD, operator.password_hash)
        assert token_row.used_at is not None

    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        verified = await service.verify_platform_password(email="ops@example.com", password=SETUP_PASSWORD)
        await session.commit()
    assert verified is not None

    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        with pytest.raises(PlatformOperatorTokenInvalidError):
            await service.setup_credential(setup_token=token, password=SETUP_PASSWORD)
        await session.rollback()


@pytest.mark.asyncio
async def test_forgot_and_reset_password_are_neutral_hash_only_and_single_use():
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        await service.invite_operator(email="reset@example.com")
        setup_token = get_dev_platform_operator_email_deliveries("reset@example.com")[0].token
        await service.setup_credential(setup_token=setup_token, password=SETUP_PASSWORD)
        await session.commit()

    async with await _platform_client() as client:
        missing = await client.post(
            "/api/v1/platform/operators/forgot-password",
            json={"email": "missing@example.com"},
        )
        existing = await client.post(
            "/api/v1/platform/operators/forgot-password",
            json={"email": "reset@example.com"},
        )

    assert missing.status_code == 200
    assert existing.status_code == 200
    reset_deliveries = [
        delivery for delivery in get_dev_platform_operator_email_deliveries("reset@example.com")
        if delivery.purpose == "platform_operator_reset"
    ]
    assert len(reset_deliveries) == 1
    reset_token = reset_deliveries[0].token

    async with AsyncSessionLocal() as session:
        reset_row = (
            await session.execute(select(PlatformOperatorResetToken).execution_options(ignore_tenant=True))
        ).scalar_one()
    assert reset_row.token_hash == hash_token(reset_token)
    assert reset_token not in reset_row.token_hash

    async with await _platform_client() as client:
        leaked = await client.post(
            f"/api/v1/platform/operators/reset-password?resetToken={reset_token}",
            json={"reset_token": reset_token, "new_password": RESET_PASSWORD},
        )
        ok = await client.post(
            "/api/v1/platform/operators/reset-password",
            json={"reset_token": reset_token, "new_password": RESET_PASSWORD},
        )

    assert leaked.status_code == 401
    assert ok.status_code == 200
    ok_body = ok.json()
    assert ok_body["data"] == {}
    assert "operator_id" not in ok_body["data"]
    assert "status" not in ok_body["data"]
    operator = await _operator_by_email("reset@example.com")
    assert verify_password(RESET_PASSWORD, operator.password_hash)

    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        with pytest.raises(PlatformOperatorTokenInvalidError):
            await service.reset_password(reset_token=reset_token, new_password=RESET_PASSWORD)
        await session.rollback()


@pytest.mark.asyncio
async def test_disable_enable_revoke_and_break_glass_preserve_password_hash():
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        await service.invite_operator(email="recover@example.com")
        setup_token = get_dev_platform_operator_email_deliveries("recover@example.com")[0].token
        await service.setup_credential(setup_token=setup_token, password=SETUP_PASSWORD)
        operator = await service.verify_platform_password(email="recover@example.com", password=SETUP_PASSWORD)
        await service.store_recovery_credential(
            operator_id=operator.id,
            raw_credential=BREAK_GLASS_CREDENTIAL,
        )
        original_hash = operator.password_hash
        disabled = await service.disable_operator(operator.id)
        assert disabled.status == "disabled"
        enabled = await service.enable_operator(operator.id)
        assert enabled.status == "active"
        revoked = await service.revoke_operator(operator.id)
        assert revoked.status == "disabled"
        with pytest.raises(PlatformOperatorInvalidStateError):
            await service.enable_operator(operator.id)
        recovered = await service.break_glass_recover(
            raw_credential=BREAK_GLASS_CREDENTIAL,
            replacement_credential=REPLACEMENT_RECOVERY_CREDENTIAL,
            operator_email="recover@example.com",
        )
        await session.commit()

    assert recovered.status == "active"
    operator = await _operator_by_email("recover@example.com")
    assert operator.password_hash == original_hash
    assert operator.revoked_at is None
    assert operator.failed_login_attempts == 0
    assert any(
        delivery.purpose == "platform_operator_reset"
        for delivery in get_dev_platform_operator_email_deliveries("recover@example.com")
    )

    async with AsyncSessionLocal() as session:
        credentials = (
            await session.execute(
                select(PlatformOperatorRecoveryCredential)
                .order_by(PlatformOperatorRecoveryCredential.created_at.asc())
                .execution_options(ignore_tenant=True)
            )
        ).scalars().all()
        service = PlatformOperatorService(session)
        assert [credential.status for credential in credentials] == ["used", "active"]
        assert credentials[1].credential_hash == hash_token(REPLACEMENT_RECOVERY_CREDENTIAL)
        assert REPLACEMENT_RECOVERY_CREDENTIAL not in credentials[1].credential_hash
        with pytest.raises(PlatformOperatorRecoveryInvalidError):
            await service.break_glass_recover(
                raw_credential=BREAK_GLASS_CREDENTIAL,
                replacement_credential="R1AnotherVaultKey-2026-Charlie!",  # pragma: allowlist secret
                operator_email="recover@example.com",
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_normal_enable_cannot_revive_revoked_operator():
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        await service.invite_operator(email="revoked-enable@example.com")
        token = get_dev_platform_operator_email_deliveries("revoked-enable@example.com")[0].token
        await service.setup_credential(setup_token=token, password=SETUP_PASSWORD)
        operator = await service.verify_platform_password(
            email="revoked-enable@example.com",
            password=SETUP_PASSWORD,
        )
        await service.revoke_operator(operator.id)
        revoked_at = operator.revoked_at
        with pytest.raises(PlatformOperatorInvalidStateError):
            await service.enable_operator(operator.id)
        await session.commit()

    operator = await _operator_by_email("revoked-enable@example.com")
    assert operator.status == "disabled"
    assert operator.revoked_at == revoked_at


@pytest.mark.asyncio
async def test_email_links_use_exact_public_paths_and_encoded_tokens(monkeypatch):
    setup_raw = "setup token/+?="  # pragma: allowlist secret
    reset_raw = "reset token/+?="  # pragma: allowlist secret
    token_iter = iter([setup_raw, reset_raw])
    monkeypatch.setattr(
        "services.platform_operator_service.generate_verification_token",
        lambda: next(token_iter),
    )

    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        await service.bootstrap_first_operator(
            email="links@example.com",
            recovery_credential=BREAK_GLASS_CREDENTIAL,
        )
        setup_delivery = get_dev_platform_operator_email_deliveries("links@example.com")[0]
        await service.setup_credential(setup_token=setup_raw, password=SETUP_PASSWORD)
        await service.request_password_reset(email="links@example.com")
        await session.commit()

    reset_delivery = [
        delivery for delivery in get_dev_platform_operator_email_deliveries("links@example.com")
        if delivery.purpose == "platform_operator_reset"
    ][0]
    assert setup_delivery.link == f"/platform/setup-credential?setupToken={quote(setup_raw, safe='')}"
    assert reset_delivery.link == f"/platform/reset-password?resetToken={quote(reset_raw, safe='')}"


@pytest.mark.asyncio
async def test_public_setup_and_reset_responses_are_empty_and_neutral():
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        await service.invite_operator(email="public-neutral@example.com")
        await session.commit()

    setup_token = get_dev_platform_operator_email_deliveries("public-neutral@example.com")[0].token
    async with await _platform_client() as client:
        setup_resp = await client.post(
            "/api/v1/platform/operators/setup-credential",
            json={"setup_token": setup_token, "password": SETUP_PASSWORD},
        )
        forgot_resp = await client.post(
            "/api/v1/platform/operators/forgot-password",
            json={"email": "public-neutral@example.com"},
        )
    reset_token = [
        delivery for delivery in get_dev_platform_operator_email_deliveries("public-neutral@example.com")
        if delivery.purpose == "platform_operator_reset"
    ][0].token
    async with await _platform_client() as client:
        reset_resp = await client.post(
            "/api/v1/platform/operators/reset-password",
            json={"reset_token": reset_token, "new_password": RESET_PASSWORD},
        )

    for response in (setup_resp, forgot_resp, reset_resp):
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == {}
        forbidden_keys = {
            "operator_id", "status", "role", "auth_version", "email",
            "token_hash", "credential_hash", "recovery_credential_id",
        }
        assert forbidden_keys.isdisjoint(body["data"])


@pytest.mark.asyncio
async def test_concurrent_same_email_invite_maps_uniqueness_to_controlled_conflict():
    async def invite_once() -> str:
        async with AsyncSessionLocal() as session:
            service = PlatformOperatorService(session)
            try:
                await service.invite_operator(email="race@example.com")
                await session.commit()
                return "created"
            except PlatformOperatorExistsError:
                await session.rollback()
                return "exists"

    results = await asyncio.gather(invite_once(), invite_once())
    assert sorted(results) == ["created", "exists"]

    async with AsyncSessionLocal() as session:
        operator_count = await session.scalar(
            select(func.count(PlatformOperator.id))
            .where(PlatformOperator.email == "race@example.com")
            .execution_options(ignore_tenant=True)
        )
        active_setup_count = await session.scalar(
            select(func.count(PlatformOperatorSetupToken.id))
            .join(PlatformOperator, PlatformOperatorSetupToken.operator_id == PlatformOperator.id)
            .where(PlatformOperator.email == "race@example.com")
            .where(PlatformOperatorSetupToken.used_at.is_(None))
            .where(PlatformOperatorSetupToken.revoked_at.is_(None))
            .where(PlatformOperatorSetupToken.is_deleted.is_(False))
            .execution_options(ignore_tenant=True)
        )
    assert operator_count == 1
    assert active_setup_count == 1


@pytest.mark.asyncio
async def test_bootstrap_and_invite_delivery_fail_closed_rolls_back(monkeypatch):
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session, settings=_production_settings_missing_smtp())
        with pytest.raises(EmailDeliveryNotConfiguredError):
            await service.bootstrap_first_operator(
                email="missing-smtp-bootstrap@example.com",
                recovery_credential=BREAK_GLASS_CREDENTIAL,
            )
        await session.rollback()
    assert await _platform_counts() == {
        "operators": 0,
        "setup_tokens": 0,
        "reset_tokens": 0,
        "recovery_credentials": 0,
        "audits": 0,
    }

    def fail_smtp(**_kwargs):
        raise EmailDeliveryNotConfiguredError(SMTP_FAILURE)

    monkeypatch.setattr("services.email_delivery._send_smtp_email", fail_smtp)
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session, settings=_production_settings_with_smtp())
        with pytest.raises(EmailDeliveryNotConfiguredError):
            await service.invite_operator(email="smtp-fail-invite@example.com")
        await session.rollback()
    assert await _platform_counts() == {
        "operators": 0,
        "setup_tokens": 0,
        "reset_tokens": 0,
        "recovery_credentials": 0,
        "audits": 0,
    }


@pytest.mark.asyncio
async def test_reset_delivery_failure_preserves_operator_and_prior_token(monkeypatch):
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        await service.invite_operator(email="reset-fail@example.com")
        setup_token = get_dev_platform_operator_email_deliveries("reset-fail@example.com")[0].token
        await service.setup_credential(setup_token=setup_token, password=SETUP_PASSWORD)
        await service.request_password_reset(email="reset-fail@example.com")
        await session.commit()

    operator_before = await _operator_by_email("reset-fail@example.com")
    async with AsyncSessionLocal() as session:
        old_token = (
            await session.execute(select(PlatformOperatorResetToken).execution_options(ignore_tenant=True))
        ).scalar_one()
        old_token_snapshot = (old_token.id, old_token.token_hash, old_token.used_at, old_token.revoked_at)
        audit_count = await session.scalar(
            select(func.count(PlatformAuditLog.id))
            .where(PlatformAuditLog.action.like("platform_operator.%"))
            .execution_options(ignore_tenant=True)
        )

    def fail_delivery(**_kwargs):
        raise EmailDeliveryNotConfiguredError(SMTP_FAILURE)

    monkeypatch.setattr("services.platform_operator_service.record_platform_operator_reset_email", fail_delivery)
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        with pytest.raises(EmailDeliveryNotConfiguredError):
            await service.request_password_reset(email="reset-fail@example.com")
        await session.rollback()

    operator_after = await _operator_by_email("reset-fail@example.com")
    async with AsyncSessionLocal() as session:
        tokens_after = (
            await session.execute(
                select(PlatformOperatorResetToken)
                .order_by(PlatformOperatorResetToken.created_at.asc())
                .execution_options(ignore_tenant=True)
            )
        ).scalars().all()
        audit_count_after = await session.scalar(
            select(func.count(PlatformAuditLog.id))
            .where(PlatformAuditLog.action.like("platform_operator.%"))
            .execution_options(ignore_tenant=True)
        )
    assert operator_after.password_hash == operator_before.password_hash
    assert operator_after.auth_version == operator_before.auth_version
    assert len(tokens_after) == 1
    assert (tokens_after[0].id, tokens_after[0].token_hash, tokens_after[0].used_at, tokens_after[0].revoked_at) == old_token_snapshot
    assert audit_count_after == audit_count


@pytest.mark.asyncio
async def test_break_glass_delivery_failure_preserves_prior_state(monkeypatch):
    manual_reset_token = "R1ManualResetToken-2026!"  # pragma: allowlist secret
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        await service.invite_operator(email="break-fail@example.com")
        setup_token = get_dev_platform_operator_email_deliveries("break-fail@example.com")[0].token
        await service.setup_credential(setup_token=setup_token, password=SETUP_PASSWORD)
        operator = await service.verify_platform_password(email="break-fail@example.com", password=SETUP_PASSWORD)
        await service.store_recovery_credential(
            operator_id=operator.id,
            raw_credential=BREAK_GLASS_CREDENTIAL,
        )
        await service.revoke_operator(operator.id)
        session.add(
            PlatformOperatorResetToken(
                operator_id=operator.id,
                token_hash=hash_token(manual_reset_token),
                purpose="reset",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        await session.commit()

    before = await _operator_by_email("break-fail@example.com")
    async with AsyncSessionLocal() as session:
        credential_before = (
            await session.execute(select(PlatformOperatorRecoveryCredential).execution_options(ignore_tenant=True))
        ).scalar_one()
        token_before = (
            await session.execute(select(PlatformOperatorResetToken).execution_options(ignore_tenant=True))
        ).scalar_one()
        audit_count = await session.scalar(
            select(func.count(PlatformAuditLog.id))
            .where(PlatformAuditLog.action.like("platform_operator.%"))
            .execution_options(ignore_tenant=True)
        )

    def fail_delivery(**_kwargs):
        raise EmailDeliveryNotConfiguredError(SMTP_FAILURE)

    monkeypatch.setattr("services.platform_operator_service.record_platform_operator_reset_email", fail_delivery)
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        with pytest.raises(EmailDeliveryNotConfiguredError):
            await service.break_glass_recover(
                raw_credential=BREAK_GLASS_CREDENTIAL,
                replacement_credential=REPLACEMENT_RECOVERY_CREDENTIAL,
                operator_email="break-fail@example.com",
            )
        await session.rollback()

    after = await _operator_by_email("break-fail@example.com")
    async with AsyncSessionLocal() as session:
        credentials_after = (
            await session.execute(select(PlatformOperatorRecoveryCredential).execution_options(ignore_tenant=True))
        ).scalars().all()
        tokens_after = (
            await session.execute(select(PlatformOperatorResetToken).execution_options(ignore_tenant=True))
        ).scalars().all()
        audit_count_after = await session.scalar(
            select(func.count(PlatformAuditLog.id))
            .where(PlatformAuditLog.action.like("platform_operator.%"))
            .execution_options(ignore_tenant=True)
        )
    assert after.password_hash == before.password_hash
    assert after.auth_version == before.auth_version
    assert after.revoked_at == before.revoked_at
    assert len(credentials_after) == 1
    assert credentials_after[0].id == credential_before.id
    assert credentials_after[0].status == "active"
    assert len(tokens_after) == 1
    assert tokens_after[0].id == token_before.id
    assert tokens_after[0].token_hash == token_before.token_hash
    assert tokens_after[0].revoked_at is None
    assert audit_count_after == audit_count


@pytest.mark.asyncio
async def test_recovery_credential_rotation_boundary_for_p3_wiring():
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        await service.invite_operator(email="rotate@example.com")
        setup_token = get_dev_platform_operator_email_deliveries("rotate@example.com")[0].token
        await service.setup_credential(setup_token=setup_token, password=SETUP_PASSWORD)
        operator = await service.verify_platform_password(email="rotate@example.com", password=SETUP_PASSWORD)
        await service.store_recovery_credential(
            operator_id=operator.id,
            raw_credential=BREAK_GLASS_CREDENTIAL,
        )
        before_auth_version = operator.auth_version
        result = await service.rotate_recovery_credential(
            operator_id=operator.id,
            current_credential=BREAK_GLASS_CREDENTIAL,
            replacement_credential=REPLACEMENT_RECOVERY_CREDENTIAL,
        )
        await session.commit()

    assert result.auth_version == before_auth_version
    async with AsyncSessionLocal() as session:
        credentials = (
            await session.execute(
                select(PlatformOperatorRecoveryCredential)
                .order_by(PlatformOperatorRecoveryCredential.created_at.asc())
                .execution_options(ignore_tenant=True)
            )
        ).scalars().all()
    assert [credential.status for credential in credentials] == ["revoked", "active"]
    assert credentials[1].credential_hash == hash_token(REPLACEMENT_RECOVERY_CREDENTIAL)


def test_bootstrap_and_break_glass_cli_recovery_credentials_are_hidden_stdin_only():
    bootstrap_source = (ROOT / "backend" / "scripts" / "bootstrap_platform_operator.py").read_text()
    break_glass_source = (ROOT / "backend" / "scripts" / "break_glass_platform_operator.py").read_text()
    assert "getpass.getpass" in bootstrap_source
    assert "getpass.getpass" in break_glass_source
    assert "--recovery" not in bootstrap_source
    assert "--recovery" not in break_glass_source
    assert "replacement" not in bootstrap_source.lower()


@pytest.mark.asyncio
async def test_dc11p2_routes_are_registered_public_or_guarded_by_policy_harness():
    from tests.test_route_authorization_policy import classify_route

    routes = {
        route.path: classify_route(route)
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/platform/operators")
    }
    assert routes["/api/v1/platform/operators/setup-credential"].policy == "public"
    assert routes["/api/v1/platform/operators/forgot-password"].policy == "public"
    assert routes["/api/v1/platform/operators/reset-password"].policy == "public"
    assert routes["/api/v1/platform/operators"].policy == "platform_permission"
    assert routes["/api/v1/platform/operators/invite"].policy == "platform_permission"
    assert routes["/api/v1/platform/operators/{operator_id}/disable"].policy == "platform_permission"
    assert routes["/api/v1/platform/operators/{operator_id}/enable"].policy == "platform_permission"
    assert routes["/api/v1/platform/operators/{operator_id}/revoke"].policy == "platform_permission"


def test_dc11p2_does_not_modify_p3_auth_jwt_or_guard_files():
    changed_candidates = {
        "backend/api/v1/auth.py",
        "backend/core/security.py",
        "backend/api/v1/platform/p10/guard.py",
    }
    for rel in changed_candidates:
        assert (ROOT / rel).exists()
    # P3 will modify these files; DC-11P2 must leave them to the exact base.
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--name-only", BASE_REF, "--", *changed_candidates],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == ""


def test_dc11p2_schema_sufficiency_no_new_migration_or_034_mutation():
    versions_dir = ROOT / "backend" / "alembic" / "versions"
    assert not list(versions_dir.glob("035*.py"))
    migration_034 = versions_dir / "034_platform_operators.py"
    assert migration_034.exists()
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--name-only", BASE_REF, "--", str(migration_034.relative_to(ROOT))],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == ""
