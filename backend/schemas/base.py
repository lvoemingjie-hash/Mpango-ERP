"""
v0.1.9: CamelCase Adapter Base Schema.

WHY THIS IS HARDENING, NOT A BUG FIX:
    The existing API returns snake_case JSON. Frontend consumes snake_case.
    This base class introduces camelCase acceptance on INPUT (validation)
    without changing OUTPUT (serialization). This eliminates future friction
    when the frontend migrates to camelCase conventions.

BEHAVIOR:
    - Input:  accepts BOTH snake_case ("plan_type") AND camelCase ("planType")
    - Output: remains snake_case ("plan_type") — NO breaking change
    - When ready to switch output to camelCase, add:
        serialization_alias=to_camel  to the AliasGenerator

USAGE:
    from schemas.base import CamelModel

    class MyRead(CamelModel):
        some_field: str
        # Accepts {"some_field": "x"} AND {"someField": "x"}
        # Serializes as {"some_field": "x"}
"""
from pydantic import AliasGenerator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base schema with camelCase validation alias support.

    Inherits from BaseModel with:
    - from_attributes=True: ORM model → schema conversion
    - populate_by_name=True: accept both field name and alias
    - alias_generator: AliasGenerator with validation_alias only
      (serialization stays snake_case for backward compatibility)
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
        ),
    )
