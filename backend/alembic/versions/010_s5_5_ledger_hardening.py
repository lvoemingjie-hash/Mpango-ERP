"""S5.5-1: Ledger Hardening - Database-Level Immutability

Revision ID: 010_s5_5_ledger_hardening
Revises: 009_s5_b_financial_ledger
Create Date: 2026-02-06

Philosophy: "The Ledger is write-only. No exceptions."

Changes:
1. Add PL/pgSQL trigger function to prevent UPDATE/DELETE on ledger_entries
2. Add entry_version column for versioning
3. Add hash column for future blockchain/crypto-hashing
4. Apply trigger to all tenant schemas
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '010_s5_5_ledger_hardening'
down_revision = '009_s5_b_financial_ledger'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Apply ledger hardening to all tenant schemas.
    
    Steps:
    1. Create trigger function in public schema (shared across all tenants)
    2. Add versioning and hash columns to ledger_entries
    3. Attach trigger to ledger_entries in each tenant schema
    """
    
    # =========================================================================
    # Step 1: Create trigger function in public schema
    # =========================================================================
    # This function will be shared across all tenant schemas
    op.execute("""
        CREATE OR REPLACE FUNCTION public.prevent_ledger_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Block UPDATE operations
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'Ledger entries are immutable. UPDATE operations are not allowed.'
                    USING ERRCODE = 'integrity_constraint_violation',
                          HINT = 'Ledger entries cannot be modified after creation. Create a correction entry instead.';
            END IF;
            
            -- Block DELETE operations
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Ledger entries are immutable. DELETE operations are not allowed.'
                    USING ERRCODE = 'integrity_constraint_violation',
                          HINT = 'Ledger entries cannot be deleted. Create a reversal entry instead.';
            END IF;
            
            -- This should never be reached, but return OLD for safety
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # =========================================================================
    # Step 2: Get all tenant schemas
    # =========================================================================
    # Query to find all schemas that start with 't_' (tenant schemas)
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT schema_name 
        FROM information_schema.schemata 
        WHERE schema_name LIKE 't_%'
        ORDER BY schema_name
    """))
    tenant_schemas = [row[0] for row in result]
    
    # =========================================================================
    # Step 3: Apply changes to each tenant schema
    # =========================================================================
    for schema in tenant_schemas:
        # Add entry_version column (default 1)
        op.execute(sa.text(f"""
            ALTER TABLE "{schema}".ledger_entries 
            ADD COLUMN IF NOT EXISTS entry_version INTEGER NOT NULL DEFAULT 1
        """))
        
        # Add hash column (nullable, for future use)
        op.execute(sa.text(f"""
            ALTER TABLE "{schema}".ledger_entries 
            ADD COLUMN IF NOT EXISTS hash VARCHAR(64) NULL
        """))
        
        # Add comment to entry_version column
        op.execute(sa.text(f"""
            COMMENT ON COLUMN "{schema}".ledger_entries.entry_version IS 
            'Entry format version for schema evolution tracking'
        """))
        
        # Add comment to hash column
        op.execute(sa.text(f"""
            COMMENT ON COLUMN "{schema}".ledger_entries.hash IS 
            'Cryptographic hash for blockchain/audit trail (future use)'
        """))
        
        # Create trigger to prevent modifications
        op.execute(sa.text(f"""
            DROP TRIGGER IF EXISTS prevent_ledger_modification_trigger 
            ON "{schema}".ledger_entries
        """))
        
        op.execute(sa.text(f"""
            CREATE TRIGGER prevent_ledger_modification_trigger
            BEFORE UPDATE OR DELETE ON "{schema}".ledger_entries
            FOR EACH ROW
            EXECUTE FUNCTION public.prevent_ledger_modification()
        """))
        
        print(f"✅ Applied ledger hardening to schema: {schema}")
    
    print(f"\n✅ Ledger hardening applied to {len(tenant_schemas)} tenant schema(s)")
    print("🔒 Ledger is now write-only at database level")


def downgrade() -> None:
    """
    Remove ledger hardening from all tenant schemas.
    
    WARNING: This removes immutability protection!
    """
    
    # Get all tenant schemas
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT schema_name 
        FROM information_schema.schemata 
        WHERE schema_name LIKE 't_%'
        ORDER BY schema_name
    """))
    tenant_schemas = [row[0] for row in result]
    
    # Remove triggers and columns from each tenant schema
    for schema in tenant_schemas:
        # Drop trigger
        op.execute(sa.text(f"""
            DROP TRIGGER IF EXISTS prevent_ledger_modification_trigger 
            ON "{schema}".ledger_entries
        """))
        
        # Drop columns
        op.execute(sa.text(f"""
            ALTER TABLE "{schema}".ledger_entries 
            DROP COLUMN IF EXISTS hash
        """))
        
        op.execute(sa.text(f"""
            ALTER TABLE "{schema}".ledger_entries 
            DROP COLUMN IF EXISTS entry_version
        """))
        
        print(f"⚠️  Removed ledger hardening from schema: {schema}")
    
    # Drop trigger function
    op.execute("""
        DROP FUNCTION IF EXISTS public.prevent_ledger_modification() CASCADE
    """)
    
    print(f"\n⚠️  Ledger hardening removed from {len(tenant_schemas)} tenant schema(s)")
    print("⚠️  WARNING: Ledger is no longer protected at database level!")
