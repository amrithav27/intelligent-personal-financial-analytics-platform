"""Unit tests for the Adapter pattern — CSV, ICICI, and Manual adapters."""
import pytest
from adapters.csv_adapter import CSVUploadAdapter
from adapters.icici_adapter import ICICIBankAdapter
from adapters.manual_adapter import ManualEntryAdapter
from adapters.registry import AdapterRegistry


class TestCSVAdapter:
    def test_validate_valid_csv(self):
        adapter = CSVUploadAdapter()
        csv = "date,amount,description\n2024-01-15,500,Groceries\n"
        result = adapter.validate(csv)
        assert result.is_valid is True

    def test_validate_missing_columns(self):
        adapter = CSVUploadAdapter()
        csv = "name,price\nApple,100\n"
        result = adapter.validate(csv)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_transform(self):
        adapter = CSVUploadAdapter()
        csv = "date,amount,description\n2024-01-15,500.50,Groceries at BigBasket\n"
        txns = adapter.transform(csv)
        assert len(txns) == 1
        assert float(txns[0].amount) == 500.50
        assert txns[0].currency == "INR"


class TestICICIAdapter:
    def test_validate_valid(self):
        adapter = ICICIBankAdapter()
        data = {
            "transaction_id": "T123",
            "amount": 1500,
            "description": "UPI Payment",
            "transaction_date": "2024-01-15T10:30:00",
        }
        result = adapter.validate(data)
        assert result.is_valid is True

    def test_validate_invalid(self):
        adapter = ICICIBankAdapter()
        result = adapter.validate({"amount": 100})
        assert result.is_valid is False

    def test_transform(self):
        adapter = ICICIBankAdapter()
        data = {
            "transaction_id": "T123",
            "amount": 1500,
            "description": "UPI Payment",
            "transaction_date": "2024-01-15T10:30:00",
            "currency": "INR",
        }
        txn = adapter.transform(data)
        assert txn.external_id == "icici_T123"
        assert float(txn.amount) == 1500


class TestManualAdapter:
    def test_validate_valid(self):
        adapter = ManualEntryAdapter()
        result = adapter.validate({"amount": 100, "description": "Coffee"})
        assert result.is_valid is True

    def test_validate_missing_amount(self):
        adapter = ManualEntryAdapter()
        result = adapter.validate({"description": "Coffee"})
        assert result.is_valid is False


class TestAdapterRegistry:
    def test_registered_adapters(self):
        adapters = AdapterRegistry.list_adapters()
        assert "csv_v1" in adapters
        assert "icici_v1" in adapters
        assert "manual_v1" in adapters

    def test_get_adapter(self):
        adapter = AdapterRegistry.get("csv_v1")
        assert isinstance(adapter, CSVUploadAdapter)

    def test_get_unknown_adapter(self):
        with pytest.raises(ValueError):
            AdapterRegistry.get("unknown_adapter")
