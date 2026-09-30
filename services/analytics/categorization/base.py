"""
STRATEGY PATTERN — Base interface for categorization strategies.
Both RuleBasedCategorizer and LLMCategorizer implement ICategorizer.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class CategorizationMethod(str, Enum):
    RULE_MCC = "RULE_MCC"
    RULE_MERCHANT = "RULE_MERCHANT"
    RULE_KEYWORD = "RULE_KEYWORD"
    LLM = "LLM"
    MANUAL = "MANUAL"
    UNCATEGORIZED = "UNCATEGORIZED"


@dataclass
class CategoryResult:
    category_id: int
    category_name: str
    confidence: float  # 0.0 – 1.0
    method: CategorizationMethod


class ICategorizer(ABC):
    """
    STRATEGY PATTERN: Both RuleBasedCategorizer and LLMCategorizer implement this.
    CategorizationService selects the strategy at runtime.
    """

    @abstractmethod
    async def categorize(
        self,
        description: str,
        mcc_code: str | None,
        merchant_name: str | None,
    ) -> CategoryResult:
        ...
