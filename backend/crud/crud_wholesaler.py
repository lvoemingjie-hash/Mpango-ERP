"""
CRUD class for Wholesaler model.
Operates on public schema.
"""
from crud.base import CRUDBase
from models.wholesaler import Wholesaler
from schemas.wholesaler import WholesalerCreate, WholesalerUpdate


class CRUDWholesaler(CRUDBase[Wholesaler, WholesalerCreate, WholesalerUpdate]):
    pass


wholesaler = CRUDWholesaler(Wholesaler)
