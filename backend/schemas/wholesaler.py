from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class WholesalerBase(BaseModel):
    """批发商基础字段"""
    code: str
    name: str
    address: Optional[str] = None
    contact: Optional[str] = None
    plan_type: Optional[str] = None


class WholesalerCreate(WholesalerBase):
    """创建批发商"""
    pass


class WholesalerUpdate(BaseModel):
    """更新批发商"""
    name: Optional[str] = None
    address: Optional[str] = None
    contact: Optional[str] = None
    plan_type: Optional[str] = None


class WholesalerRead(WholesalerBase):
    """批发商响应"""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
