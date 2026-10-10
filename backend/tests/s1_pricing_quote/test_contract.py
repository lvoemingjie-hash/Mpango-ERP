"""Named S1 semantic controls; exact money and per-line consent, no services."""
import copy
import ast
from pathlib import Path
from decimal import Decimal
import time

import pytest
from fastapi import HTTPException

from repositories.pricing_repository import effective_price
from services.pricing_quote_service import (
    amount_string, money, read_quote, require_consent, sign_quote, PURPOSE,
)


def test_confirmation_quote_refresh_preserves_joined_stock_lock_order():
    source = Path(__file__).resolve().parents[2] / 'services/order_command_service.py'
    tree = ast.parse(source.read_text())
    method = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == 'confirm_order')
    calls = {getattr(n.func, 'attr', getattr(n.func, 'id', '')): n.lineno
             for n in ast.walk(method) if isinstance(n, ast.Call)}
    assert (calls['_prelock_stocks'] < calls['validate_draft_for_confirmation']
            < calls['_reserve_inventory'] < calls['_open_credit_hold']), \
        'S1_CONFIRM_JOIN_LOCK_ORDER_AND_ZERO_WRITES_BEFORE_CONSENT'


def payload():
    now = int(time.time())
    return dict(purpose=PURPOSE, iat=now, exp=now + 900, tenant="t_fixture",
                wholesaler="merchant", retailer="customer", actor="actor",
                operation="client-create", country="KE", currency="KES", registration="registration",
                lines=[dict(sku_id="unit", sku_code="BOX", quantity=2, unit="Box",
                            package_quantity="12", unit_price="90.00", subtotal="180.00",
                            revision=0, source="BASE_PRICE", display_label="Box")], total="180.00")


@pytest.mark.parametrize("base,override,value,origin,reason", [
    (None, Decimal("12"), None, None, "BASE_PRICE_REQUIRED"),
    (Decimal("10"), None, Decimal("10"), "BASE_PRICE", None),
    (Decimal("10"), Decimal("12"), Decimal("12"), "RETAILER_OVERRIDE", None),
    (Decimal("0"), Decimal("12"), None, None, "PRICE_DATA_INTEGRITY_RED"),
    (Decimal("10"), Decimal("NaN"), None, None, "PRICE_DATA_INTEGRITY_RED"),
])
def test_common_effective_price(base, override, value, origin, reason):
    assert effective_price(base, override) == (value, origin, reason), "S1_EFFECTIVE_PRICE_AUTHORITY"


@pytest.mark.parametrize("value,currency,expected", [
    ("90.000", "UGX", "90"), ("90.000", "KES", "90.00"),
    ("0", "UGX", "0"), ("9999999999.99", "KES", "9999999999.99"),
])
def test_exact_string_amount(value, currency, expected):
    assert amount_string(value, currency) == expected, "S1_MONEY_STRING"


@pytest.mark.parametrize("value,currency,code", [
    ("90.01", "UGX", "MONEY_PRECISION"), ("90.001", "KES", "MONEY_PRECISION"),
    ("NaN", "KES", "INVALID_MONEY"), ("Infinity", "KES", "INVALID_MONEY"),
    ("-1", "KES", "INVALID_MONEY"), ("0", "KES", "INVALID_MONEY"),
    ("10000000000", "KES", "INVALID_MONEY"), ("1", "XXX", "TENANT_CURRENCY_UNRESOLVED"),
])
def test_money_refusals(value, currency, code):
    with pytest.raises(HTTPException) as error:
        money(value, currency)
    assert error.value.detail["code"] == code, "S1_PRECISION_REFUSAL"


def test_price_change_requires_explicit_consent():
    old = payload()
    current = copy.deepcopy(old)
    current["lines"][0].update(unit_price="110.00", subtotal="220.00", revision=1)
    current["total"] = "220.00"
    with pytest.raises(HTTPException) as error:
        require_consent(old, current)
    assert error.value.detail["code"] == "PRICE_PREVIEW_STALE", "S1_LINE_PRICE_CONSENT"
    assert error.value.detail["details"]["old_total"] == "180.00"
    assert error.value.detail["details"]["new_total"] == "220.00"
    assert error.value.detail["details"]["delta"] == "40.00"
    assert read_quote(error.value.detail["details"]["quote"]["quote_token"])["total"] == "220.00"


def test_same_total_opposing_lines_still_red():
    old = payload()
    old["lines"].append({**old["lines"][0], "sku_id": "second"})
    old["total"] = "360.00"
    current = copy.deepcopy(old)
    current["lines"][0].update(unit_price="110.00", subtotal="220.00")
    current["lines"][1].update(unit_price="70.00", subtotal="140.00")
    rejected = False
    try:
        require_consent(old, current)
    except HTTPException as error:
        rejected = error.detail['code'] == 'PRICE_PREVIEW_STALE'
    assert rejected, 'S1_ONLY_GRAND_TOTAL_IS_FALSE_CONSENT'


def test_aba_revision_source_and_label_do_not_add_consent_click():
    old = payload()
    current = copy.deepcopy(old)
    current["lines"][0].update(revision=4, source="RETAILER_OVERRIDE", display_label="Readable box")
    require_consent(old, current)
    assert old["lines"][0]["revision"] == 0


@pytest.mark.parametrize("field,value", [("retailer", "another"), ("tenant", "other"),
                                          ("actor", "other"), ("currency", "UGX")])
def test_cross_context_rejected(field, value):
    old = payload()
    current = copy.deepcopy(old)
    current[field] = value
    with pytest.raises(HTTPException) as error:
        require_consent(old, current)
    assert error.value.detail["code"] == "QUOTE_CONTEXT_CHANGED", "S1_CONTEXT_BINDING"


def test_quote_tamper_and_expiry():
    old = payload()
    token = sign_quote(old)
    assert read_quote(token) == old
    with pytest.raises(HTTPException):
        read_quote(token[:-5] + "aaaaa")
    old["iat"] -= 901
    old["exp"] -= 901
    with pytest.raises(HTTPException) as error:
        read_quote(sign_quote(old))
    assert error.value.detail["code"] == "QUOTE_EXPIRED"
    assert read_quote(sign_quote(old), check_expiry=False) == old
