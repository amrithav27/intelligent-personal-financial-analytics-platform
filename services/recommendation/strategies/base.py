"""STRATEGY PATTERN — Base interface for recommendation strategies."""

from abc import ABC, abstractmethod


class IRecommendationStrategy(ABC):
    @abstractmethod
    async def compute_budget(
        self, user_id: str, month: str, spending_history: list, past_income: float = 0.0, current_income: float = 0.0
    ) -> list[dict]:
        ...
