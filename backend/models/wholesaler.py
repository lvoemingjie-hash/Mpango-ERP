from sqlalchemy import Column, String, Text
from database.base import BaseModel


class Wholesaler(BaseModel):
    """批发商模型 - 存储在public schema中作为租户注册表"""
    __tablename__ = "wholesalers"
    
    code = Column(String(32), unique=True, nullable=False, index=True)  # tenant_code
    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    contact = Column(Text, nullable=True)
    plan_type = Column(String(50), nullable=True)
    
    def get_tenant_schema(self) -> str:
        """获取租户schema名称"""
        return f"t_{str(self.id).replace('-', '')}"