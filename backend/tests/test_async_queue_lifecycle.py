"""Finite A2 lifecycle controls; the two BASE controls use shared public APIs."""
import asyncio
from contextlib import suppress
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
import threading
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text

from core.jobs import LocalJobQueue, job_handler, get_job_registry
from database.session import AsyncSessionLocal
from models.job import Job
from tests.async_export_process_probe import launch_probe, private_json, process_fact, launch_controlled_probe


async def rows(ids):
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        return (await db.execute(select(Job).where(Job.id.in_([UUID(str(j)) for j in ids])))).scalars().all()


async def remove(ids):
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        await db.execute(delete(Job).where(Job.id.in_([UUID(str(j)) for j in ids])))
        await db.commit()


async def seed(identity, *, name='export_report', status='pending', attempts=0, retries=2, deleted=False):
    jid = uuid4()
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        db.add(Job(id=jid, job_name=name, payload=identity, status=status, attempts=attempts,
                   max_retries=retries, is_deleted=deleted))
        await db.commit()
    return str(jid)


async def until(predicate, seconds=3):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.005)
    await asyncio.wait_for(poll(), seconds)


async def export_world(tmp_path, monkeypatch):
    from jobs import export_jobs
    from tests.test_dc10e_export_worker_tenant_context import _create_reporting_table
    from tests.test_async_export_formats import payload
    identity = payload(); identity['tenant_id'] = str(uuid4()); identity['tenant_schema'] = 't_' + UUID(identity['tenant_id']).hex
    await _create_reporting_table(identity['tenant_schema'], '123.4500')
    # All queue generations in this database use one controlled state path.
    # Each artifact still has an independently generated tenant/file identity.
    directory = Path(os.environ['EXPORT_DIR']); directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(export_jobs, 'EXPORT_DIR', directory)
    monkeypatch.setenv('EXPORT_DIR', str(directory))
    return identity


async def drop_world(identity):
    from tests.test_dc10e_export_worker_tenant_context import _drop_reporting_schema
    await _drop_reporting_schema(identity['tenant_schema'])


async def proof_from_child(identity, mode, monkeypatch):
    fact, root = await launch_probe(mode, identity)
    # Wait on an observable lock fact, not a guessed post-exit sleep.
    async def unlocked():
        async with AsyncSessionLocal() as db:
            db.info['tenant_schema'] = 'public'
            return not (await db.execute(text("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND classid=742019 AND objid=5106 AND granted)"))).scalar_one()
    async def wait_unlock():
        while not await unlocked():
            await asyncio.sleep(0.005)
    await asyncio.wait_for(wait_unlock(), 5)
    proof = root / 'exit-proof.json'; private_json(proof, fact, input_file=True)
    monkeypatch.setenv('JOB_QUEUE_RECOVERY_CONFIRMED', '1')
    monkeypatch.setenv('JOB_QUEUE_RECOVERY_PROOF_FILE', str(proof))
    return fact


@pytest.mark.asyncio
async def test_not_accepting_refuses_without_persistent_write(tmp_path, monkeypatch):
    from core.jobs.base import JobQueueNotAccepting
    from api.schemas.jobs import ExportRequest
    from api.v1.exports import create_export
    from tests.test_dc10e_export_worker_tenant_context import _request_with_context, _exports_create_token
    queue = LocalJobQueue(1)
    async with AsyncSessionLocal() as db:
        before = (await db.execute(text('SELECT count(*) FROM public.sys_jobs'))).scalar_one()
    with pytest.raises(JobQueueNotAccepting, match='JOB_QUEUE_NOT_ACCEPTING'):
        await queue.enqueue('export_report', {})
    monkeypatch.setattr('main.get_job_queue', lambda: queue)
    request = _request_with_context(); token = await _exports_create_token(request)
    response = await create_export(request, ExportRequest(view='sales_daily', metrics=['revenue']), token)
    assert response.status_code == 503 and json.loads(response.body)['error']['code'] == 'JOB_QUEUE_NOT_ACCEPTING'
    async with AsyncSessionLocal() as db:
        assert (await db.execute(text('SELECT count(*) FROM public.sys_jobs'))).scalar_one() == before


@pytest.mark.asyncio
async def test_committed_acceptance_survives_caller_cancel_and_close(monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    queue = LocalJobQueue(1); await queue.start()
    committed = asyncio.Event(); release = asyncio.Event(); executed = []
    @job_handler('a2_acceptance')
    async def handler(data): executed.append(data)
    original = AsyncSession.commit; armed = True
    async def paused(db):
        nonlocal armed
        await original(db)
        if armed:
            armed = False; committed.set(); await release.wait()
    ids = []
    try:
        with patch.object(AsyncSession, 'commit', paused):
            caller = asyncio.create_task(queue.enqueue('a2_acceptance', {'sent': 1}))
            await asyncio.wait_for(committed.wait(), 5)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError): await caller
            closing = asyncio.create_task(queue.stop())
            release.set(); await asyncio.wait_for(closing, 5)
        ids = list(queue.jobs)
        assert len(ids) == 1 and executed == [{'sent': 1}], 'COMMITTED_ACCEPTANCE_WAS_LOST'
        assert (await rows(ids))[0].status == 'completed'
        assert queue.close_report['accepted_rows'] == queue.close_report['completed'] == 1
    finally:
        release.set(); await queue.stop(); await remove(ids or list(queue._owned))


@pytest.mark.asyncio
async def test_public_stop_drains_accepted_backlog():
    # This exact test is copied to b8 for the shared-entry BASE counterexample.
    queue = LocalJobQueue(max_workers=1); await queue.start()
    queue.drain_seconds = 0.5
    entered = asyncio.Event(); release = asyncio.Event(); executed = []; ids = []; closing = None
    @job_handler('a2_backlog')
    async def handler(data):
        entered.set(); await release.wait(); executed.append(data['index'])
    try:
        for i in range(3): ids.append(await queue.enqueue('a2_backlog', {'index': i}))
        await asyncio.wait_for(entered.wait(), 3)
        closing = asyncio.create_task(queue.stop())
        await asyncio.sleep(0)  # scheduled stop reaches its first await before release
        release.set()
        await asyncio.wait({closing}, timeout=2)
        assert executed == [0, 1, 2], 'ACCEPTED_BACKLOG_NOT_DRAINED'
        assert closing.done() and closing.exception() is None
        assert all(row.status == 'completed' for row in await rows(ids))
    finally:
        release.set()
        if closing is not None and not closing.done():
            closing.cancel()
            with suppress(asyncio.CancelledError): await closing
        for worker in queue.workers:
            if not worker.done(): worker.cancel()
        if queue.workers: await asyncio.gather(*queue.workers, return_exceptions=True)
        await remove(ids)


@pytest.mark.asyncio
async def test_public_restart_recovers_pending_same_identity(tmp_path, monkeypatch, ensure_reporting_user_password):
    # No candidate-only production API is imported by this BASE control.
    identity = await export_world(tmp_path, monkeypatch); queue = None; ids = []
    try:
        fact = await proof_from_child(identity, 'pending', monkeypatch); ids = [fact['job_id']]
        queue = LocalJobQueue(max_workers=1); await queue.start()
        await asyncio.wait_for(queue.queue.join(), 10)
        row = (await rows(ids))[0]
        assert row.status == 'completed', 'PENDING_EXPORT_NOT_RECOVERED_SAME_IDENTITY'
        assert row.payload == identity and row.attempts == 1 and str(row.id) == fact['job_id']
        from jobs.export_jobs import read_metadata
        meta = read_metadata(identity['file_id'])
        assert meta['tenant_id'] == identity['tenant_id'] and meta['file_id'] == fact['file_id']
    finally:
        if queue is not None: await queue.stop()
        await remove(ids); await drop_world(identity)


@pytest.mark.asyncio
async def test_running_restart_preserves_attempts_and_owner_exit(tmp_path, monkeypatch, ensure_reporting_user_password):
    identity = await export_world(tmp_path, monkeypatch); queue = None; ids = []
    try:
        fact = await proof_from_child(identity, 'running', monkeypatch); ids = [fact['job_id']]
        before = (await rows(ids))[0]
        assert before.status == 'running' and before.attempts == 1
        queue = LocalJobQueue(1); await queue.start(); await asyncio.wait_for(queue.queue.join(), 10)
        row = (await rows(ids))[0]
        assert row.status == 'completed' and row.attempts == 2 and row.payload == identity
        assert queue.recovery['replayed'] == 1
    finally:
        if queue is not None: await queue.stop()
        await remove(ids); await drop_world(identity)


@pytest.mark.asyncio
async def test_complete_result_reconciles_without_handler_or_requery(tmp_path, monkeypatch, ensure_reporting_user_password):
    identity = await export_world(tmp_path, monkeypatch); queue = None; ids = []
    original = get_job_registry()['export_report']
    try:
        fact = await proof_from_child(identity, 'result', monkeypatch); ids = [fact['job_id']]
        assert (await rows(ids))[0].status == 'running'
        from jobs import export_jobs
        path = export_jobs.EXPORT_DIR / (identity['file_id'] + '.csv'); before = path.read_bytes()
        async def forbidden(data): raise AssertionError('RECONCILE_MUST_NOT_RERUN_HANDLER')
        monkeypatch.setitem(get_job_registry(), 'export_report', forbidden)
        queue = LocalJobQueue(1); await queue.start(); await asyncio.wait_for(queue.queue.join(), 5)
        row = (await rows(ids))[0]
        assert row.status == 'completed' and row.attempts == 1 and path.read_bytes() == before
        assert queue.recovery == dict(found=1, replayed=0, completed_reconciled=1, unrecoverable_failed=0, manual_blocked=0)
    finally:
        get_job_registry()['export_report'] = original
        if queue is not None: await queue.stop()
        await remove(ids); await drop_world(identity)


@pytest.mark.asyncio
async def test_unknown_preserved_then_valid_and_invalid_classified(tmp_path, monkeypatch, ensure_reporting_user_password):
    from core.jobs.base import JobRecoveryRequired
    identity = await export_world(tmp_path, monkeypatch); ids = []; queue = None
    try:
        fact = await proof_from_child(identity, 'pending', monkeypatch); ids.append(fact['job_id'])
        bad = await seed({**identity, 'file_id': uuid4().hex, 'tenant_schema': 't_' + uuid4().hex}); ids.append(bad)
        unknown = await seed({}, name='unknown_handler'); ids.append(unknown)
        refused = LocalJobQueue(1)
        with pytest.raises(JobRecoveryRequired, match='JOB_RECOVERY_MANUAL_REQUIRED'): await refused.start()
        assert all(row.status == 'pending' for row in await rows(ids))
        assert refused.recovery['manual_blocked'] == 1
        await remove([unknown]); ids.remove(unknown)
        queue = LocalJobQueue(1); await queue.start(); await asyncio.wait_for(queue.queue.join(), 10)
        result = {str(row.id): row for row in await rows(ids)}
        assert result[fact['job_id']].status == 'completed'
        assert result[bad].status == 'failed' and result[bad].last_error == 'EXPORT_RECOVERY_TENANT_MISMATCH'
        assert queue.recovery['replayed'] == queue.recovery['unrecoverable_failed'] == 1
    finally:
        if queue is not None: await queue.stop()
        await remove(ids); await drop_world(identity)


@pytest.mark.asyncio
async def test_attempt_boundaries_and_deleted_rows_not_rewritten(tmp_path, monkeypatch, ensure_reporting_user_password):
    identity = await export_world(tmp_path, monkeypatch); ids = []; queue = None
    try:
        fact = await proof_from_child(identity, 'pending', monkeypatch); ids.append(fact['job_id'])
        first = await seed({**identity, 'file_id': uuid4().hex}, retries=0); ids.append(first)
        exhausted = await seed({**identity, 'file_id': uuid4().hex}, attempts=2, retries=2); ids.append(exhausted)
        deleted = await seed({}, deleted=True); ids.append(deleted)
        terminal = await seed({}, status='failed'); ids.append(terminal)
        queue = LocalJobQueue(1); await queue.start(); await asyncio.wait_for(queue.queue.join(), 10)
        result = {str(row.id): row for row in await rows(ids)}
        assert result[first].status == 'completed' and result[first].attempts == 1
        assert result[exhausted].status == 'failed' and result[exhausted].attempts == 2
        assert result[exhausted].last_error == 'EXPORT_RECOVERY_ATTEMPTS_EXHAUSTED'
        assert result[deleted].status == 'pending' and result[deleted].attempts == 0
        assert result[terminal].status == 'failed' and result[terminal].last_error is None
        assert queue.recovery['found'] == 3
    finally:
        if queue is not None: await queue.stop()
        await remove(ids); await drop_world(identity)


@pytest.mark.asyncio
async def test_confirmation_flag_cannot_prove_live_owner_exit(tmp_path, monkeypatch):
    from core.jobs.base import JobRecoveryRequired
    identity = await export_world(tmp_path, monkeypatch)
    fact = await proof_from_child(identity, 'pending', monkeypatch); jid = fact['job_id']
    proof = tmp_path / 'live-proof.json'; private_json(proof, process_fact(), input_file=True)
    monkeypatch.setenv('JOB_QUEUE_RECOVERY_CONFIRMED', '1')
    monkeypatch.setenv('JOB_QUEUE_RECOVERY_PROOF_FILE', str(proof))
    try:
        queue = LocalJobQueue(1)
        with pytest.raises(JobRecoveryRequired, match='JOB_RECOVERY_OWNER_EXIT_UNPROVEN'): await queue.start()
        assert (await rows([jid]))[0].status == 'pending' and queue.recovery['found'] == 0
    finally:
        real_proof = tmp_path / 'exit-proof.json'; private_json(real_proof, fact, input_file=True)
        monkeypatch.setenv('JOB_QUEUE_RECOVERY_PROOF_FILE', str(real_proof))
        closed = LocalJobQueue(1); await closed.start(); await closed.stop()
        await remove([jid]); await drop_world(identity)


async def wait_probe_fact(root, name):
    path = root / name
    await until(path.exists, seconds=15)
    return json.loads(path.read_text())


async def finish_controlled_probe(process, root, *, primary_error=None):
    import hashlib
    plan_bytes = (root / 'plan.json').read_bytes()
    commands = json.loads(plan_bytes)['commands']
    assert len(commands) == 1, 'CONTROLLED_PRODUCER_PLAN_AMBIGUOUS'
    command = commands[0]
    binding = (str(root.resolve()), hashlib.sha256(plan_bytes).hexdigest(), command['invocation_id'], process.pid)
    release = root / 'release.json'
    if not release.exists(): private_json(release, {'release': True}, input_file=True)
    cached = getattr(process, '_a2_completion', None)
    if cached is None:
        async def collect():
            out, err = await asyncio.wait_for(process.communicate(), 90)
            private_json(root / 'capture-result.json', {'capture_pid':process.pid,
                'invocation_id':command['invocation_id'], 'capture_rc': process.returncode,
                'stdout_sha256':hashlib.sha256(out).hexdigest(), 'stderr_sha256':hashlib.sha256(err).hexdigest()})
            rec = json.loads((root / 'record.json').read_text())
            assert rec['invocation_id'] == command['invocation_id'] and rec['argv'] == command['argv']
            assert rec['cwd'] == command['cwd'] and rec['metadata_errors'] == []
            actual = json.loads((root / 'intent.process.json').read_text())
            assert all(actual[key] == rec[key] for key in ('pid', 'pgid', 'start_ticks'))
            for value in rec['outputs'].values():
                data = Path(value['path']).read_bytes()
                assert len(data) == value['bytes'] and hashlib.sha256(data).hexdigest() == value['sha256']
            assert process.returncode == 0 and rec['native_rc'] == 0 and not rec['timed_out'], 'CONTROLLED_PRODUCER_NATIVE_FAILED'
            assert (root / 'facts.json').is_file(), 'CONTROLLED_PRODUCER_FACTS_MISSING'
            fact = json.loads((root / 'facts.json').read_text())
            assert (fact['pid'], fact['start_ticks']) == (rec['pid'], rec['start_ticks'])
            try:
                alive = LocalJobQueue._ticks(fact['pid']) == fact['start_ticks']
            except FileNotFoundError:
                alive = False
            assert not alive, 'CONTROLLED_OLD_PID_STILL_ALIVE'
            return fact
        cached = {'binding':binding, 'task':asyncio.create_task(collect()), 'cleanup_recorded':False}
        process._a2_completion = cached
    assert cached['binding'] == binding, 'CONTROLLED_PRODUCER_COMPLETION_IDENTITY_CHANGED'
    try:
        return await asyncio.shield(cached['task'])
    except Exception as error:
        if primary_error is None:
            raise
        if not cached['cleanup_recorded']:
            private_json(root / 'cleanup-result.json', {'invocation_id':command['invocation_id'],
                'primary_class':type(primary_error).__name__, 'completion_class':type(error).__name__,
                'same_primary_exception':primary_error is error, 'nonpassing_completion_retained':True})
            cached['cleanup_recorded'] = True
        # Cleanup is not a passing result; the caller's original exception
        # remains active and must propagate after finally.
        return None


async def terminate_probe_owner(root, fact, identity):
    assert LocalJobQueue._ticks(fact['pid']) == fact['start_ticks'], 'OLD_PID_MUST_BE_ALIVE_AT_LOSS'
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        matches = (await db.execute(text("SELECT pid FROM pg_locks WHERE locktype='advisory' AND classid=742019 AND objid=5106 AND granted AND pid=:p"), {'p': fact['owner_backend']})).scalars().all()
        assert matches == [fact['owner_backend']], 'FAULT_TARGET_NOT_THIS_REGISTERED_OWNER'
        visible = (await db.execute(select(Job).where(Job.job_name == 'export_report',
            Job.payload['file_id'].as_string() == identity['file_id']))).scalars().all()
        before = [{'id':str(x.id),'status':x.status,'attempts':x.attempts,'payload':x.payload} for x in visible]
        killed = (await db.execute(text('SELECT pg_terminate_backend(:p)'), {'p': fact['owner_backend']})).scalar_one()
        assert killed is True
    async def absent():
        async with AsyncSessionLocal() as db:
            while (await db.execute(text("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND classid=742019 AND objid=5106 AND granted AND pid=:p)"), {'p':fact['owner_backend']})).scalar_one():
                await asyncio.sleep(0.005)
    await asyncio.wait_for(absent(), 5)
    private_json(root / 'parent-loss-facts.json', dict(old_pid_alive=True, old_pid=fact['pid'],
        old_start_ticks=fact['start_ticks'], host=fact['host'], boot=fact['boot'], database=fact['database'],
        owner_backend=fact['owner_backend'], exact_lock_pid_matched=matches == [fact['owner_backend']],
        old_transaction_visible_rows=before, terminate_returned=killed))
    return before


async def public_job_vector():
    """Version-neutral pre-fault vector; no v2 row identity imported."""
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        all_rows = (await db.execute(select(Job).order_by(Job.id))).scalars().all()
    return {str(row.id): json.loads(json.dumps(
        {col.name:getattr(row, col.name) for col in Job.__table__.columns}, sort_keys=True, default=str))
        for row in all_rows}


async def common_takeover_checkpoint(premature, root, fact, identity, before, filename):
    """Observe the common start boundary before ANY v2 proof or cleanup."""
    old_alive_before = LocalJobQueue._ticks(fact['pid']) == fact['start_ticks']
    succeeded = False; error = None
    try:
        await premature.start()
        succeeded = True
    except Exception as caught:
        error = caught
    # Actual outcome is durable before any fallible observer or close.
    attempt = dict(start_succeeded=succeeded, exception_class=type(error).__name__ if error else None,
        rejection_code=getattr(error, 'code', None), successor_state=premature.state.value,
        successor_backend=premature._owner_backend, old_pid=fact['pid'], old_start_ticks=fact['start_ticks'],
        old_pid_alive_before=old_alive_before)
    private_json(root / (filename + '-operation.json'), attempt)
    old_alive_after = LocalJobQueue._ticks(fact['pid']) == fact['start_ticks']
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        visible = (await db.execute(select(Job).where(Job.job_name == 'export_report',
            Job.payload['file_id'].as_string() == identity['file_id']))).scalars().all()
        locks = (await db.execute(text("SELECT pid FROM pg_locks WHERE locktype='advisory' AND classid=742019 AND objid=5106 AND granted ORDER BY pid"))).scalars().all()
    loss = json.loads((root / 'parent-loss-facts.json').read_text())
    result = dict(attempt, old_pid_alive_after=old_alive_after, owner_loss=loss,
        visible_before=before, visible_after=[{'id':str(x.id), 'status':x.status,
        'attempts':x.attempts, 'payload':x.payload} for x in visible], actual_lock_backends=locks)
    private_json(root / (filename + '.json'), result)
    if error is not None:
        from core.jobs.base import JobRecoveryRequired
        if not isinstance(error, JobRecoveryRequired):
            raise error
    return result


def require_common_no_takeover(observed, signature):
    """One oracle across sources: only a successful takeover is semantic RED."""
    loss = observed['owner_loss']
    assert observed['old_pid_alive_before'] and observed['old_pid_alive_after'], 'COMMON_OLD_PID_PREMISE_FALSE'
    assert (loss['old_pid'], loss['old_start_ticks']) == (observed['old_pid'], observed['old_start_ticks'])
    assert loss['exact_lock_pid_matched'] and loss['terminate_returned'], 'COMMON_OWNER_LOCK_PREMISE_FALSE'
    assert loss['old_transaction_visible_rows'] == observed['visible_before'], 'COMMON_VISIBILITY_PREMISE_FALSE'
    assert loss['owner_backend'] not in observed['actual_lock_backends'], 'COMMON_OLD_LOCK_NOT_RELEASED'
    if observed['start_succeeded']:
        assert observed['exception_class'] is None and observed['rejection_code'] is None
        assert observed['successor_state'] == 'ACCEPTING', 'COMMON_START_STATE_CONTRADICTION'
        assert observed['successor_backend'] in observed['actual_lock_backends'], 'COMMON_SUCCESSOR_LOCK_MISSING'
        raise AssertionError(signature)
    assert observed['exception_class'] == 'JobRecoveryRequired', 'COMMON_UNEXPECTED_REJECTION_CLASS'
    assert observed['rejection_code'] == 'JOB_RECOVERY_OWNER_EXIT_UNPROVEN', 'COMMON_UNEXPECTED_REJECTION_CODE'
    assert observed['successor_state'] != 'ACCEPTING', 'COMMON_REJECTED_BUT_ACCEPTING'


def require_v2_starting_checkpoint(fact, older_marker, checkpoint):
    """Mandatory current-candidate proof, intentionally after common judgment."""
    assert fact['state'] == 'STARTING' and fact['marker']['state'] == 'STARTING'
    assert fact['marker']['generation'] != older_marker['generation']
    assert fact['marker'] == checkpoint


async def close_combination_resources(process, root, premature, successor, ids, identity, primary_error):
    """One native completion; primary failure survives secondary cleanup errors."""
    failures = []
    steps = []
    async def step(label, action):
        try:
            result = await action()
            if label == 'premature_stop':
                assert premature.state.value == 'CLOSED' and premature._owner_connection is None, 'PREMATURE_OWNER_NOT_CLOSED'
                assert all(worker.done() for worker in premature.workers), 'PREMATURE_WORKERS_NOT_CLOSED'
            if label == 'native_completion':
                assert isinstance(result, dict), 'CONTROLLED_COMPLETION_NOT_PASSING'
        except Exception as error:
            failures.append((label, error))
            steps.append({'phase':label, 'success':False, 'class':type(error).__name__, 'code':getattr(error, 'code', None)})
        else:
            steps.append({'phase':label, 'success':True, 'class':None, 'code':None})
    # The dangerous takeover is already recorded/judged by the caller. Close
    # that successor BEFORE releasing the old startup tail that can overwrite
    # its marker on the version under counterexample. Never rewrite a marker.
    if premature is not None:
        await step('premature_stop', premature.stop)
    if process is not None:
        await step('native_completion', lambda: finish_controlled_probe(process, root, primary_error=primary_error))
    if successor is not None:
        await step('successor_stop', successor.stop)
    await step('remove_target_rows', lambda: remove(ids))
    await step('drop_target_schema', lambda: drop_world(identity))
    if root is not None:
        private_json(root / 'combination-cleanup-order.json', {'primary_class':type(primary_error).__name__ if primary_error else None,
            'steps':steps, 'counter_cleanup_closed':not failures})
    if failures:
        if root is not None:
            private_json(root / 'secondary-cleanup-failures.json', {'primary_class':type(primary_error).__name__ if primary_error else None,
                'secondary':[{'phase':label, 'class':type(error).__name__, 'code':getattr(error, 'code', None)}
                    for label, error in failures]})
        if primary_error is None:
            raise failures[0][1]


async def owner_checkpoint():
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        return (await db.execute(select(Job.payload).where(Job.job_name == '__local_queue_owner_v2__'))).scalar_one_or_none()


async def assert_owner_internal_boundary(queue, ids, root, label, *, expected_found=None):
    """Real public rows and route consumers; this is not login/HTTP E2E."""
    from core.jobs.local_queue import OWNER_ROW_ID, OWNER_ROW_NAME
    from api.v1.exports import get_export_status, download_export
    from tests.test_dc10e_export_worker_tenant_context import (
        _request_with_context, _exports_create_token, TENANT_A_ID, TENANT_B_ID,
    )
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        all_rows = (await db.execute(select(Job).order_by(Job.id))).scalars().all()
    owners = [row for row in all_rows if row.id == OWNER_ROW_ID or row.job_name == OWNER_ROW_NAME]
    assert len(owners) == 1, 'INTERNAL_OWNER_IDENTITY_NOT_UNIQUE'
    owner = owners[0]
    assert OWNER_ROW_ID.version == 5 and all(UUID(value).version == 4 for value in ids)
    assert owner.id == OWNER_ROW_ID and owner.job_name == OWNER_ROW_NAME and owner.status == 'completed'
    assert owner.attempts == owner.max_retries == 0 and owner.is_deleted is False
    assert str(OWNER_ROW_ID) not in ids, 'INTERNAL_OWNER_STOLE_BUSINESS_JOB_ID'
    if queue is not None:
        assert str(OWNER_ROW_ID) not in queue.jobs
        assert all(item['job_id'] != str(OWNER_ROW_ID) for item in queue.queue._queue)
        assert queue.recovery['found'] == expected_found, 'INTERNAL_OWNER_COUNTED_AS_RECOVERABLE_JOB'
    route_results = []
    for tenant in (TENANT_A_ID, TENANT_B_ID):
        request = _request_with_context(tenant)
        token = await _exports_create_token(request)
        for consumer in (get_export_status, download_export):
            response = await consumer(request, str(OWNER_ROW_ID), token)
            assert response.status_code == 404
            assert json.loads(response.body)['error']['code'] == 'EXPORT_NOT_FOUND'
            route_results.append({'tenant':tenant, 'consumer':consumer.__name__, 'status':404, 'code':'EXPORT_NOT_FOUND'})
    other_business = {}
    for row in all_rows:
        if row.id == OWNER_ROW_ID or str(row.id) in ids:
            continue
        other_business[str(row.id)] = json.loads(json.dumps(
            {col.name:getattr(row, col.name) for col in Job.__table__.columns}, sort_keys=True, default=str))
    private_json(root / (label + '.json'), {'owner_id':str(OWNER_ROW_ID), 'owner':owner.payload,
        'raw_sys_jobs_count':len(all_rows), 'business_row_count':len(all_rows)-1,
        'internal_row_count':1, 'business_ids':ids, 'other_business':other_business,
        'route_rejections':route_results, 'recovery_found':queue.recovery['found'] if queue else None})
    return other_business


@pytest.mark.asyncio
async def test_inflight_accept_owner_loss_requires_quiescence_before_takeover(tmp_path, monkeypatch, ensure_reporting_user_password):
    """Declared matrix: uncommitted loss rolls back; committed loss recovers once."""
    from core.jobs.base import JobQueueNotAccepting, JobRecoveryRequired
    for mode in ('accept-inflight', 'accept-committed'):
        identity = await export_world(tmp_path, monkeypatch)
        process = None; root = None; successor = None; premature = None; ids = []
        try:
            process, root = await launch_controlled_probe(mode, identity)
            fact = await wait_probe_fact(root, 'ready.json'); ids = [fact['job_id']]
            vector_before = await public_job_vector()
            before = await terminate_probe_owner(root, fact, identity)
            assert len(before) == (0 if mode == 'accept-inflight' else 1), 'COMMIT_VISIBILITY_PREMISE_WRONG'
            premature = LocalJobQueue(1)
            observed = await common_takeover_checkpoint(premature, root, fact, identity, before, 'takeover-facts')
            require_common_no_takeover(observed, 'INFLIGHT_OLD_OWNER_WAS_ALLOWED_TO_TAKE_OVER')
            # v2-only evidence is mandatory, but cannot mask the common RED.
            others_before = await assert_owner_internal_boundary(None, ids, root, 'internal-before')
            assert await public_job_vector() == vector_before, 'EARLY_TAKEOVER_MUTATED_BUSINESS_OR_OWNER_ROW'
            await premature.stop(); premature = None
            dead = await finish_controlled_probe(process, root); process = None
            settled = json.loads((root / 'settled.json').read_text())
            assert settled['row_exists'] is (mode == 'accept-committed'), 'OWNER_BACKEND_TXN_NOT_RESOLVED'
            if mode == 'accept-inflight':
                assert settled['exception_code'] == 'JOB_QUEUE_OWNER_LOST', 'UNCOMMITTED_PRODUCER_FAILURE_NOT_OWNER_LOSS'
            proof = root / 'exit-proof.json'; private_json(proof, dead, input_file=True)
            monkeypatch.setenv('JOB_QUEUE_RECOVERY_CONFIRMED', '1')
            monkeypatch.setenv('JOB_QUEUE_RECOVERY_PROOF_FILE', str(proof))
            successor = LocalJobQueue(1); await successor.start(); await asyncio.wait_for(successor.queue.join(), 10)
            result = await rows(ids)
            if mode == 'accept-inflight':
                assert result == [] and successor.recovery['replayed'] == 0, 'ROLLED_BACK_ACCEPTANCE_WAS_INVENTED'
            else:
                assert len(result) == 1 and result[0].status == 'completed' and result[0].attempts == 1
                assert result[0].payload == identity and str(result[0].id) == fact['job_id'], 'COMMITTED_IDENTITY_CHANGED'
                assert successor.recovery['replayed'] == 1 and successor.stats['completed'] == 1
            assert await assert_owner_internal_boundary(successor, ids, root, 'internal-after',
                expected_found=0 if mode == 'accept-inflight' else 1) == others_before, 'OTHER_BUSINESS_ROW_OVERWRITTEN'
            private_json(root / 'recovered-facts.json', {'same_job_id':fact['job_id'], 'file_id':identity['file_id'],
                'tenant_id':identity['tenant_id'], 'row_count':len(result), 'attempts':[x.attempts for x in result],
                'recovery':successor.recovery.copy()})
        finally:
            await close_combination_resources(process, root, premature, successor, ids, identity, sys.exc_info()[1])


@pytest.mark.asyncio
async def test_owner_loss_during_startup_cannot_publish_or_mutate_successor(tmp_path, monkeypatch, ensure_reporting_user_password):
    """STARTING supersedes old CLOSED; lost writer cannot mutate/publish after loss."""
    from core.jobs.base import JobQueueNotAccepting, JobRecoveryRequired
    from jobs import export_jobs
    identity = await export_world(tmp_path, monkeypatch)
    prior = LocalJobQueue(1); await prior.start(); await prior.stop()
    older_marker = json.loads(prior._receipt_path().read_text())
    jid = await seed(identity); process = None; root = None; successor = None; premature = None
    try:
        process, root = await launch_controlled_probe('startup', identity)
        fact = await wait_probe_fact(root, 'ready.json')
        vector_before = await public_job_vector()
        before = await terminate_probe_owner(root, fact, identity)
        assert len(before) == 1 and before[0]['id'] == jid and before[0]['attempts'] == 0
        premature = LocalJobQueue(1)
        monkeypatch.setenv('JOB_QUEUE_RECOVERY_CONFIRMED', '1')
        monkeypatch.delenv('JOB_QUEUE_RECOVERY_PROOF_FILE', raising=False)
        observed = await common_takeover_checkpoint(premature, root, fact, identity, before, 'startup-takeover-facts')
        require_common_no_takeover(observed, 'STARTING_OWNER_LOSS_ALLOWED_TAKEOVER')
        require_v2_starting_checkpoint(fact, older_marker, await owner_checkpoint())
        others_before = await assert_owner_internal_boundary(None, [jid], root, 'internal-before')
        assert await public_job_vector() == vector_before, 'EARLY_TAKEOVER_MUTATED_BUSINESS_OR_OWNER_ROW'
        await premature.stop(); premature = None
        dead = await finish_controlled_probe(process, root); process = None
        private_json(root / 'startup-loss-facts.json', {'earlier_closed_generation':older_marker['generation'],
            'starting_marker':fact['marker'], 'successor_blocked_while_old_alive':not observed['start_succeeded'],
            'settled':json.loads((root/'settled.json').read_text()), 'checkpoint':await owner_checkpoint()})
        settled = json.loads((root/'settled.json').read_text())
        assert settled['status'] == 'pending' and settled['attempts'] == 0, 'LOST_STARTER_WROTE_TASK_STATE'
        assert settled['exception_code'] == 'JOB_QUEUE_OWNER_LOST', 'LOST_STARTER_FAILURE_NOT_OWNER_LOSS'
        proof = root / 'exit-proof.json'; private_json(proof, dead, input_file=True)
        monkeypatch.setenv('JOB_QUEUE_RECOVERY_PROOF_FILE', str(proof))
        successor = LocalJobQueue(1); await successor.start(); await asyncio.wait_for(successor.queue.join(), 10)
        row = (await rows([jid]))[0]
        assert row.status == 'completed' and row.attempts == 1 and row.payload == identity
        marker = json.loads(successor._receipt_path().read_text())
        assert marker['generation'] == successor._generation != fact['marker']['generation']
        assert (await owner_checkpoint()) == marker
        assert await assert_owner_internal_boundary(successor, [jid], root, 'internal-after', expected_found=1) == others_before, 'OTHER_BUSINESS_ROW_OVERWRITTEN'
        await successor.stop()
        stable = await owner_checkpoint(); old_root = os.environ['EXPORT_DIR']
        fixed_path = successor._receipt_path()
        monkeypatch.setenv('EXPORT_DIR', str(tmp_path/'missing-state-path'))
        assert successor._receipt_path() == fixed_path, 'STATE_ROOT_CHANGED_WITHIN_INSTANCE'
        with pytest.raises(JobRecoveryRequired, match='JOB_RECOVERY_STATE_PATH_MISMATCH'):
            await LocalJobQueue(1).start()
        assert await owner_checkpoint() == stable, 'PATH_SWITCH_MUTATED_GENERATION'
        monkeypatch.setenv('EXPORT_DIR', old_root)
    finally:
        await close_combination_resources(process, root, premature, successor, [jid], identity, sys.exc_info()[1])


@pytest.mark.asyncio
async def test_durable_close_defers_and_then_recovers(tmp_path, monkeypatch, ensure_reporting_user_password):
    identity = await export_world(tmp_path, monkeypatch); queue = LocalJobQueue(1); next_queue = None; ids = []
    try:
        await queue.start(); await queue.semaphore.acquire()
        jid = await queue.enqueue('export_report', identity); ids.append(jid)
        queue.drain_seconds = 0.01
        await queue.stop()
        assert queue.close_report['pending'] == queue.close_report['deferred'] == 1
        assert queue.state.value == 'CLOSED' and not queue.workers
        monkeypatch.setenv('JOB_QUEUE_RECOVERY_CONFIRMED', '1')
        monkeypatch.delenv('JOB_QUEUE_RECOVERY_PROOF_FILE', raising=False)
        next_queue = LocalJobQueue(1); await next_queue.start(); await asyncio.wait_for(next_queue.queue.join(), 10)
        assert (await rows(ids))[0].status == 'completed'
    finally:
        await queue.stop()
        if next_queue is not None: await next_queue.stop()
        await remove(ids); await drop_world(identity)


@pytest.mark.asyncio
async def test_incomplete_retains_owner_until_actual_file_thread_closes(tmp_path, monkeypatch, ensure_reporting_user_password):
    from core.jobs.base import JobQueueShutdownIncomplete, JobQueueNotAccepting
    from jobs import export_jobs
    identity = await export_world(tmp_path, monkeypatch); entered = threading.Event(); release = threading.Event()
    original = export_jobs._ExportFileWork.append
    def blocked(work, batch):
        entered.set(); release.wait(10); return original(work, batch)
    monkeypatch.setattr(export_jobs._ExportFileWork, 'append', blocked)
    queue = LocalJobQueue(1); ids = []
    try:
        await queue.start(); ids.append(await queue.enqueue('export_report', identity))
        await until(entered.is_set)
        queue.drain_seconds = 0.01; queue.close_seconds = 0.03
        with pytest.raises(JobQueueShutdownIncomplete): await queue.stop()
        assert queue.state.value == 'INCOMPLETE' and queue._owner_connection is not None
        assert export_jobs.export_io_pending(queue._io_keys()), 'FILE_THREAD_MUST_REMAIN_OWNED'
        with pytest.raises(JobQueueNotAccepting, match='JOB_QUEUE_OWNER_BUSY'): await LocalJobQueue(1).start()
        release.set(); queue.close_seconds = 5; await queue.stop()
        assert queue.state.value == 'CLOSED' and not export_jobs.export_io_pending(queue._io_keys())
        assert queue.close_report['deferred'] == 1
        assert not list(export_jobs.EXPORT_DIR.glob('*.part.*'))
    finally:
        release.set(); queue.close_seconds = 5; await queue.stop(); await remove(ids); await drop_world(identity)


@pytest.mark.asyncio
async def test_state_write_error_still_balances_task_done(monkeypatch):
    queue = LocalJobQueue(1); await queue.start(); original = queue._write_job; ids = []
    @job_handler('a2_db_failure')
    async def handler(data): raise AssertionError('HANDLER_MUST_NOT_RUN_AFTER_STATE_WRITE_FAILURE')
    async def broken(jid, **values):
        async with AsyncSessionLocal() as db:
            await db.execute(text('SELECT 1/0'))
    try:
        monkeypatch.setattr(queue, '_write_job', broken)
        ids.append(await queue.enqueue('a2_db_failure', {}))
        await asyncio.wait_for(queue.queue.join(), 3)
        assert queue.state.value == 'INCOMPLETE' and ids[0] in queue._db_uncertain
        assert (await rows(ids))[0].attempts == 0
        monkeypatch.setattr(queue, '_write_job', original)
        await queue.stop()
        assert queue.close_report['pending'] == 1 and queue.close_report['completed'] == 0
    finally:
        monkeypatch.setattr(queue, '_write_job', original); await queue.stop(); await remove(ids)


async def _owner_isolation_snapshot():
    """Read the real task scope; a pool dispose is not an Owner cleanup."""
    from core.jobs.local_queue import OWNER_KEYS, OWNER_ROW_ID, _strict_reboot_json

    directory = Path(os.environ['EXPORT_DIR'])
    info = directory.lstat()
    assert directory.is_absolute() and not directory.is_symlink(), 'OWNER_ISOLATION_EXPORT_PATH'
    assert stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077, 'OWNER_ISOLATION_EXPORT_PERMISSIONS'
    vector = await public_job_vector()
    owner = vector.pop(str(OWNER_ROW_ID), None)
    marker_path = directory / '.queue-owner.json'
    assert not marker_path.is_symlink(), 'OWNER_ISOLATION_MARKER_SYMLINK'
    marker = _strict_reboot_json(marker_path.read_bytes()) if marker_path.exists() else None
    journal = directory / '.queue-reboot-handoff.json'
    assert not journal.is_symlink(), 'OWNER_ISOLATION_JOURNAL_SYMLINK'
    if journal.exists():
        assert _strict_reboot_json(journal.read_bytes())['phase'] == 'COMPLETE', 'OWNER_ISOLATION_HANDOFF_INCOMPLETE'
    artifacts = {}
    for path in directory.iterdir():
        assert not path.is_symlink() and path.is_file(), 'OWNER_ISOLATION_UNEXPECTED_ARTIFACT_TYPE'
        if not path.name.startswith('.queue-'):
            with path.open('rb') as handle:
                artifacts[path.name] = hashlib.file_digest(handle, 'sha256').hexdigest()
    assert owner is None or isinstance(owner['payload'], dict), 'OWNER_ISOLATION_OWNER_PAYLOAD'
    backend = owner['payload'].get('owner_backend') if owner else None
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        name, role, oid = (await db.execute(text(
            'SELECT current_database(), current_user, oid FROM pg_database WHERE datname=current_database()'
        ))).one()
        locks = (await db.execute(text(
            "SELECT pid FROM pg_locks WHERE locktype='advisory' AND classid=:a AND objid=:b "
            'AND objsubid=2 AND granted AND database=:oid ORDER BY pid'
        ), dict(a=OWNER_KEYS[0], b=OWNER_KEYS[1], oid=oid))).scalars().all()
        present = (await db.execute(text(
            'SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datid=:oid AND pid=:pid)'
        ), dict(oid=oid, pid=backend))).scalar_one()
    return dict(owner=owner, marker=marker, ordinary=vector, artifacts=artifacts,
        state_path=str(marker_path.resolve()), owner_backend_present=present,
        lock_backends=list(locks), database=dict(name=name, role=role, oid=oid,
            identity=process_fact()['database']))


def _require_owner_isolation_precondition(observed):
    assert observed['database']['role'] == 'mpango_app', 'OWNER_ISOLATION_RUNTIME_ROLE'
    assert re.fullmatch(r'(?:test|pytest|ci)[_-][a-z0-9_-]+', observed['database']['name']), 'OWNER_ISOLATION_TEST_DATABASE'
    assert not observed['lock_backends'] and observed['owner_backend_present'] is False, 'OWNER_ISOLATION_PREDECESSOR_BUSY'
    assert not any(row['status'] not in ('completed', 'failed') and not row['is_deleted']
        for row in observed['ordinary'].values()), 'OWNER_ISOLATION_ORDINARY_BACKLOG'
    if observed['owner'] is None:
        assert observed['marker'] is None and not observed['ordinary'], 'OWNER_ISOLATION_NOT_FRESH'
    else:
        row = observed['owner']; fact = row['payload']
        assert row['job_name'] == '__local_queue_owner_v2__' and row['status'] == 'completed' and not row['is_deleted'], 'OWNER_ISOLATION_OWNER_ROW'
        parent = process_fact()
        assert fact.get('version') == 2 and all(fact[key] == parent[key]
            for key in ('host', 'boot', 'database')), 'OWNER_ISOLATION_PREDECESSOR_SCOPE'
        assert observed['marker'] == fact and fact['state_path'] == observed['state_path'], 'OWNER_ISOLATION_PREDECESSOR_MAPPING'
        assert fact['closed'] is True and fact['state'] == 'CLOSED' and all(
            type(fact[key]) is int and fact[key] == 0
            for key in ('active_handlers', 'active_io', 'active_admissions')
        ), 'OWNER_ISOLATION_PREDECESSOR_NOT_CLOSED'
        assert fact['database'] == observed['database']['identity'], 'OWNER_ISOLATION_DATABASE_MISMATCH'


async def _exercise_owner_loss_refusal():
    """The original fault body, executed once by the explicit probe child."""
    before = await _owner_isolation_snapshot()
    _require_owner_isolation_precondition(before)
    from core.jobs.base import JobQueueNotAccepting, JobQueueShutdownIncomplete
    queue = LocalJobQueue(1); await queue.start()
    claimed = await _owner_isolation_snapshot()
    with pytest.raises(JobQueueNotAccepting, match='JOB_QUEUE_OWNER_BUSY'): await LocalJobQueue(1).start()
    async with queue._owner_query_lock:
        await queue._owner_connection.execute(text('SELECT pg_advisory_unlock(742019,5106)'))
    with pytest.raises(JobQueueNotAccepting): await queue.enqueue('export_report', {})
    with pytest.raises(JobQueueShutdownIncomplete): await queue.stop()
    assert queue._owner_connection is None and all(t.done() for t in queue.workers)
    after = await _owner_isolation_snapshot()
    assert queue.state.value == 'INCOMPLETE', 'OWNER_ISOLATION_FAULT_STATE'
    assert after['owner'] == claimed['owner'] and after['marker'] == claimed['marker'], 'OWNER_ISOLATION_FAULT_RECEIPT_REWRITTEN'
    assert after['ordinary'] == before['ordinary'] and after['artifacts'] == before['artifacts'], 'OWNER_ISOLATION_FAULT_BUSINESS_DRIFT'
    return dict(before=before, claimed=claimed, open_owner=after,
        fault_state=queue.state.value, owner_connection_released=True,
        workers_done=True, busy_assertion_passed=True,
        enqueue_refusal_assertion_passed=True, incomplete_stop_assertion_passed=True)


async def _recover_exited_owner_and_close(fact, root, before, monkeypatch, evidence):
    """Only a proven exited child can precede the real recovery/close APIs."""
    from core.jobs.base import JobRecoveryRequired
    from core.jobs.local_queue import _strict_reboot_json

    root = Path(root)
    declared_probe_root = Path(os.environ['ASYNC_QUEUE_PROBE_ROOT'])
    assert declared_probe_root.is_absolute() and not declared_probe_root.is_symlink(), 'OWNER_ISOLATION_PROBE_SCOPE'
    probe_root = declared_probe_root.resolve()
    assert root.is_absolute() and not root.is_symlink() and root.parent.resolve() == probe_root, 'OWNER_ISOLATION_PROBE_SCOPE'
    info = root.lstat()
    assert stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077, 'OWNER_ISOLATION_PROBE_PERMISSIONS'
    def read(name):
        path = root / name
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and not info.st_mode & 0o077, 'OWNER_ISOLATION_NATIVE_FILE'
        return _strict_reboot_json(path.read_bytes())
    plan = read('plan.json'); record = read('record.json'); controller = read('capture-result.json')
    intent = read('intent.json'); process = read('intent.process.json')
    plan_bytes = (root / 'plan.json').read_bytes()
    assert len(plan['commands']) == 1, 'OWNER_ISOLATION_NATIVE_PLAN'
    call = plan['commands'][0]
    backend = str(Path(__file__).resolve().parents[1])
    expected_argv = [sys.executable, '-B', '-m', 'tests.async_export_process_probe',
        'owner-loss-refusal', str(root / 'input.json'), str(root / 'facts.json')]
    assert call['id'] == 'probe' and call['argv'] == expected_argv and call['cwd'] == backend, 'OWNER_ISOLATION_NATIVE_COMMAND'
    assert call['native_timeout_seconds'] == 40 and call['invocation_id'] == 'A2-probe:' + root.name, 'OWNER_ISOLATION_NATIVE_PLAN'
    assert all(call[key + '_path'] == str(root / (key + suffix)) for key, suffix in
        [('stdout', '.txt'), ('stderr', '.txt'), ('intent', '.json'), ('record', '.json')]), 'OWNER_ISOLATION_NATIVE_PATHS'
    assert record['plan_sha256'] == hashlib.sha256(plan_bytes).hexdigest(), 'OWNER_ISOLATION_PLAN_DIGEST'
    assert all(record[key] == call[key] for key in ('id', 'argv', 'cwd', 'invocation_id')), 'OWNER_ISOLATION_NATIVE_BINDING'
    assert all(intent[key] == record[key] for key in
        ('id', 'plan_sha256', 'argv', 'cwd', 'env_key_names', 'invocation_id', 'timeout_seconds', 'started_at')) and intent.get('metadata_errors') == [], 'OWNER_ISOLATION_INTENT_BINDING'
    assert type(record.get('native_rc')) is int and record['native_rc'] == 0 and record.get('timed_out') is False and record.get('metadata_errors') == [], 'OWNER_ISOLATION_NATIVE_FAILED'
    assert record['timeout_seconds'] == 40 and type(controller.get('rc')) is int and controller['rc'] == 0, 'OWNER_ISOLATION_CONTROLLER_FAILED'
    assert all(type(record.get(key)) is int and record[key] > 0 for key in ('pid', 'pgid', 'start_ticks')), 'OWNER_ISOLATION_NATIVE_IDENTITY'
    assert all(process[key] == record[key] for key in
        ('id', 'pid', 'pgid', 'start_ticks', 'started_at')) and process.get('metadata_errors') == [], 'OWNER_ISOLATION_PROCESS_BINDING'
    assert type(controller.get('pid')) is int and controller['pid'] > 0 and controller['pid'] != os.getpid(), 'OWNER_ISOLATION_CONTROLLER_IDENTITY'
    assert record['pid'] == record['pgid'] and record['pid'] not in (os.getpid(), controller['pid']), 'OWNER_ISOLATION_CHILD_IDENTITY'
    for kind in ('stdout', 'stderr'):
        path = root / (kind + '.txt')
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and not info.st_mode & 0o077, 'OWNER_ISOLATION_NATIVE_FILE'
        output = record['outputs'][kind]; raw = path.read_bytes()
        assert output == dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()), 'OWNER_ISOLATION_OUTPUT_BINDING'
    assert fact == read('facts.json') and fact['mode'] == 'owner-loss-refusal', 'OWNER_ISOLATION_FACT_BINDING'
    assert fact['pid'] == record['pid'] and fact['start_ticks'] == record['start_ticks'] and type(fact.get('version')) is int and fact['version'] == 1, 'OWNER_ISOLATION_FACT_IDENTITY'
    parent = process_fact()
    assert all(fact[key] == parent[key] for key in ('host', 'boot', 'database')), 'OWNER_ISOLATION_PROCESS_SCOPE'
    try:
        alive = LocalJobQueue._ticks(fact['pid']) == fact['start_ticks']
    except FileNotFoundError:
        alive = False
    assert not alive, 'OWNER_ISOLATION_CHILD_STILL_ALIVE'
    assert all(fact['before'][key] == before[key] for key in
        ('owner', 'marker', 'ordinary', 'artifacts', 'state_path', 'database')), 'OWNER_ISOLATION_PRESTATE_DRIFT'
    async def quiet_snapshot(expected, label):
        # Only catalog absence is polled. Persisted identity/business changes
        # fail immediately; no business API is retried or state repaired.
        last = None
        async def observe():
            nonlocal last
            while True:
                last = await _owner_isolation_snapshot()
                assert all(last[key] == expected[key] for key in
                    ('owner', 'marker', 'ordinary', 'artifacts', 'state_path', 'database')), 'OWNER_ISOLATION_CHILD_OBSERVATION_DRIFT'
                if not last['lock_backends'] and last['owner_backend_present'] is False:
                    return last
                await asyncio.sleep(0.005)
        try:
            return await asyncio.wait_for(observe(), 5)
        except asyncio.TimeoutError:
            primary = AssertionError(label)
            try:
                private_json(evidence / (label + '.json'), last)
            except BaseException as secondary:
                primary.add_note('OWNER_ISOLATION_SECONDARY_RECORD:' + type(secondary).__name__)
            raise primary from None
    observed = await quiet_snapshot(fact['open_owner'], 'OWNER_ISOLATION_OWNER_BACKEND_PRESENT')
    owner = observed['owner']['payload']
    assert observed['owner']['job_name'] == '__local_queue_owner_v2__' and observed['owner']['status'] == 'completed' and not observed['owner']['is_deleted'], 'OWNER_ISOLATION_OWNER_ROW'
    assert observed['marker'] == owner and owner['version'] == 2 and owner['closed'] is False, 'OWNER_ISOLATION_OPEN_OWNER'
    assert all(owner[key] == fact[key] for key in ('host', 'boot', 'database', 'pid', 'start_ticks')), 'OWNER_ISOLATION_OWNER_IDENTITY'
    assert owner['state_path'] == observed['state_path'] and re.fullmatch(r'[0-9a-f]{32}', owner['generation']), 'OWNER_ISOLATION_OWNER_MAPPING'
    assert type(owner['owner_backend']) is int and owner['owner_backend'] > 0, 'OWNER_ISOLATION_OWNER_BACKEND'
    assert not observed['lock_backends'] and observed['owner_backend_present'] is False, 'OWNER_ISOLATION_OWNER_BACKEND_PRESENT'
    assert fact['fault_state'] == 'INCOMPLETE' and all(fact[key] is True for key in
        ('owner_connection_released', 'workers_done', 'busy_assertion_passed',
         'enqueue_refusal_assertion_passed', 'incomplete_stop_assertion_passed')), 'OWNER_ISOLATION_FAULT_ORACLE'
    assert observed['ordinary'] == before['ordinary'] and observed['artifacts'] == before['artifacts'], 'OWNER_ISOLATION_BUSINESS_DRIFT'
    assert not any(row['status'] not in ('completed', 'failed') and not row['is_deleted']
        for row in observed['ordinary'].values()), 'OWNER_ISOLATION_ORDINARY_BACKLOG'
    private_json(evidence / 'child-open-observed.json', observed)
    proof_keys = ('version', 'host', 'boot', 'database', 'pid', 'start_ticks')
    wrong = root / 'negative-mismatched-owner-proof.json'
    private_json(wrong, {key: parent[key] for key in proof_keys}, input_file=True)
    with monkeypatch.context() as scope:
        scope.setenv('JOB_QUEUE_RECOVERY_CONFIRMED', '1')
        scope.setenv('JOB_QUEUE_RECOVERY_PROOF_FILE', str(wrong))
        with pytest.raises(JobRecoveryRequired, match='JOB_RECOVERY_OWNER_EXIT_UNPROVEN'):
            await LocalJobQueue(1).start()
    assert await quiet_snapshot(observed, 'OWNER_ISOLATION_MISMATCH_BACKEND_PRESENT') == observed, 'OWNER_ISOLATION_MISMATCH_MUTATED_STATE'
    # Identity mismatch is rejected before the live-owner check. It is not
    # evidence that the matching-live-Owner branch was exercised.
    private_json(evidence / 'mismatched-owner-proof.json', dict(
        result='MISMATCHED_OWNER_PROOF_REJECTED',
        proof_identity_matches_owner=all(parent[key] == owner[key] for key in
            ('host', 'boot', 'database', 'pid', 'start_ticks')),
        matching_live_owner_branch='NOT_VERIFIED'))
    proof = root / 'exited-child-proof.json'
    private_json(proof, {key: fact[key] for key in proof_keys}, input_file=True)
    queue = LocalJobQueue(1)
    started = stop_attempted = False
    try:
        with monkeypatch.context() as scope:
            scope.setenv('JOB_QUEUE_RECOVERY_CONFIRMED', '1')
            scope.setenv('JOB_QUEUE_RECOVERY_PROOF_FILE', str(proof))
            await queue.start()
            started = True
            assert queue.recovery['found'] == queue.recovery['replayed'] == 0 and not queue.jobs, 'OWNER_ISOLATION_RECOVERY_TOUCHED_BACKLOG'
            stop_attempted = True
            await queue.stop()
        closed = await _owner_isolation_snapshot()
        private_json(evidence / 'parent-close-observed.json', closed)
        closed = await quiet_snapshot(closed, 'OWNER_ISOLATION_CLOSED_BACKEND_PRESENT')
        _require_owner_isolation_precondition(closed)
        current = closed['owner']['payload']
        assert current['generation'] != owner['generation'] and all(
            current[key] == parent[key] for key in ('host', 'boot', 'database', 'pid', 'start_ticks')
        ), 'OWNER_ISOLATION_CLOSED_GENERATION'
        assert closed['ordinary'] == before['ordinary'] and closed['artifacts'] == before['artifacts'], 'OWNER_ISOLATION_RECOVERY_BUSINESS_DRIFT'
        assert queue.state.value == 'CLOSED' and queue._owner_connection is None and all(task.done() for task in queue.workers), 'OWNER_ISOLATION_CLOSE_NOT_COMPLETE'
        private_json(evidence / 'parent-close-verified.json', closed)
    except BaseException as primary:
        if started and not stop_attempted:
            try:
                await queue.stop()
            except BaseException as secondary:
                primary.add_note('OWNER_ISOLATION_SECONDARY_CLOSE:' + type(secondary).__name__)
        raise


@pytest.mark.asyncio
async def test_second_owner_and_lost_lock_refuse_acceptance(monkeypatch):
    """Preserve the fault oracle; recover only after its real child exited."""
    evidence = Path(os.environ['ASYNC_QUEUE_PROBE_ROOT']) / ('owner-loss-parent-' + uuid4().hex)
    evidence.mkdir(mode=0o700)
    phase = 'precondition'
    try:
        before = await _owner_isolation_snapshot()
        _require_owner_isolation_precondition(before)
        private_json(evidence / 'parent-before.json', before)
        phase = 'child-launch'
        fact, root = await launch_probe('owner-loss-refusal', {})
        private_json(evidence / 'child-binding.json', dict(root=str(root), pid=fact['pid'], start_ticks=fact['start_ticks']))
        phase = 'exit-proof-and-recovery'
        await _recover_exited_owner_and_close(fact, root, before, monkeypatch, evidence)
    except BaseException as primary:
        try:
            private_json(evidence / 'parent-result.json', dict(success=False, phase=phase,
                exception_class=type(primary).__name__, exception_code=getattr(primary, 'code', None)))
        except BaseException as secondary:
            primary.add_note('OWNER_ISOLATION_SECONDARY_RECORD:' + type(secondary).__name__)
        raise
    private_json(evidence / 'parent-result.json', dict(success=True, phase='closed',
        matching_live_owner_branch='NOT_VERIFIED'))


@pytest.mark.asyncio
async def test_shutdown_is_single_task_and_engines_follow_queue(monkeypatch):
    import main
    from core.jobs.base import JobQueueShutdownIncomplete
    order = []; entered = asyncio.Event(); release = asyncio.Event()
    old = (main._job_queue, main._shutdown_task, main._shutdown_loop, main._shutdown_event)
    async def stop(): entered.set(); await release.wait(); order.append('queue')
    async def mark(name): order.append(name)
    async def transaction(): await mark('transaction')
    async def reporting(): await mark('reporting')
    async def limiter(): await mark('limiter')
    async def cache(): await mark('cache')
    try:
        main._shutdown_task = main._shutdown_loop = None
        main._job_queue = type('Queue', (), {'stop': staticmethod(AsyncMock(side_effect=stop))})()
        with patch('database.session.async_engine', SimpleNamespace(dispose=AsyncMock(side_effect=transaction))), \
             patch('database.reporting_session.reporting_engine', SimpleNamespace(dispose=AsyncMock(side_effect=reporting))), \
             patch('core.rate_limiter.close_rate_limiter', AsyncMock(side_effect=limiter)), \
             patch('core.cache.close_redis_client', AsyncMock(side_effect=cache)):
            tasks = [asyncio.create_task(main.graceful_shutdown()) for _ in range(2)]
            await asyncio.wait_for(entered.wait(), 2); assert order == []
            release.set(); await asyncio.gather(*tasks)
            await main.graceful_shutdown()
            assert main._job_queue.stop.await_count == 1
            assert order == ['queue', 'transaction', 'reporting', 'limiter', 'cache']
            thread_errors = []
            def other_loop():
                try:
                    asyncio.run(main.graceful_shutdown())
                except BaseException as error:
                    thread_errors.append(type(error).__name__)
            thread = threading.Thread(target=other_loop)
            thread.start()
            await until(lambda: not thread.is_alive())
            thread.join()
            assert thread_errors == [] and main._shutdown_task.get_loop().is_closed()
            await main.graceful_shutdown()
            assert main._job_queue.stop.await_count == 3
            assert order == ['queue', 'transaction', 'reporting', 'limiter', 'cache'] * 3
            main._job_queue.start = AsyncMock()
            with patch('core.jobs.LocalJobQueue', return_value=main._job_queue), \
                 patch('core.governance.registry.register_resolver'), patch('signal.signal') as signals:
                from fastapi import FastAPI
                with pytest.raises(RuntimeError, match='LIFESPAN_BODY_CONTROL'):
                    async with main.lifespan(FastAPI()):
                        raise RuntimeError('LIFESPAN_BODY_CONTROL')
                assert main._job_queue.start.await_count == 1
                assert main._job_queue.stop.await_count == 4
                assert order == ['queue', 'transaction', 'reporting', 'limiter', 'cache'] * 4
                signals.assert_not_called()
            main._shutdown_task = main._shutdown_loop = None
            main._job_queue.stop.side_effect = JobQueueShutdownIncomplete()
            order.clear()
            with pytest.raises(JobQueueShutdownIncomplete): await main.graceful_shutdown()
            with pytest.raises(JobQueueShutdownIncomplete): await main.graceful_shutdown()
            assert order == [] and main._job_queue.stop.await_count == 5
    finally:
        release.set()
        main._job_queue, main._shutdown_task, main._shutdown_loop, main._shutdown_event = old
