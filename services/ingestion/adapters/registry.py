"""Adapter Registry — maps source_type strings to ITransactionAdapter instances."""

from adapters.base import ITransactionAdapter
from adapters.csv_adapter import CSVUploadAdapter
from adapters.manual_adapter import ManualEntryAdapter
from adapters.icici_adapter import ICICIBankAdapter


class AdapterRegistry:
    """
    Maps source_type strings to ITransactionAdapter instances.
    To add a new source: implement ITransactionAdapter, add one line here.
    """
    _adapters: dict[str, ITransactionAdapter] = {}

    @classmethod
    def register(cls, adapter: ITransactionAdapter) -> None:
        cls._adapters[adapter.adapter_id()] = adapter

    @classmethod
    def get(cls, adapter_id: str) -> ITransactionAdapter:
        if adapter_id not in cls._adapters:
            raise ValueError(f"No adapter registered for '{adapter_id}'")
        return cls._adapters[adapter_id]

    @classmethod
    def list_adapters(cls) -> list[str]:
        return list(cls._adapters.keys())


# Registration — the only place new adapters are wired in
AdapterRegistry.register(CSVUploadAdapter())
AdapterRegistry.register(ManualEntryAdapter())
AdapterRegistry.register(ICICIBankAdapter())
