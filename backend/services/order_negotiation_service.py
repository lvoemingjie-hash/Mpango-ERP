"""S3 commercial consent. No inventory, credit, payment or status authority.

Mutations lock source order -> proposal -> sorted units. Confirmation locks
replacement order -> accepted proposal -> the existing stock/unit lock set.
The source is terminal then and is never locked in the opposite direction.
"""
from __future__ import annotations

import hashlib
import hmac
from copy import deepcopy
from datetime import timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select, text

from crud.order import create_order
from models.order import Order, OrderStatus
from models.order_negotiation import OrderNegotiationProposal as Proposal
from services.order_creation_service import assert_binding, creation_key_digest
from services.pricing_quote_service import (
    amount_string, canonical_bytes, economic_lines, money, refuse, resolve_currency,
    validate_negotiated_units,
)

OPERATION = 'client-negotiation'


def proposal_digest(payload):
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def order_snapshot(order):
    if not order.currency_snapshot or not order.registration_snapshot_id or not order.quote_resolved:
        refuse('DRAFT_REQUOTE_REQUIRED', 'Replace this legacy draft using a verified quote first')
    lines = sorted([{
        'sku_id': str(item.sellable_unit_id), 'sku_code': item.sku_code,
        'product_name': item.product_name, 'quantity': item.quantity,
        'unit': item.unit_snapshot,
        'package_quantity': format(item.package_quantity_snapshot.normalize(), 'f')
            if item.package_quantity_snapshot is not None else None,
        'display_label': item.display_label_snapshot,
        'unit_price': amount_string(item.unit_price, order.currency_snapshot),
        'subtotal': amount_string(item.subtotal, order.currency_snapshot),
    } for item in order.items], key=lambda item: item['sku_id'])
    resolved = order.quote_resolved
    if (economic_lines({'lines': lines}) != economic_lines(resolved)
            or amount_string(order.total_amount, order.currency_snapshot) != resolved.get('total')
            or resolved.get('currency') != order.currency_snapshot
            or resolved.get('country') != order.country_snapshot
            or resolved.get('registration') != str(order.registration_snapshot_id)
            or resolved.get('wholesaler') != str(order.wholesaler_id)
            or resolved.get('retailer') != str(order.retailer_id)):
        refuse('NEGOTIATION_CONTEXT_CHANGED', 'The source draft snapshots cannot be verified')
    return {'order_id': str(order.id), 'wholesaler': str(order.wholesaler_id),
            'retailer': str(order.retailer_id), 'country': order.country_snapshot,
            'currency': order.currency_snapshot, 'registration': str(order.registration_snapshot_id),
            'lines': lines, 'total': resolved['total'], 'notes': order.notes}


async def authoritative_now(db):
    # Transaction-start now() is deliberately not used at the lock boundary.
    return (await db.execute(text('SELECT clock_timestamp()'))).scalar_one()


async def require_unexpired(db, proposal):
    if await authoritative_now(db) >= proposal.expires_at:
        refuse('NEGOTIATION_EXPIRED', 'The merchant must confirm before the stated deadline')


async def _locked_source(db, order_id, wholesaler_id, retailer_id=None):
    filters = [Order.id == UUID(str(order_id)), Order.wholesaler_id == UUID(str(wholesaler_id)),
               Order.is_deleted.is_(False)]
    if retailer_id is not None:
        filters.append(Order.retailer_id == UUID(str(retailer_id)))
    order = (await db.execute(select(Order).where(*filters).with_for_update()
                              .execution_options(populate_existing=True))).scalar_one_or_none()
    if order is None:
        refuse('ORDER_NOT_FOUND', 'Order not found', status=404)
    await assert_binding(db, order.wholesaler_id, order.retailer_id)
    return order


async def _proposal(db, source, proposal_id, decision):
    proposal = (await db.execute(select(Proposal).where(
        Proposal.id == UUID(str(proposal_id)), Proposal.source_order_id == source.id,
        Proposal.wholesaler_id == source.wholesaler_id, Proposal.retailer_id == source.retailer_id,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if proposal is None:
        refuse('NEGOTIATION_NOT_FOUND', 'Proposal not found', status=404)
    _verify_proposal(proposal)
    if proposal.version != decision.version or not hmac.compare_digest(proposal.digest, decision.digest):
        refuse('NEGOTIATION_INTENT_CONFLICT', 'The proposal identity or accepted version changed')
    return proposal


async def _zero_effects(db, source):
    if source.status != OrderStatus.DRAFT:
        refuse('NEGOTIATION_SOURCE_CHANGED', 'Only a zero-effect draft can be negotiated')
    count = (await db.execute(text(
        'SELECT (SELECT count(*) FROM payments WHERE order_id=:oid) + '
        '(SELECT count(*) FROM order_credit_holds WHERE order_id=:oid) + '
        '(SELECT count(*) FROM inventory_reservations WHERE order_id=:oid) + '
        "(SELECT count(*) FROM ledger_entries WHERE reference_type='order' AND reference_id=:oid) + "
        "(SELECT count(*) FROM inventory_movements WHERE reference_type='order' AND reference_id=:oid)"
    ), {'oid': source.id})).scalar_one()
    if count:
        refuse('NEGOTIATION_SOURCE_CHANGED', 'The draft has retained economic effects')


def _verify_proposal(proposal):
    try:
        payload = proposal.payload
        expected = {'proposal_id': str(proposal.id), 'version': proposal.version,
                    'source_order_id': str(proposal.source_order_id),
                    'wholesaler': str(proposal.wholesaler_id), 'retailer': str(proposal.retailer_id),
                    'proposer': str(proposal.created_by),
                    'expires_at': proposal.expires_at.astimezone(timezone.utc).isoformat()}
        if (any(payload.get(key) != value for key, value in expected.items())
                or not hmac.compare_digest(proposal_digest(payload), proposal.digest)
                or payload['source']['order_id'] != str(proposal.source_order_id)
                or payload['source']['wholesaler'] != str(proposal.wholesaler_id)
                or payload['source']['retailer'] != str(proposal.retailer_id)):
            refuse('NEGOTIATION_INTEGRITY', 'The stored proposal identity cannot be verified')
        identifiers = ('sku_id', 'quantity', 'unit', 'package_quantity')
        if ([{k: line[k] for k in identifiers} for line in payload['lines']] !=
                [{k: line[k] for k in identifiers} for line in payload['source']['lines']]):
            refuse('NEGOTIATION_INTEGRITY', 'The proposed selection differs from its source')
        for key in ('country', 'currency', 'registration'):
            if payload[key] != payload['source'][key]:
                refuse('NEGOTIATION_INTEGRITY', 'The proposed trading context differs from its source')
    except (KeyError, TypeError, ValueError, AttributeError):
        refuse('NEGOTIATION_INTEGRITY', 'The stored proposal is malformed')


def _assert_source_snapshot(source, proposal):
    if order_snapshot(source) != proposal.payload['source']:
        refuse('NEGOTIATION_SOURCE_CHANGED', 'The original draft changed after this proposal')


def _accepted_fingerprint(proposal, actor_id):
    return proposal_digest({'proposal_id': str(proposal.id), 'version': proposal.version,
                            'digest': proposal.digest, 'actor': str(actor_id),
                            'operation': OPERATION})


def _accepted_quote(proposal):
    payload = deepcopy(proposal.payload)
    return {key: payload[key] for key in ('tenant', 'wholesaler', 'retailer', 'country',
            'currency', 'registration', 'lines', 'total')} | {
        'actor': str(proposal.decided_by), 'operation': OPERATION,
        'negotiation': {'id': str(proposal.id), 'version': proposal.version,
                        'digest': proposal.digest, 'expires_at': payload['expires_at']},
    }


async def _verify_accepted(db, proposal, source=None):
    if proposal.status != 'accepted' or not proposal.accepted_order_id or not proposal.decided_by:
        refuse('NEGOTIATION_CONSENT_REQUIRED', 'A durable customer acceptance is required')
    fingerprint = _accepted_fingerprint(proposal, proposal.decided_by)
    order = (await db.execute(select(Order).where(
        Order.id == proposal.accepted_order_id, Order.is_deleted.is_(False),
        Order.wholesaler_id == proposal.wholesaler_id, Order.retailer_id == proposal.retailer_id,
    ).execution_options(populate_existing=True))).scalar_one_or_none()
    if (order is None or order.replaces_order_id != proposal.source_order_id
            or order.creation_operation != OPERATION or order.created_by != proposal.decided_by
            or order.creation_key_digest != proposal.accept_key_digest
            or order.creation_fingerprint != fingerprint or proposal.accepted_intent_digest != fingerprint
            or order.quote_seen != _accepted_quote(proposal) or order.quote_resolved != _accepted_quote(proposal)):
        refuse('NEGOTIATION_INTEGRITY', 'The replacement cannot be bound to durable customer consent')
    if source is None:
        source = (await db.execute(select(Order).where(Order.id == proposal.source_order_id,
            Order.wholesaler_id == proposal.wholesaler_id, Order.retailer_id == proposal.retailer_id,
            Order.is_deleted.is_(False)).execution_options(populate_existing=True))).scalar_one_or_none()
    if source is None or source.status != OrderStatus.CANCELLED:
        refuse('NEGOTIATION_INTEGRITY', 'The accepted source was not atomically closed')
    _assert_source_snapshot(source, proposal)
    # Include each actual price and subtotal, not just an equal order total.
    actual = order_snapshot(order)
    if (economic_lines(actual) != economic_lines(proposal.payload)
            or actual['total'] != proposal.payload['total']):
        refuse('NEGOTIATION_INTEGRITY', 'The accepted line snapshots changed')
    return order


async def create_proposal(db, *, order_id, wholesaler_id, actor_id, request):
    source = await _locked_source(db, order_id, wholesaler_id)
    await _zero_effects(db, source)
    snapshot = order_snapshot(source)
    currency = await resolve_currency(db, wholesaler_id)
    pending = (await db.execute(select(Proposal.id).where(
        Proposal.source_order_id == source.id, Proposal.status == 'pending'))).first()
    if pending:
        refuse('NEGOTIATION_PENDING', 'Withdraw the existing proposal before offering a new one')
    expiry = request.expires_at.astimezone(timezone.utc)
    offered = {str(item.sku_id): item.unit_price for item in request.lines}
    if len(offered) != len(request.lines) or set(offered) != {line['sku_id'] for line in snapshot['lines']}:
        refuse('NEGOTIATION_SELECTION_CHANGED', 'Provide exactly one price for every original item', status=422)
    lines = deepcopy(snapshot['lines'])
    for line in lines:
        price = money(offered[line['sku_id']], currency.currency)
        line['unit_price'] = format(price, 'f')
        line['subtotal'] = format(money(price * line['quantity'], currency.currency), 'f')
    version = 1 + (await db.execute(select(func.coalesce(func.max(Proposal.version), 0)).where(
        Proposal.source_order_id == source.id))).scalar_one()
    pid = uuid4()
    payload = {'proposal_id': str(pid), 'version': version, 'source_order_id': str(source.id),
               'tenant': currency.tenant_schema, 'wholesaler': str(source.wholesaler_id),
               'retailer': str(source.retailer_id), 'proposer': str(actor_id),
               'country': currency.country, 'currency': currency.currency,
               'registration': currency.registration_id, 'expires_at': expiry.isoformat(),
               'source': snapshot, 'lines': lines,
               'total': format(money(sum((Decimal(line['subtotal']) for line in lines), Decimal(0)), currency.currency), 'f')}
    proposal = Proposal(id=pid, source_order_id=source.id, wholesaler_id=source.wholesaler_id,
        retailer_id=source.retailer_id, created_by=UUID(str(actor_id)), version=version,
        expires_at=expiry, payload=payload, digest=proposal_digest(payload), status='pending')
    _verify_proposal(proposal)
    await validate_negotiated_units(db, wholesaler_id=source.wholesaler_id, payload=payload)
    await require_unexpired(db, proposal)
    db.add(proposal)
    await db.flush()
    return proposal


async def decide_proposal(db, *, order_id, proposal_id, wholesaler_id, actor_id,
                          decision, action, retailer_id=None):
    if action not in {'withdrawn', 'rejected'}:
        refuse('NEGOTIATION_ACTION_INVALID', 'Unknown proposal decision', status=422)
    source = await _locked_source(db, order_id, wholesaler_id, retailer_id)
    proposal = await _proposal(db, source, proposal_id, decision)
    if proposal.status != 'pending':
        if proposal.status == action and proposal.decided_by == UUID(str(actor_id)):
            return proposal, True
        refuse('NEGOTIATION_ALREADY_DECIDED', 'This proposal already has a terminal decision')
    await _zero_effects(db, source)
    _assert_source_snapshot(source, proposal)
    proposal.status, proposal.decided_by = action, UUID(str(actor_id))
    proposal.decided_at = await authoritative_now(db)
    await db.flush()
    return proposal, False


async def accept_proposal(db, *, order_id, proposal_id, wholesaler_id, retailer_id,
                          actor_id, decision, idempotency_key):
    key_digest = creation_key_digest(idempotency_key)
    lock_key = proposal_digest({'tenant': str(wholesaler_id), 'retailer': str(retailer_id),
                                'actor': str(actor_id), 'operation': OPERATION, 'key': key_digest})
    await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),
                     {'key': int.from_bytes(bytes.fromhex(lock_key)[:8], 'big', signed=True)})
    source = await _locked_source(db, order_id, wholesaler_id, retailer_id)
    proposal = await _proposal(db, source, proposal_id, decision)
    existing = (await db.execute(select(Proposal.id).where(
        Proposal.wholesaler_id == source.wholesaler_id, Proposal.retailer_id == source.retailer_id,
        Proposal.decided_by == UUID(str(actor_id)), Proposal.accept_key_digest == key_digest,
    ))).scalar_one_or_none()
    if existing is not None and existing != proposal.id:
        refuse('NEGOTIATION_IDEMPOTENCY_CONFLICT', 'This key committed a different proposal')
    fingerprint = _accepted_fingerprint(proposal, actor_id)
    if proposal.status == 'accepted':
        if (proposal.decided_by != UUID(str(actor_id)) or proposal.accept_key_digest != key_digest
                or proposal.accepted_intent_digest != fingerprint):
            refuse('NEGOTIATION_IDEMPOTENCY_CONFLICT', 'Acceptance already committed under a different intent')
        await _verify_accepted(db, proposal, source)
        return proposal, True
    if proposal.status != 'pending':
        refuse('NEGOTIATION_ALREADY_DECIDED', 'This proposal already has a terminal decision')
    await _zero_effects(db, source)
    _assert_source_snapshot(source, proposal)
    await validate_negotiated_units(db, wholesaler_id=source.wholesaler_id, payload=proposal.payload)
    await require_unexpired(db, proposal)
    items = [{
        'sellable_unit_id': line['sku_id'], 'product_name': line['product_name'],
        'sku_code': line['sku_code'], 'unit_snapshot': line['unit'],
        'package_quantity_snapshot': Decimal(line['package_quantity']),
        'display_label_snapshot': line['display_label'], 'quantity': line['quantity'],
        'unit_price': Decimal(line['unit_price']),
    } for line in proposal.payload['lines']]
    async with db.begin_nested():
        order = await create_order(db=db, wholesaler_id=str(source.wholesaler_id),
            retailer_id=str(source.retailer_id), items=items, notes=source.notes, created_by=str(actor_id))
        proposal.status, proposal.decided_by = 'accepted', UUID(str(actor_id))
        proposal.decided_at = await authoritative_now(db)
        proposal.accept_key_digest, proposal.accepted_intent_digest = key_digest, fingerprint
        proposal.accepted_order_id = order.id
        quote = _accepted_quote(proposal)
        order.country_snapshot, order.currency_snapshot = quote['country'], quote['currency']
        order.registration_snapshot_id = UUID(quote['registration'])
        order.creation_operation, order.creation_key_digest = OPERATION, key_digest
        order.creation_fingerprint, order.quote_seen, order.quote_resolved = fingerprint, quote, quote
        order.replaces_order_id = source.id
        await db.flush()
        from services.order_command_service import OrderCommandService
        await OrderCommandService(db).cancel_order(source.id, updated_by=str(actor_id))
        await db.flush()
    return proposal, False


async def list_proposals(db, *, order_id, wholesaler_id, retailer_id=None):
    # Read paths do not take the command lock, but always enforce ownership/binding.
    filters = [Order.id == UUID(str(order_id)), Order.wholesaler_id == UUID(str(wholesaler_id)),
               Order.is_deleted.is_(False)]
    if retailer_id is not None:
        filters.append(Order.retailer_id == UUID(str(retailer_id)))
    source = (await db.execute(select(Order).where(*filters))).scalar_one_or_none()
    if source is None:
        refuse('ORDER_NOT_FOUND', 'Order not found', status=404)
    await assert_binding(db, source.wholesaler_id, source.retailer_id)
    proposals = (await db.execute(select(Proposal).where(
        (Proposal.source_order_id == source.id) | (Proposal.accepted_order_id == source.id),
        Proposal.wholesaler_id == source.wholesaler_id, Proposal.retailer_id == source.retailer_id)
        .order_by(Proposal.version.desc()).execution_options(populate_existing=True))).scalars().all()
    now = await authoritative_now(db)
    return [proposal_view(proposal, now=now) for proposal in proposals]


async def lock_confirmation_proposal(db, order):
    proposal = (await db.execute(select(Proposal).where(Proposal.accepted_order_id == order.id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if proposal is not None or order.creation_operation == OPERATION:
        if proposal is None:
            refuse('NEGOTIATION_CONSENT_REQUIRED', 'A persisted accepted proposal is required')
        _verify_proposal(proposal)
        await assert_binding(db, order.wholesaler_id, order.retailer_id)
        await _verify_accepted(db, proposal)
    return proposal


async def validate_negotiated_confirmation(db, order):
    proposal = await lock_confirmation_proposal(db, order)
    if proposal is None:
        return False
    await validate_negotiated_units(db, wholesaler_id=order.wholesaler_id, payload=proposal.payload)
    # This check follows all stock/unit/proposal lock waits, before economic writes.
    await require_unexpired(db, proposal)
    return True


def proposal_view(proposal, *, now=None):
    _verify_proposal(proposal)
    return {'id': str(proposal.id), 'source_order_id': str(proposal.source_order_id),
            'version': proposal.version, 'digest': proposal.digest, 'status': proposal.status,
            'expires_at': proposal.expires_at.isoformat(), 'expired': now is not None and now >= proposal.expires_at,
            'created_at': proposal.created_at.isoformat() if proposal.created_at else None,
            'accepted_order_id': str(proposal.accepted_order_id) if proposal.accepted_order_id else None,
            'currency': proposal.payload['currency'], 'country': proposal.payload['country'],
            'lines': proposal.payload['lines'], 'original_lines': proposal.payload['source']['lines'],
            'total': proposal.payload['total'], 'original_total': proposal.payload['source']['total'],
            'confirmation_required_before_expiry': True}
