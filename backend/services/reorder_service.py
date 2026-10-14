"""S2 source/selection adapter around the sole S1 quote and DRAFT authority.

Historical identities are never resolved by a code or name. Every retained
source item has a persisted, explicit decision; stock warnings do not change
quantities and this service never invokes confirmation or cancellation.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from models.order import Order
from services.pricing_quote_service import (
    CURRENCY_SCALE, amount_string, build_quote, canonical_bytes, quote_view,
    refuse, resolve_currency, read_quote,
)

OPERATION = 'client-reorder'
AUDIT_VERSION = 1


async def load_source(db, *, source_order_id, wholesaler_id, retailer_id, lock=False):
    """Fresh dual-key ownership lookup, including on a committed replay."""
    query = select(Order).where(
        Order.id == UUID(str(source_order_id)),
        Order.wholesaler_id == UUID(str(wholesaler_id)),
        Order.retailer_id == UUID(str(retailer_id)),
        Order.is_deleted.is_(False),
    ).options(selectinload(Order.items)).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    source = (await db.execute(query)).scalar_one_or_none()
    if source is None:
        refuse('ORDER_NOT_FOUND', 'Order not found', status=404)
    return source


def _historical_items(source):
    # There is no original click-position column. UUID order is durable and
    # is disclosed as historical display order, not reconstructed click order.
    return sorted(source.items, key=lambda item: str(item.id))


def canonical_selections(source, selections):
    originals = _historical_items(source)
    ids = {str(item.id) for item in originals}
    if selections is None:
        selections = [{'source_item_id': str(item.id), 'action': 'keep'} for item in originals]
    supplied = {}
    for selection in selections:
        sid = str(selection['source_item_id'])
        if sid in supplied or sid not in ids:
            refuse('REORDER_SELECTION_INVALID', 'Each historical item needs exactly one decision', status=422)
        action = selection['action']
        clean = {'source_item_id': sid, 'action': action}
        if action == 'replace':
            clean.update(sellable_unit_id=str(selection['sellable_unit_id']), quantity=selection['quantity'])
            original = next(item for item in originals if str(item.id) == sid)
            if original.sellable_unit_id and clean['sellable_unit_id'] == str(original.sellable_unit_id):
                refuse('REORDER_SELECTION_INVALID', 'Replacement must explicitly select a different sellable unit', status=422)
        supplied[sid] = clean
    if set(supplied) != ids:
        refuse('REORDER_SELECTION_INVALID', 'No historical line may be silently omitted', status=422)
    return [supplied[str(item.id)] for item in originals]


def _decimal_string(value):
    return format(Decimal(str(value)).normalize(), 'f') if value is not None else None


def _historical_amount(value, currency):
    if currency in CURRENCY_SCALE:
        try:
            return amount_string(value, currency)
        except HTTPException:
            # Retained NUMERIC(12,2) history can predate the country's
            # precision contract. Display it exactly; never round old facts.
            pass
    return format(Decimal(str(value)), 'f')


def _historical_money_verified(source, currency):
    if source.currency_snapshot != currency or currency not in CURRENCY_SCALE:
        return False
    try:
        for amount in [source.total_amount] + [value for item in _historical_items(source)
                                              for value in (item.unit_price, item.subtotal)]:
            amount_string(amount, currency)
    except HTTPException:
        return False
    return True


def _audit(source, selections):
    return {'version': AUDIT_VERSION, 'source_order_id': str(source.id),
            'source_currency': source.currency_snapshot, 'selections': selections,
            'source_lines': [{
                'source_item_id': str(item.id),
                'sellable_unit_id': str(item.sellable_unit_id) if item.sellable_unit_id else None,
                'identity_status': item.identity_status,
                'unit': item.unit_snapshot,
                'package_quantity': _decimal_string(item.package_quantity_snapshot),
                'quantity': item.quantity,
            } for item in _historical_items(source)]}


def _identity_reason(line):
    package = line['package_quantity']
    if (line['identity_status'] not in ('stable', 'linked_legacy')
            or not line['sellable_unit_id'] or not line['unit'] or not line['unit'].strip()
            or package is None):
        return 'LEGACY_IDENTITY_UNRESOLVED'
    value = Decimal(package)
    if not value.is_finite() or value <= 0 or value != value.quantize(Decimal('0.001')):
        return 'LEGACY_IDENTITY_UNRESOLVED'
    return None


def _selected_items(intent, *, refuse_unavailable=True):
    originals = {line['source_item_id']: line for line in intent['source_lines']}
    items = []
    for selection in intent['selections']:
        if selection['action'] == 'remove':
            continue
        original = originals[selection['source_item_id']]
        if selection['action'] == 'keep':
            reason = _identity_reason(original)
            if reason:
                if refuse_unavailable:
                    refuse('REORDER_SELECTION_UNAVAILABLE', 'Explicitly remove or replace the unresolved historical line',
                           source_item_id=selection['source_item_id'], reason=reason)
                continue
            sid, quantity = original['sellable_unit_id'], original['quantity']
        else:
            sid, quantity = selection['sellable_unit_id'], selection['quantity']
        items.append({'sellable_unit_id': sid, 'quantity': quantity})
    return items


def validate_source_selection(intent, current):
    """A keep cannot acknowledge an altered definition under the old UUID."""
    originals = {line['source_item_id']: line for line in intent['source_lines']}
    lines = {line['sku_id']: line for line in current['lines']}
    for selection in intent['selections']:
        if selection['action'] != 'keep':
            continue
        original = originals[selection['source_item_id']]
        reason = _identity_reason(original)
        line = lines.get(original['sellable_unit_id'])
        if reason or line is None:
            refuse('REORDER_SELECTION_UNAVAILABLE', 'Explicitly remove or replace the unresolved historical line',
                   source_item_id=selection['source_item_id'], reason=reason or 'SELLABLE_UNIT_NOT_FOUND')
        if (line['unit'] != original['unit']
                or Decimal(line['package_quantity']) != Decimal(original['package_quantity'])):
            refuse('REORDER_SELECTION_UNAVAILABLE', 'The historical unit cannot be reused with a changed definition',
                   source_item_id=selection['source_item_id'], reason='PACKAGING_IDENTITY_CHANGED')


async def validate_reorder_source(db, *, intent, wholesaler_id, retailer_id, lock=False):
    source = await load_source(db, source_order_id=intent['source_order_id'],
                               wholesaler_id=wholesaler_id, retailer_id=retailer_id, lock=lock)
    fresh = _audit(source, canonical_selections(source, intent['selections']))
    if canonical_bytes(fresh) != canonical_bytes(intent):
        refuse('REORDER_SOURCE_CHANGED', 'The historical identity evidence changed; review the source again')
    return source


async def authorize_reorder_intent(db, *, source_order_id, wholesaler_id, retailer_id,
                                   actor_id, selections, quote_token, notes, idempotency_key):
    """Read-only source proof used by both first submit and cached replay.

The route's RequirePermission subclass is recognized by the existing replay
authority collector. Reuse the same signature/context/source proof here;
expiry and fresh pricing remain first-commit checks in submit_draft.
"""
    from services.order_creation_service import (
        assert_binding, _selection_matches, accepted_fingerprint,
        assert_committed_intent, creation_key_digest,
    )
    schema = (await db.execute(text('SELECT current_schema()'))).scalar_one()
    verified_tenant = str(UUID(str(wholesaler_id)))
    if (schema != 't_' + UUID(verified_tenant).hex
            or (db.info.get('tenant_schema') is not None and db.info['tenant_schema'] != schema)
            or (db.info.get('tenant_id') is not None and str(db.info['tenant_id']) != verified_tenant)):
        refuse('QUOTE_CONTEXT_CHANGED', 'The current verified tenant session does not match the trading context')
    # Cached replay is outside AuthenticationMiddleware's ContextVars. Record
    # the SAME server-derived client tenant in its already verified session;
    # the global ORM guard remains enabled and every source query is scoped.
    db.info.setdefault('tenant_schema', schema)
    db.info.setdefault('tenant_id', verified_tenant)
    await assert_binding(db, wholesaler_id, retailer_id)
    source = await load_source(db, source_order_id=source_order_id,
                               wholesaler_id=wholesaler_id, retailer_id=retailer_id)
    intent = _audit(source, canonical_selections(source, selections))
    items = _selected_items(intent)
    if not items:
        refuse('REORDER_EMPTY_SELECTION', 'Select at least one verified item before accepting', status=422)
    seen = read_quote(quote_token, check_expiry=False)
    expected = {'tenant': schema, 'wholesaler': str(wholesaler_id),
                'retailer': str(retailer_id), 'actor': str(actor_id), 'operation': OPERATION}
    if any(seen.get(key) != value for key, value in expected.items()) or seen.get('reorder') != intent:
        refuse('QUOTE_CONTEXT_CHANGED', 'The source, decisions and current actor must match the accepted quote')
    if not _selection_matches(items, seen):
        refuse('QUOTE_CONTEXT_CHANGED', 'The selected lines do not match the accepted quote')
    digest = creation_key_digest(idempotency_key)
    existing = (await db.execute(select(Order).where(
        Order.wholesaler_id == UUID(str(wholesaler_id)),
        Order.retailer_id == UUID(str(retailer_id)), Order.created_by == UUID(str(actor_id)),
        Order.creation_operation == OPERATION, Order.creation_key_digest == digest,
    ).execution_options(populate_existing=True))).scalar_one_or_none()
    if existing is not None:
        assert_committed_intent(existing,
            accepted_fingerprint(seen, notes=notes, reorder_intent=intent), intent)


async def _stock_warning(db, line):
    stock = (await db.execute(text(
        'SELECT quantity_on_hand - quantity_reserved FROM inventory_stocks '
        'WHERE sku_id=:sid AND is_deleted IS FALSE'
    ), {'sid': UUID(line['sku_id'])})).scalar_one_or_none()
    return 'INSUFFICIENT_STOCK' if stock is None or Decimal(str(stock)) < line['quantity'] else None


async def preview_reorder(db, *, source_order_id, wholesaler_id, retailer_id, actor_id, selections=None):
    from services.order_creation_service import assert_binding
    await assert_binding(db, wholesaler_id, retailer_id)
    source = await load_source(db, source_order_id=source_order_id,
                               wholesaler_id=wholesaler_id, retailer_id=retailer_id)
    selections = canonical_selections(source, selections)
    intent = _audit(source, selections)
    currency = (await resolve_currency(db, wholesaler_id)).currency
    original_audit = {line['source_item_id']: line for line in intent['source_lines']}
    selected = _selected_items(intent, refuse_unavailable=False)
    duplicates = {sid for sid, count in Counter(item['sellable_unit_id'] for item in selected).items() if count > 1}
    rows = []
    for item, selection in zip(_historical_items(source), selections):
        audit_line = original_audit[str(item.id)]
        row = {'source_item_id': str(item.id), 'selection': selection,
               'original': {
                   'product_name': item.product_name, 'sku_code': item.sku_code,
                   'sellable_unit_id': audit_line['sellable_unit_id'], 'identity_status': item.identity_status,
                   'unit': item.unit_snapshot, 'package_quantity': audit_line['package_quantity'],
                   'display_label': item.display_label_snapshot, 'quantity': item.quantity,
                   'unit_price': _historical_amount(item.unit_price, source.currency_snapshot),
                   'subtotal': _historical_amount(item.subtotal, source.currency_snapshot),
               }, 'status': 'REMOVED' if selection['action'] == 'remove' else 'READY',
               'reason': None, 'current': None, 'stock_warning': None}
        if selection['action'] != 'remove':
            reason = _identity_reason(audit_line) if selection['action'] == 'keep' else None
            sid = audit_line['sellable_unit_id'] if selection['action'] == 'keep' else selection['sellable_unit_id']
            quantity = item.quantity if selection['action'] == 'keep' else selection['quantity']
            if sid in duplicates:
                reason = 'QUOTE_DUPLICATE_LINE'
            if not reason:
                try:
                    payload = await build_quote(db, wholesaler_id=wholesaler_id, retailer_id=retailer_id,
                        actor_id=actor_id, operation=OPERATION,
                        items=[{'sellable_unit_id': sid, 'quantity': quantity}])
                    line = payload['lines'][0]
                    if selection['action'] == 'keep' and (
                            line['unit'] != audit_line['unit'] or
                            Decimal(line['package_quantity']) != Decimal(audit_line['package_quantity'])):
                        reason = 'PACKAGING_IDENTITY_CHANGED'
                    else:
                        row['current'] = line
                        row['stock_warning'] = await _stock_warning(db, line)
                except HTTPException as error:
                    if not isinstance(error.detail, dict) or not error.detail.get('code'):
                        raise
                    reason = error.detail['code']
            if reason:
                row.update(status='UNAVAILABLE', reason=reason)
        rows.append(row)
    ready = bool(selected) and all(row['status'] != 'UNAVAILABLE' for row in rows)
    quote = None
    if ready:
        payload = await build_quote(db, wholesaler_id=wholesaler_id, retailer_id=retailer_id,
            actor_id=actor_id, operation=OPERATION, items=selected)
        payload['reorder'] = intent
        validate_source_selection(intent, payload)
        quote = quote_view(payload)
        latest = {line['sku_id']: line for line in payload['lines']}
        for row in rows:
            if row['current'] is not None:
                row['current'] = latest[row['current']['sku_id']]
                row['stock_warning'] = await _stock_warning(db, row['current'])
    comparable = _historical_money_verified(source, currency)
    delta = None
    if quote and comparable:
        quantum = Decimal(1).scaleb(-CURRENCY_SCALE[currency])
        delta = format((Decimal(quote['total']) - source.total_amount).quantize(quantum), 'f')
    return {'source_order_id': str(source.id), 'order_basis': 'HISTORICAL_ITEM_ID',
            'historical_total': _historical_amount(source.total_amount, source.currency_snapshot),
            'historical_currency': source.currency_snapshot,
            'historical_currency_status': 'KNOWN' if source.currency_snapshot in CURRENCY_SCALE else 'LEGACY_CURRENCY_UNVERIFIED',
            'rows': rows, 'ready': ready, 'quote': quote,
            'current_total': quote['total'] if quote else None, 'current_currency': currency,
            'delta': delta}


async def submit_reorder(db, *, source_order_id, wholesaler_id, retailer_id, actor_id,
                         selections, notes, quote_token, idempotency_key):
    from services.order_creation_service import assert_binding, submit_draft
    await assert_binding(db, wholesaler_id, retailer_id)
    source = await load_source(db, source_order_id=source_order_id,
                               wholesaler_id=wholesaler_id, retailer_id=retailer_id)
    intent = _audit(source, canonical_selections(source, selections))
    items = _selected_items(intent)
    if not items:
        refuse('REORDER_EMPTY_SELECTION', 'Select at least one verified item before accepting', status=422)
    return await submit_draft(db, wholesaler_id=wholesaler_id, retailer_id=retailer_id,
        actor_id=actor_id, operation=OPERATION, items=items, notes=notes,
        quote_token=quote_token, idempotency_key=idempotency_key, reorder_intent=intent)
