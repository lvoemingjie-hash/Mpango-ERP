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
statement is checked against ``FORBIDDEN_SQL_FRAGMENTS`` (a grant-minimality
policy) before execution, so ``ALTER SCHEMA public OWNER``, ``ALTER FUNCTION
... OWNER`` and ``GRANT ALL`` can never be issued here.  Injection defense
is separate and structural: every role/database identifier passes the strict
allowlist ``validate_identifier`` in ALL modes before any connection opens.

R1-R1 hardening:
- ``--verify`` is STRICTLY read-only: pure catalog checks only, no DDL probe
  (not even in a rolled-back transaction).
- Every write mode first passes ``_assert_cluster_binding``: the
  admin/migrate/app URLs must resolve to one cluster (same
  ``pg_control_system().system_identifier``), migrate/app must target the
  configured database, and each URL must bind its expected ``current_user``
  (admin user superuser, migration authority, runtime role).  Any mismatch
  refuses with ZERO writes.

R1-R2 hardening (see ``_assert_cluster_binding``): the frozen endpoint
binding covers ALL THREE URLs; deferred provisioning is allowed only for a
catalog-proven fresh first deployment or credential-proven established
principals; diagnostics are credential-free (host:port only, never netloc).

R1-R3 hardening:
- ANY Layer 1 binding violation raises ``ClusterBindingError`` BEFORE ANY
  connection — the admin URL included (zero-connection endpoint refusal).
  The refusal is proven by intercepting-spy tests: admin/migrate/app
  endpoint mismatches each produce ZERO asyncpg.connect calls.

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
from urllib.parse import urlsplit, urlunsplit

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
#
# NOTE: this list is a GRANT-MINIMALITY policy, not an injection defense.
# Injection defense is the strict allowlist validation below: identifiers
# that fail validation can never reach SQL text at all.
FORBIDDEN_SQL_FRAGMENTS = (
    "alter schema",
    "owner to",
    "grant all",
    "alter function",
    "with admin option",
    "with grant option",
    "alter database",
)

# R1-R1 fix 5: strict allowlist identifier validation, applied uniformly in
# EVERY run mode (provision / apply-grants / verify) BEFORE any connection or
# statement.  A plain [a-z_][a-z0-9_] name (PostgreSQL NAMEDATALEN-1 bound)
# cannot contain quotes, semicolons, comments, whitespace or any other SQL
# syntax, so safely quoted interpolation of a VALIDATED identifier is
# injection-proof by construction — no blacklist involved.
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def validate_identifier(value: str, label: str) -> str:
    """Validate a role/database identifier against the strict allowlist.

    Rejects (by never allowing in the first place) double quotes, single
    quotes, semicolons, comment markers, spaces, dashes, unicode and every
    other character outside [a-z0-9_].  Raises ValueError on violation.
    """
    if not isinstance(value, str) or not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            f"invalid {label} identifier: {value!r} — only plain "
            "'[a-z_][a-z0-9_]*' names (max 63 chars) are accepted; quotes, "
            "semicolons, comments and any other SQL syntax are rejected"
        )
    return value

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


class ClusterBindingError(RuntimeError):
    """Zero-write refusal: the three URLs do not describe one deployment."""


def _binding_refusal_message(problems: list[str]) -> str:
    """Render the binding refusal diagnostic.

    Credential-free by construction: callers only ever append host:port
    pairs, role names and the configured database name to ``problems`` —
    never a DSN, netloc or password.
    """
    message = "cluster binding preflight failed (zero writes performed):"
    for problem in problems:
        message = message + "\n  - " + problem
    return message


class Provisioner:
    def __init__(self, admin_url: str, migrate_url: str, app_url: str,
                 migrate_role: str, app_role: str, database: str) -> None:
        # R1-R1 fix 5: uniform identifier validation in EVERY mode, before
        # any connection is opened or any statement rendered.
        validate_identifier(migrate_role, "migration authority role")
        validate_identifier(app_role, "runtime role")
        validate_identifier(database, "database")
        self.admin_url = admin_url
        self.migrate_url = migrate_url
        self.app_url = app_url
        self.migrate_role = migrate_role
        self.app_role = app_role
        self.database = database
        self._expected_admin_user = urlsplit(admin_url).username or ""

    # ------------------------------------------------------- binding preflight
    async def _assert_cluster_binding(self, *, require_live: bool = True) -> dict:
        """Prove the three URLs describe ONE deployment; refuse with zero
        writes on any mismatch.

        Layer 1 (always, BEFORE ANY CONNECTION - zero-connection refusal):
        FROZEN ENDPOINT BINDING - ALL THREE URLs (admin, migrate, app) must
        share ONE host:port, the migrate/app URLs must both name the
        configured database, and their usernames must equal the
        migration-authority and runtime roles.  ANY Layer 1 violation raises
        ClusterBindingError IMMEDIATELY: not even the admin URL is connected,
        so a mis-wired deployment never sees a single connection attempt
        (R1-R3 fix 1).  Diagnostics render host:port only - NEVER netloc,
        DSN or passwords.

        Layer 2 (always): the admin URL is connected live; its current_user
        must equal the URL user and that user must be a superuser, and the
        cluster system identifier is captured.

        Layer 3 (whenever the migrate/app roles and database are connectable):
        all three connections must report the SAME
        pg_control_system().system_identifier, both must resolve
        current_database() to the configured database, and each current_user
        must equal its expected role.

        R1-R2 fix 1/2: when the migrate/app endpoints are NOT connectable,
        deferral is allowed ONLY in two catalog-proven shapes - (a) a fully
        fresh first deployment (target database and both roles all absent)
        or (b) an established deployment adding a database (both roles
        exist, target database absent, AND both roles pass a live
        credential probe against the maintenance database BEFORE any
        write).  Any partial state (exactly one role, or the database
        already existing) or a failed credential probe refuses with ZERO
        writes; provisioning never happens blind.

        ``require_live=False`` is used only for the FIRST --provision call;
        the full live proof is re-asserted immediately after creation.
        """
        problems: list[str] = []
        admin_parsed = urlsplit(self.admin_url)
        migrate_parsed = urlsplit(self.migrate_url)
        app_parsed = urlsplit(self.app_url)

        def _endpoint(parsed) -> tuple[str, int]:
            return (parsed.hostname or "").lower(), parsed.port or 5432

        # Layer 1: frozen endpoint binding across ALL THREE URLs.  Only
        # host:port is rendered in diagnostics; userinfo is never printed.
        endpoints = {
            "admin": _endpoint(admin_parsed),
            "migrate": _endpoint(migrate_parsed),
            "app": _endpoint(app_parsed),
        }
        if len(set(endpoints.values())) != 1:
            rendered = " vs ".join(
                f"{host}:{port}" for host, port in endpoints.values()
            )
            problems.append(
                "URLs do not share one frozen endpoint (admin/migrate/app "
                f"host:port must be identical): {rendered}"
            )
        if (migrate_parsed.path or "/") != (app_parsed.path or "/")                 or (migrate_parsed.path or "/").lstrip("/") != self.database:
            problems.append(
                "migrate and app URLs do not both target the configured "
                f"database {self.database!r}"
            )
        if (migrate_parsed.username or "") != self.migrate_role:
            problems.append(
                f"migrate URL username does not equal the migration "
                f"authority role {self.migrate_role!r}"
            )
        if (app_parsed.username or "") != self.app_role:
            problems.append(
                f"app URL username does not equal the runtime role "
                f"{self.app_role!r}"
            )

        # R1-R3 fix 1 (zero-connection endpoint refusal): ANY Layer 1
        # violation raises IMMEDIATELY - before asyncpg is even imported and
        # before ANY connection attempt, the admin URL included.  A mis-wired
        # URL set must never cause a single connection: reaching out to an
        # unverified cluster is itself an action on the wrong target, and the
        # refusal must be observable with zero network side effects.
        if problems:
            raise ClusterBindingError(
                _binding_refusal_message(problems)
            )

        import asyncpg

        async def _probe(url: str) -> dict:
            conn = await asyncpg.connect(url)
            try:
                return dict(await conn.fetchrow(
                    "SELECT system_identifier, "
                    "       current_user AS bound_user, "
                    "       current_database() AS bound_database, "
                    "       (SELECT rolsuper FROM pg_roles "
                    "        WHERE rolname = current_user) AS is_superuser "
                    "FROM pg_control_system()"
                ))
            finally:
                await conn.close()

        admin = await _probe(self.admin_url)
        if admin["bound_user"] != self._expected_admin_user:
            problems.append(
                f"admin URL binds current_user {admin['bound_user']!r}, "
                f"expected {self._expected_admin_user!r}"
            )
        if not admin["is_superuser"]:
            problems.append(
                f"admin URL user {admin['bound_user']!r} is not a superuser"
            )

        live: dict = {}
        try:
            live["migrate"] = await _probe(self.migrate_url)
            live["app"] = await _probe(self.app_url)
        except (asyncpg.InvalidPasswordError,
                asyncpg.InvalidAuthorizationSpecificationError,
                asyncpg.InvalidCatalogNameError,
                asyncpg.UndefinedObjectError,
                ConnectionError, OSError):
            live = {}

        if live:
            identifiers = {
                "admin": admin["system_identifier"],
                "migrate": live["migrate"]["system_identifier"],
                "app": live["app"]["system_identifier"],
            }
            if len(set(identifiers.values())) != 1:
                problems.append(
                    "URLs target different clusters (system identifiers differ)"
                )
            if not (
                live["migrate"]["bound_database"] == self.database
                and live["app"]["bound_database"] == self.database
            ):
                problems.append(
                    "migrate/app connections do not both resolve the "
                    f"configured database {self.database!r}"
                )
            if live["migrate"]["bound_user"] != self.migrate_role:
                problems.append(
                    f"migrate URL binds current_user "
                    f"{live['migrate']['bound_user']!r}, expected "
                    f"migration authority {self.migrate_role!r}"
                )
            if live["app"]["bound_user"] != self.app_role:
                problems.append(
                    f"app URL binds current_user "
                    f"{live['app']['bound_user']!r}, expected runtime "
                    f"role {self.app_role!r}"
                )
        else:
            # R1-R2 fixes 1+2: a non-connectable migrate/app pair is
            # deferrable in EXACTLY two catalog-proven shapes; every other
            # state refuses with zero writes:
            #   (a) proven-fresh first deployment: target database AND both
            #       roles absent — nothing can be half-created;
            #   (b) established principals, absent database: BOTH roles
            #       exist (cluster-wide principals shared by multiple
            #       application databases) and only the database is absent.
            #       The unconnectable reason is then provably the missing
            #       database, but the CREDENTIALS are still verified live
            #       first — both roles must authenticate against the admin
            #       endpoint's existing maintenance database with their
            #       expected current_user — so a wrong password over an
            #       established deployment still refuses with zero writes.
            # Refused shapes: exactly one role exists (partial role set),
            # the target database already exists (live idempotent mode
            # requires connectable URLs), or the credential probe fails.
            admin_conn = await asyncpg.connect(self.admin_url)
            try:
                migrate_role_exists = bool(await admin_conn.fetchval(
                    "SELECT 1 FROM pg_roles WHERE rolname = $1",
                    self.migrate_role,
                ))
                app_role_exists = bool(await admin_conn.fetchval(
                    "SELECT 1 FROM pg_roles WHERE rolname = $1",
                    self.app_role,
                ))
                database_exists = bool(await admin_conn.fetchval(
                    "SELECT 1 FROM pg_database WHERE datname = $1",
                    self.database,
                ))
            finally:
                await admin_conn.close()

            deferral_allowed = False
            if database_exists:
                problems.append(
                    "deferred provisioning refused: the deployment state is "
                    f"not fresh (target database {self.database!r} already "
                    "exists) while the migrate/app URLs are not connectable "
                    "- re-provisioning an existing database requires "
                    "connectable URLs (zero writes performed)"
                )
            elif migrate_role_exists != app_role_exists:
                existing, absent = (
                    (self.migrate_role, self.app_role)
                    if migrate_role_exists
                    else (self.app_role, self.migrate_role)
                )
                problems.append(
                    "deferred provisioning refused: the deployment state is "
                    f"not fresh (partial role set: role {existing!r} already "
                    f"exists while role {absent!r} does not) - partial role "
                    "states are never provisioned over (zero writes "
                    "performed)"
                )
            elif not migrate_role_exists and not app_role_exists:
                deferral_allowed = True  # proven-fresh first deployment
            else:
                # Both roles exist, database absent: verify credentials by
                # authenticating each role against the maintenance database
                # BEFORE any write.
                try:
                    for url, expected_role in (
                        (self.migrate_url, self.migrate_role),
                        (self.app_url, self.app_role),
                    ):
                        parsed = urlsplit(url)
                        maintenance = urlsplit(self.admin_url)
                        probe_url = urlunsplit(parsed._replace(
                            path=maintenance.path or "/postgres"
                        ))
                        conn = await asyncpg.connect(probe_url)
                        try:
                            bound = await conn.fetchval("SELECT current_user")
                        finally:
                            await conn.close()
                        if bound != expected_role:
                            problems.append(
                                "deferred provisioning refused: credential "
                                f"probe for {expected_role!r} bound "
                                f"current_user {bound!r} (zero writes "
                                "performed)"
                            )
                            break
                    else:
                        deferral_allowed = True
                except (asyncpg.InvalidPasswordError,
                        asyncpg.InvalidAuthorizationSpecificationError,
                        ConnectionError, OSError):
                    problems.append(
                        "deferred provisioning refused: credential probe "
                        "failed for the established roles while the target "
                        "database is absent - wrong credentials are never "
                        "tolerated (zero writes performed)"
                    )
            if not deferral_allowed:
                pass  # problems already appended above
            elif require_live:
                problems.append(
                    "live binding required but the migrate/app URLs are not "
                    "connectable although the deployment state allows "
                    "deferred provisioning"
                )

        if problems:
            raise ClusterBindingError(_binding_refusal_message(problems))
        result = {
            "system_identifier": str(admin["system_identifier"]),
            "endpoint": f"{endpoints['admin'][0]}:{endpoints['admin'][1]}",
            "database": self.database,
            "admin_user": admin["bound_user"],
            "mode": "live" if live else "deferred-first-provision-fresh",
        }
        if live:
            result["migrate_user"] = live["migrate"]["bound_user"]
            result["app_user"] = live["app"]["bound_user"]
        return result

    # ------------------------------------------------------------------ admin
    async def _ensure_role(self, admin, role: str, password: str | None,
                           template: str) -> None:
        validate_identifier(role, "role")
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

        # R1-R1 fix 6: binding preflight BEFORE any role or database is
        # created; a mismatch refuses with zero writes.  On the very first
        # run the migrate/app URLs cannot connect yet (nothing exists), so
        # the deferred URL-consistency + live-admin proof runs first and the
        # FULL live proof is re-asserted immediately after creation.
        binding = await self._assert_cluster_binding(require_live=False)
        print(f"[binding] cluster {binding['system_identifier']} / "
              f"database {binding['database']} verified "
              f"({binding['mode']}) for admin user {binding['admin_user']}")
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
        # Full live proof now that the roles/database exist.
        binding = await self._assert_cluster_binding(require_live=True)
        print(f"[binding] post-creation live proof ok: cluster "
              f"{binding['system_identifier']}, "
              f"{binding['migrate_user']} / {binding['app_user']} bound")

    # ------------------------------------------------------- migration authority
    async def apply_minimum_grants(self) -> None:
        """Apply the declared minimum runtime grants as the migration authority.

        The migration authority owns the database, schema public and every
        object migrations create there, so it holds GRANT OPTION on exactly
        these privileges and nothing beyond them is conferred.
        """
        import asyncpg

        # R1-R1 fix 6: binding preflight precedes every write statement.
        binding = await self._assert_cluster_binding()
        print(f"[binding] cluster {binding['system_identifier']} / "
              f"database {binding['database']} verified before grants")
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
        """Strictly READ-ONLY verification of the frozen authority contract.

        R1-R1 fix 1: every check below is a pure catalog read.  There is
        deliberately NO DDL probe — not even inside a transaction — so
        --verify can never mutate the cluster under any outcome.  The
        runtime role's inability to replace the guard is proven from the
        catalog instead: PostgreSQL allows CREATE OR REPLACE / DROP on an
        existing function only for its owner, a superuser, or a member of
        the owning role, and creating a shadow function in public
        additionally requires CREATE on that schema — each of those paths
        is separately asserted to be closed.
        """
        import asyncpg

        report: dict = {"database": self.database, "checks": {}, "ok": True}

        def _record(name: str, ok: bool, **detail: object) -> None:
            report["checks"][name] = {"ok": ok, **detail}
            if not ok:
                report["ok"] = False

        # Uniform read-only preflight; also proves the URL binding.
        try:
            report["cluster_binding"] = await self._assert_cluster_binding()
        except ClusterBindingError as exc:
            report["cluster_binding"] = {"ok": False, "error": str(exc)}
            report["ok"] = False
            return report

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
                "SELECT p.oid::bigint AS function_oid, "
                "pg_get_userbyid(p.proowner) AS owner, "
                "format_type(p.prorettype, NULL) AS return_type, "
                "pg_get_function_identity_arguments(p.oid) AS identity_arguments, "
                "md5(pg_get_functiondef(p.oid)) AS definition_md5 "
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
                definition_md5=row["definition_md5"] if row else None,
                function_oid=row["function_oid"] if row else None,
            )
            schema_row = await migrate.fetchrow(
                "SELECT pg_get_userbyid(nspowner) AS owner FROM pg_namespace "
                "WHERE nspname = 'public'"
            )
            # PG15+/PG16: the public schema is owned by the pseudo-role
            # pg_database_owner, whose implicit member is the database owner
            # (the migration authority here) - equivalent ownership.
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
            app_create_on_public = await migrate.fetchval(
                "SELECT has_schema_privilege($1, 'public', 'CREATE')",
                self.app_role,
            )
            _record(
                "app_no_create_on_public_schema",
                not app_create_on_public,
                has_create=app_create_on_public,
                reason=(
                    "" if not app_create_on_public
                    else "runtime can create objects in schema public "
                         "(DROP+CREATE substitution path)"
                ),
            )
        finally:
            await migrate.close()

        app = await asyncpg.connect(self.app_url)
        try:
            app_user = await app.fetchval("SELECT current_user")
            _record(
                "runtime_differs_from_authority",
                app_user != self.migrate_role,
                runtime=app_user,
                authority=self.migrate_role,
                reason=(
                    "" if app_user != self.migrate_role
                    else "single-role topology: runtime IS the authority"
                ),
            )
            member_of_authority = await app.fetchval(
                "SELECT pg_has_role($1, $2, 'MEMBER') "
                "OR pg_has_role($1, $2, 'USAGE')",
                self.app_role, self.migrate_role,
            )
            _record(
                "runtime_not_member_of_authority",
                not member_of_authority,
                member_or_usage=bool(member_of_authority),
                reason=(
                    "" if not member_of_authority
                    else "SET ROLE escalation path exists from runtime to "
                         "the authority"
                ),
            )
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
            # Pure-catalog replace-capability proof: replacing or dropping
            # the existing guard requires being its owner, a superuser, or
            # a member of the owning role.  All three paths asserted closed.
            if row is not None:
                guard_owner = row["owner"]
                app_is_owner = guard_owner == self.app_role
                app_member_of_owner = await app.fetchval(
                    "SELECT pg_has_role($1, $2, 'MEMBER') "
                    "OR pg_has_role($1, $2, 'USAGE')",
                    self.app_role, guard_owner,
                )
                app_superuser = await app.fetchval(
                    "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
                )
                no_replace_path = (
                    not app_is_owner
                    and not bool(app_member_of_owner)
                    and not app_superuser
                )
                _record(
                    "app_no_replace_path_on_guard",
                    no_replace_path,
                    app_is_owner=app_is_owner,
                    app_member_of_owner=bool(app_member_of_owner),
                    app_superuser=app_superuser,
                    reason=(
                        "" if no_replace_path
                        else "runtime can replace or drop the guard via "
                             "ownership, membership or superuser"
                    ),
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
