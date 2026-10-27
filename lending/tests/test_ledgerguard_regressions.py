"""LedgerGuard regression tests for MR !1 (Airtel Money callback).

Each test fails on the merge request's code and passes once the bug is fixed.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from lending.models import Loan, Repayment

pytestmark = pytest.mark.django_db

PHONE = "0781234567"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def loan_id(client):
    res = client.post("/loans", {
        "borrower_name": "Test Borrower", "phone": PHONE,
        "principal": "100000.00", "monthly_rate": "0.0250", "term_months": 6,
    }, format="json")
    assert res.status_code == 201
    return res.json()["id"]


def test_idempotency_duplicate_airtel_callback_records_one_repayment(client, loan_id):
    """IDEMPOTENCY: Airtel retries the same transaction_id; only one payment may post.

    Fails today because handle_airtel_callback ignores transaction_id and uses a
    random uuid as the repayment external_id, so every retry posts a new repayment
    and a new ledger transaction.
    """
    body = {"transaction_id": "AIRTEL-TXN-001", "loan_id": loan_id, "amount": "19166.67"}
    first = client.post("/airtel/callback", body, format="json")
    second = client.post("/airtel/callback", body, format="json")
    assert first.status_code == 200
    assert second.status_code == 200

    # exactly one repayment for one Airtel transaction
    assert Repayment.objects.filter(loan_id=loan_id).count() == 1

    # the borrower is credited once: 100000.00 - 16666.67 principal
    loan = Loan.objects.get(id=loan_id)
    assert loan.outstanding_principal == Decimal("83333.33")

    # cash went up by exactly one payment (100000.00 disbursed + 19166.67), not two,
    # and the ledger still balances
    balance = client.get("/ledger/balance").json()
    assert balance["balanced"] is True
    assert balance["debits"] == "119166.67"
    assert balance["credits"] == "119166.67"
