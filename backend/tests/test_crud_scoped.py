import pytest

from crud.base import CRUDBase
from database.base import BaseModel as DBBaseModel


class _FakeDB:
    def __init__(self, info=None):
        self.info = info


def test_scoped_requires_tenant_schema_in_session_info():
    crud = CRUDBase(DBBaseModel)

    with pytest.raises(RuntimeError) as exc:
        crud.scoped(_FakeDB(info={}))

    assert str(exc.value) == "Tenant session required"


def test_scoped_allows_tenant_session_info():
    crud = CRUDBase(DBBaseModel)

    scoped = crud.scoped(_FakeDB(info={"tenant_schema": "t_test"}))

    # Minimal smoke assertion: scoped wrapper created
    assert scoped is not None
