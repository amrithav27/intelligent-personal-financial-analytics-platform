"""FHS Processor — Financial Health Score computation (0–100)."""

from decimal import Decimal


class FHSProcessor:
    """
    Computes Financial Health Score (0–100) from four metrics.
    Each metric contributes equally (25 points max).
    """

    def compute(self, user_id: str, metrics: dict) -> Decimal:
        score = Decimal("0")

        # Component 1: Savings Rate (0–25 pts)
        savings_rate = Decimal(str(metrics.get("savings_rate", 0)))
        score += min(savings_rate / Decimal("0.20"), Decimal("1")) * 25

        # Component 2: Debt-to-Income Ratio (0–25 pts)
        dti = Decimal(str(metrics.get("dti_ratio", 0)))
        score += max(Decimal("0"), (1 - dti / Decimal("0.36"))) * 25

        # Component 3: Spending Volatility (0–25 pts)
        cv = Decimal(str(metrics.get("spending_volatility", 0)))
        score += max(Decimal("0"), (1 - cv / Decimal("0.5"))) * 25

        # Component 4: Emergency Fund Ratio (0–25 pts)
        ef_months = Decimal(str(metrics.get("emergency_fund_months", 0)))
        score += min(ef_months / Decimal("3"), Decimal("1")) * 25

        return round(score, 2)
