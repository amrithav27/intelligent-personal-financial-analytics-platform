"""Recommendation Router — budget recommendations endpoint with full spending + override enrichment."""

import logging
from datetime import datetime, date as date_type

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from engine import RecommendationEngine

logger = logging.getLogger(__name__)
router = APIRouter()
engine = RecommendationEngine()


async def get_db():
    raise NotImplementedError("get_db must be overridden at app startup")


def _alert_level(pct: float) -> str:
    if pct >= 100:
        return "over"
    if pct >= 80:
        return "warning"
    return "ok"


def _merge_recommendations_by_category(recommendations: list[dict]) -> list[dict]:
    merged: dict[int, dict] = {}
    for rec in recommendations:
        category_id = rec.get("category_id")
        if category_id is None:
            continue

        if category_id not in merged:
            merged[category_id] = {**rec}
            continue

        existing = merged[category_id]
        existing["recommended_amount"] = (
            float(existing.get("recommended_amount", 0) or 0)
            + float(rec.get("recommended_amount", 0) or 0)
        )

    return list(merged.values())


@router.get("/budget")
async def get_budget_recommendations(
    month: str = Query(None, description="YYYY-MM format, defaults to current month"),
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Get personalized budget recommendations enriched with actual spending and saved overrides."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    if not month:
        month = datetime.utcnow().strftime("%Y-%m")

    try:
        month_date = datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM format")

    month_start_dt: date_type = month_date.date().replace(day=1)
    if month_date.month == 12:
        month_end_dt: date_type = date_type(month_date.year + 1, 1, 1)
    else:
        month_end_dt: date_type = date_type(month_date.year, month_date.month + 1, 1)

    # month_start_dt is a datetime.date — must be used (not a string) for asyncpg queries

    # ── 1. Count months of history ─────────────────────────────────────────────
    try:
        result = await db.execute(
            text(
                "SELECT COUNT(DISTINCT DATE_TRUNC('month', ts)) as months "
                "FROM transactions WHERE user_id = :uid"
            ),
            {"uid": x_user_id},
        )
        months_of_history = result.scalar() or 0
    except Exception as e:
        logger.error(f"Error counting months of history: {e}")
        months_of_history = 0

    # ── 2. Load full spending history (all months) for strategy computation ────
    # Only expenditure (amount < 0) is considered spending; income (amount > 0) handled separately
    try:
        result = await db.execute(
            text(
                "SELECT tc.category_id, c.name as category_name, "
                "DATE_TRUNC('month', t.ts) as month, SUM(t.amount) as total "
                "FROM transactions t "
                "JOIN transaction_categories tc ON t.id = tc.transaction_id "
                "JOIN categories c ON tc.category_id = c.id "
                "WHERE t.user_id = :uid AND t.amount < 0 "
                "GROUP BY tc.category_id, c.name, DATE_TRUNC('month', t.ts) "
                "ORDER BY month DESC"
            ),
            {"uid": x_user_id},
        )
        spending_history = [
            {
                "category_id": row.category_id,
                "category_name": row.category_name,
                "month": str(row.month),
                "total": abs(float(row.total)),  # normalize: treat all spending as positive magnitude
            }
            for row in result.fetchall()
        ]
    except Exception as e:
        logger.error(f"Error loading spending history: {e}")
        spending_history = []

    # ── 2b. Load full income history (all positive transactions) ───────────────
    try:
        result = await db.execute(
            text(
                "SELECT DATE_TRUNC('month', ts) as month, SUM(amount) as income "
                "FROM transactions "
                "WHERE user_id = :uid AND amount > 0 "
                "GROUP BY DATE_TRUNC('month', ts)"
            ),
            {"uid": x_user_id},
        )
        past_income = 0.0
        current_month_income = 0.0
        
        target_month_str = str(month_start_dt)
        for row in result.fetchall():
            row_month_str = str(row.month).split(" ")[0]
            if row_month_str == target_month_str:
                current_month_income += float(row.income)
            else:
                past_income += float(row.income)
                
    except Exception as e:
        logger.error(f"Error loading income history: {e}")
        past_income = 0.0
        current_month_income = 0.0

    # If no spending history at all, return empty recommendations gracefully
    if not spending_history and months_of_history == 0:
        return {
            "month": month,
            "strategy_used": "proportional_income",
            "months_of_history": 0,
            "current_month_income": round(current_month_income, 2),
            "recommendations": [],
        }

    # ── 3. Current-month actual spending per category ──────────────────────────
    # We only count spending (outflow), which are negative amounts.
    # We use LEFT JOIN as categorization might be pending/failed.
    try:
        result = await db.execute(
            text(
                "SELECT COALESCE(tc.category_id, 0) as category_id, SUM(ABS(t.amount)) as spent "
                "FROM transactions t "
                "LEFT JOIN transaction_categories tc ON t.id = tc.transaction_id "
                "WHERE t.user_id = :uid "
                "  AND t.amount < 0 "
                "  AND t.ts >= :month_start "
                "  AND t.ts < :month_end "
                "GROUP BY COALESCE(tc.category_id, 0)"
            ),
            {"uid": x_user_id, "month_start": month_start_dt, "month_end": month_end_dt},
        )
        actual_spending: dict[int, float] = {
            int(row.category_id): float(row.spent) for row in result.fetchall()
        }
    except Exception as e:
        logger.error(f"Error loading current spending: {e}")
        actual_spending = {}

    # ── 4. Saved budget overrides from budgets table ───────────────────────────
    try:
        result = await db.execute(
            text(
                "SELECT category_id, limit_amount, recommended_amount "
                "FROM budgets "
                "WHERE user_id = :uid AND month = :month_start"
            ),
            {"uid": x_user_id, "month_start": month_start_dt},
        )
        saved_overrides: dict[int, dict] = {
            row.category_id: {
                "limit_amount": float(row.limit_amount),
                "recommended_amount": float(row.recommended_amount),
            }
            for row in result.fetchall()
        }
    except Exception as e:
        logger.error(f"Error loading saved overrides: {e}")
        saved_overrides = {}

    try:
        strategy = engine.get_strategy(months_of_history)
        raw_recommendations = await strategy.compute_budget(
            x_user_id, month, spending_history,
            past_income=past_income,
            current_income=current_month_income
        )
    except Exception as e:
        logger.error(f"Error computing budget strategy: {e}")
        raw_recommendations = []

    if not raw_recommendations:
        return {
            "month": month,
            "strategy_used": "proportional_income",
            "months_of_history": months_of_history,
            "current_month_income": round(current_month_income, 2),
            "recommendations": [],
        }

    raw_recommendations = _merge_recommendations_by_category(raw_recommendations)

    # ── 6. Merge: enrich each recommendation with spending + override data ─────
    enriched = []
    for rec in raw_recommendations:
        try:
            cat_id = rec.get("category_id")
            if cat_id is None:
                continue
            recommended = float(rec.get("recommended_amount", 0) or 0)
            if recommended <= 0:
                recommended = 1.0  # guard against 0-limit divide

            override = saved_overrides.get(cat_id)
            current_limit = float(override["limit_amount"]) if override else None
            effective_limit = current_limit if current_limit is not None else recommended

            spent = float(actual_spending.get(cat_id, 0.0))
            pct = round((spent / effective_limit * 100), 1) if effective_limit > 0 else 0.0

            enriched.append({
                **rec,
                "recommended_amount": round(recommended, 2),
                "current_limit": round(current_limit, 2) if current_limit is not None else None,
                "effective_limit": round(effective_limit, 2),
                "current_spending": round(spent, 2),
                "pct_used": pct,
                "alert_level": _alert_level(pct),
            })
        except Exception as e:
            logger.warning(f"Skipping recommendation for category {rec}: {e}")
            continue

    # ── 7. Handle Uncategorized (Other) spending ──────────────────────────────
    other_spent = actual_spending.get(0, 0.0)
    if other_spent > 0:
        pct = 0.0  # No limit for 'Other' usually
        enriched.append({
            "category_id": 0,
            "category_name": "Uncategorized / Other",
            "recommended_amount": 0.0,
            "current_limit": None,
            "effective_limit": 0.0,
            "current_spending": round(other_spent, 2),
            "pct_used": 0.0,
            "alert_level": "ok",
            "strategy": "none",
        })

    # Sort: over-budget first, then by pct_used descending
    enriched.sort(key=lambda x: x.get("pct_used", 0), reverse=True)

    return {
        "month": month,
        "strategy_used": "proportional_income",
        "months_of_history": months_of_history,
        "current_month_income": round(current_month_income, 2),
        "recommendations": enriched,
    }


@router.post("/budget/{category_id}/override")
async def override_budget(
    category_id: int,
    limit_amount: float = Query(..., gt=0, description="New budget limit in INR"),
    month: str = Query(None, description="YYYY-MM format, defaults to current month"),
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Allow user to set or update a budget limit for a category in a given month."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    # category_id=0 is a virtual "Uncategorized" bucket — it has no FK in the categories table
    if category_id <= 0:
        raise HTTPException(status_code=400, detail="Cannot set a limit on Uncategorized transactions. Categorize them first.")

    if not month:
        month = datetime.utcnow().strftime("%Y-%m")

    try:
        month_date = datetime.strptime(month, "%Y-%m")
        month_start_dt: date_type = month_date.date().replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM format")

    # Preserve existing recommended_amount if already saved
    result = await db.execute(
        text(
            "SELECT recommended_amount FROM budgets "
            "WHERE user_id = :uid AND category_id = :cid AND month = :month"
        ),
        {"uid": x_user_id, "cid": category_id, "month": month_start_dt},
    )
    existing = result.fetchone()
    recommended_amount = float(existing.recommended_amount) if existing else limit_amount

    await db.execute(
        text(
            "INSERT INTO budgets (user_id, category_id, month, recommended_amount, limit_amount) "
            "VALUES (:uid, :cid, :month, :rec, :limit) "
            "ON CONFLICT (user_id, category_id, month) "
            "DO UPDATE SET limit_amount = :limit"
        ),
        {
            "uid": x_user_id,
            "cid": category_id,
            "month": month_start_dt,
            "rec": recommended_amount,
            "limit": limit_amount,
        },
    )
    await db.commit()
    return {"status": "ok", "category_id": category_id, "limit_amount": limit_amount, "month": month}
