"""Ingestion Router — endpoints for CSV upload, manual entry, bank API, and transaction listing."""

import logging
import io
import csv
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from schemas import (
    ManualTransactionRequest,
    BankAPITransactionRequest,
    IngestionResponse,
    TransactionListResponse,
    TransactionResponse,
)
from service import IngestionService
from models import Transaction
from publishers.base import INotificationPublisher

logger = logging.getLogger(__name__)
router = APIRouter(redirect_slashes=False)


async def get_db():
    """Dependency — injected by main.py."""
    raise NotImplementedError("get_db must be overridden at app startup")


async def get_publisher() -> INotificationPublisher:
    """Dependency — injected by main.py."""
    raise NotImplementedError("get_publisher must be overridden at app startup")


@router.post("/ingest", response_model=IngestionResponse)
async def ingest_csv(
    file: UploadFile = File(...),
    source_type: str = Form(default="csv_v1"),
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
    publisher: INotificationPublisher = Depends(get_publisher),
):
    """Ingest transactions from a CSV file upload."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    content = await file.read()
    csv_text = content.decode("utf-8")

    service = IngestionService(db, publisher)
    try:
        result = await service.ingest(x_user_id, source_type, csv_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return IngestionResponse(**result)


@router.post("/manual", response_model=IngestionResponse)
async def ingest_manual(
    req: ManualTransactionRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
    publisher: INotificationPublisher = Depends(get_publisher),
):
    """Ingest a single manually entered transaction."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    service = IngestionService(db, publisher)
    try:
        result = await service.ingest(x_user_id, "manual_v1", req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return IngestionResponse(**result)


@router.post("/bank-api", response_model=IngestionResponse)
async def ingest_bank_api(
    req: BankAPITransactionRequest,
    source_type: str = Query(default="icici_v1"),
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
    publisher: INotificationPublisher = Depends(get_publisher),
):
    """Ingest a transaction from a bank API."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    service = IngestionService(db, publisher)
    try:
        result = await service.ingest(x_user_id, source_type, req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return IngestionResponse(**result)


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str = Query(None, description="Filter by category name"),
    date_from: str = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: str = Query(None, description="Filter to date (YYYY-MM-DD)"),
    amount_min: float = Query(None, description="Minimum amount"),
    amount_max: float = Query(None, description="Maximum amount"),
    search: str = Query(None, description="Search description or merchant"),
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """List transactions for the authenticated user with pagination and filters."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")
    logger.info(f"LIST_TRANSACTIONS: user_id={x_user_id}")

    from sqlalchemy import text as sa_text

    offset = (page - 1) * page_size

    # Build WHERE clauses
    conditions = ["t.user_id = :user_id"]
    params: dict = {"user_id": x_user_id}

    if category:
        conditions.append("c.name = :category")
        params["category"] = category
    if date_from:
        conditions.append("t.ts >= :date_from::timestamptz")
        params["date_from"] = date_from
    if date_to:
        conditions.append("t.ts <= :date_to::timestamptz + INTERVAL '1 day'")
        params["date_to"] = date_to
    if amount_min is not None:
        conditions.append("ABS(t.amount) >= :amount_min")
        params["amount_min"] = amount_min
    if amount_max is not None:
        conditions.append("ABS(t.amount) <= :amount_max")
        params["amount_max"] = amount_max
    if search:
        conditions.append(
            "(LOWER(t.raw_description) LIKE :search OR LOWER(t.merchant_name) LIKE :search)"
        )
        params["search"] = f"%{search.lower()}%"

    where_clause = " AND ".join(conditions)

    # Count total (with same filters)
    count_sql = (
        "SELECT COUNT(*) FROM transactions t "
        "LEFT JOIN transaction_categories tc ON t.id = tc.transaction_id "
        "LEFT JOIN categories c ON tc.category_id = c.id "
        f"WHERE {where_clause}"
    )
    count_result = await db.execute(sa_text(count_sql), params)
    total = count_result.scalar()

    # Fetch page with category join
    fetch_sql = (
        "SELECT t.id, t.amount, t.currency, t.merchant_name, t.raw_description, "
        "t.mcc_code, t.ts, t.created_at, c.name AS category_name, c.icon AS category_icon "
        "FROM transactions t "
        "LEFT JOIN transaction_categories tc ON t.id = tc.transaction_id "
        "LEFT JOIN categories c ON tc.category_id = c.id "
        f"WHERE {where_clause} "
        "ORDER BY t.ts DESC "
        "OFFSET :offset LIMIT :page_size"
    )
    params["offset"] = offset
    params["page_size"] = page_size

    result = await db.execute(sa_text(fetch_sql), params)
    rows = result.fetchall()

    return TransactionListResponse(
        transactions=[
            TransactionResponse(
                id=str(row.id),
                amount=float(row.amount),
                currency=row.currency,
                merchant_name=row.merchant_name,
                raw_description=row.raw_description,
                mcc_code=row.mcc_code,
                category_name=row.category_name,
                category_icon=row.category_icon,
                ts=row.ts,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/export")
async def export_transactions(
    x_user_id: str = Header(None, alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Export all transactions for the user as CSV."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID not provided")

    from sqlalchemy import text as sa_text

    sql = (
        "SELECT t.ts, t.amount, t.currency, t.merchant_name, t.raw_description, c.name AS category_name "
        "FROM transactions t "
        "LEFT JOIN transaction_categories tc ON t.id = tc.transaction_id "
        "LEFT JOIN categories c ON tc.category_id = c.id "
        "WHERE t.user_id = :user_id "
        "ORDER BY t.ts DESC"
    )
    result = await db.execute(sa_text(sql), {"user_id": x_user_id})
    rows = result.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Amount", "Currency", "Merchant", "Description", "Category"])

    for row in rows:
        writer.writerow([
            row.ts.strftime("%Y-%m-%d %H:%M:%S") if row.ts else "",
            float(row.amount),
            row.currency,
            row.merchant_name or "",
            row.raw_description or "",
            row.category_name or "Uncategorized"
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions_export.csv"}
    )

