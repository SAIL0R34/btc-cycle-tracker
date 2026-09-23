"""Tests for CSV export functionality."""

import os
import tempfile
from datetime import datetime, timedelta

import pytest

from btc_cycle_tracker.models import OHLCV, PivotPoint, PivotType, SwingLeg, AnalysisMetadata, SummaryStatistics, AnalysisResult
from btc_cycle_tracker.export.csv_writer import CSVWriter


class TestCSVWriter:
    """Tests for CSV export."""

    def test_write_pivots(self):
        """Test writing pivots to CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CSVWriter(output_dir=tmpdir)

            pivots = [
                PivotPoint(
                    index=0,
                    timestamp=datetime.now(),
                    price=100.0,
                    pivot_type=PivotType.SWING_HIGH,
                    source_candle_index=0,
                    left_bars=5,
                    right_bars=5,
                ),
            ]

            filepath = writer.write_pivots(pivots)
            assert os.path.exists(filepath)

            # Verify file content
            with open(filepath, "r") as f:
                content = f.read()
                assert "pivot_id" in content
                assert "pivot_type" in content
                assert "confidence" in content

    def test_write_legs(self):
        """Test writing legs to CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CSVWriter(output_dir=tmpdir)

            now = datetime.now()
            legs = [
                SwingLeg(
                    leg_id=1,
                    start_pivot_id=1,
                    end_pivot_id=2,
                    direction="down",
                    start_timestamp=now,
                    end_timestamp=now + timedelta(hours=1),
                    start_price=100.0,
                    end_price=95.0,
                    absolute_change=5.0,
                    percent_change=-5.0,
                    duration_seconds=3600,
                    duration_minutes=60.0,
                    duration_bars=10,
                ),
            ]

            filepath = writer.write_legs(legs)
            assert os.path.exists(filepath)

            # Verify file content
            with open(filepath, "r") as f:
                content = f.read()
                assert "leg_id" in content
                assert "start_pivot_id" in content
                assert "end_pivot_id" in content
                assert "absolute_change" in content
                assert "percent_change" in content
                assert "duration_minutes" in content

    def test_write_analysis_result(self):
        """Test writing complete analysis result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CSVWriter(output_dir=tmpdir)

            now = datetime.now()
            result = AnalysisResult(
                metadata=AnalysisMetadata(
                    symbol="BTC-USD",
                    timeframe="5m",
                    pivot_method="zigzag",
                    start_date=now,
                    end_date=now,
                    total_candles=100,
                    total_pivots=10,
                    total_legs=5,
                    run_timestamp=now,
                ),
                pivots=[
                    PivotPoint(
                        index=0,
                        timestamp=now,
                        price=100,
                        pivot_type=PivotType.SWING_HIGH,
                        source_candle_index=0,
                        left_bars=5,
                        right_bars=5,
                    ),
                ],
                legs=[
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
                ],
                summary=SummaryStatistics(
                    total_legs=1,
                    avg_percent_change=-5.0,
                    avg_duration_minutes=60.0,
                    avg_duration_bars=10,
                    min_percent_change=-5.0,
                    max_percent_change=-5.0,
                    min_duration_minutes=60.0,
                    max_duration_minutes=60.0,
                    up_legs_count=0,
                    down_legs_count=1,
                    up_legs_total_change=0.0,
                    down_legs_total_change=-5.0,
                ),
                raw_data=[
                    OHLCV(timestamp=now, open=100, high=100, low=100, close=100, volume=100),
                ],
            )

            files = writer.write_analysis_result(result)

            assert "pivots" in files
            assert "legs" in files

    def test_write_summary(self):
        """Test writing summary statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CSVWriter(output_dir=tmpdir)

            now = datetime.now()
            result = AnalysisResult(
                metadata=AnalysisMetadata(
                    symbol="BTC-USD",
                    timeframe="5m",
                    pivot_method="zigzag",
                    start_date=now,
                    end_date=now,
                    total_candles=100,
                    total_pivots=10,
                    total_legs=5,
                    run_timestamp=now,
                ),
                pivots=[],
                legs=[],
                summary=SummaryStatistics(
                    total_legs=1,
                    avg_percent_change=-5.0,
                    avg_duration_minutes=60.0,
                    avg_duration_bars=10,
                    min_percent_change=-5.0,
                    max_percent_change=-5.0,
                    min_duration_minutes=60.0,
                    max_duration_minutes=60.0,
                    up_legs_count=0,
                    down_legs_count=1,
                    up_legs_total_change=0.0,
                    down_legs_total_change=-5.0,
                ),
                raw_data=[],
            )

            filepath = writer.write_summary(result)
            assert os.path.exists(filepath)

            with open(filepath, "r") as f:
                content = f.read()
                assert "total_legs" in content
                assert "avg_percent_change" in content
                assert "up_legs_total_change" in content
                assert "down_legs_total_change" in content
