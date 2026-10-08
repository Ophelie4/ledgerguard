from decimal import Decimal

from django.db import models

# Every amount of money in this app uses these settings. Never FloatField.
MONEY = {"max_digits": 14, "decimal_places": 2}

class Borrower(models.Model):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Loan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        REPAID = "repaid"

    borrower = models.ForeignKey(Borrower, on_delete=models.PROTECT, related_name="loans")
    principal = models.DecimalField(**MONEY)
    monthly_rate = models.DecimalField(max_digits=6, decimal_places=4)  # 0.0250 = 2.5% a month
    term_months = models.PositiveSmallIntegerField()
    outstanding_principal = models.DecimalField(**MONEY)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

class Repayment(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name="repayments")
    amount = models.DecimalField(**MONEY)
    interest_portion = models.DecimalField(**MONEY)
    principal_portion = models.DecimalField(**MONEY)
    external_id = models.CharField(max_length=64, unique=True)
    paid_at = models.DateTimeField(auto_now_add=True)

class LedgerEntry(models.Model):
    class Account(models.TextChoices):
        CASH = "cash"
        LOANS_RECEIVABLE = "loans_receivable"
        INTEREST_INCOME = "interest_income"
        FEE_INCOME = "fee_income"

    txn_id = models.CharField(max_length=64, db_index=True)
    account = models.CharField(max_length=20, choices=Account.choices)
    debit = models.DecimalField(**MONEY, default=Decimal("0.00"))
    credit = models.DecimalField(**MONEY, default=Decimal("0.00"))
    memo = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class MomoCallback(models.Model):
    # unique=True is what stops the same mobile-money payment being counted twice
    external_id = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(**MONEY)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)