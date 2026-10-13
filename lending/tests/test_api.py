import logging

import pytest
from rest_framework.test import APIClient

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


def test_schedule_endpoint(client, loan_id):
    res = client.get(f"/loans/{loan_id}/schedule")
    assert res.status_code == 200
    assert len(res.json()["schedule"]) == 6


def test_duplicate_callback_is_ignored(client, loan_id):
    body = {"external_id": "MOMO-123", "loan_id": loan_id, "amount": "19166.67", "msisdn": PHONE}
    first = client.post("/momo/callback", body, format="json")
    second = client.post("/momo/callback", body, format="json")
    assert first.json()["status"] == "recorded"
    assert second.json()["status"] == "duplicate ignored"
    balance = client.get("/ledger/balance").json()
    assert balance["balanced"] is True
    # cash went up by exactly one payment, not two
    assert balance["debits"] == "119166.67"


def test_invalid_input_is_rejected(client):
    res = client.post("/loans", {"borrower_name": "X", "phone": PHONE, "principal": "-5",
                                 "monthly_rate": "0.0250", "term_months": 6}, format="json")
    assert res.status_code == 400


def test_no_phone_number_in_logs(client, loan_id, caplog):
    caplog.set_level(logging.INFO, logger="lending")
    client.post("/momo/callback", {"external_id": "MOMO-LOG", "loan_id": loan_id,
                                   "amount": "1000.00", "msisdn": PHONE}, format="json")
    assert caplog.records, "expected the callback to log something"
    assert PHONE not in caplog.text