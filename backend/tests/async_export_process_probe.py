"""Finite test support for a producer crash and a real restart worker.

Both controls use the public queue APIs also present on b8. Native capture is
the approved original; this module neither supplies resources nor judges a run.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
from uuid import uuid4


def private_json(path, value, *, input_file=False):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x') as handle:
        os.chmod(path, 0o600)
        json.dump(value, handle); handle.flush(); os.fsync(handle.fileno())
    if input_file:
        info = path.stat()
        record = dict(path=str(path), uid=info.st_uid, mode=oct(info.st_mode & 0o777), nlink=info.st_nlink,
            dev=info.st_dev, inode=info.st_ino, bytes=info.st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        registry = Path(os.environ['ASYNC_QUEUE_PROBE_ROOT']) / 'input-registry.jsonl'
        fd = os.open(registry, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(record) + '\n').encode())
        finally:
            os.close(fd)


def process_fact():
    from database.session import async_engine
    url = async_engine.url
    return dict(version=1, host=socket.gethostname(), boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        pid=os.getpid(), start_ticks=int(Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19]),
        database=hashlib.sha256(json.dumps([url.host, url.port or 5432, url.database, url.username]).encode()).hexdigest())


async def launch_probe(mode, identity):
    root = Path(os.environ['ASYNC_QUEUE_PROBE_ROOT']) / uuid4().hex
    root.mkdir(parents=True, mode=0o700)
    inputs = root / 'input.json'; facts = root / 'facts.json'
    private_json(inputs, identity, input_file=True)
    env = json.loads(Path(os.environ['ASYNC_QUEUE_RUNTIME_ENV']).read_text())
    env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]), EXPORT_DIR=os.environ['EXPORT_DIR'],
        ASYNC_QUEUE_PROBE_ROOT=os.environ['ASYNC_QUEUE_PROBE_ROOT'])
    for key in ['JOB_QUEUE_RECOVERY_CONFIRMED', 'JOB_QUEUE_RECOVERY_PROOF_FILE']:
        env.pop(key, None)
    envfile = root / 'env.json'; private_json(envfile, env, input_file=True)
    argv = [sys.executable, '-B', '-m', 'tests.async_export_process_probe', mode, str(inputs), str(facts)]
    command = dict(id='probe', argv=argv, cwd=str(Path(__file__).resolve().parents[1]), native_timeout_seconds=40,
        invocation_id='A2-probe:' + root.name)
    command.update({k + '_path': str(root / (k + ext)) for k, ext in
        [('stdout', '.txt'), ('stderr', '.txt'), ('intent', '.json'), ('record', '.json')]})
    plan = root / 'plan.json'; private_json(plan, {'commands': [command]}, input_file=True)
    process = await asyncio.create_subprocess_exec(sys.executable, '-B', os.environ['ASYNC_QUEUE_NATIVE_CAPTURE'],
        str(plan), 'probe', str(envfile), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(process.communicate(), 75)
    private_json(root / 'capture-result.json', dict(pid=process.pid, rc=process.returncode,
        stdout_sha256=hashlib.sha256(stdout).hexdigest(), stderr_sha256=hashlib.sha256(stderr).hexdigest()))
    record = json.loads((root / 'record.json').read_text())
    assert record['native_rc'] == 0 and not record['timed_out'], 'PROBE_NATIVE_PROCESS_FAILED'
    fact = json.loads(facts.read_text())
    assert fact['pid'] == record['pid'] and fact['start_ticks'] == record['start_ticks']
    # A matching live identity would refute the required old-owner exit premise.
    try:
        alive = int(Path('/proc/' + str(fact['pid']) + '/stat').read_text().rsplit(')', 1)[1].split()[19]) == fact['start_ticks']
    except FileNotFoundError:
        alive = False
    assert not alive, 'OLD_OWNER_IDENTITY_STILL_ALIVE'
    return fact, root


async def launch_controlled_probe(mode, identity):
    """Same native capture, but keep the producer alive across named barriers."""
    root = Path(os.environ['ASYNC_QUEUE_PROBE_ROOT']) / uuid4().hex
    root.mkdir(parents=True, mode=0o700)
    source = root / 'input.json'
    private_json(source, identity, input_file=True)
    env = json.loads(Path(os.environ['ASYNC_QUEUE_RUNTIME_ENV']).read_text())
    env.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]), EXPORT_DIR=os.environ['EXPORT_DIR'],
        ASYNC_QUEUE_PROBE_ROOT=os.environ['ASYNC_QUEUE_PROBE_ROOT'])
    env.pop('JOB_QUEUE_RECOVERY_PROOF_FILE', None)
    if mode == 'startup':
        env['JOB_QUEUE_RECOVERY_CONFIRMED'] = '1'
    else:
        env.pop('JOB_QUEUE_RECOVERY_CONFIRMED', None)
    envfile = root / 'env.json'; private_json(envfile, env, input_file=True)
    command = dict(id='controlled-probe', argv=[sys.executable, '-B', '-m',
        'tests.async_export_process_probe', 'control-' + mode, str(source), str(root / 'facts.json')],
        cwd=str(Path(__file__).resolve().parents[1]), native_timeout_seconds=60,
        invocation_id='A2R1R1-controlled:' + root.name)
    command.update({k + '_path': str(root / (k + ext)) for k, ext in
        [('stdout', '.txt'), ('stderr', '.txt'), ('intent', '.json'), ('record', '.json')]})
    plan = root / 'plan.json'; private_json(plan, {'commands': [command]}, input_file=True)
    process = await asyncio.create_subprocess_exec(sys.executable, '-B', os.environ['ASYNC_QUEUE_NATIVE_CAPTURE'],
        str(plan), 'controlled-probe', str(envfile), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    return process, root


async def close_controlled_owner(queue, root):
    """Observe a real close; only the documented owner-loss path is tolerated."""
    from core.jobs.base import JobQueueNotAccepting, JobQueueShutdownIncomplete
    close_error = None
    close_attempts = []
    try:
        await queue.stop()
    except Exception as error:
        close_error = error
        close_attempts.append(dict(exception_class=type(error).__name__, exception_code=getattr(error, 'code', None)))
        # Legacy stop can first discover a dead connection in its final owner
        # check. Retry only that known incomplete close, through the real API.
        if isinstance(error, JobQueueNotAccepting) and error.code == 'JOB_QUEUE_OWNER_LOST' and queue._owner_lost:
            try:
                await queue.stop()
            except Exception as retry_error:
                close_error = retry_error
                close_attempts.append(dict(exception_class=type(retry_error).__name__,
                    exception_code=getattr(retry_error, 'code', None)))
            else:
                close_error = None
    private_json(root / 'close-result.json', dict(phase='old owner close', success=close_error is None,
        exception_class=type(close_error).__name__ if close_error else None,
        exception_code=getattr(close_error, 'code', None), state=queue.state.value, attempts=close_attempts,
        owner_connection_released=queue._owner_connection is None,
        workers_done=all(worker.done() for worker in queue.workers), recorded_monotonic_ns=time.monotonic_ns()))
    if close_error is not None:
        if not (isinstance(close_error, JobQueueShutdownIncomplete) and queue._owner_lost
                and queue._owner_connection is None and all(worker.done() for worker in queue.workers)):
            raise close_error


async def controlled_main(mode, identity, target):
    from unittest.mock import patch
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from database.session import AsyncSessionLocal
    from core.jobs.local_queue import LocalJobQueue
    from models.job import Job
    import jobs.export_jobs
    root = target.parent
    queue = LocalJobQueue(1)
    original_commit = AsyncSession.commit
    original_write = queue._write_job
    reached = False
    job_id = None

    async def barrier(jid):
        nonlocal reached, job_id
        reached = True; job_id = str(jid)
        marker = queue._receipt_path()
        private_json(root / 'ready.json', dict(process_fact(), job_id=job_id, file_id=identity['file_id'],
            owner_backend=queue._owner_backend, state=queue.state.value,
            marker=json.loads(marker.read_text()) if marker.exists() else None, mode=mode))
        async def released():
            while not (root / 'release.json').exists():
                await asyncio.sleep(0.005)
        await asyncio.wait_for(released(), 35)

    async def commit(db):
        if not reached:
            # Flush reveals a genuine uncommitted row to THIS transaction;
            # the parent independently proves it is invisible outside it.
            await db.flush()
            jid = (await db.execute(select(Job.id).where(Job.job_name == 'export_report',
                Job.payload['file_id'].as_string() == identity['file_id']))).scalar_one()
            if mode == 'accept-committed':
                await original_commit(db)
                await barrier(jid)
                return
            await barrier(jid)
        await original_commit(db)

    async def write(jid, **values):
        if not reached:
            await barrier(jid)
        return await original_write(jid, **values)

    failure = None
    failure_code = None
    phase = 'queue.start'
    try:
        if mode == 'startup':
            queue._write_job = write  # pause before the real state writer, never replace its decision
            await queue.start()
        else:
            await queue.start()
            await queue.semaphore.acquire()
            phase = 'queue.enqueue'
            with patch.object(AsyncSession, 'commit', commit):
                await queue.enqueue('export_report', identity, max_retries=2)
    except Exception as error:
        failure = type(error).__name__
        failure_code = getattr(error, 'code', None)
    # Preserve the actual operation before any fallible observer SQL.
    private_json(root / 'operation-result.json', dict(process_fact(), mode=mode, job_id=job_id,
        phase=phase, success=failure is None, exception_class=failure,
        exception_code=failure_code, recorded_monotonic_ns=time.monotonic_ns()))
    assert reached, 'CONTROLLED_PRODUCER_DID_NOT_REACH_REAL_BOUNDARY'
    try:
        async with AsyncSessionLocal() as db:
            db.info['tenant_schema'] = 'public'
            row = (await db.execute(select(Job).where(Job.id == __import__('uuid').UUID(job_id)))).scalar_one_or_none()
            private_json(root / 'settled.json', dict(process_fact(), job_id=job_id, exception_class=failure, exception_code=failure_code,
                row_exists=row is not None, status=row.status if row else None,
                attempts=row.attempts if row else None, payload=row.payload if row else None))
    except Exception as error:
        private_json(root / 'observation-result.json', dict(phase='public.sys_jobs observation', success=False,
            exception_class=type(error).__name__, exception_code=getattr(error, 'code', None),
            recorded_monotonic_ns=time.monotonic_ns()))
        raise
    private_json(root / 'observation-result.json', dict(phase='public.sys_jobs observation', success=True,
        exception_class=None, exception_code=None, recorded_monotonic_ns=time.monotonic_ns()))
    await close_controlled_owner(queue, root)
    private_json(target, dict(process_fact(), job_id=job_id, mode=mode, exception_class=failure, exception_code=failure_code))
    os._exit(0)


async def _owner_loss_main(target):
    """One explicit fault scenario; never enter the generic export enqueue."""
    engines = []
    primary = None
    secondary = []
    result = None
    try:
        from database.session import async_engine
        engines.append(async_engine)
        from database.reporting_session import reporting_engine
        engines.append(reporting_engine)
        from tests.test_async_queue_lifecycle import _exercise_owner_loss_refusal
        result = await _exercise_owner_loss_refusal()
    except BaseException as error:
        primary = error
    for engine in engines:
        try:
            await engine.dispose()
        except BaseException as error:
            if primary is None:
                primary = error
            else:
                secondary.append(type(error).__name__)
    try:
        private_json(target.parent / 'owner-loss-operation-result.json', dict(
            success=primary is None, exception_class=type(primary).__name__ if primary else None,
            exception_code=getattr(primary, 'code', None), secondary_errors=secondary,
            matching_live_owner_branch='NOT_VERIFIED'))
    except BaseException as error:
        if primary is None:
            primary = error
        else:
            primary.add_note('OWNER_ISOLATION_SECONDARY_RECORD:' + type(error).__name__)
    if primary is not None:
        if secondary:
            primary.add_note('OWNER_ISOLATION_SECONDARY_DISPOSE:' + ','.join(secondary))
        raise primary
    private_json(target, dict(process_fact(), mode='owner-loss-refusal', **result))


async def main():
    mode, source, target = sys.argv[1:]
    identity = json.loads(Path(source).read_text())
    if mode == 'owner-loss-refusal':
        return await _owner_loss_main(Path(target))
    if mode.startswith('control-'):
        return await controlled_main(mode[len('control-'):], identity, Path(target))
    from core.jobs.base import get_job_registry
    from core.jobs.local_queue import LocalJobQueue
    import jobs.export_jobs
    queue = LocalJobQueue(max_workers=1)
    ready = asyncio.Event(); release = asyncio.Event()
    original = get_job_registry()['export_report']
    if mode in ('running', 'result'):
        async def paused(payload):
            if mode == 'result':
                await original(payload)
            ready.set()
            await release.wait()
        get_job_registry()['export_report'] = paused
    await queue.start()
    if mode == 'pending':
        await queue.semaphore.acquire()
    jid = await queue.enqueue('export_report', identity, max_retries=2)
    if mode != 'pending':
        await asyncio.wait_for(ready.wait(), 15)
    private_json(Path(target), dict(process_fact(), job_id=jid, file_id=identity['file_id'], mode=mode,
        producer_module=str(Path(__file__).resolve())))
    # A deliberate process exit, not a fake successful queue.stop().
    os._exit(0)


if __name__ == '__main__':
    asyncio.run(main())
