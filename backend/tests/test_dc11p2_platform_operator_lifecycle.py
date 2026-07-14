"""DC-11P2 platform operator credential lifecycle tests.

Scope guard: these tests cover service/bootstrap/invite/setup/reset/break-glass
only. Login/JWT/guard integration is intentionally held for DC-11P3.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from api.app import app
from api.dependencies import get_platform_db
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
    PlatformOperatorRecoveryInvalidError,
    PlatformOperatorService,
    PlatformOperatorTokenInvalidError,
)


ROOT = Path(__file__).resolve().parents[2]
BASE_REF = "d0c7c6f1a754d4ea160547e59a6dfec6ce2b451a"  # pragma: allowlist secret
SETUP_PASSWORD = "Dc11p2_SetupPw_01!"  # pragma: allowlist secret
RESET_PASSWORD = "Dc11p2_ResetPw_01!"  # pragma: allowlist secret
BREAK_GLASS_CREDENTIAL = "dc11p2-break-glass-credential"  # pragma: allowlist secret


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


@pytest.mark.asyncio
async def test_bootstrap_first_operator_issues_hash_only_setup_token_and_audit():
    async with AsyncSessionLocal() as session:
        service = PlatformOperatorService(session)
        result = await service.bootstrap_first_operator(email="Admin@Platform.Example")
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
        audit_actions = (
            await session.execute(select(PlatformAuditLog.action).execution_options(ignore_tenant=True))
        ).scalars().all()

    assert operator.email == "admin@platform.example"
    assert operator.password_hash is None
    assert setup_token.operator_id == operator.id
    assert setup_token.token_hash == hash_token(deliveries[0].token)
    assert deliveries[0].token not in setup_token.token_hash
    assert "platform_operator.bootstrap" in audit_actions


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
        recovered = await service.break_glass_recover(
            raw_credential=BREAK_GLASS_CREDENTIAL,
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
        credential = (
            await session.execute(
                select(PlatformOperatorRecoveryCredential).execution_options(ignore_tenant=True)
            )
        ).scalar_one()
        service = PlatformOperatorService(session)
        assert credential.status == "used"
        with pytest.raises(PlatformOperatorRecoveryInvalidError):
            await service.break_glass_recover(
                raw_credential=BREAK_GLASS_CREDENTIAL,
                operator_email="recover@example.com",
            )
        await session.rollback()


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
