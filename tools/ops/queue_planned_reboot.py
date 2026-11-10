"""Create signed, private planned-clean-reboot evidence; never mutate jobs.

The infrastructure authority file and signing key must be provisioned by a
separately authorized operator. This command does not stop or start services.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine

from core.jobs.local_queue import (LocalJobQueue, OWNER_KEYS, OWNER_ROW_ID,
    OWNER_ROW_NAME, _canonical_reboot, _observe_reboot_authority,
    _read_protected_reboot_file, _strict_reboot_json, _verify_signed_reboot_permit)
from database.session import async_engine


def _signing_key(path, authority):
    if os.getuid() != authority['issuer_uid']:
        raise ValueError('issuer uid mismatch')
    raw = _read_protected_reboot_file(path, authority['issuer_uid'], private=True)
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw.strip(), validate=True))
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if base64.b64encode(public).decode() != authority['signing_public_key']:
        raise ValueError('signing authority mismatch')
    return key


def _verify_storage_and_cluster(authority, infra_config):
    """Operator-only observation; privileged credentials never enter the app."""
    import psycopg2
    if Path(authority['pg_data_root']).resolve() != Path(authority['pg_data_root']):
        raise ValueError('unsafe PG data root')
    if os.stat(authority['pg_data_root']).st_dev != authority['pg_device']:
        raise ValueError('PG storage mapping changed')
    config = _strict_reboot_json(_read_protected_reboot_file(infra_config, 0, private=True))
    if set(config) != {'DATABASE_URL'} or not isinstance(config['DATABASE_URL'], str):
        raise ValueError('invalid infrastructure config')
    infra_url = make_url(config['DATABASE_URL'])
    app_url = async_engine.url
    if ((infra_url.host, infra_url.port or 5432, infra_url.database)
            != (app_url.host, app_url.port or 5432, app_url.database)):
        raise ValueError('infrastructure endpoint mismatch')
    container_id = authority['pg_container_id']
    if (len(container_id) != 64 or any(c not in '0123456789abcdef' for c in container_id)
            or app_url.host != '127.0.0.1'):
        raise ValueError('invalid registered PG container')
    def inspect(fmt):
        result = subprocess.run(['docker', 'inspect', '--format', fmt, container_id],
            env={'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'},
            capture_output=True, check=True, timeout=15)
        return result.stdout.decode().strip()
    if inspect('{{.Id}}') != container_id or inspect('{{.Image}}') != authority['pg_image_id']:
        raise ValueError('registered PG container changed')
    if inspect('{{.State.Running}}') != 'true':
        raise ValueError('registered PG container is not running')
    mounts = json.loads(inspect('{{json .Mounts}}'))
    ports = json.loads(inspect('{{json .NetworkSettings.Ports}}'))
    if ports.get('5432/tcp') != [{'HostIp': '127.0.0.1', 'HostPort': str(app_url.port or 5432)}]:
        raise ValueError('registered PG endpoint changed')
    with psycopg2.connect(config['DATABASE_URL']) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cursor:
            cursor.execute('SELECT system_identifier::text FROM pg_control_system()')
            if cursor.fetchone()[0] != authority['pg_system_identifier']:
                raise ValueError('PG cluster mismatch')
            cursor.execute('SHOW data_directory')
            data_directory = cursor.fetchone()[0]
    matching = [m for m in mounts if m.get('Type') == 'volume'
                and m.get('Name') == authority['pg_storage_id']
                and m.get('Source') == authority['pg_data_root']
                and (data_directory == m.get('Destination')
                     or data_directory.startswith(m.get('Destination', '') + '/'))]
    if len(matching) != 1:
        raise ValueError('PG data mount mismatch')


async def _closed_snapshot(authority):
    queue = LocalJobQueue()
    if str(queue._owner_state_root) != authority['export_root']:
        raise ValueError('export root mismatch')
    journal = queue._read_reboot_journal(file_uid=authority['app_uid'])
    if journal is not None and journal['phase'] != 'COMPLETE':
        raise ValueError('planned handoff incomplete')
    engine = create_async_engine(async_engine.url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text('SET TRANSACTION READ ONLY'))
            lock = (await conn.execute(text('SELECT pg_try_advisory_lock(:a,:b)'),
                                       {'a': OWNER_KEYS[0], 'b': OWNER_KEYS[1]})).scalar_one()
            if not lock:
                raise ValueError('owner still active')
            db = (await conn.execute(text('SELECT current_user, current_database(), oid FROM pg_database WHERE datname=current_database()'))).one()
            if (db[0] != 'mpango_app' or db[1] != authority['database_name']
                    or db[2] != authority['database_oid']):
                raise ValueError('app identity mismatch')
            row = (await conn.execute(text('SELECT job_name,status,is_deleted,payload FROM public.sys_jobs WHERE id=:id'),
                                      {'id': OWNER_ROW_ID})).one_or_none()
            if row is None or row[0] != OWNER_ROW_NAME or row[1] != 'completed' or row[2]:
                raise ValueError('owner row missing')
            fact = row[3]
            if fact != queue._read_generation(file_uid=authority['app_uid']):
                raise ValueError('owner marker mismatch')
            if (not isinstance(fact, dict) or fact.get('version') != 2
                    or fact.get('state') != 'CLOSED' or fact.get('closed') is not True
                    or any(type(fact.get(k)) is not int or fact[k] != 0
                           for k in ('active_handlers', 'active_io', 'active_admissions'))):
                raise ValueError('owner not clean')
            queue._check_reboot_handoff(fact, file_uid=authority['app_uid'])
            if fact.get('state_path') != str(queue._receipt_path()) or fact.get('database') != queue._database_identity():
                raise ValueError('owner identity mismatch')
            if fact.get('boot') == authority['boot']:
                try:
                    if queue._ticks(fact['pid']) == fact['start_ticks']:
                        raise ValueError('owner process still alive')
                except FileNotFoundError:
                    pass
            unsafe = (await conn.execute(text("SELECT EXISTS(SELECT 1 FROM public.sys_jobs WHERE id<>:owner AND (job_name=:name OR status IS NULL OR status NOT IN ('completed','failed')))"),
                {'owner': OWNER_ROW_ID, 'name': OWNER_ROW_NAME})).scalar_one()
            if unsafe:
                raise ValueError('unfinished business')
            return fact
    finally:
        await engine.dispose()


def _write_new(path, envelope, uid):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or not path.name:
        raise ValueError('unsafe output path')
    if os.getuid() not in (0, uid):
        raise ValueError('cannot assign output owner')
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:-1]:
            parent = os.fstat(directory)
            if not stat.S_ISDIR(parent.st_mode) or parent.st_uid not in (0, uid) or parent.st_mode & 0o022:
                raise ValueError('unsafe output directory')
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = nxt
        parent = os.fstat(directory)
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid not in (0, uid) or parent.st_mode & 0o022:
            raise ValueError('unsafe output directory')
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, 'wb') as stream:
            if os.getuid() == 0:
                os.fchown(stream.fileno(), uid, -1)
            stream.write(_canonical_reboot(envelope))
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)


def _sign(payload, key):
    return {'payload': payload, 'signature': base64.b64encode(key.sign(_canonical_reboot(payload))).decode()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('checkpoint', 'admit'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--out', required=True)
        cmd.add_argument('--signing-key-file', required=True)
        cmd.add_argument('--infra-config-file', required=True)
        if name == 'admit':
            cmd.add_argument('--checkpoint', required=True)
    args = parser.parse_args(argv)
    try:
        authority = _observe_reboot_authority()
        _verify_storage_and_cluster(authority, args.infra_config_file)
        key = _signing_key(args.signing_key_file, authority)
        old = asyncio.run(_closed_snapshot(authority))
        if args.action == 'checkpoint':
            if old.get('boot') != authority['boot']:
                raise ValueError('checkpoint boot mismatch')
            payload = {'kind': 'planned_clean_checkpoint_v1', 'owner': old, 'authority': authority}
        else:
            checkpoint, _ = _verify_signed_reboot_permit(args.checkpoint, authority, file_uid=authority['issuer_uid'])
            prior = checkpoint['authority']
            stable = set(authority) - {'boot', 'pg_device', 'export_device'}
            if (checkpoint.get('kind') != 'planned_clean_checkpoint_v1' or checkpoint['owner'] != old
                    or prior['boot'] != old['boot'] or prior['boot'] == authority['boot']
                    or any(prior[k] != authority[k] for k in stable)):
                raise ValueError('checkpoint identity mismatch')
            payload = {'kind': 'planned_clean_reboot_v1', 'old_owner_sha256': hashlib.sha256(_canonical_reboot(old)).hexdigest(),
                       'old_generation': old['generation'], 'old_boot': old['boot'],
                       'new_boot': authority['boot'], 'authority': authority}
        output_uid = authority['issuer_uid'] if args.action == 'checkpoint' else authority['app_uid']
        _write_new(args.out, _sign(payload, key), output_uid)
        print('PLANNED_REBOOT_EVIDENCE_CREATED')
        return 0
    except Exception as error:
        print('PLANNED_REBOOT_EVIDENCE_REFUSED:' + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
