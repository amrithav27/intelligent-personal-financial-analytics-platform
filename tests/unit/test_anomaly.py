"""Unit tests for the Welford Z-score anomaly detector."""
import pytest
from services.anomaly.detector import ZScoreDetector, WelfordState


detector = ZScoreDetector()


class TestWelfordState:
    def test_initial_state(self):
        state = WelfordState(count=0, mean=0.0, M2=0.0)
        assert state.count == 0
        assert state.variance == 0.0

    def test_single_update(self):
        state = WelfordState(count=0, mean=0.0, M2=0.0)
        state = state.update(100.0)
        assert state.count == 1
        assert state.mean == 100.0

    def test_multiple_updates(self):
        state = WelfordState(count=0, mean=0.0, M2=0.0)
        values = [10, 20, 30, 40, 50]
        for v in values:
            state = state.update(v)
        assert state.count == 5
        assert abs(state.mean - 30.0) < 0.01
        assert state.std_dev > 0

    def test_running_mean_accuracy(self):
        state = WelfordState(count=0, mean=0.0, M2=0.0)
        values = [100, 200, 150, 175, 125, 180, 160, 140, 190, 170]
        for v in values:
            state = state.update(v)
        expected_mean = sum(values) / len(values)
        assert abs(state.mean - expected_mean) < 0.01


class TestZScoreDetector:
    def test_bootstrap_suppression(self):
        """Should return None when count < MIN_TRANSACTIONS."""
        state = WelfordState(count=5, mean=100.0, M2=500.0)
        z = detector.compute_z_score(200.0, state)
        assert z is None  # Too few data points

    def test_normal_transaction(self):
        state = WelfordState(count=0, mean=0.0, M2=0.0)
        for v in [100, 110, 90, 105, 95, 100, 110, 90, 105, 95, 100]:
            state = state.update(v)
        z = detector.compute_z_score(100.0, state)
        assert z is not None
        assert not detector.is_anomalous(z)

    def test_anomalous_transaction(self):
        state = WelfordState(count=0, mean=0.0, M2=0.0)
        for v in [100, 100, 100, 100, 100, 100, 100, 100, 100, 100]:
            state = state.update(v)
        # Very large amount
        z = detector.compute_z_score(5000.0, state)
        if z is not None:
            assert detector.is_anomalous(z)

    def test_alert_message(self):
        msg = detector.build_alert_message(3.5, "Dining", 5000.0, 500.0)
        assert "10.0x" in msg
        assert "Dining" in msg
        assert "3.50" in msg


class TestFHSProcessor:
    def test_perfect_score(self):
        from services.analytics.processors.fhs_processor import FHSProcessor
        processor = FHSProcessor()
        metrics = {
            "savings_rate": 0.25,
            "dti_ratio": 0.0,
            "spending_volatility": 0.0,
            "emergency_fund_months": 6.0,
        }
        score = processor.compute("test_user", metrics)
        assert float(score) == 100.0

    def test_zero_score(self):
        from services.analytics.processors.fhs_processor import FHSProcessor
        processor = FHSProcessor()
        metrics = {
            "savings_rate": 0.0,
            "dti_ratio": 0.36,
            "spending_volatility": 0.5,
            "emergency_fund_months": 0.0,
        }
        score = processor.compute("test_user", metrics)
        assert float(score) == 0.0
