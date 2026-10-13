from decimal import Decimal

import pytest

from lending.services import build_schedule


@pytest.mark.parametrize("principal,rate,months", [
    (Decimal("100000.01"), Decimal("0.0250"), 7),
    (Decimal("333.33"), Decimal("0.0300"), 3),
    (Decimal("250000.00"), Decimal("0.0175"), 12),
])
def test_principal_adds_up_exactly(principal, rate, months):
    rows = build_schedule(principal, rate, months)
    assert len(rows) == months
    assert sum(r["principal"] for r in rows) == principal
    assert rows[-1]["balance_after"] == Decimal("0.00")


def test_interest_never_negative_and_never_rises():
    rows = build_schedule(Decimal("100000.00"), Decimal("0.0250"), 6)
    interest = [r["interest"] for r in rows]
    assert all(i >= 0 for i in interest)
    assert all(later <= earlier for earlier, later in zip(interest, interest[1:]))


def test_every_amount_is_decimal_with_two_places():
    rows = build_schedule(Decimal("1000.00"), Decimal("0.0333"), 4)
    for r in rows:
        for key in ("principal", "interest", "payment", "balance_after"):
            assert isinstance(r[key], Decimal)
            assert r[key] == r[key].quantize(Decimal("0.01"))