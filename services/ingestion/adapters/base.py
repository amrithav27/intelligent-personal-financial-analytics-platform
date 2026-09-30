"""
ADAPTER PATTERN — Base interface for transaction source adapters.
All adapters must produce UnifiedTransaction objects.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import Any


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]


@dataclass
class UnifiedTransaction:
    """Canonical transaction schema. All adapters must produce this."""
    external_id: str          # Unique ID from the source (dedup key)
    amount: Decimal           # ALWAYS Decimal, never float
    currency: str             # ISO 4217 e.g. "INR"
    merchant_name: str | None
    raw_description: str
    mcc_code: str | None      # ISO 18245
    ts: datetime              # Transaction timestamp (UTC)
    metadata: dict[str, Any]  # Source-specific extra fields


class ITransactionAdapter(ABC):
    """
    ADAPTER PATTERN: All transaction source adapters implement this interface.
    Adding a new source = implementing these two methods + registering in AdapterRegistry.
    No other code changes required (satisfies NFR-06: < 2 dev-days per new source).
    """

    @abstractmethod
    def validate(self, raw: Any) -> ValidationResult:
        """Validate raw source data before transformation."""
        ...

    @abstractmethod
    def transform(self, raw: Any) -> list[UnifiedTransaction] | UnifiedTransaction:
        """Transform raw source data into UnifiedTransaction."""
        ...

    @classmethod
    @abstractmethod
    def adapter_id(cls) -> str:
        """Unique identifier for this adapter, e.g. 'icici_v1'."""
        ...
