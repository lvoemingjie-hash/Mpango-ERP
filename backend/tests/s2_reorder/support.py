"""Read-only economic evidence shared by real TCP tests and browser journeys.

The production APIs own catalog, price, stock and source creation. Historical
test setup writes, when required, are explicitly named in the test module;
this vector function opens a PostgreSQL READ ONLY transaction and never writes.
"""
from __future__ import annotations

import hashlib
import asyncio
import json
import os
import re
import stat
from pathlib import Path
from uuid import UUID
import uuid
import time

import asyncpg

def task_root():
    """An explicit task attachment is mandatory; no checkout ancestry fallback."""
    value = os.environ.get('S2_TASK_ROOT')
    if not value or not Path(value).is_absolute():
        raise RuntimeError('S2_TASK_RUNTIME_NOT_CONFIGURED: explicit absolute S2_TASK_ROOT required')
    root = Path(value).resolve(strict=True)
    config_value = os.environ.get('S2_PRIVATE_CONFIG')
    if not config_value or not Path(config_value).is_absolute():
        raise RuntimeError('S2_TASK_RUNTIME_NOT_CONFIGURED: explicit absolute S2_PRIVATE_CONFIG required')
    config = Path(config_value)
    if config.is_symlink() or config.resolve(strict=True).parent != root / 'private':
        raise RuntimeError('S2_TASK_PRIVATE_CONFIG_INVALID: config must belong to this task private directory')
    metadata = config.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RuntimeError('S2_TASK_PRIVATE_CONFIG_INVALID: owned 0600 regular file required')
    for helper in ('runtime_inputs.py', 's2_fixture_api.py', 's2_observed_app.py'):
        if not (root / 'work' / helper).is_file():
            raise RuntimeError('S2_TASK_RUNTIME_CAPSULE_NOT_CONFIGURED: missing ' + helper)
    return root


TASK_ROOT = task_root()


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


class CommitOverlapGate:
    """Hold one real outer commit and observe the actual durable-lock waiter.

    The task-only app attachment observes SQLAlchemy's outer before_commit;
    it never replaces a handler or authority. All lock observations below use
    a READ ONLY PostgreSQL transaction, scoped to the two exact lock identities.
    """
    def __init__(self, fixture, key):
        self.fixture = fixture
        self.key_digest = hashlib.sha256(key.encode('ascii')).hexdigest()
        scope = {'wid': fixture.account['wholesaler'], 'rid': fixture.account['retailer'],
                 'actor': fixture.account['customer'], 'operation': 'client-reorder',
                 'key': self.key_digest}
        canonical = json.dumps(scope, sort_keys=True, separators=(',', ':'),
                               ensure_ascii=True, allow_nan=False).encode('ascii')
        self.intent_identity = int.from_bytes(hashlib.sha256(canonical).digest()[:8], 'big', signed=True)
        self.gate_identity = int.from_bytes(uuid.uuid4().bytes[:8], 'big', signed=True)
        self.active_path = TASK_ROOT / 'private' / 'commit-overlap-active.json'
        directory = TASK_ROOT / 'private' / 'concurrency-events'
        directory.mkdir(exist_ok=True, mode=0o700)
        self.event_path = directory / (fixture.country + '-' + uuid.uuid4().hex + '.json')
        self.evidence_path = self.event_path.with_suffix('.locks.json')
        self.evidence = {'country': fixture.country, 'events': [],
                         'key_digest': self.key_digest, 'intent_identity': self.intent_identity,
                         'gate_identity': self.gate_identity}
        self.connection = None
        self.released = False
        self.first = None

    async def __aenter__(self):
        self.connection = await asyncpg.connect(self.fixture.env['APP_DB_DSN'], command_timeout=10)
        try:
            self.holder_pid = await self.connection.fetchval('SELECT pg_backend_pid()')
            await self.connection.execute('SELECT pg_advisory_lock($1)', self.gate_identity)
            descriptor = os.open(self.active_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as stream:
                json.dump({'operation': 'client-reorder', 'schema': self.fixture.account['schema'],
                           'key_digest': self.key_digest, 'gate_identity': self.gate_identity,
                           'event_path': str(self.event_path)}, stream, sort_keys=True)
                stream.write('\n')
        except BaseException:
            await self.connection.close()
            raise
        self.evidence['events'].append({'event': 'GATE_HELD', 'pid': self.holder_pid, 'utc_ns': time.time_ns()})
        return self

    async def _lock_rows(self):
        gate_hi, gate_lo = (self.gate_identity >> 32) & 0xffffffff, self.gate_identity & 0xffffffff
        intent_hi, intent_lo = (self.intent_identity >> 32) & 0xffffffff, self.intent_identity & 0xffffffff
        async with self.connection.transaction(readonly=True):
            assert await self.connection.fetchval('SHOW transaction_read_only') == 'on'
            return [dict(row) for row in await self.connection.fetch(
                "SELECT l.pid,l.granted,l.mode,l.classid::bigint AS high,l.objid::bigint AS low,"
                "a.state,a.wait_event_type,a.wait_event,a.xact_start,a.query_start,a.query,"
                "pg_blocking_pids(l.pid) AS blocking_pids "
                "FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid "
                "WHERE l.locktype='advisory' AND l.objsubid=1 AND "
                "((l.classid::bigint=$1 AND l.objid::bigint=$2) OR "
                "(l.classid::bigint=$3 AND l.objid::bigint=$4)) ORDER BY l.pid,l.granted",
                gate_hi, gate_lo, intent_hi, intent_lo)]

    async def wait_first(self):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.event_path.exists():
                try:
                    event = json.loads(self.event_path.read_text())
                except (json.JSONDecodeError, OSError):
                    # The writer may still be mid-write; the deadline bounds this.
                    await asyncio.sleep(0.02)
                    continue
                rows = await self._lock_rows()
                pid = event['backend_pid']
                gate_wait = [r for r in rows if r['pid'] == pid and not r['granted']
                             and r['high'] == (self.gate_identity >> 32) & 0xffffffff
                             and r['low'] == self.gate_identity & 0xffffffff]
                intent_owned = [r for r in rows if r['pid'] == pid and r['granted']
                                and r['high'] == (self.intent_identity >> 32) & 0xffffffff
                                and r['low'] == self.intent_identity & 0xffffffff]
                if gate_wait and intent_owned and self.holder_pid in gate_wait[0]['blocking_pids']:
                    assert event['event'] == 'BEFORE_OUTER_COMMIT' and not event['nested_transaction']
                    self.first = event
                    self.evidence['events'].append({'event': 'FIRST_UNCOMMITTED_BEFORE_OUTER_COMMIT',
                        'utc_ns': time.time_ns(), 'app_event': event, 'lock_rows': rows})
                    return event
            await asyncio.sleep(0.02)
        self.evidence['events'].append({'event': 'FIRST_GATE_TIMEOUT', 'lock_rows': await self._lock_rows()})
        raise AssertionError('S2_CONCURRENCY_FIRST_BEFORE_COMMIT_GATE_NOT_OBSERVED')

    async def wait_second(self):
        assert self.first is not None
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            rows = await self._lock_rows()
            first_pid = self.first['backend_pid']
            waits = [r for r in rows if r['pid'] not in (first_pid, self.holder_pid)
                     and not r['granted'] and first_pid in r['blocking_pids']
                     and r['high'] == (self.intent_identity >> 32) & 0xffffffff
                     and r['low'] == self.intent_identity & 0xffffffff
                     and r['wait_event_type'] == 'Lock' and r['wait_event'] == 'advisory'
                     and 'pg_advisory_xact_lock' in r['query']]
            first_still_waits = [r for r in rows if r['pid'] == first_pid and not r['granted']
                                 and self.holder_pid in r['blocking_pids']]
            if waits and first_still_waits:
                assert waits[0]['xact_start'] is not None
                self.evidence['events'].append({'event': 'SECOND_REAL_SUBMIT_DURABLE_LOCK_WAIT',
                    'utc_ns': time.time_ns(), 'second_pid': waits[0]['pid'], 'first_pid': first_pid,
                    'lock_rows': rows, 'first_order_id': self.first['order_id']})
                return waits[0]['pid']
            await asyncio.sleep(0.02)
        self.evidence['events'].append({'event': 'SECOND_OVERLAP_TIMEOUT', 'lock_rows': await self._lock_rows()})
        raise AssertionError('S2_CONCURRENCY_SECOND_BEARING_PATH_BEFORE_FIRST_COMMIT_NOT_OBSERVED')

    async def release(self):
        if not self.released:
            self.active_path.unlink(missing_ok=True)
            assert await self.connection.fetchval('SELECT pg_advisory_unlock($1)', self.gate_identity)
            self.released = True
            self.evidence['events'].append({'event': 'GATE_RELEASED', 'utc_ns': time.time_ns()})

    async def __aexit__(self, *exception):
        try:
            await self.release()
        finally:
            if self.connection is not None:
                await self.connection.close()
            self.evidence_path.write_text(json.dumps(self.evidence, default=str, indent=2, sort_keys=True) + '\n')
            self.evidence_path.chmod(0o600)


def commit_overlap_gate(fixture, key):
    return CommitOverlapGate(fixture, key)


async def assert_two_requests_overlap(gate):
    return await gate.wait_second()
