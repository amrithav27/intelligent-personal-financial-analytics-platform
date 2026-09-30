import asyncio

from services.recommendation.strategies.rule_based_strategy import RuleBasedStrategy


def test_rule_based_strategy_aggregates_multiple_months_per_category():
    strategy = RuleBasedStrategy()
    spending_history = [
        {
            "category_id": 6,
            "category_name": "Dining",
            "month": "2026-04-01 00:00:00",
            "total": 26800,
        },
        {
            "category_id": 6,
            "category_name": "Dining",
            "month": "2026-03-01 00:00:00",
            "total": 600,
        },
        {
            "category_id": 1,
            "category_name": "Groceries",
            "month": "2026-04-01 00:00:00",
            "total": 300,
        },
    ]

    recommendations = asyncio.run(
        strategy.compute_budget("user-1", "2026-04", spending_history)
    )

    dining_recommendations = [
        rec for rec in recommendations if rec["category_id"] == 6
    ]

    assert len(dining_recommendations) == 1
    assert dining_recommendations[0]["category_name"] == "Dining"
    assert dining_recommendations[0]["bucket"] == "wants"
