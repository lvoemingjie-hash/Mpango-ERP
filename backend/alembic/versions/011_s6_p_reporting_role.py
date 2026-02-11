"""S6-P2: Reporting Role & Database Isolation

Revision ID: 011_s6_p_reporting_role
Revises: 010_s5_5_ledger_hardening
Create Date: 2026-02-07

Philosophy: "Reporting reads the truth. It never writes it."

Changes:
1. Create reporting_role (NOLOGIN) with SELECT-only permissions
2. Grant CONNECT, USAGE, SELECT on public and all tenant schemas
3. Set statement_timeout = 30s on reporting_role
4. Create reporting_user with membership in reporting_role
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '011_s6_p_reporting_role'
down_revision = '010_s5_5_ledger_hardening'
branch_labels = None
depends_on = None

# S8-SEC: Reporting user password — MUST be injected via environment variable.
import os as _os
REPORTING_USER_PASSWORD = _os.environ.get("REPORTING_USER_PASSWORD")
if not REPORTING_USER_PASSWORD:
    raise RuntimeError(
        "REPORTING_USER_PASSWORD environment variable must be set before running this migration"
    )


def upgrade() -> None:
    """
    Create reporting_role and reporting_user for read-only BI access.

    Steps:
    1. Create reporting_role (NOLOGIN) — the permission container
    2. Grant CONNECT on database
    3. Grant USAGE + SELECT on public schema
    4. Grant USAGE + SELECT on all tenant schemas
    5. Set statement_timeout = 30s (query safety net)
    6. Set default_transaction_read_only = on (belt-and-suspenders)
    7. Create reporting_user with LOGIN, member of reporting_role
    """
    connection = op.get_bind()
    db_name = connection.engine.url.database

    # =========================================================================
    # Step 1: Create reporting_role (idempotent)
    # =========================================================================
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reporting_role') THEN
                CREATE ROLE reporting_role NOLOGIN;
                RAISE NOTICE 'Created reporting_role';
            ELSE
                RAISE NOTICE 'reporting_role already exists';
            END IF;
        END
        $$;
    """)

    # =========================================================================
    # Step 2: Grant CONNECT on database
    # =========================================================================
    op.execute(sa.text(
        f'GRANT CONNECT ON DATABASE "{db_name}" TO reporting_role'
    ))

    # =========================================================================
    # Step 3: Grant USAGE + SELECT on public schema
    # =========================================================================
    op.execute("GRANT USAGE ON SCHEMA public TO reporting_role")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO reporting_role")
    # Ensure future tables in public are also readable
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT ON TABLES TO reporting_role"
    )

    # =========================================================================
    # Step 4: Grant USAGE + SELECT on all tenant schemas
    # =========================================================================
    result = connection.execute(sa.text("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name LIKE 't_%'
        ORDER BY schema_name
    """))
    tenant_schemas = [row[0] for row in result]

    for schema in tenant_schemas:
        op.execute(sa.text(
            f'GRANT USAGE ON SCHEMA "{schema}" TO reporting_role'
        ))
        op.execute(sa.text(
            f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}" TO reporting_role'
        ))
        op.execute(sa.text(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" '
            f'GRANT SELECT ON TABLES TO reporting_role'
        ))
        print(f"  ✅ Granted reporting_role access to schema: {schema}")

    # =========================================================================
    # Step 5: Set statement_timeout = 30s
    # =========================================================================
    op.execute("ALTER ROLE reporting_role SET statement_timeout = '30000'")

    # =========================================================================
    # Step 6: Set default_transaction_read_only = on
    # =========================================================================
    op.execute(
        "ALTER ROLE reporting_role SET default_transaction_read_only = on"
    )

    # =========================================================================
    # Step 7: Create reporting_user (idempotent)
    # =========================================================================
    op.execute(sa.text(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reporting_user') THEN
                CREATE USER reporting_user WITH PASSWORD '{REPORTING_USER_PASSWORD}';
                GRANT reporting_role TO reporting_user;
                RAISE NOTICE 'Created reporting_user with reporting_role membership';
            ELSE
                RAISE NOTICE 'reporting_user already exists';
            END IF;
        END
        $$;
    """))

    # =========================================================================
    # Step 8: Apply session defaults directly on reporting_user
    # =========================================================================
    # ALTER ROLE ... SET on a parent role is NOT inherited by member users.
    # We must set these directly on reporting_user for them to take effect.
    op.execute(
        "ALTER ROLE reporting_user SET statement_timeout = '30000'"
    )
    op.execute(
        "ALTER ROLE reporting_user SET default_transaction_read_only = on"
    )

    print(f"\n✅ Reporting role created with 30s timeout")
    print(f"✅ Reporting user created (member of reporting_role)")
    print(f"✅ Granted SELECT on {len(tenant_schemas)} tenant schema(s) + public")
    print(f"🔒 Reporting path is read-only with 30s query timeout")


def downgrade() -> None:
    """
    Remove reporting_user and reporting_role.

    WARNING: This removes all reporting access!
    """
    connection = op.get_bind()
    db_name = connection.engine.url.database

    # Revoke default privileges from tenant schemas
    result = connection.execute(sa.text("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name LIKE 't_%'
        ORDER BY schema_name
    """))
    tenant_schemas = [row[0] for row in result]

    for schema in tenant_schemas:
        op.execute(sa.text(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" '
            f'REVOKE SELECT ON TABLES FROM reporting_role'
        ))
        op.execute(sa.text(
            f'REVOKE ALL ON ALL TABLES IN SCHEMA "{schema}" FROM reporting_role'
        ))
        op.execute(sa.text(
            f'REVOKE USAGE ON SCHEMA "{schema}" FROM reporting_role'
        ))

    # Revoke public schema privileges
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT ON TABLES FROM reporting_role"
    )
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM reporting_role")
    op.execute("REVOKE USAGE ON SCHEMA public FROM reporting_role")

    # Revoke database connect
    op.execute(sa.text(
        f'REVOKE CONNECT ON DATABASE "{db_name}" FROM reporting_role'
    ))

    # Drop user and role
    op.execute("DROP USER IF EXISTS reporting_user")
    op.execute("DROP ROLE IF EXISTS reporting_role")

    print(f"⚠️  Reporting user and role removed")
    print(f"⚠️  WARNING: Reporting access has been revoked!")
