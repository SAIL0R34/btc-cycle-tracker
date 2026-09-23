"""Validation script for BTC Swing Cycle Tracker.

Tests the current implementation with synthetic data to identify issues.
"""

import asyncio
from datetime import datetime, timedelta

from btc_cycle_tracker.models import OHLCV, PivotType, Config
from btc_cycle_tracker.pivots.zigzag import ZigZagDetector
from btc_cycle_tracker.pivots.fractal import FractalDetector
from btc_cycle_tracker.pivots.filters import ATRFilter, PercentChangeFilter
from btc_cycle_tracker.analytics.legs import LegBuilder, calculate_leg_metrics
from btc_cycle_tracker.analytics.stats import calculate_summary_stats, calculate_distribution_stats


def create_synthetic_data():
    """Create synthetic BTC-like price data with clear swing structure."""
    now = datetime.now()
    data = []

    # Pattern: Clear swing structure with noise
    # Up leg: 100 -> 110
    for i in range(10):
        data.append(OHLCV(
            timestamp=now + timedelta(minutes=i * 5),
            open=100 + i,
            high=100 + i + 1,
            low=100 + i - 1,
            close=100 + i + 0.5,
            volume=100 + i * 10,
        ))

    # Down leg: 110 -> 95
    for i in range(15):
        data.append(OHLCV(
            timestamp=now + timedelta(minutes=50 + i * 5),
            open=110 - i * 1.5,
            high=110 - i * 1.5 + 1,
            low=110 - i * 1.5 - 1,
            close=110 - i * 1.5 - 0.5,
            volume=100 + i * 10,
        ))

    # Up leg: 95 -> 105
    for i in range(12):
        data.append(OHLCV(
            timestamp=now + timedelta(minutes=125 + i * 5),
            open=95 + i,
            high=95 + i + 1,
            low=95 + i - 1,
            close=95 + i + 0.5,
            volume=100 + i * 10,
        ))

    # Choppy/flat period
    for i in range(20):
        data.append(OHLCV(
            timestamp=now + timedelta(minutes=185 + i * 5),
            open=105 + (i % 5 - 2) * 0.5,
            high=105 + (i % 5 - 2) * 0.5 + 0.5,
            low=105 + (i % 5 - 2) * 0.5 - 0.5,
            close=105,
            volume=50,
        ))

    # Final up leg: 105 -> 115
    for i in range(10):
        data.append(OHLCV(
            timestamp=now + timedelta(minutes=285 + i * 5),
            open=105 + i,
            high=105 + i + 1,
            low=105 + i - 1,
            close=105 + i + 0.5,
            volume=100 + i * 10,
        ))

    return data


def test_zigzag_detection():
    """Test ZigZag pivot detection."""
    print("\n" + "=" * 60)
    print("TEST: ZigZag Pivot Detection")
    print("=" * 60)

    data = create_synthetic_data()
    config = Config(min_move_pct=1.0, left_bars=2, right_bars=2)

    detector = ZigZagDetector(
        left_bars=2,
        right_bars=2,
        min_move_pct=1.0,
        use_atr_filter=False,
        min_candles_between=3,
        min_leg_duration_bars=2,
    )

    pivots = detector.detect_pivots(data, config)

    print(f"Total pivots detected: {len(pivots)}")
    print(f"Swing highs: {sum(1 for p in pivots if p.pivot_type == PivotType.SWING_HIGH)}")
    print(f"Swing lows: {sum(1 for p in pivots if p.pivot_type == PivotType.SWING_LOW)}")

    # Check alternation
    alternation_ok = True
    for i in range(len(pivots) - 1):
        if pivots[i].pivot_type == pivots[i + 1].pivot_type:
            alternation_ok = False
            print(f"WARNING: Consecutive pivots of same type at indices {i}, {i+1}")

    print(f"Alternation check: {'PASS' if alternation_ok else 'FAIL'}")

    # Print pivot details
    print("\nPivot details:")
    for i, p in enumerate(pivots):
        print(f"  {i+1}. {p.pivot_type} at index {p.index}, price ${p.price:.2f}")

    return pivots


def test_leg_generation():
    """Test swing leg generation."""
    print("\n" + "=" * 60)
    print("TEST: Swing Leg Generation")
    print("=" * 60)

    data = create_synthetic_data()
    config = Config(min_move_pct=1.0, left_bars=2, right_bars=2)

    detector = ZigZagDetector(
        left_bars=2,
        right_bars=2,
        min_move_pct=1.0,
        use_atr_filter=False,
        min_candles_between=3,
        min_leg_duration_bars=2,
    )

    pivots = detector.detect_pivots(data, config)
    legs = LegBuilder.build_legs_from_pivots(pivots, data, min_leg_change_pct=2.0)

    print(f"Total legs: {len(legs)}")

    for leg in legs:
        print(f"  Leg {leg.leg_id}: {leg.direction.upper()}")
        print(f"    Start: ${leg.start_price:.2f} -> End: ${leg.end_price:.2f}")
        print(f"    Change: {leg.percent_change:+.2f}%")
        print(f"    Duration: {leg.duration_minutes:.1f} min ({leg.duration_bars} candles)")

    metrics = calculate_leg_metrics(legs)
    print(f"\nMetrics:")
    print(f"  Avg % Change: {metrics['avg_percent_change']:.2f}%")
    print(f"  Up legs: {metrics['up_legs_count']} (avg: {metrics['up_legs_avg_change']:.2f}%)")
    print(f"  Down legs: {metrics['down_legs_count']} (avg: {metrics['down_legs_avg_change']:.2f}%)")

    return legs


def test_statistics():
    """Test summary statistics."""
    print("\n" + "=" * 60)
    print("TEST: Summary Statistics")
    print("=" * 60)

    data = create_synthetic_data()
    config = Config(min_move_pct=1.0, left_bars=2, right_bars=2)

    detector = ZigZagDetector(
        left_bars=2,
        right_bars=2,
        min_move_pct=1.0,
        use_atr_filter=False,
        min_candles_between=3,
        min_leg_duration_bars=2,
    )

    pivots = detector.detect_pivots(data, config)
    legs = LegBuilder.build_legs_from_pivots(pivots, data, min_leg_change_pct=2.0)
    stats = calculate_summary_stats(legs)

    print(f"Total legs: {stats.total_legs}")
    print(f"Avg % change: {stats.avg_percent_change:.2f}%")
    print(f"Min % change: {stats.min_percent_change:.2f}%")
    print(f"Max % change: {stats.max_percent_change:.2f}%")
    print(f"Avg duration: {stats.avg_duration_minutes:.1f} min")
    print(f"Up legs: {stats.up_legs_count} (avg: {stats.up_legs_avg_change:.2f}%)")
    print(f"Down legs: {stats.down_legs_count} (avg: {stats.down_legs_avg_change:.2f}%)")

    # Distribution stats
    dist = calculate_distribution_stats(legs, num_bins=5)
    print(f"\nPercent change distribution:")
    for bin_info in dist['percent_change']['histogram']:
        print(f"  {bin_info['bin_start']:.1f}% - {bin_info['bin_end']:.1f}%: {bin_info['count']} legs")

    return stats


def test_edge_cases():
    """Test edge cases."""
    print("\n" + "=" * 60)
    print("TEST: Edge Cases")
    print("=" * 60)

    # Test 1: Flat price
    print("\n1. Flat price (no movement):")
    flat_data = [
        OHLCV(
            timestamp=datetime.now() + timedelta(minutes=i * 5),
            open=100, high=100, low=100, close=100, volume=100
        )
        for i in range(50)
    ]
    config = Config(min_move_pct=1.0, left_bars=2, right_bars=2)
    detector = ZigZagDetector(left_bars=2, right_bars=2, min_move_pct=1.0, min_candles_between=3, min_leg_duration_bars=2)
    pivots = detector.detect_pivots(flat_data, config)
    print(f"   Pivots detected: {len(pivots)} (expected: 0-2)")

    # Test 2: Single candle
    print("\n2. Single candle:")
    single_data = [OHLCV(
        timestamp=datetime.now(),
        open=100, high=105, low=95, close=102, volume=100
    )]
    pivots = detector.detect_pivots(single_data, config)
    print(f"   Pivots detected: {len(pivots)} (expected: 0)")

    # Test 3: Insufficient data for left/right bars
    print("\n3. Insufficient data (less than left_bars + right_bars):")
    short_data = [
        OHLCV(timestamp=datetime.now() + timedelta(minutes=i * 5), open=100 + i, high=100 + i, low=100 + i, close=100 + i, volume=100)
        for i in range(3)
    ]
    pivots = detector.detect_pivots(short_data, config)
    print(f"   Pivots detected: {len(pivots)} (expected: 0)")

    # Test 4: Extreme volatility
    print("\n4. Extreme volatility:")
    volatile_data = []
    price = 100
    for i in range(30):
        price = price + (i % 5 - 2) * 10  # Large swings
        volatile_data.append(OHLCV(
            timestamp=datetime.now() + timedelta(minutes=i * 5),
            open=price, high=price + 5, low=price - 5, close=price + 2, volume=100
        ))
    pivots = detector.detect_pivots(volatile_data, config)
    print(f"   Pivots detected: {len(pivots)}")


def test_atr_filter():
    """Test ATR filter functionality."""
    print("\n" + "=" * 60)
    print("TEST: ATR Filter")
    print("=" * 60)

    data = create_synthetic_data()
    config = Config(min_move_pct=0.5, left_bars=2, right_bars=2, use_atr_filter=True)

    detector = ZigZagDetector(
        left_bars=2,
        right_bars=2,
        min_move_pct=0.5,
        use_atr_filter=True,
        atr_period=5,
        atr_multiplier=1.5,
        min_candles_between=3,
        min_leg_duration_bars=2,
    )

    pivots = detector.detect_pivots(data, config)
    print(f"Pivots with ATR filter: {len(pivots)}")

    # Compare with no filter
    detector_no_atr = ZigZagDetector(
        left_bars=2,
        right_bars=2,
        min_move_pct=0.5,
        use_atr_filter=False,
        min_candles_between=3,
        min_leg_duration_bars=2,
    )
    pivots_no_atr = detector_no_atr.detect_pivots(data, config)
    print(f"Pivots without ATR filter: {len(pivots_no_atr)}")


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("BTC Swing Cycle Tracker - Validation Tests")
    print("=" * 60)

    test_zigzag_detection()
    test_leg_generation()
    test_statistics()
    test_edge_cases()
    test_atr_filter()

    print("\n" + "=" * 60)
    print("Validation Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
