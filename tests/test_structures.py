"""Tests for deterministic core market-structure discovery."""

from datetime import datetime, timedelta, timezone

from btc_cycle_tracker.analytics.structures import discover_structures
from btc_cycle_tracker.models import OHLCV, PivotPoint, PivotType


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _pivot(index: int, price: float, kind: PivotType) -> PivotPoint:
    return PivotPoint(index=index, timestamp=BASE + timedelta(days=index), price=price,
                      pivot_type=kind, source_candle_index=index, left_bars=2, right_bars=2)


def _data(count: int, close: float) -> list[OHLCV]:
    return [OHLCV(timestamp=BASE + timedelta(days=i), open=close, high=close + 1,
                  low=close - 1, close=close, volume=100) for i in range(count)]


def test_discovers_rising_structure_and_bullish_break():
    pivots = [
        _pivot(1, 100, PivotType.SWING_HIGH), _pivot(2, 80, PivotType.SWING_LOW),
        _pivot(3, 110, PivotType.SWING_HIGH), _pivot(4, 90, PivotType.SWING_LOW),
        _pivot(5, 120, PivotType.SWING_HIGH),
    ]
    found = discover_structures(_data(7, 115), pivots)
    types = {item.structure_type for item in found}
    assert "uptrend_structure" in types
    assert "break_of_structure" in types


def test_discovers_change_of_character_after_falling_highs():
    pivots = [
        _pivot(1, 120, PivotType.SWING_HIGH), _pivot(2, 90, PivotType.SWING_LOW),
        _pivot(3, 110, PivotType.SWING_HIGH), _pivot(4, 80, PivotType.SWING_LOW),
        _pivot(5, 115, PivotType.SWING_HIGH),
    ]
    found = discover_structures(_data(7, 112), pivots)
    change = next(item for item in found if item.structure_type == "change_of_character")
    assert change.direction == "bullish"
    assert change.anchors[-1].price == 115


def test_discovers_range_and_repeated_zones():
    pivots = [
        _pivot(1, 100, PivotType.SWING_HIGH), _pivot(2, 90, PivotType.SWING_LOW),
        _pivot(3, 100.2, PivotType.SWING_HIGH), _pivot(4, 90.1, PivotType.SWING_LOW),
        _pivot(5, 99.9, PivotType.SWING_HIGH), _pivot(6, 89.9, PivotType.SWING_LOW),
    ]
    found = discover_structures(_data(8, 95), pivots, min_move_pct=1.0)
    types = {item.structure_type for item in found}
    assert "range" in types
    assert "support_zone" in types
    assert "resistance_zone" in types


def test_requires_data_and_pivots():
    assert discover_structures([], []) == []
