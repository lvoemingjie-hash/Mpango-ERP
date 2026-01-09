from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1 import auth, users
from core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    print("🚀 Mpango ERP Backend starting...")
    yield
    # 关闭时执行
    print("🛑 Mpango ERP Backend shutting down...")


app = FastAPI(
    title="Mpango ERP API",
    description="Multi-tenant ERP system for African wholesale-retail operations",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])

@app.get("/")
async def root():
    return {"message": "Mpango ERP API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}