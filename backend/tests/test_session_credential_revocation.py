"""Session-generation contracts; native PG controls are separate from unit controls."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import secrets

from jose import jwt
import pytest
import pytest_asyncio

from core import security


@pytest.fixture
def protocol_settings(monkeypatch):
    # Unit-only configuration boundary: real encoder/decoder/claim checks run.
    config = SimpleNamespace(
        SECRET_KEY=secrets.token_hex(32), ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=15, REFRESH_TOKEN_EXPIRE_DAYS=1,
    )
    monkeypatch.setattr(security, "get_settings", lambda: config)
    return config


@pytest.mark.usefixtures("protocol_settings")
class TestSessionProtocol:
    def test_contextual_and_compatibility_issuers_preserve_explicit_generation(self):
        uid, tid = str(uuid4()), str(uuid4())
        schema = "t_" + tid.replace("-", "")
        tokens = [
            security.create_contextual_token(uid, ["admin"], tid, schema, credential_epoch=7),
            security.create_access_token(uid, tid, schema, credential_epoch=7),
            security.create_refresh_token(uid, tid, schema, credential_epoch=7),
        ]
        for raw in tokens:
            decoded = security.decode_token(raw)
            assert decoded.sv == 2 and decoded.credential_epoch == 7
            assert decoded.tmap is None and decoded.tver is None

    def test_identity_keeps_independent_versions_for_different_local_users(self):
        a, b, u, v = [str(uuid4()) for _ in range(4)]
        raw = security.create_identity_token(
            u, ["admin"], tenant_user_map={a: u, b: v},
            tenant_credential_epochs={a: 3, b: 9},
        )
        decoded = security.decode_token(raw)
        assert decoded.tver == {a: 3, b: 9}
        assert security.selected_credential_binding(decoded, b) == (v, 9)

    @pytest.mark.parametrize("bad", [None, True, False, "1", 1.0, 0, -1, 2**63])
    def test_invalid_epoch_in_signed_payload_is_rejected(self, protocol_settings, bad):
        uid, tid = str(uuid4()), str(uuid4())
        payload = dict(user_id=uid, tenant_id=tid, tenant_schema="t_" + tid.replace("-", ""),
                       sv=2, credential_epoch=bad, type="access", roles=[],
                       exp=datetime.now(timezone.utc) + timedelta(minutes=1))
        raw = jwt.encode(payload, protocol_settings.SECRET_KEY, algorithm="HS256")
        with pytest.raises(security.InvalidTokenError):
            security.decode_token(raw)

    @pytest.mark.parametrize("kind", ["access", "refresh"])
    def test_old_protocol_must_reauthenticate(self, protocol_settings, kind):
        uid, tid = str(uuid4()), str(uuid4())
        raw = jwt.encode(dict(user_id=uid, tenant_id=tid,
            tenant_schema="t_" + tid.replace("-", ""), roles=[], type=kind,
            exp=datetime.now(timezone.utc) + timedelta(minutes=1)),
            protocol_settings.SECRET_KEY, algorithm="HS256")
        with pytest.raises(security.InvalidTokenError, match="new login"):
            security.decode_token(raw)

    @pytest.mark.parametrize("defect", ["missing", "extra", "bad_uid", "primary_missing", "partial_context"])
    def test_identity_binding_shape_is_not_repaired(self, protocol_settings, defect):
        a, b, u = [str(uuid4()) for _ in range(3)]
        p = dict(user_id=u, tmap={a: u}, tver={a: 1}, sv=2, roles=[], type="access")
        if defect == "missing":
            p["tver"] = {}
        elif defect == "extra":
            p["tver"][b] = 1
        elif defect == "bad_uid":
            p["tmap"][a] = "not-a-user-id"
        elif defect == "primary_missing":
            p["user_id"] = str(uuid4())
        else:
            p["tenant_id"] = a
        with pytest.raises(security.InvalidTokenError):
            security.decode_token(jwt.encode(p, protocol_settings.SECRET_KEY, algorithm="HS256"))

    def test_contextual_token_cannot_acquire_unsigned_foreign_binding(self):
        uid, a, b = [str(uuid4()) for _ in range(3)]
        raw = security.create_contextual_token(uid, [], a, "t_" + a.replace("-", ""), credential_epoch=4)
        token = security.decode_token(raw)
        assert security.selected_credential_binding(token, a) == (uid, 4)
        with pytest.raises(security.InvalidTokenError, match="change tenant"):
            security.selected_credential_binding(token, b)

    def test_epoch_comparison_never_coerces_or_supplies_a_default(self):
        assert security.credential_epoch_matches(2, 2)
        for signed, current in [(None, 1), (1, None), (True, 1), (1, True), (1, "1"), (1, 2)]:
            assert not security.credential_epoch_matches(signed, current)


@pytest_asyncio.fixture
async def live_session_world():
    """Actual product provisioning and middleware; no injected AuthContext."""
    import os
    from fastapi import FastAPI, Depends
    from httpx import ASGITransport, AsyncClient
    from api.app import configure_app
    from api.middleware.rbac import RequirePermission
    from auth.strategies.jwt import JwtAuthStrategy
    from core.config import get_settings
    from core.error_codes import register_exception_handlers
    from tests.test_inventory_manual_adjustment_safety import StockWorld

    assert get_settings().MPANGO_ENV == "staging"
    assert os.environ["TEST_DATABASE_URL"] == os.environ["DATABASE_URL"]
    assert not any(key in os.environ for key in (
        "TEST_ADMIN_DATABASE_URL", "TEST_MIGRATION_DATABASE_URL", "TEST_OPERATOR_DATABASE_URL",
        "MPANGO_DB_ADMIN_URL", "MPANGO_DB_MIGRATE_URL",
    ))
    world = StockWorld()
    await world.initialize()
    app = FastAPI()
    register_exception_handlers(app)
    configure_app(app, get_settings())
    assert isinstance(app.state.auth_strategy, JwtAuthStrategy)
    app.state.effects = 0

    @app.post("/api/v1/foundation-effect")
    async def guarded_effect(token=Depends(RequirePermission("orders:read"))):
        app.state.effects += 1
        return {"effect": app.state.effects, "subject": token.user_id}

    # Independent synthetic clients get independent rate-limit buckets; the
    # real limiter remains configured and no Redis flush/threshold override runs.
    transport = ASGITransport(app=app, client=("192.0.2." + str(1 + uuid4().int % 254), 49152))
    try:
        async with AsyncClient(transport=transport, base_url="http://foundation.invalid") as client:
            yield world, client, app
    finally:
        from database.session import async_engine
        await async_engine.dispose()
        await world.engine.dispose()


async def _identity(client, world, password=None):
    r = await client.post("/api/v1/auth/login", json={"email": world.email, "password": password or world.password})
    assert r.status_code == 200
    return r.json()["data"]


async def _context(client, identity, tid):
    r = await client.post("/api/v1/auth/select-tenant", json={"tenant_id": str(tid)},
                          headers={"Authorization": "Bearer " + identity["access_token"]})
    assert r.status_code == 200
    return r.json()["data"]


async def _me(client, raw):
    return await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + raw})


async def _reset_credential(world, replacement):
    from services.password_reset_service import PasswordResetService
    from services.email_delivery import get_dev_reset_email_deliveries
    async with world.session() as db:
        issued = await PasswordResetService(db).request_reset(world.email)
        assert issued.issued
    proof = get_dev_reset_email_deliveries(world.email)[-1].token
    async with world.session() as db:
        result = await PasswordResetService(db).consume_reset(proof, replacement)
        assert result.action == "reset"
    return proof


async def _join_copy(other, source):
    from uuid import UUID
    from services.staff_credential_service import StaffCredentialService
    from services.staff_management_service import StaffManagementService
    from services.email_delivery import get_dev_staff_email_deliveries
    async with other.session() as db:
        row = await StaffManagementService(db, other.wid, other.schema).create_member(
            other.actor, email=source.email, full_name="Shared identity", template_key="sales",
            create_key=uuid4().hex, adopt_existing=False,
        )
    async with other.session() as db:
        await StaffCredentialService(db).invite(
            tenant_id=other.wid, schema=other.schema, actor_id=other.actor,
            user_id=UUID(row["id"]), owner_password=other.password, expected_version=row["version"],
        )
    proof = get_dev_staff_email_deliveries(source.email)[-1].token
    async with other.session() as db:
        await StaffCredentialService(db).consume(proof, source.password)
    return UUID(row["id"])


@pytest.mark.integration
class TestSessionLive:
    async def test_login_both_refresh_modes_and_legal_tenant_selection(self, live_session_world):
        w, c, _ = live_session_world
        identity = await _identity(c, w)
        assert (await _me(c, identity["access_token"])).status_code == 200
        r = await c.post("/api/v1/auth/refresh", json={"refresh_token": identity["refresh_token"]})
        assert r.status_code == 200
        contextual = await _context(c, r.json()["data"], w.wid)
        assert (await _me(c, contextual["access_token"])).status_code == 200
        r = await c.post("/api/v1/auth/refresh", json={"refresh_token": contextual["refresh_token"]})
        assert r.status_code == 200
        assert (await _me(c, r.json()["data"]["access_token"])).status_code == 200
        r = await c.post("/api/v1/auth/select-tenant", json={"tenant_id": str(w.wid)},
                         headers={"Authorization": "Bearer " + contextual["access_token"]})
        assert r.status_code == 200

    async def test_old_protocol_rejected_by_real_access_refresh_and_selection(self, live_session_world):
        from core.config import get_settings
        w, c, _ = live_session_world
        identity = await _identity(c, w)
        contextual = await _context(c, identity, w.wid)
        config = get_settings()

        def legacy(raw):
            payload = jwt.decode(raw, config.SECRET_KEY, algorithms=[config.ALGORITHM])
            for key in ("sv", "credential_epoch", "tver"):
                payload.pop(key, None)
            return jwt.encode(payload, config.SECRET_KEY, algorithm=config.ALGORITHM)

        # Same real subject/tenant/signature, only the old protocol differs.
        for pair in (identity, contextual):
            r = await _me(c, legacy(pair["access_token"]))
            assert r.status_code == 401 and r.json()["code"] == "INVALID_TOKEN"
            r = await c.post("/api/v1/auth/refresh", json={"refresh_token": legacy(pair["refresh_token"])})
            assert r.status_code == 401 and r.json()["code"] == "INVALID_REFRESH_TOKEN"
        r = await c.post("/api/v1/auth/select-tenant", json={"tenant_id": str(w.wid)},
                         headers={"Authorization": "Bearer " + legacy(identity["access_token"])})
        assert r.status_code == 401 and r.json()["code"] == "INVALID_TOKEN"
        assert (await _me(c, contextual["access_token"])).status_code == 200

    async def test_reset_revokes_access_refresh_and_hot_replays_not_unrelated_user(self, live_session_world):
        from tests.test_inventory_manual_adjustment_safety import StockWorld
        w, c, app = live_session_world
        other = StockWorld()
        try:
            await other.initialize()
            identity = await _identity(c, w)
            contextual = await _context(c, identity, w.wid)
            unrelated = await _context(c, await _identity(c, other), other.wid)
            calls = [
                ("/api/v1/auth/select-tenant", {"tenant_id": str(w.wid)}, identity["access_token"]),
                ("/api/v1/auth/refresh", {"refresh_token": contextual["refresh_token"]}, None),
                ("/api/v1/auth/refresh", {"refresh_token": identity["refresh_token"]}, None),
                ("/api/v1/foundation-effect", {}, contextual["access_token"]),
            ]
            warmed = []
            for path, body, bearer in calls:
                headers = {"X-Idempotency-Key": uuid4().hex}
                if bearer:
                    headers["Authorization"] = "Bearer " + bearer
                assert (await c.post(path, json=body, headers=headers)).status_code == 200
                replay = await c.post(path, json=body, headers=headers)
                assert replay.status_code == 200 and replay.headers.get("X-Idempotency-Replayed") == "true"
                warmed.append((path, body, headers))
            assert app.state.effects == 1
            replacement = secrets.token_urlsafe(32)
            await _reset_credential(w, replacement)
            for raw in (identity["access_token"], contextual["access_token"]):
                denied = await _me(c, raw)
                assert denied.status_code == 401 and denied.json()["code"] == "SESSION_REVOKED"
            for path, body, headers in warmed:
                denied = await c.post(path, json=body, headers=headers)
                assert denied.status_code == 401
                assert denied.headers.get("X-Idempotency-Replayed") is None
            assert app.state.effects == 1
            assert (await _me(c, unrelated["access_token"])).status_code == 200
            assert (await c.post("/api/v1/auth/refresh", json={"refresh_token": unrelated["refresh_token"]})).status_code == 200
            assert (await c.post("/api/v1/auth/login", json={"email": w.email, "password": w.password})).status_code == 401
            assert (await _me(c, (await _context(c, await _identity(c, w, replacement), w.wid))["access_token"])).status_code == 200
        finally:
            await other.engine.dispose()

    async def test_noncredential_update_and_manual_epoch_assignment_do_not_revoke(self, live_session_world):
        from sqlalchemy import text
        w, c, _ = live_session_world
        contextual = await _context(c, await _identity(c, w), w.wid)
        old = security.decode_token(contextual["access_token"]).credential_epoch
        async with w.session() as db:
            await db.execute(text("UPDATE users SET full_name=:n,credential_epoch=999 WHERE id=:u"),
                             {"n": "Ordinary profile edit", "u": w.actor})
        async with w.session() as db:
            assert await db.scalar(text("SELECT credential_epoch FROM users WHERE id=:u"), {"u": w.actor}) == old
        assert (await _me(c, contextual["access_token"])).status_code == 200
        assert (await c.post("/api/v1/auth/refresh", json={"refresh_token": contextual["refresh_token"]})).status_code == 200

    async def test_login_snapshot_cannot_upgrade_old_password_during_reset(self, live_session_world, monkeypatch):
        from api.v1 import auth
        w, c, _ = live_session_world
        real = auth.find_user_across_tenants
        replacement = secrets.token_urlsafe(32)

        async def reset_after_verified_snapshot(*args, **kwargs):
            result = await real(*args, **kwargs)
            assert result[0] is not None
            await _reset_credential(w, replacement)
            return result

        with monkeypatch.context() as patch:
            patch.setattr(auth, "find_user_across_tenants", reset_after_verified_snapshot)
            stale = await _identity(c, w)
        denied = await _me(c, stale["access_token"])
        assert denied.status_code == 401 and denied.json()["code"] == "SESSION_REVOKED"
        assert (await _me(c, (await _identity(c, w, replacement))["access_token"])).status_code == 200

    @pytest.mark.parametrize("mode", ["identity", "contextual"])
    async def test_refresh_does_not_upgrade_signed_generation_during_reset(self, live_session_world, monkeypatch, mode):
        from api.v1 import auth
        from services import identity_authority
        w, c, _ = live_session_world
        identity = await _identity(c, w)
        pair = identity if mode == "identity" else await _context(c, identity, w.wid)
        replacement = secrets.token_urlsafe(32)
        module = identity_authority if mode == "identity" else auth
        name = "current_identity" if mode == "identity" else "_validate_contextual_refresh_subject"
        real = getattr(module, name)

        async def reset_after_validated_refresh(*args, **kwargs):
            signed = await real(*args, **kwargs)
            await _reset_credential(w, replacement)
            return signed

        with monkeypatch.context() as patch:
            patch.setattr(module, name, reset_after_validated_refresh)
            r = await c.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
            assert r.status_code == 200
        denied = await _me(c, r.json()["data"]["access_token"])
        assert denied.status_code == 401 and denied.json()["code"] == "SESSION_REVOKED"
        assert (await _me(c, (await _identity(c, w, replacement))["access_token"])).status_code == 200

    async def test_cross_copy_failure_rolls_back_password_epoch_and_token(self, live_session_world):
        from sqlalchemy import text
        from tests.test_inventory_manual_adjustment_safety import StockWorld
        from services.password_reset_service import PasswordResetService, PasswordResetApplyFailedError, _enumerate_active_tenant_users
        from services.email_delivery import get_dev_reset_email_deliveries
        from services.onboarding_service import hash_token
        w, c, _ = live_session_world
        other = StockWorld()
        installed = False
        try:
            await other.initialize()
            uid = await _join_copy(other, w)
            identity = await _identity(c, w)
            a = await _context(c, identity, w.wid)
            b = await _context(c, identity, other.wid)
            before = []
            authority_before = []
            for world, user in [(w, w.actor), (other, uid)]:
                async with world.session() as db:
                    before.append(tuple((await db.execute(text(
                        "SELECT password_hash,credential_epoch,is_active,is_deleted FROM users WHERE id=:u"
                    ), {"u": user})).one()))
                    authority_before.append((
                        (await db.execute(text("SELECT to_jsonb(m) FROM staff_memberships m WHERE user_id=:u"), {"u": user})).scalar_one_or_none(),
                        (await db.execute(text("SELECT role_id::text FROM user_roles WHERE user_id=:u ORDER BY role_id"), {"u": user})).scalars().all(),
                    ))
            async with w.session() as db:
                scan = await _enumerate_active_tenant_users(db)
                assert [schema for email, schema, _ in scan.rows if email == w.email] == [w.schema, other.schema]
                assert (await PasswordResetService(db).request_reset(w.email)).issued
            proof = get_dev_reset_email_deliveries(w.email)[-1].token
            async with other.session() as db:
                await db.execute(text(f'CREATE FUNCTION "{other.schema}".foundation_reject_write() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION \'FOUNDATION_SECOND_COPY_WRITE_REJECTED\'; END; $$'))
                await db.execute(text(f'CREATE TRIGGER foundation_reject_write BEFORE UPDATE OF password_hash ON "{other.schema}".users FOR EACH ROW EXECUTE FUNCTION "{other.schema}".foundation_reject_write()'))
            installed = True
            replacement = secrets.token_urlsafe(32)
            with pytest.raises(PasswordResetApplyFailedError) as failure:
                async with w.session() as db:
                    await PasswordResetService(db).consume_reset(proof, replacement)
            assert failure.value.updated_count == 1
            for (world, user), expected in zip([(w, w.actor), (other, uid)], before):
                async with world.session() as db:
                    assert tuple((await db.execute(text(
                        "SELECT password_hash,credential_epoch,is_active,is_deleted FROM users WHERE id=:u"
                    ), {"u": user})).one()) == expected
            async with w.session() as db:
                assert await db.scalar(text("SELECT used_at IS NULL FROM public.password_reset_tokens WHERE token_hash=:h"),
                                       {"h": hash_token(proof)}) is True
            assert (await _me(c, a["access_token"])).status_code == 200
            assert (await _me(c, b["access_token"])).status_code == 200
            async with other.session() as db:
                await db.execute(text(f'DROP TRIGGER foundation_reject_write ON "{other.schema}".users'))
                await db.execute(text(f'DROP FUNCTION "{other.schema}".foundation_reject_write()'))
            installed = False
            r = await c.post("/api/v1/auth/reset-password", json={"resetToken": proof, "newPassword": replacement})
            assert r.status_code == 200
            assert (await _me(c, a["access_token"])).status_code == 401
            assert (await _me(c, b["access_token"])).status_code == 401
            for (world, user), expected in zip([(w, w.actor), (other, uid)], authority_before):
                async with world.session() as db:
                    observed = (
                        (await db.execute(text("SELECT to_jsonb(m) FROM staff_memberships m WHERE user_id=:u"), {"u": user})).scalar_one_or_none(),
                        (await db.execute(text("SELECT role_id::text FROM user_roles WHERE user_id=:u ORDER BY role_id"), {"u": user})).scalars().all(),
                    )
                    assert observed == expected
            current = await _identity(c, w, replacement)
            assert (await _me(c, (await _context(c, current, other.wid))["access_token"])).status_code == 200
        finally:
            if installed:
                async with other.session() as db:
                    await db.execute(text(f'DROP TRIGGER foundation_reject_write ON "{other.schema}".users'))
                    await db.execute(text(f'DROP FUNCTION "{other.schema}".foundation_reject_write()'))
            await other.engine.dispose()

    async def test_retailer_issuer_and_existing_reset_participate(self, live_session_world):
        from services.invitation_service import InvitationService
        from services.retailer_provisioning_service import RetailerProvisioningService
        from services.email_delivery import get_dev_retailer_email_deliveries
        w, c, _ = live_session_world
        email, password = secrets.token_hex(12) + "@example.com", secrets.token_urlsafe(32)
        async with w.session() as db:
            invite = await InvitationService().create_invitation(db, wholesaler_id=w.wid)
            await RetailerProvisioningService(db).register_with_invitation(
                invitation_code=invite.code, phone="+254" + str(uuid4().int)[:9], name="Session retailer", email=email,
            )
        proof = get_dev_retailer_email_deliveries(email)[-1].token
        async with w.session() as db:
            await RetailerProvisioningService(db).consume_setup_token(proof, password)
        body = {"email": email, "password": password, "wholesaler_code": w.code}
        r = await c.post("/api/v1/client/auth/login", json=body)
        assert r.status_code == 200
        pair = r.json()["data"]["tokens"]
        assert (await _me(c, pair["access_token"])).status_code == 200
        assert (await c.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code == 200
        async with w.session() as db:
            assert await RetailerProvisioningService(db).request_password_reset(email=email, wholesaler_code=w.code)
        proof = get_dev_retailer_email_deliveries(email)[-1].token
        replacement = secrets.token_urlsafe(32)
        async with w.session() as db:
            await RetailerProvisioningService(db).consume_password_reset(proof, replacement)
        assert (await _me(c, pair["access_token"])).status_code == 401
        assert (await c.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code == 401
        body["password"] = replacement
        r = await c.post("/api/v1/client/auth/login", json=body)
        assert r.status_code == 200
        assert (await _me(c, r.json()["data"]["tokens"]["access_token"])).status_code == 200

    async def test_existing_owner_writer_revokes_old_tokens_without_grant_changes(self, live_session_world):
        from sqlalchemy import text
        from services.owner_credential_service import OwnerCredentialSetupService
        w, c, _ = live_session_world
        identity = await _identity(c, w)
        contextual = await _context(c, identity, w.wid)
        async with w.session() as db:
            owner_before = tuple((await db.execute(text(
                "SELECT owner_user_id,state,tenant_id,registration_id,source,evidence_digest FROM staff_authority"
            ))).one())
            grants_before = (await db.execute(text(
                "SELECT ur.role_id::text,rp.permission_id::text FROM user_roles ur "
                "JOIN role_permissions rp ON rp.role_id=ur.role_id WHERE ur.user_id=:u ORDER BY 1,2"
            ), {"u": w.actor})).all()
        replacement = secrets.token_urlsafe(32)
        async with w.session() as db:
            writer = OwnerCredentialSetupService(db)
            issued = await writer.issue_setup_token(w.registration)
            setup = await writer.consume_setup_token(issued.raw_token, replacement)
            assert (await writer.create_first_admin_rbac(setup)).user_id == w.actor
        for pair in (identity, contextual):
            assert (await _me(c, pair["access_token"])).status_code == 401
            assert (await c.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})).status_code == 401
        async with w.session() as db:
            assert tuple((await db.execute(text(
                "SELECT owner_user_id,state,tenant_id,registration_id,source,evidence_digest FROM staff_authority"
            ))).one()) == owner_before
            assert (await db.execute(text(
                "SELECT ur.role_id::text,rp.permission_id::text FROM user_roles ur "
                "JOIN role_permissions rp ON rp.role_id=ur.role_id WHERE ur.user_id=:u ORDER BY 1,2"
            ), {"u": w.actor})).all() == grants_before
        assert (await _me(c, (await _identity(c, w, replacement))["access_token"])).status_code == 200

    async def test_real_employee_disable_and_rejoin_never_resurrect_old_tokens(self, live_session_world):
        from tests.test_inventory_manual_adjustment_safety import StockWorld
        from services.staff_management_service import StaffManagementService
        from services.staff_credential_service import StaffCredentialService
        from services.email_delivery import get_dev_staff_email_deliveries
        w, c, _ = live_session_world
        other = StockWorld()
        try:
            await other.initialize()
            uid = await _join_copy(other, w)
            identity = await _identity(c, w)
            a = await _context(c, identity, w.wid)
            b = await _context(c, identity, other.wid)
            async with other.session() as db:
                manager = StaffManagementService(db, other.wid, other.schema)
                row = await manager.member(uid)
                await manager.edit_member(other.actor, uid, expected_version=row["version"], is_active=False)
            assert (await _me(c, b["access_token"])).status_code == 401
            assert (await c.post("/api/v1/auth/refresh", json={"refresh_token": b["refresh_token"]})).status_code == 401
            assert (await _me(c, a["access_token"])).status_code == 200
            async with other.session() as db:
                manager = StaffManagementService(db, other.wid, other.schema)
                row = await manager.member(uid)
                restored = await manager.edit_member(other.actor, uid, expected_version=row["version"], is_active=True)
                assert restored["is_active"] is False
            assert (await _me(c, b["access_token"])).status_code == 401
            async with other.session() as db:
                await StaffCredentialService(db).invite(tenant_id=other.wid, schema=other.schema,
                    actor_id=other.actor, user_id=uid, owner_password=other.password, expected_version=restored["version"])
            proof = get_dev_staff_email_deliveries(w.email)[-1].token
            async with other.session() as db:
                await StaffCredentialService(db).consume(proof, w.password)
            refused = await _me(c, b["access_token"])
            assert refused.status_code == 401 and refused.json()["code"] == "SESSION_REVOKED"
            assert (await _me(c, a["access_token"])).status_code == 200
            assert (await _me(c, (await _context(c, await _identity(c, w), other.wid))["access_token"])).status_code == 200
        finally:
            await other.engine.dispose()

    async def test_repeat_bootstrap_preserves_generation_and_rejects_damaged_guard(self, live_session_world):
        import os
        from sqlalchemy import text
        from scripts.bootstrap_tenant_schema import bootstrap
        w, c, _ = live_session_world
        replacement = secrets.token_urlsafe(32)
        await _reset_credential(w, replacement)
        async with w.session() as db:
            epoch = await db.scalar(text("SELECT credential_epoch FROM users WHERE id=:u"), {"u": w.actor})
        await bootstrap(w.schema, os.environ["DATABASE_URL"])
        await bootstrap(w.schema, os.environ["DATABASE_URL"])
        async with w.session() as db:
            assert await db.scalar(text("SELECT credential_epoch FROM users WHERE id=:u"), {"u": w.actor}) == epoch
            await db.execute(text(f'ALTER TABLE "{w.schema}".users DISABLE TRIGGER credential_epoch_monotonic'))
        try:
            with pytest.raises(RuntimeError, match="CREDENTIAL_EPOCH_GUARD_CONTRACT_MISMATCH"):
                await bootstrap(w.schema, os.environ["DATABASE_URL"])
        finally:
            async with w.session() as db:
                await db.execute(text(f'ALTER TABLE "{w.schema}".users ENABLE TRIGGER credential_epoch_monotonic'))
        assert (await _me(c, (await _identity(c, w, replacement))["access_token"])).status_code == 200
