"""M1 pure contract tests; runtime authority/HTTP evidence is separate."""
from uuid import UUID

from fastapi import HTTPException
import pytest

from core.permission_registry import (
    ADMIN_PERMISSION_CODES,
    STAFF_DEFAULT_PERMISSION_CODES,
    STAFF_DELEGABLE_PERMISSION_CODES,
    validate_staff_permission_codes,
)
from services.staff_identity_guard import credential_mutex_key, normalize_staff_email
from services.staff_management_service import checked_staff_schema


def test_staff_defaults_are_exact_and_nonadministrative():
    assert STAFF_DEFAULT_PERMISSION_CODES == {
        'warehouse': {'skus:read', 'inventory:read', 'orders:read', 'orders:ship'},
        'sales': {'skus:read', 'retailers:read', 'pricing:read', 'orders:read', 'orders:create'},
        'finance': {'orders:read', 'payments:read', 'finance:read'},
    }
    assert STAFF_DELEGABLE_PERMISSION_CODES <= ADMIN_PERMISSION_CODES
    for codes in STAFF_DEFAULT_PERMISSION_CODES.values():
        assert codes <= STAFF_DELEGABLE_PERMISSION_CODES


@pytest.mark.parametrize('code', [
    'users:create', 'roles:assign', 'orders:update', 'inventory:update', 'inventory:write',
    'system:admin', 'metrics:admin', 'client:orders:create', 'platform:admin', 'orders:*',
    'inventory:adjustments:approve',
])
def test_staff_protected_and_m2_capabilities_cannot_be_delegated(code):
    with pytest.raises(ValueError, match='INVALID_STAFF_TEMPLATE'):
        validate_staff_permission_codes([code])


@pytest.mark.parametrize('codes', [['orders:read','orders:read'], ['orders:read',True], 'orders:read', None])
def test_staff_capabilities_do_not_coerce_or_union_unknown_input(codes):
    with pytest.raises(ValueError, match='INVALID_STAFF_TEMPLATE'):
        validate_staff_permission_codes(codes)


def test_staff_all_authorized_capabilities_can_be_explicitly_selected():
    assert validate_staff_permission_codes(sorted(STAFF_DELEGABLE_PERMISSION_CODES)) == STAFF_DELEGABLE_PERMISSION_CODES


def test_staff_schema_is_bound_to_exact_tenant_uuid():
    tenant_id = UUID('ef11ef81-11c1-4f4f-9178-9041187f1581')
    schema = 't_' + tenant_id.hex
    assert checked_staff_schema(tenant_id, schema) == '"'+schema+'"'
    for wrong in ('public', schema.upper(), 't_test', schema+';', 't_'+'0'*32):
        with pytest.raises(HTTPException) as caught:
            checked_staff_schema(tenant_id, wrong)
        assert caught.value.status_code == 403
        assert caught.value.detail['code'] == 'STAFF_TENANT_MISMATCH'


def test_email_mutex_is_normalized_stable_and_domain_separated():
    assert normalize_staff_email(' Staff@Example.com ') == 'staff@example.com'
    assert credential_mutex_key(' Staff@Example.com ') == credential_mutex_key('staff@example.com')
    assert credential_mutex_key('staff@example.com') != credential_mutex_key('other@example.com')
    assert -(2**63) <= credential_mutex_key('staff@example.com') < 2**63


@pytest.mark.parametrize('value', ['', 'a b@example.com', None, 1])
def test_email_mutex_rejects_invalid_input_before_sql(value):
    with pytest.raises(ValueError, match='STAFF_EMAIL_INVALID'):
        normalize_staff_email(value)
