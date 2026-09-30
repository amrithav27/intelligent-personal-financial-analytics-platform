"""Z-Score Anomaly Detector with Welford's Online Algorithm."""

from dataclasses import dataclass
import math


@dataclass
class WelfordState:
    count: int
    mean: float
    M2: float  # Sum of squared deviations from mean

    @property
    def variance(self) -> float:
        return self.M2 / self.count if self.count > 1 else 0.0

    @property
    def std_dev(self) -> float:
        return math.sqrt(self.variance)

    def update(self, new_value: float) -> "WelfordState":
        """Returns updated state after incorporating new_value."""
        count = self.count + 1
        delta = new_value - self.mean
        mean = self.mean + delta / count
        delta2 = new_value - mean
        M2 = self.M2 + delta * delta2
        return WelfordState(count=count, mean=mean, M2=M2)


class ZScoreDetector:
    """
    Per-user per-category Z-score anomaly detection.
    Uses Welford's online algorithm for O(1) incremental updates.
    """

    THRESHOLD = 2.5
    MIN_TRANSACTIONS = 10

    def __init__(self):
        self.THRESHOLD = float(
            __import__("os").getenv("ANOMALY_Z_THRESHOLD", "2.5")
        )
        self.MIN_TRANSACTIONS = int(
            __import__("os").getenv("ANOMALY_MIN_TRANSACTIONS", "10")
        )

    def compute_z_score(self, amount: float, state: WelfordState) -> float | None:
        """Returns Z-score or None if insufficient baseline."""
        if state.count < self.MIN_TRANSACTIONS:
            return None  # Bootstrap suppression
        if state.std_dev == 0:
            return None  # All transactions identical — no variance to detect
        return (amount - state.mean) / state.std_dev

    def is_anomalous(self, z_score: float | None) -> bool:
        return z_score is not None and abs(z_score) > self.THRESHOLD

    def build_alert_message(
        self, z_score: float, category_name: str, amount: float, mean: float
    ) -> str:
        ratio = abs(amount / mean) if mean != 0 else 0
        direction = "above" if amount > mean else "below"
        return (
            f"This transaction ({amount:.2f}) is {ratio:.1f}x your typical "
            f"{category_name} spend ({mean:.2f}). "
            f"Z-score: {z_score:.2f} ({direction} your 30-day baseline)."
        )
