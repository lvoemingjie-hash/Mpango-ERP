"""
Mpango ERP Backend - Main FastAPI Application.

This is the skeleton implementation that proves OpenAPI ↔ DB ↔ FastAPI alignment.
No business logic is implemented - all endpoints return 501 Not Implemented.
"""
import yaml
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from core.config import get_settings
from api.v1 import auth, users, roles, orders


# Get settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    print("🚀 Mpango ERP Backend starting...")
    print(f"📋 Loading OpenAPI spec from docs/contracts/openapi.yaml")
    yield
    print("🛑 Mpango ERP Backend shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Mpango ERP API",
    description="Multi-tenant ERP system for African wholesale-retail operations (Skeleton)",
    version="1.0.0",
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


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(roles.router, prefix="/api/v1/roles", tags=["roles"])
app.include_router(orders.router, prefix="/api/v1/orders", tags=["orders"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Mpango ERP API",
        "version": "1.0.0",
        "status": "skeleton",
        "note": "All endpoints return 501 Not Implemented"
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Implements requirement 4.5: Include health check endpoint at /health
    """
    return {
        "status": "healthy",
        "service": "mpango-erp-backend",
        "version": "1.0.0"
    }
