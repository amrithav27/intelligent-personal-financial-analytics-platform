"""FACTORY METHOD — Analytics Processor Factory."""

from processors.fhs_processor import FHSProcessor
from processors.category_aggregator import CategoryAggregator
from processors.trend_analyzer import TrendAnalyzer


class AnalyticsServiceFactory:
    """
    FACTORY METHOD: Creates the correct analytics processor without
    the AnalyticsService orchestrator knowing the concrete types.
    """
    _registry = {
        "fhs": FHSProcessor,
        "category": CategoryAggregator,
        "trend": TrendAnalyzer,
    }

    @classmethod
    def create(cls, processor_type: str):
        if processor_type not in cls._registry:
            raise ValueError(f"Unknown processor type: {processor_type}")
        return cls._registry[processor_type]()

    @classmethod
    def list_processors(cls) -> list[str]:
        return list(cls._registry.keys())
