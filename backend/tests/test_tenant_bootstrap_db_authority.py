"""MPANGO-TENANT-BOOTSTRAP-DB-AUTHORITY-R1 — V3 data-integrity suite.

Authorization: CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-2026-09-16.

Frozen architectural decision under test:
1. The migration authority owns the public schema and the shared security
   function ``public.prevent_ledger_modification()``.
2. The runtime role must never own or replace that function.
3. The runtime role stays non-superuser, NO CREATEDB, NO CREATEROLE.
4. Tenant bootstrap may create tenant-owned objects and triggers, but may
   only REFERENCE the existing migration-owned public function.
5. A missing/incompatible shared function or missing EXECUTE permission must
   fail closed without activating a partial tenant.

NO_DIRECT_BOOTSTRAP (mirrors the smtp-suite doctrine): this suite performs no
cluster-level DDL of its own.  Roles, databases, migrations (run AS the
migration authority) and the four deliberately-broken negative states are all
prepared by ``scripts/v3_tenant_bootstrap_db_authority_harness.py`` before
pytest starts; the suite's preparation gate is read-only and refuses to run
against an unprepared environment.  The tenant schema itself is created by the
PRODUCT's public onboarding path (verify-email provisioning) under test.

Scenario selection (process environment, one scenario per pytest process):
    MPANGO_DB_AUTHORITY_MANIFEST  path to the harness manifest JSON
    MPANGO_DB_AUTHORITY_SCENARIO  one of v3_ok / v3_nofunc / v3_badsig /
                                  v3_wrongown / v3_nopriv
Without a manifest the database-backed tests SKIP and only the static source
invariants run, so ordinary suite runs are unaffected.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import sys
import tokenize
import uuid
from typing import Any

from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
import pytest_asyncio
from asyncpg import InsufficientPrivilegeError
from sqlalchemy import text

MANIFEST_PATH = os.environ.get("MPANGO_DB_AUTHORITY_MANIFEST", "")
SCENARIO = os.environ.get("MPANGO_DB_AUTHORITY_SCENARIO", "")
MIGRATION_AUTHORITY_ROLE = os.environ.get(
    "MPANGO_MIGRATION_AUTHORITY_ROLE", "mpango_migrate"
)
RUNTIME_ROLE = os.environ.get("MPANGO_DB_APP_ROLE", "mpango_app")

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOTSTRAP_SCRIPT = os.path.join(
    BACKEND_DIR, "scripts", "bootstrap_tenant_schema.py"
)
GRANTS_SCRIPT = os.path.join(
    BACKEND_DIR, "scripts", "provision_runtime_db_roles.py"
)

SIGNUP_URL = "/api/v1/auth/signup"
VERIFY_URL = "/api/v1/auth/verify-email"
SETUP_URL = "/api/v1/auth/onboarding/setup-credential"
LOGIN_URL = "/api/v1/auth/login"
SELECT_URL = "/api/v1/auth/select-tenant"
ME_URL = "/api/v1/auth/me"

OWNER_PASSWORD = "V3AuthorityOwner!2026"  # pragma: allowlist secret

# Tenant objects required by the frozen provisioning contract.
REQUIRED_TENANT_TABLES = {
    "users", "roles", "permissions", "user_roles", "role_permissions",
    "catalog_products", "skus", "inventory_stocks", "inventory_movements",
    "inventory_reservations", "orders", "order_items", "payments",
    "ledger_entries", "retailer_prices", "import_runs", "intake_workspaces",
    "intake_uploads", "intake_product_rows", "intake_validation_issues",
    "payment_declarations", "receipt_sequences",
}
REQUIRED_REPORTING_VIEWS = ("rpt_receivables_summary", "rpt_cash_flow_daily")
MV_SALES_DAILY = "mv_sales_daily"
MV_SALES_DAILY_UQ = "idx_mv_sales_daily_u1"

LEDGER_GUARD_SIGNATURE = "public.prevent_ledger_modification()"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _manifest() -> dict[str, Any]:
    if not MANIFEST_PATH:
        pytest.skip("MPANGO_DB_AUTHORITY_MANIFEST not set")
    with open(MANIFEST_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _scenario(manifest: dict[str, Any], key: str) -> dict[str, Any]:
    entry = manifest["scenarios"].get(key)
    if entry is None:
        pytest.skip(f"scenario {key} not present in manifest")
    return entry


def _scenario_urls(entry: dict[str, Any]) -> tuple[str, str, str]:
    return entry["migrate_url"], entry["app_url"], entry["database"]


def _async_url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _only_scenario(key: str):
    return pytest.mark.skipif(
        SCENARIO != key,
        reason=f"test targets scenario {key} (active: {SCENARIO or 'none'})",
    )


def _executable_source_text(path: str) -> str:
    """Source with docstrings and comments removed.

    Prose may legitimately NAME forbidden SQL (e.g. "this script must never
    issue ALTER SCHEMA public OWNER ..."); only executable text is scanned so
    such prose is not a false positive while a real statement always is.
    """
    with open(path, encoding="utf-8") as handle:
        source = handle.read()

    tree = ast.parse(source)
    docstring_spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstring_spans.append((first.lineno, first.end_lineno))

    lines = source.splitlines(keepends=True)
    kept = [
        line for index, line in enumerate(lines, start=1)
        if not any(start <= index <= end for start, end in docstring_spans)
    ]
    remainder = "".join(kept)

    tokens = tokenize.generate_tokens(io.StringIO(remainder).readline)
    parts = [
        token.string for token in tokens
        if token.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                              tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING, tokenize.ENDMARKER)
    ]
    return "\n".join(parts)


def _normalized(path: str) -> str:
    return " ".join(_executable_source_text(path).lower().split())


def _relkind(value: object) -> str:
    """pg char fields arrive as bytes through asyncpg."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode()
    return str(value)


async def _fetch_rows(db, sql: str, params: dict | None = None) -> list[dict]:
    result = await db.execute(text(sql), params or {})
    return [dict(row) for row in result.mappings()]


async def _guard_identity(db) -> dict[str, Any]:
    """Read-only identity of the migration-owned guard function."""
    rows = await _fetch_rows(
        db,
        """
        SELECT p.oid::bigint AS oid,
               pg_get_userbyid(p.proowner) AS owner_name,
               format_type(p.prorettype, NULL) AS return_type,
               pg_get_function_identity_arguments(p.oid) AS identity_arguments,
               l.lanname AS language_name,
               n.nspname AS function_schema,
               pg_get_functiondef(p.oid) AS definition
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_language l ON l.oid = p.prolang
        WHERE n.nspname = 'public'
          AND p.proname = 'prevent_ledger_modification'
        """,
    )
    assert len(rows) == 1, (
        f"expected exactly one guard function, got {len(rows)}"
    )
    identity = rows[0]
    identity["definition_sha256"] = hashlib.sha256(
        identity["definition"].encode("utf-8")
    ).hexdigest()
    return identity


async def _connect(url: str) -> asyncpg.Connection:
    return await asyncpg.connect(url)


def _app_engine(url: str):
    from sqlalchemy.ext.asyncio import create_async_engine

    return create_async_engine(_async_url(url))


# ---------------------------------------------------------------------------
# static source invariants (always run, no database)
# ---------------------------------------------------------------------------


def test_bootstrap_script_never_replaces_or_reowns_public_guard():
    """Frozen decisions 2/4/5: the runtime bootstrap must only REFERENCE the
    migration-owned guard function — never replace, re-own or blanket-grant."""
    source = _normalized(BOOTSTRAP_SCRIPT)
    assert (
        "create or replace function public.prevent_ledger_modification"
        not in source
    )
    assert "alter schema" not in source
    assert "owner to" not in source
    assert "grant all" not in source
    assert "alter function" not in source
    # The trigger must still reference the migration-owned function.
    assert "execute function public.prevent_ledger_modification()" in source
    # The precondition must exist and run before any tenant DDL.
    assert "_assert_ledger_guard_function_authority" in source
    precondition_position = source.index(
        "await _assert_ledger_guard_function_authority"
    )
    create_schema_position = source.index("create schema if not exists")
    assert precondition_position < create_schema_position, (
        "the ledger-guard authority precondition must run before CREATE SCHEMA "
        "so a refusal leaves zero partial tenant"
    )


def test_bootstrap_script_keeps_fail_closed_precondition_semantics():
    source = _normalized(BOOTSTRAP_SCRIPT)
    for fragment in (
        "to_regprocedure",
        "pg_get_userbyid",
        "has_function_privilege",
        "ledgerguardauthorityerror",
        "mpango_migration_authority_role",
    ):
        assert fragment in source, f"missing fail-closed element: {fragment}"


def test_grants_script_declares_only_minimum_runtime_grants():
    """Frozen decisions 3/5, executable-contract form: the declared statement
    vocabulary must contain the minimum grants and no ownership transfer,
    public-schema rewrite or blanket grant."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "v3_provision_runtime_db_roles", GRANTS_SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for forbidden in (
        "alter schema", "owner to", "grant all", "alter function",
        "with admin option", "with grant option",
    ):
        assert forbidden in module.FORBIDDEN_SQL_FRAGMENTS
        for statement in (
            module.MINIMUM_GRANT_STATEMENTS
            + module.DATABASE_SCOPE_GRANT_TEMPLATES
        ):
            collapsed = " ".join(statement.lower().split())
            assert forbidden not in collapsed, (
                f"grants script declares forbidden SQL {forbidden!r}: "
                f"{statement!r}"
            )

    collapsed_statements = [
        " ".join(statement.lower().split())
        for statement in (
            module.MINIMUM_GRANT_STATEMENTS
            + module.DATABASE_SCOPE_GRANT_TEMPLATES
        )
    ]
    for required in (
        "grant usage on schema public",
        "grant create on database",
        "grant execute on function public.prevent_ledger_modification()",
        "grant select, insert, update, delete on all tables in schema public",
    ):
        assert any(
            statement.startswith(required) for statement in collapsed_statements
        ), f"missing minimum grant: {required}"

    # The refusal guard itself must be live: it refuses a forbidden statement.
    try:
        module._assert_sanctioned_sql(
            'ALTER SCHEMA public OWNER TO "mpango_app"'
        )
    except RuntimeError:
        pass
    else:
        pytest.fail(
            "provision_runtime_db_roles._assert_sanctioned_sql accepted a "
            "forbidden ownership-transfer statement"
        )

    role_ddl = module.RUNTIME_ROLE_DDL_TEMPLATE
    for attribute in ("nosuperuser", "nocreatedb", "nocreaterole"):
        assert attribute in role_ddl.lower(), (
            f"runtime role DDL must enforce {attribute}"
        )
    migration_ddl = module.MIGRATION_AUTHORITY_ROLE_DDL_TEMPLATE.lower()
    for attribute in ("nosuperuser", "nocreatedb"):
        assert attribute in migration_ddl, (
            f"migration authority DDL must enforce {attribute}"
        )


# ---------------------------------------------------------------------------
# R1-R1 static invariants (always run, no database)
# ---------------------------------------------------------------------------


def test_static_owner_fallback_removed_and_authority_derived_from_db_owner():
    """R1-R1 fix 3: the bootstrap precondition must derive the migration
    authority from the database owner (catalog fact) and must contain NO
    connected-role fallback; the single-role topology must be refused."""
    source = _normalized(BOOTSTRAP_SCRIPT)
    assert "database_owner" in source, (
        "authority must be derived from the database owner (pg_database)"
    )
    assert " or connected_role" not in source, (
        "connected-role owner fallback must not exist"
    )
    assert "single-role topology" in source, (
        "the single-role (runtime == authority) topology must be explicitly "
        "refused"
    )
    assert "pg_has_role" in source, (
        "membership/SET ROLE escalation path must be checked"
    )


def test_static_verify_is_pure_catalog_read_only():
    """R1-R1 fix 1: --verify must be strictly read-only — no DDL statement
    and no transactional probe anywhere inside Provisioner.verify."""
    import ast

    with open(GRANTS_SCRIPT, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    verify_functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "verify"
    ]
    assert verify_functions, "Provisioner.verify not found"
    ddl_pattern = re.compile(r"^\s*(create|alter|drop|grant|revoke)\b", re.I)
    for function in verify_functions:
        body = list(function.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]  # skip the docstring
        for node in ast.walk(ast.Module(body=body, type_ignores=[])):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not ddl_pattern.match(node.value), (
                    f"verify() contains DDL-looking string: {node.value[:60]!r}"
                )
            if isinstance(node, ast.Attribute) and node.attr == "transaction":
                pytest.fail("verify() must not open transactions (no DDL probe)")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "execute", (
                    "verify() must not call raw execute()"
                )


def test_static_identifier_validation_wired_in_all_modes():
    """R1-R1 fix 5: strict allowlist identifier validation must run for the
    migration role, the runtime role and the database in Provisioner.__init__
    (every mode), and the bootstrap script must validate the tenant schema
    identifier before interpolating it."""
    with open(GRANTS_SCRIPT, encoding="utf-8") as handle:
        source = handle.read()
    for fragment in (
        "validate_identifier(migrate_role",
        "validate_identifier(app_role",
        "validate_identifier(database",
        "_SAFE_IDENTIFIER_RE",
    ):
        assert fragment in source, f"missing identifier-validation element: {fragment}"
    # Reject quotes/semicolons/comments by construction (allowlist).
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "v3r1_provision_check", GRANTS_SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for malicious in (
        'x" ; DROP FUNCTION public.prevent_ledger_modification(); --',
        "x'; --",
        "a b",
        "a-b",
        "UPPER",
    ):
        with pytest.raises(ValueError):
            module.validate_identifier(malicious, "probe")

    bootstrap_source = _normalized(BOOTSTRAP_SCRIPT)
    assert "fullmatch" in bootstrap_source and "a-za-z0-9_" in bootstrap_source.replace(" ", ""), (
        "bootstrap must allowlist-validate the tenant schema identifier"
    )


def test_static_cluster_binding_precedes_writes():
    """R1-R1 fix 6: the binding preflight must run inside both write modes
    before any role/database/grant statement is rendered."""
    with open(GRANTS_SCRIPT, encoding="utf-8") as handle:
        source = handle.read()

    def _method_segment(name: str) -> str:
        start = source.index(f"async def {name}")
        next_def = re.search(r"\n    async def |\n\ndef |\n\nclass ", source[start:])
        end = start + (next_def.start() if next_def else len(source))
        return source[start:end]

    provision_segment = _method_segment("create_roles_and_database")
    assert "_assert_cluster_binding" in provision_segment
    assert provision_segment.index("_assert_cluster_binding") < (
        provision_segment.index("_ensure_role")
    ), "binding must precede role creation"

    grants_segment = _method_segment("apply_minimum_grants")
    assert "_assert_cluster_binding" in grants_segment
    assert grants_segment.index("_assert_cluster_binding") < (
        grants_segment.index("render_minimum_grant_statements")
    ), "binding must precede grant rendering"


# ---------------------------------------------------------------------------
# read-only preparation gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v3_preparation_gate_authority_topology_is_wired():
    manifest = _manifest()
    migrate_url, app_url, database = _scenario_urls(
        _scenario(manifest, manifest["active_scenario"])
    )

    admin = await _connect(manifest["admin_url"])
    try:
        # The RUNTIME role carries the frozen decision-3 attributes strictly.
        # The migration authority may hold CREATEROLE (migration 011 creates
        # reporting_role) but stays NOSUPERUSER and NOCREATEDB.
        for role, allow_createrole in (
            (MIGRATION_AUTHORITY_ROLE, True),
            (RUNTIME_ROLE, False),
        ):
            row = await admin.fetchrow(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
                "rolcanlogin FROM pg_roles WHERE rolname = $1",
                role,
            )
            assert row is not None, f"role {role} is missing"
            assert not row["rolsuper"], f"{role} must be NOSUPERUSER"
            assert not row["rolcreatedb"], f"{role} must be NOCREATEDB"
            assert not row["rolreplication"], f"{role} must be NOREPLICATION"
            if not allow_createrole:
                assert not row["rolcreaterole"], (
                    f"{role} must be NOCREATEROLE"
                )
            assert row["rolcanlogin"], f"{role} must be able to login"
        db_row = await admin.fetchrow(
            "SELECT pg_get_userbyid(datdba) AS owner FROM pg_database "
            "WHERE datname = $1",
            database,
        )
        assert db_row is not None
        assert db_row["owner"] == MIGRATION_AUTHORITY_ROLE, (
            "the database (and with it the public schema on PG15+) must be "
            "owned by the migration authority"
        )
        schema_owner_row = await admin.fetchrow(
            "SELECT pg_get_userbyid(nspowner) AS owner FROM pg_namespace "
            "WHERE nspname = 'public'"
        )
        # PG15+/PG16: the public schema is owned by the pseudo-role
        # pg_database_owner, whose implicit member is the database owner.
        assert (
            schema_owner_row["owner"] == MIGRATION_AUTHORITY_ROLE
            or (
                schema_owner_row["owner"] == "pg_database_owner"
                and db_row["owner"] == MIGRATION_AUTHORITY_ROLE
            )
        ), "schema public must be owned by the migration authority"
    finally:
        await admin.close()

    migrate = await _connect(migrate_url)
    try:
        version_rows = await migrate.fetch(
            "SELECT version_num FROM public.alembic_version"
        )
        assert version_rows, "public.alembic_version is empty: migrations not run"
        if manifest["active_scenario"] != "v3_verify_wrongown":
            # (the wrong-owner counterexample database deliberately has the
            # runtime role owning the guard in public)
            app_owned = await migrate.fetchval(
                "SELECT count(*) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' "
                "AND pg_get_userbyid(c.relowner) = $1",
                RUNTIME_ROLE,
            )
            assert not app_owned, "the runtime role must own nothing in public"
        # R1-R1 fix 4: no SET ROLE escalation path from runtime to authority,
        # and the runtime role has no CREATE in schema public.
        member = await migrate.fetchval(
            "SELECT pg_has_role($1, $2, 'MEMBER') OR pg_has_role($1, $2, 'USAGE')",
            RUNTIME_ROLE, MIGRATION_AUTHORITY_ROLE,
        )
        assert not member, (
            "runtime role must not be a member of the migration authority "
            "(SET ROLE escalation path)"
        )
        app_create_public = await migrate.fetchval(
            "SELECT has_schema_privilege($1, 'public', 'CREATE')",
            RUNTIME_ROLE,
        )
        assert not app_create_public, (
            "runtime role must not hold CREATE on schema public "
            "(DROP+CREATE substitution path)"
        )
    finally:
        await migrate.close()

    app = await _connect(app_url)
    try:
        assert await app.fetchval("SELECT current_user") == RUNTIME_ROLE
        # R1-R1 fix 4: runtime differs from the derived authority.
        assert await app.fetchval("SELECT current_user") != (
            await app.fetchval(
                "SELECT pg_get_userbyid(datdba) FROM pg_database "
                "WHERE datname = current_database()"
            )
        ), "single-role topology: runtime connection binds the authority"
    finally:
        await app.close()


@_only_scenario("v3_ok")
@pytest.mark.asyncio
async def test_v3_ok_preparation_gate_guard_function_is_intact():
    """In the authoritative topology the shared guard must be exactly intact
    and executable by the runtime role before any lifecycle runs."""
    manifest = _manifest()
    migrate_url, app_url, database = _scenario_urls(_scenario(manifest, "v3_ok"))
    migrate_engine = _app_engine(migrate_url)
    try:
        async with migrate_engine.connect() as conn:
            guard = await _guard_identity(conn)
    finally:
        await migrate_engine.dispose()
    assert guard["owner_name"] == MIGRATION_AUTHORITY_ROLE
    assert guard["return_type"] == "trigger"
    assert guard["identity_arguments"].strip() == ""
    assert guard["language_name"] == "plpgsql"
    app = await _connect(app_url)
    try:
        can_execute = await app.fetchval(
            "SELECT has_function_privilege(current_user, $1, 'EXECUTE')",
            LEDGER_GUARD_SIGNATURE,
        )
        assert can_execute, "runtime role must hold EXECUTE on the guard"
        can_create = await app.fetchval(
            "SELECT has_database_privilege(current_user, $1, 'CREATE')",
            database,
        )
        assert can_create, (
            "runtime role must hold CREATE on the database to create tenant "
            "schemas"
        )
    finally:
        await app.close()


# ---------------------------------------------------------------------------
# happy path (scenario v3_ok) — the official public lifecycle as runtime role
# ---------------------------------------------------------------------------


async def _official_lifecycle(app_url: str) -> dict[str, Any]:
    """Drive signup -> mail -> verify -> setup -> login -> select-tenant.

    Uses the production ASGI app with the REAL JwtAuthStrategy (the reviewed
    dual-layer swap from the r3r1 suite).  The app's own session dependency
    and the provisioning service connect with ``settings.DATABASE_URL`` —
    i.e. the RUNTIME ROLE url of the active scenario process.
    """
    from api.app import app
    from auth.strategies.jwt import JwtAuthStrategy
    from httpx import ASGITransport, AsyncClient
    from services.email_delivery import (
        clear_dev_email_deliveries,
        get_dev_email_deliveries,
    )

    def _find_auth_middleware(node: Any) -> Any | None:
        while node is not None:
            cls = getattr(node, "__class__", None)
            if cls is not None and cls.__name__ == "AuthenticationMiddleware":
                return node
            node = getattr(node, "app", None)
        return None

    swapped: list[tuple[object, str, object]] = []
    jwt_strategy = JwtAuthStrategy()
    mw = _find_auth_middleware(app)
    if mw is not None:
        swapped.append((mw, "_strategy", mw._strategy))
        mw._strategy = jwt_strategy
    for entry in app.user_middleware:
        if entry.cls.__name__ == "AuthenticationMiddleware":
            swapped.append(
                (entry.kwargs, "strategy", entry.kwargs.get("strategy"))
            )
            entry.kwargs["strategy"] = jwt_strategy

    clear_dev_email_deliveries()
    email = f"v3ok_{uuid.uuid4().hex[:10]}@authority.example"
    result: dict[str, Any] = {"email": email, "http": {}}
    try:
        def _client() -> AsyncClient:
            return AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://testserver",
            )

        async with _client() as client:
            response = await client.post(
                SIGNUP_URL,
                json={
                    "companyName": "V3 Authority Wholesaler",
                    "country": "KE",
                    "email": email,
                    "phone": "+254700000000",
                    "businessType": "wholesale",
                },
            )
            result["http"]["signup"] = response.status_code
            assert response.status_code == 202, response.text

        verification_token = [
            d for d in get_dev_email_deliveries(email)
            if d.purpose == "email_verification"
        ][0].token
        result["verification_mail_captured"] = True

        # verify-email triggers the provisioning path:
        # TenantProvisioningService calls scripts.bootstrap_tenant_schema
        # .bootstrap AS the runtime role.
        async with _client() as client:
            response = await client.post(
                VERIFY_URL, json={"token": verification_token}
            )
            result["http"]["verify"] = response.status_code
            assert response.status_code == 200, response.text

        setup_token = [
            d for d in get_dev_email_deliveries(email)
            if d.purpose == "owner_setup"
        ][0].token
        result["setup_mail_captured"] = True

        async with _client() as client:
            response = await client.post(
                SETUP_URL,
                json={"setupToken": setup_token, "password": OWNER_PASSWORD},
            )
            result["http"]["setup"] = response.status_code
            assert response.status_code == 200, response.text

        async with _client() as client:
            response = await client.post(
                LOGIN_URL, json={"email": email, "password": OWNER_PASSWORD}
            )
            result["http"]["login"] = response.status_code
            assert response.status_code == 200, response.text
            login_data = response.json()["data"]
            tenants = login_data["available_tenants"]
            assert tenants, "identity login must list the verified tenant"
            result["tenant_id"] = tenants[0]["id"]

            response = await client.post(
                SELECT_URL,
                json={"tenant_id": result["tenant_id"]},
                headers={
                    "Authorization": f"Bearer {login_data['access_token']}"
                },
            )
            result["http"]["select_tenant"] = response.status_code
            assert response.status_code == 200, response.text
            select_data = response.json()["data"]
            result["tenant_schema"] = select_data["tenant_schema"]
            result["context_token"] = select_data["access_token"]

        async with _client() as client:
            response = await client.get(
                ME_URL,
                headers={
                    "Authorization": f"Bearer {result['context_token']}"
                },
            )
            result["http"]["me"] = response.status_code
            assert response.status_code == 200, response.text
            assert (
                response.json()["data"]["tenant_schema"]
                == result["tenant_schema"]
            )
        return result
    finally:
        for owner, attribute, original in reversed(swapped):
            if isinstance(owner, dict):
                owner[attribute] = original
            else:
                setattr(owner, attribute, original)
        clear_dev_email_deliveries()


@pytest_asyncio.fixture(scope="module")
async def _provisioned():
    manifest = _manifest()
    migrate_url, app_url, database = _scenario_urls(_scenario(manifest, "v3_ok"))
    app_engine = _app_engine(app_url)
    migrate_engine = _app_engine(migrate_url)
    state: dict[str, Any] = {"database": database}

    try:
        async with migrate_engine.connect() as conn:
            state["guard_before"] = await _guard_identity(conn)
        state["lifecycle"] = await _official_lifecycle(app_url)
        yield state
    finally:
        await app_engine.dispose()
        await migrate_engine.dispose()


@_only_scenario("v3_ok")
@pytest.mark.asyncio
async def test_r1_public_lifecycle_activates_tenant_as_runtime_role(
    _provisioned,
):
    lifecycle = _provisioned["lifecycle"]
    assert lifecycle["verification_mail_captured"] is True
    assert lifecycle["setup_mail_captured"] is True
    assert {
        "signup": 202,
        "verify": 200,
        "setup": 200,
        "login": 200,
        "select_tenant": 200,
        "me": 200,
    } == lifecycle["http"], lifecycle["http"]
    assert lifecycle["tenant_schema"].startswith("t_")

    manifest = _manifest()
    _, app_url, _ = _scenario_urls(_scenario(manifest, "v3_ok"))
    app_engine = _app_engine(app_url)
    try:
        async with app_engine.connect() as conn:
            rows = await _fetch_rows(
                conn,
                "SELECT status FROM public.tenant_registrations "
                "WHERE owner_email = :email",
                {"email": lifecycle["email"]},
            )
            assert rows and rows[0]["status"] == "active"
            rows = await _fetch_rows(
                conn,
                "SELECT status FROM public.wholesalers WHERE contact = :email",
                {"email": lifecycle["email"]},
            )
            assert rows and rows[0]["status"] == "active"
    finally:
        await app_engine.dispose()


@_only_scenario("v3_ok")
@pytest.mark.asyncio
async def test_r2_tenant_contains_required_tables_two_views_mv_and_unique_index(
    _provisioned,
):
    schema = _provisioned["lifecycle"]["tenant_schema"]
    manifest = _manifest()
    _, app_url, _ = _scenario_urls(_scenario(manifest, "v3_ok"))
    app_engine = _app_engine(app_url)
    try:
        async with app_engine.connect() as conn:
            rows = await _fetch_rows(
                conn,
                "SELECT c.relname, c.relkind FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relkind IN ('r', 'v', 'm')",
                {"schema": schema},
            )
            grants = await _fetch_rows(
                conn,
                "SELECT has_table_privilege('reporting_role', :v1, 'SELECT') AS v1, "
                "has_table_privilege('reporting_role', :v2, 'SELECT') AS v2, "
                "has_table_privilege('reporting_role', :mv, 'SELECT') AS mv",
                {"v1": f"{schema}.{REQUIRED_REPORTING_VIEWS[0]}",
                 "v2": f"{schema}.{REQUIRED_REPORTING_VIEWS[1]}",
                 "mv": f"{schema}.{MV_SALES_DAILY}"},
            )
            indexes = await _fetch_rows(
                conn,
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = :schema AND indexname = :name",
                {"schema": schema, "name": MV_SALES_DAILY_UQ},
            )
    finally:
        await app_engine.dispose()

    tables = {
        r["relname"] for r in rows if _relkind(r["relkind"]) == "r"
    }
    views = {r["relname"] for r in rows if _relkind(r["relkind"]) == "v"}
    matviews = {r["relname"] for r in rows if _relkind(r["relkind"]) == "m"}
    missing = REQUIRED_TENANT_TABLES - tables
    assert not missing, f"tenant is missing required tables: {sorted(missing)}"
    for view in REQUIRED_REPORTING_VIEWS:
        assert view in views, f"reporting view {view} missing in tenant"
    assert MV_SALES_DAILY in matviews, "mv_sales_daily missing in tenant"
    assert grants[0]["v1"] and grants[0]["v2"] and grants[0]["mv"], (
        "reporting_role must hold SELECT on both reporting views and the "
        "materialized view"
    )
    assert indexes, f"unique index {MV_SALES_DAILY_UQ} missing on mv_sales_daily"
    assert "UNIQUE INDEX" in indexes[0]["indexdef"].upper()
    assert "transaction_date" in indexes[0]["indexdef"]


@_only_scenario("v3_ok")
@pytest.mark.asyncio
async def test_r3_guard_owner_and_definition_preserved_across_tenant_creation(
    _provisioned,
):
    """Frozen decisions 1/2/4: creating a tenant must leave the migration-owned
    guard function byte/semantic-identical, including its catalog identity."""
    before = _provisioned["guard_before"]
    manifest = _manifest()
    migrate_url, _, _ = _scenario_urls(_scenario(manifest, "v3_ok"))
    migrate_engine = _app_engine(migrate_url)
    try:
        async with migrate_engine.connect() as conn:
            after = await _guard_identity(conn)
    finally:
        await migrate_engine.dispose()
    assert after["oid"] == before["oid"], (
        "guard function oid changed: the function was dropped/recreated or "
        "replaced during tenant creation"
    )
    assert after["owner_name"] == before["owner_name"] == MIGRATION_AUTHORITY_ROLE
    assert after["definition"] == before["definition"]
    assert after["definition_sha256"] == before["definition_sha256"]
    assert after["return_type"] == "trigger"
    assert after["identity_arguments"].strip() == ""
    assert after["language_name"] == "plpgsql"


@_only_scenario("v3_ok")
@pytest.mark.asyncio
async def test_r4_ledger_update_and_delete_blocked_by_migration_owned_guard(
    _provisioned,
):
    """Frozen decision 4 in action: the tenant trigger references the shared
    migration-owned function, whose message proves which body executes.
    Each probe runs in its own transaction: a refused statement aborts its
    transaction, so sharing one would cascade 'transaction is aborted'."""
    schema = _provisioned["lifecycle"]["tenant_schema"]
    manifest = _manifest()
    _, app_url, _ = _scenario_urls(_scenario(manifest, "v3_ok"))
    app_engine = _app_engine(app_url)
    try:
        async with app_engine.connect() as conn:
            triggers = await _fetch_rows(
                conn,
                "SELECT t.tgname, t.tgenabled, "
                "pg_get_triggerdef(t.oid) AS def, "
                "p.proname AS func_name, pn.nspname AS func_schema, "
                "pg_get_userbyid(p.proowner) AS func_owner "
                "FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_proc p ON p.oid = t.tgfoid "
                "JOIN pg_namespace pn ON pn.oid = p.pronamespace "
                "WHERE n.nspname = :schema AND c.relname = 'ledger_entries' "
                "AND NOT t.tgisinternal",
                {"schema": schema},
            )
            # Rendering-independent proof: the trigger must fire THE
            # migration-owned public guard function (by catalog identity,
            # not by name text).
            guard_triggers = [
                t for t in triggers
                if t["func_name"] == "prevent_ledger_modification"
                and t["func_schema"] == "public"
            ]
            assert guard_triggers, (
                f"no trigger on {schema}.ledger_entries fires the shared "
                "public.prevent_ledger_modification() function"
            )
            assert all(
                t["func_owner"] == MIGRATION_AUTHORITY_ROLE
                for t in guard_triggers
            ), "the guard function fired by the tenant trigger is not "
            "migration-owned"
            assert any(
                _relkind(t["tgenabled"]) == "O" for t in guard_triggers
            ), "guard trigger exists but is disabled"

        # INSERT (allowed — the ledger is write-only) in its own transaction.
        async with app_engine.begin() as conn:
            entry_id = (
                await conn.execute(
                    text(
                        f'INSERT INTO "{schema}".ledger_entries '
                        "(account_type, amount, reference_type, reference_id, "
                        "description) VALUES ('cash', 100, 'v3_proof', "
                        "gen_random_uuid(), 'guard proof') RETURNING id"
                    )
                )
            ).scalar()
            assert entry_id is not None

        for statement, operation in (
            (
                f'UPDATE "{schema}".ledger_entries SET amount = 1 '
                "WHERE id = :id",
                "UPDATE",
            ),
            (
                f'DELETE FROM "{schema}".ledger_entries WHERE id = :id',
                "DELETE",
            ),
        ):
            async with app_engine.begin() as conn:
                try:
                    await conn.execute(text(statement), {"id": entry_id})
                except Exception as exc:  # noqa: BLE001 - any refusal counts
                    assert "Ledger entries are immutable" in str(exc), (
                        f"{operation} was refused with an unexpected error: "
                        f"{exc}"
                    )
                else:
                    pytest.fail(
                        f"{operation} on {schema}.ledger_entries was NOT "
                        "blocked by the ledger guard trigger"
                    )
    finally:
        await app_engine.dispose()


@_only_scenario("v3_ok")
@pytest.mark.asyncio
async def test_r5_runtime_role_cannot_replace_reown_or_escalate(_provisioned):
    """Frozen decisions 2/3 enforced at the database level, probed from a
    live runtime-role connection; mutating probes roll back."""
    manifest = _manifest()
    migrate_url, app_url, database = _scenario_urls(
        _scenario(manifest, "v3_ok")
    )
    guard_before = _provisioned["guard_before"]

    conn = await _connect(app_url)
    try:
        async def _refused_in_rolled_back_transaction(sql: str) -> bool:
            transaction = conn.transaction()
            await transaction.start()
            try:
                await conn.execute(sql)
            except InsufficientPrivilegeError:
                return True
            finally:
                await transaction.rollback()
            return False

        assert await _refused_in_rolled_back_transaction(
            f"CREATE OR REPLACE FUNCTION {LEDGER_GUARD_SIGNATURE} "
            "RETURNS TRIGGER AS $$ BEGIN RETURN OLD; END; $$ LANGUAGE plpgsql"
        ), "runtime role was able to REPLACE the migration-owned guard"
        assert await _refused_in_rolled_back_transaction(
            f"ALTER FUNCTION {LEDGER_GUARD_SIGNATURE} OWNER TO {RUNTIME_ROLE}"
        ), "runtime role was able to re-own the migration-owned guard"
        assert await _refused_in_rolled_back_transaction(
            f"ALTER SCHEMA public OWNER TO {RUNTIME_ROLE}"
        ), "runtime role was able to re-own schema public"
        assert await _refused_in_rolled_back_transaction(
            f"CREATE ROLE {RUNTIME_ROLE}_v3_probe LOGIN"
        ), "runtime role was able to create a role (NOCREATEROLE violated)"
    finally:
        await conn.close()

    # CREATE DATABASE cannot run inside a transaction block — probe bare; a
    # NOCREATEDB runtime role must be refused outright.
    conn = await _connect(app_url)
    try:
        refused = False
        try:
            await conn.execute(f'CREATE DATABASE "{database}_v3probe"')
        except InsufficientPrivilegeError:
            refused = True
        else:
            try:
                await conn.execute(f'DROP DATABASE "{database}_v3probe"')
            except InsufficientPrivilegeError:
                pass
        assert refused, (
            "runtime role was able to create a database (NOCREATEDB violated)"
        )
    finally:
        await conn.close()

    migrate_engine = _app_engine(migrate_url)
    try:
        async with migrate_engine.connect() as db:
            guard_after = await _guard_identity(db)
    finally:
        await migrate_engine.dispose()
    assert guard_after["oid"] == guard_before["oid"]
    assert guard_after["definition"] == guard_before["definition"]
    assert guard_after["owner_name"] == MIGRATION_AUTHORITY_ROLE


# ---------------------------------------------------------------------------
# negative scenarios — fail closed with zero active partial tenant
# ---------------------------------------------------------------------------


async def _negative_lifecycle_assertions(app_url: str) -> dict[str, Any]:
    """Run signup->verify over the broken-authority database and prove that
    nothing was activated and no partial tenant remains."""
    from api.app import app
    from httpx import ASGITransport, AsyncClient
    from services.email_delivery import (
        clear_dev_email_deliveries,
        get_dev_email_deliveries,
    )

    clear_dev_email_deliveries()
    email = f"v3neg_{uuid.uuid4().hex[:10]}@authority.example"
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                SIGNUP_URL,
                json={
                    "companyName": "V3 Negative Wholesaler",
                    "country": "KE",
                    "email": email,
                    "phone": "+254700000000",
                    "businessType": "wholesale",
                },
            )
            assert response.status_code == 202, response.text
            verification_token = [
                d for d in get_dev_email_deliveries(email)
                if d.purpose == "email_verification"
            ][0].token
            response = await client.post(
                VERIFY_URL, json={"token": verification_token}
            )
            verify_status = response.status_code
            verify_code = response.json().get("detail", {}).get("code")

        # verify-email must fail closed at the public boundary...
        assert verify_status == 503, (
            f"verify-email answered {verify_status} instead of the "
            "fail-closed 503"
        )
        assert verify_code == "ONBOARDING_ORCHESTRATION_FAILED", verify_code
    finally:
        clear_dev_email_deliveries()

    app_engine = _app_engine(app_url)
    proof: dict[str, Any] = {"email": email, "verify_status": verify_status}
    try:
        async with app_engine.connect() as conn:
            registrations = await _fetch_rows(
                conn,
                "SELECT status, wholesaler_id, tenant_schema "
                "FROM public.tenant_registrations WHERE owner_email = :email",
                {"email": email},
            )
            wholesalers = await _fetch_rows(
                conn,
                "SELECT status FROM public.wholesalers WHERE contact = :email",
                {"email": email},
            )
    finally:
        await app_engine.dispose()

    assert registrations, "registration row vanished (unexpected state)"
    status = registrations[0]["status"]
    assert status != "active", "a partial tenant was ACTIVATED"
    # On bootstrap refusal the whole verify-email transaction rolls back, so
    # the registration stays pending (token unconsumed) — anything but
    # 'active' proves zero activation.
    assert status in {
        "pending_email_verification", "email_verified",
        "provisioning", "failed",
    }, status
    assert registrations[0]["wholesaler_id"] is None
    assert not wholesalers, "a wholesaler row was activated for a broken signup"
    return proof


async def _direct_bootstrap_refusal(
    app_url: str, scenario_key: str, message_fragment: str
) -> None:
    """Unit-level: bootstrap() itself must raise the fail-closed error and
    leave zero tenant objects behind."""
    from scripts.bootstrap_tenant_schema import (
        LedgerGuardAuthorityError,
        bootstrap,
    )

    tenant_schema = f"t_v3direct_{uuid.uuid4().hex[:12]}"
    with pytest.raises(LedgerGuardAuthorityError) as excinfo:
        await bootstrap(tenant_schema, app_url)
    message = str(excinfo.value)
    assert "Bootstrap precondition failed" in message
    assert message_fragment in message, message

    app_engine = _app_engine(app_url)
    try:
        async with app_engine.connect() as conn:
            rows = await _fetch_rows(
                conn,
                "SELECT 1 FROM information_schema.schemata "
                "WHERE schema_name = :s OR schema_name LIKE 't\\_v3direct%' "
                "ESCAPE '\\'",
                {"s": tenant_schema},
            )
    finally:
        await app_engine.dispose()
    assert not rows, (
        f"{scenario_key}: bootstrap refusal still left a partial tenant schema"
    )


async def _assert_induced_state(scenario_key: str, migrate_url: str) -> None:
    """Prove the harness actually produced the broken authority state."""
    migrate = await _connect(migrate_url)
    try:
        rows = await migrate.fetch(
            "SELECT pg_get_userbyid(p.proowner) AS owner, "
            "format_type(p.prorettype, NULL) AS return_type, "
            "has_function_privilege($1, p.oid, 'EXECUTE') AS app_can_execute "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' "
            "AND p.proname = 'prevent_ledger_modification'",
            RUNTIME_ROLE,
        )
    finally:
        await migrate.close()
    if scenario_key == "v3_nofunc":
        assert not rows, "v3_nofunc: the guard function was not dropped"
    elif scenario_key == "v3_badsig":
        assert rows and rows[0]["return_type"] != "trigger", (
            "v3_badsig: the guard function was not replaced by an "
            "incompatible signature"
        )
    elif scenario_key == "v3_wrongown":
        assert rows and rows[0]["owner"] == RUNTIME_ROLE, (
            "v3_wrongown: the guard function was not re-owned by the "
            "runtime role"
        )
    elif scenario_key == "v3_nopriv":
        assert rows and not rows[0]["app_can_execute"], (
            "v3_nopriv: EXECUTE was not revoked from the runtime role"
        )


@_only_scenario("v3_nofunc")
@pytest.mark.asyncio
async def test_n1_missing_guard_function_fails_closed_zero_partial_tenant():
    manifest = _manifest()
    migrate_url, app_url, _ = _scenario_urls(_scenario(manifest, "v3_nofunc"))
    await _assert_induced_state("v3_nofunc", migrate_url)
    await _negative_lifecycle_assertions(app_url)
    await _direct_bootstrap_refusal(app_url, "v3_nofunc", "does not exist")


@_only_scenario("v3_badsig")
@pytest.mark.asyncio
async def test_n2_incompatible_guard_signature_fails_closed_zero_partial_tenant():
    manifest = _manifest()
    migrate_url, app_url, _ = _scenario_urls(_scenario(manifest, "v3_badsig"))
    await _assert_induced_state("v3_badsig", migrate_url)
    await _negative_lifecycle_assertions(app_url)
    await _direct_bootstrap_refusal(
        app_url, "v3_badsig", "incompatible with the migration authority contract"
    )


@_only_scenario("v3_wrongown")
@pytest.mark.asyncio
async def test_n3_runtime_owned_guard_function_fails_closed_zero_partial_tenant():
    manifest = _manifest()
    migrate_url, app_url, _ = _scenario_urls(_scenario(manifest, "v3_wrongown"))
    await _assert_induced_state("v3_wrongown", migrate_url)
    await _negative_lifecycle_assertions(app_url)
    await _direct_bootstrap_refusal(
        app_url, "v3_wrongown", "incompatible with the migration authority contract"
    )


@_only_scenario("v3_nopriv")
@pytest.mark.asyncio
async def test_n4_missing_execute_privilege_fails_closed_zero_partial_tenant():
    manifest = _manifest()
    migrate_url, app_url, _ = _scenario_urls(_scenario(manifest, "v3_nopriv"))
    await _assert_induced_state("v3_nopriv", migrate_url)
    await _negative_lifecycle_assertions(app_url)
    await _direct_bootstrap_refusal(app_url, "v3_nopriv", "lacks EXECUTE")


# ---------------------------------------------------------------------------
# R1-R1 behavioral proofs: fail-closed authority, read-only verify,
# injection refusal, cross-cluster refusal
# ---------------------------------------------------------------------------


async def _guard_identity_via_asyncpg(url: str) -> dict | None:
    conn = await _connect(url)
    try:
        row = await conn.fetchrow(
            "SELECT p.oid::bigint AS oid, "
            "pg_get_userbyid(p.proowner) AS owner_name, "
            "md5(pg_get_functiondef(p.oid)) AS definition_md5 "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' "
            "AND p.proname = 'prevent_ledger_modification'"
        )
        return dict(row) if row else None
    finally:
        await conn.close()


def _run_cli(args: list[str], extra_env: dict[str, str]):
    import subprocess

    env = os.environ.copy()
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, GRANTS_SCRIPT, *args],
        capture_output=True, text=True, env=env, cwd=BACKEND_DIR,
        timeout=300,
    )


@_only_scenario("v3_ok")
@pytest.mark.asyncio
async def test_r0_single_role_topology_refused_zero_partial_tenant():
    """R1-R1 fix 3/4: bootstrapping AS the migration authority (the
    single-role topology) must fail closed - the runtime role must be a
    different, non-privileged role - and must leave zero tenant objects."""
    from scripts.bootstrap_tenant_schema import (
        LedgerGuardAuthorityError,
        bootstrap,
    )

    manifest = _manifest()
    migrate_url, app_url, _ = _scenario_urls(_scenario(manifest, "v3_ok"))
    tenant_schema = f"t_v3single_{uuid.uuid4().hex[:12]}"
    with pytest.raises(LedgerGuardAuthorityError) as excinfo:
        await bootstrap(tenant_schema, migrate_url)
    message = str(excinfo.value)
    assert "single-role topology" in message, message
    assert MIGRATION_AUTHORITY_ROLE in message, message

    app_engine = _app_engine(app_url)
    try:
        async with app_engine.connect() as conn:
            rows = await _fetch_rows(
                conn,
                "SELECT 1 FROM information_schema.schemata "
                "WHERE schema_name LIKE :prefix",
                {"prefix": "t\\_v3single%"},
            )
    finally:
        await app_engine.dispose()
    assert not rows, "single-role refusal still left a partial tenant schema"


@_only_scenario("v3_wrongown")
@pytest.mark.asyncio
async def test_r0_owner_fallback_removed_env_undeclared(monkeypatch):
    """R1-R1 fix 3: with the authority env UNDECLARED, a runtime-owned guard
    must still be refused - the authority is the database owner from the
    catalog, never the connected role.  (Restoring the fallback lets this
    bootstrap proceed - the named RED for mutation MM2.)"""
    from scripts.bootstrap_tenant_schema import (
        LedgerGuardAuthorityError,
        bootstrap,
    )

    manifest = _manifest()
    _, app_url, _ = _scenario_urls(_scenario(manifest, "v3_wrongown"))
    monkeypatch.delenv("MPANGO_MIGRATION_AUTHORITY_ROLE", raising=False)
    tenant_schema = f"t_v3noenv_{uuid.uuid4().hex[:12]}"
    with pytest.raises(LedgerGuardAuthorityError) as excinfo:
        await bootstrap(tenant_schema, app_url)
    assert "expected migration authority" in str(excinfo.value), excinfo.value

    app_engine = _app_engine(app_url)
    try:
        async with app_engine.connect() as conn:
            rows = await _fetch_rows(
                conn,
                "SELECT 1 FROM information_schema.schemata "
                "WHERE schema_name LIKE :prefix",
                {"prefix": "t\\_v3noenv%"},
            )
    finally:
        await app_engine.dispose()
    assert not rows, "refusal still left a partial tenant schema"


@_only_scenario("v3_verify_wrongown")
@pytest.mark.asyncio
async def test_verify_cli_wrongowner_nonzero_and_read_only():
    """R1-R1 fixes 1+2: against a database whose guard is owned by the
    RUNTIME role, --verify must exit non-zero AND leave the function OID,
    owner and body digest byte-identical (strict read-only proof)."""
    import json as _json

    manifest = _manifest()
    migrate_url, app_url, database = _scenario_urls(
        _scenario(manifest, "v3_verify_wrongown")
    )
    admin_scenario_url = manifest["admin_url"].rsplit("/", 1)[0] + "/" + database

    before = await _guard_identity_via_asyncpg(migrate_url)
    assert before is not None, "counterexample database must have the guard"
    assert before["owner_name"] == RUNTIME_ROLE, (
        "harness must have induced runtime ownership first"
    )

    result = _run_cli(
        ["--verify", "--admin-url", admin_scenario_url,
         "--migrate-url", migrate_url, "--app-url", app_url],
        extra_env={},
    )
    assert result.returncode != 0, (
        "--verify must exit non-zero when the runtime role owns the guard"
    )
    stdout_json = result.stdout[result.stdout.index("{"):]
    report = _json.loads(stdout_json)
    assert report["ok"] is False
    assert report["checks"]["ledger_guard_function"]["ok"] is False
    assert report["checks"]["ledger_guard_function"]["owner"] == RUNTIME_ROLE
    assert report["checks"]["runtime_differs_from_authority"]["ok"] is True

    after = await _guard_identity_via_asyncpg(migrate_url)
    assert after is not None, "read-only verify must not drop the function"
    assert after["oid"] == before["oid"], "guard OID changed under --verify"
    assert after["owner_name"] == before["owner_name"]
    assert after["definition_md5"] == before["definition_md5"], (
        "guard BODY changed under --verify - verify is not read-only"
    )


INJECTION_ROLE = (
    'v3inject" ; DROP FUNCTION public.prevent_ledger_modification(); --'
)


@_only_scenario("v3_verify_wrongown")
@pytest.mark.asyncio
async def test_injection_identifiers_rejected_zero_writes():
    """R1-R1 fix 5: a malicious role identifier (quote + semicolon + comment
    aimed at dropping the guard) must be rejected by the allowlist BEFORE
    any connection or statement, leaving the role set and the guard
    byte-identical.  (Bypassing validation lets the payload execute - the
    named RED for mutation MM3.)"""
    manifest = _manifest()
    migrate_url, app_url, database = _scenario_urls(
        _scenario(manifest, "v3_verify_wrongown")
    )
    admin_scenario_url = manifest["admin_url"].rsplit("/", 1)[0] + "/" + database
    parsed = urlsplit(app_url)
    host_part = parsed.netloc.split("@")[1]
    malicious_app_url = urlunsplit(parsed._replace(
        netloc=f"{INJECTION_ROLE}:{parsed.password}@{host_part}"
    ))

    async def _cluster_state():
        conn = await _connect(admin_scenario_url)
        try:
            roles = tuple(await conn.fetchval(
                "SELECT array_agg(rolname ORDER BY rolname) FROM pg_roles"
            ) or [])
        finally:
            await conn.close()
        return roles, await _guard_identity_via_asyncpg(migrate_url)

    before_roles, before_guard = await _cluster_state()

    result = _run_cli(
        ["--provision", "--admin-url", admin_scenario_url,
         "--migrate-url", migrate_url, "--app-url", malicious_app_url],
        extra_env={"MPANGO_DB_APP_ROLE": INJECTION_ROLE},
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "invalid runtime role identifier" in combined, combined[-600:]
    assert "quotes, semicolons, comments" in combined, combined[-600:]

    after_roles, after_guard = await _cluster_state()
    assert "v3inject" not in after_roles, (
        "injection created a role despite identifier validation"
    )
    assert after_roles == before_roles, "cluster role set changed"
    assert after_guard == before_guard, (
        "guard identity changed - injection survived validation"
    )


@_only_scenario("v3_ok")
@pytest.mark.asyncio
async def test_cluster_binding_mismatch_zero_writes():
    """R1-R1 fix 6: an admin URL on ANOTHER cluster with migrate/app URLs on
    this cluster must be refused by the binding preflight with ZERO writes
    on the second cluster.  (Bypassing binding writes roles/database there -
    the named RED for mutation MM4.)"""
    manifest = _manifest()
    second = manifest.get("second_cluster") or {}
    second_admin_url = second.get("admin_url")
    if not second_admin_url:
        pytest.skip("manifest has no second cluster wired")
    migrate_url, app_url, _ = _scenario_urls(_scenario(manifest, "v3_ok"))

    async def _second_cluster_state():
        conn = await _connect(second_admin_url)
        try:
            roles = tuple(r["rolname"] for r in await conn.fetch(
                "SELECT rolname FROM pg_roles "
                "WHERE rolname IN ($1, $2, 'v3inject') ORDER BY rolname",
                MIGRATION_AUTHORITY_ROLE, RUNTIME_ROLE,
            ))
            databases = tuple(r["datname"] for r in await conn.fetch(
                "SELECT datname FROM pg_database "
                "WHERE datname NOT IN ('postgres', 'template0', 'template1') "
                "ORDER BY datname"
            ))
        finally:
            await conn.close()
        return roles, databases

    before_roles, before_databases = await _second_cluster_state()

    result = _run_cli(
        ["--provision", "--admin-url", second_admin_url,
         "--migrate-url", migrate_url, "--app-url", app_url],
        extra_env={},
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, "cross-cluster provision must be refused"
    assert "cluster binding preflight failed" in combined, combined[-600:]

    after_roles, after_databases = await _second_cluster_state()
    assert after_roles == before_roles, (
        "roles were written to the second cluster despite binding refusal"
    )
    assert after_databases == before_databases, (
        "databases were written to the second cluster despite binding refusal"
    )


# ---------------------------------------------------------------------------
# semantic mutation sentinels (harness re-runs these after patching source)
# ---------------------------------------------------------------------------


@_only_scenario("v3_ok")
@pytest.mark.asyncio
async def test_mutation_m1_sentinel_reintroducing_runtime_replace_is_refused(
    _provisioned,
):
    """Named RED sentinel for mutation M1 (runtime CREATE OR REPLACE
    reintroduced): in the two-role topology the replacement must be refused
    by PostgreSQL itself, so the lifecycle fails closed and the guard stays
    migration-owned.  GREEN in the unmuted run proves the mutation run's RED
    came from the mutation, not from a broken environment."""
    lifecycle = _provisioned["lifecycle"]
    assert lifecycle["http"]["verify"] == 200, lifecycle["http"]
    before = _provisioned["guard_before"]
    assert before["owner_name"] == MIGRATION_AUTHORITY_ROLE


@_only_scenario("v3_wrongown")
@pytest.mark.asyncio
async def test_mutation_m2_sentinel_ownership_precondition_is_load_bearing():
    """Named RED sentinel for mutation M2 (ownership precondition removed):
    with the precondition active, a runtime-owned guard must still be
    refused.  GREEN here proves the mutation run's RED came from the
    removal."""
    manifest = _manifest()
    _, app_url, _ = _scenario_urls(_scenario(manifest, "v3_wrongown"))
    await _direct_bootstrap_refusal(
        app_url, "v3_wrongown",
        "incompatible with the migration authority contract",
    )
