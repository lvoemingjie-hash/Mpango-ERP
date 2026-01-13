"""
Configuration module for Mpango ERP Backend.
Loads settings from environment variables with .env file support.
"""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database - REQUIRED
    DATABASE_URL: str = Field(
        ...,
        description="PostgreSQL connection string"
    )
    DATABASE_ECHO: bool = Field(
        default=False,
        description="Echo SQL queries for debugging"
    )
    
    # Security - REQUIRED
    SECRET_KEY: str = Field(
        ...,
        description="Secret key for JWT signing"
    )
    ALGORITHM: str = Field(
        default="HS256",
        description="JWT signing algorithm"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="Access token expiration in minutes"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        description="Refresh token expiration in days"
    )
    
    # Application
    APP_NAME: str = Field(
        default="Mpango ERP",
        description="Application name"
    )
    DEBUG: bool = Field(
        default=False,
        description="Debug mode"
    )
    
    # CORS
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins"
    )
    
    # Multi-tenancy
    DEFAULT_TENANT_SCHEMA: str = Field(
        default="t_dev",
        description="Default tenant schema for development"
    )
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Raises ValidationError if required config is missing.
    """
    return Settings()


# For backward compatibility - will raise if required vars missing
try:
    settings = Settings()
except Exception:
    # Allow import without .env for testing/CI
    settings = None  # type: ignore
