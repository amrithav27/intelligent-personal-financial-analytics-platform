"""Unit tests for ingestion router endpoints — validates adapter-level logic for manual and CSV ingestion."""
import pytest
from adapters.csv_adapter import CSVUploadAdapter
from adapters.manual_adapter import ManualEntryAdapter


class TestManualEntryValidation:
    def test_valid_payload_passes_validation(self):
        adapter = ManualEntryAdapter()
        result = adapter.validate({"amount": 250.0, "description": "Lunch at Cafe"})
        assert result.is_valid is True
        assert result.errors == []

    def test_missing_amount_fails(self):
        adapter = ManualEntryAdapter()
        result = adapter.validate({"description": "Coffee"})
        assert result.is_valid is False
        assert any("amount" in e for e in result.errors)

    def test_missing_description_fails(self):
        adapter = ManualEntryAdapter()
        result = adapter.validate({"amount": 100})
        assert result.is_valid is False
        assert any("description" in e for e in result.errors)

    def test_invalid_amount_type_fails(self):
        adapter = ManualEntryAdapter()
        result = adapter.validate({"amount": "not_a_number", "description": "Test"})
        assert result.is_valid is False
        assert any("amount" in e.lower() for e in result.errors)

    def test_transform_sets_default_currency(self):
        adapter = ManualEntryAdapter()
        txn = adapter.transform({"amount": 500, "description": "ATM withdrawal"})
        assert txn.currency == "INR"

    def test_transform_uses_explicit_date(self):
        adapter = ManualEntryAdapter()
        txn = adapter.transform({"amount": 100, "description": "Test", "date": "2024-03-15T10:00:00"})
        assert txn.ts.year == 2024
        assert txn.ts.month == 3
        assert txn.ts.day == 15

    def test_transform_external_id_starts_with_manual(self):
        adapter = ManualEntryAdapter()
        txn = adapter.transform({"amount": 250, "description": "Manual entry"})
        assert txn.external_id.startswith("manual_")

    def test_transform_includes_merchant_name(self):
        adapter = ManualEntryAdapter()
        txn = adapter.transform({"amount": 350, "description": "Dinner", "merchant_name": "Zomato"})
        assert txn.merchant_name == "Zomato"


class TestCSVIngestionValidation:
    def test_valid_csv_passes_validation(self):
        adapter = CSVUploadAdapter()
        csv = "date,amount,description\n2024-01-15,500,BigBasket Groceries\n"
        result = adapter.validate(csv)
        assert result.is_valid is True

    def test_csv_missing_required_date_column_fails(self):
        adapter = CSVUploadAdapter()
        csv = "amount,description\n500,Coffee\n"
        result = adapter.validate(csv)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_csv_missing_required_amount_column_fails(self):
        adapter = CSVUploadAdapter()
        csv = "date,description\n2024-01-15,Coffee\n"
        result = adapter.validate(csv)
        assert result.is_valid is False

    def test_csv_parses_amount_with_rupee_symbol(self):
        adapter = CSVUploadAdapter()
        csv = "date,amount,description\n2024-01-15,₹1500.50,Rent\n"
        txns = adapter.transform(csv)
        assert len(txns) == 1
        assert float(txns[0].amount) == 1500.50

    def test_csv_parses_multiple_rows(self):
        adapter = CSVUploadAdapter()
        csv = (
            "date,amount,description\n"
            "2024-01-10,200,Grocery\n"
            "2024-01-11,150,Coffee\n"
            "2024-01-12,3000,Electricity Bill\n"
        )
        txns = adapter.transform(csv)
        assert len(txns) == 3

    def test_csv_amount_with_commas(self):
        adapter = CSVUploadAdapter()
        csv = "date,amount,description\n2024-02-01,\"10,000\",Laptop EMI\n"
        # comma-stripped amount should parse correctly
        txns = adapter.transform(csv)
        assert float(txns[0].amount) == 10000.0

    def test_csv_each_row_has_unique_external_id(self):
        adapter = CSVUploadAdapter()
        csv = (
            "date,amount,description\n"
            "2024-03-01,100,A\n"
            "2024-03-02,200,B\n"
        )
        txns = adapter.transform(csv)
        assert txns[0].external_id != txns[1].external_id

    def test_csv_default_currency_is_inr(self):
        adapter = CSVUploadAdapter()
        csv = "date,amount,description\n2024-01-15,400,Petrol\n"
        txns = adapter.transform(csv)
        assert txns[0].currency == "INR"
