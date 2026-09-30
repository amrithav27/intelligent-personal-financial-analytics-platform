"""CSV Upload Adapter — transforms user-uploaded CSV into UnifiedTransaction objects."""

import csv
import io
from decimal import Decimal
from datetime import datetime
from adapters.base import ITransactionAdapter, UnifiedTransaction, ValidationResult

REQUIRED_COLUMNS = {"date", "amount", "description"}


class CSVUploadAdapter(ITransactionAdapter):
    """
    Transforms a user-uploaded CSV into UnifiedTransaction objects.
    Supports configurable column mapping for different bank CSV formats.
    """

    def __init__(self, column_map: dict[str, str] | None = None):
        self.column_map = column_map or {
            "date": "date",
            "amount": "amount",
            "description": "description",
            "merchant": "merchant",
        }

    @classmethod
    def adapter_id(cls) -> str:
        return "csv_v1"

    def validate(self, raw: str) -> ValidationResult:
        errors = []
        try:
            reader = csv.DictReader(io.StringIO(raw))
            headers = set(reader.fieldnames or [])
            for required, mapped in self.column_map.items():
                if required in REQUIRED_COLUMNS and mapped not in headers:
                    errors.append(f"Missing column '{mapped}' (expected for '{required}')")
        except Exception as e:
            errors.append(f"CSV parse error: {e}")
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def transform(self, raw: str) -> list[UnifiedTransaction]:
        reader = csv.DictReader(io.StringIO(raw))
        results = []
        for i, row in enumerate(reader):
            amount_str = row[self.column_map["amount"]].replace(",", "").replace("₹", "").strip()
            results.append(
                UnifiedTransaction(
                    external_id=f"csv_{i}_{row.get(self.column_map['date'], '')}",
                    amount=Decimal(amount_str),
                    currency="INR",
                    merchant_name=row.get(self.column_map.get("merchant", ""), None),
                    raw_description=row[self.column_map["description"]],
                    mcc_code=None,
                    ts=datetime.strptime(row[self.column_map["date"]], "%Y-%m-%d"),
                    metadata={"source_row": i},
                )
            )
        return results
