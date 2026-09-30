"""Unit tests for the rule-based categorizer."""
import asyncio
import pytest
from services.analytics.categorization.rule_based import RuleBasedCategorizer
from services.analytics.categorization.base import CategorizationMethod


categorizer = RuleBasedCategorizer()


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestMCCCodeCategorization:
    def test_grocery_mcc(self):
        result = run(categorizer.categorize("Purchase", "5411", None))
        assert result.category_name == "Groceries"
        assert result.confidence == 0.95
        assert result.method == CategorizationMethod.RULE_MCC

    def test_transport_mcc(self):
        result = run(categorizer.categorize("Ride", "4121", None))
        assert result.category_name == "Transportation"

    def test_dining_mcc(self):
        result = run(categorizer.categorize("Meal", "5812", None))
        assert result.category_name == "Dining"


class TestMerchantNameCategorization:
    def test_swiggy(self):
        result = run(categorizer.categorize("Order payment", None, "Swiggy"))
        assert result.category_name == "Dining"
        assert result.confidence == 0.90
        assert result.method == CategorizationMethod.RULE_MERCHANT

    def test_amazon(self):
        result = run(categorizer.categorize("Purchase", None, "Amazon"))
        assert result.category_name == "Shopping"

    def test_uber(self):
        result = run(categorizer.categorize("Trip", None, "Uber"))
        assert result.category_name == "Transportation"

    def test_netflix(self):
        result = run(categorizer.categorize("Subscription", None, "Netflix"))
        assert result.category_name == "Entertainment"


class TestKeywordCategorization:
    def test_grocery_keyword(self):
        result = run(categorizer.categorize("BIGBASKET ORDER #123", None, None))
        assert result.category_name == "Groceries"
        assert result.confidence == 0.70
        assert result.method == CategorizationMethod.RULE_KEYWORD

    def test_fuel_keyword(self):
        result = run(categorizer.categorize("PETROL PUMP FUEL", None, None))
        assert result.category_name == "Transportation"

    def test_electricity_keyword(self):
        result = run(categorizer.categorize("ELECTRICITY BILL PAYMENT", None, None))
        assert result.category_name == "Utilities"

    def test_restaurant_keyword(self):
        result = run(categorizer.categorize("DINNER AT RESTAURANT", None, None))
        assert result.category_name == "Dining"


class TestFallback:
    def test_uncategorized(self):
        result = run(categorizer.categorize("RANDOM UNKNOWN ENTRY XYZ", None, None))
        assert result.category_name == "Other"
        assert result.confidence == 0.0
        assert result.method == CategorizationMethod.UNCATEGORIZED


class TestPriority:
    """MCC should take priority over merchant name and keywords."""

    def test_mcc_priority_over_merchant(self):
        # MCC says Groceries (5411), merchant says Dining (Swiggy)
        result = run(categorizer.categorize("Order", "5411", "Swiggy"))
        assert result.category_name == "Groceries"
        assert result.method == CategorizationMethod.RULE_MCC

    def test_merchant_priority_over_keyword(self):
        # No MCC, merchant says Dining (Zomato), description says Shopping
        result = run(categorizer.categorize("SHOPPING AT MALL", None, "Zomato"))
        assert result.category_name == "Dining"
        assert result.method == CategorizationMethod.RULE_MERCHANT
