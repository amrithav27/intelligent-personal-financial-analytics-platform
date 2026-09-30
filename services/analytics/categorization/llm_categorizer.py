"""LLM Categorizer — OpenAI-powered transaction classification with Redis caching."""

import hashlib
import json
import os
import logging

import openai
import redis.asyncio as aioredis
from categorization.base import ICategorizer, CategoryResult, CategorizationMethod

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial transaction categorizer.
Given a transaction description, respond with ONLY valid JSON:
{"category": "<category_name>", "confidence": <float 0-1>}
Valid categories: Groceries, Transportation, Utilities, Entertainment, Healthcare,
Dining, Shopping, Education, Travel, Investments, Rent/Housing, Insurance,
Personal Care, Subscriptions, Other"""

CATEGORY_NAME_TO_ID = {
    "Groceries": 1, "Transportation": 2, "Utilities": 3, "Entertainment": 4,
    "Healthcare": 5, "Dining": 6, "Shopping": 7, "Education": 8, "Travel": 9,
    "Investments": 10, "Rent/Housing": 11, "Insurance": 12, "Personal Care": 13,
    "Subscriptions": 14, "Other": 15,
}


class LLMCategorizer(ICategorizer):
    """
    Secondary categorization strategy — only invoked when:
    1. ENABLE_LLM_CATEGORIZATION=true
    2. Rule-based confidence < LLM_CONFIDENCE_THRESHOLD (default 0.7)
    Results cached in Redis for 24h by SHA-256 of description.
    On OpenAI API failure, silently falls back to rule-based result.
    """

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    async def categorize(
        self,
        description: str,
        mcc_code: str | None,
        merchant_name: str | None,
    ) -> CategoryResult:
        cache_key = f"llm_category:{hashlib.sha256(description.encode()).hexdigest()}"

        # Check Redis cache first
        cached = await self.redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return CategoryResult(
                data["category_id"],
                data["category_name"],
                data["confidence"],
                CategorizationMethod.LLM,
            )

        # Call OpenAI API
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Description: {description}"},
                ],
                max_tokens=50,
                temperature=0,
            )
            raw = json.loads(response.choices[0].message.content)
            category_name = raw["category"]
            category_id = CATEGORY_NAME_TO_ID.get(category_name, 15)
            confidence = float(raw["confidence"])

            result = CategoryResult(
                category_id, category_name, confidence, CategorizationMethod.LLM
            )

            # Cache result (24h TTL)
            await self.redis.setex(
                cache_key,
                86400,
                json.dumps(
                    {
                        "category_id": category_id,
                        "category_name": category_name,
                        "confidence": confidence,
                    }
                ),
            )
            return result

        except Exception as e:
            logger.warning(f"LLM categorization failed: {e}")
            raise
