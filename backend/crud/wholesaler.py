from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crud.base import CRUDBase
from models.wholesaler import Wholesaler
from schemas.wholesaler import WholesalerCreate, WholesalerUpdate


class CRUDWholesaler(CRUDBase[Wholesaler, WholesalerCreate, WholesalerUpdate]):
    async def get_by_code(self, db: AsyncSession, *, code: str) -> Optional[Wholesaler]:
        """根据租户代码获取批发商"""
        result = await db.execute(
            select(Wholesaler).where(
                Wholesaler.code == code,
                Wholesaler.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    async def create_with_schema(
        self, 
        db: AsyncSession, 
        *, 
        obj_in: WholesalerCreate
    ) -> Wholesaler:
        """创建批发商并创建对应的租户schema"""
        from database.session import create_tenant_schema
        
        # 创建批发商记录
        wholesaler = await self.create(db, obj_in=obj_in)
        
        # 创建租户schema
        tenant_schema = wholesaler.get_tenant_schema()
        await create_tenant_schema(tenant_schema)
        
        return wholesaler


# 创建CRUD实例
wholesaler = CRUDWholesaler(Wholesaler)