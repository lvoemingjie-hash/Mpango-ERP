from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, StrictBool


class StaffCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email: EmailStr
    full_name: str=Field(min_length=1,max_length=255)
    template_key: Literal['warehouse','sales','finance']
    adopt_existing: StrictBool=False


class StaffEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version: int=Field(strict=True,gt=0)
    full_name: str | None=Field(default=None,min_length=1,max_length=255)
    is_active: StrictBool | None=None
    template_key: Literal['warehouse','sales','finance'] | None=None


class StaffTemplateEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version: int=Field(strict=True,gt=0)
    permission_codes: list[str]


class StaffRoleEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version: int=Field(strict=True,gt=0)
    template_key: Literal['warehouse','sales','finance']


class StaffInvite(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version: int=Field(strict=True,gt=0)
    owner_password: SecretStr


class StaffCredentialConsume(BaseModel):
    model_config=ConfigDict(extra='forbid')
    setup_token: SecretStr
    password: SecretStr
