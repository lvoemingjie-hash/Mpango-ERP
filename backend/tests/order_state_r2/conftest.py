"""R2 test fixtures — re-export the R1 fixture chain (real ASGI app, real
PG16 task database, tenant provisioning pool, cashier identity)."""
from tests.order_state_r1.conftest import (  # noqa: F401
    cashier_identity,
    provisioned_pool,
    r1_client,
    s2_clean_db,
    two_tenants,
)
