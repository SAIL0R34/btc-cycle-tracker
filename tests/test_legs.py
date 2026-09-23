"""Tests for swing leg generation and metrics."""

import pytest
from datetime import datetime, timedelta

from btc_cycle_tracker.models import OHLCV, PivotPoint, PivotType, SwingLeg
from btc_cycle_tracker.analytics.legs import LegBuilder, calculate_leg_metrics
from btc_cycle_tracker.analytics.stats import calculate_summary_stats


class TestLegBuilder:
    """Tests for the LegBuilder."""

    def test_build_legs_basic(self):
        """Test basic leg building with alternating pivots."""
        now = datetime.now()
        pivots = [
            PivotPoint(
                index=0,
                timestamp=now,
                price=100,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=0,
                left_bars=1,
                right_bars=1,
            ),
            PivotPoint(
                index=10,
                timestamp=now + timedelta(hours=1),
                price=95,
                pivot_type=PivotType.SWING_LOW,
                source_candle_index=10,
                left_bars=1,
                right_bars=1,
            ),
            PivotPoint(
                index=20,
                timestamp=now + timedelta(hours=2),
                price=105,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=20,
                left_bars=1,
                right_bars=1,
            ),
        ]

        # Create data with matching timestamps
        data = [
            OHLCV(
                timestamp=now + timedelta(minutes=i * 6),
                open=100,
                high=100,
                low=100,
                close=100,
                volume=100,
            )
            for i in range(30)
        ]

        legs = LegBuilder.build_legs(pivots, data)

        assert len(legs) == 2
        assert legs[0].direction == "down"
        assert legs[1].direction == "up"

        # Check leg metrics
        assert legs[0].percent_change < 0  # Down leg
        assert legs[1].percent_change > 0  # Up leg

    def test_build_legs_empty(self):
        """Test leg building with no pivots."""
        legs = LegBuilder.build_legs([], [])
        assert legs == []

    def test_build_legs_single_pivot(self):
        """Test leg building with single pivot."""
        pivots = [
            PivotPoint(
                index=0,
                timestamp=datetime.now(),
                price=100,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=0,
                left_bars=1,
                right_bars=1,
            ),
        ]
        data = []

        legs = LegBuilder.build_legs(pivots, data)
        assert legs == []

    def test_build_legs_all_metrics(self):
        """Test that all leg metrics are calculated correctly."""
        now = datetime.now()
        pivots = [
            PivotPoint(
                index=0,
                timestamp=now,
                price=100,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=0,
                left_bars=1,
                right_bars=1,
            ),
            PivotPoint(
                index=10,
                timestamp=now + timedelta(hours=1),
                price=90,
                pivot_type=PivotType.SWING_LOW,
                source_candle_index=10,
                left_bars=1,
                right_bars=1,
            ),
        ]

        data = [
            OHLCV(
                timestamp=now + timedelta(minutes=i * 6),
                open=100,
                high=100,
                low=100,
                close=100,
                volume=100,
            )
            for i in range(20)
        ]

        legs = LegBuilder.build_legs(pivots, data)

        assert len(legs) == 1
        leg = legs[0]

        # Check all metrics
        assert leg.leg_id == 1
        assert leg.start_pivot_id == 1
        assert leg.end_pivot_id == 2
        assert leg.direction == "down"
        assert leg.start_price == 100
        assert leg.end_price == 90
        assert leg.absolute_change == 10
        assert leg.percent_change == pytest.approx(-10.0, rel=0.01)
        assert leg.duration_seconds == 3600
        assert leg.duration_minutes == 60.0
        assert leg.duration_bars == 10

    def test_build_legs_min_leg_change(self):
        """Test leg filtering by minimum percent change."""
        now = datetime.now()
        pivots = [
            PivotPoint(
                index=0,
                timestamp=now,
                price=100,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=0,
                left_bars=1,
                right_bars=1,
            ),
            PivotPoint(
                index=10,
                timestamp=now + timedelta(hours=1),
                price=99,  # Only 1% change
                pivot_type=PivotType.SWING_LOW,
                source_candle_index=10,
                left_bars=1,
                right_bars=1,
            ),
            PivotPoint(
                index=20,
                timestamp=now + timedelta(hours=2),
                price=110,  # 11% change
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=20,
                left_bars=1,
                right_bars=1,
            ),
        ]

        data = [
            OHLCV(
                timestamp=now + timedelta(minutes=i * 6),
                open=100,
                high=100,
                low=100,
                close=100,
                volume=100,
            )
            for i in range(30)
        ]

        # With min_leg_change_pct=5, only the second leg should be included
        legs = LegBuilder.build_legs(pivots, data, min_leg_change_pct=5.0)

        # First leg (1% change) should be filtered out
        assert len(legs) == 1
        assert legs[0].percent_change == pytest.approx(11.0, rel=0.1)

    def test_build_legs_from_pivots_alternation(self):
        """Test that build_legs_from_pivots ensures alternation."""
        now = datetime.now()
        # Create pivots with two swing highs in a row
        pivots = [
            PivotPoint(
                index=0,
                timestamp=now,
                price=100,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=0,
                left_bars=1,
                right_bars=1,
            ),
            PivotPoint(
                index=5,
                timestamp=now + timedelta(minutes=30),
                price=110,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=5,
                left_bars=1,
                right_bars=1,
            ),
            PivotPoint(
                index=10,
                timestamp=now + timedelta(hours=1),
                price=95,
                pivot_type=PivotType.SWING_LOW,
                source_candle_index=10,
                left_bars=1,
                right_bars=1,
            ),
        ]

        data = [
            OHLCV(
                timestamp=now + timedelta(minutes=i * 6),
                open=100,
                high=100,
                low=100,
                close=100,
                volume=100,
            )
            for i in range(20)
        ]

        legs = LegBuilder.build_legs_from_pivots(pivots, data)

        # Should filter out the second swing high
        assert len(legs) == 1
        assert legs[0].direction == "down"

    def test_build_legs_from_pivots_ignores_invalid_reversal(self):
        """Skip opposite-type pivots that do not actually reverse price."""
        now = datetime.now()
        pivots = [
            PivotPoint(
                index=0,
                timestamp=now,
                price=110,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=0,
            ),
            PivotPoint(
                index=5,
                timestamp=now + timedelta(minutes=25),
                price=112,  # Invalid swing low above the prior high
                pivot_type=PivotType.SWING_LOW,
                source_candle_index=5,
            ),
            PivotPoint(
                index=8,
                timestamp=now + timedelta(minutes=40),
                price=115,  # More extreme swing high should replace the first one
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=8,
            ),
            PivotPoint(
                index=14,
                timestamp=now + timedelta(minutes=70),
                price=102,
                pivot_type=PivotType.SWING_LOW,
                source_candle_index=14,
            ),
        ]

        data = [
            OHLCV(
                timestamp=now + timedelta(minutes=i * 5),
                open=100,
                high=100,
                low=100,
                close=100,
                volume=100,
            )
            for i in range(20)
        ]

        legs = LegBuilder.build_legs_from_pivots(pivots, data)

        assert len(legs) == 1
        assert legs[0].start_price == 115
        assert legs[0].end_price == 102
        assert legs[0].direction == "down"

    def test_build_leg_direction_uses_actual_price_move(self):
        """Leg direction should always match the plotted slope."""
        now = datetime.now()
        start = PivotPoint(
            index=0,
            timestamp=now,
            price=100,
            pivot_type=PivotType.SWING_HIGH,
            source_candle_index=0,
        )
        end = PivotPoint(
            index=5,
            timestamp=now + timedelta(minutes=25),
            price=105,
            pivot_type=PivotType.SWING_LOW,
            source_candle_index=5,
        )

        leg = LegBuilder._build_leg(start, end, leg_id=1, start_pivot_id=1, data=[])

        assert leg is not None
        assert leg.direction == "up"
        assert leg.percent_change > 0

    def test_build_legs_non_sequential_indices(self):
        """Test leg building when pivot indices are not sequential."""
        now = datetime.now()
        pivots = [
            PivotPoint(
                index=0,
                timestamp=now,
                price=100,
                pivot_type=PivotType.SWING_HIGH,
                source_candle_index=0,
                left_bars=1,
                right_bars=1,
            ),
            PivotPoint(
                index=20,  # Large gap in indices
                timestamp=now + timedelta(hours=2),
                price=90,
                pivot_type=PivotType.SWING_LOW,
                source_candle_index=20,
                left_bars=1,
                right_bars=1,
            ),
        ]

        data = [
            OHLCV(
                timestamp=now + timedelta(minutes=i * 6),
                open=100,
                high=100,
                low=100,
                close=100,
                volume=100,
            )
            for i in range(30)
        ]

        legs = LegBuilder.build_legs(pivots, data)

        assert len(legs) == 1
        assert legs[0].duration_bars == 20


class TestLegMetrics:
    """Tests for leg metrics calculation."""

    def test_calculate_leg_metrics(self):
        """Test metrics calculation."""
        now = datetime.now()
        legs = [
            SwingLeg(
                leg_id=1,
                start_pivot_id=1,
                end_pivot_id=2,
                direction="down",
                start_timestamp=now,
                end_timestamp=now + timedelta(hours=1),
                start_price=100,
                end_price=95,
                absolute_change=5,
                percent_change=-5.0,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
            SwingLeg(
                leg_id=2,
                start_pivot_id=2,
                end_pivot_id=3,
                direction="up",
                start_timestamp=now + timedelta(hours=1),
                end_timestamp=now + timedelta(hours=2),
                start_price=95,
                end_price=105,
                absolute_change=10,
                percent_change=10.53,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
        ]

        metrics = calculate_leg_metrics(legs)

        assert metrics["total_legs"] == 2
        assert metrics["up_legs_count"] == 1
        assert metrics["down_legs_count"] == 1
        assert metrics["avg_percent_change"] == pytest.approx(2.76, rel=0.01)
        assert metrics["up_legs_total_change"] == pytest.approx(10.53, rel=0.01)
        assert metrics["down_legs_total_change"] == pytest.approx(-5.0, rel=0.01)

    def test_calculate_leg_metrics_empty(self):
        """Test metrics calculation with no legs."""
        metrics = calculate_leg_metrics([])
        assert metrics["total_legs"] == 0
        assert metrics["up_legs_count"] == 0
        assert metrics["down_legs_count"] == 0

    def test_calculate_leg_metrics_single_leg(self):
        """Test metrics calculation with single leg."""
        now = datetime.now()
        legs = [
            SwingLeg(
                leg_id=1,
                start_pivot_id=1,
                end_pivot_id=2,
                direction="up",
                start_timestamp=now,
                end_timestamp=now + timedelta(hours=1),
                start_price=100,
                end_price=110,
                absolute_change=10,
                percent_change=10.0,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
        ]

        metrics = calculate_leg_metrics(legs)

        assert metrics["total_legs"] == 1
        assert metrics["up_legs_count"] == 1
        assert metrics["up_legs_avg_change"] == pytest.approx(10.0, rel=0.01)


class TestSummaryStats:
    """Tests for summary statistics calculation."""

    def test_calculate_summary_stats(self):
        """Test summary statistics."""
        now = datetime.now()
        legs = [
            SwingLeg(
                leg_id=1,
                start_pivot_id=1,
                end_pivot_id=2,
                direction="down",
                start_timestamp=now,
                end_timestamp=now + timedelta(hours=1),
                start_price=100,
                end_price=95,
                absolute_change=5,
                percent_change=-5.0,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
            SwingLeg(
                leg_id=2,
                start_pivot_id=2,
                end_pivot_id=3,
                direction="up",
                start_timestamp=now + timedelta(hours=1),
                end_timestamp=now + timedelta(hours=2),
                start_price=95,
                end_price=105,
                absolute_change=10,
                percent_change=10.0,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
        ]

        stats = calculate_summary_stats(legs)

        assert stats.total_legs == 2
        assert stats.up_legs_count == 1
        assert stats.down_legs_count == 1
        assert stats.avg_percent_change == pytest.approx(2.5, rel=0.01)
        assert stats.up_legs_total_change == pytest.approx(10.0, rel=0.01)
        assert stats.down_legs_total_change == pytest.approx(-5.0, rel=0.01)

    def test_calculate_summary_stats_empty(self):
        """Test summary statistics with no legs."""
        stats = calculate_summary_stats([])
        assert stats.total_legs == 0
        assert stats.up_legs_count == 0
        assert stats.down_legs_count == 0

    def test_calculate_summary_stats_median(self):
        """Test that median values are calculated correctly."""
        now = datetime.now()
        legs = [
            SwingLeg(
                leg_id=1,
                start_pivot_id=1,
                end_pivot_id=2,
                direction="down",
                start_timestamp=now,
                end_timestamp=now + timedelta(hours=1),
                start_price=100,
                end_price=95,
                absolute_change=5,
                percent_change=-5.0,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
            SwingLeg(
                leg_id=2,
                start_pivot_id=2,
                end_pivot_id=3,
                direction="up",
                start_timestamp=now + timedelta(hours=1),
                end_timestamp=now + timedelta(hours=2),
                start_price=95,
                end_price=105,
                absolute_change=10,
                percent_change=10.0,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
            SwingLeg(
                leg_id=3,
                start_pivot_id=3,
                end_pivot_id=4,
                direction="down",
                start_timestamp=now + timedelta(hours=2),
                end_timestamp=now + timedelta(hours=3),
                start_price=105,
                end_price=100,
                absolute_change=5,
                percent_change=-5.0,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
        ]

        stats = calculate_summary_stats(legs)

        # Median of [-5, 10, -5] = -5
        assert stats.median_percent_change == pytest.approx(-5.0, rel=0.01)
        assert stats.median_duration_minutes == pytest.approx(60.0, rel=0.01)

    def test_calculate_summary_stats_asymmetry(self):
        """Test up/down asymmetry calculation."""
        now = datetime.now()
        # 3 up legs, 1 down leg = 75% up, 25% down = 0.5 asymmetry
        legs = [
            SwingLeg(
                leg_id=1,
                start_pivot_id=1,
                end_pivot_id=2,
                direction="up",
                start_timestamp=now,
                end_timestamp=now + timedelta(hours=1),
                start_price=100,
                end_price=110,
                absolute_change=10,
                percent_change=10.0,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
            SwingLeg(
                leg_id=2,
                start_pivot_id=2,
                end_pivot_id=3,
                direction="up",
                start_timestamp=now + timedelta(hours=1),
                end_timestamp=now + timedelta(hours=2),
                start_price=110,
                end_price=120,
                absolute_change=10,
                percent_change=9.09,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
            SwingLeg(
                leg_id=3,
                start_pivot_id=3,
                end_pivot_id=4,
                direction="up",
                start_timestamp=now + timedelta(hours=2),
                end_timestamp=now + timedelta(hours=3),
                start_price=120,
                end_price=130,
                absolute_change=10,
                percent_change=8.33,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
            SwingLeg(
                leg_id=4,
                start_pivot_id=4,
                end_pivot_id=5,
                direction="down",
                start_timestamp=now + timedelta(hours=3),
                end_timestamp=now + timedelta(hours=4),
                start_price=130,
                end_price=120,
                absolute_change=10,
                percent_change=-7.69,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
        ]

        stats = calculate_summary_stats(legs)

        # Asymmetry is the signed *magnitude* imbalance between up and down
        # legs: (avg|up| - avg|down|) / (avg|up| + avg|down|).
        avg_up = (10.0 + 9.09 + 8.33) / 3
        avg_down = 7.69
        expected = (avg_up - avg_down) / (avg_up + avg_down)
        assert stats.up_legs_count == 3
        assert stats.down_legs_count == 1
        assert stats.up_down_asymmetry == pytest.approx(expected, rel=0.01)

    def test_calculate_summary_stats_single_leg(self):
        """Test summary statistics with single leg."""
        now = datetime.now()
        legs = [
            SwingLeg(
                leg_id=1,
                start_pivot_id=1,
                end_pivot_id=2,
                direction="up",
                start_timestamp=now,
                end_timestamp=now + timedelta(hours=1),
                start_price=100,
                end_price=110,
                absolute_change=10,
                percent_change=10.0,
                duration_seconds=3600,
                duration_minutes=60.0,
                duration_bars=10,
            ),
        ]

        stats = calculate_summary_stats(legs)

        assert stats.total_legs == 1
        assert stats.up_legs_count == 1
        assert stats.up_legs_avg_change == pytest.approx(10.0, rel=0.01)
        assert stats.median_percent_change == pytest.approx(10.0, rel=0.01)
