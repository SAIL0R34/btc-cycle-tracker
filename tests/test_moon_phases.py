"""Tests for moon-phase correlation analytics."""

from datetime import datetime, timedelta

from btc_cycle_tracker.analytics.moon_phases import (
    analyze_moon_phase_correlation,
    generate_major_moon_phase_events,
)
from btc_cycle_tracker.models import Config, OHLCV, PivotPoint, PivotType, SwingLeg


def _make_candle(timestamp: datetime, price: float) -> OHLCV:
    return OHLCV(
        timestamp=timestamp,
        open=price,
        high=price + 2,
        low=price - 2,
        close=price + 1,
        volume=1000,
    )


def _make_leg(
    leg_id: int,
    start: datetime,
    hours: int,
    start_price: float,
    end_price: float,
) -> SwingLeg:
    direction = "up" if end_price > start_price else "down"
    pct_change = ((end_price - start_price) / start_price) * 100
    return SwingLeg(
        leg_id=leg_id,
        start_pivot_id=leg_id,
        end_pivot_id=leg_id + 1,
        direction=direction,
        start_timestamp=start,
        end_timestamp=start + timedelta(hours=hours),
        start_price=start_price,
        end_price=end_price,
        absolute_change=abs(end_price - start_price),
        percent_change=pct_change,
        duration_seconds=hours * 3600,
        duration_minutes=hours * 60,
        duration_bars=hours,
    )


def test_generate_major_moon_phase_events_returns_expected_phases():
    start = datetime(2026, 1, 1)
    end = datetime(2026, 2, 1)

    events = generate_major_moon_phase_events(start, end)

    assert events
    phase_names = {event.phase_name for event in events}
    assert "New Moon" in phase_names
    assert "Full Moon" in phase_names


def test_analyze_moon_phase_correlation_builds_phase_stats():
    start = datetime(2026, 1, 1)
    data = [_make_candle(start + timedelta(hours=12 * idx), 100 + idx) for idx in range(80)]
    pivots = [
        PivotPoint(
            index=0,
            timestamp=datetime(2026, 1, 6, 20, 0),
            price=106,
            pivot_type=PivotType.SWING_LOW,
            source_candle_index=10,
        ),
        PivotPoint(
            index=1,
            timestamp=datetime(2026, 1, 14, 12, 0),
            price=118,
            pivot_type=PivotType.SWING_HIGH,
            source_candle_index=25,
        ),
        PivotPoint(
            index=2,
            timestamp=datetime(2026, 1, 21, 8, 0),
            price=109,
            pivot_type=PivotType.SWING_LOW,
            source_candle_index=40,
        ),
        PivotPoint(
            index=3,
            timestamp=datetime(2026, 1, 29, 10, 0),
            price=121,
            pivot_type=PivotType.SWING_HIGH,
            source_candle_index=55,
        ),
    ]
    legs = [
        _make_leg(1, datetime(2026, 1, 6, 20, 0), 36, 106, 115),
        _make_leg(2, datetime(2026, 1, 14, 12, 0), 48, 118, 110),
        _make_leg(3, datetime(2026, 1, 21, 8, 0), 42, 109, 120),
        _make_leg(4, datetime(2026, 1, 29, 10, 0), 36, 121, 112),
    ]
    config = Config(
        timeframe="1d",
        enable_moon_phase_analysis=True,
        left_bars=5,
        right_bars=5,
    )

    insight = analyze_moon_phase_correlation(data, pivots, legs, config)

    assert insight is not None
    assert insight.total_events > 0
    assert insight.phase_stats
    assert any(stat.phase_name == "Full Moon" for stat in insight.phase_stats)
    assert all(event.phase_name for event in insight.events)
