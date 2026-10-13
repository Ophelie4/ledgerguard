from django.urls import path

from . import views

urlpatterns = [
    path("loans", views.create_loan),
    path("loans/<int:loan_id>/schedule", views.loan_schedule),
    path("repayments", views.create_repayment),
    path("momo/callback", views.momo_callback),
    path("ledger/balance", views.ledger_balance),
]