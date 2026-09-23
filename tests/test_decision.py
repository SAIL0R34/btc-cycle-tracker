"""Tests for the decision engine scorecard and walk-forward replay."""

import math
from datetime import datetime, timedelta

from btc_cycle_tracker.analytics.decision import (
    DecisionInputs,
    action_for_score,
    run_decision_walk_forward,
    score_decision,
)
from btc_cycle_tracker.models import OHLCV, Config
from btc_cycle_tracker.pivots.confirmation import confirm_pivots
from btc_cycle_tracker.pivots.zigzag import ZigZagDetector
from btc_cycle_tracker.analytics.legs import LegBuilder
from btc_cycle_tracker.analytics.stats import calculate_summary_stats
from btc_cycle_tracker.analytics.structures import discover_structures


def _series(direction: float, bars: int = 900) -> list[OHLCV]:
    """Synthetic trending series with regular 2.2-amplitude swings."""
    start = datetime(2026, 9, 23, 12, 0)
    out = []
    for i in range(bars):
        p = 100 + i * 0.03 * direction + math.sin(i / 22) * 2.2
        out.append(
            OHLCV(
                timestamp=start + timedelta(hours=i),
                open=p, high=p + 0.9, low=p - 0.9, close=p, volume=10,
            )
        )
    return out


def _inputs_for(data: list[OHLCV], config: Config) -> DecisionInputs:
    detector = ZigZagDetector(
        left_bars=config.left_bars, right_bars=config.right_bars,
        min_move_pct=config.min_move_pct, use_atr_filter=False,
    )
    pivots = confirm_pivots(detector.detect_pivots(data, config), data, config)
    legs = LegBuilder.build_legs_from_pivots(pivots, data)
    structures = discover_structures(data, pivots, config.min_move_pct)
    return DecisionInputs(
        pivots=pivots,
        legs=legs,
        summary=calculate_summary_stats(legs, data),
        structures=structures,
        forming_leg=LegBuilder.build_forming_leg(pivots, legs, data),
    )


def test_uptrend_scores_invest_side():
    config = Config(timeframe="1h", use_atr_filter=False)
    inputs = _inputs_for(_series(1.0), config)
    brief = score_decision(inputs)

    by_source = {c.source: c for c in brief.contributions}
    assert by_source["structure_trend"].stance == "invest"
    assert by_source["regime_momentum"].score > 0
    assert brief.composite_score > 0
    # Every contribution carries its weight — the scorecard is auditable
    total_weight = sum(c.weight for c in brief.contributions)
    assert total_weight == 100


def test_downtrend_scores_divest_side():
    config = Config(timeframe="1h", use_atr_filter=False)
    inputs = _inputs_for(_series(-1.0), config)
    brief = score_decision(inputs)

    by_source = {c.source: c for c in brief.contributions}
    assert by_source["structure_trend"].stance == "divest"
    assert brief.composite_score < 0
    assert brief.action in {"divest", "strong_divest", "hold"}  # quality gate may cap


def test_pattern_evidence_needs_validated_edge():
    config = Config(timeframe="1h", use_atr_filter=False)
    inputs = _inputs_for(_series(1.0), config)
    inputs.pattern_bias = "bullish"
    inputs.pattern_confidence = 0.9
    inputs.pattern_horizon_edge = 0.0  # no edge over the naive null
    brief = score_decision(inputs)
    by_source = {c.source: c for c in brief.contributions}
    assert by_source["pattern_evidence"].score == 0  # unvalidated bias counts for nothing

    inputs.pattern_horizon_edge = 0.15  # full edge
    brief = score_decision(inputs)
    by_source = {c.source: c for c in brief.contributions}
    assert by_source["pattern_evidence"].score > 0


def test_low_quality_caps_action():
    assert action_for_score(80, quality="high") == "strong_invest"
    assert action_for_score(80, quality="low") == "invest"
    assert action_for_score(20, quality="low") == "hold"
    assert action_for_score(-80, quality="low") == "divest"
    assert action_for_score(25, quality="high") == "invest"


def test_moon_excluded_from_decision():
    config = Config(timeframe="1h", use_atr_filter=False)
    brief = score_decision(_inputs_for(_series(1.0), config))
    sources = {c.source for c in brief.contributions}
    assert "moon_phase" not in sources
    assert any("moon" in e for e in brief.excluded)


def test_walk_forward_no_lookahead_shape():
    config = Config(timeframe="1h", use_atr_filter=False, decision_walk_forward_checkpoints=6)
    data = _series(1.0, bars=600)
    wf = run_decision_walk_forward(data, config)

    assert wf is not None
    assert len(wf.checkpoints) <= 6
    # Timestamps strictly ascending and within the data window
    stamps = [cp.timestamp for cp in wf.checkpoints]
    assert stamps == sorted(stamps)
    assert stamps[-1] < data[-1].timestamp
    # Every checkpoint has a realised forward return over the horizon
    assert all(cp.forward_return_pct is not None for cp in wf.checkpoints)
    # Band stats only cover actions that actually occurred
    occurred = {cp.action for cp in wf.checkpoints}
    assert {s.action for s in wf.band_stats} <= occurred


def test_walk_forward_disabled_with_zero_checkpoints():
    config = Config(timeframe="1h", use_atr_filter=False, decision_walk_forward_checkpoints=0)
    assert run_decision_walk_forward(_series(1.0, 600), config) is None


def test_optional_modules_default_on_for_visibility():
    config = Config()
    assert config.enable_moon_phase_analysis is True
    assert config.enable_gold_correlation_analysis is True
    assert config.enable_nasdaq_correlation_analysis is True
    assert config.enable_decision_engine is True
