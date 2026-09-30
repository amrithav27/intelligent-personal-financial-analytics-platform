"""RuleBasedCategorizer — three-tier rule matching strategy."""

import re
from categorization.base import ICategorizer, CategoryResult, CategorizationMethod
from categorization.rules.mcc_codes import MCC_CODE_MAP
from categorization.rules.merchants import MERCHANT_MAP
from categorization.rules.keywords import KEYWORD_RULES


class RuleBasedCategorizer(ICategorizer):
    """
    Primary categorization strategy. Three-tier rule matching:
    1. MCC code exact match (confidence 0.95) — fastest, most reliable
    2. Merchant name exact match (confidence 0.90)
    3. Keyword/regex match on description (confidence 0.70)
    Falls through to 'Other' with confidence 0.0 if no rule matches.
    """

    async def categorize(
        self,
        description: str,
        mcc_code: str | None,
        merchant_name: str | None,
    ) -> CategoryResult:
        # Tier 1: MCC code lookup
        if mcc_code and mcc_code in MCC_CODE_MAP:
            cat = MCC_CODE_MAP[mcc_code]
            return CategoryResult(cat.id, cat.name, 0.95, CategorizationMethod.RULE_MCC)

        # Tier 2: Merchant name — contains match (case-insensitive)
        # e.g. "coffee at starbucks" → contains "STARBUCKS" → Dining
        if merchant_name:
            merchant_upper = merchant_name.strip().upper()
            # First try exact match (faster)
            if merchant_upper in MERCHANT_MAP:
                cat = MERCHANT_MAP[merchant_upper]
                return CategoryResult(
                    cat.id, cat.name, 0.90, CategorizationMethod.RULE_MERCHANT
                )
            # Then try contains match for partial names
            for known, cat in MERCHANT_MAP.items():
                if known in merchant_upper:
                    return CategoryResult(
                        cat.id, cat.name, 0.80, CategorizationMethod.RULE_MERCHANT
                    )

        # Tier 3: Keyword/regex on description
        desc_upper = (description or "").upper()
        for pattern, cat_id, cat_name in KEYWORD_RULES:
            if re.search(pattern, desc_upper):
                return CategoryResult(
                    cat_id, cat_name, 0.70, CategorizationMethod.RULE_KEYWORD
                )

        # No match
        return CategoryResult(15, "Other", 0.0, CategorizationMethod.UNCATEGORIZED)
