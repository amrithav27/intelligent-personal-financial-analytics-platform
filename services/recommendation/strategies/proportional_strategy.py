"""Proportional Strategy — income-scaled budgets with 50/30/20 guardrails.

Computes per-category budgets proportionally based on historical expenditure
patterns relative to historical income, then scales them to the current
month's income.  The 50/30/20 rule is applied as a soft guardrail to ensure
needs categories don't exceed 50% of income, wants don't exceed 30%, and
at least 20% is preserved for savings/investments.
"""

from strategies.base import IRecommendationStrategy

CATEGORY_NAMES = {
    1: "Groceries", 2: "Transportation", 3: "Utilities", 4: "Entertainment",
    5: "Healthcare", 6: "Dining", 7: "Shopping", 8: "Education", 9: "Travel",
    10: "Investments", 11: "Rent/Housing", 12: "Insurance", 13: "Personal Care",
    14: "Subscriptions", 15: "Other",
}

# 50/30/20 bucket classification
NEEDS_CATEGORIES = {1, 2, 3, 5, 11, 12}       # Groceries, Transport, Utilities, Healthcare, Rent, Insurance
WANTS_CATEGORIES = {4, 6, 7, 8, 9, 13, 14, 15}  # Entertainment, Dining, Shopping, Education, Travel, Personal Care, Subs, Other
SAVINGS_CATEGORIES = {10}                       # Investments


class ProportionalStrategy(IRecommendationStrategy):
    """
    STRATEGY PATTERN implementation — Proportional Income Strategy.

    Algorithm:
    1. Aggregate all expenditure from months *before* the target month, grouped by category.
    2. Compute each category's proportion = (category_past_spend / total_past_income).
    3. Budget for each category = current_month_income × proportion.
    4. Apply 50/30/20 soft caps: if the proportional totals for "needs" exceed
       50% of income, scale them down; similarly for "wants" at 30%.  The
       remaining 20% is always reserved for savings.
    """

    async def compute_budget(
        self, user_id: str, month: str, spending_history: list,
        past_income: float = 0.0, current_income: float = 0.0
    ) -> list[dict]:

        # ── 1. Separate past-only spending (exclude the target month) ─────────
        category_past_totals: dict[int, float] = {}

        for h in spending_history:
            h_month_str = str(h.get("month", ""))
            cat_id = h.get("category_id", 15)

            # Only include months *before* the target month
            if not h_month_str.startswith(month):
                category_past_totals[cat_id] = (
                    category_past_totals.get(cat_id, 0.0) + h.get("total", 0.0)
                )

        # ── 2. Compute raw proportions ────────────────────────────────────────
        raw_budgets: dict[int, float] = {}
        for category_id, total_spend in category_past_totals.items():
            if past_income > 0:
                proportion = total_spend / past_income
            else:
                proportion = 0.0

            raw_budgets[category_id] = current_income * proportion

        # ── 3. Apply 50/30/20 guardrails ──────────────────────────────────────
        needs_total = sum(v for k, v in raw_budgets.items() if k in NEEDS_CATEGORIES)
        wants_total = sum(v for k, v in raw_budgets.items() if k in WANTS_CATEGORIES)

        needs_cap = current_income * 0.50
        wants_cap = current_income * 0.30

        # Scale down if a bucket exceeds its cap
        needs_scale = (needs_cap / needs_total) if needs_total > needs_cap else 1.0
        wants_scale = (wants_cap / wants_total) if wants_total > wants_cap else 1.0

        final_budgets: dict[int, float] = {}
        for cat_id, amount in raw_budgets.items():
            if cat_id in NEEDS_CATEGORIES:
                final_budgets[cat_id] = amount * needs_scale
            elif cat_id in WANTS_CATEGORIES:
                final_budgets[cat_id] = amount * wants_scale
            else:
                final_budgets[cat_id] = amount  # savings — pass through

        # ── 4. Ensure a savings recommendation exists (20% floor) ─────────────
        savings_floor = current_income * 0.20
        existing_savings = sum(v for k, v in final_budgets.items() if k in SAVINGS_CATEGORIES)
        if existing_savings < savings_floor and current_income > 0:
            # category 10 = Investments / Savings
            final_budgets[10] = max(final_budgets.get(10, 0.0), savings_floor)

        # ── 5. Build recommendation list ──────────────────────────────────────
        recommendations = []
        for category_id, amount in final_budgets.items():
            if amount <= 0:
                continue

            # Determine bucket label
            if category_id in NEEDS_CATEGORIES:
                bucket = "needs"
            elif category_id in WANTS_CATEGORIES:
                bucket = "wants"
            else:
                bucket = "savings"

            recommendations.append({
                "category_id": category_id,
                "category_name": CATEGORY_NAMES.get(category_id, "Other"),
                "recommended_amount": round(amount, 2),
                "strategy": "proportional_income",
                "bucket": bucket,
            })

        return sorted(recommendations, key=lambda x: x["recommended_amount"], reverse=True)
