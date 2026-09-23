"""Tests for data loading and normalization."""

import pytest
from datetime import datetime, timedelta

from btc_cycle_tracker.models import OHLCV
from btc_cycle_tracker.data.normalization import (
    normalize_ohlcv,
    fill_gaps,
    calculate_returns,
    calculate_volatility,
    calculate_atr,
)


class TestOHLCVNormalization:
    """Tests for OHLCV data normalization."""

    def test_normalize_sorts_by_timestamp(self):
        """Test that normalization sorts by timestamp."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now + timedelta(hours=1), open=100, high=100, low=100, close=100, volume=100),
            OHLCV(timestamp=now, open=100, high=100, low=100, close=100, volume=100),
        ]

        normalized = normalize_ohlcv(data)

        assert normalized[0].timestamp < normalized[1].timestamp

    def test_normalize_removes_duplicates(self):
        """Test that normalization removes duplicate timestamps."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now, open=100, high=100, low=100, close=100, volume=100),
            OHLCV(timestamp=now, open=101, high=101, low=101, close=101, volume=100),
        ]

        normalized = normalize_ohlcv(data)

        assert len(normalized) == 1

    def test_normalize_empty(self):
        """Test normalization with empty data."""
        normalized = normalize_ohlcv([])
        assert normalized == []


class TestGapFilling:
    """Tests for gap filling in OHLCV data."""

    def test_fill_gaps_creates_candles(self):
        """Test that gaps are filled with candles."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now, open=100, high=100, low=100, close=100, volume=100),
            OHLCV(timestamp=now + timedelta(minutes=15), open=100, high=100, low=100, close=100, volume=100),
        ]

        filled = fill_gaps(data, expected_timeframe="5m")

        # Should have filled the 10-minute gap
        assert len(filled) >= 2

    def test_fill_gaps_no_gaps(self):
        """Test gap filling with no gaps."""
        now = datetime.now()
        data = [
            OHLCV(timestamp=now, open=100, high=100, low=100, close=100, volume=100),
            OHLCV(timestamp=now + timedelta(minutes=5), open=100, high=100, low=100, close=100, volume=100),
        ]

        filled = fill_gaps(data, expected_timeframe="5m")

        assert len(filled) == 2


class TestReturnsCalculation:
    """Tests for returns calculation."""

    def test_calculate_returns(self):
        """Test returns calculation."""
        data = [
            OHLCV(timestamp=datetime.now(), open=100, high=100, low=100, close=100, volume=100),
            OHLCV(timestamp=datetime.now(), open=100, high=100, low=100, close=110, volume=100),
            OHLCV(timestamp=datetime.now(), open=100, high=100, low=100, close=105, volume=100),
        ]

        returns = calculate_returns(data)

        assert len(returns) == 2
        assert returns[0] == pytest.approx(10.0, rel=0.01)  # 10% increase
        assert returns[1] == pytest.approx(-4.55, rel=0.1)  # ~4.5% decrease

    def test_calculate_returns_empty(self):
        """Test returns calculation with empty data."""
        returns = calculate_returns([])
        assert returns == []

    def test_calculate_returns_single(self):
        """Test returns calculation with single candle."""
        data = [
            OHLCV(timestamp=datetime.now(), open=100, high=100, low=100, close=100, volume=100),
        ]

        returns = calculate_returns(data)
        assert returns == []


class TestATRCalculation:
    """Tests for ATR calculation."""

    def test_calculate_atr(self):
        """Test ATR calculation."""
        data = [
            OHLCV(timestamp=datetime.now(), open=100, high=105, low=95, close=102, volume=100),
            OHLCV(timestamp=datetime.now(), open=102, high=107, low=98, close=105, volume=100),
            OHLCV(timestamp=datetime.now(), open=105, high=110, low=100, close=108, volume=100),
            OHLCV(timestamp=datetime.now(), open=108, high=112, low=103, close=110, volume=100),
            OHLCV(timestamp=datetime.now(), open=110, high=115, low=105, close=112, volume=100),
        ]

        atr_values = calculate_atr(data, window=3)

        # Should have None for first few values, then ATR
        assert atr_values[0] is None
        assert atr_values[1] is None
        assert atr_values[2] is None
        assert atr_values[3] is not None

    def test_calculate_atr_insufficient_data(self):
        """Test ATR calculation with insufficient data."""
        data = [
            OHLCV(timestamp=datetime.now(), open=100, high=105, low=95, close=102, volume=100),
        ]

        atr_values = calculate_atr(data, window=14)
        assert all(v is None for v in atr_values)
