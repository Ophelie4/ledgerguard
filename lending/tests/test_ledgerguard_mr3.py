"""LedgerGuard regression tests for MR !3 (charge_late_fee).

Each test fails on the MR's code and passes once the bug is fixed.
"""
from decimal import Decimal

import pytest
from django.db.models import Sum

from lending import services
from lending.models import LedgerEntry

pytestmark = pytest.mark.django_db

A = LedgerEntry.Account


def new_loan(principal="100000.00"):
    return services.disburse_loan("Test Borrower", "0781234567", Decimal(principal),
                                  Decimal("0.0250"), 6)


def fee_income_total():
    total = LedgerEntry.objects.filter(account=A.FEE_INCOME).aggregate(s=Sum("credit"))["s"]
    return services.money(total or 0)


def test_late_fee_keeps_ledger_balanced():
    # UNBALANCED_LEDGER: the fee must be posted with a matching debit.
    loan = new_loan()
    assert services.ledger_balance()["balanced"] is True

    fee = services.charge_late_fee(loan.id)

    assert fee == Decimal("2000.00")                      # 2% of 100000.00
    balance = services.ledger_balance()
    assert balance["balanced"] is True, balance
    assert balance["debits"] == balance["credits"]


def test_late_fee_debit_matches_fee_income_credit():
    # UNBALANCED_LEDGER: every fee credit needs an equal debit in the same transaction.
    loan = new_loan()

    fee = services.charge_late_fee(loan.id)

    late_entries = LedgerEntry.objects.filter(txn_id__startswith=f"LATE-{loan.id}-")
    debits = late_entries.aggregate(s=Sum("debit"))["s"] or Decimal("0.00")
    credits = late_entries.aggregate(s=Sum("credit"))["s"] or Decimal("0.00")
    assert services.money(credits) == fee
    assert services.money(debits) == fee


def test_late_fee_charged_twice_for_same_missed_payment_is_charged_once():
    # IDEMPOTENCY: a retry or double-run of the job must not charge the borrower again.
    loan = new_loan()

    first = services.charge_late_fee(loan.id)
    services.charge_late_fee(loan.id)

    assert fee_income_total() == first == Decimal("2000.00")   # not 4000.00
    late_txn_ids = set(
        LedgerEntry.objects.filter(txn_id__startswith=f"LATE-{loan.id}-")
        .values_list("txn_id", flat=True)
    )
    assert len(late_txn_ids) == 1
    assert services.ledger_balance()["balanced"] is True


def test_late_fee_retry_does_not_change_outstanding_amount_twice():
    # IDEMPOTENCY: the ledger must not grow on a retry of the same fee.
    loan = new_loan()

    services.charge_late_fee(loan.id)
    entries_after_first = LedgerEntry.objects.count()
    services.charge_late_fee(loan.id)

    assert LedgerEntry.objects.count() == entries_after_first
