from decimal import Decimal

import pytest

from lending import services
from lending.models import Loan

pytestmark = pytest.mark.django_db


def new_loan(principal="100000.00"):
    return services.disburse_loan("Test Borrower", "0781234567", Decimal(principal),
                                  Decimal("0.0250"), 6)


def test_balanced_after_disbursement():
    new_loan()
    assert services.ledger_balance()["balanced"] is True


def test_balanced_after_repayment_and_splits_interest_first():
    loan = new_loan()
    r = services.record_repayment(loan.id, Decimal("19166.67"), "PAY-1")
    assert r.interest_portion == Decimal("2500.00")      # 100000 x 2.5%
    assert r.principal_portion == Decimal("16666.67")
    assert services.ledger_balance()["balanced"] is True
    loan.refresh_from_db()
    assert loan.outstanding_principal == Decimal("83333.33")


def test_overpayment_is_rejected_and_writes_nothing():
    loan = new_loan("1000.00")
    before = services.ledger_balance()
    with pytest.raises(ValueError):
        services.record_repayment(loan.id, Decimal("5000.00"), "PAY-TOO-MUCH")
    assert services.ledger_balance() == before


def test_loan_marked_repaid_when_fully_paid():
    loan = new_loan("1000.00")
    services.record_repayment(loan.id, Decimal("1025.00"), "PAY-ALL")   # 25 interest + 1000
    loan.refresh_from_db()
    assert loan.status == Loan.Status.REPAID
    assert services.ledger_balance()["balanced"] is True


def test_unbalanced_post_is_refused():
    with pytest.raises(ValueError):
        services.post("BAD-1", [("cash", Decimal("10.00"), 0), ("fee_income", 0, Decimal("9.99"))])