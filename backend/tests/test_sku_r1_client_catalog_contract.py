"""DC-12R1-MVP-L1-SKU-R0-M1-R1-R1 — product-level client catalog HTTP contract.

Runs the REAL FastAPI app (JWT retailer identity) against real PostgreSQL 16,
reusing the S2/S3 tenant-provisioning infrastructure.

Contract proven end-to-end over HTTP:

- R1-LIST-1  one product object per CatalogProduct; active packaging units
             nested with their own sellable_unit_id / price / stock / can_order
- R1-LIST-2  pagination counts PRODUCTS (never SKUs); stable product order
- R1-DETAIL-1 GET /client/products/{catalog_product_id} returns the product
             container with its units
- R1-DETAIL-2 the old ambiguity is REMOVED: a sellable-unit UUID as the path
             id is a clean 404 PRODUCT_NOT_FOUND (it used to be interpreted
             as the product)
- R1-VIS-1   inactive units are hidden; products whose units are all inactive
             disappear from the list
- R1-VIS-2   an inactive product is 404 PRODUCT_INACTIVE on detail
- R1-ISO-1   retailer-specific pricing: only the bound retailer's price is
             visible; unpriced units are can_order=false
- R1-ORD-1   deterministic unit ordering inside the container
"""

from __future__ import annotations

import uuid
from http import HTTPStatus
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import configure_app
from auth.strategies.jwt import JwtAuthStrategy
from core.config import get_settings
from core.error_codes import register_exception_handlers

from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: F401
    provisioned_pool,
    s2_clean_db,
    two_tenants,
)
from tests.test_dc12r1_s3_s1_catalog_order_hardening import (
    _resolve_binding,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _reset_shared_engine_pool():
    from database.session import async_engine
    yield
    await async_engine.dispose()


@pytest_asyncio.fixture
async def r1_client():
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


# ---------------------------------------------------------------------------
# Seeding helpers (test infrastructure; ids committed through the fixture db)
# ---------------------------------------------------------------------------


async def _seed_product(
    db,
    schema: str,
    retailer_id: str,
    *,
    name: str,
    units: list[dict],
    price: str = "25.50",
    stock: int = 100,
    is_active: bool = True,
) -> str:
    """Insert a CatalogProduct with units (each: sku_code/unit/package_quantity/
    is_active) + stock rows + a retailer-specific price. Returns product id."""
    product = (
        await db.execute(
            text(
                f'INSERT INTO "{schema}".catalog_products (name, category, is_active, is_deleted) '
                "VALUES (:name, 'staples', :active, false) RETURNING id"
            ),
            {"name": name, "active": is_active},
        )
    ).fetchone()
    product_id = str(product.id)
    for spec in units:
        unit = (
            await db.execute(
                text(
                    f'INSERT INTO "{schema}".skus '
                    "(sku_code, name, unit, package_quantity, is_active, is_deleted, catalog_product_id) "
                    "VALUES (:code, :name, :unit, :qty, :active, false, :pid) RETURNING id"
                ),
                {
                    "code": spec["sku_code"],
                    "name": name,
                    "unit": spec.get("unit", "bottle"),
                    "qty": spec.get("package_quantity", "1.000"),
                    "active": spec.get("is_active", True),
                    "pid": product_id,
                },
            )
        ).fetchone()
        unit_id = str(unit.id)
        await db.execute(
            text(
                f'INSERT INTO "{schema}".inventory_stocks (sku_id, quantity_on_hand, is_deleted) '
                "VALUES (:s, :q, false)"
            ),
            {"s": unit_id, "q": spec.get("stock", stock)},
        )
        unit_price = spec.get("price", price)
        if spec.get("is_active", True) and unit_price is not None:
            await db.execute(
                text(
                    f'INSERT INTO "{schema}".retailer_prices (sku_id, retailer_id, price, is_deleted) '
                    "VALUES (:s, :r, :p, false)"
                ),
                {"s": unit_id, "r": retailer_id, "p": unit_price},
            )
    await db.commit()
    return product_id


async def _login_retailer(client: AsyncClient, two_tenants) -> str:
    code_a, _b, _sb, email, password, _a, _b2 = two_tenants
    resp = await client.post(
        "/api/v1/client/auth/login",
        json={"email": email, "password": password, "wholesaler_code": code_a},
    )
    assert resp.status_code == HTTPStatus.OK, resp.text
    return resp.json()["data"]["tokens"]["access_token"]


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


class TestProductLevelList:
    async def test_one_container_per_product_with_nested_units(
        self, r1_client, two_tenants, s2_clean_db
    ):
        db, _reg = s2_clean_db
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, two_tenants[5])
        name = f"R1HTTP Multi {uuid.uuid4().hex[:6].upper()}"
        product_id = await _seed_product(
            db, sch_a, ret_a,
            name=name,
            units=[
                {"sku_code": f"RH1-{name[-6:]}-BTL", "unit": "bottle", "package_quantity": "1.000"},
                {"sku_code": f"RH1-{name[-6:]}-CASE", "unit": "case", "package_quantity": "12.000"},
            ],
        )
        token = await _login_retailer(r1_client, two_tenants)
        resp = await r1_client.get(
            "/api/v1/client/products",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == HTTPStatus.OK, resp.text
        items = resp.json()["data"]["items"]
        mine = [i for i in items if i["name"] == name]
        assert len(mine) == 1, "exactly ONE customer product object per CatalogProduct"
        container = mine[0]
        assert container["id"] == product_id, "container id is the CatalogProduct.id"
        assert container["unit_count"] == 2
        assert [u["sku_code"] for u in container["units"]] == [
            f"RH1-{name[-6:]}-BTL",
            f"RH1-{name[-6:]}-CASE",
        ], "active packaging choices nested in deterministic (qty, code) order"
        unit = container["units"][0]
        assert unit["sellable_unit_id"] and unit["price"] == "25.50"
        assert unit["in_stock"] is True and unit["can_order"] is True
        assert container["in_stock"] is True and container["can_order"] is True

    async def test_pagination_counts_products_not_units(
        self, r1_client, two_tenants, s2_clean_db
    ):
        db, _reg = s2_clean_db
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, two_tenants[5])
        run = uuid.uuid4().hex[:6].upper()
        for idx in range(3):
            await _seed_product(
                db, sch_a, ret_a,
                name=f"R1HTTP Page {run} {idx}",
                units=[{"sku_code": f"RHP{run}-{idx}", "unit": "bottle"}],
            )
        token = await _login_retailer(r1_client, two_tenants)

        page1 = await r1_client.get(
            "/api/v1/client/products",
            params={"page": 1, "size": 2, "search": f"R1HTTP Page {run}"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert page1.status_code == HTTPStatus.OK, page1.text
        data1 = page1.json()["data"]
        assert data1["pagination"]["total"] == 3, "pagination total counts PRODUCTS"
        assert data1["pagination"]["pages"] == 2
        assert len(data1["items"]) == 2
        names1 = [i["name"] for i in data1["items"]]
        assert names1 == [f"R1HTTP Page {run} {idx}" for idx in (0, 1)], (
            "deterministic product order (name ASC, id ASC)"
        )

        page2 = await r1_client.get(
            "/api/v1/client/products",
            params={"page": 2, "size": 2, "search": f"R1HTTP Page {run}"},
            headers={"Authorization": f"Bearer {token}"},
        )
        data2 = page2.json()["data"]
        assert len(data2["items"]) == 1

    async def test_search_by_unit_sku_code_finds_the_product(
        self, r1_client, two_tenants, s2_clean_db
    ):
        db, _reg = s2_clean_db
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, two_tenants[5])
        code = f"RHSRCH-{uuid.uuid4().hex[:8].upper()}"
        await _seed_product(
            db, sch_a, ret_a,
            name=f"R1HTTP Search {code}",
            units=[{"sku_code": code, "unit": "bottle"}],
        )
        token = await _login_retailer(r1_client, two_tenants)
        resp = await r1_client.get(
            "/api/v1/client/products",
            params={"search": code},
            headers={"Authorization": f"Bearer {token}"},
        )
        items = resp.json()["data"]["items"]
        mine = [i for i in items if i["units"][0]["sku_code"] == code]
        assert len(mine) == 1


class TestProductLevelDetail:
    async def test_detail_by_catalog_product_id_returns_units(
        self, r1_client, two_tenants, s2_clean_db
    ):
        db, _reg = s2_clean_db
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, two_tenants[5])
        run = uuid.uuid4().hex[:6].upper()
        product_id = await _seed_product(
            db, sch_a, ret_a,
            name=f"R1HTTP Detail {run}",
            units=[
                {"sku_code": f"RHD{run}-BTL", "unit": "bottle", "package_quantity": "1.000"},
                {"sku_code": f"RHD{run}-CASE", "unit": "case", "package_quantity": "12.000"},
            ],
        )
        token = await _login_retailer(r1_client, two_tenants)
        resp = await r1_client.get(
            f"/api/v1/client/products/{product_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == HTTPStatus.OK, resp.text
        detail = resp.json()["data"]
        assert detail["id"] == product_id
        assert detail["description"] is None
        assert len(detail["units"]) == 2
        assert [u["sku_code"] for u in detail["units"]] == [f"RHD{run}-BTL", f"RHD{run}-CASE"]

    async def test_detail_with_sellable_unit_uuid_is_404_not_the_product(
        self, r1_client, two_tenants, s2_clean_db
    ):
        """The OLD contract answered GET /client/products/{sku_id} with the
        product — the ambiguity is removed: a unit UUID is NOT a product id."""
        db, _reg = s2_clean_db
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, two_tenants[5])
        run = uuid.uuid4().hex[:6].upper()
        product_id = await _seed_product(
            db, sch_a, ret_a,
            name=f"R1HTTP Amb {run}",
            units=[{"sku_code": f"RHA{run}-BTL", "unit": "bottle"}],
        )
        unit_id_row = (
            await db.execute(
                text(f'SELECT id FROM "{sch_a}".skus WHERE catalog_product_id = :p'),
                {"p": product_id},
            )
        ).fetchone()
        unit_id = str(unit_id_row.id)
        token = await _login_retailer(r1_client, two_tenants)

        ok_resp = await r1_client.get(
            f"/api/v1/client/products/{product_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ok_resp.status_code == HTTPStatus.OK
        amb_resp = await r1_client.get(
            f"/api/v1/client/products/{unit_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert amb_resp.status_code == HTTPStatus.NOT_FOUND, amb_resp.text
        assert amb_resp.json()["code"] == "PRODUCT_NOT_FOUND"

        malformed = await r1_client.get(
            "/api/v1/client/products/not-a-uuid",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert malformed.status_code == HTTPStatus.NOT_FOUND

    async def test_inactive_product_detail_is_product_inactive_404(
        self, r1_client, two_tenants, s2_clean_db
    ):
        db, _reg = s2_clean_db
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, two_tenants[5])
        run = uuid.uuid4().hex[:6].upper()
        product_id = await _seed_product(
            db, sch_a, ret_a,
            name=f"R1HTTP Inactive {run}",
            units=[{"sku_code": f"RHI{run}-BTL", "unit": "bottle"}],
            is_active=False,
        )
        token = await _login_retailer(r1_client, two_tenants)
        listed = await r1_client.get(
            "/api/v1/client/products",
            params={"search": f"R1HTTP Inactive {run}"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert listed.json()["data"]["items"] == [], "inactive product must not be listed"
        detail = await r1_client.get(
            f"/api/v1/client/products/{product_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail.status_code == HTTPStatus.NOT_FOUND
        assert detail.json()["code"] == "PRODUCT_INACTIVE"


class TestIsolationAndVisibility:
    async def test_inactive_units_hidden_and_unpriced_units_not_orderable(
        self, r1_client, two_tenants, s2_clean_db
    ):
        db, _reg = s2_clean_db
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, two_tenants[5])
        run = uuid.uuid4().hex[:6].upper()
        product_id = await _seed_product(
            db, sch_a, ret_a,
            name=f"R1HTTP Units {run}",
            units=[
                {"sku_code": f"RHU{run}-ACTIVE", "unit": "bottle", "is_active": True},
                {"sku_code": f"RHU{run}-OFF", "unit": "case", "is_active": False},
                {"sku_code": f"RHU{run}-NOPRICE", "unit": "box", "price": None},
            ],
        )
        token = await _login_retailer(r1_client, two_tenants)
        detail = await r1_client.get(
            f"/api/v1/client/products/{product_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail.status_code == HTTPStatus.OK
        units = detail.json()["data"]["units"]
        assert [u["sku_code"] for u in units] == [f"RHU{run}-ACTIVE", f"RHU{run}-NOPRICE"], (
            "inactive unit must be hidden from packaging choices"
        )
        priced = units[0]
        unpriced = units[1]
        assert priced["can_order"] is True
        assert unpriced["price"] is None and unpriced["can_order"] is False

    async def test_retailer_price_isolation(self, r1_client, two_tenants, s2_clean_db):
        db, _reg = s2_clean_db
        from tests.test_dc12r1_s2_supplier_scoped_retailer_login import _pool_instance

        ws_a = _pool_instance.tenants["a"]["ws_id"]
        sch_a = _pool_instance.tenants["a"]["schema"]
        ret_a = await _resolve_binding(db, ws_a, two_tenants[5])
        run = uuid.uuid4().hex[:6].upper()
        # stock 0 -> OUT_OF_STOCK for this retailer (no price rows either)
        product_id = await _seed_product(
            db, sch_a, ret_a,
            name=f"R1HTTP NoPrice {run}",
            units=[{"sku_code": f"RHN{run}-BTL", "unit": "bottle"}],
            price=None,
            stock=0,
        )
        token = await _login_retailer(r1_client, two_tenants)
        detail = await r1_client.get(
            f"/api/v1/client/products/{product_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        unit = detail.json()["data"]["units"][0]
        assert unit["price"] is None
        assert unit["stock_level"] == "OUT_OF_STOCK"
        assert unit["can_order"] is False
