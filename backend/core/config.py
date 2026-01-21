"""
Configuration module for Mpango ERP Backend.
Loads settings from environment variables with .env file support.
"""
from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True)

    # Database - REQUIRED
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/mpango_dev",
        description="PostgreSQL connection string (defaults to local dev instance)",
    )
    DATABASE_ECHO: bool = Field(
        default=False,
        description="Echo SQL queries for debugging"
    )
    
    # Security - REQUIRED
    SECRET_KEY: str = Field(
        default="dev-secret-key-change-me",
        description="Secret key for JWT signing (use env override in production)",
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
    
@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Raises ValidationError if required config is missing.
    """
    return Settings()


# Backwards compatible alias for modules that previously imported settings directly
settings = get_settings()
