"""Ledger proof against a running LedgerGuard API.

Creates a loan, sends the same mobile-money callback twice, and checks that the
duplicate is ignored and the whole ledger still balances. Exits 1 on any failure.
Writes ledger-proof.json so CI keeps the evidence.

Usage: STAGING_URL=https://... python scripts/reconcile.py
"""
import json
import os
import sys
import uuid

import requests

BASE = os.environ["STAGING_URL"].rstrip("/")
checks = []
totals = {}


def check(ok, msg):
    checks.append({"check": msg, "result": "PASS" if ok else "FAIL"})
    print(("PASS " if ok else "FAIL ") + msg, flush=True)
    return ok


def finish(code):
    proof = {
        "url": BASE,
        "commit": os.environ.get("CI_COMMIT_SHA", "local"),
        "checks": checks,
        "debits": totals.get("debits"),
        "credits": totals.get("credits"),
        "verdict": "VERIFIED" if code == 0 else "NOT VERIFIED",
    }
    with open("ledger-proof.json", "w") as f:
        json.dump(proof, f, indent=2)
    print(f"VERDICT {proof['verdict']}")
    sys.exit(code)


print(f"Ledger proof for {BASE} at commit {os.environ.get('CI_COMMIT_SHA', 'local')}")

loan_res = requests.post(f"{BASE}/loans", json={
    "borrower_name": "Reconcile Bot", "phone": "0780000000",
    "principal": "250000.00", "monthly_rate": "0.0250", "term_months": 6,
}, timeout=60)
if not check(loan_res.status_code == 201, "loan created"):
    finish(1)
loan = loan_res.json()

txn = f"RECON-{uuid.uuid4()}"
callback = {"external_id": txn, "loan_id": loan["id"], "amount": "48000.00"}
first = requests.post(f"{BASE}/momo/callback", json=callback, timeout=60)
second = requests.post(f"{BASE}/momo/callback", json=callback, timeout=60)
ok = check(first.ok and first.json().get("status") == "recorded", "first callback recorded")
ok &= check(second.ok and second.json().get("status") == "duplicate ignored",
            "duplicate callback ignored")

bal = requests.get(f"{BASE}/ledger/balance", timeout=60).json()
totals.update(debits=bal["debits"], credits=bal["credits"])
print(f"Debits {bal['debits']}  Credits {bal['credits']}")
ok &= check(bal["debits"] == bal["credits"] and bal["balanced"] is True, "ledger balances")

finish(0 if ok else 1)
