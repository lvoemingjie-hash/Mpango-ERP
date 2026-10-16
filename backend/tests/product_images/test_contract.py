"""Finite component contracts. These are not a full-app JWT or DB acceptance."""
import asyncio
import io
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from PIL import Image
from starlette.requests import Request

from schemas.product_image import image_state
from services.product_image_processor import _decode
from services.product_image_service import bounded_body, expected_revision
from services.product_image_storage import MAX_INPUT, MediaStore
from tests.async_test_utils import run_coroutine


def fixture_image(kind='PNG', size=(100, 80)):
    out = io.BytesIO()
    Image.new('RGB', size, '#267a64').save(out, format=kind)
    return out.getvalue()


@pytest.mark.parametrize('kind', ['JPEG', 'PNG', 'WEBP'])
def test_real_decoder_static_formats_strip_metadata(kind):
    variants = _decode(fixture_image(kind), kind)
    for key, limit in [('thumb', 80 * 1024), ('detail', 300 * 1024)]:
        data, width, height = variants[key]
        assert 0 < len(data) <= limit
        with Image.open(io.BytesIO(data)) as actual:
            assert actual.format == 'WEBP' and actual.n_frames == 1
            assert actual.size == (width, height) and not actual.getexif()


@pytest.mark.parametrize('raw,format_name', [(b'<svg/>', 'PNG'), (b'\x89PNG\r\n', 'PNG'), (fixture_image(), 'JPEG')])
def test_decoder_refuses_invalid_or_disguised(raw, format_name):
    with pytest.raises(HTTPException) as failure:
        _decode(raw, format_name)
    assert failure.value.detail['code'] == 'IMAGE_INVALID'


def test_decoder_refuses_oversized_dimensions():
    with pytest.raises(HTTPException) as failure:
        _decode(fixture_image(size=(4097, 1)), 'PNG')
    assert failure.value.status_code == 422


def test_decoder_refuses_animated_webp():
    out = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(out, format='WEBP', save_all=True,
        append_images=[Image.new('RGB', (8, 8), 'blue')], duration=50, loop=0)
    with pytest.raises(HTTPException) as failure:
        _decode(out.getvalue(), 'WEBP')
    assert failure.value.status_code == 422


def test_real_decoder_strips_exif_and_applies_orientation():
    source = Image.new('RGB', (100, 80), 'green')
    exif = Image.Exif(); exif[0x010F] = 'fixture camera'; exif[0x0112] = 6
    raw = io.BytesIO(); source.save(raw, format='JPEG', exif=exif)
    variants = _decode(raw.getvalue(), 'JPEG')
    with Image.open(io.BytesIO(variants['detail'][0])) as output:
        assert output.size == (80, 100) and not output.getexif()


def test_hard_timeout_reaps_its_actual_child(monkeypatch):
    import subprocess
    import sys
    import services.product_image_processor as processor
    native = subprocess.Popen
    owned = []
    def slow(*args, **kwargs):
        child = native([sys.executable, '-I', '-c', 'import time; time.sleep(30)'], **kwargs)
        owned.append(child)
        return child
    monkeypatch.setattr(processor.subprocess, 'Popen', slow)
    with pytest.raises(HTTPException) as failure:
        processor._decode(fixture_image(), 'PNG')
    assert failure.value.detail['code'] == 'IMAGE_PROCESS_TIMEOUT'
    assert len(owned) == 1 and owned[0].poll() is not None, 'IMAGE_TIMEOUT_MUST_REAP'


def test_init_failure_releases_only_owned_memfd(monkeypatch):
    import services.product_image_processor as processor
    native = os.memfd_create
    owned = []
    def fail_second(*args, **kwargs):
        if owned:
            raise OSError('fixture initialization failure')
        fd = native(*args, **kwargs); owned.append(fd); return fd
    monkeypatch.setattr(processor.os, 'memfd_create', fail_second)
    with pytest.raises(HTTPException) as failure:
        processor._decode(fixture_image(), 'PNG')
    assert failure.value.detail['code'] == 'IMAGE_PROCESS_UNAVAILABLE'
    with pytest.raises(OSError):
        os.fstat(owned[0])


def test_revision_zero_and_deleted_tombstone_are_readable():
    pid = uuid4()
    assert image_state(None, pid) == {'image_revision': 0, 'image': None}
    row = SimpleNamespace(image_revision=4, current_version=None)
    assert image_state(row, pid) == {'image_revision': 4, 'image': None}


@pytest.mark.parametrize('value,status', [(None, 428), ('-1', 422), ('1.0', 422), ('１２', 422), ('1'*19, 422)])
def test_invalid_revision_not_silently_upgraded(value, status):
    with pytest.raises(HTTPException) as failure:
        expected_revision(value)
    assert failure.value.status_code == status


@pytest.mark.parametrize('declared', ['1', str(MAX_INPUT), '999999999999'])
def test_stream_limit_independent_of_content_length(declared):
    seen = []
    async def receive():
        seen.append(1)
        return {'type': 'http.request', 'body': b'x' * (MAX_INPUT + 1), 'more_body': True}
    request = Request({'type': 'http', 'method': 'PUT', 'headers': [(b'content-length', declared.encode())]}, receive)
    with pytest.raises(HTTPException) as failure:
        run_coroutine(bounded_body(request))
    assert failure.value.detail['code'] == 'IMAGE_INPUT_LIMIT', 'IMAGE_BYTE_GATE_MUST_REJECT'
    assert len(seen) == 1


def test_body_chunking_and_empty_input():
    async def run(chunks):
        async def receive():
            body = chunks.pop(0)
            return {'type': 'http.request', 'body': body, 'more_body': bool(chunks)}
        return await bounded_body(Request({'type': 'http', 'method': 'PUT', 'headers': []}, receive))
    assert run_coroutine(run([b'ab', b'cd'])) == b'abcd'
    with pytest.raises(HTTPException):
        run_coroutine(run([b'']))


def test_descriptor_storage_roundtrip_and_symlink_refusal(tmp_path):
    os.chmod(tmp_path, 0o700)
    store = MediaStore(str(tmp_path))
    lock = store.acquire_write()
    tenant, product = uuid4(), uuid4()
    try:
        variants = _decode(fixture_image(), 'PNG')
        version, metadata = store.publish(tenant, product, variants)
        assert store.read(tenant, product, version, 'thumb', metadata['thumb']) == variants['thumb'][0]
        source = tmp_path / str(tenant) / str(product) / str(version) / 'thumb.webp'
        original = source.read_bytes()
        source.unlink()
        decoy = tmp_path / 'decoy'; decoy.write_bytes(original); os.chmod(decoy, 0o600)
        source.symlink_to(decoy)
        with pytest.raises(OSError):
            store.read(tenant, product, version, 'thumb', metadata['thumb'])
        assert decoy.read_bytes() == original
    finally:
        os.close(lock); store.close()


def test_root_symlink_refused_without_changing_decoy(tmp_path):
    root = tmp_path / 'actual'; root.mkdir(mode=0o700)
    link = tmp_path / 'link'; link.symlink_to(root, target_is_directory=True)
    with pytest.raises(OSError):
        MediaStore(str(link))
    assert list(root.iterdir()) == []


def test_cross_worker_lease_and_transaction_finalization(tmp_path):
    from sqlalchemy.orm import Session
    # Import installs the production transaction-end listener.
    import services.product_image_service  # noqa: F401
    os.chmod(tmp_path, 0o700)
    from services.product_image_storage import MediaIOLease
    lease, second = MediaIOLease(), MediaStore(str(tmp_path))
    lease.open(str(tmp_path), write=True)
    first = lease.store
    with pytest.raises(HTTPException) as failure:
        second.acquire_write()
    assert failure.value.detail['code'] == 'IMAGE_BUSY'
    with Session() as session:
        with session.begin():
            session.info['product_image_leases'] = [lease]
        assert first.fd is None, 'IMAGE_LEASE_ENDS_AFTER_TRANSACTION'
    acquired = second.acquire_write(); os.close(acquired); second.close()


def test_root_binding_requires_operator_preparation_and_exact_database(tmp_path):
    from services.product_image_storage import DATABASE_IDENTITY_SQL
    os.chmod(tmp_path, 0o700)
    store = MediaStore(str(tmp_path))
    identity = {'database': 'test_images', 'database_oid': '101', 'server_address': '127.0.0.1',
                'server_port': 5432, 'pairing': 'mpango-media-v1:' + str(uuid4())}
    try:
        with pytest.raises(HTTPException, match='IMAGE_DATABASE_BINDING_REQUIRED'):
            store.verify_database(identity)
        store.initialize_binding(identity)
        before = (tmp_path / 'media-binding.json').read_bytes()
        store.verify_database(identity)
        for key, value in [('database_oid', '102'), ('pairing', 'mpango-media-v1:' + str(uuid4())),
                           ('server_address', '127.0.0.2')]:
            with pytest.raises(HTTPException, match='IMAGE_DATABASE_BINDING_MISMATCH'):
                store.verify_database({**identity, key: value})
        assert (tmp_path / 'media-binding.json').read_bytes() == before
        with pytest.raises(HTTPException, match='IMAGE_DATABASE_BINDING_ROOT_NOT_EMPTY'):
            store.initialize_binding(identity)
        assert 'obj_description' in DATABASE_IDENTITY_SQL
    finally:
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('interrupt', ['cancel', 'timeout'])
async def test_inflight_io_keeps_ownership_until_actual_completion(tmp_path, monkeypatch, interrupt):
    import threading
    from services import product_image_storage as storage
    os.chmod(tmp_path, 0o700)
    lease = storage.MediaIOLease()
    await storage.storage_io(lease, lambda owner: owner.open(str(tmp_path), write=True))
    entered, finished = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    def blocked(owner):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(3), 'IMAGE_TEST_BARRIER_NOT_RELEASED'
        try:
            return owner.store.publish(uuid4(), uuid4(), _decode(fixture_image(), 'PNG'))
        finally:
            loop.call_soon_threadsafe(finished.set)
    monkeypatch.setattr(storage, 'IO_TIMEOUT', 0.05 if interrupt == 'timeout' else 2)
    task = asyncio.create_task(storage.storage_io(lease, blocked))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        if interrupt == 'cancel':
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
        else:
            with pytest.raises(HTTPException, match='IMAGE_STORAGE_TIMEOUT'): await task
        lease.transaction_ended()
        assert lease.pending and lease.store.fd is not None, 'IMAGE_IO_NOT_PREMATURELY_CLOSED'
        other = MediaStore(str(tmp_path))
        try:
            with pytest.raises(HTTPException, match='IMAGE_BUSY'): other.acquire_write()
        finally:
            other.close()
    finally:
        release.set()
        await asyncio.wait_for(finished.wait(), 3)
        # The callback notification is scheduled before the worker's finally;
        # a second admitted job on this lease is not used as a cleanup oracle.
        for _ in range(100):
            if lease.store.fd is None: break
            await asyncio.sleep(0.01)
        assert not lease.pending and lease.store.fd is None, 'IMAGE_IO_RELEASED_AFTER_COMPLETION'


@pytest.mark.asyncio
async def test_io_admission_has_no_unbounded_queue():
    import threading
    from services.product_image_storage import MediaIOLease, storage_io
    entered = [asyncio.Event() for _ in range(4)]
    release = threading.Event()
    loop = asyncio.get_running_loop()
    leases = [MediaIOLease() for _ in entered]
    def block(index):
        loop.call_soon_threadsafe(entered[index].set)
        assert release.wait(3)
    tasks = [asyncio.create_task(storage_io(lease, lambda _, i=i: block(i)))
             for i, lease in enumerate(leases)]
    try:
        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in entered)), 1)
        with pytest.raises(HTTPException, match='IMAGE_IO_BUSY'):
            await storage_io(MediaIOLease(), lambda _: pytest.fail('IMAGE_FIFTH_JOB_STARTED'))
    finally:
        release.set()
        await asyncio.gather(*tasks)
        for lease in leases: lease.transaction_ended()


def test_partial_publish_failure_preserves_existing_version(tmp_path, monkeypatch):
    os.chmod(tmp_path, 0o700)
    store = MediaStore(str(tmp_path)); fd = store.acquire_write()
    tenant, product = uuid4(), uuid4()
    try:
        variants = _decode(fixture_image(), 'PNG')
        version, metadata = store.publish(tenant, product, variants)
        def fail(*args, **kwargs): raise OSError('fixture rename failure')
        with monkeypatch.context() as scoped:
            scoped.setattr(os, 'rename', fail)
            with pytest.raises(OSError): store.publish(tenant, product, variants)
        assert store.read(tenant, product, version, 'detail', metadata['detail']) == variants['detail'][0]
        assert [p.name for p in (tmp_path / str(tenant) / str(product)).iterdir()] == [str(version)]
    finally:
        os.close(fd); store.close()


def test_exact_media_route_delegates_before_body_hash_even_with_key():
    from api.middleware.idempotency import IdempotencyMiddleware
    async def run(path):
        reads = []
        async def denied(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 401, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'not authenticated'})
        async def receive():
            reads.append(1)
            return {'type': 'http.request', 'body': b'{}', 'more_body': False}
        scope = {'type': 'http', 'method': 'PUT', 'path': path, 'query_string': b'',
                 'headers': [(b'x-idempotency-key', b'hostile-key')], 'scheme': 'http',
                 'server': ('test', 80), 'client': ('test', 1), 'http_version': '1.1'}
        messages = []
        async def send(message): messages.append(message)
        await IdempotencyMiddleware(denied)(scope, receive, send)
        return reads
    pid = str(uuid4())
    assert run_coroutine(run(f'/api/v1/catalog-products/{pid}/image')) == []
    assert run_coroutine(run(f'/api/v1/catalog-products/{pid}/image-other')) != []
