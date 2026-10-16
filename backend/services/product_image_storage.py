"""Private descriptor-rooted immutable files. Never serves a user-supplied path."""
import asyncio
import fcntl
import hashlib
import json
import os
import stat
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from contextlib import contextmanager
from uuid import UUID, uuid4

from fastapi import HTTPException

MAX_INPUT = 5 * 1024 * 1024
VARIANT_LIMITS = {'thumb': 80 * 1024, 'detail': 300 * 1024}
TENANT_BYTES = 500 * 1024 * 1024
TENANT_IMAGES = 1000
DATABASE_IDENTITY_SQL = """SELECT current_database() AS database, d.oid::text AS database_oid,
    inet_server_addr()::text AS server_address, inet_server_port() AS server_port,
    shobj_description(d.oid,'pg_database') AS pairing
    FROM pg_catalog.pg_database d WHERE d.datname=current_database()"""
IO_TIMEOUT = 5
_IO_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix='product-media')
_IO_SLOTS = threading.BoundedSemaphore(4)


class MediaIOLease:
    """A transaction and an in-flight worker jointly own the root/lock fds.

    Timeout bounds the request, NOT a kernel syscall. A late worker retains its
    slot and lease until it actually returns; it cannot publish any DB pointer.
    Local private filesystem only. A permanently stuck disk needs operator
    process/storage recovery, not more queued threads or premature fd reuse.
    """
    def __init__(self):
        self.store = None
        self.lock_fd = None
        self.pending = False
        self.ended = False
        self.guard = threading.Lock()

    def open(self, root, *, write=False):
        self.store = MediaStore(root)
        if write:
            self.lock_fd = self.store.acquire_write()

    def _close(self):
        try:
            if self.lock_fd is not None:
                fd, self.lock_fd = self.lock_fd, None
                os.close(fd)
        finally:
            if self.store is not None:
                self.store.close()

    def transaction_ended(self):
        with self.guard:
            self.ended = True
            if not self.pending:
                self._close()


async def storage_io(lease, operation):
    # Admission is synchronous and non-waiting: at most four submitted jobs,
    # including jobs that timed out from the caller's point of view.
    if not _IO_SLOTS.acquire(blocking=False):
        refuse('IMAGE_IO_BUSY', 429)
    with lease.guard:
        if lease.pending or lease.ended:
            _IO_SLOTS.release()
            refuse('IMAGE_IO_OWNER_INVALID')
        lease.pending = True

    def work():
        try:
            return operation(lease)
        finally:
            try:
                with lease.guard:
                    lease.pending = False
                    if lease.ended:
                        lease._close()
            finally:
                _IO_SLOTS.release()
    try:
        future = asyncio.get_running_loop().run_in_executor(_IO_EXECUTOR, work)
    except BaseException:
        with lease.guard:
            lease.pending = False
            if lease.ended:
                lease._close()
        _IO_SLOTS.release()
        raise
    # Consume late exceptions without losing the worker's cleanup ownership.
    future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    try:
        return await asyncio.wait_for(asyncio.shield(future), IO_TIMEOUT)
    except TimeoutError:
        refuse('IMAGE_STORAGE_TIMEOUT')


def refuse(code, status=503):
    raise HTTPException(status_code=status, detail={'code': code, 'message': code})


def canonical_uuid(value):
    try:
        parsed = UUID(str(value))
        if str(parsed) != str(value):
            raise ValueError
        return str(parsed)
    except (TypeError, ValueError, AttributeError):
        refuse('PRODUCT_NOT_FOUND', 404)


def _directory(parent, name, create=False):
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    st = os.fstat(fd)
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        os.close(fd)
        refuse('IMAGE_STORAGE_IDENTITY')
    return fd


class MediaStore:
    def __init__(self, root):
        if not root or not os.path.isabs(root) or os.path.normpath(root) != root or root == '/':
            refuse('IMAGE_STORAGE_NOT_CONFIGURED')
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            for part in root.split('/')[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                os.close(fd)
                fd = child
            st = os.fstat(fd)
            if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
                refuse('IMAGE_STORAGE_IDENTITY')
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _binding(self, identity):
        keys = {'database', 'database_oid', 'server_address', 'server_port', 'pairing'}
        if (set(identity) != keys or not isinstance(identity['pairing'], str)
                or not identity['pairing'].startswith('mpango-media-v1:')):
            refuse('IMAGE_DATABASE_BINDING_REQUIRED')
        canonical_uuid(identity['pairing'].removeprefix('mpango-media-v1:'))
        if (not identity['database'] or not str(identity['database_oid']).isdigit()
                or not identity['server_address'] or type(identity['server_port']) is not int):
            refuse('IMAGE_DATABASE_BINDING_MISMATCH')
        st = os.fstat(self.fd)
        return {'format': 1, 'database': dict(identity), 'root_device': st.st_dev,
                'root_inode': st.st_ino}

    def initialize_binding(self, identity):
        """Explicit operator preparation on an EMPTY root, never runtime adoption.

        The DB owner first assigns a fresh database-comment pairing UUID on the
        independently approved target. Copying a DB/root is NOT rebinding it.
        Restore binds a new empty target before copying immutable versions.
        """
        lock = self.acquire_write()
        try:
            record = self._binding(identity)
            if set(os.listdir(self.fd)) != {'media.lock'}:
                refuse('IMAGE_DATABASE_BINDING_ROOT_NOT_EMPTY')
            fd = os.open('media-binding.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self.fd)
            try:
                view = memoryview(json.dumps(record, sort_keys=True).encode('ascii'))
                while view:
                    count = os.write(fd, view)
                    if count <= 0:
                        raise OSError('no write progress')
                    view = view[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(self.fd)
        finally:
            os.close(lock)

    def verify_database(self, identity):
        expected = self._binding(identity)
        try:
            fd = os.open('media-binding.json', os.O_RDONLY | os.O_NOFOLLOW
                         | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=self.fd)
        except FileNotFoundError:
            refuse('IMAGE_DATABASE_BINDING_REQUIRED')
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.getuid()
                    or stat.S_IMODE(st.st_mode) != 0o600 or not 0 < st.st_size <= 2048):
                refuse('IMAGE_DATABASE_BINDING_MISMATCH')
            raw = os.read(fd, 2049)
            try:
                actual = json.loads(raw)
            except (ValueError, UnicodeError):
                refuse('IMAGE_DATABASE_BINDING_MISMATCH')
            if actual != expected:
                refuse('IMAGE_DATABASE_BINDING_MISMATCH')
        finally:
            os.close(fd)

    def acquire_write(self):
        try:
            fd = os.open('media.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600, dir_fd=self.fd)
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600:
                os.close(fd)
                refuse('IMAGE_STORAGE_IDENTITY')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:
                os.close(fd)
                raise
            return fd
        except BlockingIOError:
            refuse('IMAGE_BUSY', 429)

    @contextmanager
    def product_dir(self, tenant, product, *, create=False):
        t = _directory(self.fd, canonical_uuid(tenant), create)
        try:
            p = _directory(t, canonical_uuid(product), create)
            try:
                yield p
            finally:
                os.close(p)
        finally:
            os.close(t)

    def check_capacity(self, tenant):
        fs = os.fstatvfs(self.fd)
        if fs.f_bavail * fs.f_frsize < 1024**3 or fs.f_bavail < fs.f_blocks * 0.1:
            refuse('IMAGE_DISK_RESERVE', 429)
        try:
            fd = _directory(self.fd, canonical_uuid(tenant))
        except FileNotFoundError:
            return
        deadline = time.monotonic() + 1
        visited = 0
        def usage(parent):
            nonlocal visited
            total = 0
            for name in os.listdir(parent):
                visited += 1
                if visited > 12000 or time.monotonic() > deadline:
                    refuse('IMAGE_STORAGE_INVENTORY_LIMIT', 429)
                st = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if stat.S_ISDIR(st.st_mode):
                    child = _directory(parent, name)
                    try:
                        total += usage(child)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.getuid():
                    total += st.st_size
                else:
                    refuse('IMAGE_STORAGE_IDENTITY')
            return total
        try:
            if usage(fd) + MAX_INPUT + sum(VARIANT_LIMITS.values()) > TENANT_BYTES:
                refuse('IMAGE_TENANT_QUOTA', 429)
        finally:
            os.close(fd)

    def publish(self, tenant, product, variants):
        version = str(uuid4())
        with self.product_dir(tenant, product, create=True) as parent:
            pending = '.' + version + '.pending'
            os.mkdir(pending, 0o700, dir_fd=parent)
            fd = _directory(parent, pending)
            created = []
            try:
                metadata = {}
                for name, limit in VARIANT_LIMITS.items():
                    data, width, height = variants[name]
                    if not data or len(data) > limit:
                        refuse('IMAGE_OUTPUT_LIMIT', 422)
                    filename = name + '.webp'
                    out = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
                    created.append(filename)
                    try:
                        view = memoryview(data)
                        while view:
                            n = os.write(out, view)
                            if n <= 0:
                                raise OSError('no write progress')
                            view = view[n:]
                        os.fsync(out)
                    finally:
                        os.close(out)
                    metadata[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'width': width, 'height': height, 'mime': 'image/webp'}
                manifest = json.dumps({'tenant': canonical_uuid(tenant), 'product': canonical_uuid(product),
                    'version': version, 'created_utc': datetime.now(timezone.utc).isoformat(),
                    'variants': metadata}, sort_keys=True).encode('ascii')
                marker = os.open('manifest.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
                created.append('manifest.json')
                try:
                    view = memoryview(manifest)
                    while view:
                        n = os.write(marker, view)
                        if n <= 0:
                            raise OSError('no write progress')
                        view = view[n:]
                    os.fsync(marker)
                finally:
                    os.close(marker)
                os.fsync(fd)
                os.rename(pending, version, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
                return UUID(version), metadata
            except BaseException:
                # Only this invocation's still-private pending directory is owned.
                if os.path.exists(f'/proc/self/fd/{parent}/{pending}'):
                    for filename in created:
                        os.unlink(filename, dir_fd=fd)
                    os.rmdir(pending, dir_fd=parent)
                raise
            finally:
                os.close(fd)

    def read(self, tenant, product, version, variant, metadata):
        if variant not in VARIANT_LIMITS:
            refuse('IMAGE_NOT_FOUND', 404)
        with self.product_dir(tenant, product) as parent:
            fd = _directory(parent, canonical_uuid(version))
            try:
                source = os.open(variant + '.webp', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
                try:
                    st = os.fstat(source)
                    limit = VARIANT_LIMITS[variant]
                    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600 or not 0 < st.st_size <= limit:
                        refuse('IMAGE_STORAGE_IDENTITY')
                    data = bytearray()
                    while len(data) <= limit:
                        chunk = os.read(source, min(65536, limit + 1 - len(data)))
                        if not chunk:
                            break
                        data.extend(chunk)
                    if len(data) != metadata['bytes'] or hashlib.sha256(data).hexdigest() != metadata['sha256']:
                        refuse('IMAGE_CONTENT_MISMATCH')
                    return bytes(data)
                finally:
                    os.close(source)
            finally:
                os.close(fd)
