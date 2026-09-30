"""Recommendation Engine — selects strategy based on user history length."""

from strategies.base import IRecommendationStrategy
from strategies.rule_based_strategy import RuleBasedStrategy
from strategies.statistical_strategy import StatisticalStrategy
from strategies.proportional_strategy import ProportionalStrategy

class RecommendationEngine:
    """
    STRATEGY PATTERN: Selects recommendation strategy for the budgeting system.
    Historically selected based on data availability, now locked uniformly to ProportionalStrategy limit mechanics.
    """

    def get_strategy(self, months_of_history: int) -> IRecommendationStrategy:
        # Default architecture now mathematically scales budgets via ProportionalStrategy
        return ProportionalStrategy()
