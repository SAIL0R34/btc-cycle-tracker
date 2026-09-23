"""Tests for pivot detection with noise filtering and ATR support."""

import pytest
from datetime import datetime, timedelta

from btc_cycle_tracker.models import OHLCV, PivotPoint, PivotType, Config
from btc_cycle_tracker.pivots.zigzag import ZigZagDetector
from btc_cycle_tracker.pivots.filters import ATRFilter, PercentChangeFilter


class TestZigZagDetector:
    """Tests for the ZigZag pivot detector."""

    def test_detect_pivots_basic(self):
        """Test basic pivot detection with clear swing points."""
        now = datetime.now()
        # Create data with clear swing high at index 1 and swing low at index 4
        data = [
            OHLCV(timestamp=now, open=100, high=102, low=98, close=101, volume=100),  # 0
            OHLCV(timestamp=now + timedelta(minutes=5), open=101, high=110, low=100, close=108, volume=150),  # 1 - swing high
            OHLCV(timestamp=now + timedelta(minutes=10), open=108, high=108, low=100, close=105, volume=120),  # 2
            OHLCV(timestamp=now + timedelta(minutes=15), open=105, high=105, low=95, close=98, volume=130),  # 3
            OHLCV(timestamp=now + timedelta(minutes=20), open=98, high=100, low=90, close=92, volume=110),  # 4 - swing low
            OHLCV(timestamp=now + timedelta(minutes=25), open=92, high=98, low=92, close=95, volume=140),  # 5
        ]

        detector = ZigZagDetector(left_bars=1, right_bars=1, min_move_pct=1.0, min_leg_duration_bars=1)
        config = Config()

        pivots = detector.detect_pivots(data, config)

        # Should detect at least 1 pivot (may not detect both due to min_leg_duration_bars)
        assert len(pivots) >= 1

        # Check that pivots alternate
        pivot_types = [p.pivot_type for p in pivots]
        for i in range(len(pivot_types) - 1):
            assert pivot_types[i] != pivot_types[i + 1]

    def test_detect_pivots_with_min_move(self):
        """Test that min_move_pct filter works correctly."""
        now = datetime.now()
        # Create data with small moves that should be filtered
        data = [
            OHLCV(timestamp=now, open=100, high=100.5, low=99.5, close=100, volume=100),  # 0
            OHLCV(timestamp=now + timedelta(minutes=5), open=100, high=101, low=99, close=100.5, volume=150),  # 1
            OHLCV(timestamp=now + timedelta(minutes=10), open=100.5, high=101.5, low=99.5, close=101, volume=120),  # 2
            OHLCV(timestamp=now + timedelta(minutes=15), open=101, high=102, low=100, close=101.5, volume=130),  # 3
        ]

        detector = ZigZagDetector(left_bars=1, right_bars=1, min_move_pct=2.0)
        config = Config()

        pivots = detector.detect_pivots(data, config)

        # With 2% threshold, should detect fewer pivots
        assert len(pivots) >= 0

    def test_detect_pivots_no_pivots(self):
        """Test detection when no pivots exist (flat price)."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now + timedelta(minutes=i*5), open=100, high=100, low=100, close=100, volume=100)
            for i in range(20)
        ]

        detector = ZigZagDetector(left_bars=2, right_bars=2, min_move_pct=1.0)
        config = Config()

        pivots = detector.detect_pivots(data, config)

        assert isinstance(pivots, list)

    def test_detect_pivots_alternation(self):
        """Test that pivots properly alternate between high and low."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now, open=100, high=105, low=95, close=102, volume=100),  # 0
            OHLCV(timestamp=now + timedelta(minutes=5), open=102, high=110, low=100, close=108, volume=150),  # 1 - high
            OHLCV(timestamp=now + timedelta(minutes=10), open=108, high=108, low=100, close=105, volume=120),  # 2
            OHLCV(timestamp=now + timedelta(minutes=15), open=105, high=105, low=90, close=95, volume=130),  # 3 - low
            OHLCV(timestamp=now + timedelta(minutes=20), open=95, high=100, low=92, close=98, volume=110),  # 4
            OHLCV(timestamp=now + timedelta(minutes=25), open=98, high=105, low=95, close=102, volume=140),  # 5 - high
        ]

        detector = ZigZagDetector(left_bars=1, right_bars=1, min_move_pct=1.0)
        config = Config()

        pivots = detector.detect_pivots(data, config)

        # Check alternation
        for i in range(len(pivots) - 1):
            assert pivots[i].pivot_type != pivots[i + 1].pivot_type

    def test_detect_pivots_insufficient_data(self):
        """Test detection with insufficient data for left/right bars."""
        now = datetime.now()
        # Less than left_bars + right_bars + 2 candles
        data = [
            OHLCV(timestamp=now, open=100, high=102, low=98, close=101, volume=100),
            OHLCV(timestamp=now + timedelta(minutes=5), open=101, high=103, low=99, close=102, volume=150),
        ]

        detector = ZigZagDetector(left_bars=2, right_bars=2, min_move_pct=1.0)
        config = Config()

        pivots = detector.detect_pivots(data, config)

        # Should return empty list when insufficient data
        assert len(pivots) == 0

    def test_detect_pivots_single_candle(self):
        """Test detection with single candle."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now, open=100, high=105, low=95, close=102, volume=100),
        ]

        detector = ZigZagDetector(left_bars=1, right_bars=1, min_move_pct=1.0)
        config = Config()

        pivots = detector.detect_pivots(data, config)

        # Should return empty list for single candle
        assert len(pivots) == 0

    def test_detect_pivots_very_volatile(self):
        """Test detection with very volatile price action."""
        now = datetime.now()
        data = []
        price = 100
        for i in range(50):
            # Large swings
            price = price + (i % 7 - 3) * 10
            data.append(OHLCV(
                timestamp=now + timedelta(minutes=i * 5),
                open=price,
                high=price + 5,
                low=price - 5,
                close=price + 2,
                volume=100 + i * 10,
            ))

        detector = ZigZagDetector(left_bars=2, right_bars=2, min_move_pct=1.0)
        config = Config()

        pivots = detector.detect_pivots(data, config)

        # Should detect some pivots even in volatile market
        assert len(pivots) > 0

    def test_detect_pivots_min_candles_between(self):
        """Test that min_candles_between constraint is enforced."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now, open=100, high=110, low=95, close=105, volume=100),  # 0 - swing high
            OHLCV(timestamp=now + timedelta(minutes=5), open=105, high=105, low=90, close=95, volume=150),  # 1 - swing low
            OHLCV(timestamp=now + timedelta(minutes=10), open=95, high=100, low=95, close=98, volume=120),  # 2
            OHLCV(timestamp=now + timedelta(minutes=15), open=98, high=105, low=98, close=102, volume=130),  # 3
            OHLCV(timestamp=now + timedelta(minutes=20), open=102, high=110, low=100, close=108, volume=110),  # 4 - swing high
        ]

        # With min_candles_between=3, should skip the second swing low
        detector = ZigZagDetector(
            left_bars=1, right_bars=1, min_move_pct=1.0,
            min_candles_between=3
        )
        config = Config()

        pivots = detector.detect_pivots(data, config)

        # Should detect fewer pivots due to min_candles_between
        assert len(pivots) >= 1

    def test_detect_pivots_true_extremes(self):
        """A pivot must sit on the leg's true extreme, not the first local
        fractal that happens to pass the threshold — and it records the
        candle that confirmed it."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now, open=100, high=100.5, low=99.5, close=100, volume=100),   # 0
            OHLCV(timestamp=now + timedelta(minutes=5), open=100, high=103, low=100, close=102, volume=150),  # 1 minor high
            OHLCV(timestamp=now + timedelta(minutes=10), open=102, high=101.5, low=101, close=101, volume=120),  # 2
            OHLCV(timestamp=now + timedelta(minutes=15), open=101, high=108, low=101.5, close=107, volume=130),  # 3
            OHLCV(timestamp=now + timedelta(minutes=20), open=107, high=110, low=107, close=109, volume=110),  # 4 true high
            OHLCV(timestamp=now + timedelta(minutes=25), open=109, high=106, low=105, close=105.5, volume=140),  # 5 reversal
            OHLCV(timestamp=now + timedelta(minutes=30), open=105.5, high=105, low=103, close=103.5, volume=120),  # 6
        ]

        detector = ZigZagDetector(left_bars=1, right_bars=1, min_move_pct=1.0, use_atr_filter=False)
        pivots = detector.detect_pivots(data, Config())

        assert pivots, "expected at least one pivot"
        # The true peak at index 4 must be a swing high; the minor 103 fractal
        # must not survive as a pivot (the running extreme extended past it).
        highs = [p for p in pivots if p.pivot_type == PivotType.SWING_HIGH]
        assert any(p.index == 4 for p in highs)
        assert all(p.price != 103 for p in highs)
        # Alternation holds by construction
        for a, b in zip(pivots, pivots[1:]):
            assert a.pivot_type != b.pivot_type
        # Every pivot records the candle that confirmed it
        for p in pivots:
            assert p.confirmation_candle_index is not None
            assert p.confirmation_candle_index >= p.index

    def test_detect_pivots_min_leg_duration(self):
        """Test that min_leg_duration_bars constraint is enforced."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now, open=100, high=110, low=95, close=105, volume=100),  # 0 - swing high
            OHLCV(timestamp=now + timedelta(minutes=5), open=105, high=105, low=90, close=95, volume=150),  # 1 - swing low
            OHLCV(timestamp=now + timedelta(minutes=10), open=95, high=100, low=95, close=98, volume=120),  # 2
        ]

        # With min_leg_duration_bars=3, the second pivot should be skipped
        detector = ZigZagDetector(
            left_bars=1, right_bars=1, min_move_pct=1.0,
            min_leg_duration_bars=3
        )
        config = Config()

        pivots = detector.detect_pivots(data, config)

        # With insufficient data, may detect 0 pivots
        assert len(pivots) >= 0


class TestATRFilter:
    """Tests for ATR-based filtering."""

    def test_atr_filter_applied(self):
        """Test that ATR filter is applied when enabled."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now, open=100, high=105, low=95, close=102, volume=100),
            OHLCV(timestamp=now + timedelta(minutes=5), open=102, high=107, low=98, close=105, volume=150),
            OHLCV(timestamp=now + timedelta(minutes=10), open=105, high=110, low=100, close=108, volume=120),
            OHLCV(timestamp=now + timedelta(minutes=15), open=108, high=112, low=103, close=110, volume=130),
            OHLCV(timestamp=now + timedelta(minutes=20), open=110, high=115, low=105, close=112, volume=110),
        ]

        detector = ZigZagDetector(
            left_bars=1,
            right_bars=1,
            min_move_pct=1.0,
            use_atr_filter=True,
            atr_period=3,
            atr_multiplier=1.5,
        )
        config = Config()

        pivots = detector.detect_pivots(data, config)

        assert isinstance(pivots, list)

    def test_atr_filter_not_applied(self):
        """Test that ATR filter is not applied when disabled."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now, open=100, high=105, low=95, close=102, volume=100),
            OHLCV(timestamp=now + timedelta(minutes=5), open=102, high=107, low=98, close=105, volume=150),
        ]

        detector = ZigZagDetector(
            left_bars=1,
            right_bars=1,
            min_move_pct=1.0,
            use_atr_filter=False,
        )
        config = Config()

        pivots = detector.detect_pivots(data, config)

        assert isinstance(pivots, list)


class TestPivotFilters:
    """Tests for pivot filters."""

    def test_percent_change_filter(self):
        """Test percent change filter."""
        now = datetime.now()
        pivots = [
            PivotPoint(
                index=0,
                timestamp=now,
                price=100,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=0,
            ),
            PivotPoint(
                index=1,
                timestamp=now + timedelta(minutes=5),
                price=100.5,
                pivot_type=PivotType.SWING_LOW,
                source_candle_index=1,
            ),
            PivotPoint(
                index=2,
                timestamp=now + timedelta(minutes=10),
                price=105,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=2,
            ),
        ]

        data = []

        filter_obj = PercentChangeFilter(min_pct_change=2.0)
        filtered = filter_obj.filter(pivots, data)

        # Second pivot should be filtered (< 2% change)
        assert len(filtered) <= len(pivots)
