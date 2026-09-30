"""Rule-Based Strategy — 50/30/20 budget rule for users with < 6 months history."""

from strategies.base import IRecommendationStrategy

# Category classifications
NEEDS_CATEGORIES = {1, 2, 3, 5, 11}  # Groceries, Transport, Utilities, Healthcare, Rent
WANTS_CATEGORIES = {4, 6, 7, 9, 13, 14}  # Entertainment, Dining, Shopping, Travel, Personal Care, Subs

CATEGORY_NAMES = {
    1: "Groceries", 2: "Transportation", 3: "Utilities", 4: "Entertainment",
    5: "Healthcare", 6: "Dining", 7: "Shopping", 8: "Education", 9: "Travel",
    10: "Investments", 11: "Rent/Housing", 12: "Insurance", 13: "Personal Care",
    14: "Subscriptions", 15: "Other",
}

def _aggregate_history_by_category(spending_history: list[dict]) -> list[dict]:
    """Collapse category-month rows into one row per category."""
    categories: dict[int, dict] = {}
    for row in spending_history:
        category_id = row.get("category_id")
        if category_id is None:
            continue

        category = categories.setdefault(
            category_id,
            {
                "category_id": category_id,
                "category_name": row.get("category_name") or CATEGORY_NAMES.get(category_id, "Other"),
                "total": 0.0,
            },
        )
        category["total"] += float(row.get("total", 0) or 0)

    return list(categories.values())


def _average_monthly_spend(spending_history: list[dict]) -> float:
    monthly_totals: dict[str, float] = {}
    for row in spending_history:
        month = row.get("month") or "unknown"
        monthly_totals[month] = monthly_totals.get(month, 0.0) + float(row.get("total", 0) or 0)

    if not monthly_totals:
        return 0.0
    return sum(monthly_totals.values()) / len(monthly_totals)


class RuleBasedStrategy(IRecommendationStrategy):
    """
    Used when user has < 6 months of history.
    Applies the 50/30/20 rule to estimated monthly income:
    50% Needs (groceries, utilities, rent, transport, healthcare)
    30% Wants (dining, entertainment, shopping, subscriptions, travel)
    20% Savings/Debt
    """

    async def compute_budget(self, user_id, month, spending_history):
        # Estimate income from last available spending (assume spending = 80% of income)
        if spending_history:
            avg_spend = _average_monthly_spend(spending_history)
            estimated_income = max(50000, avg_spend / 0.80) # Floor at 50k to avoid tiny budgets for new users
        else:
            estimated_income = 50000  # Default INR

        needs_budget = estimated_income * 0.50
        wants_budget = estimated_income * 0.30
        savings_budget = estimated_income * 0.20

        category_history = _aggregate_history_by_category(spending_history)

        # Distribute needs budget across need categories proportionally
        needs_cats = [h for h in category_history if h.get("category_id") in NEEDS_CATEGORIES]
        wants_cats = [h for h in category_history if h.get("category_id") in WANTS_CATEGORIES]

        recommendations = []

        # Distribute needs budget
        total_needs_spend = sum(h.get("total", 0) for h in needs_cats) or 1
        for h in needs_cats:
            proportion = h.get("total", 0) / total_needs_spend
            recommendations.append({
                "category_id": h["category_id"],
                "category_name": CATEGORY_NAMES.get(h["category_id"], "Other"),
                "recommended_amount": round(needs_budget * proportion, 2),
                "strategy": "50/30/20",
                "bucket": "needs",
            })

        # Distribute wants budget
        total_wants_spend = sum(h.get("total", 0) for h in wants_cats) or 1
        for h in wants_cats:
            proportion = h.get("total", 0) / total_wants_spend
            recommendations.append({
                "category_id": h["category_id"],
                "category_name": CATEGORY_NAMES.get(h["category_id"], "Other"),
                "recommended_amount": round(wants_budget * proportion, 2),
                "strategy": "50/30/20",
                "bucket": "wants",
            })

        # Savings / Investments recommendation (category_id=10 = 'Investments' in DB)
        recommendations.append({
            "category_id": 10,
            "category_name": "Investments / Savings",
            "recommended_amount": round(savings_budget, 2),
            "strategy": "50/30/20",
            "bucket": "savings",
        })

        return recommendations
