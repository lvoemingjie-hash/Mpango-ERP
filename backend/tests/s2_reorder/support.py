"""Read-only economic evidence shared by real TCP tests and browser journeys.

The production APIs own catalog, price, stock and source creation. Historical
test setup writes, when required, are explicitly named in the test module;
this vector function opens a PostgreSQL READ ONLY transaction and never writes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from uuid import UUID

import asyncpg

TASK_ROOT = Path(os.environ.get('S2_TASK_ROOT', Path(__file__).resolve().parents[4]))


def _runtime():
    from runtime_inputs import load_runtime
    return load_runtime()


def _uuid_array(values):
    return sorted({UUID(str(value)) for value in values}, key=str)


async def economic_vector(schema, order_ids, sku_ids, wholesaler, retailer, *,
                          dsn=None, evidence_name=None):
    """Full retained rows, scoped by exact source/draft/SKU IDs and binding."""
    assert re.fullmatch(r't_[0-9a-f]{32}', schema), 'S2_VECTOR_CANONICAL_SCHEMA'
    orders, skus = _uuid_array(order_ids), _uuid_array(sku_ids)
    connection = await asyncpg.connect(dsn or _runtime()['APP_DB_DSN'])
    vector = {}
    try:
        async with connection.transaction(readonly=True):
            await connection.execute('SELECT set_config(\'search_path\', $1, true)', schema + ',public')
            assert await connection.fetchval('SHOW transaction_read_only') == 'on'
            queries = {
                'orders': ('SELECT * FROM orders WHERE id=ANY($1::uuid[]) ORDER BY id', orders),
                'items': ('SELECT * FROM order_items WHERE order_id=ANY($1::uuid[]) ORDER BY id', orders),
                'payments': ('SELECT * FROM payments WHERE order_id=ANY($1::uuid[]) ORDER BY id', orders),
                'declarations': ('SELECT * FROM payment_declarations WHERE order_id=ANY($1::uuid[]) ORDER BY id', orders),
                'ledger': ('SELECT * FROM ledger_entries WHERE reference_id=ANY($1::uuid[]) '
                           'OR reference_id IN (SELECT id FROM payments WHERE order_id=ANY($1::uuid[])) ORDER BY id', orders),
                'reservations': ('SELECT * FROM inventory_reservations WHERE order_id=ANY($1::uuid[]) ORDER BY id', orders),
                'holds': ('SELECT * FROM order_credit_holds WHERE order_id=ANY($1::uuid[]) ORDER BY id', orders),
                'order_movements': ('SELECT * FROM inventory_movements WHERE reference_id=ANY($1::uuid[]) ORDER BY id', orders),
                'stocks': ('SELECT * FROM inventory_stocks WHERE sku_id=ANY($1::uuid[]) ORDER BY id', skus),
                'stock_movements': ('SELECT * FROM inventory_movements WHERE sku_id=ANY($1::uuid[]) ORDER BY id', skus),
            }
            for name, (query, ids) in queries.items():
                vector[name] = [dict(row) for row in await connection.fetch(query, ids)]
            vector['binding'] = [dict(row) for row in await connection.fetch(
                'SELECT * FROM public.wholesaler_retailer_bindings '
                'WHERE wholesaler_id=$1 AND retailer_id=$2 ORDER BY id',
                UUID(str(wholesaler)), UUID(str(retailer)))]
    finally:
        await connection.close()
    # Normalize exact Decimal and timestamp values; no totals-only comparison.
    vector = json.loads(json.dumps(vector, default=str, sort_keys=True))
    if evidence_name:
        assert re.fullmatch(r'[A-Za-z0-9._-]+', evidence_name)
        directory = TASK_ROOT / 'private' / 'backend-projections'
        directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / (evidence_name + '.json')
        path.write_text(json.dumps(vector, indent=2, sort_keys=True) + '\n')
        path.chmod(0o600)
    return vector


async def vector_for(fixture, orders, products, *, label=None):
    if label and hasattr(fixture, 'evidence_suffix'):
        label += '-' + fixture.evidence_suffix
    return await economic_vector(fixture.account['schema'], orders,
        [product['sku_id'] for product in products], fixture.account['wholesaler'],
        fixture.account['retailer'], dsn=fixture.env['APP_DB_DSN'], evidence_name=label)


def assert_zero_draft_effects(vector):
    for name in ('payments', 'declarations', 'ledger', 'reservations', 'holds', 'order_movements'):
        assert vector[name] == [], 'S2_NEW_DRAFT_ZERO_' + name.upper()
    assert len(vector['orders']) == 1, 'S2_NEW_ONE_ORDER'
    order = vector['orders'][0]
    assert order['status'] == 'draft', 'S2_NEW_DRAFT_STATUS'
    assert order['replaces_order_id'] is None, 'S2_NO_SOURCE_REPLACEMENT'


async def count_intent(fixture, key):
    connection = await asyncpg.connect(fixture.env['APP_DB_DSN'])
    try:
        async with connection.transaction(readonly=True):
            await connection.execute('SELECT set_config(\'search_path\', $1, true)', fixture.account['schema'] + ',public')
            return await connection.fetchval(
                "SELECT count(*) FROM orders WHERE creation_operation='client-reorder' "
                'AND created_by=$1 AND retailer_id=$2 AND wholesaler_id=$3 AND creation_key_digest=$4',
                UUID(fixture.account['customer']), UUID(fixture.account['retailer']),
                UUID(fixture.account['wholesaler']), hashlib.sha256(key.encode('ascii')).hexdigest())
    finally:
        await connection.close()


def decisions(preview):
    return [{key: value for key, value in row['selection'].items() if value is not None}
            for row in preview['rows']]


def submit_body(preview, *, selections=None, notes=None):
    body = {'selections': selections if selections is not None else decisions(preview),
            'quote_token': preview['quote']['quote_token']}
    if notes is not None:
        body['notes'] = notes
    return body


async def submit_reorder(fixture, source, preview, *, key=None, body=None, expected=201):
    import uuid
    payload = {**(submit_body(preview) if body is None else body), 'source_order_id': source['id']}
    return await fixture.request('POST', '/api/v1/client/orders', payload, expected=expected,
        headers={'X-Idempotency-Key': key or 's2-test-' + uuid.uuid4().hex})


async def controlled_history_setup(fixture, sql, *parameters, reason):
    """Explicit fixture setup only, separate from all READ ONLY vectors."""
    assert reason.startswith('DECLARED_HISTORY_FIXTURE:'), 'S2_LABEL_HISTORY_SETUP'
    assert re.fullmatch(r't_[0-9a-f]{32}', fixture.account['schema'])
    connection = await asyncpg.connect(fixture.env['APP_DB_DSN'])
    try:
        async with connection.transaction():
            await connection.execute('SELECT set_config(\'search_path\', $1, true)', fixture.account['schema'] + ',public')
            await connection.execute(sql, *parameters)
    finally:
        await connection.close()
    directory = TASK_ROOT / 'private' / 'backend-history-setup'
    directory.mkdir(exist_ok=True, mode=0o700)
    import uuid
    path = directory / (uuid.uuid4().hex + '.json')
    path.write_text(json.dumps({'reason': reason, 'sql': sql, 'parameters': parameters}, default=str, indent=2) + '\n')
    path.chmod(0o600)
