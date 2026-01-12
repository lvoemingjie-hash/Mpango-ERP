"""
Wholesaler model - Tenant registry in public schema.
Implements database_contract.md public.wholesalers table.
"""
from typing import Optional

from sqlalchemy import String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from models.base import PublicBaseModel


class Wholesaler(PublicBaseModel):
    """
    Wholesaler model - stored in public schema as tenant registry.
    
    Each wholesaler represents a tenant with their own schema.
    The tenant_schema is derived from the wholesaler's UUID.
    
    Implements database_contract.md:
    - public.wholesalers table
    - code: varchar(32), UNIQUE, NOT NULL, regex ^[A-Z0-9]+$
    - name: varchar(255), NOT NULL
    - address: text, NULL
    - contact: text, NULL
    - plan_type: varchar(50), NULL
    """
    __tablename__ = "wholesalers"
    __table_args__ = (
        Index('ix_wholesalers_code', 'code', unique=True),
        {"schema": "public"}
    )
    
    code: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
        comment="Tenant code, regex ^[A-Z0-9]+$, immutable"
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    address: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    contact: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    plan_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    
    def get_tenant_schema(self) -> str:
        """
        Get the tenant schema name derived from wholesaler UUID.
        Format: t_<uuid_without_dashes>
        
        Per multi_tenancy_spec.md section 2.2
        """
        return f"t_{str(self.id).replace('-', '')}"
    
    @staticmethod
    def derive_schema_from_id(tenant_id: str) -> str:
        """
        Derive tenant schema name from tenant_id UUID string.
        
        Args:
            tenant_id: UUID string (with or without dashes)
            
        Returns:
            Schema name in format t_<uuid_without_dashes>
        """
        return f"t_{tenant_id.replace('-', '')}"
