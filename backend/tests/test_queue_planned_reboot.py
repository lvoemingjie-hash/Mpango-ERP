"""Planned reboot controls using real queue/PG, with only boot/asset observation simulated."""
import asyncio
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from uuid import UUID, uuid4

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select, text

import core.jobs.local_queue as local
from core.jobs.base import JobRecoveryRequired
from database.session import AsyncSessionLocal
from models.job import Job


async def _owner():
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        row = (await db.execute(select(Job).where(Job.id == local.OWNER_ROW_ID))).scalar_one()
        return dict(row.payload)


async def _business(job_id):
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        row = (await db.execute(select(Job).where(Job.id == UUID(str(job_id))))).scalar_one()
        return row.to_dict()


def _boot_override(value):
    original = Path.read_text
    def read(path, *args, **kwargs):
        if str(path) == '/proc/sys/kernel/random/boot_id':
            return value() + '\n'
        return original(path, *args, **kwargs)
    return read


async def _child(mode, tmp_path, boot, *, extra=None):
    root = tmp_path / ('child-' + uuid4().hex)
    root.mkdir(mode=0o700)
    env = json.loads(Path(os.environ['ASYNC_QUEUE_RUNTIME_ENV']).read_text())
    env.update(EXPORT_DIR=os.environ['EXPORT_DIR'], A2_CHILD_BOOT=boot)
    env.pop('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE', None)
    env.pop('JOB_QUEUE_RECOVERY_PROOF_FILE', None)
    env.pop('JOB_QUEUE_RECOVERY_CONFIRMED', None)
    env.update(extra or {})
    envfile = root / 'environment.json'
    envfile.write_text(json.dumps(env)); envfile.chmod(0o600)
    command = {'id':'child', 'invocation_id':'planned-reboot-child-' + uuid4().hex,
        'argv':[sys.executable, '-B', str(Path(__file__).resolve()), '--child', mode],
        'cwd':str(Path(__file__).resolve().parents[1]), 'native_timeout_seconds':45}
    for key in ('stdout','stderr','intent','record'):
        command[key+'_path'] = str(root/key)
    plan = root/'plan.json'; plan.write_text(json.dumps({'commands':[command]}))
    process = await asyncio.create_subprocess_exec(sys.executable, '-B', os.environ['ASYNC_QUEUE_NATIVE_CAPTURE'],
        str(plan), 'child', str(envfile), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={k:os.environ[k] for k in ('PATH','HOME','LANG','USER','LOGNAME') if k in os.environ})
    stdout, stderr = await asyncio.wait_for(process.communicate(), 75)
    record = json.loads((root/'record').read_text())
    assert process.returncode == 0 and record['native_rc'] == 0 and not record['timed_out'] and not record['metadata_errors'], (stdout, stderr, (root/'stderr').read_text())
    assert record['pid'] > 0 and record['pgid'] == record['pid'] and record['start_ticks'] > 0
    payload = [line for line in (root/'stdout').read_text().splitlines() if line.startswith('A2_CHILD_RESULT=')]
    assert len(payload) == 1
    return json.loads(payload[0].split('=',1)[1]), record


async def _child_main(mode):
    Path.read_text = _boot_override(lambda: os.environ['A2_CHILD_BOOT'])
    queue = local.LocalJobQueue(1)
    if mode == 'old-closed':
        await queue.start()
        await queue.stop()
        print('A2_CHILD_RESULT='+json.dumps({'code':'CLOSED'}))
    elif mode == 'interrupted':
        authority = json.loads(Path(os.environ['A2_CHILD_AUTHORITY']).read_text())
        local._observe_reboot_authority = lambda: authority
        async def fail_after_both_starting():
            raise RuntimeError('INJECTED_HANDOFF_AFTER_STARTING')
        queue._recover = fail_after_both_starting
        try:
            await queue.start()
        except RuntimeError as error:
            assert str(error) == 'INJECTED_HANDOFF_AFTER_STARTING'
            print('A2_CHILD_RESULT='+json.dumps({'code':'INJECTED_HANDOFF_AFTER_STARTING','workers':len(queue.workers)}))
        else:
            raise AssertionError('HANDOFF_FAULT_DID_NOT_FIRE')
    elif mode == 'retry-old-proof':
        try:
            await queue.start()
        except JobRecoveryRequired as error:
            print('A2_CHILD_RESULT='+json.dumps({'code':error.code,'workers':len(queue.workers)}))
        else:
            raise AssertionError('INCOMPLETE_HANDOFF_WAS_ADMITTED')
    else:
        raise ValueError('unknown child mode')


@pytest.fixture
def physical_identity(monkeypatch, tmp_path):
    actual = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    boot = {'value':actual}
    monkeypatch.setattr(Path, 'read_text', _boot_override(lambda: boot['value']))
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    current = {'authority':None}
    # Only infrastructure observation is substituted; signature and queue gates stay real.
    monkeypatch.setattr(local, '_observe_reboot_authority', lambda: current['authority'], raising=False)
    return {'actual':actual, 'boot':boot, 'key':key, 'public':public, 'current':current, 'tmp':tmp_path}


async def _permit(state, new_boot):
    old = await _owner()
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema'] = 'public'
        dbname, oid = (await db.execute(text('SELECT current_database(), oid FROM pg_database WHERE datname=current_database()'))).one()
    root = str(Path(os.environ['EXPORT_DIR']).resolve())
    authority = {'vm_id':'synthetic-vm','deployment_id':'synthetic-deployment',
        'pg_system_identifier':'synthetic-cluster','database_name':dbname,'database_oid':oid,
        'pg_storage_id':'synthetic-pg-volume','export_storage_id':'synthetic-export-volume',
        'export_root':root,'pg_data_root':root,'pg_container_id':'a'*64,
        'pg_image_id':'sha256:'+'b'*64,'pg_device':os.stat(root).st_dev,
        'export_device':os.stat(root).st_dev,'boot':new_boot,'signing_public_key':state['public'],
        'app_uid':os.getuid(),'issuer_uid':os.getuid()}
    payload = {'kind':'planned_clean_reboot_v1','old_owner_sha256':hashlib.sha256(
        json.dumps(old,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest(),
        'old_generation':old['generation'],'old_boot':old['boot'],'new_boot':new_boot,'authority':authority}
    encoded = json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    envelope = {'payload':payload,'signature':base64.b64encode(state['key'].sign(encoded)).decode()}
    proof = state['tmp']/('permit-'+uuid4().hex+'.json');proof.write_text(json.dumps(envelope));proof.chmod(0o600)
    return proof, authority


async def _advance_back_to_real_boot(state, monkeypatch):
    # A second actual queue handoff restores the test's physical-observation fixture;
    # no SQL/marker rewrite is used to repair test state.
    result, _ = await _child('old-closed', state['tmp'], state['boot']['value'])
    assert result['code'] == 'CLOSED'
    proof, authority = await _permit(state, state['actual'])
    state['boot']['value'] = state['actual'];state['current']['authority'] = authority
    monkeypatch.setenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE', str(proof))
    queue = local.LocalJobQueue(1)
    await queue.start(); await queue.stop()
    monkeypatch.delenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE', raising=False)


@pytest.mark.asyncio
async def test_clean_reboot_preserves_download_and_does_not_execute_twice(physical_identity, monkeypatch, tmp_path, ensure_reporting_user_password):
    from core.jobs import get_job_registry
    from tests.test_async_queue_lifecycle import export_world, drop_world, remove
    from tests.test_dc10e_export_worker_tenant_context import _request_with_context, _exports_create_token
    from api.v1.exports import download_export
    state=physical_identity; identity=await export_world(tmp_path, monkeypatch); queue=None; jobs=[]; advanced=False
    original_handler=get_job_registry()['export_report']
    try:
        initial=local.LocalJobQueue(1);await initial.start()
        job_id=await initial.enqueue('export_report',identity);jobs=[job_id]
        await asyncio.wait_for(initial.queue.join(),20);await initial.stop()
        before=await _business(job_id);assert before['status']=='completed'
        file=Path(os.environ['EXPORT_DIR'])/(identity['file_id']+'.csv');body=file.read_bytes();digest=hashlib.sha256(body).hexdigest()
        result, _ = await _child('old-closed',tmp_path,state['actual']);assert result['code']=='CLOSED'
        new_boot='simulated-'+uuid4().hex;proof,authority=await _permit(state,new_boot)
        state['boot']['value']=new_boot;state['current']['authority']=authority
        monkeypatch.setenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE',str(proof))
        async def forbidden(_):raise AssertionError('HANDLER_RERAN')
        monkeypatch.setitem(get_job_registry(),'export_report',forbidden)
        queue=local.LocalJobQueue(1);observed='ACCEPTED'
        try:await queue.start();advanced=True
        except JobRecoveryRequired as error:observed=error.code
        assert observed=='ACCEPTED', 'PLANNED_CLEAN_REBOOT_NOT_ADMITTED:'+observed
        await asyncio.wait_for(queue.queue.join(),10)
        assert await _business(job_id)==before and hashlib.sha256(file.read_bytes()).hexdigest()==digest
        request=_request_with_context(identity['tenant_id']);token=await _exports_create_token(request)
        response=await download_export(request,job_id,token);messages=[]
        async def receive():return {'type':'http.request','body':b'','more_body':False}
        async def send(message):messages.append(message)
        await response({'type':'http','method':'GET','headers':[],'asgi':{'spec_version':'2.4'}},receive,send)
        assert b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')==body
        foreign=_request_with_context(str(uuid4()));foreign_token=await _exports_create_token(foreign)
        denied=await download_export(foreign,job_id,foreign_token);assert denied.status_code==404
    finally:
        get_job_registry()['export_report']=original_handler
        if queue is not None and advanced:await queue.stop()
        monkeypatch.delenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE',raising=False)
        if advanced:await _advance_back_to_real_boot(state,monkeypatch)
        else:state['boot']['value']=state['actual']
        await remove(jobs);await drop_world(identity)


@pytest.mark.asyncio
async def test_late_unsettled_business_rejected_without_writes(physical_identity, monkeypatch, tmp_path, ensure_reporting_user_password):
    from tests.test_async_queue_lifecycle import export_world, drop_world, remove, seed
    state=physical_identity;identity=await export_world(tmp_path,monkeypatch);job_id=None;queue=None;admitted=False
    try:
        result,_=await _child('old-closed',tmp_path,state['actual']);assert result['code']=='CLOSED'
        new_boot='simulated-'+uuid4().hex;proof,authority=await _permit(state,new_boot)
        job_id=await seed(identity,status='pending')
        before=await _owner();marker=Path(os.environ['EXPORT_DIR'])/'.queue-owner.json';before_marker=marker.read_bytes()
        state['boot']['value']=new_boot;state['current']['authority']=authority
        monkeypatch.setenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE',str(proof))
        monkeypatch.setenv('JOB_QUEUE_RECOVERY_CONFIRMED','1')
        queue=local.LocalJobQueue(1);observed='ACCEPTED'
        try:await queue.start();admitted=True
        except JobRecoveryRequired as error:observed=error.code
        assert observed=='JOB_RECOVERY_REBOOT_UNSETTLED', 'REBOOT_ADMITTED_WITH_UNSETTLED_BUSINESS:'+observed
        assert await _owner()==before and marker.read_bytes()==before_marker
    finally:
        if admitted:
            await queue.stop()
            await _advance_back_to_real_boot(state,monkeypatch)
        else:state['boot']['value']=state['actual']
        monkeypatch.delenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE',raising=False)
        monkeypatch.delenv('JOB_QUEUE_RECOVERY_CONFIRMED',raising=False)
        if job_id:await remove([job_id])
        await drop_world(identity)


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['vm_id','pg_system_identifier','pg_storage_id','export_storage_id'])
async def test_wrong_bound_identity_refused_without_writes(field, physical_identity, monkeypatch, tmp_path):
    state=physical_identity;result,_=await _child('old-closed',tmp_path,state['actual']);assert result['code']=='CLOSED'
    new_boot='simulated-'+uuid4().hex;proof,authority=await _permit(state,new_boot)
    before=await _owner();marker=Path(os.environ['EXPORT_DIR'])/'.queue-owner.json';before_marker=marker.read_bytes()
    state['boot']['value']=new_boot;state['current']['authority']=dict(authority,**{field:'different'})
    monkeypatch.setenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE',str(proof))
    try:
        with pytest.raises(JobRecoveryRequired,match='JOB_RECOVERY_REBOOT_PROOF_INVALID'):
            await local.LocalJobQueue(1).start()
        assert await _owner()==before and marker.read_bytes()==before_marker
    finally:state['boot']['value']=state['actual']


@pytest.mark.asyncio
async def test_same_boot_replayed_permit_is_refused(physical_identity, monkeypatch, tmp_path):
    state=physical_identity;result,_=await _child('old-closed',tmp_path,state['actual']);assert result['code']=='CLOSED'
    proof,_=await _permit(state,'simulated-'+uuid4().hex)
    before=await _owner();marker=Path(os.environ['EXPORT_DIR'])/'.queue-owner.json';raw=marker.read_bytes()
    monkeypatch.setenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE',str(proof))
    with pytest.raises(JobRecoveryRequired,match='JOB_RECOVERY_REBOOT_PROOF_STALE'):
        await local.LocalJobQueue(1).start()
    assert await _owner()==before and marker.read_bytes()==raw


@pytest.mark.asyncio
async def test_symlink_permit_is_refused(physical_identity, monkeypatch, tmp_path):
    state=physical_identity;result,_=await _child('old-closed',tmp_path,state['actual']);assert result['code']=='CLOSED'
    boot='simulated-'+uuid4().hex;proof,authority=await _permit(state,boot);link=tmp_path/'link.json';link.symlink_to(proof)
    before=await _owner();marker=Path(os.environ['EXPORT_DIR'])/'.queue-owner.json';raw=marker.read_bytes()
    state['boot']['value']=boot;state['current']['authority']=authority;monkeypatch.setenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE',str(link))
    try:
        with pytest.raises(JobRecoveryRequired,match='JOB_RECOVERY_REBOOT_PROOF_INVALID'):
            await local.LocalJobQueue(1).start()
        assert await _owner()==before and marker.read_bytes()==raw
    finally:state['boot']['value']=state['actual']


def test_offline_signed_input_and_journal_file_controls(physical_identity, tmp_path):
    state=physical_identity;payload={'kind':'fixture'}
    encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    envelope={'payload':payload,'signature':base64.b64encode(state['key'].sign(encoded)).decode()}
    authority={'signing_public_key':state['public']}
    proof=tmp_path/'proof.json';proof.write_text(json.dumps(envelope));proof.chmod(0o600)
    actual,_=local._verify_signed_reboot_permit(proof,authority);assert actual==payload
    envelope['payload']['kind']='modified';proof.write_text(json.dumps(envelope))
    with pytest.raises(InvalidSignature):local._verify_signed_reboot_permit(proof,authority)
    with pytest.raises(ValueError):local._strict_reboot_json(b'{"phase":1,"phase":2}')
    link=tmp_path/'proof-link';link.symlink_to(proof)
    with pytest.raises((ValueError,OSError)):local._read_protected_reboot_file(link,os.getuid(),private=True)
    queue=local.LocalJobQueue(1);queue._owner_state_root=tmp_path
    queue._planned_reboot_handoff={'phase':'INCOMPLETE','old_generation':'fixture'}
    queue._write_reboot_journal('INCOMPLETE',None,threading.Event())
    assert queue._read_reboot_journal()['phase']=='INCOMPLETE'
    with pytest.raises(JobRecoveryRequired,match='JOB_RECOVERY_HANDOFF_INCOMPLETE'):
        queue._check_reboot_handoff({'state':'STARTING','planned_reboot_handoff':queue._planned_reboot_handoff})


@pytest.mark.asyncio
async def test_active_file_io_does_not_release_owner_on_incomplete_handoff():
    from jobs.export_jobs import export_io_scope, run_export_file_operation, export_io_pending
    queue=local.LocalJobQueue(1);queue._planned_reboot_handoff={'phase':'INCOMPLETE'}
    queue._owner_connection=object();owner=queue._owner_connection;entered=threading.Event();release=threading.Event()
    def blocking(cancel):
        entered.set();release.wait(5)
    try:
        with export_io_scope((queue._generation,'owner-receipt')):
            task=asyncio.create_task(run_export_file_operation(blocking))
        for _ in range(500):
            if entered.is_set():break
            await asyncio.sleep(.01)
        assert entered.is_set() and export_io_pending(queue._io_keys())
        with pytest.raises(JobRecoveryRequired,match='JOB_RECOVERY_HANDOFF_INCOMPLETE'):
            await queue._close()
        assert queue._owner_connection is owner and export_io_pending(queue._io_keys())
    finally:
        release.set();await asyncio.wait_for(task,10)


@pytest.mark.asyncio
@pytest.mark.parametrize('primary', [RuntimeError, asyncio.CancelledError])
async def test_lifespan_preserves_startup_and_cleanup_errors(primary, monkeypatch):
    import main
    import core.jobs
    from fastapi import FastAPI
    class FailingQueue:
        def __init__(self,**kwargs):pass
        async def start(self):raise primary('PRIMARY_START_FAILURE')
        async def stop(self):raise JobRecoveryRequired('JOB_RECOVERY_HANDOFF_INCOMPLETE')
    prior=(main._job_queue,main._shutdown_task,main._shutdown_loop,main._shutdown_event)
    monkeypatch.setattr(core.jobs,'LocalJobQueue',FailingQueue)
    try:
        main._shutdown_task=main._shutdown_loop=None
        with pytest.raises(primary) as caught:
            async with main.lifespan(FastAPI()):pass
        assert any('JOB_RECOVERY_HANDOFF_INCOMPLETE' in note for note in caught.value.__notes__)
    finally:
        main._job_queue,main._shutdown_task,main._shutdown_loop,main._shutdown_event=prior


@pytest.mark.asyncio
async def test_ops_checkpoint_and_admit_read_real_owner_without_writes(physical_identity, monkeypatch, tmp_path):
    state=physical_identity;result,_=await _child('old-closed',tmp_path,state['actual']);assert result['code']=='CLOSED'
    _,authority=await _permit(state,state['actual'])
    module_path=Path(__file__).resolve().parents[2]/'tools/ops/queue_planned_reboot.py'
    spec=importlib.util.spec_from_file_location('a2_planned_reboot_ops',module_path);ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
    current={'authority':authority};monkeypatch.setattr(ops,'_observe_reboot_authority',lambda:current['authority'])
    monkeypatch.setattr(ops,'_verify_storage_and_cluster',lambda _a,_p:None)
    monkeypatch.setattr(ops,'_signing_key',lambda _p,_a:state['key'])
    marker=Path(os.environ['EXPORT_DIR'])/'.queue-owner.json';before=await _owner();raw=marker.read_bytes()
    checkpoint=tmp_path/'checkpoint.json';permit=tmp_path/'permit-ops.json'
    rc=await asyncio.to_thread(ops.main,['checkpoint','--out',str(checkpoint),'--signing-key-file','/unused-fixture','--infra-config-file','/unused-fixture'])
    assert rc==0 and checkpoint.is_file()
    new_boot='simulated-'+uuid4().hex;state['boot']['value']=new_boot;current['authority']=dict(authority,boot=new_boot)
    try:
        rc=await asyncio.to_thread(ops.main,['admit','--checkpoint',str(checkpoint),'--out',str(permit),'--signing-key-file','/unused-fixture','--infra-config-file','/unused-fixture'])
        assert rc==0 and permit.is_file()
        payload,_=local._verify_signed_reboot_permit(permit,current['authority']);assert payload['old_generation']==before['generation'] and payload['new_boot']==new_boot
        assert await _owner()==before and marker.read_bytes()==raw
        rc=await asyncio.to_thread(ops.main,['admit','--checkpoint',str(checkpoint),'--out',str(permit),'--signing-key-file','/unused-fixture','--infra-config-file','/unused-fixture'])
        assert rc!=0 and await _owner()==before and marker.read_bytes()==raw
    finally:state['boot']['value']=state['actual']


@pytest.mark.asyncio
async def test_z_interrupted_handoff_refuses_fresh_process_with_old_proof(physical_identity, monkeypatch, tmp_path):
    state=physical_identity
    result,_=await _child('old-closed',tmp_path,state['actual']);assert result['code']=='CLOSED'
    new_boot='simulated-'+uuid4().hex;proof,authority=await _permit(state,new_boot)
    authority_path=tmp_path/'authority.json';authority_path.write_text(json.dumps(authority));authority_path.chmod(0o600)
    result,_=await _child('interrupted',tmp_path,new_boot,extra={'JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE':str(proof),'A2_CHILD_AUTHORITY':str(authority_path)})
    assert result=={'code':'INJECTED_HANDOFF_AFTER_STARTING','workers':0}
    owner=await _owner();marker=Path(os.environ['EXPORT_DIR'])/'.queue-owner.json';journal=Path(os.environ['EXPORT_DIR'])/'.queue-reboot-handoff.json'
    marker_before=marker.read_bytes();journal_before=journal.read_bytes()
    assert owner['state']=='STARTING' and owner['planned_reboot_handoff']['phase']=='INCOMPLETE'
    assert json.loads(marker_before)==owner and json.loads(journal_before)['phase']=='INCOMPLETE'
    oldproof={k:owner[k] for k in ('host','boot','database','pid','start_ticks')};oldproof['version']=1
    oldpath=tmp_path/'old-exit-proof.json';oldpath.write_text(json.dumps(oldproof));oldpath.chmod(0o600)
    state['boot']['value']=new_boot;monkeypatch.setenv('JOB_QUEUE_RECOVERY_CONFIRMED','1');monkeypatch.setenv('JOB_QUEUE_RECOVERY_PROOF_FILE',str(oldpath))
    legacy=local.LocalJobQueue(1);legacy._previous_receipt=owner
    assert legacy._recovery_proven() is True, 'OLD_SAME_BOOT_PROOF_MUST_BE_VALID'
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema']='public';before=(await db.execute(text('SELECT id::text, status, attempts, payload::text, is_deleted FROM public.sys_jobs ORDER BY id'))).all()
    result,_=await _child('retry-old-proof',tmp_path,new_boot,extra={'JOB_QUEUE_RECOVERY_CONFIRMED':'1','JOB_QUEUE_RECOVERY_PROOF_FILE':str(oldpath)})
    assert result=={'code':'JOB_RECOVERY_HANDOFF_INCOMPLETE','workers':0}
    async with AsyncSessionLocal() as db:
        db.info['tenant_schema']='public';after=(await db.execute(text('SELECT id::text, status, attempts, payload::text, is_deleted FROM public.sys_jobs ORDER BY id'))).all()
    assert after==before and marker.read_bytes()==marker_before and journal.read_bytes()==journal_before


@pytest.fixture
def _offline_no_connections(monkeypatch):
    import socket
    def refuse(*args, **kwargs):
        raise AssertionError('OFFLINE_NETWORK_BLOCKED')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket, 'create_connection', refuse)


def _offline_ops():
    module_path = Path(__file__).resolve().parents[2] / 'tools/ops/queue_planned_reboot.py'
    spec = importlib.util.spec_from_file_location('r1r4_ops', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _offline_owner(root, *, closed, handoff=None):
    import socket
    queue = local.LocalJobQueue(1)
    queue._owner_state_root = root
    fact = {'version': 2, 'host': socket.gethostname(),
            'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'pid': 2147480000, 'start_ticks': 1, 'database': queue._database_identity(),
            'generation': uuid4().hex, 'state_path': str(root / '.queue-owner.json'),
            'owner_backend': 123, 'closed': closed,
            'state': 'CLOSED' if closed else 'ACCEPTING',
            'active_handlers': 0, 'active_io': 0, 'active_admissions': 0}
    if handoff is not None:
        fact['planned_reboot_handoff'] = handoff
    (root / '.queue-owner.json').write_bytes(local._canonical_reboot(fact))
    (root / '.queue-owner.json').chmod(0o600)
    return fact


def test_offline_r1r4_signed_checkpoint_admit_and_path_controls(tmp_path, monkeypatch, _offline_no_connections):
    from concurrent.futures import ThreadPoolExecutor

    ops = _offline_ops()
    root = tmp_path / 'state'; root.mkdir(mode=0o700)
    monkeypatch.setenv('EXPORT_DIR', str(root))
    fact = _offline_owner(root, closed=True)
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    private = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    key_file = tmp_path / 'issuer-key'; key_file.write_bytes(base64.b64encode(private)); key_file.chmod(0o600)
    authority = {'app_uid': os.getuid(), 'issuer_uid': os.getuid(), 'export_root': str(root),
                 'signing_public_key': public, 'database_name': 'synthetic_test', 'database_oid': 42,
                 'boot': fact['boot'], 'deployment_id': 'synthetic-deployment'}
    current = {'value': authority}
    monkeypatch.setattr(ops, '_observe_reboot_authority', lambda: current['value'])
    monkeypatch.setattr(ops, '_verify_storage_and_cluster', lambda *_: None)
    class Result:
        def __init__(self, value): self.value = value
        def scalar_one(self): return self.value
        def one(self): return self.value
        def one_or_none(self): return self.value
    class Connection:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def execute(self, query, params=None):
            sql = str(query)
            if sql.startswith('SET TRANSACTION READ ONLY'): return Result(None)
            if 'pg_try_advisory_lock' in sql: return Result(True)
            if 'current_user, current_database()' in sql: return Result(('mpango_app', 'synthetic_test', 42))
            if 'SELECT job_name,status,is_deleted,payload' in sql: return Result((local.OWNER_ROW_NAME, 'completed', False, fact))
            if 'SELECT EXISTS' in sql: return Result(False)
            raise AssertionError('UNEXPECTED_SQL')
    class Engine:
        def connect(self): return Connection()
        async def dispose(self): pass
    monkeypatch.setattr(ops, 'create_async_engine', lambda *_args, **_kw: Engine())
    checkpoint, permit = tmp_path / 'checkpoint.json', tmp_path / 'permit.json'
    common = ['--signing-key-file', str(key_file), '--infra-config-file', str(tmp_path/'unused')]
    # The CLI calls asyncio.run(); keep pytest's main-thread loop slot intact.
    with ThreadPoolExecutor(max_workers=1) as executor:
        rc = executor.submit(ops.main, ['checkpoint', '--out', str(checkpoint), *common]).result()
        assert rc == 0
        checkpoint_payload, _ = local._verify_signed_reboot_permit(checkpoint, authority, file_uid=authority['issuer_uid'])
        assert checkpoint_payload['kind'] == 'planned_clean_checkpoint_v1'
        current['value'] = dict(authority, boot='synthetic-new-boot')
        rc = executor.submit(ops.main, ['admit', '--out', str(permit), '--checkpoint', str(checkpoint), *common]).result()
        assert rc == 0
    payload, _ = local._verify_signed_reboot_permit(permit, current['value'], file_uid=authority['app_uid'])
    assert payload['kind'] == 'planned_clean_reboot_v1' and payload['old_generation'] == fact['generation']
    before = (root / '.queue-owner.json').read_bytes()
    with pytest.raises((ValueError, OSError)):
        local._read_protected_reboot_file(root / '.queue-owner.json', os.getuid()+1, private=True)
    tampered = json.loads(permit.read_text()); tampered['payload']['old_generation'] = uuid4().hex
    permit.write_text(json.dumps(tampered)); permit.chmod(0o600)
    with pytest.raises(InvalidSignature): local._verify_signed_reboot_permit(permit, current['value'])
    link = tmp_path/'link'; link.symlink_to(root, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        local._read_protected_reboot_file(link/'.queue-owner.json', os.getuid(), private=True)
    unsafe = tmp_path/'unsafe'; unsafe.mkdir(mode=0o700); unsafe.chmod(0o770)
    unsafe_file = unsafe/'file'; unsafe_file.write_text('{}'); unsafe_file.chmod(0o600)
    with pytest.raises(ValueError, match='unsafe parent'):
        local._read_protected_reboot_file(unsafe_file, os.getuid(), private=True)
    assert (root/'.queue-owner.json').read_bytes() == before


@pytest.mark.asyncio
async def test_offline_r1r4_enqueue_refuses_before_handoff_completion(_offline_no_connections):
    queue = local.LocalJobQueue(1)
    queue.state = local.QueueState.ACCEPTING
    queue._planned_reboot_handoff = {'phase': 'INCOMPLETE'}
    with pytest.raises(local.JobQueueNotAccepting):
        await queue.enqueue('export_report', {})
    assert not queue._admissions and not queue.workers


async def _offline_r1r4_child(root, fact, proof):
    import socket
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    def refuse(*args, **kwargs): raise AssertionError('OFFLINE_NETWORK_BLOCKED')
    socket.socket.connect = refuse
    queue = local.LocalJobQueue(1); queue._owner_state_root = root
    queue._previous_receipt = fact
    os.environ['JOB_QUEUE_RECOVERY_CONFIRMED'] = '1'
    os.environ['JOB_QUEUE_RECOVERY_PROOF_FILE'] = str(proof)
    assert queue._recovery_proven() is True, 'OLD_PROOF_POSITIVE_FAILED'
    row = SimpleNamespace(job_name=local.OWNER_ROW_NAME, status='completed', is_deleted=False, payload=fact)
    class Result:
        def scalar_one_or_none(self): return row
    class DB:
        writes = 0
        async def execute(self, statement):
            if self.writes: raise AssertionError('UNEXPECTED_DB_ACCESS')
            return Result()
        def add(self, value): self.writes += 1
    db = DB()
    @asynccontextmanager
    async def transaction(*, claimed=True): yield db
    queue._owner_transaction = transaction
    original = json.dumps(fact, sort_keys=True)
    try:
        await queue._claim_generation()
    except JobRecoveryRequired as error:
        assert error.code == 'JOB_RECOVERY_HANDOFF_INCOMPLETE'
    else:
        raise AssertionError('INCOMPLETE_HANDOFF_ADMITTED')
    assert json.dumps(row.payload, sort_keys=True) == original and db.writes == 0 and not queue.workers
    return {'code': 'JOB_RECOVERY_HANDOFF_INCOMPLETE', 'old_proof_valid': True, 'db_writes': 0, 'workers': 0}


@pytest.mark.asyncio
async def test_offline_r1r4_replace_then_dir_fsync_fails_new_process_refuses(tmp_path, monkeypatch, _offline_no_connections):
    import stat
    root = tmp_path/'state'; root.mkdir(mode=0o700)
    monkeypatch.setenv('EXPORT_DIR', str(root))
    handoff = {'phase': 'INCOMPLETE', 'old_generation': uuid4().hex}
    fact = _offline_owner(root, closed=False, handoff=dict(handoff, phase='COMPLETE'))
    queue = local.LocalJobQueue(1); queue._owner_state_root = root; queue._generation = fact['generation']
    queue._planned_reboot_handoff = handoff
    queue._write_reboot_journal('INCOMPLETE', fact, threading.Event())
    queue._planned_reboot_handoff = fact['planned_reboot_handoff']
    queue._write_reboot_seal(fact, threading.Event())
    original_fsync = os.fsync; fault = {'fired': False}
    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            fault['fired'] = True
            raise OSError('INJECTED_FINAL_DIRECTORY_FSYNC')
        return original_fsync(fd)
    with monkeypatch.context() as scoped:
        scoped.setattr(os, 'fsync', fail_directory)
        with pytest.raises(OSError, match='INJECTED_FINAL_DIRECTORY_FSYNC'):
            queue._write_reboot_journal('COMPLETE', None, threading.Event())
    journal = root/'.queue-reboot-handoff.json'
    assert fault['fired'] and json.loads(journal.read_bytes())['phase'] == 'COMPLETE'
    proof = tmp_path/'old-proof.json'
    proof.write_text(json.dumps({'version': 1, **{k:fact[k] for k in ('host','boot','database','pid','start_ticks')}})); proof.chmod(0o600)
    inputs = tmp_path/'input.json'; inputs.write_text(json.dumps({'fact':fact, 'proof':str(proof), 'root':str(root)})); inputs.chmod(0o600)
    before = {p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    env = {k:os.environ[k] for k in ('PATH','HOME','LANG','DATABASE_URL','REPORTING_DATABASE_URL','SECRET_KEY','MPANGO_ENV','REDIS_URL','EXPORT_DIR') if k in os.environ}
    child = await asyncio.create_subprocess_exec(sys.executable, '-B', '-m', 'tests.test_queue_planned_reboot', '--offline-r1r4-child', str(inputs),
        cwd=str(Path(__file__).resolve().parents[1]), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(child.communicate(), 30)
    assert child.returncode == 0, (stdout, stderr)
    result = json.loads(stdout.decode().strip().splitlines()[-1])
    assert result == {'code':'JOB_RECOVERY_HANDOFF_INCOMPLETE','old_proof_valid':True,'db_writes':0,'workers':0}
    assert {p.name:p.read_bytes() for p in root.iterdir() if p.is_file()} == before


@pytest.mark.asyncio
async def test_offline_r1r4_legacy_same_boot_proof_remains_accepted(tmp_path, monkeypatch, _offline_no_connections):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    root = tmp_path/'state'; root.mkdir(mode=0o700)
    monkeypatch.setenv('EXPORT_DIR', str(root))
    fact = _offline_owner(root, closed=False)
    proof = tmp_path/'legacy-proof.json'
    proof.write_text(json.dumps({'version':1, **{k:fact[k] for k in ('host','boot','database','pid','start_ticks')}})); proof.chmod(0o600)
    monkeypatch.setenv('JOB_QUEUE_RECOVERY_CONFIRMED', '1')
    monkeypatch.setenv('JOB_QUEUE_RECOVERY_PROOF_FILE', str(proof))
    queue = local.LocalJobQueue(1); queue._previous_receipt = fact
    assert queue._recovery_proven() is True
    row = SimpleNamespace(job_name=local.OWNER_ROW_NAME, status='completed', is_deleted=False, payload=fact)
    class Result:
        def scalar_one_or_none(self): return row
    class DB:
        async def execute(self, statement): return Result()
    @asynccontextmanager
    async def transaction(*, claimed=True): yield DB()
    writes = []
    async def persist(closed, **kwargs): writes.append(closed)
    queue._owner_transaction = transaction
    queue._persist_receipt = persist
    await queue._claim_generation()
    assert queue._generation_claimed and writes == [False]


@pytest.mark.asyncio
async def test_offline_r1r4_both_starting_are_refused_without_writes(tmp_path, monkeypatch, _offline_no_connections):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    root = tmp_path/'state'; root.mkdir(mode=0o700)
    monkeypatch.setenv('EXPORT_DIR', str(root))
    handoff = {'phase':'INCOMPLETE', 'old_generation':uuid4().hex}
    fact = _offline_owner(root, closed=False, handoff=handoff); fact['state'] = 'STARTING'
    marker = root/'.queue-owner.json'; marker.write_bytes(local._canonical_reboot(fact)); marker.chmod(0o600)
    writer = local.LocalJobQueue(1); writer._planned_reboot_handoff = handoff
    writer._write_reboot_journal('INCOMPLETE', fact, threading.Event())
    before = {p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    row = SimpleNamespace(job_name=local.OWNER_ROW_NAME, status='completed', is_deleted=False, payload=fact)
    class Result:
        def scalar_one_or_none(self): return row
    class DB:
        async def execute(self, statement): return Result()
    @asynccontextmanager
    async def transaction(*, claimed=True): yield DB()
    queue = local.LocalJobQueue(1); queue._owner_transaction = transaction
    with pytest.raises(JobRecoveryRequired, match='JOB_RECOVERY_HANDOFF_INCOMPLETE'):
        await queue._claim_generation()
    assert row.payload == fact and not queue.workers
    assert {p.name:p.read_bytes() for p in root.iterdir() if p.is_file()} == before


def test_offline_r1r5_real_authority_uid_validation(tmp_path, monkeypatch, _offline_no_connections):
    root = tmp_path/'registered-export'; root.mkdir(mode=0o700)
    device = os.stat(root).st_dev
    authority = {'vm_id':'synthetic-vm', 'deployment_id':'synthetic-deployment',
        'pg_system_identifier':'synthetic-pg', 'database_name':'synthetic_test', 'database_oid':42,
        'pg_storage_id':'synthetic-pg-volume', 'export_storage_id':'synthetic-export-volume',
        'export_root':str(root), 'pg_data_root':str(root), 'pg_container_id':'a'*64,
        'pg_image_id':'sha256:'+'b'*64, 'pg_device':device, 'export_device':device,
        'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'signing_public_key':'synthetic-public-key', 'issuer_uid':0, 'app_uid':os.getuid()}
    current = {'value':authority}
    def fake_authority_file(path, uid, *, private):
        assert path == local.REBOOT_AUTHORITY_PATH and uid == 0 and private is False
        return local._canonical_reboot(current['value'])
    monkeypatch.setattr(local, '_read_protected_reboot_file', fake_authority_file)
    assert local._observe_reboot_authority() == authority
    for key, value in [('issuer_uid',True),('issuer_uid',False),('issuer_uid','0'),
                       ('issuer_uid',-1),('issuer_uid',os.getuid()),('app_uid',0),
                       ('app_uid',True),('app_uid','1000'),('app_uid',-1)]:
        current['value'] = dict(authority, **{key:value})
        with pytest.raises(ValueError): local._observe_reboot_authority()
    for key in ('issuer_uid','app_uid'):
        current['value'] = {k:v for k,v in authority.items() if k != key}
        with pytest.raises(ValueError): local._observe_reboot_authority()


@pytest.mark.asyncio
async def test_offline_r1r5_legacy_0775_and_handoff_refusal(tmp_path, monkeypatch, _offline_no_connections):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    ancestor=tmp_path/'legacy-ancestor';ancestor.mkdir(mode=0o700);ancestor.chmod(0o775)
    root=ancestor/'state';root.mkdir(mode=0o700)
    monkeypatch.setenv('EXPORT_DIR',str(root))
    class Result:
        def __init__(self,row):self.row=row
        def scalar_one_or_none(self):return self.row
        def first(self):return None
    class DB:
        def __init__(self,row):self.row=row;self.added=[]
        async def execute(self,statement):return Result(self.row)
        def add(self,value):self.added.append(value)
    def bind(queue,db,writes):
        @asynccontextmanager
        async def transaction(*,claimed=True):yield db
        async def persist(closed,**kwargs):writes.append(closed)
        queue._owner_transaction=transaction;queue._persist_receipt=persist
    fresh=local.LocalJobQueue(1); fresh_db=DB(None); fresh_writes=[];bind(fresh,fresh_db,fresh_writes)
    await fresh._claim_generation()
    assert fresh._generation_claimed and len(fresh_db.added)==1 and fresh_writes==[False]
    fact=_offline_owner(root,closed=False)
    proof=tmp_path/'legacy-proof';proof.write_text(json.dumps({'version':1,**{k:fact[k] for k in ('host','boot','database','pid','start_ticks')}}));proof.chmod(0o600)
    monkeypatch.setenv('JOB_QUEUE_RECOVERY_CONFIRMED','1');monkeypatch.setenv('JOB_QUEUE_RECOVERY_PROOF_FILE',str(proof))
    row=SimpleNamespace(job_name=local.OWNER_ROW_NAME,status='completed',is_deleted=False,payload=fact)
    legacy=local.LocalJobQueue(1);legacy._previous_receipt=fact
    assert legacy._recovery_proven() is True
    old_db=DB(row);old_writes=[];bind(legacy,old_db,old_writes)
    await legacy._claim_generation()
    assert legacy._generation_claimed and old_writes==[False]
    row.payload=fact
    journal=root/'.queue-reboot-handoff.json';journal.write_text('{broken');journal.chmod(0o600)
    raw=(root/'.queue-owner.json').read_bytes()
    refused=local.LocalJobQueue(1);refused_db=DB(row);refused_writes=[];bind(refused,refused_db,refused_writes)
    with pytest.raises(JobRecoveryRequired,match='JOB_RECOVERY_HANDOFF_INCOMPLETE'):
        await refused._claim_generation()
    assert not refused_writes and row.payload==fact and (root/'.queue-owner.json').read_bytes()==raw
    journal.write_text(json.dumps({'version':1,'phase':'INCOMPLETE','generation':uuid4().hex,'handoff':{'phase':'INCOMPLETE'}}));journal.chmod(0o600)
    with pytest.raises(JobRecoveryRequired,match='JOB_RECOVERY_HANDOFF_INCOMPLETE'):
        await refused._claim_generation()
    journal.unlink();journal.symlink_to(root/'missing-target')
    with pytest.raises(JobRecoveryRequired,match='JOB_RECOVERY_HANDOFF_INCOMPLETE'):
        await refused._claim_generation()
    journal.unlink()
    monkeypatch.setenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE',str(proof))
    with pytest.raises(JobRecoveryRequired,match='JOB_RECOVERY_HANDOFF_INCOMPLETE'):
        await refused._claim_generation()
    assert not refused_writes and row.payload==fact and (root/'.queue-owner.json').read_bytes()==raw
    monkeypatch.delenv('JOB_QUEUE_PLANNED_REBOOT_PROOF_FILE')
    marked=dict(fact,planned_reboot_handoff={'phase':'INCOMPLETE'})
    row.payload=marked;(root/'.queue-owner.json').write_bytes(local._canonical_reboot(marked))
    marked_raw=(root/'.queue-owner.json').read_bytes()
    with pytest.raises(JobRecoveryRequired,match='JOB_RECOVERY_HANDOFF_INCOMPLETE'):
        await refused._claim_generation()
    assert not refused_writes and row.payload==marked and (root/'.queue-owner.json').read_bytes()==marked_raw


if __name__ == '__main__' and len(sys.argv)==3 and sys.argv[1]=='--offline-r1r4-child':
    data = json.loads(Path(sys.argv[2]).read_text())
    print(json.dumps(asyncio.run(_offline_r1r4_child(Path(data['root']), data['fact'], Path(data['proof'])))))


if __name__ == '__main__' and len(sys.argv)==3 and sys.argv[1]=='--child':
    asyncio.run(_child_main(sys.argv[2]))
