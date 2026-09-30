"""Trend Analyzer — computes monthly spending trends."""

from decimal import Decimal
from datetime import datetime
from collections import defaultdict


class TrendAnalyzer:
    """
    Computes spending trends over time for trend line charts.
    Aggregates monthly totals and calculates month-over-month changes.
    """

    def compute(self, transactions: list[dict], months: int = 6) -> list[dict]:
        """
        Input: list of {amount, currency, ts, category_name}
        Output: list of {month, total, categories: {category: amount}}
        """
        # Static exchange rates for normalization (Base: INR)
        EXCHANGE_RATES = {
            "INR": Decimal("1.0"),
            "USD": Decimal("83.0"),
            "EUR": Decimal("90.0"),
            "GBP": Decimal("105.0"),
        }

        monthly: dict[str, dict] = defaultdict(
            lambda: {"total": Decimal("0"), "categories": defaultdict(Decimal), "count": 0}
        )

        for txn in transactions:
            ts = txn.get("ts")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            month_key = ts.strftime("%Y-%m") if ts else "unknown"
            
            raw_amount = Decimal(str(txn.get("amount", 0)))
            currency = txn.get("currency", "INR").upper()
            rate = EXCHANGE_RATES.get(currency, Decimal("1.0"))
            
            # Normalize to INR
            amount = abs(raw_amount) * rate
            category = txn.get("category_name", "Other")

            monthly[month_key]["total"] += amount
            monthly[month_key]["categories"][category] += amount
            monthly[month_key]["count"] += 1

        # Sort by month and limit
        sorted_months = sorted(monthly.items(), key=lambda x: x[0])[-months:]

        result = []
        prev_total = None
        for month_key, data in sorted_months:
            mom_change = None
            if prev_total and prev_total > 0:
                mom_change = float(
                    (data["total"] - prev_total) / prev_total * 100
                )

            result.append(
                {
                    "month": month_key,
                    "total": float(data["total"]),
                    "count": data["count"],
                    "categories": {
                        k: float(v) for k, v in data["categories"].items()
                    },
                    "mom_change_percent": round(mom_change, 2) if mom_change is not None else None,
                }
            )
            prev_total = data["total"]

        return result
