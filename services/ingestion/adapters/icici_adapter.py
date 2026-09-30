"""ICICI Bank API Adapter — transforms ICICI bank JSON payload into UnifiedTransaction."""

from decimal import Decimal
from datetime import datetime
from typing import Any
from adapters.base import ITransactionAdapter, UnifiedTransaction, ValidationResult


class ICICIBankAdapter(ITransactionAdapter):
    """
    Adapter for ICICI Bank API JSON format.
    Expects JSON payload with ICICI-specific field names.
    """

    @classmethod
    def adapter_id(cls) -> str:
        return "icici_v1"

    def validate(self, raw: Any) -> ValidationResult:
        errors = []
        if not isinstance(raw, dict):
            errors.append("Expected JSON object")
            return ValidationResult(is_valid=False, errors=errors)

        required_fields = ["transaction_id", "amount", "description", "transaction_date"]
        for field in required_fields:
            if field not in raw:
                errors.append(f"Missing required field: {field}")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def transform(self, raw: Any) -> UnifiedTransaction:
        return UnifiedTransaction(
            external_id=f"icici_{raw['transaction_id']}",
            amount=Decimal(str(raw["amount"])),
            currency=raw.get("currency", "INR"),
            merchant_name=raw.get("merchant_name"),
            raw_description=raw["description"],
            mcc_code=raw.get("mcc_code"),
            ts=datetime.fromisoformat(raw["transaction_date"]),
            metadata={
                "bank": "ICICI",
                "branch": raw.get("branch_code"),
                "reference_number": raw.get("reference_number"),
            },
        )
