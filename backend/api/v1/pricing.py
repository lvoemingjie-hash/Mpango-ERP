"""S1 merchant pricing: base completion, overrides and versioned writes."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from repositories.pricing_repository import effective_price, set_base_price, set_price
from schemas.common import DataResponse
from services.order_creation_service import assert_binding
from services.pricing_quote_service import amount_string, money, resolve_currency

router = APIRouter()


class SetPriceRequest(BaseModel):
    retailer_id: UUID
    sku_id: UUID
    price: str = Field(min_length=1, max_length=40)
    expected_revision: int = Field(ge=0)
    retire: bool = False
    model_config = {"extra": "forbid"}

    @field_validator('price')
    @classmethod
    def positive_decimal(cls, value):
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError('An exact positive decimal price is required') from exc
        if not amount.is_finite() or amount <= 0:
            raise ValueError('An exact positive decimal price is required')
        return value


class SetBaseRequest(BaseModel):
    price: str = Field(min_length=1, max_length=40)
    expected_revision: int = Field(ge=0)
    model_config = {"extra": "forbid"}

    @field_validator('price')
    @classmethod
    def positive_decimal(cls, value):
        return SetPriceRequest.positive_decimal(value)


@router.get("/prices", response_model=DataResponse[dict])
async def list_retailer_prices(
    retailer_id: UUID = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    token: TokenPayload = Depends(RequirePermission("pricing:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    await assert_binding(db, token.tenant_id, retailer_id)
    source = await resolve_currency(db, token.tenant_id)
    total = (await db.execute(text(
        "SELECT count(*) FROM skus WHERE is_deleted IS FALSE"
    ))).scalar_one()
    rows = (await db.execute(text(
        "SELECT s.id, s.sku_code, s.name, s.unit, s.display_label, s.base_price, "
        "s.pricing_revision, s.updated_at, rp.price AS override_price, rp.is_deleted AS retired "
        "FROM skus s LEFT JOIN retailer_prices rp ON rp.sku_id=s.id AND rp.retailer_id=:rid "
        "WHERE s.is_deleted IS FALSE ORDER BY s.name, s.id OFFSET :off LIMIT :lim"
    ), {"rid": retailer_id, "off": (page - 1) * size, "lim": size})).mappings().all()
    items = []
    for row in rows:
        override = None if row["retired"] else row["override_price"]
        value, origin, reason = effective_price(row["base_price"], override)
        rendered = {}
        audit_price_issues = {}
        for name, amount in (("base_price", row["base_price"]),
                             ("override_price", row["override_price"]), ("price", value)):
            try:
                rendered[name] = amount_string(amount, source.currency) if amount is not None else None
            except HTTPException as exc:
                # Retained incompatible prices must be visible for correction,
                # but never become an orderable currency-rounded value.
                rendered[name] = str(amount)
                if name == 'override_price' and row['retired']:
                    audit_price_issues[name] = exc.detail['code']
                else:
                    reason = exc.detail['code']
        items.append({
            "sku_id": str(row["id"]), "sku_code": row["sku_code"], "sku_name": row["name"],
            "retailer_id": str(retailer_id), "unit": row["unit"],
            "display_label": row["display_label"] or row["unit"],
            "base_price": rendered['base_price'],
            "override_price": rendered['override_price'],
            "override_retired": bool(row["retired"]),
            "audit_price_issues": audit_price_issues,
            "price": None if reason else rendered['price'],
            "price_source": origin, "unorderable_reason": reason,
            "currency": source.currency, "pricing_revision": row["pricing_revision"],
            "updated_at": row["updated_at"],
        })
    return DataResponse(success=True, data={"items": items, "total": total}, timestamp=datetime.utcnow())


@router.put("/prices", response_model=DataResponse[dict])
async def set_retailer_price(
    request: SetPriceRequest,
    token: TokenPayload = Depends(RequirePermission("pricing:write")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    await assert_binding(db, token.tenant_id, request.retailer_id)
    source = await resolve_currency(db, token.tenant_id)
    record = await set_price(db, request.retailer_id, request.sku_id,
                             Decimal(request.price),
                             updated_by=UUID(token.user_id),
                             expected_revision=request.expected_revision, retire=request.retire)
    return DataResponse(success=True, data={
        "sku_id": str(request.sku_id), "retailer_id": str(request.retailer_id),
        "price": str(record.price) if request.retire else amount_string(record.price, source.currency),
        "action": "retired" if request.retire else "saved",
    }, timestamp=datetime.utcnow())


@router.put("/base-prices/{sku_id}", response_model=DataResponse[dict])
async def update_base_price(
    sku_id: UUID, request: SetBaseRequest,
    token: TokenPayload = Depends(RequirePermission("pricing:write")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    sku = await set_base_price(db, sku_id=sku_id, price=request.price,
                               expected_revision=request.expected_revision, actor_id=UUID(token.user_id))
    source = await resolve_currency(db, token.tenant_id)
    return DataResponse(success=True, data={
        "sku_id": str(sku.id), "price": amount_string(sku.base_price, source.currency),
        "pricing_revision": sku.pricing_revision, "currency": source.currency,
    }, timestamp=datetime.utcnow())
