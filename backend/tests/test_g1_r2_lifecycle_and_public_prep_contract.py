"""C91 R2: real loop, pool and write-connection preparation boundaries."""
import asyncio
import importlib
import os
from urllib.parse import urlparse

import psycopg2
import pytest
from sqlalchemy import text

from database.session import AsyncSessionLocal, async_engine
from tests.async_test_utils import (
    assert_migration_public_connection,
    migration_prep_identity,
    run_coroutine,
    temporary_database_url,
)


def _catalog(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT n.nspname,c.relname,c.relkind,c.relowner "
                       "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                       "WHERE n.nspname='public' ORDER BY c.relname")
        return cursor.fetchall()


def test_sync_shared_pool_released_on_its_actual_loop():
    async def use_pool():
        loop = asyncio.get_running_loop()
        async with AsyncSessionLocal() as session:
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
        print("FR2_SYNC_POOL", id(loop), "closed", loop.is_closed())
    run_coroutine(use_pool())
    assert async_engine.pool.checkedout() == 0, "FR2_POOL_CHECKED_OUT"
    assert async_engine.pool.checkedin() == 0, "FR2_POOL_OWNER_BOUNDARY"


@pytest.mark.asyncio
async def test_async_victim_after_sync_pool_executes_real_sql():
    loop = asyncio.get_running_loop()
    try:
        async with AsyncSessionLocal() as session:
            assert (await session.execute(text("SELECT 42"))).scalar_one() == 42
        print("FR2_ASYNC_VICTIM", id(loop), "closed", loop.is_closed())
    finally:
        await async_engine.dispose()


_PREPARATIONS = (
    ("tests.test_dc11d_payment_replay_concurrency_integrity", "_ensure_public_tables"),
    ("tests.test_dc12r1_j1_h2b_forgot_password_runtime_closure", "_prepare_tables"),
)


@pytest.mark.parametrize("module,function", _PREPARATIONS)
def test_public_preparation_wrong_live_database_is_write_free(monkeypatch, module, function):
    real_connect = psycopg2.connect
    preparation = getattr(importlib.import_module(module), function)
    with temporary_database_url(os.environ["TEST_DATABASE_URL"], "fr2wrong") as wrong:
        connection = real_connect(wrong)
        before = _catalog(connection)
        connection.rollback()
        with monkeypatch.context() as patch:
            patch.setattr(psycopg2, "connect", lambda *a, **kw: connection)
            with pytest.raises(RuntimeError, match="PUBLIC_PREP_REFUSED_ACTUAL_IDENTITY_MISMATCH"):
                preparation()
        assert connection.closed
        check = real_connect(wrong)
        try:
            assert _catalog(check) == before, "FR2_WRONG_DATABASE_WAS_WRITTEN"
        finally:
            check.close()


@pytest.mark.parametrize("module,function", _PREPARATIONS)
@pytest.mark.parametrize("key", ("TEST_DATABASE_URL", "TEST_MIGRATION_DATABASE_URL", "TEST_OPERATOR_DATABASE_URL"))
def test_public_preparation_missing_key_refused_before_connect(monkeypatch, module, function, key):
    preparation = getattr(importlib.import_module(module), function)
    monkeypatch.delenv(key)
    def forbid_connect(*args, **kwargs):
        pytest.fail("FR2_MISSING_CONFIG_OPENED_CONNECTION")
    monkeypatch.setattr(psycopg2, "connect", forbid_connect)
    with pytest.raises(RuntimeError, match="missing:"):
        preparation()


def test_actual_admin_and_operator_refused_without_public_writes():
    identity = migration_prep_identity()
    for key in ("TEST_ADMIN_DATABASE_URL", "TEST_OPERATOR_DATABASE_URL"):
        url = urlparse(os.environ[key])._replace(path="/" + identity.database).geturl()
        connection = psycopg2.connect(url)
        try:
            before = _catalog(connection)
            with pytest.raises(RuntimeError, match="PUBLIC_PREP_REFUSED_ACTUAL_IDENTITY_MISMATCH"):
                assert_migration_public_connection(connection, identity)
            assert _catalog(connection) == before
        finally:
            connection.close()


def test_absent_object_allowed_only_after_live_database_and_schema_proof():
    source = migration_prep_identity()
    with temporary_database_url(source.url, "fr2empty") as url:
        identity = type(source)(str(url), source.user, urlparse(url).path.lstrip("/"))
        connection = psycopg2.connect(url)
        try:
            assert_migration_public_connection(connection, identity, ("fr2_object",))
            with connection.cursor() as cursor:
                cursor.execute("CREATE TABLE public.fr2_object(id integer PRIMARY KEY)")
            connection.commit()
            assert any(row[1] == "fr2_object" for row in _catalog(connection))
        finally:
            connection.close()


def test_p21_missing_migration_identity_is_failure_not_skip(monkeypatch):
    from tests.test_platform_p21_durable_approval_schema import _boot
    monkeypatch.delenv("TEST_MIGRATION_DATABASE_URL")
    with pytest.raises(RuntimeError, match="PUBLIC_PREP_REFUSED_MISSING_MIGRATION_IDENTITY"):
        try:
            next(_boot.__wrapped__())
        except pytest.skip.Exception:
            pytest.fail("FR2_MISSING_CONFIGURATION_MUST_NOT_SKIP")


def test_smoke_session_context_comes_from_its_own_tenant():
    from tests.test_s3a_fresh_tenant_runtime_smoke import _make_mock_session
    a = _make_mock_session(tenant_id="tenant-a", tenant_schema="t_a")
    b = _make_mock_session(tenant_id="tenant-b", tenant_schema="t_b")
    assert a.info["tenant_schema"] == "t_a"
    assert b.info["tenant_schema"] == "t_b"
    assert _make_mock_session().info == {}


def test_s1r5_catalog_dispatch_uses_owned_database_and_removes_it(monkeypatch):
    from tests import test_dc12r1_s1_r5_migration_preflight_exact_catalog as subject
    source = migration_prep_identity()
    seen = []

    def inspect_boundary(database_url, *args, **kwargs):
        target = urlparse(database_url).path.lstrip("/")
        assert target != source.database, "FR2_S1R5_SHARED_DATABASE_REFUSED"
        connection = psycopg2.connect(database_url)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user")
                assert cursor.fetchone() == (target, source.user)
                cursor.execute("SELECT version_num FROM public.alembic_version")
                assert cursor.fetchone()[0] == "039_order_credit_holds"
        finally:
            connection.close()
        seen.append(target)

    monkeypatch.setattr(subject, "_validate_isolated_token_catalog", inspect_boundary)
    subject._validate_token_catalog_in_transaction("setup", "", expect_failure=False)
    assert len(seen) == 1
    connection = psycopg2.connect(source.url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_database WHERE datname=%s", (seen[0],))
            assert cursor.fetchone()[0] == 0, "FR2_S1R5_DATABASE_RESIDUE"
    finally:
        connection.close()


@pytest.mark.parametrize("field", ("id", "owner", "task", "mount", "image"))
def test_p21_wrong_resource_identity_never_stops(field):
    from tests.task_owned_pg_resources import OWNER, TASK, stop_owned_postgres

    cid = "a" * 64
    record = {"id": cid, "image": "sha256:" + "b" * 64, "volume": "owned-volume"}
    info = {"Id": cid, "Image": record["image"],
            "Config": {"Labels": {"mpango.owner": OWNER, "mpango.task": TASK}},
            "Mounts": [{"Type": "volume", "Name": "owned-volume",
                        "Destination": "/var/lib/postgresql/data"}],
            "State": {"Running": True}}
    if field == "id":
        info["Id"] = "c" * 64
    elif field in ("owner", "task"):
        info["Config"]["Labels"]["mpango." + field] = "other-task"
    elif field == "mount":
        info["Mounts"][0]["Name"] = "other-volume"
    else:
        info["Image"] = "other-image"
    calls = []
    try:
        with pytest.raises(RuntimeError, match="TASK_PG_.*_MISMATCH"):
            stop_owned_postgres(record, inspect=lambda value: info, stop=calls.append)
    finally:
        assert calls == [], "FR3_WRONG_RESOURCE_WAS_STOPPED"


def test_p21_owned_resource_stops_only_exact_id():
    from tests.task_owned_pg_resources import OWNER, TASK, stop_owned_postgres

    cid = "a" * 64
    record = {"id": cid, "image": "sha256:" + "b" * 64, "volume": "owned-volume"}
    info = {"Id": cid, "Image": record["image"],
            "Config": {"Labels": {"mpango.owner": OWNER, "mpango.task": TASK}},
            "Mounts": [{"Type": "volume", "Name": "owned-volume",
                        "Destination": "/var/lib/postgresql/data"}],
            "State": {"Running": True}}
    calls = []
    def stop(value):
        calls.append(value)
        info["State"]["Running"] = False
    stop_owned_postgres(record, inspect=lambda value: info, stop=stop)
    assert calls == [cid], "FR3_STOP_NOT_BOUND_TO_EXACT_ID"


def test_p21_stop_failure_is_not_suppressed():
    from tests.task_owned_pg_resources import OWNER, TASK, stop_owned_postgres

    cid = "a" * 64
    record = {"id": cid, "image": "image", "volume": "owned-volume"}
    info = {"Id": cid, "Image": "image",
            "Config": {"Labels": {"mpango.owner": OWNER, "mpango.task": TASK}},
            "Mounts": [{"Type": "volume", "Name": "owned-volume",
                        "Destination": "/var/lib/postgresql/data"}]}
    def fail(value):
        raise RuntimeError("stop failed")
    with pytest.raises(RuntimeError, match="stop failed"):
        stop_owned_postgres(record, inspect=lambda value: info, stop=fail)


def test_p21_real_runtime_identity_and_closed_connections():
    import json
    from pathlib import Path
    from tests.task_owned_pg_resources import _inspect, task_postgres

    with task_postgres("p21control") as urls:
        cid = urls["container"]
        connection = psycopg2.connect(urls["mig_sync"])
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user")
                row = cursor.fetchone()
                assert row == ("mpango_app", False, False, False, False, False), "FR3_P21_BUSINESS_IDENTITY_ELEVATED"
                cursor.execute("SELECT has_schema_privilege(current_user,'public','CREATE')")
                assert cursor.fetchone() == (False,), "FR3_P21_RUNTIME_PUBLIC_CREATE"
        finally:
            connection.close()
    assert _inspect(cid)["State"]["Running"] is False, "FR3_OWNED_PG_NOT_STOPPED"
    root = Path(urls["private_root"])
    before = json.loads((root / "authority-before.json").read_text())
    after = json.loads((root / "authority-after.json").read_text())
    assert before == after, "FR3_P21_AUTHORITY_CHANGED"
    assert before["head"] == [["039_order_credit_holds"]], "FR3_P21_WRONG_HEAD"
    assert json.loads((root / "connection-close-proof.json").read_text())["remaining"] == [], "FR3_P21_CONNECTIONS_REMAIN"


@pytest.mark.parametrize("fault", ["inspect", "receipt"])
def test_p21_post_create_failure_enters_owned_stop_boundary(tmp_path,
                                                           monkeypatch, fault):
    from tests import task_owned_pg_resources as resources

    tmp_path.chmod(0o700)
    monkeypatch.setenv("C91_R3_RESOURCE_ROOT", str(tmp_path))
    cid = "b" * 64
    image = "sha256:" + "c" * 64
    created = []
    stopped = []
    failure = RuntimeError("C91_EXPECTED_POST_CREATE_FAILURE")
    original_save = resources._save
    def native(root, name, argv, **kwargs):
        assert name in ("volume", "container"), "C91_UNEXPECTED_SETUP_REACHED"
        if name == "container":
            created.append(cid)
            return cid
        return argv[-1]
    def inspect(value):
        assert value == cid
        raise failure
    def save(path, data):
        if fault == "receipt" and path.name == "resource-created.json":
            raise failure
        original_save(path, data)
    monkeypatch.setattr(resources, "_native", native)
    monkeypatch.setattr(resources, "_postgres_image_id", lambda: image)
    monkeypatch.setattr(resources, "_inspect", inspect)
    monkeypatch.setattr(resources, "_save", save)
    monkeypatch.setattr(resources, "stop_owned_postgres",
                        lambda record: stopped.append(record.copy()))
    with pytest.raises(RuntimeError) as caught:
        with resources.task_postgres("exception-control"):
            pytest.fail("C91_FAILED_SETUP_YIELDED")
    assert caught.value is failure
    assert created == [cid]
    assert len(stopped) == 1, "C91_CREATED_CONTAINER_ESCAPED_FINALIZER"
    assert stopped[0]["id"] == cid and stopped[0]["image"] == image
    assert stopped[0]["owner"] == resources.OWNER
    assert stopped[0]["task"] == resources.TASK
