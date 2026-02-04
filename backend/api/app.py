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
    from api.middleware.metrics import BasicMetricsMiddleware
    from auth.factory import get_auth_strategy

    app.add_middleware(BasicMetricsMiddleware)
    app.add_middleware(AuthenticationMiddleware, strategy=get_auth_strategy())
    app.add_middleware(IdempotencyMiddleware)

    # Routers
    from api.v1 import auth, users, roles, orders, health, invitations, retailers, skus, inventory, metrics, payments

    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    app.include_router(roles.router, prefix="/api/v1/roles", tags=["roles"])
    app.include_router(orders.router, prefix="/api/v1/orders", tags=["orders"])
    app.include_router(skus.router, prefix="/api/v1/skus", tags=["skus"])
    app.include_router(inventory.router, prefix="/api/v1/inventory", tags=["inventory"])
    app.include_router(invitations.router, prefix="/api/v1", tags=["invitations"])
    app.include_router(retailers.router, prefix="/api/v1", tags=["retailers"])
    app.include_router(payments.router, prefix="/api/v1/payments", tags=["payments"])
