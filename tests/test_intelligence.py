"""Tests for deterministic model-facing market intelligence."""

from types import SimpleNamespace

from btc_cycle_tracker.analytics.intelligence import build_market_intelligence
from btc_cycle_tracker.models import PivotType


def _leg(index: int, change: float, bars: int = 10):
    return SimpleNamespace(percent_change=change, duration_bars=bars)


def _pivot(price: float, pivot_type: PivotType):
    return SimpleNamespace(price=price, pivot_type=pivot_type)


def test_intelligence_detects_rising_structure_and_expansion():
    result = SimpleNamespace(
        legs=[_leg(i, value, 8) for i, value in enumerate([-1, 1, -1, 1, -1, 1, -1, 1, -3, 5, -2, 6])],
        pivots=[
            _pivot(100, PivotType.SWING_HIGH), _pivot(80, PivotType.SWING_LOW),
            _pivot(110, PivotType.SWING_HIGH), _pivot(90, PivotType.SWING_LOW),
        ],
        pattern_insight=SimpleNamespace(
            dominant_bias="bullish", matches_used=20, adaptive_confidence=0.8
        ),
    )

    brief = build_market_intelligence(result)

    assert brief["bias"] == "bullish"
    assert brief["structure"] == "higher_highs_higher_lows"
    assert brief["regime"].startswith("expanding_amplitude")
    assert brief["conflicts"] == []


def test_intelligence_surfaces_pattern_conflict_and_reduces_quality():
    legs = [_leg(i, -2 if i % 2 == 0 else 0.5) for i in range(20)]
    result = SimpleNamespace(
        legs=legs,
        pivots=[],
        pattern_insight=SimpleNamespace(
            dominant_bias="bullish", matches_used=20, adaptive_confidence=0.9
        ),
    )

    brief = build_market_intelligence(result)

    assert brief["bias"] == "bearish"
    assert brief["conflicts"]
    assert "conflict" in brief["quality"]["reasons"][-1]


def test_intelligence_handles_no_legs():
    brief = build_market_intelligence(SimpleNamespace(legs=[]))
    assert brief["quality"]["label"] == "insufficient"
    assert brief["regime"] == "undetermined"


def test_intelligence_does_not_compare_short_history_to_itself():
    result = SimpleNamespace(
        legs=[_leg(i, 2 if i % 2 else -1) for i in range(7)],
        pivots=[],
        pattern_insight=None,
    )
    brief = build_market_intelligence(result)
    assert brief["regime"] == "insufficient_history_amplitude_insufficient_history_duration"
    assert brief["baseline"]["legs"] == 0
