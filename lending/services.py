"""All money logic lives here. Views only validate input and call these functions."""
import logging
import uuid
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum

from .models import Borrower, LedgerEntry, Loan, MomoCallback, Repayment

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
A = LedgerEntry.Account

def money(value) -> Decimal:
    """Round to cents, half up. The only rounding rule in the app."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def mask_phone(phone: str) -> str:
    """0781234567 -> ******4567, for anything that might reach a log."""
    return "*" * max(len(phone) - 4, 0) + phone[-4:]

def post(txn_id: str, lines: list, memo: str = "") -> None:
    """Write one balanced transaction. lines = [(account, debit, credit), ...]."""
    debits = sum((money(d) for _, d, _ in lines), Decimal("0.00"))
    credits = sum((money(c) for _, _, c in lines), Decimal("0.00"))
    if debits != credits:
        raise ValueError(f"Unbalanced transaction {txn_id}: debits {debits} != credits {credits}")
    LedgerEntry.objects.bulk_create(
        LedgerEntry(txn_id=txn_id, account=acct, debit=money(d), credit=money(c), memo=memo)
        for acct, d, c in lines
    )

def build_schedule(principal: Decimal, monthly_rate: Decimal, term_months: int) -> list:
    """Declining balance, equal principal each month.

    The last month absorbs any leftover cent so principal paid equals the loan exactly.
    """
    principal = money(principal)
    base = (principal / term_months).quantize(CENT, rounding=ROUND_DOWN)
    outstanding = principal
    rows = []
    for month in range(1, term_months + 1):
        principal_part = base if month < term_months else outstanding
        interest = money(outstanding * monthly_rate)
        rows.append({
            "month": month,
            "principal": principal_part,
            "interest": interest,
            "payment": principal_part + interest,
            "balance_after": outstanding - principal_part,
        })
        outstanding -= principal_part
    return rows

@transaction.atomic
def disburse_loan(borrower_name: str, phone: str, principal: Decimal,
                  monthly_rate: Decimal, term_months: int) -> Loan:
    principal = money(principal)
    borrower = Borrower.objects.create(name=borrower_name, phone=phone)
    loan = Loan.objects.create(
        borrower=borrower, principal=principal, monthly_rate=monthly_rate,
        term_months=term_months, outstanding_principal=principal,
    )
    post(f"DISB-{uuid.uuid4().hex[:12]}", [
        (A.LOANS_RECEIVABLE, principal, 0),
        (A.CASH, 0, principal),
    ], memo=f"Disburse loan {loan.id}")
    logger.info("Disbursed loan %s to borrower %s", loan.id, mask_phone(phone))
    return loan

@transaction.atomic
def record_repayment(loan_id: int, amount: Decimal, external_id: str) -> Repayment:
    loan = Loan.objects.select_for_update().get(id=loan_id)
    amount = money(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    interest_due = money(loan.outstanding_principal * loan.monthly_rate)
    interest_part = min(amount, interest_due)
    principal_part = amount - interest_part
    if principal_part > loan.outstanding_principal:
        raise ValueError("Payment is larger than the amount owed")

    repayment = Repayment.objects.create(
        loan=loan, amount=amount, interest_portion=interest_part,
        principal_portion=principal_part, external_id=external_id,
    )
    post(f"REPAY-{external_id}", [
        (A.CASH, amount, 0),
        (A.INTEREST_INCOME, 0, interest_part),
        (A.LOANS_RECEIVABLE, 0, principal_part),
    ], memo=f"Repayment on loan {loan.id}")

    loan.outstanding_principal -= principal_part
    if loan.outstanding_principal == 0:
        loan.status = Loan.Status.REPAID
    loan.save(update_fields=["outstanding_principal", "status"])
    return repayment

@transaction.atomic
def handle_momo_callback(external_id: str, loan_id: int, amount: Decimal, payload: dict) -> dict:
    """Mobile-money providers can send the same confirmation more than once.

    get_or_create on a unique external_id means the second copy changes nothing.
    """
    callback, created = MomoCallback.objects.get_or_create(
        external_id=external_id, defaults={"amount": money(amount), "payload": payload},
    )
    if not created:
        logger.info("Duplicate mobile-money callback %s ignored", external_id)
        return {"status": "duplicate ignored", "external_id": external_id}

    repayment = record_repayment(loan_id, amount, external_id)
    logger.info("Mobile-money callback %s recorded on loan %s", external_id, loan_id)
    return {"status": "recorded", "external_id": external_id, "repayment_id": repayment.id}


def ledger_balance() -> dict:
    totals = LedgerEntry.objects.aggregate(debits=Sum("debit"), credits=Sum("credit"))
    debits = money(totals["debits"] or 0)
    credits = money(totals["credits"] or 0)
    return {"debits": str(debits), "credits": str(credits), "balanced": debits == credits}


@transaction.atomic
def handle_airtel_callback(transaction_id: str, loan_id: int, amount: Decimal) -> dict:
    """Airtel Money confirmations. Airtel uses its own transaction IDs."""
    repayment = record_repayment(loan_id, amount, f"AIRTEL-{uuid.uuid4().hex[:12]}")
    logger.info("Airtel callback %s recorded on loan %s", transaction_id, loan_id)
    return {"status": "recorded", "transaction_id": transaction_id, "repayment_id": repayment.id}
