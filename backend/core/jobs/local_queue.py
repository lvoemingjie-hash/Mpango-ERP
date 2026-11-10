"""Single-owner local queue; durable acceptance and finite export recovery.

An advisory lock excludes another owner, but is never proof that an old
process or writer has exited. Recovery requires independent local evidence.
"""
import asyncio
import base64
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import uuid
from contextlib import nullcontext, asynccontextmanager
from datetime import datetime
from enum import Enum

from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import or_, select, text, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from core.jobs.base import (JobQueue, get_job_handler, JobQueueNotAccepting,
                            JobQueueShutdownIncomplete, JobRecoveryRequired)
from core.structured_logging import get_logger
from database.session import AsyncSessionLocal, async_engine
from models.job import Job

logger = get_logger(__name__)
OWNER_KEYS = (742019, 5106)
DRAIN_SECONDS = 30.0
CLOSE_SECONDS = 5.0
# One terminal bookkeeping row, not a runnable job or a new task platform.
# Its DB-persisted path/generation prevents a missing/moved local marker from
# being mistaken for a fresh queue after a process or owner connection dies.
OWNER_ROW_ID = uuid.uuid5(uuid.NAMESPACE_URL, 'mpango/local-queue-owner/v2')
OWNER_ROW_NAME = '__local_queue_owner_v2__'

# This file is provisioned by a trusted infrastructure operator, not by the
# application user. The Windows/VM identity source is not deployed by A2.
REBOOT_AUTHORITY_PATH = Path('/etc/mpango/queue-reboot/authority.json')


def _canonical_reboot(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def _strict_reboot_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    if not isinstance(value, dict):
        raise ValueError('object required')
    return value


def _read_protected_reboot_file(path, uid, *, private):
    """Read via verified directory descriptors, without following any symlink."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or path.name in ('', '.', '..'):
        raise ValueError('unsafe path')
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:-1]:
            st = os.fstat(directory)
            if st.st_uid not in (0, uid) or st.st_mode & 0o022:
                raise ValueError('unsafe parent')
            next_directory = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        st = os.fstat(directory)
        if st.st_uid not in (0, uid) or st.st_mode & 0o022:
            raise ValueError('unsafe parent')
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != uid or st.st_size > 65536
                    or st.st_mode & (0o077 if private else 0o022)):
                raise ValueError('unsafe file')
            with os.fdopen(fd, 'rb') as stream:
                fd = -1
                data = stream.read(65537)
            if len(data) > 65536:
                raise ValueError('unsafe file')
            return data
        finally:
            if fd != -1:
                os.close(fd)
    finally:
        os.close(directory)


def _legacy_journal_missing(path):
    """Establish absence without following symlinks, including a dangling one."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or not path.name:
        raise ValueError('unsafe journal path')
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:-1]:
            try:
                nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            except FileNotFoundError:
                return True
            os.close(directory)
            directory = nxt
        try:
            os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return True
        return False
    finally:
        os.close(directory)


def _observe_reboot_authority():
    """Read a root-owned protected attestation; no environment fallback."""
    authority = _strict_reboot_json(_read_protected_reboot_file(REBOOT_AUTHORITY_PATH, 0, private=False))
    required = ('vm_id', 'deployment_id', 'pg_system_identifier', 'database_name',
                'database_oid', 'pg_storage_id', 'export_storage_id', 'export_root',
                'pg_data_root', 'pg_container_id', 'pg_image_id', 'pg_device',
                'export_device', 'boot', 'signing_public_key', 'app_uid', 'issuer_uid')
    if set(authority) != set(required):
        raise ValueError('incomplete authority')
    if any(type(authority[k]) is not int or authority[k] <= 0
           for k in ('database_oid', 'pg_device', 'export_device', 'app_uid')):
        raise ValueError('invalid authority identity')
    if type(authority['issuer_uid']) is not int or authority['issuer_uid'] != 0:
        raise ValueError('invalid issuer identity')
    if authority['app_uid'] == authority['issuer_uid']:
        raise ValueError('issuer and application identities must differ')
    if any(not isinstance(authority[k], str) or not authority[k] or len(authority[k]) > 4096
           for k in required if k not in ('database_oid', 'pg_device', 'export_device', 'app_uid', 'issuer_uid')):
        raise ValueError('invalid authority field')
    if authority['boot'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        raise ValueError('authority boot mismatch')
    if os.stat(authority['export_root']).st_dev != authority['export_device']:
        raise ValueError('export mount mismatch')
    return authority


def _verify_signed_reboot_permit(path, authority, *, file_uid=None):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    raw = _read_protected_reboot_file(path, os.getuid() if file_uid is None else file_uid, private=True)
    envelope = _strict_reboot_json(raw)
    if set(envelope) != {'payload', 'signature'} or not isinstance(envelope['payload'], dict):
        raise ValueError('invalid envelope')
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(authority['signing_public_key'], validate=True))
    key.verify(base64.b64decode(envelope['signature'], validate=True), _canonical_reboot(envelope['payload']))
    return envelope['payload'], hashlib.sha256(raw).hexdigest()


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class QueueState(str, Enum):
    STARTING = "STARTING"
    ACCEPTING = "ACCEPTING"
    DRAINING = "DRAINING"
    CLOSED = "CLOSED"
    INCOMPLETE = "INCOMPLETE"


jobs_enqueued_total = Counter('jobs_enqueued_total', 'Total jobs enqueued', ['job_name'])
jobs_completed_total = Counter('jobs_completed_total', 'Total jobs completed successfully', ['job_name'])
jobs_failed_total = Counter('jobs_failed_total', 'Total jobs failed', ['job_name'])
job_execution_duration_seconds = Histogram('job_execution_duration_seconds', 'Job execution duration in seconds',
    ['job_name'], buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 120.0))
jobs_pending_gauge = Gauge('jobs_pending', 'Number of jobs pending in queue')
jobs_running_gauge = Gauge('jobs_running', 'Number of jobs currently running')


class LocalJobQueue(JobQueue):
    def __init__(self, max_workers=5):
        self.max_workers = max_workers
        self.queue = asyncio.Queue()
        self.semaphore = asyncio.Semaphore(max_workers)
        self.workers = []
        self.jobs = {}
        self.running = False
        self.state = QueueState.CLOSED
        self.stats = dict(enqueued=0, completed=0, failed=0, pending=0, running=0, deferred=0)
        self.recovery = dict(found=0, replayed=0, completed_reconciled=0, unrecoverable_failed=0, manual_blocked=0)
        self.drain_seconds = DRAIN_SECONDS
        self.close_seconds = CLOSE_SECONDS
        self._admissions = set()
        self._owned = set()
        self._recovery_ids = set()
        self._stop_task = None
        self._owner_connection = None
        self._owner_engine = None
        self._owner_backend = None
        self._owner_lost = False
        self._owner_query_lock = asyncio.Lock()
        self._finalizer = None
        self._monitor = None
        self._generation = uuid.uuid4().hex
        self._db_uncertain = set()
        self.close_report = {}
        self._previous_receipt = None
        self._marker_generation = None
        self._generation_claimed = False
        self._planned_reboot_handoff = None
        self._planned_reboot_complete = False
        # Same configuration/default as the file writer, captured once for
        # this queue instance. A per-operation writer-directory replacement
        # is not an ownership-state relocation.
        self._owner_state_root = Path(os.environ.get(
            'EXPORT_DIR', str(Path(__file__).resolve().parents[2] / 'exports')
        )).resolve()

    def _io_keys(self):
        return [(self._generation, jid) for jid in self._owned | self._recovery_ids] + [(self._generation, 'owner-receipt')]

    @staticmethod
    def _database_identity():
        url = async_engine.url
        return hashlib.sha256(json.dumps([url.host, url.port or 5432, url.database, url.username]).encode()).hexdigest()

    @staticmethod
    def _ticks(pid):
        return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19])

    def _receipt_path(self):
        return self._owner_state_root / '.queue-owner.json'

    def _generation_fact(self, closed, *, published_state=None):
        fact = dict(version=2, host=socket.gethostname(), boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            pid=os.getpid(), start_ticks=self._ticks(os.getpid()), database=self._database_identity(),
            generation=self._generation, state_path=str(self._receipt_path().resolve()),
            owner_backend=self._owner_backend, closed=closed, state='CLOSED' if closed else (published_state or self.state.value),
            active_handlers=0 if closed else len(self.workers), active_io=0 if closed else None,
            active_admissions=0 if closed else len(self._admissions))
        if self._planned_reboot_handoff is not None:
            fact['planned_reboot_handoff'] = copy.deepcopy(self._planned_reboot_handoff)
        return fact

    def _reboot_seal_path(self, generation):
        if not isinstance(generation, str) or len(generation) != 32 or any(c not in '0123456789abcdef' for c in generation):
            raise ValueError('invalid generation')
        return self._owner_state_root / ('.queue-reboot-complete-' + generation + '.json')

    def _read_reboot_journal(self, *, file_uid=None):
        path = self._owner_state_root / '.queue-reboot-handoff.json'
        uid = os.getuid() if file_uid is None else file_uid
        try:
            # Absence must be established through no-follow directory handles.
            # The legacy path may have a group-writable ancestor; a present
            # journal is always reopened using the stricter protected reader.
            if _legacy_journal_missing(path):
                return None
            raw = _read_protected_reboot_file(path, uid, private=True)
        except (OSError, ValueError):
            raise JobRecoveryRequired('JOB_RECOVERY_HANDOFF_INCOMPLETE') from None
        try:
            journal = _strict_reboot_json(raw)
            if (set(journal) != {'version', 'phase', 'generation', 'handoff'}
                    or journal['version'] != 1 or journal['phase'] not in ('INCOMPLETE', 'COMPLETE')
                    or not isinstance(journal['handoff'], dict)):
                raise ValueError('invalid journal')
            self._reboot_seal_path(journal['generation'])
            if journal['phase'] == 'COMPLETE':
                self._check_reboot_handoff({'generation': journal['generation'], 'state': 'ACCEPTING',
                                             'planned_reboot_handoff': journal['handoff']}, file_uid=uid)
            return journal
        except (OSError, ValueError, TypeError, KeyError, JobRecoveryRequired):
            raise JobRecoveryRequired('JOB_RECOVERY_HANDOFF_INCOMPLETE') from None

    def _write_reboot_journal(self, phase, expected_marker, cancel):
        path = self._owner_state_root / '.queue-reboot-handoff.json'
        temporary = path.with_name(path.name + '.' + self._generation + '.tmp')
        lock = os.open(self._owner_state_root / '.queue-owner.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        created = False
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            previous = self._read_reboot_journal()
            if phase == 'INCOMPLETE':
                if previous is not None and previous['phase'] != 'COMPLETE':
                    raise JobRecoveryRequired('JOB_RECOVERY_HANDOFF_INCOMPLETE')
                if self._read_generation() != expected_marker:
                    raise JobQueueShutdownIncomplete()
            elif previous is None or previous['phase'] != 'INCOMPLETE' or previous['generation'] != self._generation:
                raise JobRecoveryRequired('JOB_RECOVERY_HANDOFF_INCOMPLETE')
            journal = {'version': 1, 'phase': phase, 'generation': self._generation,
                       'handoff': copy.deepcopy(self._planned_reboot_handoff)}
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            created = True
            with os.fdopen(fd, 'wb') as stream:
                stream.write(_canonical_reboot(journal))
                stream.flush()
                os.fsync(stream.fileno())
            if cancel.is_set():
                raise JobQueueShutdownIncomplete()
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if created:
                temporary.unlink(missing_ok=True)
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)

    async def _publish_reboot_journal(self, phase, expected_marker=None):
        from jobs.export_jobs import export_io_scope, run_export_file_operation
        with export_io_scope((self._generation, 'owner-receipt')):
            await run_export_file_operation(lambda cancel: self._write_reboot_journal(phase, expected_marker, cancel))

    def _check_reboot_handoff(self, fact, *, file_uid=None):
        if not isinstance(fact, dict) or 'planned_reboot_handoff' not in fact:
            return
        handoff = fact['planned_reboot_handoff']
        try:
            if (not isinstance(handoff, dict) or handoff.get('phase') != 'COMPLETE'
                    or fact.get('state') == 'STARTING'):
                raise ValueError('handoff not complete')
            seal = _strict_reboot_json(_read_protected_reboot_file(
                self._reboot_seal_path(fact.get('generation')), os.getuid() if file_uid is None else file_uid, private=True))
            if seal != {'generation': fact['generation'], 'handoff': handoff}:
                raise ValueError('completion seal mismatch')
        except (OSError, ValueError, TypeError, KeyError):
            raise JobRecoveryRequired('JOB_RECOVERY_HANDOFF_INCOMPLETE') from None

    def _write_reboot_seal(self, receipt, cancel):
        # The same filesystem lock prevents a stale writer sealing a later owner.
        lock = os.open(self._owner_state_root / '.queue-owner.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if cancel.is_set() or self._read_generation() != receipt:
                raise JobQueueShutdownIncomplete()
            path = self._reboot_seal_path(self._generation)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(_canonical_reboot({'generation': self._generation,
                                                'handoff': receipt['planned_reboot_handoff']}))
                stream.flush()
                os.fsync(stream.fileno())
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)

    async def _planned_reboot_proven(self, db, old):
        try:
            authority = _observe_reboot_authority()
            if authority['app_uid'] != os.getuid():
                raise ValueError('application uid mismatch')
            permit_path = os.environ.get('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE')
            if not permit_path:
                raise JobRecoveryRequired('JOB_RECOVERY_REBOOT_PROOF_REQUIRED')
            permit, permit_sha = _verify_signed_reboot_permit(permit_path, authority)
            expected = {'kind', 'old_owner_sha256', 'old_generation', 'old_boot', 'new_boot', 'authority'}
            if set(permit) != expected or permit['kind'] != 'planned_clean_reboot_v1':
                raise ValueError('invalid permit fields')
            if (permit['authority'] != authority or permit['old_generation'] != old['generation']
                    or permit['old_boot'] != old['boot'] or permit['new_boot'] != authority['boot']
                    or permit['old_boot'] == permit['new_boot']
                    or permit['old_owner_sha256'] != hashlib.sha256(_canonical_reboot(old)).hexdigest()
                    or authority['export_root'] != str(self._owner_state_root)):
                raise ValueError('stale or mismatched permit')
            if (old.get('state') != 'CLOSED' or old.get('closed') is not True
                    or any(type(old.get(k)) is not int or old[k] != 0
                           for k in ('active_handlers', 'active_io', 'active_admissions'))):
                raise JobRecoveryRequired('JOB_RECOVERY_REBOOT_NOT_CLEAN')
            database = (await db.execute(text('SELECT current_database(), oid FROM pg_database WHERE datname=current_database()'))).one()
            if database[0] != authority['database_name'] or database[1] != authority['database_oid']:
                raise ValueError('database identity mismatch')
            duplicate = (await db.execute(select(Job.id).where(Job.id != OWNER_ROW_ID, Job.job_name == OWNER_ROW_NAME).limit(1))).first()
            unsettled = (await db.execute(select(Job.id).where(Job.id != OWNER_ROW_ID,
                or_(Job.status.is_(None), Job.status.notin_(['completed', 'failed']))).limit(1))).first()
            if duplicate or unsettled:
                raise JobRecoveryRequired('JOB_RECOVERY_REBOOT_UNSETTLED')
            return {'phase': 'INCOMPLETE', 'old_generation': old['generation'],
                    'old_owner_sha256': permit['old_owner_sha256'], 'permit_sha256': permit_sha}
        except JobRecoveryRequired:
            raise
        except Exception:
            raise JobRecoveryRequired('JOB_RECOVERY_REBOOT_PROOF_INVALID') from None

    def _read_generation(self, *, file_uid=None):
        path = self._receipt_path()
        try:
            if file_uid is not None:
                raw = _read_protected_reboot_file(path, file_uid, private=False)
            else:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as stream:
                    st = os.fstat(stream.fileno())
                    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o022:
                        raise ValueError('unsafe owner marker')
                    raw = stream.read()
        except FileNotFoundError:
            return None
        except (ValueError, OSError):
            raise JobRecoveryRequired('JOB_RECOVERY_STATE_PATH_INVALID')
        try:
            fact = _strict_reboot_json(raw)
            if file_uid is None and 'planned_reboot_handoff' in fact:
                protected = _read_protected_reboot_file(path, os.getuid(), private=False)
                if raw != protected:
                    raise ValueError('owner marker changed')
            return fact
        except (ValueError, OSError):
            raise JobRecoveryRequired('JOB_RECOVERY_STATE_PATH_INVALID') from None

    def _write_receipt(self, receipt, cancel):
        path = self._receipt_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.' + self._generation + '.tmp')
        fd = os.open(path.with_name('.queue-owner.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            current = self._read_generation()
            if (current.get('generation') if current else None) != self._marker_generation:
                raise JobQueueShutdownIncomplete()
            with temporary.open('x') as handle:
                json.dump(receipt, handle); handle.flush(); os.fsync(handle.fileno())
            if cancel.is_set():
                raise JobQueueShutdownIncomplete()
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self._marker_generation = self._generation
        finally:
            temporary.unlink(missing_ok=True)
            fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)

    async def _persist_receipt(self, closed, *, published_state=None):
        from jobs.export_jobs import export_io_scope, run_export_file_operation
        async with self._owner_transaction() as db:
            receipt = self._generation_fact(closed, published_state=published_state)
            with export_io_scope((self._generation, 'owner-receipt')):
                await run_export_file_operation(lambda cancel: self._write_receipt(receipt, cancel))
            await db.execute(update(Job).where(Job.id == OWNER_ROW_ID).values(payload=receipt))

    def _recovery_proven(self):
        if os.environ.get('JOB_QUEUE_RECOVERY_CONFIRMED') != '1':
            return False
        marker = self._previous_receipt
        if marker and marker.get('closed') is True and marker.get('active_handlers') == 0 and marker.get('active_io') == 0 and marker.get('active_admissions') == 0:
            return True
        external = os.environ.get('JOB_QUEUE_RECOVERY_PROOF_FILE')
        path = Path(external) if external else self._receipt_path()
        try:
            if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
                return False
            fact = json.loads(path.read_text())
            if not marker or marker.get('pid') != fact.get('pid') or marker.get('start_ticks') != fact.get('start_ticks'):
                return False
            if (fact.get('version') != 1 or fact.get('host') != socket.gethostname()
                    or fact.get('boot') != Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                    or fact.get('database') != self._database_identity()
                    or type(fact.get('pid')) is not int or fact['pid'] <= 0
                    or type(fact.get('start_ticks')) is not int or fact['start_ticks'] <= 0):
                return False
            try:
                old_alive = self._ticks(fact['pid']) == fact['start_ticks']
            except FileNotFoundError:
                old_alive = False
            return not old_alive
        except (OSError, ValueError, KeyError, TypeError):
            return False

    async def _acquire_owner(self):
        self._owner_engine = create_async_engine(async_engine.url, poolclass=NullPool)
        self._owner_connection = await self._owner_engine.connect()
        result = (await self._owner_connection.execute(text('SELECT pg_try_advisory_lock(:a,:b), pg_backend_pid()'),
            dict(a=OWNER_KEYS[0], b=OWNER_KEYS[1]))).one()
        if not result[0]:
            await self._release_owner()
            raise JobQueueNotAccepting('JOB_QUEUE_OWNER_BUSY')
        self._owner_backend = result[1]
        await self._owner_connection.commit()

    async def _ensure_owner_locked(self):
        if self._owner_lost or self._owner_connection is None:
            raise JobQueueNotAccepting('JOB_QUEUE_OWNER_LOST')
        result = await self._owner_connection.execute(text("SELECT pg_backend_pid(), EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND pid=pg_backend_pid() AND classid=:a AND objid=:b AND objsubid=2 AND granted)"), dict(a=OWNER_KEYS[0], b=OWNER_KEYS[1]))
        row = result.one()
        if row[0] != self._owner_backend or not row[1]:
            self._owner_lost = True
            self.state = QueueState.INCOMPLETE
            raise JobQueueNotAccepting('JOB_QUEUE_OWNER_LOST')

    @asynccontextmanager
    async def _owner_transaction(self, *, claimed=True):
        # Lock ownership AND every queue mutation use the same PG backend.
        # Backend exit releases its advisory lock only after its transactions
        # have ended. No independent old acceptance session can commit late.
        async with self._owner_query_lock:
            try:
                await self._ensure_owner_locked()
                async with AsyncSession(bind=self._owner_connection, expire_on_commit=False,
                                        join_transaction_mode='control_fully') as db:
                    db.info['tenant_schema'] = 'public'
                    if claimed:
                        fact = (await db.execute(select(Job.payload).where(Job.id == OWNER_ROW_ID))).scalar_one()
                        if fact.get('generation') != self._generation:
                            raise JobQueueNotAccepting('JOB_QUEUE_OWNER_LOST')
                    yield db
                    await self._ensure_owner_locked()
                    await db.commit()
            except BaseException as error:
                lost = isinstance(error, DBAPIError) and error.connection_invalidated
                if lost:
                    self._owner_lost = True
                    self.state = QueueState.INCOMPLETE
                if self._owner_connection is not None:
                    try:
                        await self._owner_connection.rollback()
                    except SQLAlchemyError:
                        if not lost:
                            raise
                if lost:
                    raise JobQueueNotAccepting('JOB_QUEUE_OWNER_LOST') from None
                raise

    async def _claim_generation(self):
        # The fixed DB row binds the local path even if no task is visible.
        # Publish STARTING before touching any recovered task. A partial
        # DB/file marker write is deliberately fail-closed, not "fresh".
        async with self._owner_transaction(claimed=False) as db:
            row = (await db.execute(select(Job).where(Job.id == OWNER_ROW_ID))).scalar_one_or_none()
            journal = self._read_reboot_journal()
            if journal is not None and journal['phase'] != 'COMPLETE':
                raise JobRecoveryRequired('JOB_RECOVERY_HANDOFF_INCOMPLETE')
            if row is not None:
                self._check_reboot_handoff(row.payload)
            marker = self._read_generation()
            self._check_reboot_handoff(marker)
            if os.environ.get('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE') and marker is not None:
                try:
                    protected_marker = _strict_reboot_json(_read_protected_reboot_file(
                        self._receipt_path(), os.getuid(), private=False))
                    if protected_marker != marker:
                        raise ValueError('owner marker changed')
                except (OSError, ValueError, TypeError):
                    raise JobRecoveryRequired('JOB_RECOVERY_HANDOFF_INCOMPLETE') from None
            if row is None:
                if os.environ.get('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE'):
                    raise JobRecoveryRequired('JOB_RECOVERY_REBOOT_PROOF_STALE')
                history = (await db.execute(select(Job.id).limit(1))).first()
                if history is not None or marker is not None:
                    raise JobRecoveryRequired('JOB_RECOVERY_GENERATION_MISSING')
            else:
                fact = row.payload
                # A visible COMPLETE is insufficient after an uncertain directory
                # fsync. Only a later real durable close permits legacy recovery.
                if isinstance(fact, dict) and 'planned_reboot_handoff' in fact and fact.get('closed') is not True:
                    raise JobRecoveryRequired('JOB_RECOVERY_HANDOFF_INCOMPLETE')
                if (row.job_name != OWNER_ROW_NAME or row.status != 'completed' or row.is_deleted
                        or not isinstance(fact, dict) or fact.get('version') != 2
                        or fact.get('database') != self._database_identity()
                        or fact.get('state_path') != str(self._receipt_path().resolve())
                        or marker != fact):
                    raise JobRecoveryRequired('JOB_RECOVERY_STATE_PATH_MISMATCH')
                if fact.get('host') != socket.gethostname():
                    raise JobRecoveryRequired('JOB_RECOVERY_OWNER_EXIT_UNPROVEN')
                if fact.get('boot') != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
                    self._planned_reboot_handoff = await self._planned_reboot_proven(db, fact)
                    await self._publish_reboot_journal('INCOMPLETE', fact)
                elif os.environ.get('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE'):
                    raise JobRecoveryRequired('JOB_RECOVERY_REBOOT_PROOF_STALE')
                self._previous_receipt = fact
                if self._planned_reboot_handoff is None and fact.get('closed') is not True and not self._recovery_proven():
                    raise JobRecoveryRequired('JOB_RECOVERY_OWNER_EXIT_UNPROVEN')
            self._marker_generation = marker.get('generation') if marker else None
            receipt = self._generation_fact(False)
            if row is None:
                db.add(Job(id=OWNER_ROW_ID, job_name=OWNER_ROW_NAME, status='completed', payload=receipt, attempts=0, max_retries=0))
            else:
                row.payload = receipt
        self._generation_claimed = True
        await self._persist_receipt(False)

    async def _ensure_owner(self):
        if self._owner_lost or self._owner_connection is None:
            raise JobQueueNotAccepting('JOB_QUEUE_OWNER_LOST')
        try:
            async with self._owner_query_lock:
                await asyncio.wait_for(self._ensure_owner_locked(), timeout=1.0)
                await self._owner_connection.commit()
        except Exception:
            self._owner_lost = True
            self.state = QueueState.INCOMPLETE
            raise JobQueueNotAccepting('JOB_QUEUE_OWNER_LOST') from None

    async def _watch_owner(self):
        try:
            while self.running:
                await asyncio.sleep(0.25)
                await self._ensure_owner()
        except JobQueueNotAccepting:
            for worker in self.workers:
                worker.cancel()

    async def _release_owner(self):
        if self._owner_connection is not None:
            await self._owner_connection.close()
            self._owner_connection = None
        if self._owner_engine is not None:
            await self._owner_engine.dispose()
            self._owner_engine = None

    async def enqueue(self, job_name, payload, delay_seconds=0, max_retries=3):
        if self.state != QueueState.ACCEPTING or (self._planned_reboot_handoff is not None and not self._planned_reboot_complete):
            raise JobQueueNotAccepting('JOB_QUEUE_OWNER_LOST' if self._owner_lost else 'JOB_QUEUE_NOT_ACCEPTING')
        await self._ensure_owner()
        if self.state != QueueState.ACCEPTING or (self._planned_reboot_handoff is not None and not self._planned_reboot_complete):
            raise JobQueueNotAccepting()
        get_job_handler(job_name)
        task = asyncio.create_task(self._persist_accept(job_name, copy.deepcopy(payload), delay_seconds, max_retries))
        self._admissions.add(task)
        task.add_done_callback(self._admissions.discard)
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        return await asyncio.shield(task)

    async def _persist_accept(self, name, payload, delay, retries):
        jid = str(uuid.uuid4())
        self._owned.add(jid)
        self._db_uncertain.add(jid)
        async with self._owner_transaction() as db:
            db.add(Job(id=uuid.UUID(jid), job_name=name, payload=payload, status='pending', attempts=0, max_retries=retries))
        record = dict(job_id=jid, job_name=name, payload=payload, delay_seconds=delay, max_retries=retries,
            status=JobStatus.PENDING, enqueued_at=datetime.utcnow(), started_at=None, completed_at=None, error=None)
        self.jobs[jid] = record
        self.queue.put_nowait(record)
        self._db_uncertain.discard(jid)
        self.stats['enqueued'] += 1; self.stats['pending'] += 1
        jobs_enqueued_total.labels(job_name=name).inc()
        jobs_pending_gauge.set(self.stats['pending'])
        return jid

    async def _worker(self, worker_id):
        while self.running and not self._owner_lost:
            record = await self.queue.get()
            try:
                async with self.semaphore:
                    await self._execute_job(record)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._db_uncertain.add(record['job_id'])
                self.state = QueueState.INCOMPLETE
                logger.error('Job state write incomplete', extra={'error_class': type(error).__name__})
            finally:
                self.queue.task_done()

    async def _write_job(self, jid, **values):
        async with self._owner_transaction() as db:
            await db.execute(update(Job).where(Job.id == uuid.UUID(jid)).values(**values))

    async def _execute_job(self, record):
        jid = record['job_id']; name = record['job_name']
        await self._ensure_owner()
        self.stats['pending'] -= 1; self.stats['running'] += 1
        record['status'] = JobStatus.RUNNING; record['started_at'] = datetime.utcnow()
        started = asyncio.get_running_loop().time()
        try:
            await self._write_job(jid, status='running', started_at=record['started_at'], attempts=Job.attempts + 1)
            if record['delay_seconds']:
                await asyncio.sleep(record['delay_seconds'])
            from jobs.export_jobs import export_io_scope
            scope = export_io_scope((self._generation, jid)) if name == 'export_report' else nullcontext()
            with scope:
                try:
                    await get_job_handler(name)(record['payload'])
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    async with AsyncSessionLocal() as db:
                        db.info['tenant_schema'] = 'public'
                        row = (await db.execute(select(Job).where(Job.id == uuid.UUID(jid)))).scalar_one()
                        retry = row.attempts < record['max_retries']
                    await self._write_job(jid, status='pending' if retry else 'failed', last_error=str(error),
                        completed_at=None if retry else datetime.utcnow())
                    record['error'] = str(error); self.stats['failed'] += 1
                    jobs_failed_total.labels(job_name=name).inc()
                    if retry:
                        record['status'] = JobStatus.PENDING; self.stats['pending'] += 1
                        self.queue.put_nowait(record)
                    else:
                        record['status'] = JobStatus.FAILED; record['completed_at'] = datetime.utcnow()
                    return
            await self._ensure_owner()
            await self._write_job(jid, status='completed', completed_at=datetime.utcnow())
            record['status'] = JobStatus.COMPLETED; record['completed_at'] = datetime.utcnow()
            self.stats['completed'] += 1
            jobs_completed_total.labels(job_name=name).inc()
        finally:
            self.stats['running'] -= 1
            jobs_pending_gauge.set(self.stats['pending']); jobs_running_gauge.set(self.stats['running'])
            job_execution_duration_seconds.labels(job_name=name).observe(asyncio.get_running_loop().time() - started)

    @staticmethod
    def _validate_export(row):
        from api.schemas.jobs import ExportJobPayload
        from jobs.export_jobs import _validate_file_id
        from services.reporting.semantic_layer import ViewScope, ReportMetric, ReportDimension, get_view_registration
        p = ExportJobPayload(**row.payload)
        if row.attempts < 0 or row.max_retries < 0:
            raise ValueError('EXPORT_RECOVERY_ATTEMPTS_INVALID')
        tenant = uuid.UUID(p.tenant_id); uuid.UUID(p.user_id)
        if p.tenant_schema != 't_' + tenant.hex:
            raise ValueError('EXPORT_RECOVERY_TENANT_MISMATCH')
        _validate_file_id(p.file_id)
        if p.format not in ('csv', 'xlsx') or p.limit < 1:
            raise ValueError('EXPORT_RECOVERY_FORMAT_INVALID')
        view = ViewScope(p.view); registration = get_view_registration(view)
        if not p.metrics or any(ReportMetric(m) not in registration.metrics for m in p.metrics):
            raise ValueError('EXPORT_RECOVERY_QUERY_INVALID')
        if any(ReportDimension(d) not in registration.dimensions for d in p.dimensions or []):
            raise ValueError('EXPORT_RECOVERY_QUERY_INVALID')
        for value in [p.date_from, p.date_to]:
            if value is not None:
                datetime.fromisoformat(value)
        return p

    async def _recover(self):
        await self._ensure_owner()
        async with AsyncSessionLocal() as db:
            db.info['tenant_schema'] = 'public'
            rows = (await db.execute(select(Job).where(Job.status.notin_(['completed', 'failed']), Job.is_deleted.is_(False)).order_by(Job.created_at, Job.id))).scalars().all()
        self.recovery['found'] = len(rows)
        await self._ensure_owner()
        if not rows:
            return
        if not self._recovery_proven():
            raise JobRecoveryRequired('JOB_RECOVERY_OWNER_EXIT_UNPROVEN')
        unknown = [row for row in rows if row.job_name != 'export_report' or row.status not in ('pending', 'running')]
        self.recovery['manual_blocked'] = len(unknown)
        if unknown:
            raise JobRecoveryRequired()
        decisions = []
        from api.v1.exports import _find_job_metadata
        from jobs.export_jobs import require_xlsx_dependency, export_io_scope, run_export_file_operation, read_metadata, ExportFileError, EXPORT_DIR
        self._recovery_ids = {str(row.id) for row in rows}
        for row in rows:
            try:
                self._validate_export(row)
                def result_metadata(cancel):
                    p = row.payload
                    raw = read_metadata(p['file_id'])
                    if raw is not None:
                        expected = EXPORT_DIR.resolve() / (p['file_id'] + '.' + p['format'])
                        if (not isinstance(raw, dict) or any(raw.get(k) != p.get(k) for k in ['file_id', 'tenant_id', 'user_id', 'format'])
                                or Path(raw.get('file_path', '')).resolve() != expected
                                or raw.get('file_name') != expected.name):
                            raise ExportFileError('EXPORT_RECOVERY_MAPPING_INVALID')
                    return _find_job_metadata(str(row.id), p)
                with export_io_scope((self._generation, str(row.id))):
                    result_meta = await run_export_file_operation(result_metadata)
                if result_meta:
                    decisions.append((row, 'complete'))
                elif row.attempts > 0 and row.attempts >= max(1, row.max_retries):
                    decisions.append((row, 'exhausted'))
                else:
                    if row.payload['format'] == 'xlsx':
                        require_xlsx_dependency()
                    decisions.append((row, 'replay'))
            except (ValueError, TypeError, AttributeError, KeyError) as error:
                reason = str(error)
                approved = {'EXPORT_XLSX_DEPENDENCY_UNAVAILABLE', 'EXPORT_RECOVERY_TENANT_MISMATCH', 'EXPORT_RECOVERY_FORMAT_INVALID', 'EXPORT_RECOVERY_QUERY_INVALID', 'EXPORT_RECOVERY_ATTEMPTS_INVALID', 'EXPORT_RECOVERY_MAPPING_INVALID'}
                decisions.append((row, reason if reason in approved else 'invalid'))
        for row, decision in decisions:
            jid = str(row.id)
            if decision == 'complete':
                await self._write_job(jid, status='completed', completed_at=datetime.utcnow())
                self.recovery['completed_reconciled'] += 1
            elif decision != 'replay':
                await self._write_job(jid, status='failed', completed_at=datetime.utcnow(),
                    last_error=('EXPORT_RECOVERY_INVALID' if decision == 'invalid' else
                        'EXPORT_RECOVERY_ATTEMPTS_EXHAUSTED' if decision == 'exhausted' else decision))
                self.recovery['unrecoverable_failed'] += 1
            else:
                await self._write_job(jid, status='pending', last_error='EXPORT_RECOVERY_REPLAYED')
                record = dict(job_id=jid, job_name=row.job_name, payload=row.payload, delay_seconds=0,
                    max_retries=row.max_retries, status=JobStatus.PENDING, enqueued_at=row.created_at,
                    started_at=None, completed_at=None, error=None)
                self._owned.add(jid); self.jobs[jid] = record
                self.queue.put_nowait(record); self.stats['pending'] += 1
                self.recovery['replayed'] += 1

    async def start(self):
        if self.state == QueueState.ACCEPTING:
            if self._planned_reboot_handoff is not None and not self._planned_reboot_complete:
                raise JobQueueNotAccepting()
            return
        if self.state not in (QueueState.CLOSED,):
            raise JobQueueNotAccepting()
        if self._stop_task is not None:
            self._stop_task = self._finalizer = None
            self.queue = asyncio.Queue()
            self.jobs = {}; self._owned.clear(); self._recovery_ids.clear()
            self._generation = uuid.uuid4().hex
            self._planned_reboot_handoff = None
            self._planned_reboot_complete = False
        self.state = QueueState.STARTING
        try:
            await self._acquire_owner()
            await self._claim_generation()
            await self._recover()
            await self._ensure_owner()
            if self._planned_reboot_handoff is not None:
                from jobs.export_jobs import export_io_scope, run_export_file_operation
                self._planned_reboot_handoff['phase'] = 'COMPLETE'
                await self._persist_receipt(False, published_state=QueueState.ACCEPTING.value)
                await self._ensure_owner()
                receipt = self._generation_fact(False, published_state=QueueState.ACCEPTING.value)
                with export_io_scope((self._generation, 'owner-receipt')):
                    await run_export_file_operation(lambda cancel: self._write_reboot_seal(receipt, cancel))
                await self._publish_reboot_journal('COMPLETE')
                self._planned_reboot_complete = True
            else:
                await self._persist_receipt(False, published_state=QueueState.ACCEPTING.value)
            self.state = QueueState.ACCEPTING
            self.running = True
            self.workers = [asyncio.create_task(self._worker(i)) for i in range(self.max_workers)]
            self._monitor = asyncio.create_task(self._watch_owner())
        except BaseException:
            from jobs.export_jobs import export_io_pending
            if export_io_pending(self._io_keys()):
                self.state = QueueState.INCOMPLETE
            elif self._planned_reboot_handoff is not None and not self._planned_reboot_complete:
                await self._release_owner()
                self.state = QueueState.INCOMPLETE
            else:
                if self._generation_claimed and not self._owner_lost and not self._owned and self.queue.empty():
                    try:
                        await self._persist_receipt(True)
                    except BaseException:
                        pass  # Preserve the STARTING fact; never declare it closed.
                await self._release_owner()
                self.state = QueueState.CLOSED
            raise

    async def _settle_stopped(self):
        from jobs.export_jobs import export_io_pending
        if export_io_pending(self._io_keys()):
            raise JobQueueShutdownIncomplete()
        async with AsyncSessionLocal() as db:
            db.info['tenant_schema'] = 'public'
            rows = (await db.execute(select(Job).where(Job.id.in_([uuid.UUID(jid) for jid in self._owned]), Job.is_deleted.is_(False)))).scalars().all() if self._owned else []
        self.close_report = dict(completed=0, failed=0, pending=0, running=0, deferred=0, accepted_rows=len(rows))
        for row in rows:
            state = row.status
            if state in ('pending', 'running') and row.job_name == 'export_report':
                if row.attempts > 0 and row.attempts >= max(1, row.max_retries):
                    await self._write_job(str(row.id), status='failed', last_error='EXPORT_ATTEMPTS_EXHAUSTED', completed_at=datetime.utcnow())
                    state = 'failed'
                else:
                    await self._write_job(str(row.id), status='pending', last_error='EXPORT_DEFERRED_ON_SHUTDOWN')
                    state = 'pending'; self.close_report['deferred'] += 1
            self.close_report[state] += 1
            if str(row.id) in self.jobs:
                self.jobs[str(row.id)]['status'] = JobStatus(state)
        self.stats['deferred'] = self.close_report['deferred']
        self._db_uncertain.clear()

    async def _finalize_close(self):
        if self._monitor is not None:
            # running is already false. Let an in-progress owner SQL finish;
            # cancelling it could invalidate the dedicated connection itself.
            await self._monitor
            self._monitor = None
        await self._settle_stopped()
        await self._ensure_owner()
        await self._persist_receipt(True)
        await self._ensure_owner()
        await self._release_owner()
        self.workers.clear()
        self.state = QueueState.CLOSED

    async def _close(self):
        if self._planned_reboot_handoff is not None and not self._planned_reboot_complete:
            self.state = QueueState.INCOMPLETE
            raise JobRecoveryRequired('JOB_RECOVERY_HANDOFF_INCOMPLETE')
        if self.state == QueueState.CLOSED and self._owner_connection is None:
            return
        self.state = QueueState.DRAINING
        try:
            deadline = asyncio.get_running_loop().time() + self.drain_seconds
            if self._admissions:
                _, pending = await asyncio.wait(self._admissions, timeout=max(0, deadline - asyncio.get_running_loop().time()))
                if pending:
                    raise JobQueueShutdownIncomplete()
            try:
                await asyncio.wait_for(self.queue.join(), max(0, deadline - asyncio.get_running_loop().time()))
            except asyncio.TimeoutError:
                pass
            self.running = False
            close_deadline = asyncio.get_running_loop().time() + self.close_seconds
            from jobs.export_jobs import request_export_io_stop, wait_export_io
            request_export_io_stop(self._io_keys())
            for worker in self.workers:
                if not worker.cancelling():
                    worker.cancel()
            if self.workers:
                _, pending = await asyncio.wait(self.workers, timeout=max(0, close_deadline - asyncio.get_running_loop().time()))
                if pending:
                    raise JobQueueShutdownIncomplete()
            if not await wait_export_io(self._io_keys(), max(0, close_deadline - asyncio.get_running_loop().time())):
                raise JobQueueShutdownIncomplete()
            if self._owner_lost:
                if self._monitor is not None:
                    self._monitor.cancel()
                    await asyncio.gather(self._monitor, return_exceptions=True)
                await self._release_owner()
                raise JobQueueShutdownIncomplete()
            if self._finalizer is None:
                self._finalizer = asyncio.create_task(self._finalize_close())
            _, pending = await asyncio.wait([self._finalizer], timeout=max(0, close_deadline - asyncio.get_running_loop().time()))
            if pending:
                raise JobQueueShutdownIncomplete()
            self._finalizer.result()
        except BaseException:
            self.state = QueueState.INCOMPLETE
            raise

    async def stop(self):
        if self._stop_task is None or (self._stop_task.done() and self.state == QueueState.INCOMPLETE):
            self.state = QueueState.DRAINING if self.state != QueueState.CLOSED else self.state
            self._stop_task = asyncio.create_task(self._close())
        return await asyncio.shield(self._stop_task)

    async def get_status(self):
        return dict(running=self.running, state=self.state.value, max_workers=self.max_workers,
            queue_size=self.queue.qsize(), stats=self.stats.copy(), total_jobs=len(self.jobs), recovery=self.recovery.copy(), close_report=self.close_report.copy())

    def get_job(self, job_id):
        return self.jobs.get(job_id)
