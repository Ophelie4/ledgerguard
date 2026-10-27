from decimal import Decimal
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import services
from .models import Loan
from .serializers import LoanCreateSerializer, MomoCallbackSerializer, RepaymentSerializer


@api_view(["POST"])
def create_loan(request):
    s = LoanCreateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    loan = services.disburse_loan(**s.validated_data)
    return Response({
        "id": loan.id,
        "principal": str(loan.principal),
        "monthly_rate": str(loan.monthly_rate),
        "term_months": loan.term_months,
        "status": loan.status,
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def loan_schedule(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id)
    rows = services.build_schedule(loan.principal, loan.monthly_rate, loan.term_months)
    return Response({
        "loan_id": loan.id,
        "schedule": [{k: (str(v) if k != "month" else v) for k, v in r.items()} for r in rows],
    })


@api_view(["POST"])
def create_repayment(request):
    s = RepaymentSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    get_object_or_404(Loan, id=s.validated_data["loan_id"])
    try:
        r = services.record_repayment(**s.validated_data)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"id": r.id, "interest_portion": str(r.interest_portion),
                     "principal_portion": str(r.principal_portion)}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def momo_callback(request):
    s = MomoCallbackSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    get_object_or_404(Loan, id=d["loan_id"])
    try:
        result = services.handle_momo_callback(d["external_id"], d["loan_id"], d["amount"],
                                               payload=request.data)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)


@api_view(["GET"])
def ledger_balance(request):
    return Response(services.ledger_balance())


@api_view(["POST"])
def airtel_callback(request):
    d = request.data
    get_object_or_404(Loan, id=d["loan_id"])
    result = services.handle_airtel_callback(d["transaction_id"], int(d["loan_id"]), Decimal(d["amount"]))
    return Response(result)
