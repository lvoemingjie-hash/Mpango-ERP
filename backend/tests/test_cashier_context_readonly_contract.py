"""Real JWT/PG contracts for the additive cashier read, not a writer replay.

Owner/bootstrap and stock use the existing task-owned StockWorld fixture.
Retailer/staff identities use production invitation/credential services, the
non-production email sink, and real login/select-tenant HTTP. No auth override,
self-signed JWT, manual permission grant, or business guard replacement.
Only explicitly damaged-history controls below write SQL business facts.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import secrets
from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
from sqlalchemy import event, text

from api.app import configure_app
from core.config import get_settings
from core.error_codes import register_exception_handlers
from services.email_delivery import get_dev_retailer_email_deliveries, get_dev_staff_email_deliveries
from services.invitation_service import InvitationService
from services.retailer_provisioning_service import RetailerProvisioningService
from services.staff_credential_service import StaffCredentialService
from services.staff_management_service import StaffManagementService
from tests.test_inventory_manual_adjustment_safety import StockWorld

pytestmark = pytest.mark.asyncio


def headers(token):
    return {"Authorization": "Bearer " + token}


def code(response):
    body = response.json()
    return body.get("code") or body.get("error", {}).get("code")


def retain(label, value):
    directory = os.environ.get("PARTY_CONTEXT_EVIDENCE_DIR")
    if directory:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (root / (label + "-" + uuid4().hex + ".json")).open("x") as handle:
            os.chmod(handle.name, 0o600)
            json.dump(value, handle, default=str, indent=2)
            handle.write("\n")


class ContextWorld:
    async def initialize(self):
        assert get_settings().MPANGO_ENV == "staging", "CONTEXT_REAL_JWT_PROFILE_REQUIRED"
        self.a, self.b = StockWorld(), StockWorld()
        await self.a.initialize(country="KE")
        await self.b.initialize(country="UG")
        app = FastAPI()
        configure_app(app, get_settings())
        register_exception_handlers(app)
        self.app = app
        self.http = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver",
                                headers={"X-Forwarded-For": "10.231.42.19"})
        self.owner, self.identity = await self.login(self.a.email, self.a.password, self.a)
        self.owner_b, _ = await self.login(self.b.email, self.b.password, self.b)
        self.ra = await self.retailer(self.a)
        self.ra2 = await self.retailer(self.a)
        self.rb = await self.retailer(self.b)
        self.read = await self.staff("finance", ["payments:read"])
        self.confirm = await self.staff("sales", ["payments:confirm_declaration"])
        return self

    async def login(self, email, password, tenant):
        response = await self.http.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        identity = response.json()["data"]["access_token"]
        response = await self.http.post("/api/v1/auth/select-tenant", json={"tenant_id": str(tenant.wid)},
                                        headers=headers(identity))
        assert response.status_code == 200, response.text
        return response.json()["data"]["access_token"], identity

    async def retailer(self, tenant):
        email = uuid4().hex + "@example.com"
        password = secrets.token_urlsafe(32)
        async with tenant.session() as db:
            invitation = await InvitationService().create_invitation(db, wholesaler_id=tenant.wid)
            result = await RetailerProvisioningService(db).register_with_invitation(
                invitation_code=invitation.code, phone="+254" + str(uuid4().int)[:12],
                name="Retailer", email=email)
            rid, uid, bid = result.retailer.id, result.binding.tenant_user_id, result.binding.id
        deliveries = get_dev_retailer_email_deliveries(email)
        assert len(deliveries) == 1
        response = await self.http.post("/api/v1/retailers/setup-credential", json={
            "setup_token": deliveries[0].token, "new_password": password})
        assert response.status_code == 200, response.text
        response = await self.http.post("/api/v1/client/auth/login", json={
            "email": email, "password": password, "wholesaler_code": tenant.code})
        assert response.status_code == 200, response.text
        return {"id": rid, "uid": uid, "binding": bid, "token": response.json()["data"]["tokens"]["access_token"]}

    async def staff(self, template, permissions):
        email, password = uuid4().hex + "@example.com", secrets.token_urlsafe(32)
        async with self.a.session() as db:
            service = StaffManagementService(db, self.a.wid, self.a.schema)
            current = next(item for item in await service.templates(self.a.actor) if item["key"] == template)
            await service.edit_template(self.a.actor, template, permissions, current["version"])
            member = await service.create_member(self.a.actor, email=email, full_name="Context control",
                                                 template_key=template, create_key=uuid4().hex)
            uid = UUID(member["id"])
            await StaffCredentialService(db).invite(tenant_id=self.a.wid, schema=self.a.schema,
                actor_id=self.a.actor, user_id=uid, owner_password=self.a.password, expected_version=member["version"])
        delivery = get_dev_staff_email_deliveries(email)
        assert len(delivery) == 1
        response = await self.http.post("/api/v1/auth/staff/setup-credential", json={
            "setup_token": delivery[0].token, "password": password})
        assert response.status_code == 200, response.text
        token, _ = await self.login(email, password, self.a)
        return {"id": uid, "token": token, "template": template}

    async def order(self, *, tenant=None, retailer=None, total="100.25", declare="25.15", method="cash"):
        tenant = tenant or self.a
        retailer = retailer or self.ra
        owner = self.owner if tenant is self.a else self.owner_b
        async with tenant.session() as db:
            revision = await db.scalar(text("SELECT pricing_revision FROM skus WHERE id=:id"), {"id": tenant.sku})
        response = await self.http.put("/api/v1/pricing/base-prices/" + str(tenant.sku), headers=headers(owner),
                                      json={"price": total, "expected_revision": revision})
        assert response.status_code == 200, response.text
        body = {"retailer_id": str(retailer["id"]), "items": [{"sellable_unit_id": str(tenant.sku), "quantity": 1}]}
        response = await self.http.post("/api/v1/orders/quote", json=body, headers=headers(owner))
        assert response.status_code == 200, response.text
        body["quote_token"] = response.json()["data"]["quote_token"]
        response = await self.http.post("/api/v1/orders", json=body,
                                       headers={**headers(owner), "X-Idempotency-Key": uuid4().hex})
        assert response.status_code == 201, response.text
        oid = response.json()["data"]["id"]
        response = await self.http.post(f"/api/v1/orders/{oid}/confirm", headers=headers(owner))
        assert response.status_code == 200, response.text
        declaration = {"declared_amount": declare, "method": method}
        if method == "transfer":
            declaration["transfer_reference"] = uuid4().hex
        response = await self.http.post(f"/api/v1/client/orders/{oid}/declare", json=declaration,
            headers={**headers(retailer["token"]), "X-Declaration-Idempotency-Key": uuid4().hex})
        assert response.status_code == 201, response.text
        return {"order": oid, "declaration": response.json()["data"]["id"], "tenant": tenant, "retailer": retailer}

    async def pay(self, case, amount, method="cash"):
        owner = self.owner if case["tenant"] is self.a else self.owner_b
        body = {"amount": amount, "method": method}
        if method == "transfer":
            body["transaction_id"] = uuid4().hex
        response = await self.http.post(f'/api/v1/orders/{case["order"]}/pay', json=body,
            headers={**headers(owner), "X-Idempotency-Key": uuid4().hex})
        assert response.status_code == 200, response.text
        return response

    async def vector(self, tenant):
        vector = {}
        async with tenant.session() as db:
            for table in ("orders", "payments", "order_credit_holds", "payment_declarations", "ledger_entries", "receipt_sequences"):
                vector[table] = list((await db.execute(text(
                    f'SELECT row_to_json(t)::text FROM "{tenant.schema}"."{table}" t ORDER BY row_to_json(t)::text'
                ))).scalars())
            vector["binding"] = list((await db.execute(text(
                'SELECT row_to_json(b)::text FROM public.wholesaler_retailer_bindings b WHERE wholesaler_id=:w ORDER BY id'
            ), {"w": tenant.wid})).scalars())
        assert vector["orders"] and vector["order_credit_holds"] and vector["payment_declarations"] and vector["binding"]
        return vector

    async def review(self, case, token=None, suffix=""):
        before = await self.vector(case["tenant"])
        response = await self.http.get(f'/api/v1/declarations/{case["declaration"]}/review-context' + suffix,
                                       headers=headers(token or self.owner))
        after = await self.vector(case["tenant"])
        retain("read-vector", {"before": before, "after": after, "http_status": response.status_code})
        assert before == after, "CONTEXT_GET_MUTATED_SEVEN_ECONOMIC_SURFACES"
        return response

    @asynccontextmanager
    async def damage(self, tenant, apply, restore, params):
        async with tenant.session() as db:
            await db.execute(text(apply), params)
        try:
            yield
        finally:
            async with tenant.session() as db:
                await db.execute(text(restore), params)


@pytest_asyncio.fixture(scope="module")
async def context_world():
    import subprocess
    from urllib.parse import urlparse
    endpoint = urlparse(os.environ["TEST_DATABASE_URL"])
    assert os.environ["DATABASE_URL"] == os.environ["TEST_DATABASE_URL"]
    assert endpoint.username == "mpango_app" and endpoint.hostname == "127.0.0.1"
    assert endpoint.path == "/test_mpango_cashier_context_20261029"
    cid = os.environ["CI_PG_CONTAINER_ID"]
    info = json.loads(subprocess.check_output(["docker", "inspect", cid]))[0]
    assert info["Id"] == cid and info["Image"] == os.environ["CONTEXT_PG_IMAGE_ID"]
    assert info["Config"]["Labels"]["mpango.task"] == os.environ["CI_TASK_LABEL"]
    assert info["Config"]["Labels"]["mpango.owner"] == os.environ["CI_OWNER_LABEL"]
    assert info["NetworkSettings"]["Ports"]["5432/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": str(endpoint.port)}]
    world = ContextWorld()
    try:
        yield await world.initialize()
    finally:
        if hasattr(world, "http"):
            await world.http.aclose()
        for tenant in (world.a, world.b):
            if hasattr(tenant, "engine"):
                await tenant.engine.dispose()


@pytest.mark.parametrize("method", ["cash", "transfer"])
async def test_pending_paid_total_and_no_declaration_double_count(context_world, method):
    world = context_world
    case = await world.order()
    await world.pay(case, "40.15", method)
    async with world.a.session() as db:
        from repositories.payment_repository import PaymentRepository
        paid = await PaymentRepository().get_order_paid_total(db, order_id=UUID(case["order"]))
        assert paid == Decimal("40.15")
        payment_status = await db.scalar(text("SELECT status FROM payments WHERE order_id=:o AND is_deleted IS FALSE"), {"o": UUID(case["order"])})
        assert payment_status == "pending", "PENDING_CONTROL_PRESTATE_NOT_ESTABLISHED"
    response = await world.review(case, world.read["token"])
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["money"]["balance_due"] == "60.10", "CONTEXT_PENDING_PAYMENT_NOT_COUNTED"
    assert data["declaration"]["declared_amount"] == "25.15"
    assert data["review_state"] == "READY" and data["reason_codes"] == []
    async with world.a.session() as db:
        await db.execute(text("UPDATE payment_declarations SET status='confirmed' WHERE id=:d"), {"d": UUID(case["declaration"])})
    response = await world.review(case)
    assert response.json()["data"]["money"]["balance_due"] == "60.10"
    assert response.json()["data"]["review_state"] == "NOT_ACTIONABLE"


async def test_read_only_does_not_inherit_invoice_or_confirm(context_world):
    world = context_world
    case = await world.order()
    assert (await world.review(case, world.read["token"])).status_code == 200
    for path in (f'/api/v1/orders/{case["order"]}/invoice', f'/api/v1/declarations/{case["declaration"]}/confirm'):
        response = await (world.http.get(path, headers=headers(world.read["token"])) if path.endswith("invoice")
                          else world.http.post(path, headers=headers(world.read["token"])))
        assert (response.status_code, code(response)) == (403, "PERMISSION_DENIED")
    response = await world.review(case, world.confirm["token"])
    assert (response.status_code, code(response)) == (403, "PERMISSION_DENIED")


async def test_identity_retailer_and_current_mixed_audience(context_world):
    world = context_world
    case = await world.order()
    for token, expected in ((world.identity, "TENANT_CONTEXT_REQUIRED"), (world.ra["token"], "PERMISSION_DENIED")):
        response = await world.review(case, token)
        assert (response.status_code, code(response)) == (403, expected)
    # A deliberately damaged legacy mixed audience, using the production role
    # helper rather than SQL granting permissions. The JWT predates this role.
    async with world.a.session() as db:
        await RetailerProvisioningService(db)._grant_retailer_operator(tenant_schema=world.a.schema, user_id=world.a.actor)
    try:
        response = await world.review(case)
        assert (response.status_code, code(response)) == (403, "PERMISSION_DENIED")
    finally:
        async with world.a.session() as db:
            await db.execute(text("DELETE FROM user_roles WHERE user_id=:u AND role_id IN (SELECT id FROM roles WHERE name='retailer_operator')"), {"u": world.a.actor})


@pytest.mark.parametrize("selector", ["retailer_id", "wholesaler_id", "order_id", "binding_id", "schema"])
async def test_no_query_selection(context_world, selector):
    world = context_world
    case = await world.order()
    response = await world.review(case, suffix=f"?{selector}={uuid4()}")
    assert (response.status_code, code(response)) == (400, "INVALID_CONTEXT_SELECTOR")


async def test_cross_tenant_and_attribution_neutral(context_world):
    world = context_world
    case = await world.order()
    foreign = await world.order(tenant=world.b, retailer=world.rb, total="10000", declare="2500")
    response = await world.review(foreign)
    assert (response.status_code, code(response)) == (404, "DECLARATION_NOT_FOUND")
    async with world.damage(world.a, "UPDATE payment_declarations SET retailer_id=:other WHERE id=:d",
                            "UPDATE payment_declarations SET retailer_id=:original WHERE id=:d",
                            {"other": world.ra2["id"], "original": world.ra["id"], "d": UUID(case["declaration"])}):
        response = await world.review(case)
        assert (response.status_code, code(response)) == (404, "DECLARATION_NOT_FOUND")
    for value in ("not-a-uuid", str(uuid4())):
        response = await world.http.get(f"/api/v1/declarations/{value}/review-context", headers=headers(world.owner))
        assert (response.status_code, code(response)) == (404, "DECLARATION_NOT_FOUND")


@pytest.mark.parametrize("name", [None, "   "])
async def test_missing_name_never_ready(context_world, name):
    world = context_world
    case = await world.order()
    async with world.damage(world.a, "UPDATE public.retailers SET name=:missing WHERE id=:r",
                            "UPDATE public.retailers SET name='Retailer' WHERE id=:r",
                            {"missing": name, "r": world.ra["id"]}):
        response = await world.review(case)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["retailer"]["name_resolution"] == "MISSING", "CONTEXT_MISSING_NAME_FALSELY_RESOLVED"
        assert data["retailer"]["name"] is None
        assert data["review_state"] == "UNRESOLVED" and data["reason_codes"] == ["NAME_UNRESOLVED"]


async def test_literal_party_names_and_statement_observation(context_world):
    world = context_world
    case = await world.order()
    async with world.a.session() as db:
        original = await db.scalar(text("SELECT name FROM public.wholesalers WHERE id=:w"), {"w": world.a.wid})
    async with world.damage(world.a, "UPDATE public.wholesalers SET name='Supplier' WHERE id=:w",
                            "UPDATE public.wholesalers SET name=:old WHERE id=:w", {"w": world.a.wid, "old": original}):
        start = datetime.now(timezone.utc)
        response = await world.review(case)
        end = datetime.now(timezone.utc)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["supplier"]["name"] == "Supplier" and data["retailer"]["name"] == "Retailer"
        assert data["supplier"]["name_resolution"] == data["retailer"]["name_resolution"] == "RESOLVED"
        assert data["review_state"] == "READY"
        observed = datetime.fromisoformat(data["observed_at"].replace("Z", "+00:00"))
        assert start <= observed <= end


async def test_ugx_zero_and_credit_not_cash(context_world):
    world = context_world
    case = await world.order(tenant=world.b, retailer=world.rb, total="10000", declare="2500")
    await world.pay(case, "10000", "credit")
    response = await world.review(case, world.owner_b)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["money"]["balance_due"] == "10000"
    await world.pay(case, "10000", "transfer")
    response = await world.review(case, world.owner_b)
    data = response.json()["data"]
    assert data["money"] == {"currency": "UGX", "currency_status": "KNOWN", "balance_due": "0", "balance_status": "VERIFIED"}
    assert data["review_state"] == "NOT_ACTIONABLE" and data["reason_codes"] == ["NO_REMAINING_BALANCE"]


async def test_kes_zero_and_nonaction_priority(context_world):
    world = context_world
    case = await world.order(total="100.00", declare="80.00")
    await world.pay(case, "100.00")
    response = await world.review(case)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["money"]["balance_due"] == "0.00" and data["money"]["balance_status"] == "VERIFIED"
    assert data["reason_codes"] == ["NO_REMAINING_BALANCE"]
    async with world.damage(world.a, "UPDATE public.retailers SET name=NULL WHERE id=:r",
                            "UPDATE public.retailers SET name='Retailer' WHERE id=:r", {"r": world.ra["id"]}):
        response = await world.review(case)
        assert response.json()["data"]["review_state"] == "NOT_ACTIONABLE"
        assert response.json()["data"]["reason_codes"] == ["NO_REMAINING_BALANCE", "NAME_UNRESOLVED"]


async def test_terminal_states_do_not_invent_current_balance(context_world):
    world = context_world
    case = await world.order()
    # These are deliberately inconsistent legacy shapes, not normal writers.
    # No CHECK is removed and no monetary/permission writer is altered.
    for state in ("draft", "cancelled", "voided", "returned"):
        async with world.damage(world.a, "UPDATE orders SET status=CAST(:state AS order_status) WHERE id=:o",
                                "UPDATE orders SET status='confirmed' WHERE id=:o", {"state": state, "o": UUID(case["order"])}):
            response = await world.review(case)
            assert response.status_code == 200, response.text
            data = response.json()["data"]
            assert data["review_state"] == "NOT_ACTIONABLE" and data["money"]["balance_due"] is None
            assert data["money"]["balance_status"] == "UNVERIFIED"
            assert data["reason_codes"] == ["ORDER_STATE_NOT_REVIEWABLE"]


async def test_one_statement_and_no_business_row_locks(context_world):
    world = context_world
    case = await world.order()
    from database.session import async_engine
    captured = []

    def observe(_connection, _cursor, statement, _params, _context, _many):
        captured.append(statement)

    event.listen(async_engine.sync_engine, "before_cursor_execute", observe)
    try:
        response = await world.review(case)
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", observe)
    assert response.status_code == 200, response.text
    projections = [statement for statement in captured if "AS declaration_id" in statement]
    assert len(projections) == 1 and "statement_timestamp()" in projections[0]
    assert not [statement for statement in captured if "FOR UPDATE" in statement.upper()]
    assert not [statement for statement in captured if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}]
    retain("read-sql", captured)


async def test_null_currency_and_transfer_reference_are_unresolved(context_world):
    world = context_world
    case = await world.order(method="transfer")
    ids = {"o": UUID(case["order"]), "d": UUID(case["declaration"])}
    async with world.a.session() as db:
        before_order = dict((await db.execute(text("SELECT * FROM orders WHERE id=:o"), ids)).mappings().one())
        before_declaration = dict((await db.execute(text("SELECT * FROM payment_declarations WHERE id=:d"), ids)).mappings().one())
    assert before_order["id"] == before_declaration["order_id"] == ids["o"]
    assert before_declaration["id"] == ids["d"]
    assert before_order["wholesaler_id"] == before_declaration["wholesaler_id"] == world.a.wid
    assert before_order["retailer_id"] == before_declaration["retailer_id"] == case["retailer"]["id"]
    fields = ("currency_snapshot", "creation_key_digest", "creation_fingerprint", "creation_operation")
    assert all(before_order[field] is not None for field in fields)
    assert before_declaration["transfer_reference"]
    expected_order = {**before_order, **dict.fromkeys(fields)}
    expected_declaration = {**before_declaration, "transfer_reference": None}
    retain("legacy-original", {"order": before_order, "declaration": before_declaration})
    try:
        async with world.a.session() as db:
            changed_order = (await db.execute(text(
                "UPDATE orders SET currency_snapshot=NULL, creation_key_digest=NULL, "
                "creation_fingerprint=NULL, creation_operation=NULL WHERE id=:o RETURNING id"
            ), ids)).scalar_one()
            changed_declaration = (await db.execute(text(
                "UPDATE payment_declarations SET transfer_reference=NULL WHERE id=:d RETURNING id"
            ), ids)).scalar_one()
            assert changed_order == ids["o"] and changed_declaration == ids["d"]
        # StockWorld uses NullPool: this is a new connection after commit.
        async with world.a.session() as db:
            legacy_order = dict((await db.execute(text("SELECT * FROM orders WHERE id=:o"), ids)).mappings().one())
            legacy_declaration = dict((await db.execute(text("SELECT * FROM payment_declarations WHERE id=:d"), ids)).mappings().one())
        assert legacy_order == expected_order and legacy_declaration == expected_declaration
        retain("legacy-committed", {"order": legacy_order, "declaration": legacy_declaration})
        response = await world.review(case)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["money"]["currency"] is data["money"]["balance_due"] is None
        assert data["money"]["balance_status"] == "UNVERIFIED"
        assert data["reason_codes"] == ["CURRENCY_UNVERIFIED", "TRANSFER_REFERENCE_MISSING"]
        assert data["review_state"] == "UNRESOLVED"
    finally:
        async with world.a.session() as db:
            restored_order_id = (await db.execute(text(
                "UPDATE orders SET currency_snapshot=:currency, creation_key_digest=:key, "
                "creation_fingerprint=:fingerprint, creation_operation=:operation WHERE id=:o RETURNING id"
            ), {**ids, "currency": before_order["currency_snapshot"], "key": before_order["creation_key_digest"],
                "fingerprint": before_order["creation_fingerprint"], "operation": before_order["creation_operation"]})).scalar_one()
            restored_declaration_id = (await db.execute(text(
                "UPDATE payment_declarations SET transfer_reference=:reference WHERE id=:d RETURNING id"
            ), {**ids, "reference": before_declaration["transfer_reference"]})).scalar_one()
            assert restored_order_id == ids["o"] and restored_declaration_id == ids["d"]
        async with world.a.session() as db:
            restored_order = dict((await db.execute(text("SELECT * FROM orders WHERE id=:o"), ids)).mappings().one())
            restored_declaration = dict((await db.execute(text("SELECT * FROM payment_declarations WHERE id=:d"), ids)).mappings().one())
        retain("legacy-restored", {"order": restored_order, "declaration": restored_declaration,
                                  "order_matches": restored_order == before_order,
                                  "declaration_matches": restored_declaration == before_declaration})
        assert restored_order == before_order and restored_declaration == before_declaration, "CONTEXT_LEGACY_EXACT_RESTORATION_FAILED"


@pytest.mark.parametrize("damage", ["hold", "history", "negative", "precision"])
async def test_bad_history_or_hold_is_not_a_green_label(context_world, damage):
    world = context_world
    case = await world.order()
    await world.pay(case, "40.15")
    if damage == "hold":
        apply, restore = "UPDATE order_credit_holds SET remaining_amount=1 WHERE order_id=:o", "UPDATE order_credit_holds SET remaining_amount=60.10 WHERE order_id=:o"
    elif damage == "history":
        apply, restore = "UPDATE payments SET retailer_id=:other WHERE order_id=:o", "UPDATE payments SET retailer_id=:original WHERE order_id=:o"
    elif damage == "negative":
        apply, restore = "UPDATE payments SET amount=101 WHERE order_id=:o", "UPDATE payments SET amount=40.15 WHERE order_id=:o"
    else:
        # UGX precision damage is representable without removing any CHECK.
        apply, restore = "UPDATE orders SET currency_snapshot='UGX' WHERE id=:o", "UPDATE orders SET currency_snapshot='KES' WHERE id=:o"
    async with world.damage(world.a, apply, restore, {"o": UUID(case["order"]), "other": world.ra2["id"], "original": world.ra["id"]}):
        response = await world.review(case)
        assert response.status_code == 409
        assert code(response) == ("PAYMENT_HISTORY_INTEGRITY" if damage == "history" else "REVIEW_CONTEXT_INTEGRITY")


async def test_concurrent_payment_does_not_turn_review_into_permission(context_world):
    world = context_world
    case = await world.order(total="100.00", declare="80.00")
    payment_entered, read_finished = asyncio.Event(), asyncio.Event()
    from services.canonical_payment_service import CanonicalPaymentService
    original = CanonicalPaymentService._confirm_payment_for_locked_order

    async def barrier(service, *args, **kwargs):
        payment_entered.set()
        await asyncio.wait_for(read_finished.wait(), 10)
        return await original(service, *args, **kwargs)

    # Instrument the real writer only to hold its existing order lock. Neither
    # read nor writer return/validation is mocked or replaced.
    from unittest.mock import patch
    with patch.object(CanonicalPaymentService, "_confirm_payment_for_locked_order", barrier):
        payment = asyncio.create_task(world.pay(case, "60.00"))
        try:
            await asyncio.wait_for(payment_entered.wait(), 10)
            response = await world.review(case)
            assert response.status_code == 200 and response.json()["data"]["review_state"] == "READY"
        finally:
            read_finished.set()
            await asyncio.wait_for(payment, 10)
    before = await world.vector(world.a)
    response = await world.http.post(f'/api/v1/declarations/{case["declaration"]}/confirm', headers=headers(world.owner))
    assert (response.status_code, code(response)) == (400, "PAYMENT_EXCEEDS_REMAINING")
    assert before == await world.vector(world.a), "STALE_REVIEW_ALLOWED_OVERCOLLECTION"


async def test_service_statement_and_read_only_seams():
    import ast
    from services import party_context_service as service
    source = Path(service.__file__).read_text()
    tree = ast.parse(source)
    for name in ("read_cashier_declaration_context", "read_client_portal_context"):
        function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == name)
        assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute" for node in ast.walk(function)) == 1
    assert "FOR UPDATE" not in source and "FOR SHARE" not in source
    assert not {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)} & {"commit", "flush", "add", "delete"}
    assert "float" not in source
