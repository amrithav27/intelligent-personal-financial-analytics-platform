"""Statistical Strategy — percentile-based budgets for users with >= 6 months history."""

import statistics
from strategies.base import IRecommendationStrategy

CATEGORY_NAMES = {
    1: "Groceries", 2: "Transportation", 3: "Utilities", 4: "Entertainment",
    5: "Healthcare", 6: "Dining", 7: "Shopping", 8: "Education", 9: "Travel",
    10: "Investments", 11: "Rent/Housing", 12: "Insurance", 13: "Personal Care",
    14: "Subscriptions", 15: "Other",
}


class StatisticalStrategy(IRecommendationStrategy):
    """
    Used when user has >= 6 months of history.
    Computes per-category recommendations as the 25th percentile of
    the user's own spending in that category (conservative budget).
    """

    async def compute_budget(self, user_id, month, spending_history):
        # Group by category
        category_monthly: dict[int, list[float]] = {}
        for h in spending_history:
            cat_id = h.get("category_id", 15)
            if cat_id not in category_monthly:
                category_monthly[cat_id] = []
            category_monthly[cat_id].append(h.get("total", 0))

        recommendations = []
        for category_id, monthly_amounts in category_monthly.items():
            if not monthly_amounts:
                continue
            sorted_amounts = sorted(monthly_amounts)
            # 25th percentile (conservative target)
            idx = max(0, int(len(sorted_amounts) * 0.25) - 1)
            p25 = sorted_amounts[idx]
            # Median for reference
            median = statistics.median(sorted_amounts)

            recommendations.append({
                "category_id": category_id,
                "category_name": CATEGORY_NAMES.get(category_id, "Other"),
                "recommended_amount": round(p25, 2),
                "median_spending": round(median, 2),
                "strategy": "statistical_p25",
            })

        return sorted(recommendations, key=lambda x: x["recommended_amount"], reverse=True)
