"""
Mpango ERP Backend - Main FastAPI Application.

v0.1.0-platform - Stabilization release with:
- Full RBAC enforcement
- Tenant isolation
- Order state machine
- Idempotency middleware
- Health checks
"""
import yaml
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from api.app import configure_app
from core.config import get_settings
from core.logging_config import setup_logging


# Setup structured logging
setup_logging(level="INFO")

# Get settings
settings = get_settings()

# Version
__version__ = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    print(f"🚀 Mpango ERP Backend v{__version__} starting...")
    print(f"📋 Loading OpenAPI spec from docs/contracts/openapi.yaml")
    yield
    print("🛑 Mpango ERP Backend shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Mpango ERP API",
    description="Multi-tenant ERP system for African wholesale-retail operations",
    version=__version__,
    lifespan=lifespan
)


def custom_openapi():
    """
    Load and serve OpenAPI specification from canonical source.
    
    Implements requirement 4.1: Load OpenAPI spec from docs/contracts/openapi.yaml
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    try:
        # Load canonical OpenAPI spec
        with open("docs/contracts/openapi.yaml", "r") as f:
            openapi_schema = yaml.safe_load(f)
        
        # Cache the schema
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    except FileNotFoundError:
        # Fallback to FastAPI's generated schema if file not found
        print("⚠️  Warning: docs/contracts/openapi.yaml not found, using generated schema")
        return get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )


# Override OpenAPI schema generation
app.openapi = custom_openapi


# Configure middleware and routers per Boot Contract layering
configure_app(app, settings)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Mpango ERP API",
        "version": __version__,
        "status": "v0.1-platform",
        "endpoints": {
            "health": "/health",
            "api": "/api/v1"
        }
    }
