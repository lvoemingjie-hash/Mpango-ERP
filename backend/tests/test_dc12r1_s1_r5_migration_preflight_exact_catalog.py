"""DC-12R1-S1-R5 migration preflight and exact catalog evidence tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from tests.async_test_utils import run_alembic_upgrade, temporary_database_url


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_PATH = BACKEND_DIR / "alembic" / "versions" / "036_retailer_mvp_identity.py"
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"
REV_035 = "035_receivable_collection_integrity"
REV_036 = "036_retailer_mvp_identity"

SETUP_TABLE = "retailer_credential_setup_tokens"
RESET_TABLE = "retailer_password_reset_tokens"  # pragma: allowlist secret


def _load_mod():
    spec = importlib.util.spec_from_file_location("m036_r5", MIGRATION_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sync_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _async_url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _engine(url: str | None = None):
    return create_engine(_sync_url(url or os.environ["DATABASE_URL"]), future=True)


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", _async_url(url))
    return config


@contextmanager
def _database_url_env(url: str):
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _tenant_auth_ddl(schema: str) -> list[str]:
    return [
        f'CREATE SCHEMA "{schema}"',
        f'CREATE TABLE "{schema}".users ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "email VARCHAR(255) NOT NULL UNIQUE, "
        "password_hash VARCHAR(255) NOT NULL, "
        "is_active BOOLEAN NOT NULL DEFAULT true, "
        "is_deleted BOOLEAN NOT NULL DEFAULT false, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "deleted_at TIMESTAMPTZ)",
        f'CREATE TABLE "{schema}".roles ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "name VARCHAR(100) NOT NULL UNIQUE, description TEXT)",
        f'CREATE TABLE "{schema}".permissions ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "code VARCHAR(100) NOT NULL UNIQUE, description TEXT)",
        f'CREATE TABLE "{schema}".user_roles ('
        f'user_id UUID NOT NULL REFERENCES "{schema}".users(id) ON DELETE CASCADE, '
        f'role_id UUID NOT NULL REFERENCES "{schema}".roles(id) ON DELETE CASCADE, '
        "PRIMARY KEY (user_id, role_id))",
        f'CREATE TABLE "{schema}".role_permissions ('
        f'role_id UUID NOT NULL REFERENCES "{schema}".roles(id) ON DELETE CASCADE, '
        f'permission_id UUID NOT NULL REFERENCES "{schema}".permissions(id) ON DELETE CASCADE, '
        "PRIMARY KEY (role_id, permission_id))",
    ]


def _create_registered_tenant(connection, *, prefix: str) -> tuple[uuid.UUID, str]:
    wholesaler_id = uuid.uuid4()
    registration_id = uuid.uuid4()
    schema = f"t_{wholesaler_id.hex}"
    connection.execute(
        text(
            "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
            "VALUES (:id, :code, :name, 'active', false)"
        ),
        {
            "id": wholesaler_id,
            "code": f"{prefix}{uuid.uuid4().hex[:8]}".upper()[:32],
            "name": f"Tenant {prefix}",
        },
    )
    connection.execute(
        text(
            "INSERT INTO public.tenant_registrations ("
            "id, company_name, tenant_code, country, owner_email, status, "
            "wholesaler_id, tenant_schema, expires_at, is_deleted"
            ") VALUES ("
            ":id, :company_name, :tenant_code, 'ZA', :owner_email, 'provisioning', "
            ":wholesaler_id, :tenant_schema, :expires_at, false"
            ")"
        ),
        {
            "id": registration_id,
            "company_name": f"Company {prefix}",
            "tenant_code": f"{prefix}{uuid.uuid4().hex[:8]}".lower()[:32],
            "owner_email": f"{prefix.lower()}_{uuid.uuid4().hex[:8]}@example.com",
            "wholesaler_id": wholesaler_id,
            "tenant_schema": schema,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        },
    )
    for ddl in _tenant_auth_ddl(schema):
        connection.execute(text(ddl))
    return wholesaler_id, schema


def _create_mapping_fixture(
    connection,
    *,
    retailer_id: uuid.UUID,
    prefix: str,
    user_exists: bool = True,
    is_active: bool = True,
    password_hash: str = "active-hash",
) -> tuple[uuid.UUID, str, uuid.UUID]:
    wholesaler_id, schema = _create_registered_tenant(connection, prefix=prefix)
    tenant_user_id = uuid.uuid4()
    connection.execute(
        text(
            "INSERT INTO public.retailers (id, phone, name, email, is_deleted) "
            "VALUES (:id, :phone, :name, :email, false) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": retailer_id,
            "phone": f"+27{uuid.uuid4().int % 10**8:08d}",
            "name": f"Retailer {prefix}",
            "email": f"{prefix.lower()}_{uuid.uuid4().hex[:8]}@example.com",
        },
    )
    connection.execute(
        text(
            "INSERT INTO public.wholesaler_retailer_bindings ("
            "wholesaler_id, retailer_id, tenant_user_id, status, outstanding_balance, is_deleted"
            ") VALUES (:wholesaler_id, :retailer_id, :tenant_user_id, 'active', 0, false)"
        ),
        {
            "wholesaler_id": wholesaler_id,
            "retailer_id": retailer_id,
            "tenant_user_id": tenant_user_id,
        },
    )
    if user_exists:
        connection.execute(
            text(
                f'INSERT INTO "{schema}".users '
                "(id, email, password_hash, is_active, is_deleted) "
                "VALUES (:id, :email, :password_hash, :is_active, false)"
            ),
            {
                "id": tenant_user_id,
                "email": f"{prefix.lower()}_{uuid.uuid4().hex[:8]}@example.com",
                "password_hash": password_hash,
                "is_active": is_active,
            },
        )
    return wholesaler_id, schema, tenant_user_id


def _live_rows(connection, mod):
    return mod._registered_tenants(connection)


def _with_isolated_mappings(assertion):
    mod = _load_mod()
    eng = _engine()
    with eng.connect() as connection:
        trans = connection.begin()
        try:
            connection.execute(
                text(
                    "UPDATE public.wholesaler_retailer_bindings "
                    "SET is_deleted = true WHERE is_deleted IS FALSE"
                )
            )
            assertion(connection, mod)
        finally:
            trans.rollback()
            eng.dispose()


def test_inactive_mapped_user_is_accepted_as_existing_mapping():
    def assertion(connection, mod):
        retailer_id = uuid.uuid4()
        _create_mapping_fixture(
            connection,
            retailer_id=retailer_id,
            prefix="r5inactive",
            is_active=False,
            password_hash="placeholder-does-not-matter",  # pragma: allowlist secret
        )
        assert mod._check_conflicting_active_hashes(connection, _live_rows(connection, mod)) == []

    _with_isolated_mappings(assertion)


def test_missing_mapped_user_is_rejected_with_exact_code():
    def assertion(connection, mod):
        retailer_id = uuid.uuid4()
        _create_mapping_fixture(
            connection,
            retailer_id=retailer_id,
            prefix="r5missing",
            user_exists=False,
        )
        failures = mod._check_conflicting_active_hashes(connection, _live_rows(connection, mod))
        assert any("RETAILER_MAPPING_USER_MISSING" in failure for failure in failures)

    _with_isolated_mappings(assertion)


def test_conflicting_active_mapped_hashes_are_rejected():
    def assertion(connection, mod):
        retailer_id = uuid.uuid4()
        _create_mapping_fixture(
            connection,
            retailer_id=retailer_id,
            prefix="r5conflicta",
            is_active=True,
            password_hash="active-hash-a",  # pragma: allowlist secret
        )
        _create_mapping_fixture(
            connection,
            retailer_id=retailer_id,
            prefix="r5conflictb",
            is_active=True,
            password_hash="active-hash-b",  # pragma: allowlist secret
        )
        failures = mod._check_conflicting_active_hashes(connection, _live_rows(connection, mod))
        assert any("active mapped copies have conflicting password hashes" in f for f in failures)

    _with_isolated_mappings(assertion)


def test_inactive_placeholder_hash_does_not_conflict_with_active_hash():
    def assertion(connection, mod):
        retailer_id = uuid.uuid4()
        _create_mapping_fixture(
            connection,
            retailer_id=retailer_id,
            prefix="r5active",
            is_active=True,
            password_hash="active-hash",  # pragma: allowlist secret
        )
        _create_mapping_fixture(
            connection,
            retailer_id=retailer_id,
            prefix="r5inactiveb",
            is_active=False,
            password_hash="different-inactive-placeholder",  # pragma: allowlist secret
        )
        assert mod._check_conflicting_active_hashes(connection, _live_rows(connection, mod)) == []

    _with_isolated_mappings(assertion)


def _token_ddl(kind: str) -> str:
    if kind == "setup":
        table = SETUP_TABLE
        purpose = "retailer_credential_setup"
        extra_columns = (
            "binding_id UUID NOT NULL REFERENCES public.wholesaler_retailer_bindings(id) "
            "ON DELETE CASCADE,\n"
            "issued_by_wholesaler_id UUID,"
        )
    else:
        table = RESET_TABLE
        purpose = "retailer_password_reset"
        extra_columns = ""
    return f"""
        CREATE TABLE public.{table} (
            id UUID DEFAULT gen_random_uuid(),
            retailer_id UUID NOT NULL REFERENCES public.retailers(id) ON DELETE CASCADE,
            {extra_columns}
            token_hash VARCHAR(128) NOT NULL,
            purpose VARCHAR(64) NOT NULL DEFAULT '{purpose}',
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMPTZ,
            CONSTRAINT pk_{table} PRIMARY KEY (id),
            CONSTRAINT ck_{table}_purpose CHECK (purpose = '{purpose}'),
            CONSTRAINT ck_{table}_not_used_and_revoked CHECK (used_at IS NULL OR revoked_at IS NULL),
            CONSTRAINT uq_{table}_token_hash UNIQUE (token_hash)
        )
    """


def _token_indexes(kind: str) -> list[str]:
    if kind == "setup":
        return [
            f"CREATE UNIQUE INDEX ux_{SETUP_TABLE}_token_hash ON public.{SETUP_TABLE} (token_hash)",
            f"CREATE INDEX ix_{SETUP_TABLE}_retailer_id ON public.{SETUP_TABLE} (retailer_id)",
            f"CREATE INDEX ix_{SETUP_TABLE}_binding_id ON public.{SETUP_TABLE} (binding_id)",
            f"CREATE INDEX ix_{SETUP_TABLE}_expires_at ON public.{SETUP_TABLE} (expires_at)",
            f"CREATE UNIQUE INDEX ux_{SETUP_TABLE}_retailer_active ON public.{SETUP_TABLE} "
            "(retailer_id) WHERE used_at IS NULL AND revoked_at IS NULL AND is_deleted = false",
        ]
    return [
        f"CREATE UNIQUE INDEX ux_{RESET_TABLE}_token_hash ON public.{RESET_TABLE} (token_hash)",
        f"CREATE INDEX ix_{RESET_TABLE}_retailer_id ON public.{RESET_TABLE} (retailer_id)",
        f"CREATE INDEX ix_{RESET_TABLE}_expires_at ON public.{RESET_TABLE} (expires_at)",
        f"CREATE UNIQUE INDEX ux_{RESET_TABLE}_retailer_active ON public.{RESET_TABLE} "
        "(retailer_id) WHERE used_at IS NULL AND revoked_at IS NULL AND is_deleted = false",
    ]


def _table_name(kind: str) -> str:
    return SETUP_TABLE if kind == "setup" else RESET_TABLE


def _validator(mod, kind: str):
    return (
        mod._validate_setup_token_table_contract
        if kind == "setup"
        else mod._validate_reset_token_table_contract
    )


def _validate_token_catalog_in_transaction(
    kind: str,
    ddl: str,
    *,
    pre_sql: list[str] | None = None,
    expect_failure: bool = True,
) -> None:
    mod = _load_mod()
    eng = _engine()
    table = _table_name(kind)
    with eng.connect() as connection:
        trans = connection.begin()
        try:
            for stmt in pre_sql or []:
                connection.execute(text(stmt))
            connection.execute(text(f"DROP TABLE IF EXISTS public.{table}"))
            connection.execute(text(ddl))
            for stmt in _token_indexes(kind):
                connection.execute(text(stmt))
            if expect_failure:
                with pytest.raises(mod.PreflightFailure):
                    _validator(mod, kind)(connection)
            else:
                _validator(mod, kind)(connection)
        finally:
            trans.rollback()
            eng.dispose()


@pytest.mark.parametrize("kind", ["setup", "reset"])
def test_valid_public_single_column_fk_is_accepted(kind: str):
    _validate_token_catalog_in_transaction(
        kind,
        _token_ddl(kind),
        expect_failure=False,
    )


@pytest.mark.parametrize("kind", ["setup", "reset"])
def test_non_public_same_name_fk_target_is_rejected(kind: str):
    ddl = _token_ddl(kind).replace(
        "REFERENCES public.retailers(id) ON DELETE CASCADE",
        "REFERENCES r5_shadow.retailers(id) ON DELETE CASCADE",
        1,
    )
    _validate_token_catalog_in_transaction(
        kind,
        ddl,
        pre_sql=[
            "CREATE SCHEMA r5_shadow",
            "CREATE TABLE r5_shadow.retailers (id UUID PRIMARY KEY)",
        ],
    )


@pytest.mark.parametrize("kind", ["setup", "reset"])
def test_composite_fk_is_rejected(kind: str):
    ddl = _token_ddl(kind).replace(
        "retailer_id UUID NOT NULL REFERENCES public.retailers(id) ON DELETE CASCADE,",
        "retailer_id UUID NOT NULL,",
        1,
    )
    if kind == "reset":
        ddl = ddl.replace(
            "token_hash VARCHAR(128) NOT NULL,",
            "binding_id UUID,\n            token_hash VARCHAR(128) NOT NULL,",
            1,
        )
    ddl = ddl.replace(
        f"CONSTRAINT pk_{_table_name(kind)} PRIMARY KEY (id),",
        f"CONSTRAINT pk_{_table_name(kind)} PRIMARY KEY (id),\n"
        "            CONSTRAINT fk_r5_composite FOREIGN KEY (retailer_id, binding_id) "
        "REFERENCES public.wholesaler_retailer_bindings(retailer_id, id) ON DELETE CASCADE,",
        1,
    )
    _validate_token_catalog_in_transaction(
        kind,
        ddl,
        pre_sql=[
            "CREATE UNIQUE INDEX ux_r5_bindings_retailer_id_id "
            "ON public.wholesaler_retailer_bindings (retailer_id, id)",
        ],
    )


@pytest.mark.parametrize("kind", ["setup", "reset"])
def test_wrong_referenced_column_is_rejected(kind: str):
    ddl = _token_ddl(kind).replace(
        "REFERENCES public.retailers(id) ON DELETE CASCADE",
        "REFERENCES public.retailers(r5_wrong_ref) ON DELETE CASCADE",
        1,
    )
    _validate_token_catalog_in_transaction(
        kind,
        ddl,
        pre_sql=[
            "ALTER TABLE public.retailers ADD COLUMN r5_wrong_ref UUID",
            "ALTER TABLE public.retailers ADD CONSTRAINT uq_r5_wrong_ref UNIQUE (r5_wrong_ref)",
        ],
    )


@pytest.mark.parametrize("kind", ["setup", "reset"])
def test_wrong_target_table_is_rejected(kind: str):
    ddl = _token_ddl(kind).replace(
        "REFERENCES public.retailers(id) ON DELETE CASCADE",
        "REFERENCES public.wholesalers(id) ON DELETE CASCADE",
        1,
    )
    _validate_token_catalog_in_transaction(kind, ddl)


@pytest.mark.parametrize("kind", ["setup", "reset"])
def test_missing_fk_cascade_is_rejected(kind: str):
    ddl = _token_ddl(kind).replace(
        "REFERENCES public.retailers(id) ON DELETE CASCADE",
        "REFERENCES public.retailers(id)",
        1,
    )
    _validate_token_catalog_in_transaction(kind, ddl)


@pytest.mark.parametrize("kind", ["setup", "reset"])
def test_missing_primary_key_is_rejected(kind: str):
    ddl = _token_ddl(kind).replace(
        f"            CONSTRAINT pk_{_table_name(kind)} PRIMARY KEY (id),\n",
        "",
        1,
    )
    _validate_token_catalog_in_transaction(kind, ddl)


@pytest.mark.parametrize("kind", ["setup", "reset"])
def test_composite_primary_key_is_rejected(kind: str):
    ddl = _token_ddl(kind).replace(
        f"CONSTRAINT pk_{_table_name(kind)} PRIMARY KEY (id)",
        f"CONSTRAINT pk_{_table_name(kind)} PRIMARY KEY (id, retailer_id)",
        1,
    )
    _validate_token_catalog_in_transaction(kind, ddl)


@pytest.mark.parametrize("kind", ["setup", "reset"])
@pytest.mark.parametrize("column", ["id", "purpose", "created_at", "updated_at", "is_deleted"])
def test_missing_required_default_is_rejected(kind: str, column: str):
    purpose = "retailer_credential_setup" if kind == "setup" else "retailer_password_reset"
    replacements = {
        "id": ("id UUID DEFAULT gen_random_uuid(),", "id UUID,"),
        "purpose": (
            f"purpose VARCHAR(64) NOT NULL DEFAULT '{purpose}',",
            "purpose VARCHAR(64) NOT NULL,",
        ),
        "created_at": (
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(),",
            "created_at TIMESTAMPTZ NOT NULL,",
        ),
        "updated_at": (
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),",
            "updated_at TIMESTAMPTZ NOT NULL,",
        ),
        "is_deleted": (
            "is_deleted BOOLEAN NOT NULL DEFAULT FALSE,",
            "is_deleted BOOLEAN NOT NULL,",
        ),
    }
    old, new = replacements[column]
    ddl = _token_ddl(kind).replace(old, new, 1)
    _validate_token_catalog_in_transaction(kind, ddl)


@pytest.mark.parametrize("kind", ["setup", "reset"])
@pytest.mark.parametrize("column", ["id", "purpose", "created_at", "updated_at", "is_deleted"])
def test_wrong_required_default_is_rejected(kind: str, column: str):
    purpose = "retailer_credential_setup" if kind == "setup" else "retailer_password_reset"
    replacements = {
        "id": (
            "id UUID DEFAULT gen_random_uuid(),",
            "id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,",
        ),
        "purpose": (
            f"purpose VARCHAR(64) NOT NULL DEFAULT '{purpose}',",
            "purpose VARCHAR(64) NOT NULL DEFAULT 'wrong_purpose',",
        ),
        "created_at": (
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(),",
            "created_at TIMESTAMPTZ NOT NULL DEFAULT "
            "'2000-01-01 00:00:00+00'::timestamptz,",
        ),
        "updated_at": (
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),",
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT "
            "'2000-01-01 00:00:00+00'::timestamptz,",
        ),
        "is_deleted": (
            "is_deleted BOOLEAN NOT NULL DEFAULT FALSE,",
            "is_deleted BOOLEAN NOT NULL DEFAULT TRUE,",
        ),
    }
    old, new = replacements[column]
    ddl = _token_ddl(kind).replace(old, new, 1)
    _validate_token_catalog_in_transaction(kind, ddl)


def _catalog_payload(connection, tenant_schema: str) -> dict[str, list[tuple]]:
    public_tables = [
        "wholesalers",
        "tenant_registrations",
        "retailers",
        "wholesaler_retailer_bindings",
        "invitations",
        SETUP_TABLE,
        RESET_TABLE,
    ]
    payload: dict[str, list[tuple]] = {}
    payload["public_columns"] = connection.execute(
        text(
            "SELECT table_schema, table_name, column_name, data_type, is_nullable, "
            "character_maximum_length, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = ANY(:tables) "
            "ORDER BY table_schema, table_name, ordinal_position"
        ),
        {"tables": public_tables},
    ).fetchall()
    payload["public_constraints"] = connection.execute(
        text(
            "SELECT n.nspname, t.relname, c.conname, c.contype, pg_get_constraintdef(c.oid) "
            "FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname = 'public' AND t.relname = ANY(:tables) "
            "ORDER BY n.nspname, t.relname, c.conname"
        ),
        {"tables": public_tables},
    ).fetchall()
    payload["public_indexes"] = connection.execute(
        text(
            "SELECT schemaname, tablename, indexname, indexdef "
            "FROM pg_indexes WHERE schemaname = 'public' AND tablename = ANY(:tables) "
            "ORDER BY schemaname, tablename, indexname"
        ),
        {"tables": public_tables},
    ).fetchall()
    payload["public_counts"] = [
        (table, connection.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one())
        for table in public_tables
        if connection.execute(text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}).scalar()
    ]
    payload["tenant_columns"] = connection.execute(
        text(
            "SELECT table_schema, table_name, column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = :schema "
            "ORDER BY table_schema, table_name, ordinal_position"
        ),
        {"schema": tenant_schema},
    ).fetchall()
    payload["tenant_indexes"] = connection.execute(
        text(
            "SELECT schemaname, tablename, indexname, indexdef "
            "FROM pg_indexes WHERE schemaname = :schema "
            "ORDER BY schemaname, tablename, indexname"
        ),
        {"schema": tenant_schema},
    ).fetchall()
    payload["version"] = connection.execute(
        text("SELECT version_num FROM public.alembic_version ORDER BY version_num")
    ).fetchall()
    return payload


def _fingerprint(payload: dict[str, list[tuple]]) -> str:
    stable = json.dumps(payload, default=str, sort_keys=True)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _current_revision(connection) -> str:
    return connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one()


def _script_heads(config: Config) -> list[str]:
    return list(ScriptDirectory.from_config(config).get_heads())


def _seed_035_evidence_fixture(connection) -> str:
    wholesaler_id, schema = _create_registered_tenant(connection, prefix="r5rollback")
    retailer_id = uuid.uuid4()
    connection.execute(
        text(
            "INSERT INTO public.retailers (id, phone, name, email, is_deleted) "
            "VALUES (:id, :phone, 'Rollback Retailer', :email, false)"
        ),
        {
            "id": retailer_id,
            "phone": f"+27{uuid.uuid4().int % 10**8:08d}",
            "email": f"r5rollback_{uuid.uuid4().hex[:8]}@example.com",
        },
    )
    connection.execute(
        text(
            "INSERT INTO public.wholesaler_retailer_bindings ("
            "wholesaler_id, retailer_id, status, outstanding_balance, is_deleted"
            ") VALUES (:wholesaler_id, :retailer_id, 'active', 0, false)"
        ),
        {"wholesaler_id": wholesaler_id, "retailer_id": retailer_id},
    )
    connection.execute(
        text(
            "INSERT INTO public.invitations (code, status, wholesaler_id, retailer_phone, expires_at) "
            "VALUES (:code, 'active', :wholesaler_id, :phone, :expires_at)"
        ),
        {
            "code": f"R5{uuid.uuid4().hex[:12]}",
            "wholesaler_id": wholesaler_id,
            "phone": f"+27{uuid.uuid4().int % 10**8:08d}",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        },
    )
    connection.execute(
        text(
            f"CREATE TABLE public.{SETUP_TABLE} ("
            "id UUID PRIMARY KEY, token_hash TEXT)"
        )
    )
    return schema


def test_actual_alembic_035_to_036_failure_rolls_back_then_repaired_upgrade_noops():
    source_url = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source_url, "dc12r1r5") as db_url:
        config = _alembic_config(db_url)
        with _database_url_env(db_url):
            run_alembic_upgrade(config, REV_035)
            eng = _engine(db_url)
            try:
                with eng.begin() as connection:
                    tenant_schema = _seed_035_evidence_fixture(connection)
                    before_payload = _catalog_payload(connection, tenant_schema)
                    before_hash = _fingerprint(before_payload)
                    assert _current_revision(connection) == REV_035

                with pytest.raises(RuntimeError) as exc:
                    run_alembic_upgrade(config, "head")
                assert exc.value.__class__.__name__ == "PreflightFailure"

                with eng.connect() as connection:
                    after_failure_payload = _catalog_payload(connection, tenant_schema)
                    after_failure_hash = _fingerprint(after_failure_payload)
                    assert _current_revision(connection) == REV_035
                    assert after_failure_payload == before_payload
                    print(
                        "R5_ROLLBACK_FINGERPRINT "
                        f"before={before_hash} after_failure={after_failure_hash}"
                    )

                with eng.begin() as connection:
                    connection.execute(text(f"DROP TABLE public.{SETUP_TABLE}"))

                run_alembic_upgrade(config, "head")
                with eng.connect() as connection:
                    assert _current_revision(connection) == REV_036
                    assert _script_heads(config) == [REV_036]
                    before_noop_payload = _catalog_payload(connection, tenant_schema)
                    before_noop_hash = _fingerprint(before_noop_payload)

                run_alembic_upgrade(config, "head")
                with eng.connect() as connection:
                    assert _current_revision(connection) == REV_036
                    assert _script_heads(config) == [REV_036]
                    after_noop_payload = _catalog_payload(connection, tenant_schema)
                    after_noop_hash = _fingerprint(after_noop_payload)
                    assert after_noop_payload == before_noop_payload
                    print(
                        "R5_NOOP_FINGERPRINT "
                        f"before={before_noop_hash} after_second_upgrade={after_noop_hash}"
                    )
            finally:
                eng.dispose()
