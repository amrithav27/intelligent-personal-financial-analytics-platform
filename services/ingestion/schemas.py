"""Pydantic schemas for the Ingestion Service."""

from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal
from typing import Optional


class ManualTransactionRequest(BaseModel):
    amount: Decimal
    description: str
    currency: str = "INR"
    merchant_name: Optional[str] = None
    mcc_code: Optional[str] = None
    date: Optional[str] = None


class BankAPITransactionRequest(BaseModel):
    transaction_id: str
    amount: Decimal
    description: str
    transaction_date: str
    currency: str = "INR"
    merchant_name: Optional[str] = None
    mcc_code: Optional[str] = None
    branch_code: Optional[str] = None
    reference_number: Optional[str] = None


class IngestionResponse(BaseModel):
    ingested: int
    skipped: int


class TransactionResponse(BaseModel):
    id: str
    amount: float
    currency: str
    merchant_name: Optional[str]
    raw_description: Optional[str]
    mcc_code: Optional[str]
    category_name: Optional[str] = None
    category_icon: Optional[str] = None
    ts: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total: int
    page: int
    page_size: int
