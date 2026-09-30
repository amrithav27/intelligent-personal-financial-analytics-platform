"""Category Aggregator — computes category distribution for a user/month."""

from decimal import Decimal
from datetime import datetime
from typing import Any


class CategoryAggregator:
    """
    Aggregates transaction amounts by category for a given month.
    Used by the dashboard to show spending distribution.
    """

    def compute(self, transactions: list[dict]) -> list[dict]:
        """
        Input: list of {category_id, category_name, amount}
        Output: list of {category, amount, count, percentage}
        """
        aggregation: dict[str, dict[str, Any]] = {}
        total = Decimal("0")

        for txn in transactions:
            cat_name = txn.get("category_name", "Other")
            amount = Decimal(str(txn.get("amount", 0)))
            total += abs(amount)

            if cat_name not in aggregation:
                aggregation[cat_name] = {
                    "category": cat_name,
                    "category_id": txn.get("category_id", 15),
                    "amount": Decimal("0"),
                    "count": 0,
                }

            aggregation[cat_name]["amount"] += abs(amount)
            aggregation[cat_name]["count"] += 1

        # Calculate percentages
        result = []
        for cat_data in aggregation.values():
            pct = (cat_data["amount"] / total * 100) if total > 0 else Decimal("0")
            result.append(
                {
                    "category": cat_data["category"],
                    "category_id": cat_data["category_id"],
                    "amount": float(cat_data["amount"]),
                    "count": cat_data["count"],
                    "percentage": float(round(pct, 2)),
                }
            )

        return sorted(result, key=lambda x: x["amount"], reverse=True)
