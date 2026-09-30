"""CategorizationService — Strategy pattern orchestrator."""

import os
import logging
from categorization.base import ICategorizer, CategoryResult
from categorization.rule_based import RuleBasedCategorizer
from categorization.llm_categorizer import LLMCategorizer

logger = logging.getLogger(__name__)


class CategorizationService:
    """
    STRATEGY PATTERN orchestrator.
    Selects the categorization strategy based on:
    1. Feature flag ENABLE_LLM_CATEGORIZATION
    2. Rule-based confidence vs. LLM_CONFIDENCE_THRESHOLD
    """

    def __init__(self, redis_client=None):
        self.rule_categorizer = RuleBasedCategorizer()
        self.llm_categorizer = LLMCategorizer(redis_client) if redis_client else None
        self.llm_enabled = os.getenv("ENABLE_LLM_CATEGORIZATION", "false").lower() == "true"
        self.llm_threshold = float(os.getenv("LLM_CONFIDENCE_THRESHOLD", "0.7"))

    async def categorize(
        self,
        description: str,
        mcc_code: str | None,
        merchant_name: str | None,
    ) -> CategoryResult:
        # Always run rule-based first
        rule_result = await self.rule_categorizer.categorize(
            description, mcc_code, merchant_name
        )

        # Upgrade to LLM if: flag is on AND rule confidence is below threshold AND LLM is available
        if (
            self.llm_enabled
            and self.llm_categorizer
            and rule_result.confidence < self.llm_threshold
        ):
            try:
                return await self.llm_categorizer.categorize(
                    description, mcc_code, merchant_name
                )
            except Exception:
                pass  # LLM failed → use rule result (graceful degradation)

        return rule_result
