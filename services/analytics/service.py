"""AnalyticsService — orchestrates categorization, FHS computation, caching,
ClickHouse dual-writes, and OLAP reads (ADR-002 polyglot persistence)."""

import json
import logging
from decimal import Decimal
import httpx
from datetime import datetime, timedelta

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from categorization.service import CategorizationService
from processors.fhs_processor import FHSProcessor
from processors.category_aggregator import CategoryAggregator
from processors.trend_analyzer import TrendAnalyzer
from cache import CacheInvalidator
from clickhouse_writer import ClickHouseWriter

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(
        self,
        db: AsyncSession,
        redis_client: aioredis.Redis,
        categorization_service: CategorizationService,
        cache_invalidator: CacheInvalidator,
        clickhouse_writer: ClickHouseWriter | None = None,
        anomaly_service_url: str | None = None,
    ):
        self.db = db
        self.redis = redis_client
        self.categorizer = categorization_service
        self.cache_invalidator = cache_invalidator
        self.ch_writer = clickhouse_writer
        self.anomaly_service_url = anomaly_service_url
        self.fhs_processor = FHSProcessor()
        self.category_aggregator = CategoryAggregator()
        self.trend_analyzer = TrendAnalyzer()

    async def process_ingestion_event(self, user_id: str, transaction_ids: list[str]) -> dict:
        """
        Main analytics pipeline triggered after transaction ingestion:
        1. Categorize each new transaction
        2. Mirror categorized transactions to ClickHouse (OLAP layer)
        3. Recompute FHS
        4. Invalidate cache
        5. Write FHS to ClickHouse (async)
        6. Notify Anomaly Detection Service
        """
        # 1. Load and categorize new transactions
        categorized = 0
        categorized_txns = []  # Track for ClickHouse mirroring
        for txn_id in transaction_ids:
            row = await self.db.execute(
                text("SELECT id, raw_description, mcc_code, merchant_name, amount, currency, ts "
                     "FROM transactions WHERE id = :id"),
                {"id": txn_id},
            )
            txn = row.fetchone()
            if not txn:
                continue

            result = await self.categorizer.categorize(
                txn.raw_description or "", txn.mcc_code, txn.merchant_name
            )

            # Insert categorization result
            await self.db.execute(
                text(
                    "INSERT INTO transaction_categories "
                    "(transaction_id, category_id, confidence, method, categorizer_version) "
                    "VALUES (:txn_id, :cat_id, :conf, :method, 'v1')"
                ),
                {
                    "txn_id": txn.id,
                    "cat_id": result.category_id,
                    "conf": result.confidence,
                    "method": result.method.value,
                },
            )
            categorized += 1
            categorized_txns.append({
                "id": str(txn.id), "amount": float(txn.amount),
                "currency": txn.currency, "category_id": result.category_id,
                "ts": str(txn.ts),
            })

        # 2. Mirror categorized transactions to ClickHouse (OLAP layer)
        #    Populates the phoenix.transactions table used for analytical trend queries.
        #    This is the key dual-write that enables OLAP/OLTP separation (ADR-002).
        if self.ch_writer and categorized_txns:
            for ct in categorized_txns:
                await self.ch_writer.write_transaction(
                    txn_id=ct["id"], user_id=user_id, amount=ct["amount"],
                    currency=ct["currency"], category_id=ct["category_id"],
                    ts=ct["ts"],
                )

        # 3. Compute FHS
        metrics = await self._compute_user_metrics(user_id)
        fhs_score = self.fhs_processor.compute(user_id, metrics)

        # Persist FHS (append-only) to PostgreSQL (source of truth)
        await self.db.execute(
            text(
                "INSERT INTO financial_health_scores "
                "(user_id, score, savings_rate, dti_ratio, spending_volatility, emergency_fund_ratio) "
                "VALUES (:user_id, :score, :savings_rate, :dti_ratio, :volatility, :ef_ratio)"
            ),
            {
                "user_id": user_id,
                "score": float(fhs_score),
                "savings_rate": metrics.get("savings_rate", 0),
                "dti_ratio": metrics.get("dti_ratio", 0),
                "volatility": metrics.get("spending_volatility", 0),
                "ef_ratio": metrics.get("emergency_fund_months", 0),
            },
        )
        await self.db.commit()

        # 4. Invalidate cache
        current_month = datetime.utcnow().strftime("%Y-%m")
        await self.cache_invalidator.invalidate_user(user_id, current_month)

        # 5. Write FHS to ClickHouse (async, fire-and-forget)
        if self.ch_writer:
            await self.ch_writer.write_fhs(
                user_id,
                {
                    "score": float(fhs_score),
                    "savings_rate": metrics.get("savings_rate", 0),
                    "dti_ratio": metrics.get("dti_ratio", 0),
                    "spending_volatility": metrics.get("spending_volatility", 0),
                },
            )

        # 6. Backfill historical FHS so the history graph has data immediately
        #    after the first CSV upload (not just a single dot).
        await self._backfill_historical_fhs(user_id)

        # 7. Notify Anomaly Detection Service (Observer chain continuation)
        if self.anomaly_service_url and categorized > 0:
            await self._notify_anomaly_service(user_id, transaction_ids)

        return {"categorized": categorized, "fhs_score": float(fhs_score)}

    async def _notify_anomaly_service(self, user_id: str, transaction_ids: list[str]) -> None:
        """Forward the analytics-complete event to the Anomaly Detection service."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.anomaly_service_url}/internal/events/analytics-complete",
                    json={"user_id": user_id, "transaction_ids": transaction_ids},
                )
                logger.info(
                    f"Anomaly service notified for user {user_id}: "
                    f"status={resp.status_code}, body={resp.json()}"
                )
        except Exception as e:
            # Non-blocking: anomaly failure must not break analytics pipeline
            logger.warning(f"Failed to notify anomaly service for user {user_id}: {e}")

    async def get_dashboard_overview(self, user_id: str) -> dict:
        """
        FACADE PATTERN: Single endpoint aggregating data from multiple sources.
        Redis cache → ClickHouse (OLAP) → PostgreSQL (OLTP fallback).
        """
        # Check cache first
        cache_key = f"dashboard:{user_id}:overview"
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # Build overview from DB
        fhs = await self._get_latest_fhs(user_id)
        categories = await self._get_category_distribution(user_id)
        recent_txns = await self._get_recent_transactions(user_id, limit=10)
        unread_alerts = await self._get_unread_alert_count(user_id)
        budget_status = await self._get_budget_status(user_id)

        overview = {
            "fhs": fhs,
            "categories": categories,
            "recent_transactions": recent_txns,
            "unread_alerts": unread_alerts,
            "budget_status": budget_status,
        }

        # Backfill history if needed (e.g., 15-day intervals for 6 months)
        await self._backfill_historical_fhs(user_id)

        # Cache for 30s
        await self.redis.setex(cache_key, 30, json.dumps(overview, default=str))
        return overview

    # ── ClickHouse OLAP Read Methods (with PostgreSQL fallback) ─────────────

    async def get_fhs_history_from_clickhouse(self, user_id: str, limit: int = 12) -> dict:
        """
        Read FHS score time-series from ClickHouse (OLAP).
        Falls back to PostgreSQL if ClickHouse is unavailable or has sparse data.
        Returns {"data": [...], "data_source": "clickhouse"|"postgresql"}.
        """
        # Ensure backfilled scores exist before reading history.
        # This is essential for new users whose first CSV upload triggers
        # process_ingestion_event (which also backfills), but this endpoint
        # may be called independently or before the ingestion pipeline finishes.
        await self._backfill_historical_fhs(user_id)

        # Try ClickHouse first (OLAP — columnar scan, partitioned by month)
        if self.ch_writer:
            rows = await self.ch_writer.query_fhs_history(user_id, limit)
            # Only use ClickHouse if it returned a meaningful number of rows.
            # Fire-and-forget CH writes may not have landed yet, so fall through
            # to PostgreSQL (the synchronous source of truth) when CH is sparse.
            if rows and len(rows) >= 2:
                return {
                    "data": [
                        {
                            "score": float(r.get("score", 0)),
                            "savings_rate": float(r.get("savings_rate", 0)),
                            "dti_ratio": float(r.get("dti_ratio", 0)),
                            "spending_volatility": float(r.get("spending_volatility", 0)),
                            "computed_at": r.get("computed_at"),
                        }
                        for r in rows
                    ],
                    "data_source": "clickhouse",
                }

        # Fallback: PostgreSQL (OLTP) — always has backfilled data synchronously
        result = await self.db.execute(
            text(
                "SELECT score, savings_rate, dti_ratio, spending_volatility, computed_at "
                "FROM financial_health_scores "
                "WHERE user_id = :uid ORDER BY computed_at DESC LIMIT :limit"
            ),
            {"uid": user_id, "limit": limit},
        )
        return {
            "data": [
                {
                    "score": float(row.score),
                    "savings_rate": float(row.savings_rate) if row.savings_rate else None,
                    "dti_ratio": float(row.dti_ratio) if row.dti_ratio else None,
                    "spending_volatility": float(row.spending_volatility) if row.spending_volatility else None,
                    "computed_at": str(row.computed_at),
                }
                for row in result.fetchall()
            ],
            "data_source": "postgresql",
        }

    async def get_spending_trends_from_clickhouse(self, user_id: str, months: int = 6) -> dict:
        """
        Read spending trends from ClickHouse (OLAP) with PostgreSQL fallback.
        ClickHouse advantage: columnar scan on (amount, ts) without touching other columns.
        Returns {"data": [...], "data_source": "clickhouse"|"postgresql"}.
        """
        # Try ClickHouse first
        if self.ch_writer:
            rows = await self.ch_writer.query_spending_trends(user_id, months)
            if rows:
                result_data = []
                prev_total = None
                for r in rows:
                    total = float(r.get("total", 0))
                    mom_change = None
                    if prev_total and prev_total > 0:
                        mom_change = round((total - prev_total) / prev_total * 100, 2)
                    result_data.append({
                        "month": str(r.get("month", ""))[:7],  # YYYY-MM
                        "total": total,
                        "count": int(r.get("tx_count", 0)),
                        "mom_change_percent": mom_change,
                    })
                    prev_total = total
                return {"data": result_data, "data_source": "clickhouse"}

        # Fallback: PostgreSQL (OLTP) — uses TrendAnalyzer
        result = await self.db.execute(
            text(
                "SELECT t.amount, t.currency, t.ts, COALESCE(c.name, 'Other') as category_name "
                "FROM transactions t "
                "LEFT JOIN transaction_categories tc ON t.id = tc.transaction_id "
                "LEFT JOIN categories c ON tc.category_id = c.id "
                "WHERE t.user_id = :uid "
                "AND t.ts >= CURRENT_DATE - (INTERVAL '1 month' * :months) "
                "ORDER BY t.ts"
            ),
            {"uid": user_id, "months": months},
        )
        txns = [
            {
                "amount": float(row.amount), "currency": row.currency,
                "ts": row.ts, "category_name": row.category_name,
            }
            for row in result.fetchall()
        ]
        return {"data": self.trend_analyzer.compute(txns, months), "data_source": "postgresql"}

    async def _backfill_historical_fhs(self, user_id: str):
        """Ensure FHS scores exist at 15-day intervals for the last 6 months.
        
        Only backfills dates that fall within the user's transaction history range,
        so we don't create meaningless zero-score entries for months before the user
        had any transactions.
        """
        # Check existing scores for this user
        result = await self.db.execute(
            text("SELECT computed_at FROM financial_health_scores WHERE user_id = :uid ORDER BY computed_at DESC"),
            {"uid": user_id}
        )
        existing_dates = {row.computed_at.date() for row in result.fetchall()}

        # Find the earliest transaction date so we don't backfill before the user had data
        earliest_result = await self.db.execute(
            text("SELECT MIN(ts) as min_ts FROM transactions WHERE user_id = :uid"),
            {"uid": user_id}
        )
        earliest_ts = earliest_result.scalar()
        if not earliest_ts:
            return  # No transactions at all — nothing to backfill
        earliest_date = earliest_ts.date() if hasattr(earliest_ts, 'date') else earliest_ts

        now = datetime.now()
        # Today's score
        if now.date() not in existing_dates:
            await self._compute_and_save_fhs(user_id, now)
            existing_dates.add(now.date())

        # Backfill at 15-day intervals, but only back to the earliest transaction date
        for i in range(15, 181, 15):
            ref_date = now - timedelta(days=i)
            # Don't backfill before the user's earliest transaction
            if ref_date.date() < earliest_date:
                break
            if ref_date.date() not in existing_dates:
                # To be efficient, we only backfill if there's no score within +/- 3 days of this window
                near_hit = any(abs((d - ref_date.date()).days) <= 3 for d in existing_dates)
                if not near_hit:
                    await self._compute_and_save_fhs(user_id, ref_date)
                    existing_dates.add(ref_date.date())

    async def _compute_and_save_fhs(self, user_id: str, ref_date: datetime):
        """Force compute and save FHS for a specific date."""
        metrics = await self._compute_user_metrics(user_id, ref_date)
        processor = FHSProcessor()
        score = processor.compute(user_id, metrics)
        
        await self.db.execute(
            text(
                "INSERT INTO financial_health_scores (user_id, score, savings_rate, dti_ratio, spending_volatility, emergency_fund_ratio, computed_at) "
                "VALUES (:uid, :score, :sr, :dti, :cv, :ef, :ts)"
            ),
            {
                "uid": user_id, 
                "score": float(score), 
                "sr": metrics.get("savings_rate"), 
                "dti": metrics.get("dti_ratio"), 
                "cv": metrics.get("spending_volatility"), 
                "ef": metrics.get("emergency_fund_months"), 
                "ts": ref_date
            }
        )
        await self.db.commit()

        # Mirror backfilled FHS to ClickHouse so the OLAP read path can see it
        if self.ch_writer:
            fhs_data = {
                "score": float(score),
                "savings_rate": metrics.get("savings_rate", 0),
                "dti_ratio": metrics.get("dti_ratio", 0),
                "spending_volatility": metrics.get("spending_volatility", 0),
            }
            await self.ch_writer.write_fhs(user_id, fhs_data, computed_at=ref_date)

    async def _compute_user_metrics(self, user_id: str, ref_date: datetime | None = None) -> dict:
        """Compute financial health metrics from transaction history as of a specific date.
        
        Only uses COMPLETE months (excludes the partial month containing ref_date)
        to prevent partial-month data from distorting ratios and volatility.
        Falls back to including the partial month if no complete months exist yet.
        """
        if ref_date is None:
            ref_date = datetime.now()

        # Use only complete months: truncate ref_date to the start of its month
        # so we only include months that have a full set of transactions.
        month_start = ref_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # First try: only complete months (before the ref_date's month)
        result = await self.db.execute(
            text(
                "SELECT DATE_TRUNC('month', ts) as month, "
                "SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income, "
                "SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as expenses "
                "FROM transactions WHERE user_id = :uid "
                "AND ts < :month_start "
                "GROUP BY DATE_TRUNC('month', ts) ORDER BY month DESC LIMIT 6"
            ),
            {"uid": user_id, "month_start": month_start},
        )
        rows = result.fetchall()

        # Fallback: if no complete months exist, include the current partial month
        if not rows:
            result = await self.db.execute(
                text(
                    "SELECT DATE_TRUNC('month', ts) as month, "
                    "SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income, "
                    "SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as expenses "
                    "FROM transactions WHERE user_id = :uid "
                    "AND ts <= :ref_date "
                    "GROUP BY DATE_TRUNC('month', ts) ORDER BY month DESC LIMIT 6"
                ),
                {"uid": user_id, "ref_date": ref_date},
            )
            rows = result.fetchall()

        if not rows:
            return {"savings_rate": 0, "dti_ratio": 0, "spending_volatility": 0, "emergency_fund_months": 0}

        monthly_incomes = [float(row.income) for row in rows]
        monthly_expenses = [float(row.expenses) for row in rows]
        
        total_income = sum(monthly_incomes)
        total_expenses = sum(monthly_expenses)
        avg_monthly_expenses = total_expenses / len(monthly_expenses) if monthly_expenses else 0

        # Savings Rate Calculation: (Income - Expenses) / Income
        if total_income > 0:
            savings_rate = max(0, (total_income - total_expenses) / total_income)
        else:
            savings_rate = 0

        # Spending Volatility (CV of expenses)
        if len(monthly_expenses) > 1 and avg_monthly_expenses > 0:
            variance = sum((x - avg_monthly_expenses) ** 2 for x in monthly_expenses) / len(monthly_expenses)
            std_dev = variance ** 0.5
            cv = std_dev / avg_monthly_expenses
        else:
            cv = 0

        # Debt-to-Income estimation: use recurring fixed payments (rent, insurance,
        # loan-like categories) as a proxy for debt obligations.
        # Look at the most recent complete month's data for this.
        dti_ratio = 0.15  # sensible default
        if monthly_incomes and monthly_incomes[0] > 0:
            # Use most recent month's figures — latest row after DESC sort
            latest_income = monthly_incomes[0]
            latest_expenses = monthly_expenses[0]
            # Estimate debt-like obligations as ~40% of total expenses (rent, EMIs, insurance)
            estimated_debt = latest_expenses * 0.4
            dti_ratio = min(estimated_debt / latest_income, 0.6)

        # Emergency Fund Months: Total Historical Delta (up to ref_date) / Avg Monthly Expenses
        delta_result = await self.db.execute(
            text("SELECT SUM(amount) FROM transactions WHERE user_id = :uid AND ts <= :ref_date"),
            {"uid": user_id, "ref_date": ref_date}
        )
        total_delta = float(delta_result.scalar() or 0)
        
        if avg_monthly_expenses > 0:
            ef_months = max(0, total_delta / avg_monthly_expenses)
        else:
            ef_months = 0 if total_delta <= 0 else 12.0

        return {
            "savings_rate": round(float(savings_rate), 4),
            "dti_ratio": round(float(dti_ratio), 4),
            "spending_volatility": round(float(cv), 4),
            "emergency_fund_months": round(float(ef_months), 2),
        }

    async def _get_latest_fhs(self, user_id: str) -> dict:
        cache_key = f"fhs:{user_id}"
        cached = await self.redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            data["data_freshness"] = "fresh"
            return data

        result = await self.db.execute(
            text(
                "SELECT score, computed_at FROM financial_health_scores "
                "WHERE user_id = :uid ORDER BY computed_at DESC LIMIT 1"
            ),
            {"uid": user_id},
        )
        row = result.fetchone()
        if row:
            fhs = {"score": float(row.score), "computed_at": str(row.computed_at), "data_freshness": "fresh"}
            await self.redis.setex(cache_key, 60, json.dumps(fhs))
            return fhs
        return {"score": 0, "computed_at": None, "data_freshness": "stale"}

    async def _get_category_distribution(self, user_id: str) -> list[dict]:
        current_month = datetime.utcnow().strftime("%Y-%m")
        cache_key = f"cat_dist:{user_id}:{current_month}"
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        result = await self.db.execute(
            text(
                "SELECT c.name as category, SUM(ABS(t.amount)) as amount, COUNT(*) as count "
                "FROM transactions t "
                "JOIN transaction_categories tc ON t.id = tc.transaction_id "
                "JOIN categories c ON tc.category_id = c.id "
                "WHERE t.user_id = :uid AND DATE_TRUNC('month', t.ts) = DATE_TRUNC('month', CURRENT_DATE) "
                "GROUP BY c.name ORDER BY amount DESC"
            ),
            {"uid": user_id},
        )
        categories = [
            {"category": row.category, "amount": float(row.amount), "count": row.count}
            for row in result.fetchall()
        ]
        if categories:
            await self.redis.setex(cache_key, 300, json.dumps(categories))
        return categories

    async def _get_recent_transactions(self, user_id: str, limit: int = 10) -> list[dict]:
        result = await self.db.execute(
            text(
                "SELECT t.id, t.amount, t.currency, t.merchant_name, t.raw_description, t.ts, "
                "c.name as category "
                "FROM transactions t "
                "LEFT JOIN transaction_categories tc ON t.id = tc.transaction_id "
                "LEFT JOIN categories c ON tc.category_id = c.id "
                "WHERE t.user_id = :uid ORDER BY t.ts DESC LIMIT :lim"
            ),
            {"uid": user_id, "lim": limit},
        )
        return [
            {
                "id": str(row.id),
                "amount": float(row.amount),
                "currency": row.currency,
                "merchant_name": row.merchant_name,
                "description": row.raw_description,
                "ts": str(row.ts),
                "category": row.category or "Other",
            }
            for row in result.fetchall()
        ]

    async def _get_unread_alert_count(self, user_id: str) -> int:
        result = await self.db.execute(
            text(
                "SELECT COUNT(*) as cnt FROM anomaly_alerts "
                "WHERE user_id = :uid AND acknowledged_at IS NULL"
            ),
            {"uid": user_id},
        )
        return result.scalar() or 0

    async def _get_budget_status(self, user_id: str) -> list[dict]:
        result = await self.db.execute(
            text(
                "SELECT b.category_id, c.name as category, b.limit_amount, "
                "COALESCE(SUM(t.amount), 0) as spent "
                "FROM budgets b "
                "JOIN categories c ON b.category_id = c.id "
                "LEFT JOIN transactions t ON t.user_id = b.user_id "
                "AND DATE_TRUNC('month', t.ts) = b.month "
                "LEFT JOIN transaction_categories tc ON t.id = tc.transaction_id "
                "AND tc.category_id = b.category_id "
                "WHERE b.user_id = :uid AND b.month = DATE_TRUNC('month', CURRENT_DATE) "
                "GROUP BY b.category_id, c.name, b.limit_amount"
            ),
            {"uid": user_id},
        )
        budgets = []
        for row in result.fetchall():
            spent = float(row.spent)
            limit_amt = float(row.limit_amount)
            status = "ok" if spent <= limit_amt * 0.8 else ("warning" if spent <= limit_amt else "over")
            budgets.append({
                "category": row.category,
                "limit": limit_amt,
                "spent": spent,
                "status": status,
            })
        return budgets
