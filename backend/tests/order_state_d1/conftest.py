"""Order-state D1 task-test fixtures (re-exported from support.py).

Kept as a pure re-export: the fixture bodies and their ownership semantics
live in ``support.py`` next to the assertion helpers they share.
"""
from tests.order_state_d1.support import (  # noqa: F401
    osd1_cashier,
    osd1_client,
)
from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (  # noqa: F401
    provisioned_pool,
    s2_clean_db,
)
from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (  # noqa: F401
    cashier_identity,
)
