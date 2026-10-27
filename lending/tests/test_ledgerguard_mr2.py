"""LedgerGuard regression tests for MR !2 (float interest calculation).

These fail while interest uses float math and Python's round() (banker's rounding),
and pass once interest is money(outstanding * monthly_rate) again (Decimal, half up).
"""
from decimal import Decimal

import pytest

from lending import services
from lending.models import LedgerEntry

pytestmark = pytest.mark.django_db


def interest_income_total():
    entries = LedgerEntry.objects.filter(account=LedgerEntry.Account.INTEREST_INCOME)
    return sum((e.credit for e in entries), Decimal("0.00"))


# ---- Finding 1: FLOAT_MONEY in build_schedule -------------------------------

def test_schedule_interest_rounds_half_up_on_exact_tie():
    # 5.00 x 0.0250 = 0.125 exactly. Half up -> 0.13. round(0.125, 2) gives 0.12.
    rows = build_schedule_rows(Decimal("5.00"), Decimal("0.0250"), 1)
    assert rows[0]["interest"] == Decimal("0.13")
    assert rows[0]["payment"] == Decimal("5.13")


def test_schedule_interest_is_quantized_to_two_places():
    # 1000.00 x 0.0100 = 10; Decimal(str(10.0)) is Decimal('10.0'), not two places.
    rows = build_schedule_rows(Decimal("1000.00"), Decimal("0.0100"), 4)
    for r in rows:
        for key in ("principal", "interest", "payment", "balance_after"):
            assert isinstance(r[key], Decimal)
            assert r[key].as_tuple().exponent == -2, f"{key} not 2 places: {r[key]!r}"


def build_schedule_rows(principal, rate, months):
    return services.build_schedule(principal, rate, months)


# ---- Finding 2: FLOAT_MONEY in record_repayment -----------------------------

def test_repayment_interest_split_rounds_half_up_on_exact_tie():
    loan = services.disburse_loan("Tie Borrower", "0781234567", Decimal("5.00"),
                                  Decimal("0.0250"), 1)
    repayment = services.record_repayment(loan.id, Decimal("1.00"), "PAY-TIE-1")
    # interest due is 0.125 -> 0.13 half up (float round() would give 0.12)
    assert repayment.interest_portion == Decimal("0.13")
    assert repayment.principal_portion == Decimal("0.87")
    loan.refresh_from_db()
    assert loan.outstanding_principal == Decimal("4.13")
    assert interest_income_total() == Decimal("0.13")
    assert services.ledger_balance()["balanced"] is True


def test_full_payoff_with_half_up_interest_clears_the_loan():
    loan = services.disburse_loan("Tie Borrower", "0781234567", Decimal("5.00"),
                                  Decimal("0.0250"), 1)
    # 5.00 principal + 0.13 half-up interest. With the float bug the interest is 0.12,
    # so principal_portion becomes 5.01 and the payment is wrongly refused.
    repayment = services.record_repayment(loan.id, Decimal("5.13"), "PAY-TIE-2")
    assert repayment.interest_portion == Decimal("0.13")
    assert repayment.principal_portion == Decimal("5.00")
    loan.refresh_from_db()
    assert loan.outstanding_principal == Decimal("0.00")
    assert services.ledger_balance()["balanced"] is True
