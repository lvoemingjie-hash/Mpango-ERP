"""
Configuration module for Mpango ERP Backend.
Loads settings from environment variables with .env file support.

S2-1: Implements strict validation and fail-fast behavior for production secrets.
"""
import os
import sys
from functools import lru_cache
from typing import List, Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    S2-1 Compliance:
    - Validates required secrets on startup
    - Fails fast if production secrets are missing
    - Enforces MPANGO_ENV constraints
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Environment - REQUIRED (S2-1)
    MPANGO_ENV: Literal["production", "staging", "test"] = Field(
        default="production",
        description="Environment mode: production, staging, or test"
    )

    # Database - REQUIRED (S2-1)
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/mpango_dev",
        description="PostgreSQL connection string (defaults to local dev instance)",
    )
    DATABASE_ECHO: bool = Field(
        default=False,
        description="Echo SQL queries for debugging"
    )

    # Redis - REQUIRED (S2-1)
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string for caching and sessions"
    )

    # Security - REQUIRED (S2-1)
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

    # Operational settings
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    REQUEST_TIMEOUT_SECONDS: int = Field(
        default=30,
        description="Request timeout in seconds"
    )
    DB_POOL_SIZE: int = Field(
        default=5,
        description="Database connection pool size"
    )
    DB_MAX_OVERFLOW: int = Field(
        default=10,
        description="Database connection pool max overflow"
    )
    DB_CONNECT_TIMEOUT: int = Field(
        default=10,
        description="Database connection timeout in seconds"
    )

    # Feature flags
    ENABLE_METRICS: bool = Field(
        default=False,
        description="Enable basic metrics collection"
    )
    ENABLE_REQUEST_LOGGING: bool = Field(
        default=True,
        description="Enable detailed request logging"
    )

    # S3-A: SQL Profiling Configuration
    SLOW_QUERY_THRESHOLD_MS: int = Field(
        default=100,
        description="Threshold in milliseconds for slow query warnings"
    )
    ENABLE_SQL_PROFILING: bool = Field(
        default=True,
        description="Enable SQL query profiling and metrics"
    )

    @field_validator("MPANGO_ENV")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate MPANGO_ENV is one of allowed values."""
        if v not in ("production", "staging", "test"):
            raise ValueError(
                f"MPANGO_ENV must be 'production', 'staging', or 'test', got '{v}'"
            )
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate DATABASE_URL format."""
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError(
                "DATABASE_URL must start with 'postgresql://' or 'postgres://'"
            )
        return v

    @field_validator("REDIS_URL")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        """Validate REDIS_URL format."""
        if not v.startswith("redis://"):
            raise ValueError("REDIS_URL must start with 'redis://'")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """S2.5: Validate SECRET_KEY meets strict security requirements.

        Requirements:
        - Minimum 32 characters
        - No weak/common substrings
        - High entropy required for production
        """
        # Check minimum length
        if len(v) < 32:
            raise ValueError(
                f"SECRET_KEY must be at least 32 characters, got {len(v)}"
            )

        # S2.5: Check for weak/common substrings
        weak_patterns = [
            "secret", "default", "password", "123456", "change-me",
            "changeme", "admin", "test", "demo", "example", "sample",
            "qwerty", "abc123", "letmein", "welcome", "monkey"
        ]

        v_lower = v.lower()
        for pattern in weak_patterns:
            if pattern in v_lower:
                raise ValueError(
                    f"SECRET_KEY contains weak substring '{pattern}'. "
                    f"Use a cryptographically secure random key. "
                    f"Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
                )

        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """S2-1: Fail fast if production secrets are using default values.

        In production mode, we MUST NOT allow default/dev secrets.
        This prevents accidental deployment with insecure defaults.
        """
        if self.MPANGO_ENV == "production":
            # Check for default DATABASE_URL
            if "postgres:postgres@localhost" in self.DATABASE_URL:
                print("❌ FATAL: Production mode detected with default DATABASE_URL", file=sys.stderr)
                print("   Set DATABASE_URL environment variable to production database", file=sys.stderr)
                raise ValueError(
                    "Production mode requires non-default DATABASE_URL. "
                    "Default dev database URL detected."
                )

            # Check for default REDIS_URL
            if self.REDIS_URL == "redis://localhost:6379/0":
                print("❌ FATAL: Production mode detected with default REDIS_URL", file=sys.stderr)
                print("   Set REDIS_URL environment variable to production Redis", file=sys.stderr)
                raise ValueError(
                    "Production mode requires non-default REDIS_URL. "
                    "Default dev Redis URL detected."
                )

            # Check for default SECRET_KEY
            if "dev-secret-key" in self.SECRET_KEY or "change-me" in self.SECRET_KEY:
                print("❌ FATAL: Production mode detected with default SECRET_KEY", file=sys.stderr)
                print("   Set SECRET_KEY environment variable to a secure random key", file=sys.stderr)
                raise ValueError(
                    "Production mode requires non-default SECRET_KEY. "
                    "Default dev secret key detected."
                )

        return self


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    S2-1 Compliance:
    - Raises ValidationError if required config is missing
    - Raises ValueError if production secrets are using defaults
    - Application will CRASH on startup if validation fails
    """
    return Settings()


def validate_startup_config() -> Settings:
    """S2-1: Validate configuration on application startup.

    This function is called during app startup to ensure all required
    secrets are present and valid. If validation fails, the application
    will crash immediately (fail fast).

    Returns:
        Settings: Validated settings instance

    Raises:
        ValidationError: If required config is missing or invalid
        ValueError: If production secrets are using default values
    """
    try:
        settings = get_settings()

        # Log successful validation
        print(f"✅ Configuration validated successfully")
        print(f"   Environment: {settings.MPANGO_ENV}")
        print(f"   Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")
        print(f"   Redis: {settings.REDIS_URL.split('@')[1] if '@' in settings.REDIS_URL else 'configured'}")
        print(f"   Secret Key: {'*' * 32} (length: {len(settings.SECRET_KEY)})")

        return settings

    except Exception as e:
        print(f"\n❌ CONFIGURATION VALIDATION FAILED", file=sys.stderr)
        print(f"   Error: {str(e)}", file=sys.stderr)
        print(f"\n   Application startup aborted.", file=sys.stderr)
        print(f"   Please check your .env file or environment variables.\n", file=sys.stderr)
        raise


# Backwards compatible alias for modules that previously imported settings directly
settings = get_settings()
