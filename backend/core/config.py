from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://mpango:mpango123@localhost:5432/mpango_erp"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:5173",  # Vite dev server (避免3000端口)
        "http://localhost:3001",  # 备用前端端口
        "http://127.0.0.1:5173",
    ]
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # AWS S3 (可选)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "mpango-erp-files"
    
    # Multi-tenancy
    DEFAULT_TENANT_SCHEMA: str = "t_dev"  # 开发环境默认租户
    
    class Config:
        env_file = ".env"


settings = Settings()