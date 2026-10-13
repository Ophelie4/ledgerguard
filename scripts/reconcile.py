import os, sys, uuid, requests

BASE = os.environ["STAGING_URL"].rstrip("/")

def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        sys.exit(1)

loan = requests.post(f"{BASE}/loans", json={
    "borrower_name": "Reconcile Bot", "phone": "0780000000",
    "principal": "250000.00", "monthly_rate": "0.0250", "term_months": 6,
}, timeout=30).json()

txn = f"RECON-{uuid.uuid4()}"
callback = {"external_id": txn, "loan_id": loan["id"], "amount": "48000.00"}
first = requests.post(f"{BASE}/momo/callback", json=callback, timeout=30)
second = requests.post(f"{BASE}/momo/callback", json=callback, timeout=30)
check(first.ok, "first callback accepted")
check(second.json().get("status") == "duplicate ignored", "duplicate callback ignored")

bal = requests.get(f"{BASE}/ledger/balance", timeout=30).json()
print(f"Debits {bal['debits']}  Credits {bal['credits']}")
check(bal["debits"] == bal["credits"], "ledger balances")