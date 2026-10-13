from decimal import Decimal

from rest_framework import serializers

AMOUNT = {"max_digits": 14, "decimal_places": 2, "min_value": Decimal("0.01")}


class LoanCreateSerializer(serializers.Serializer):
    borrower_name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=20)
    principal = serializers.DecimalField(**AMOUNT)
    monthly_rate = serializers.DecimalField(max_digits=6, decimal_places=4,
                                            min_value=Decimal("0"), max_value=Decimal("1"))
    term_months = serializers.IntegerField(min_value=1, max_value=60)


class RepaymentSerializer(serializers.Serializer):
    loan_id = serializers.IntegerField()
    amount = serializers.DecimalField(**AMOUNT)
    external_id = serializers.CharField(max_length=64)


class MomoCallbackSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=64)
    loan_id = serializers.IntegerField()
    amount = serializers.DecimalField(**AMOUNT)
    msisdn = serializers.CharField(max_length=20, required=False)  # payer's phone number