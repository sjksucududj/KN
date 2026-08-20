"""Unit tests Sub-fase 1.13 — UOM Conversion Engine (pure functions, no DB)."""
import os
import sys
import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.uom_service import convert, to_base, from_base  # noqa: E402

FIXED = {"meter": 1.0, "yard": 0.9144, "cm": 0.01, "inch": 0.0254}

# Produk base meter, 1 roll = 50 m (VARIABLE)
PROD_ROLL = {"sku": "BTK-001", "base_unit": "meter",
             "uom_conversions": [{"from_unit": "roll", "to_unit": "meter", "factor": 50}]}
# Produk tanpa konversi variable
PROD_PLAIN = {"sku": "PLN-001", "base_unit": "meter", "uom_conversions": []}


def test_same_unit_identity():
    assert to_base(PROD_PLAIN, 10, "meter", FIXED) == 10.0


def test_yard_to_meter_fixed():
    assert to_base(PROD_PLAIN, 10, "yard", FIXED) == 9.14  # 10*0.9144=9.144 → 9.14


def test_cm_inch_fixed():
    assert to_base(PROD_PLAIN, 250, "cm", FIXED) == 2.5
    assert to_base(PROD_PLAIN, 100, "inch", FIXED) == 2.54


def test_roll_to_meter_variable():
    assert to_base(PROD_ROLL, 2, "roll", FIXED) == 100.0  # 2 roll * 50 = 100 m


def test_meter_to_roll_inverse():
    assert convert(PROD_ROLL, 100, "meter", "roll", FIXED) == 2.0


def test_from_base_to_yard():
    # 9.144 m → 10 yard (≈)
    assert from_base(PROD_PLAIN, 9.144, "yard", FIXED) == 10.0


def test_roll_to_yard_one_hop():
    # 1 roll = 50 m → 50/0.9144 = 54.68 yard
    assert convert(PROD_ROLL, 1, "roll", "yard", FIXED) == 54.68


def test_missing_factor_raises():
    with pytest.raises(HTTPException) as ei:
        to_base(PROD_PLAIN, 5, "kg", FIXED)  # no gramasi/lebar → no kg factor
    assert ei.value.status_code == 400


# Sub-fase 1.13 — catch-weight kg (gramasi gsm × lebar m / 1000 = kg/meter)
PROD_KG = {"sku": "KG-001", "base_unit": "meter", "uom_conversions": [], "gramasi": 200, "lebar": 1.5}


def test_kg_to_meter_catch_weight():
    # kg/m = 200*1.5/1000 = 0.3 → 3 kg = 10 m
    assert to_base(PROD_KG, 3, "kg", FIXED) == 10.0


def test_meter_to_kg_catch_weight():
    # 10 m = 3.0 kg
    assert convert(PROD_KG, 10, "meter", "kg", FIXED) == 3.0


def test_kg_to_yard_one_hop():
    # 3 kg = 10 m = 10/0.9144 = 10.94 yard
    assert convert(PROD_KG, 3, "kg", "yard", FIXED) == 10.94


def test_pricing_consistency_base():
    # subtotal harus sama baik dihitung per base maupun per sell-unit-scaled
    price_per_meter = 185000.0
    qty_yard = 10
    factor = to_base(PROD_PLAIN, 1, "yard", FIXED, precision=6)  # 0.9144 (presisi tinggi)
    base_qty = to_base(PROD_PLAIN, qty_yard, "yard", FIXED)  # 9.14
    subtotal_via_sell = round(qty_yard * round(price_per_meter * factor, 2), 2)
    subtotal_via_base = round(base_qty * price_per_meter, 2)
    # toleransi pembulatan kecil
    assert abs(subtotal_via_sell - subtotal_via_base) < price_per_meter * 0.01
