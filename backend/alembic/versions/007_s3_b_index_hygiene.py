"""S3-B: Index Hygiene - Add missing indexes for performance

Revision ID: 007_s3_b_index_hygiene
Revises: 006_phase_b6_payments_idempotency_key
Create Date: 2026-02-06

S3-B: Database Hygiene & N+1 Elimination
Philosophy: "Single Request < 10 Queries"

This migration adds missing indexes on commonly filtered/joined columns:
- is_deleted (used in almost every query with WHERE is_deleted = false)
- Foreign keys that weren't auto-indexed
- Common filter columns (email, status, created_at)

Index Naming Convention: ix_{table_name}_{column_name}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '007_s3_b_index_hygiene'
down_revision: Union[str, None] = '006_phase_b6_payments_idempotency_key'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    S3-B: Add missing indexes for query performance.
    
    Critical indexes for multi-tenancy and common queries:
    1. is_deleted - Used in almost every WHERE clause
    2. Foreign keys - Used in JOINs
    3. Common filters - email, status, created_at
    """
    
    # ========================================
    # Tenant Schema Indexes
    # ========================================
    
    # Users table
    # - is_deleted: Used in all user queries
    # - is_active: Used for filtering active users
    op.create_index('ix_users_is_deleted', 'users', ['is_deleted'], unique=False)
    op.create_index('ix_users_is_active', 'users', ['is_active'], unique=False)
    op.create_index('ix_users_created_at', 'users', ['created_at'], unique=False)
    
    # Roles table
    # - is_deleted: Used in all role queries
    op.create_index('ix_roles_is_deleted', 'roles', ['is_deleted'], unique=False)
    op.create_index('ix_roles_created_at', 'roles', ['created_at'], unique=False)
    
    # Permissions table
    # - is_deleted: Used in all permission queries
    op.create_index('ix_permissions_is_deleted', 'permissions', ['is_deleted'], unique=False)
    op.create_index('ix_permissions_created_at', 'permissions', ['created_at'], unique=False)
    
    # Orders table
    # - is_deleted: Used in all order queries
    op.create_index('ix_orders_is_deleted', 'orders', ['is_deleted'], unique=False)
    
    # Order Items table
    # - is_deleted: Used in all order item queries
    op.create_index('ix_order_items_is_deleted', 'order_items', ['is_deleted'], unique=False)
    op.create_index('ix_order_items_created_at', 'order_items', ['created_at'], unique=False)
    
    # SKUs table
    # - is_deleted: Used in all SKU queries (already has is_active, created_at)
    op.create_index('ix_skus_is_deleted', 'skus', ['is_deleted'], unique=False)
    
    # Inventory Stocks table
    # - is_deleted: Used in all inventory queries
    op.create_index('ix_inventory_stocks_is_deleted', 'inventory_stocks', ['is_deleted'], unique=False)
    op.create_index('ix_inventory_stocks_created_at', 'inventory_stocks', ['created_at'], unique=False)
    
    # Payments table (if exists)
    # - is_deleted: Used in all payment queries
    # - order_id: Already indexed in 005_phase_b5
    # - status: Common filter
    op.create_index('ix_payments_is_deleted', 'payments', ['is_deleted'], unique=False)
    op.create_index('ix_payments_status', 'payments', ['status'], unique=False)
    op.create_index('ix_payments_created_at', 'payments', ['created_at'], unique=False)
    
    # Association tables
    # - is_deleted: Used in all association queries
    op.create_index('ix_user_roles_is_deleted', 'user_roles', ['is_deleted'], unique=False)
    op.create_index('ix_role_permissions_is_deleted', 'role_permissions', ['is_deleted'], unique=False)
    
    # ========================================
    # Public Schema Indexes
    # ========================================
    
    # Wholesalers table
    # - is_deleted: Used in all wholesaler queries
    op.create_index('ix_wholesalers_is_deleted', 'wholesalers', ['is_deleted'], unique=False, schema='public')
    op.create_index('ix_wholesalers_created_at', 'wholesalers', ['created_at'], unique=False, schema='public')
    
    # Retailers table
    # - is_deleted: Used in all retailer queries
    op.create_index('ix_retailers_is_deleted', 'retailers', ['is_deleted'], unique=False, schema='public')
    op.create_index('ix_retailers_created_at', 'retailers', ['created_at'], unique=False, schema='public')
    
    # Invitations table
    # - is_deleted: Used in all invitation queries
    # - status: Common filter
    op.create_index('ix_invitations_is_deleted', 'invitations', ['is_deleted'], unique=False, schema='public')
    op.create_index('ix_invitations_status', 'invitations', ['status'], unique=False, schema='public')
    op.create_index('ix_invitations_created_at', 'invitations', ['created_at'], unique=False, schema='public')
    
    # Bindings table
    # - is_deleted: Used in all binding queries
    op.create_index('ix_bindings_is_deleted', 'wholesaler_retailer_bindings', ['is_deleted'], unique=False, schema='public')
    op.create_index('ix_bindings_created_at', 'wholesaler_retailer_bindings', ['created_at'], unique=False, schema='public')


def downgrade() -> None:
    """Remove S3-B indexes."""
    
    # Public schema indexes
    op.drop_index('ix_bindings_created_at', table_name='wholesaler_retailer_bindings', schema='public')
    op.drop_index('ix_bindings_is_deleted', table_name='wholesaler_retailer_bindings', schema='public')
    op.drop_index('ix_invitations_created_at', table_name='invitations', schema='public')
    op.drop_index('ix_invitations_status', table_name='invitations', schema='public')
    op.drop_index('ix_invitations_is_deleted', table_name='invitations', schema='public')
    op.drop_index('ix_retailers_created_at', table_name='retailers', schema='public')
    op.drop_index('ix_retailers_is_deleted', table_name='retailers', schema='public')
    op.drop_index('ix_wholesalers_created_at', table_name='wholesalers', schema='public')
    op.drop_index('ix_wholesalers_is_deleted', table_name='wholesalers', schema='public')
    
    # Association tables
    op.drop_index('ix_role_permissions_is_deleted', table_name='role_permissions')
    op.drop_index('ix_user_roles_is_deleted', table_name='user_roles')
    
    # Tenant schema indexes
    op.drop_index('ix_payments_created_at', table_name='payments')
    op.drop_index('ix_payments_status', table_name='payments')
    op.drop_index('ix_payments_is_deleted', table_name='payments')
    op.drop_index('ix_inventory_stocks_created_at', table_name='inventory_stocks')
    op.drop_index('ix_inventory_stocks_is_deleted', table_name='inventory_stocks')
    op.drop_index('ix_skus_is_deleted', table_name='skus')
    op.drop_index('ix_order_items_created_at', table_name='order_items')
    op.drop_index('ix_order_items_is_deleted', table_name='order_items')
    op.drop_index('ix_orders_is_deleted', table_name='orders')
    op.drop_index('ix_permissions_created_at', table_name='permissions')
    op.drop_index('ix_permissions_is_deleted', table_name='permissions')
    op.drop_index('ix_roles_created_at', table_name='roles')
    op.drop_index('ix_roles_is_deleted', table_name='roles')
    op.drop_index('ix_users_created_at', table_name='users')
    op.drop_index('ix_users_is_active', table_name='users')
    op.drop_index('ix_users_is_deleted', table_name='users')
