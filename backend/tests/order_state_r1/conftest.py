"""R1 test fixtures: re-exports only; bodies live in support.py and the
shared S2/I2B fixtures."""
from tests.order_state_r1.support import r1_client  # noqa: F401
from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: F401
    provisioned_pool,
    s2_clean_db,
)
from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (  # noqa: F401
    cashier_identity,
)
