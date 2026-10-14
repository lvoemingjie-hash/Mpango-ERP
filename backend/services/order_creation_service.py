"""Limited S1 DRAFT adapter; authentication stays at the two HTTP boundaries.

The order's intent metadata is the durable result. Advisory locks serialize
an intent across processes; database uniqueness remains the final backstop.
No inventory, payment or status authority is introduced here.
"""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException

from sqlalchemy import select, text

from crud.order import create_order
from models.order import Order, OrderStatus
from services.pricing_quote_service import (
    amount_string, build_quote, canonical_bytes, context, economic_lines, read_quote,
    refuse, require_consent,
)


async def assert_binding(db, wholesaler_id, retailer_id):
    row = (await db.execute(text(
        "SELECT id FROM public.wholesaler_retailer_bindings WHERE wholesaler_id=:wid "
        "AND retailer_id=:rid AND status='active' AND is_deleted IS FALSE"
    ), {'wid': UUID(str(wholesaler_id)), 'rid': UUID(str(retailer_id))})).first()
    if row is None:
        refuse('RETAILER_NOT_BOUND', 'The retailer is not actively bound', status=403)


def _selection_matches(items, seen):
    lines = seen['lines']
    if len(items) != len(lines):
        return False
    found = set()
    for item in items:
        matches = [line for line in lines if
                   (not item.get('sellable_unit_id') or str(item['sellable_unit_id']) == line['sku_id'])
                   and (not item.get('sku_code') or item['sku_code'] == line['sku_code'])
                   and item['quantity'] == line['quantity']]
        if len(matches) != 1 or matches[0]['sku_id'] in found:
            return False
        found.add(matches[0]['sku_id'])
    return True


def creation_key_digest(idempotency_key):
    if not idempotency_key or not re.fullmatch(r'[A-Za-z0-9.:_\-]{8,64}', idempotency_key):
        refuse('MISSING_IDEMPOTENCY_KEY', 'A valid X-Idempotency-Key is required', status=400)
    return hashlib.sha256(idempotency_key.encode('ascii')).hexdigest()


def accepted_fingerprint(seen, *, notes, replaces_order_id=None, reorder_intent=None):
    accepted_intent = {
        'context': context(seen), 'lines': economic_lines(seen), 'notes': notes,
        'replaces': str(replaces_order_id) if replaces_order_id else None,
    }
    # Default S1 canonical bytes stay identical to its committed contract.
    if reorder_intent is not None:
        accepted_intent['reorder'] = reorder_intent
    return hashlib.sha256(canonical_bytes(accepted_intent)).hexdigest()


def assert_committed_intent(existing, fingerprint, reorder_intent=None):
    if (existing.creation_fingerprint != fingerprint or (reorder_intent is not None and (
            not existing.quote_seen or not existing.quote_resolved or
            existing.quote_seen.get('reorder') != reorder_intent or
            existing.quote_resolved.get('reorder') != reorder_intent))):
        refuse('ORDER_CREATE_IDEMPOTENCY_CONFLICT', 'This key already committed a different accepted intent')


async def submit_draft(db, *, wholesaler_id, retailer_id, actor_id, operation,
                       items, notes, quote_token, idempotency_key, replaces_order_id=None,
                       reorder_intent=None):
    await assert_binding(db, wholesaler_id, retailer_id)
    if (operation == 'client-reorder') != (reorder_intent is not None) or (
            reorder_intent is not None and replaces_order_id is not None):
        refuse('REORDER_CONTEXT_REQUIRED', 'Reordering requires the dedicated source-selection service')
    key_digest = creation_key_digest(idempotency_key)
    # A committed replay may outlive the quote TTL, but not authentication,
    # scope, signature or accepted-intent checks.
    seen = read_quote(quote_token, check_expiry=False)
    schema = (await db.execute(text('SELECT current_schema()'))).scalar_one()
    expected = {'tenant': schema, 'wholesaler': str(wholesaler_id),
                'retailer': str(retailer_id), 'actor': str(actor_id), 'operation': operation}
    if any(seen.get(k) != v for k, v in expected.items()):
        refuse('QUOTE_CONTEXT_CHANGED', 'The quote does not belong to this authorized operation')
    if not _selection_matches(items, seen):
        refuse('QUOTE_CONTEXT_CHANGED', 'The selected lines do not match the quote')
    if reorder_intent is not None and seen.get('reorder') != reorder_intent:
        refuse('QUOTE_CONTEXT_CHANGED', 'The source and every historical-line decision must match the accepted quote')
    fingerprint = accepted_fingerprint(seen, notes=notes, replaces_order_id=replaces_order_id,
                                       reorder_intent=reorder_intent)
    scope = {'wid': UUID(str(wholesaler_id)), 'rid': UUID(str(retailer_id)),
             'actor': UUID(str(actor_id)), 'operation': operation, 'key': key_digest}
    lock_digest = hashlib.sha256(canonical_bytes({k: str(v) for k, v in scope.items()})).digest()
    await db.execute(text('SELECT pg_advisory_xact_lock(:identity)'),
                     {'identity': int.from_bytes(lock_digest[:8], 'big', signed=True)})
    existing = (await db.execute(select(Order).where(
        Order.wholesaler_id == scope['wid'], Order.retailer_id == scope['rid'],
        Order.created_by == scope['actor'], Order.creation_operation == operation,
        Order.creation_key_digest == key_digest,
    ).execution_options(populate_existing=True))).scalar_one_or_none()
    if reorder_intent is not None:
        from services.reorder_service import validate_reorder_source
        await validate_reorder_source(db, intent=reorder_intent,
            wholesaler_id=wholesaler_id, retailer_id=retailer_id, lock=existing is None)
    if existing is not None:
        assert_committed_intent(existing, fingerprint, reorder_intent)
        return existing, True
    read_quote(quote_token, check_expiry=True)

    old = None
    if replaces_order_id:
        old = (await db.execute(select(Order).where(
            Order.id == UUID(str(replaces_order_id)), Order.wholesaler_id == scope['wid'],
            Order.retailer_id == scope['rid'], Order.is_deleted.is_(False),
        ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if old is None:
            refuse('ORDER_NOT_FOUND', 'Order not found', status=404)
        if old.status != OrderStatus.DRAFT:
            refuse('DRAFT_REPLACEMENT_NOT_ALLOWED', 'Only a zero-effect DRAFT can be replaced')
        if operation == 'client-create' and (
                old.created_by != scope['actor'] or old.creation_operation != 'client-create'):
            refuse('DRAFT_REPLACEMENT_NOT_ALLOWED', 'Ask an authorized merchant to replace this draft', status=403)
        counts = (await db.execute(text(
            'SELECT (SELECT count(*) FROM payments WHERE order_id=:oid) + '
            '(SELECT count(*) FROM order_credit_holds WHERE order_id=:oid) + '
            '(SELECT count(*) FROM inventory_reservations WHERE order_id=:oid) + '
            "(SELECT count(*) FROM ledger_entries WHERE reference_type='order' AND reference_id=:oid)"
        ), {'oid': old.id})).scalar_one()
        if counts:
            refuse('DRAFT_REPLACEMENT_NOT_ALLOWED', 'The draft has retained economic effects')

    current = await build_quote(db, wholesaler_id=wholesaler_id, retailer_id=retailer_id,
                                actor_id=actor_id, operation=operation, items=items, lock=True)
    if reorder_intent is not None:
        from services.reorder_service import validate_source_selection
        current['reorder'] = reorder_intent
        validate_source_selection(reorder_intent, current)
    try:
        require_consent(seen, current)
    except HTTPException as error:
        if (reorder_intent is not None and context(seen) == context(current)
                and economic_lines(seen) != economic_lines(current)):
            from services.pricing_quote_service import quote_view
            refuse('REORDER_PREVIEW_STALE', 'Review the current complete quote and explicitly accept again',
                   old_total=seen['total'], new_total=current['total'],
                   delta=format(Decimal(current['total']) - Decimal(seen['total']), 'f'),
                   currency=current['currency'], quote=quote_view(current))
        raise error
    # The fixed, source-validated S2 operation can save a shortage DRAFT.
    # HTTP callers cannot select this behavior on either ordinary S1 route.
    if operation != 'client-reorder':
        for line in current['lines']:
            stock = (await db.execute(text(
                'SELECT quantity_on_hand FROM inventory_stocks WHERE sku_id=:sid AND is_deleted IS FALSE'
            ), {'sid': UUID(line['sku_id'])})).scalar_one_or_none()
            if stock is None or Decimal(str(stock)) < line['quantity']:
                refuse('ORDER_VALIDATION_FAILED', 'Insufficient stock for the selected quantity', status=400)
    order_items = [{
        'sellable_unit_id': line['sku_id'], 'product_name': line['product_name'],
        'sku_code': line['sku_code'], 'unit_snapshot': line['unit'],
        'package_quantity_snapshot': Decimal(line['package_quantity']),
        'display_label_snapshot': line['display_label'], 'quantity': line['quantity'],
        'unit_price': Decimal(line['unit_price']),
    } for line in current['lines']]
    # A savepoint also makes service-level failures non-partial; the request's
    # outer commit owns both the new draft and cancellation of the old one.
    async with db.begin_nested():
        order = await create_order(db=db, wholesaler_id=str(wholesaler_id),
                                   retailer_id=str(retailer_id), items=order_items,
                                   notes=notes, created_by=str(actor_id))
        order.country_snapshot = current['country']
        order.currency_snapshot = current['currency']
        order.registration_snapshot_id = UUID(current['registration'])
        order.creation_operation = operation
        order.creation_key_digest = key_digest
        order.creation_fingerprint = fingerprint
        order.quote_seen = seen
        order.quote_resolved = current
        order.replaces_order_id = old.id if old else None
        await db.flush()
        if old:
            from services.order_command_service import OrderCommandService
            await OrderCommandService(db).cancel_order(old.id, updated_by=str(actor_id))
        await db.refresh(order, attribute_names=['updated_at'])
    return order, False


async def validate_draft_for_confirmation(db, order):
    if not order.currency_snapshot or not order.quote_resolved:
        refuse('DRAFT_REQUOTE_REQUIRED', 'Select verified items and explicitly replace this legacy draft')
    stored = sorted([{
        'sku_id': str(item.sellable_unit_id), 'quantity': item.quantity,
        'unit': item.unit_snapshot,
        'package_quantity': format(item.package_quantity_snapshot.normalize(), 'f')
            if item.package_quantity_snapshot is not None else None,
        'unit_price': amount_string(item.unit_price, order.currency_snapshot),
        'subtotal': amount_string(item.subtotal, order.currency_snapshot),
    } for item in order.items], key=lambda line: line['sku_id'])
    if (stored != economic_lines(order.quote_resolved)
            or Decimal(order.quote_resolved['total']) != order.total_amount
            or order.currency_snapshot != order.quote_resolved['currency']
            or order.country_snapshot != order.quote_resolved['country']
            or str(order.registration_snapshot_id) != order.quote_resolved['registration']):
        refuse('DRAFT_REQUOTE_REQUIRED', 'Stored item snapshots cannot be verified against the accepted quote')
    items = [{'sellable_unit_id': str(item.sellable_unit_id), 'quantity': item.quantity}
             for item in order.items]
    current = await build_quote(db, wholesaler_id=order.wholesaler_id,
                                retailer_id=order.retailer_id, actor_id=order.created_by,
                                operation=order.creation_operation, items=items, lock=True)
    try:
        require_consent(order.quote_resolved, current)
    except HTTPException:
        refuse('DRAFT_REQUOTE_REQUIRED', 'Review a fresh quote and explicitly replace this draft')
