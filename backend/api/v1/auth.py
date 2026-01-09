from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_db, get_tenant_db
from schemas.auth import LoginRequest, LoginResponse, RefreshTokenRequest
from crud.wholesaler import wholesaler
from crud.user import user
from core.security import create_access_token, create_refresh_token, verify_token
from core.exceptions import invalid_credentials, tenant_not_found

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    用户登录
    
    1. 验证租户代码
    2. 切换到租户schema
    3. 验证用户凭据
    4. 生成JWT令牌
    """
    # 1. 验证租户代码（在public schema中查询）
    tenant = await wholesaler.get_by_code(db, code=login_data.tenant_code)
    if not tenant:
        raise tenant_not_found()
    
    # 2. 获取租户schema
    tenant_schema = tenant.get_tenant_schema()
    
    # 3. 在租户schema中验证用户
    async with get_tenant_db(tenant_schema) as tenant_db:
        db_user = await user.authenticate(
            tenant_db, 
            email=login_data.email, 
            password=login_data.password
        )
        
        if not db_user:
            raise invalid_credentials()
        
        if not await user.is_active(db_user):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
    
    # 4. 生成JWT令牌
    token_data = {
        "user_id": str(db_user.id),
        "tenant_id": str(tenant.id),
        "tenant_schema": tenant_schema
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(db_user.id),
        tenant_id=str(tenant.id),
        tenant_schema=tenant_schema
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """刷新访问令牌"""
    try:
        payload = verify_token(refresh_data.refresh_token)
        
        # 验证用户仍然存在且活跃
        tenant_schema = payload.get("tenant_schema")
        user_id = payload.get("user_id")
        
        async with get_tenant_db(tenant_schema) as tenant_db:
            db_user = await user.get(tenant_db, id=user_id)
            if not db_user or not await user.is_active(db_user):
                raise invalid_credentials()
        
        # 生成新的令牌
        token_data = {
            "user_id": payload.get("user_id"),
            "tenant_id": payload.get("tenant_id"),
            "tenant_schema": payload.get("tenant_schema")
        }
        
        access_token = create_access_token(token_data)
        new_refresh_token = create_refresh_token(token_data)
        
        return LoginResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            user_id=payload.get("user_id"),
            tenant_id=payload.get("tenant_id"),
            tenant_schema=payload.get("tenant_schema")
        )
        
    except Exception:
        raise invalid_credentials()


@router.post("/logout")
async def logout():
    """登出（客户端需要删除令牌）"""
    return {"message": "Successfully logged out"}