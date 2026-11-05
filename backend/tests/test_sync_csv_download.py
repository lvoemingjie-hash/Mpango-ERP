"""Sync CSV contracts with real endpoints/RBAC and bounded session I/O doubles.

No live database, JWT resolution or production role topology is claimed here.
"""
import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
from types import SimpleNamespace
from uuid import UUID

import anyio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.dialects import postgresql

from api.context import AuthContext, TenantContext, attach_auth_context, attach_tenant_context
from api.v1 import data_export
from core.security import TokenPayload
from db.tenant_filter import get_current_tenant_id, get_current_tenant_schema
from models.order import OrderStatus


TID = UUID('11111111-1111-4111-8111-111111111111')
OTHER = UUID('22222222-2222-4222-8222-222222222222')
UID = UUID('33333333-3333-4333-8333-333333333333')
NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def order(index=1, notes='Customer note', currency='UGX'):
    return SimpleNamespace(id=UUID(int=index), wholesaler_id=TID, status=OrderStatus.CONFIRMED,
        total_amount=Decimal('125.00'), currency_snapshot=currency, retailer_id=OTHER,
        notes=notes, items=[object()], created_at=NOW, updated_at=NOW)


def stock(index=1):
    return SimpleNamespace(id=UUID(int=index), quantity_on_hand=Decimal('12.00'),
        quantity_reserved=Decimal('2.50'), created_at=NOW, updated_at=NOW,
        sku=SimpleNamespace(sku_code='=SUM(1,2)', name='产品, "quote"', category=' @SUM(1)',
                            unit='\tunit', is_active=True))


class Session:
    def __init__(self, rows=(), fail=False):
        self.rows = list(rows)
        self.calls = []
        self.fail = fail
        self.closed = False

    async def execute(self, statement):
        assert not self.closed, 'CSV_MUST_NOT_USE_CLOSED_REQUEST_SESSION'
        assert get_current_tenant_id() == str(TID)
        assert get_current_tenant_schema() == 't_csv_contract'
        self.calls.append(statement)
        await anyio.lowlevel.checkpoint()
        if self.fail:
            raise RuntimeError('CSV_OWNED_READ_FAULT')
        start = statement._offset_clause.value
        size = statement._limit_clause.value
        rows = self.rows[start:start + size]
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))


@pytest.fixture
def world(monkeypatch):
    import database.session as sessions
    w = SimpleNamespace(token=TokenPayload(user_id=str(UID), tenant_id=str(TID),
        tenant_schema='t_csv_contract', roles=['user']), permissions=['exports:create'],
        authenticated=True, has_tenant=True, opened=[], closed=[], request_db=Session(),
        export_db=Session(), schema_rows={'t_csv_foreign': [stock(999)]})

    async def owned(schema):
        assert schema == w.token.tenant_schema == 't_csv_contract'
        assert w.export_db is not w.request_db
        w.opened.append(schema)
        try:
            yield w.export_db
        finally:
            # This checkpoint would be interrupted without the real shield.
            await anyio.lowlevel.checkpoint()
            w.export_db.closed = True
            w.closed.append(schema)

    monkeypatch.setattr(sessions, 'get_tenant_db', owned)
    app = FastAPI()

    @app.middleware('http')
    async def declared_context(request, call_next):
        if w.authenticated:
            attach_auth_context(request, AuthContext(token=w.token, raw_token='unit-context'))
        if w.has_tenant:
            user = SimpleNamespace(roles=[SimpleNamespace(permissions=[
                SimpleNamespace(code=code) for code in w.permissions])])
            attach_tenant_context(request, TenantContext(str(TID), 't_csv_contract', w.request_db, user))
        return await call_next(request)

    app.include_router(data_export.router, prefix='/api/v1')
    w.app = app
    return w


@pytest.mark.parametrize('text', ['=SUM(1,2)', '+SUM(1)', '-1+2', '@SUM(1)', ' =1',
    '\t=1', '\r=1', '\n=1', '\tplain', '\ufeff=1', '\x00 =1', '\u00a0=1'])
def test_formula_text_is_neutralized_without_losing_csv_quoting(text):
    assert next(csv.reader(io.StringIO(data_export._csv_row([text])))) == ["'" + text]


def test_safe_text_unicode_quotes_and_typed_negative_numbers_keep_values():
    values = ['产品, "quoted"', 'line one\nline two', 'plain', "'already text", '',
              Decimal('-12.30'), Decimal('0.00'), 3]
    row = next(csv.reader(io.StringIO(data_export._csv_row(values))))
    assert row == ['产品, "quoted"', 'line one\nline two', 'plain', "'already text", '', '-12.30', '0.00', '3']


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['orders', 'inventory'])
async def test_bom_headers_and_empty_export_have_no_extra_data(world, kind):
    async with AsyncClient(transport=ASGITransport(app=world.app), base_url='http://csv.test') as client:
        response = await client.get('/api/v1/' + kind + '/export')
    assert response.status_code == 200
    assert response.content.startswith(b'\xef\xbb\xbf')
    assert response.content.count(b'\xef\xbb\xbf') == 1
    assert response.headers['content-type'].lower() == 'text/csv; charset=utf-8'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-disposition'].startswith('attachment; filename="' + kind + '_export_')
    rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert len(rows) == 1 and rows[0][0] == ('Order ID' if kind == 'orders' else 'Stock ID')
    assert world.opened == world.closed == ['t_csv_contract']
    assert not world.request_db.calls


@pytest.mark.parametrize('sign,ascii_sign', [
    pytest.param('＝', '=', id='equals'),
    pytest.param('＋', '+', id='plus'),
    pytest.param('－', '-', id='minus'),
    pytest.param('＠', '@', id='at'),
])
def test_r2_fullwidth_and_ascii_formula_signs_preserve_original_glyphs(sign, ascii_sign):
    for prefix in ('', ' ', '\t', '\r', '\n', '\ufeff', '\x00\x1f ', '\u00a0', '\u3000'):
        for marker in (sign, ascii_sign):
            text = prefix + marker + 'SUM(1,2);"产品"'
            actual = next(csv.reader(io.StringIO(data_export._csv_row([text]))))
            assert actual == ["'" + text], 'CSV_R2_FULLWIDTH_FORMULA_NOT_NEUTRALIZED'


def test_r2_comma_csv_keeps_delimiters_quotes_and_newlines_inside_cells():
    values = ['plain,=1', 'plain;＋1', '"quoted",@1', 'line one\n=1',
              '=SUM(1,2);"quoted"\nnext', '  +1,2;"x"', '普通,文本;"字符"']
    expected = values[:4] + ["'" + text for text in values[4:6]] + values[6:]
    encoded = data_export._csv_row(values).encode('utf-8')
    rows = list(csv.reader(io.StringIO(encoded.decode('utf-8'), newline=''), delimiter=','))
    assert rows == [expected], 'CSV_R2_DELIMITER_CREATED_EXTRA_CELL_OR_ROW'
    assert len(rows[0]) == len(values)


def test_r2_safe_unicode_ids_leading_zeros_and_typed_negatives_are_unchanged():
    values = ['产品＝新品＋大号－蓝色＠店铺', '0000123', str(TID), '', "'already text",
              Decimal('-12.30'), -2, Decimal('0.00')]
    actual = next(csv.reader(io.StringIO(data_export._csv_row(values))))
    assert actual == values[:5] + ['-12.30', '-2', '0.00']


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['orders', 'inventory'])
async def test_r2_route_bytes_keep_fullwidth_formulas_in_one_safe_cell(world, kind):
    payloads = ['＝SUM(1,2);"quoted"\nnext', ' ＋1,2;"x"',
                '\x01－1+2,"x";next', '\u3000＠SUM(1,2);"x"']
    if kind == 'orders':
        world.export_db.rows = [order(i, notes=value) for i, value in enumerate(payloads, 1)]
        expected_payloads = [value.replace('\n', ' ') for value in payloads]
        column, width = 5, 9
    else:
        world.export_db.rows = [stock(i) for i in range(1, len(payloads) + 1)]
        for row, value in zip(world.export_db.rows, payloads):
            row.sku.sku_code = value
        expected_payloads = payloads
        column, width = 1, 10
    async with AsyncClient(transport=ASGITransport(app=world.app), base_url='http://csv.test') as client:
        response = await client.get('/api/v1/' + kind + '/export')
    assert response.status_code == 200
    assert response.content.startswith(b'\xef\xbb\xbf')
    assert response.content.count(b'\xef\xbb\xbf') == 1
    assert response.headers['content-type'].lower() == 'text/csv; charset=utf-8'
    rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'), newline=''), delimiter=','))
    assert len(rows) == len(payloads) + 1 and all(len(row) == width for row in rows)
    assert [row[column] for row in rows[1:]] == ["'" + value for value in expected_payloads], (
        'CSV_R2_ROUTE_FULLWIDTH_FORMULA_NOT_NEUTRALIZED')
    assert world.opened == world.closed == ['t_csv_contract'] and world.export_db.closed
    assert not world.request_db.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['orders', 'inventory'])
async def test_two_batches_use_only_token_schema_and_keep_all_rows(world, kind):
    factory = order if kind == 'orders' else stock
    world.export_db.rows = [factory(i) for i in range(1, 503)]
    async with AsyncClient(transport=ASGITransport(app=world.app), base_url='http://csv.test') as client:
        response = await client.get('/api/v1/' + kind + '/export')
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert len(rows) == 503
    assert {r[0] for r in rows[1:]} == {str(UUID(int=i)) for i in range(1, 503)}
    assert str(world.schema_rows['t_csv_foreign'][0].id) not in {r[0] for r in rows[1:]}
    assert len(world.export_db.calls) == 2 and world.opened == world.closed == ['t_csv_contract']
    for statement in world.export_db.calls:
        compiled = statement.compile(dialect=postgresql.dialect())
        assert 'is_deleted IS false' in str(compiled)
        assert len(statement._order_by_clauses) == 2
        if kind == 'orders':
            assert 'orders.wholesaler_id =' in str(compiled) and TID in compiled.params.values()
    if kind == 'inventory':
        assert rows[1][1:6] == ["'=SUM(1,2)", '产品, "quote"', "' @SUM(1)", "'\tunit", '12.00']
    assert not world.request_db.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('currency', ['UGX', 'KES', None])
async def test_order_currency_snapshot_and_notes_formula_are_retained(world, currency):
    world.export_db.rows = [order(notes='=SUM(1,2)', currency=currency)]
    async with AsyncClient(transport=ASGITransport(app=world.app), base_url='http://csv.test') as client:
        response = await client.get('/api/v1/orders/export?status=confirmed')
    rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[1][2] == '125.00' and rows[1][3] == (currency or 'LEGACY_CURRENCY_UNVERIFIED')
    assert rows[1][5] == "'=SUM(1,2)"
    assert OrderStatus.CONFIRMED in world.export_db.calls[0].compile().params.values()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,query,code', [
    ('orders', 'status=not-a-status', 'INVALID_STATUS_FILTER'),
    ('orders', 'status=', 'INVALID_STATUS_FILTER'),
    ('orders', 'status=%20confirmed', 'INVALID_STATUS_FILTER'),
    ('orders', 'status=confirmed&status=paid', 'INVALID_EXPORT_FILTER'),
    ('orders', 'retailer_id=foreign', 'INVALID_EXPORT_FILTER'),
    ('orders', 'tenant_schema=t_csv_foreign', 'INVALID_EXPORT_FILTER'),
    ('inventory', 'tenant_id=foreign', 'INVALID_EXPORT_FILTER'),
    ('inventory', 'status=confirmed', 'INVALID_EXPORT_FILTER'),
    ('inventory', 'format=csv&format=csv', 'INVALID_EXPORT_FILTER'),
    ('orders', 'format=xlsx', 'UNSUPPORTED_FORMAT'),
    ('inventory', 'format=xlsx', 'UNSUPPORTED_FORMAT'),
])
async def test_illegal_filters_fail_before_stream_opens(world, kind, query, code):
    async with AsyncClient(transport=ASGITransport(app=world.app), base_url='http://csv.test') as client:
        response = await client.get('/api/v1/' + kind + '/export?' + query)
    assert response.status_code == 400 and response.json()['detail']['code'] == code
    assert not world.opened and not world.export_db.calls
    assert 'content-disposition' not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['orders', 'inventory'])
@pytest.mark.parametrize('denial,expected,code', [('permission', 403, 'PERMISSION_DENIED'),
    ('auth', 401, 'UNAUTHENTICATED'), ('tenant', 403, 'TENANT_CONTEXT_REQUIRED')])
async def test_real_rbac_dependency_refuses_without_export_authority(world, kind, denial, expected, code):
    if denial == 'permission':
        world.permissions = ['orders:read', 'inventory:read']
    elif denial == 'auth':
        world.authenticated = False
    else:
        world.has_tenant = False
    async with AsyncClient(transport=ASGITransport(app=world.app), base_url='http://csv.test') as client:
        response = await client.get('/api/v1/' + kind + '/export')
    assert response.status_code == expected and response.json()['detail']['code'] == code
    assert not world.opened


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['orders', 'inventory'])
@pytest.mark.parametrize('finish', ['complete', 'read_error', 'cancelled_close'])
async def test_owned_stream_survives_closed_request_and_always_finishes_cleanup(world, kind, finish):
    world.export_db.rows = [order() if kind == 'orders' else stock()]
    export = data_export.export_orders_csv if kind == 'orders' else data_export.export_inventory_csv
    kwargs = {'format': 'csv', 'token': world.token, 'db': world.request_db}
    if kind == 'orders':
        kwargs['status_filter'] = None
    before = (get_current_tenant_id(), get_current_tenant_schema())
    response = await export(**kwargs)
    world.request_db.closed = True
    iterator = response.body_iterator
    first = await anext(iterator)
    assert first.startswith('\ufeff') and ('Order ID' if kind == 'orders' else 'Stock ID') in first
    if finish == 'read_error':
        world.export_db.fail = True
        with pytest.raises(RuntimeError, match='^CSV_OWNED_READ_FAULT$'):
            await anext(iterator)
    elif finish == 'cancelled_close':
        with anyio.CancelScope() as scope:
            scope.cancel()
            await iterator.aclose()
    else:
        content = ''.join([chunk async for chunk in iterator])
        assert str(UUID(int=1)) in content
    await iterator.aclose()
    assert world.export_db.closed and world.opened == world.closed == ['t_csv_contract']
    assert (get_current_tenant_id(), get_current_tenant_schema()) == before
    assert not world.request_db.calls
