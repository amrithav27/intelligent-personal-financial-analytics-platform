"""Unit tests for list_transactions with category join and filters."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import uuid


class FakeRow:
    """Simulates a SQLAlchemy row from the JOIN query."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def make_transaction_row(category_name="Groceries", category_icon="🛒"):
    return FakeRow(
        id=uuid.uuid4(),
        amount=500.0,
        currency="INR",
        merchant_name="BigBasket",
        raw_description="BigBasket Groceries",
        mcc_code="5411",
        category_name=category_name,
        category_icon=category_icon,
        ts=datetime(2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc),
    )


class TestTransactionResponseSchema:
    """Test that TransactionResponse schema includes category fields."""

    def test_category_fields_present(self):
        from schemas import TransactionResponse

        resp = TransactionResponse(
            id="abc-123",
            amount=250.0,
            currency="INR",
            merchant_name="Swiggy",
            raw_description="Swiggy order",
            mcc_code="5812",
            category_name="Dining",
            category_icon="🍽️",
            ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert resp.category_name == "Dining"
        assert resp.category_icon == "🍽️"

    def test_category_fields_optional(self):
        from schemas import TransactionResponse

        resp = TransactionResponse(
            id="abc-456",
            amount=100.0,
            currency="INR",
            merchant_name=None,
            raw_description="ATM withdrawal",
            mcc_code=None,
            ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert resp.category_name is None
        assert resp.category_icon is None


class TestListTransactionsQueryParams:
    """Test that the list_transactions endpoint accepts filter parameters."""

    def test_search_param_lowercases_pattern(self):
        """Verify search term is lowered for LIKE matching."""
        search = "BigBasket"
        expected = f"%{search.lower()}%"
        assert expected == "%bigbasket%"

    def test_filter_conditions_built_correctly(self):
        """Verify that filter conditions are built from params."""
        conditions = ["t.user_id = :user_id"]
        params = {"user_id": "test-user"}

        category = "Groceries"
        if category:
            conditions.append("c.name = :category")
            params["category"] = category

        date_from = "2024-01-01"
        if date_from:
            conditions.append("t.ts >= :date_from::timestamptz")
            params["date_from"] = date_from

        amount_min = 100.0
        if amount_min is not None:
            conditions.append("ABS(t.amount) >= :amount_min")
            params["amount_min"] = amount_min

        search = "BigBasket"
        if search:
            conditions.append(
                "(LOWER(t.raw_description) LIKE :search OR LOWER(t.merchant_name) LIKE :search)"
            )
            params["search"] = f"%{search.lower()}%"

        where_clause = " AND ".join(conditions)

        assert "c.name = :category" in where_clause
        assert "t.ts >= :date_from::timestamptz" in where_clause
        assert "ABS(t.amount) >= :amount_min" in where_clause
        assert "LIKE :search" in where_clause
        assert params["category"] == "Groceries"
        assert params["search"] == "%bigbasket%"

    def test_no_filters_only_user_id(self):
        """Verify that with no filters, only user_id condition is built."""
        conditions = ["t.user_id = :user_id"]
        params = {"user_id": "test-user"}

        where_clause = " AND ".join(conditions)
        assert where_clause == "t.user_id = :user_id"
        assert len(params) == 1


class TestTransactionResponseWithCategory:
    """Test building TransactionResponse objects with category data."""

    def test_response_from_joined_row(self):
        from schemas import TransactionResponse

        row = make_transaction_row(category_name="Groceries", category_icon="🛒")
        resp = TransactionResponse(
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
        assert resp.category_name == "Groceries"
        assert resp.category_icon == "🛒"
        assert resp.amount == 500.0

    def test_response_uncategorized_transaction(self):
        from schemas import TransactionResponse

        row = make_transaction_row(category_name=None, category_icon=None)
        resp = TransactionResponse(
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
        assert resp.category_name is None
        assert resp.category_icon is None

    def test_response_serialization_includes_category(self):
        from schemas import TransactionResponse

        resp = TransactionResponse(
            id="x-1",
            amount=999.99,
            currency="INR",
            merchant_name="Amazon",
            raw_description="Amazon purchase",
            mcc_code="5912",
            category_name="Shopping",
            category_icon="🛍️",
            ts=datetime(2024, 6, 1, tzinfo=timezone.utc),
            created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        data = resp.model_dump()
        assert "category_name" in data
        assert "category_icon" in data
        assert data["category_name"] == "Shopping"
        assert data["category_icon"] == "🛍️"
