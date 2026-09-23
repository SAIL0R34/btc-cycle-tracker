"""Tests for pattern-recognition analytics."""

import json
from datetime import datetime, timedelta

import pytest

from btc_cycle_tracker.analytics.patterns import (
    PatternRecognitionEngine,
    build_pattern_signature,
)
from btc_cycle_tracker.models import Config, SwingLeg


def _make_leg(
    leg_id: int,
    direction: str,
    start_price: float,
    percent_change: float,
    duration_bars: int,
) -> SwingLeg:
    start = datetime(2026, 1, 1) + timedelta(hours=leg_id)
    end = start + timedelta(minutes=duration_bars * 5)
    end_price = start_price * (1 + (percent_change / 100))
    return SwingLeg(
        leg_id=leg_id,
        start_pivot_id=leg_id,
        end_pivot_id=leg_id + 1,
        direction=direction,
        start_timestamp=start,
        end_timestamp=end,
        start_price=start_price,
        end_price=end_price,
        absolute_change=abs(end_price - start_price),
        percent_change=percent_change,
        duration_seconds=duration_bars * 300,
        duration_minutes=duration_bars * 5,
        duration_bars=duration_bars,
    )


def test_build_pattern_signature():
    legs = [
        _make_leg(1, "up", 100, 2.5, 6),
        _make_leg(2, "down", 102.5, -1.8, 10),
        _make_leg(3, "up", 100.6, 4.2, 18),
    ]

    signature = build_pattern_signature(legs)

    # v2 signatures are versioned and self-normalising (bucket edges derive
    # from the run's own distribution — short series fall back to defaults).
    assert signature.startswith("v2:UDU|")
    assert signature.count("|") == 2


def test_pattern_engine_generates_insight_and_learning(tmp_path):
    config = Config(
        output_dir=str(tmp_path),
        pattern_length=3,
        pattern_forecast_horizon=2,
        pattern_max_matches=5,
    )
    engine = PatternRecognitionEngine(config, str(tmp_path))

    legs = [
        _make_leg(1, "up", 100, 2.0, 8),
        _make_leg(2, "down", 102, -1.5, 10),
        _make_leg(3, "up", 100.5, 3.2, 12),
        _make_leg(4, "up", 103.7, 2.4, 9),
        _make_leg(5, "down", 106.2, -1.2, 11),
        _make_leg(6, "up", 104.9, 3.5, 13),
        _make_leg(7, "up", 108.6, 2.1, 8),
        _make_leg(8, "down", 110.9, -1.6, 10),
        _make_leg(9, "up", 109.1, 3.4, 12),
        _make_leg(10, "up", 112.8, 1.9, 7),
        _make_leg(11, "down", 114.9, -1.4, 9),
        _make_leg(12, "up", 113.3, 3.1, 11),
    ]

    insight, learning, backtests = engine.analyze(legs, "BTC-USD", "5m")

    assert insight is not None
    assert insight.matches_used > 0
    assert insight.dominant_bias in {"bullish", "bearish", "balanced"}
    assert learning is not None
    assert learning.total_backtests > 0
    assert backtests
    assert (tmp_path / "pattern_memory.json").exists()


def test_learning_summary_reports_baselines_and_error(tmp_path):
    config = Config(
        output_dir=str(tmp_path),
        pattern_length=3,
        pattern_forecast_horizon=2,
        pattern_max_matches=5,
    )
    engine = PatternRecognitionEngine(config, str(tmp_path))

    legs = [
        _make_leg(1, "up", 100, 2.0, 8),
        _make_leg(2, "down", 102, -1.5, 10),
        _make_leg(3, "up", 100.5, 3.2, 12),
        _make_leg(4, "up", 103.7, 2.4, 9),
        _make_leg(5, "down", 106.2, -1.2, 11),
        _make_leg(6, "up", 104.9, 3.5, 13),
        _make_leg(7, "up", 108.6, 2.1, 8),
        _make_leg(8, "down", 110.9, -1.6, 10),
        _make_leg(9, "up", 109.1, 3.4, 12),
        _make_leg(10, "up", 112.8, 1.9, 7),
        _make_leg(11, "down", 114.9, -1.4, 9),
        _make_leg(12, "up", 113.3, 3.1, 11),
    ]

    _, learning, _ = engine.analyze(legs, "BTC-USD", "5m")

    assert learning is not None
    # Naive baselines are reported so accuracy can be read against a null
    assert 0.0 <= learning.baseline_reversion_hit_rate <= 1.0
    assert 0.0 <= learning.baseline_majority_hit_rate <= 1.0
    # The reported edge is exactly the direction hit rate over the best null
    best_baseline = max(learning.baseline_reversion_hit_rate, learning.baseline_majority_hit_rate)
    assert learning.direction_edge_vs_baseline == pytest.approx(
        learning.direction_hit_rate - best_baseline, abs=1e-9
    )
    assert learning.mean_abs_error_next_change_pct is not None
    assert learning.mean_abs_error_next_change_pct >= 0.0


def test_memory_deduplicates_replayed_windows(tmp_path):
    """Re-running the same leg series must not double-count outcomes."""
    config = Config(
        output_dir=str(tmp_path),
        pattern_length=3,
        pattern_forecast_horizon=2,
        pattern_max_matches=5,
    )
    engine = PatternRecognitionEngine(config, str(tmp_path))

    legs = [
        _make_leg(1, "up", 100, 2.0, 8),
        _make_leg(2, "down", 102, -1.5, 10),
        _make_leg(3, "up", 100.5, 3.2, 12),
        _make_leg(4, "up", 103.7, 2.4, 9),
        _make_leg(5, "down", 106.2, -1.2, 11),
        _make_leg(6, "up", 104.9, 3.5, 13),
        _make_leg(7, "up", 108.6, 2.1, 8),
        _make_leg(8, "down", 110.9, -1.6, 10),
        _make_leg(9, "up", 109.1, 3.4, 12),
        _make_leg(10, "up", 112.8, 1.9, 7),
        _make_leg(11, "down", 114.9, -1.4, 9),
        _make_leg(12, "up", 113.3, 3.1, 11),
    ]

    engine.analyze(legs, "BTC-USD", "5m")
    first_totals = {
        sig: data["total"] for sig, data in json.loads((tmp_path / "pattern_memory.json").read_text()).items()
    }

    engine.analyze(legs, "BTC-USD", "5m")
    second_totals = {
        sig: data["total"] for sig, data in json.loads((tmp_path / "pattern_memory.json").read_text()).items()
    }

    assert first_totals == second_totals, "identical replayed windows must not inflate memory"
