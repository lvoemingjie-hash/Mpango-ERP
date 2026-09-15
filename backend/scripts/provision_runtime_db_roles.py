#!/usr/bin/env python3
"""Provision the migration-authority and runtime DB roles with MINIMUM grants.

MPANGO-TENANT-BOOTSTRAP-DB-AUTHORITY-R1 (frozen architectural decision):

1. The migration authority owns the public schema and the shared security
   function ``public.prevent_ledger_modification()``.
2. The runtime role must never own or replace that function.
3. The runtime role stays non-superuser, NO CREATEDB, NO CREATEROLE.
4. The runtime role may create tenant-owned schemas/objects (CREATE on the
   database) and needs EXECUTE on the shared guard function so tenant
   triggers can fire — nothing more.

This tool is the ONLY sanctioned place where runtime grants are declared.
The statement vocabulary is declarative (``MINIMUM_GRANT_STATEMENTS``,
``DATABASE_SCOPE_GRANT_TEMPLATES``, ``RUNTIME_ROLE_DDL_TEMPLATE``) and every
statement is checked against ``FORBIDDEN_SQL_FRAGMENTS`` before execution, so
``ALTER SCHEMA public OWNER``, ``ALTER FUNCTION ... OWNER`` and ``GRANT ALL``
can never be issued here.  ``--verify`` re-checks the live cluster.

Topology (fresh PG15+/PG16 cluster):
    step 1 (admin, superuser): create roles + application database
                               owned by the migration authority
    step 2 (migration authority): run `alembic upgrade head`  (not this tool)
    step 3 (migration authority): apply minimum object grants (--apply-grants)
    step 4 (any operator):        --verify

Usage:
    export MPANGO_DB_ADMIN_URL="postgresql://postgres:...@127.0.0.1:5433/postgres"
    export MPANGO_DB_MIGRATE_URL="postgresql://mpango_migrate:...@127.0.0.1:5433/mpango"
    export MPANGO_DB_APP_URL="postgresql://mpango_app:...@127.0.0.1:5433/mpango"
    python scripts/provision_runtime_db_roles.py --provision --apply-grants
    python scripts/provision_runtime_db_roles.py --verify
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from urllib.parse import urlsplit

ADMIN_URL_ENV = "MPANGO_DB_ADMIN_URL"
MIGRATE_URL_ENV = "MPANGO_DB_MIGRATE_URL"
APP_URL_ENV = "MPANGO_DB_APP_URL"
MIGRATE_ROLE_ENV = "MPANGO_DB_MIGRATE_ROLE"
APP_ROLE_ENV = "MPANGO_DB_APP_ROLE"
DEFAULT_MIGRATE_ROLE = "mpango_migrate"
DEFAULT_APP_ROLE = "mpango_app"
LEDGER_GUARD_SIGNATURE = "public.prevent_ledger_modification()"

# Statements this tool must NEVER issue.  Checked (case-insensitive, whitespace
# collapsed) against every rendered statement before execution; a match
# aborts.  Role/database creation is this tool's declared job; re-owning or
# blanket-granting existing objects is not.
FORBIDDEN_SQL_FRAGMENTS = (
    "alter schema",
    "owner to",
    "grant all",
    "alter function",
    "with admin option",
    "with grant option",
    "alter database",
)

# Role creation: the RUNTIME role is born with the frozen decision-3
# attributes and can never gain more through this tool.  The migration
# authority carries CREATEROLE because migration 011_s6_p_reporting_role
# creates reporting_role/reporting_user; it stays NOSUPERUSER/NOCREATEDB.
RUNTIME_ROLE_DDL_TEMPLATE = (
    'CREATE ROLE "{role}" LOGIN{password_clause} '
    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION"
)
MIGRATION_AUTHORITY_ROLE_DDL_TEMPLATE = (
    'CREATE ROLE "{role}" LOGIN{password_clause} '
    "NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOREPLICATION"
)

# Object grants the migration authority confers on the runtime role.
# ``{app_role}`` is rendered at apply time.  Deliberately explicit: EXECUTE is
# granted for the shared guard function only, never blanket across functions.
MINIMUM_GRANT_STATEMENTS: tuple[str, ...] = (
    'GRANT USAGE ON SCHEMA public TO "{app_role}"',
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
    'TO "{app_role}"',
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public " 'TO "{app_role}"',
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, "
    'UPDATE, DELETE ON TABLES TO "{app_role}"',
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT "
    'ON SEQUENCES TO "{app_role}"',
    "GRANT EXECUTE ON FUNCTION " + LEDGER_GUARD_SIGNATURE + ' TO "{app_role}"',
)

# Database-scoped grants: CONNECT plus CREATE — CREATE is the ONLY schema-level
# authority the runtime role gets; it is what lets signup provisioning create
# tenant schemas (CREATE SCHEMA "t_<uuid>") and nothing beyond that.
DATABASE_SCOPE_GRANT_TEMPLATES: tuple[str, ...] = (
    'GRANT CONNECT ON DATABASE "{database}" TO "{app_role}"',
    'GRANT CREATE ON DATABASE "{database}" TO "{app_role}"',
)


def render_minimum_grant_statements(app_role: str, database: str) -> tuple[str, ...]:
    rendered = [
        statement.replace("{app_role}", app_role)
        for statement in MINIMUM_GRANT_STATEMENTS
    ]
    rendered += [
        template.replace("{database}", database).replace("{app_role}", app_role)
        for template in DATABASE_SCOPE_GRANT_TEMPLATES
    ]
    return tuple(rendered)


def _assert_sanctioned_sql(sql: str) -> str:
    collapsed = " ".join(sql.lower().split())
    for fragment in FORBIDDEN_SQL_FRAGMENTS:
        if fragment in collapsed:
            raise RuntimeError(
                "provision_runtime_db_roles refuses to execute non-minimal SQL: "
                f"forbidden fragment {fragment!r} detected in {sql!r}"
            )
    return sql


class Provisioner:
    def __init__(self, admin_url: str, migrate_url: str, app_url: str,
                 migrate_role: str, app_role: str, database: str) -> None:
        self.admin_url = admin_url
        self.migrate_url = migrate_url
        self.app_url = app_url
        self.migrate_role = migrate_role
        self.app_role = app_role
        self.database = database

    # ------------------------------------------------------------------ admin
    async def _ensure_role(self, admin, role: str, password: str | None,
                           template: str) -> None:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", role):
            raise RuntimeError(f"unsafe role name: {role!r}")
        existing = await admin.fetchval(
            "SELECT 1 FROM pg_roles WHERE rolname = $1", role
        )
        if existing:
            print(f"[roles] role {role} already exists")
            return
        password_clause = ""
        if password:
            password_clause = f" PASSWORD '{password.replace(chr(39), chr(39) * 2)}'"
        ddl = template.format(role=role, password_clause=password_clause)
        _assert_sanctioned_sql(ddl)
        await admin.execute(ddl)
        attribute_summary = (
            "CREATEROLE" if template is MIGRATION_AUTHORITY_ROLE_DDL_TEMPLATE
            else "NOCREATEROLE"
        )
        print(
            f"[roles] created role {role} "
            f"(NOSUPERUSER NOCREATEDB {attribute_summary})"
        )

    async def create_roles_and_database(self, app_password: str | None,
                                        migrate_password: str | None) -> None:
        import asyncpg

        admin = await asyncpg.connect(self.admin_url)
        try:
            await self._ensure_role(
                admin, self.migrate_role, migrate_password,
                MIGRATION_AUTHORITY_ROLE_DDL_TEMPLATE,
            )
            await self._ensure_role(
                admin, self.app_role, app_password,
                RUNTIME_ROLE_DDL_TEMPLATE,
            )
            exists = await admin.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", self.database
            )
            if exists:
                print(f"[database] {self.database} already exists")
            else:
                safe_db = self.database.replace('"', '""')
                _assert_sanctioned_sql(
                    f'CREATE DATABASE "{safe_db}" OWNER "{self.migrate_role}"'
                )
                await admin.execute(
                    f'CREATE DATABASE "{safe_db}" OWNER "{self.migrate_role}"'
                )
                print(
                    f"[database] created {self.database} "
                    f"(owner {self.migrate_role}; on PG15+ the public schema is "
                    "owned by the database owner, so the migration authority "
                    "owns schema public and the shared guard function)"
                )
        finally:
            await admin.close()

    # ------------------------------------------------------- migration authority
    async def apply_minimum_grants(self) -> None:
        """Apply the declared minimum runtime grants as the migration authority.

        The migration authority owns the database, schema public and every
        object migrations create there, so it holds GRANT OPTION on exactly
        these privileges and nothing beyond them is conferred.
        """
        import asyncpg

        statements = render_minimum_grant_statements(
            self.app_role, self.database
        )
        for sql in statements:
            _assert_sanctioned_sql(sql)

        migrate = await asyncpg.connect(self.migrate_url)
        try:
            for sql in statements:
                await migrate.execute(sql)
            print(
                f"[grants] {len(statements)} minimum grants applied as "
                f"{self.migrate_role}"
            )
        finally:
            await migrate.close()

    # ----------------------------------------------------------------- verify
    async def verify(self) -> dict:
        """Read-only verification of the frozen authority contract."""
        import asyncpg

        report: dict = {"database": self.database, "checks": {}, "ok": True}

        def _record(name: str, ok: bool, **detail: object) -> None:
            report["checks"][name] = {"ok": ok, **detail}
            if not ok:
                report["ok"] = False

        admin = await asyncpg.connect(self.admin_url)
        try:
            for role, allow_createrole in (
                (self.migrate_role, True),   # migration 011 creates reporting_role
                (self.app_role, False),      # frozen decision 3: strict
            ):
                attrs = await admin.fetchrow(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, "
                    "rolreplication, rolcanlogin FROM pg_roles "
                    "WHERE rolname = $1",
                    role,
                )
                if attrs is None:
                    _record(f"role_{role}", False, reason="missing")
                    continue
                ok = (
                    not (
                        attrs["rolsuper"] or attrs["rolcreatedb"]
                        or attrs["rolreplication"]
                        or (attrs["rolcreaterole"] and not allow_createrole)
                    )
                    and attrs["rolcanlogin"]
                )
                _record(
                    f"role_{role}", ok, attributes=dict(attrs),
                    reason="" if ok else "forbidden attribute set",
                )
            db_row = await admin.fetchrow(
                "SELECT pg_get_userbyid(datdba) AS owner FROM pg_database "
                "WHERE datname = $1",
                self.database,
            )
            _record(
                "database_owner",
                db_row is not None and db_row["owner"] == self.migrate_role,
                owner=db_row["owner"] if db_row else None,
            )
        finally:
            await admin.close()
        db_owner = db_row["owner"] if db_row else None

        migrate = await asyncpg.connect(self.migrate_url)
        try:
            row = await migrate.fetchrow(
                "SELECT pg_get_userbyid(p.proowner) AS owner, "
                "format_type(p.prorettype, NULL) AS return_type, "
                "pg_get_function_identity_arguments(p.oid) AS identity_arguments "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public' "
                "AND p.proname = 'prevent_ledger_modification'"
            )
            guard_ok = (
                row is not None
                and row["owner"] == self.migrate_role
                and row["return_type"] == "trigger"
                and row["identity_arguments"].strip() == ""
            )
            _record(
                "ledger_guard_function",
                guard_ok,
                owner=row["owner"] if row else None,
                return_type=row["return_type"] if row else None,
                identity_arguments=(
                    row["identity_arguments"] if row else None
                ),
            )
            schema_row = await migrate.fetchrow(
                "SELECT pg_get_userbyid(nspowner) AS owner FROM pg_namespace "
                "WHERE nspname = 'public'"
            )
            # PG15+/PG16: the public schema is owned by the pseudo-role
            # pg_database_owner, whose implicit member is the database owner
            # (the migration authority here) — equivalent ownership.
            public_owner = schema_row["owner"] if schema_row else None
            public_owner_ok = (
                public_owner == self.migrate_role
                or (
                    public_owner == "pg_database_owner"
                    and db_owner == self.migrate_role
                )
            )
            _record(
                "public_schema_owner",
                public_owner_ok,
                owner=public_owner,
                database_owner=db_owner,
            )
        finally:
            await migrate.close()

        app = await asyncpg.connect(self.app_url)
        try:
            can_execute = await app.fetchval(
                "SELECT has_function_privilege(current_user, $1, 'EXECUTE')",
                LEDGER_GUARD_SIGNATURE,
            )
            _record("app_execute_on_guard", bool(can_execute),
                    can_execute=can_execute)
            can_create_schema = await app.fetchval(
                "SELECT has_database_privilege(current_user, $1, 'CREATE')",
                self.database,
            )
            _record("app_create_on_database", bool(can_create_schema),
                    can_create=can_create_schema)
            # The refusal probe: what the runtime role must NEVER be able to
            # do.  Executed inside a transaction that is always rolled back,
            # so even a misconfigured cluster is left byte-identical.
            cannot_replace = True
            try:
                async with app.transaction():
                    await app.execute(
                        f"CREATE OR REPLACE FUNCTION {LEDGER_GUARD_SIGNATURE} "
                        "RETURNS TRIGGER AS $$ BEGIN RETURN OLD; END; "
                        "$$ LANGUAGE plpgsql"
                    )
                    cannot_replace = False
            except asyncpg.InsufficientPrivilegeError:
                cannot_replace = True
            _record(
                "app_cannot_replace_guard", cannot_replace,
                reason="" if cannot_replace else "replacement succeeded",
            )
        finally:
            await app.close()
        return report


def _database_from_url(url: str) -> str:
    path = urlsplit(url).path.lstrip("/")
    if not path:
        raise RuntimeError("database name missing from URL")
    return path


def _env(name: str, value: str | None) -> str:
    result = value or os.environ.get(name, "")
    if not result:
        raise RuntimeError(
            f"missing required --{name.replace('_', '-').lower()} or env {name}"
        )
    return result


async def _async_main(args: argparse.Namespace) -> int:
    admin_url = _env(ADMIN_URL_ENV, args.admin_url)
    migrate_url = _env(MIGRATE_URL_ENV, args.migrate_url)
    app_url = _env(APP_URL_ENV, args.app_url)
    migrate_role = os.environ.get(MIGRATE_ROLE_ENV, DEFAULT_MIGRATE_ROLE)
    app_role = os.environ.get(APP_ROLE_ENV, DEFAULT_APP_ROLE)
    database = _database_from_url(migrate_url)

    provisioner = Provisioner(
        admin_url, migrate_url, app_url, migrate_role, app_role, database
    )
    if args.provision:
        await provisioner.create_roles_and_database(
            app_password=os.environ.get("MPANGO_DB_APP_PASSWORD"),
            migrate_password=os.environ.get("MPANGO_DB_MIGRATE_PASSWORD"),
        )
    if args.apply_grants:
        await provisioner.apply_minimum_grants()
    if args.verify:
        report = await provisioner.verify()
        print(json.dumps(report, indent=2, default=str))
        if not report["ok"]:
            return 2
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision migration-authority + runtime DB roles with "
                    "minimum grants (never ALTER OWNER / GRANT ALL)."
    )
    parser.add_argument("--admin-url", default=None)
    parser.add_argument("--migrate-url", default=None)
    parser.add_argument("--app-url", default=None)
    parser.add_argument("--provision", action="store_true",
                        help="create roles and the application database as admin")
    parser.add_argument("--apply-grants", action="store_true",
                        help="apply minimum object grants as the migration "
                             "authority")
    parser.add_argument("--verify", action="store_true",
                        help="read-only verification of the authority contract")
    args = parser.parse_args()
    if not (args.provision or args.apply_grants or args.verify):
        parser.error("nothing to do: pass --provision and/or --apply-grants "
                     "and/or --verify")
    sys.exit(asyncio.run(_async_main(args)))


if __name__ == "__main__":
    main()
