"""Manual Entry Adapter — transforms a manually entered transaction into UnifiedTransaction."""

import uuid
from decimal import Decimal
from datetime import datetime
from typing import Any
from adapters.base import ITransactionAdapter, UnifiedTransaction, ValidationResult


class ManualEntryAdapter(ITransactionAdapter):
    """
    Adapter for manually entered transactions via the UI.
    Expects a simple JSON payload with amount, description, and optional fields.
    """

    @classmethod
    def adapter_id(cls) -> str:
        return "manual_v1"

    def validate(self, raw: Any) -> ValidationResult:
        errors = []
        if not isinstance(raw, dict):
            errors.append("Expected JSON object")
            return ValidationResult(is_valid=False, errors=errors)

        if "amount" not in raw:
            errors.append("Missing required field: amount")
        if "description" not in raw:
            errors.append("Missing required field: description")

        if "amount" in raw:
            try:
                Decimal(str(raw["amount"]))
            except Exception:
                errors.append("Invalid amount format")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def transform(self, raw: Any) -> UnifiedTransaction:
        return UnifiedTransaction(
            external_id=f"manual_{uuid.uuid4().hex[:12]}",
            amount=Decimal(str(raw["amount"])),
            currency=raw.get("currency", "INR"),
            merchant_name=raw.get("merchant_name"),
            raw_description=raw["description"],
            mcc_code=raw.get("mcc_code"),
            ts=datetime.fromisoformat(raw["date"]) if "date" in raw else datetime.utcnow(),
            metadata={"source": "manual_entry"},
        )
