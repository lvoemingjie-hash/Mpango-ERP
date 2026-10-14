"""Fresh synthetic registrations via the real provisioner and minimum app role."""
import os
import secrets
import uuid

import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

@pytest_asyncio.fixture
async def r1_client():
    """Exercise the configured native strategy without replacing auth.factory.

    A fresh configured application selects JWT through the real staging factory,
    matching the S2 TCP boundary. Synthetic S1 world tokens remain
    fixture inputs, not evidence of the separate product registration journey.
    """
    from api.app import configure_app
    from core.config import get_settings
    from core.error_codes import register_exception_handlers
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    app = FastAPI()
    previous_env = os.environ.get("MPANGO_ENV")
    try:
        os.environ["MPANGO_ENV"] = "staging"
        configure_app(app, get_settings())
    finally:
        if previous_env is None:
            os.environ.pop("MPANGO_ENV", None)
        else:
            os.environ["MPANGO_ENV"] = previous_env
    register_exception_handlers(app)

    ip_hex = uuid.uuid4().int
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver",
        headers={"Content-Type": "application/json",
                 "X-Forwarded-For": f"10.{(ip_hex >> 16) & 0xFF}.{(ip_hex >> 8) & 0xFF}.{ip_hex & 0xFF}"},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def world(request):
    from core.security import create_contextual_token, hash_password
    from db.tenant_filter import mark_session_as_system
    from services.tenant_provisioning_service import TenantProvisioningService
    country = getattr(request, "param", "KE")
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"].replace(
        "postgresql://", "postgresql+asyncpg://"), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    reg, retailer, actor, customer = (uuid.uuid4() for _ in range(4))
    code = "S1" + uuid.uuid4().hex[:14].upper()
    async with factory() as db:
        mark_session_as_system(db, reason="S1 synthetic task registration")
        await db.execute(text(
            "INSERT INTO public.tenant_registrations "
            "(id, company_name, tenant_code, country, owner_email, status, expires_at, email_verified_at) "
            "VALUES (:id, 'S1 fixture', :code, :country, :email, 'email_verified', now()+interval '1 day', now())"
        ), {"id": reg, "code": code, "country": country, "email": code.lower() + "@example.com"})
        await db.commit()
        service = TenantProvisioningService(db)
        claim = await service.claim_registration_for_provisioning(str(reg))
        assert claim.action == "claimed", "S1_REGISTRATION_CLAIM"
        await db.commit()
        result = await service.provision_wholesaler_and_schema(str(reg))
        assert result.action == "provisioned", "S1_REAL_PROVISIONER"
        await db.commit()
        registration = (await db.execute(text(
            "SELECT wholesaler_id, tenant_schema FROM public.tenant_registrations WHERE id=:id"
        ), {"id": reg})).one()
        schema = registration.tenant_schema
        wid = registration.wholesaler_id
        from services.owner_credential_service import OwnerCredentialSetupService
        owner = OwnerCredentialSetupService(db)
        issued = await owner.issue_setup_token(reg)
        assert issued.action == "issued", "S1_REAL_OWNER_SETUP_ISSUED"
        owner_password, customer_password = (secrets.token_urlsafe(32) for _ in range(2))
        consumed = await owner.consume_setup_token(issued.raw_token, owner_password)
        created = await owner.create_first_admin_rbac(consumed)
        actor = created.user_id
        for uid, role in ((customer, "retailer_operator"),):
            await db.execute(text(
                f'INSERT INTO "{schema}".users (id,email,password_hash,full_name,is_active) '
                "VALUES (:id,:email,:hash,'S1 fixture',true)"
            ), {"id": uid, "email": uid.hex + "@example.com",
                "hash": hash_password(customer_password)})
            await db.execute(text(
                f'INSERT INTO "{schema}".user_roles (user_id,role_id) '
                f'SELECT :id,id FROM "{schema}".roles WHERE name=:role'
            ), {"id": uid, "role": role})
        await db.execute(text("INSERT INTO public.retailers (id,phone,name) VALUES (:id,:phone,'S1 customer')"),
                         {"id": retailer, "phone": "+256" + str(uuid.uuid4().int)[:12]})
        await db.execute(text(
            "INSERT INTO public.wholesaler_retailer_bindings "
            "(wholesaler_id,retailer_id,tenant_user_id,status,outstanding_balance) VALUES (:wid,:rid,:uid,'active',0)"
        ), {"wid": wid, "rid": retailer, "uid": customer})
        product = (await db.execute(text(
            f'INSERT INTO "{schema}".catalog_products (name,is_active) VALUES (\'S1 boxes\',true) RETURNING id'
        ))).scalar_one()
        sku = (await db.execute(text(
            f'INSERT INTO "{schema}".skus (sku_code,name,unit,package_quantity,catalog_product_id,is_active,base_price) '
            "VALUES ('BOX','S1 boxes','Box',12,:pid,true,90) RETURNING id"
        ), {"pid": product})).scalar_one()
        await db.execute(text(
            f'INSERT INTO "{schema}".inventory_stocks (sku_id,quantity_on_hand) VALUES (:sid,100)'
        ), {"sid": sku})
        await db.commit()

    def session():
        db = factory()
        db.info.update(tenant_schema=schema, tenant_id=str(wid))
        @event.listens_for(db.sync_session, "after_begin")
        def tenant_path(_session, _transaction, connection):
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
        return db

    yield {"schema": schema, "wid": str(wid), "rid": str(retailer), "actor": str(actor),
           "customer": str(customer), "sku": str(sku), "product": str(product), "session": session,
           "token": create_contextual_token(str(actor), ["admin"], str(wid), schema),
           "client_token": create_contextual_token(str(customer), ["retailer_operator"], str(wid), schema),
           "currency": "UGX" if country == "UG" else "KES", "tenant_code": code,
           "owner_email": code.lower() + "@example.com", "owner_password": owner_password,
           "customer_email": customer.hex + "@example.com", "customer_password": customer_password}
    from database.session import async_engine
    await async_engine.dispose()
    await engine.dispose()
