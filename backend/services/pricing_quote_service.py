"""S1 server quotes: one country source, exact money, purpose-bound consent.

Tokens are not authentication credentials or a price/stock reservation.
Submission re-resolves each economic line under the shared SKU locks.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, text

from models.sku import SKU
from services.package_identity import lock_sku_row

PURPOSE = 'mpango.s1.quote.v1'
QUOTE_SECONDS = 900
MAX_MONEY = Decimal('9999999999.99')
COUNTRY_CURRENCY = {'KE': 'KES', 'UG': 'UGX'}
CURRENCY_SCALE = {'KES': 2, 'UGX': 0}


def refuse(code: str, message: str, *, status: int = 409, **details):
    raise HTTPException(status_code=status, detail={
        'code': code, 'message': message, **({'details': details} if details else {}),
    })


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def money(value, currency: str, *, positive: bool = True) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        refuse('INVALID_MONEY', 'Amount must be an exact decimal', status=422)
    if currency not in CURRENCY_SCALE:
        refuse('TENANT_CURRENCY_UNRESOLVED', 'Currency source has not been established')
    if not amount.is_finite() or amount < 0 or (positive and amount == 0) or amount > MAX_MONEY:
        refuse('INVALID_MONEY', 'Amount is non-positive, non-finite or exceeds storage bounds', status=422)
    quantum = Decimal(1).scaleb(-CURRENCY_SCALE[currency])
    try:
        rounded = amount.quantize(quantum)
    except InvalidOperation:
        refuse('INVALID_MONEY', 'Amount cannot be represented within storage bounds', status=422)
    if amount != rounded:
        refuse('MONEY_PRECISION', 'Amount has non-zero digits beyond the currency precision', status=422)
    return rounded


def amount_string(value, currency: str) -> str:
    return format(money(value, currency, positive=False), 'f')


@dataclass(frozen=True)
class CurrencySource:
    country: str
    currency: str
    registration_id: str
    wholesaler_id: str
    tenant_schema: str


async def resolve_currency(db, wholesaler_id=None) -> CurrencySource:
    schema = (await db.execute(text('SELECT current_schema()'))).scalar_one()
    rows = (await db.execute(text(
        "SELECT tr.id, tr.country, tr.wholesaler_id, tr.tenant_schema "
        "FROM public.tenant_registrations tr JOIN public.wholesalers w ON w.id=tr.wholesaler_id "
        "WHERE tr.tenant_schema=:schema AND tr.status='active' "
        "AND tr.provisioning_completed_at IS NOT NULL AND tr.is_deleted IS FALSE "
        "AND w.is_deleted IS FALSE AND w.status='active'"
    ), {'schema': schema})).mappings().all()
    if len(rows) != 1:
        refuse('TENANT_CURRENCY_UNRESOLVED', 'A unique completed registration is required')
    row = rows[0]
    wid = str(row['wholesaler_id'])
    if (schema != 't_' + UUID(wid).hex or row['country'] not in COUNTRY_CURRENCY
            or (wholesaler_id is not None and wid != str(wholesaler_id))):
        refuse('TENANT_CURRENCY_UNRESOLVED', 'Registration does not match the trading tenant')
    return CurrencySource(row['country'], COUNTRY_CURRENCY[row['country']],
                          str(row['id']), wid, schema)


def economic_lines(payload: dict) -> list[dict]:
    # Revision/source/harmless labels are audit, not an extra consent click.
    keys = ('sku_id', 'quantity', 'unit', 'package_quantity', 'unit_price', 'subtotal')
    return [{k: line[k] for k in keys} for line in payload['lines']]


def context(payload: dict) -> dict:
    return {k: payload[k] for k in ('tenant', 'wholesaler', 'retailer', 'actor',
                                   'operation', 'country', 'currency', 'registration')}


def _key() -> bytes:
    from core.config import get_settings
    return hmac.new(get_settings().SECRET_KEY.encode(), PURPOSE.encode(), hashlib.sha256).digest()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


QUOTE_TOKEN_MAX_LENGTH = 100000


def sign_quote(payload: dict) -> str:
    body = _encode(canonical_bytes(payload))
    signature = _encode(hmac.new(_key(), ('s1.' + body).encode('ascii'), hashlib.sha256).digest())
    token = 's1.' + body + '.' + signature
    if len(token) > QUOTE_TOKEN_MAX_LENGTH:
        refuse('QUOTE_BUDGET_EXCEEDED', 'Select fewer lines before requesting consent', status=422)
    return token


def read_quote(token: str, *, check_expiry: bool = True) -> dict:
    bad = False
    try:
        if not isinstance(token, str) or len(token) > QUOTE_TOKEN_MAX_LENGTH:
            raise ValueError()
        prefix, body, signature = token.split('.')
        expected = _encode(hmac.new(_key(), ('s1.' + body).encode('ascii'), hashlib.sha256).digest())
        if prefix != 's1' or not hmac.compare_digest(expected, signature):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        if payload['purpose'] != PURPOSE or type(payload['iat']) is not int or type(payload['exp']) is not int:
            raise ValueError()
        if payload['exp'] - payload['iat'] != QUOTE_SECONDS or payload['iat'] > int(time.time()) + 5:
            raise ValueError()
        context(payload)
        economic_lines(payload)
    except (ValueError, TypeError, KeyError, UnicodeError):
        bad = True
    if bad:
        refuse('QUOTE_INVALID', 'The server quote cannot be verified')
    if check_expiry and payload['exp'] <= int(time.time()):
        refuse('QUOTE_EXPIRED', 'Refresh the quote before submitting')
    return payload


async def build_quote(db, *, wholesaler_id, retailer_id, actor_id, operation,
                      items, lock: bool = False) -> dict:
    from models.catalog_product import CatalogProduct
    from repositories.pricing_repository import effective_price
    source = await resolve_currency(db, wholesaler_id)
    selections = []
    for item in items:
        sid, code = item.get('sellable_unit_id'), item.get('sku_code')
        selector = SKU.id == UUID(str(sid)) if sid else SKU.sku_code == code
        sku = (await db.execute(select(SKU).where(selector, SKU.is_deleted.is_(False)))).scalar_one_or_none()
        if sku is None or (code and sku.sku_code != code):
            refuse('SELLABLE_UNIT_NOT_FOUND', 'The stable item selectors do not match', status=400)
        selections.append((sku.id, item['quantity']))
    if len({sid for sid, _ in selections}) != len(selections):
        refuse('QUOTE_DUPLICATE_LINE', 'A sellable unit may occur only once', status=422)
    lines = []
    for sid, quantity in sorted(selections, key=lambda pair: str(pair[0])):
        if type(quantity) is not int or not 1 <= quantity <= 10000:
            refuse('INVALID_QUANTITY', 'Quantity must be a bounded integer', status=422)
        sku = await lock_sku_row(db, sku_id=sid) if lock else (
            await db.execute(select(SKU).where(SKU.id == sid, SKU.is_deleted.is_(False))
                             .execution_options(populate_existing=True))).scalar_one_or_none()
        if sku is None or not sku.is_active or not sku.unit or not sku.unit.strip():
            refuse('SELLABLE_UNIT_UNAVAILABLE', 'A verified active unit is required')
        if (not sku.package_quantity.is_finite() or sku.package_quantity <= 0
                or sku.package_quantity != sku.package_quantity.quantize(Decimal('0.001'))):
            refuse('SELLABLE_UNIT_UNAVAILABLE', 'A verified finite package definition is required')
        product = (await db.execute(select(CatalogProduct).where(
            CatalogProduct.id == sku.catalog_product_id, CatalogProduct.is_deleted.is_(False),
            CatalogProduct.is_active.is_(True)))).scalar_one_or_none()
        if product is None:
            refuse('SELLABLE_UNIT_UNAVAILABLE', 'The product is unavailable')
        override = (await db.execute(text(
            'SELECT price FROM retailer_prices WHERE sku_id=:sid AND retailer_id=:rid '
            'AND is_deleted IS FALSE'), {'sid': sid, 'rid': UUID(str(retailer_id))})).scalar_one_or_none()
        value, origin, reason = effective_price(sku.base_price, override)
        if reason:
            refuse(reason, 'Complete the base price before selling this item')
        money(sku.base_price, source.currency)
        price = money(value, source.currency)
        subtotal = money(price * quantity, source.currency)
        lines.append({'sku_id': str(sid), 'sku_code': sku.sku_code, 'product_name': product.name,
                      'quantity': quantity, 'unit': sku.unit,
                      'package_quantity': format(sku.package_quantity.normalize(), 'f'),
                      'display_label': sku.display_label or sku.unit,
                      'unit_price': format(price, 'f'), 'subtotal': format(subtotal, 'f'),
                      'revision': sku.pricing_revision, 'source': origin})
    total = money(sum((Decimal(line['subtotal']) for line in lines), Decimal(0)), source.currency)
    now = int(time.time())
    return {'purpose': PURPOSE, 'iat': now, 'exp': now + QUOTE_SECONDS,
            'tenant': source.tenant_schema, 'wholesaler': source.wholesaler_id,
            'retailer': str(retailer_id), 'actor': str(actor_id), 'operation': operation,
            'country': source.country, 'currency': source.currency,
            'registration': source.registration_id, 'lines': lines, 'total': format(total, 'f')}


def quote_view(payload: dict) -> dict:
    return {'quote_token': sign_quote(payload), 'currency': payload['currency'],
            'country': payload['country'], 'lines': payload['lines'], 'total': payload['total'],
            'expires_at': payload['exp']}


def require_consent(seen: dict, current: dict) -> None:
    if context(seen) != context(current):
        refuse('QUOTE_CONTEXT_CHANGED', 'The trading context changed; request a fresh quote')
    before = economic_lines(seen)
    after = economic_lines(current)
    identities = ('sku_id', 'quantity', 'unit', 'package_quantity')
    if [{k: x[k] for k in identities} for x in before] != [{k: x[k] for k in identities} for x in after]:
        refuse('QUOTE_CONTEXT_CHANGED', 'The item quantity or unit changed; request a fresh quote')
    if before != after:
        changes = [{'sku_id': a['sku_id'], 'old_price': a['unit_price'],
                    'new_price': b['unit_price'], 'old_subtotal': a['subtotal'],
                    'new_subtotal': b['subtotal'], 'quantity': a['quantity']}
                   for a, b in zip(before, after) if a != b]
        refuse('PRICE_PREVIEW_STALE', 'Review the new prices and explicitly accept before creating',
               old_total=seen['total'], new_total=current['total'],
               delta=format(Decimal(current['total']) - Decimal(seen['total']), 'f'),
               currency=current['currency'], changes=changes, quote=quote_view(current))
