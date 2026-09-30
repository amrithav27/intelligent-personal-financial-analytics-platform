"""ClickHouse Async Client — dual-purpose: writes computed analytics AND reads
analytical query results from ClickHouse (OLAP layer).

Architecture note (ADR-002):
    PostgreSQL  → OLTP (transactional source of truth, ACID guarantees)
    ClickHouse  → OLAP (analytical reads — time-series, aggregations, trends)
    Data flows: PG ──(async mirror)──▶ CH    (eventual consistency, 1-2 s lag)
    Read path:  CH ──(OLAP queries)──▶ API   (with PG fallback on CH failure)
"""

import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ClickHouseWriter:
    """
    Unified ClickHouse client for the Analytics Engine.

    WRITE side (fire-and-forget, async):
        write_fhs()               — mirror FHS scores to CH
        write_monthly_category()  — mirror monthly category aggregates
        write_transaction()       — mirror individual transactions for OLAP trends

    READ side (awaited, returns data):
        read_json()               — execute SELECT … FORMAT JSON, return rows
        query_fhs_history()       — FHS score time-series from CH
        query_spending_trends()   — monthly spending trends from CH
        query_monthly_categories()— category distribution for a month from CH
    """

    def __init__(self, clickhouse_url: str, db: str):
        self.url = f"{clickhouse_url}/?database={db}"

    # ── WRITE METHODS (fire-and-forget) ─────────────────────────────────────

    async def write_fhs(self, user_id: str, fhs_data: dict, computed_at=None) -> None:
        """Mirror a computed Financial Health Score row to ClickHouse."""
        ts_value = f"'{computed_at.strftime('%Y-%m-%d %H:%M:%S')}'" if computed_at else "now()"
        query = (
            "INSERT INTO financial_health_scores "
            "(user_id, score, savings_rate, dti_ratio, spending_volatility, computed_at) "
            f"VALUES ('{user_id}', {fhs_data['score']}, {fhs_data.get('savings_rate', 0)}, "
            f"{fhs_data.get('dti_ratio', 0)}, {fhs_data.get('spending_volatility', 0)}, {ts_value})"
        )
        asyncio.create_task(self._execute(query))

    async def write_monthly_category(
        self, user_id: str, category_id: int, category_name: str,
        month: str, total_amount: float, tx_count: int
    ) -> None:
        """Mirror a monthly category spending aggregate to ClickHouse."""
        query = (
            "INSERT INTO monthly_category_spending "
            "(user_id, category_id, category_name, month, total_amount, tx_count) "
            f"VALUES ('{user_id}', {category_id}, '{category_name}', "
            f"'{month}', {total_amount}, {tx_count})"
        )
        asyncio.create_task(self._execute(query))

    async def write_transaction(
        self, txn_id: str, user_id: str, amount: float,
        currency: str, category_id: int, ts: str
    ) -> None:
        """
        Mirror an individual transaction to ClickHouse.
        This populates the `phoenix.transactions` table used for OLAP trend queries,
        removing the need to hit PostgreSQL for heavy analytical aggregations.
        """
        query = (
            "INSERT INTO transactions "
            "(id, user_id, amount, currency, category_id, ts, created_at) "
            f"VALUES ('{txn_id}', '{user_id}', {amount}, '{currency}', "
            f"{category_id}, '{ts}', now())"
        )
        asyncio.create_task(self._execute(query))

    # ── READ METHODS (awaited, return parsed rows) ──────────────────────────

    async def read_json(self, query: str) -> list[dict[str, Any]]:
        """
        Execute a SELECT query against ClickHouse and return parsed rows.
        Appends FORMAT JSON to get structured output from CH HTTP interface.
        """
        full_query = f"{query} FORMAT JSON"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.url, content=full_query)
                resp.raise_for_status()
                data = resp.json()
                return data.get("data", [])
        except Exception as e:
            logger.warning(f"ClickHouse read failed: {e}")
            return []

    async def query_fhs_history(self, user_id: str, limit: int = 12) -> list[dict]:
        """
        OLAP query: Retrieve FHS score time-series from ClickHouse.
        Returns the most recent `limit` scores, ordered newest-first.
        ClickHouse excels here due to columnar storage + partitioning by month.
        """
        query = (
            "SELECT score, savings_rate, dti_ratio, spending_volatility, "
            "formatDateTime(computed_at, '%Y-%m-%d %H:%M:%S') as computed_at "
            "FROM financial_health_scores "
            f"WHERE user_id = '{user_id}' "
            f"ORDER BY computed_at DESC LIMIT {limit}"
        )
        return await self.read_json(query)

    async def query_spending_trends(self, user_id: str, months: int = 6) -> list[dict]:
        """
        OLAP query: Monthly spending aggregation from ClickHouse transactions mirror.
        Aggregates total spending per month — ideal for ClickHouse's columnar engine
        which can scan the amount column without touching other columns.
        """
        query = (
            "SELECT toStartOfMonth(ts) as month, "
            "sum(abs(amount)) as total, "
            "count() as tx_count "
            "FROM transactions "
            f"WHERE user_id = '{user_id}' "
            f"AND ts >= today() - INTERVAL {months} MONTH "
            "GROUP BY month ORDER BY month"
        )
        return await self.read_json(query)

    async def query_monthly_categories(self, user_id: str, month: str) -> list[dict]:
        """
        OLAP query: Category-level spending distribution for a given month.
        Uses the pre-aggregated monthly_category_spending table in ClickHouse.
        """
        query = (
            "SELECT category_name, total_amount, tx_count "
            "FROM monthly_category_spending "
            f"WHERE user_id = '{user_id}' AND month = '{month}' "
            "ORDER BY total_amount DESC"
        )
        return await self.read_json(query)

    # ── INTERNAL ────────────────────────────────────────────────────────────

    async def _execute(self, query: str) -> None:
        """Fire-and-forget write to ClickHouse. Failures are non-fatal."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(self.url, content=query)
        except Exception as e:
            logger.warning(f"ClickHouse write failed (non-fatal): {e}")
