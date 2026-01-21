"""FastAPI application configuration helpers."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import Settings


def configure_app(app: FastAPI, settings: Settings) -> None:
    """Wire middleware and routes onto the FastAPI application."""
    # Middleware stack
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from api.middleware.auth import AuthenticationMiddleware
    from api.middleware.idempotency import IdempotencyMiddleware

    app.add_middleware(AuthenticationMiddleware)
    app.add_middleware(IdempotencyMiddleware)

    # Routers
    from api.v1 import auth, users, roles, orders, health

    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    app.include_router(roles.router, prefix="/api/v1/roles", tags=["roles"])
    app.include_router(orders.router, prefix="/api/v1/orders", tags=["orders"])
