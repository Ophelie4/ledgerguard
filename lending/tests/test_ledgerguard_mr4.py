"""LedgerGuard regression tests for !4 (Log manual repayments for support).

Finding 1 (PII_LEAK): create_repayment logs the borrower's name and phone number.
"""
import logging
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from lending.models import Repayment

pytestmark = pytest.mark.django_db

PHONE = "0789876543"
BORROWER_NAME = "Zephyrine Uwimana"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def loan_id(client):
    res = client.post("/loans", {
        "borrower_name": BORROWER_NAME, "phone": PHONE,
        "principal": "100000.00", "monthly_rate": "0.0250", "term_months": 6,
    }, format="json")
    assert res.status_code == 201
    return res.json()["id"]


def _post_manual_repayment(client, loan_id, external_id):
    return client.post("/repayments", {
        "loan_id": loan_id, "amount": "1000.00", "external_id": external_id,
    }, format="json")


def test_manual_repayment_does_not_log_phone_number(client, loan_id, caplog):
    # PII_LEAK: the borrower's phone number must never reach the logs.
    caplog.set_level(logging.INFO, logger="lending")
    res = _post_manual_repayment(client, loan_id, "MANUAL-LOG-PHONE")
    assert res.status_code == 201
    assert caplog.records, "expected the manual repayment to log something"
    assert PHONE not in caplog.text


def test_manual_repayment_does_not_log_borrower_name(client, loan_id, caplog):
    # PII_LEAK: the borrower's name is personal data and must not be logged either.
    caplog.set_level(logging.INFO, logger="lending")
    res = _post_manual_repayment(client, loan_id, "MANUAL-LOG-NAME")
    assert res.status_code == 201
    assert caplog.records, "expected the manual repayment to log something"
    assert BORROWER_NAME not in caplog.text


def test_manual_repayment_log_still_traces_loan_and_money_is_correct(client, loan_id, caplog):
    # Support still needs a trace (loan id), and logging must not change the money outcome.
    caplog.set_level(logging.INFO, logger="lending")
    res = _post_manual_repayment(client, loan_id, "MANUAL-LOG-TRACE")
    assert res.status_code == 201
    assert str(loan_id) in caplog.text
    # The log must not carry PII while still tracing the repayment.
    assert PHONE not in caplog.text
    assert BORROWER_NAME not in caplog.text

    repayments = Repayment.objects.filter(loan_id=loan_id)
    assert repayments.count() == 1
    repayment = repayments.get()
    assert repayment.amount == Decimal("1000.00")
    assert repayment.interest_portion + repayment.principal_portion == Decimal("1000.00")
    assert client.get("/ledger/balance").json()["balanced"] is True
