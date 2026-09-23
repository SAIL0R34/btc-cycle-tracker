"""Data normalization utilities for OHLCV data."""

from typing import Optional

import numpy as np
import pandas as pd

from btc_cycle_tracker.models import OHLCV


def normalize_ohlcv(data: list[OHLCV]) -> list[OHLCV]:
    """Normalize OHLCV data by ensuring proper ordering and removing duplicates.

    Args:
        data: List of OHLCV candles

    Returns:
        Normalized list of OHLCV candles
    """
    if not data:
        return []

    # Sort by timestamp
    sorted_data = sorted(data, key=lambda x: x.timestamp)

    # Remove duplicates based on timestamp
    seen = set()
    unique_data = []
    for candle in sorted_data:
        ts = candle.timestamp.isoformat()
        if ts not in seen:
            seen.add(ts)
            unique_data.append(candle)

    return unique_data


def fill_gaps(
    data: list[OHLCV],
    expected_timeframe: str = "5m",
) -> list[OHLCV]:
    """Fill gaps in OHLCV data with empty candles.

    Args:
        data: List of OHLCV candles
        expected_timeframe: Expected timeframe between candles

    Returns:
        List of OHLCV candles with gaps filled
    """
    if not data:
        return []

    # Calculate expected interval in seconds
    interval_map = {
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
        "1w": 604800,
    }
    expected_interval = interval_map.get(expected_timeframe, 300)

    result = []
    prev_candle = None

    for candle in data:
        if prev_candle is not None:
            expected_time = prev_candle.timestamp.timestamp() + expected_interval
            actual_time = candle.timestamp.timestamp()

            # Fill gaps if there's a significant time difference
            while actual_time - expected_time > expected_interval * 1.5:
                # Create a gap-filling candle with same prices as previous
                gap_candle = OHLCV(
                    timestamp=prev_candle.timestamp,
                    open=prev_candle.close,
                    high=prev_candle.close,
                    low=prev_candle.close,
                    close=prev_candle.close,
                    volume=0.0,
                )
                result.append(gap_candle)
                expected_time += expected_interval

        result.append(candle)
        prev_candle = candle

    return result


def calculate_returns(data: list[OHLCV]) -> list[float]:
    """Calculate percentage returns from OHLCV data.

    Args:
        data: List of OHLCV candles

    Returns:
        List of percentage returns (starting from index 1)
    """
    if len(data) < 2:
        return []

    returns = []
    for i in range(1, len(data)):
        prev_close = data[i - 1].close
        if prev_close != 0:
            ret = (data[i].close - prev_close) / prev_close * 100
        else:
            ret = 0.0
        returns.append(ret)

    return returns


def calculate_volatility(
    data: list[OHLCV],
    window: int = 14,
) -> list[float]:
    """Calculate rolling volatility (standard deviation of returns).

    Args:
        data: List of OHLCV candles
        window: Rolling window size

    Returns:
        List of volatility values (None for insufficient data)
    """
    returns = calculate_returns(data)
    if len(returns) < window:
        return [None] * len(returns)

    volatilities = []
    for i in range(len(returns)):
        if i < window - 1:
            volatilities.append(None)
        else:
            window_returns = returns[i - window + 1 : i + 1]
            vol = np.std(window_returns)
            volatilities.append(vol)

    return volatilities


def calculate_atr(
    data: list[OHLCV],
    window: int = 14,
) -> list[float]:
    """Calculate Average True Range.

    Args:
        data: List of OHLCV candles
        window: Rolling window size

    Returns:
        List of ATR values (None for insufficient data)
    """
    if len(data) < window + 1:
        return [None] * len(data)

    tr_values = []
    for i in range(1, len(data)):
        high_low = data[i].high - data[i].low
        high_close = abs(data[i].high - data[i - 1].close)
        low_close = abs(data[i].low - data[i - 1].close)
        tr = max(high_low, high_close, low_close)
        tr_values.append(tr)

    atr_values = []
    for i in range(len(data)):
        if i < window:
            atr_values.append(None)
        else:
            window_tr = tr_values[i - window : i]
            atr = sum(window_tr) / len(window_tr)
            atr_values.append(atr)

    return atr_values


def resample_ohlcv(
    data: list[OHLCV],
    target_timeframe: str,
) -> list[OHLCV]:
    """Resample OHLCV data to a different timeframe.

    Args:
        data: List of OHLCV candles
        target_timeframe: Target timeframe (e.g., "1h", "4h")

    Returns:
        Resampled OHLCV candles
    """
    if not data:
        return []

    # Convert to DataFrame for resampling
    df = pd.DataFrame(
        [
            {
                "timestamp": d.timestamp,
                "open": d.open,
                "high": d.high,
                "low": d.low,
                "close": d.close,
                "volume": d.volume,
            }
            for d in data
        ]
    )
    df = df.set_index("timestamp")

    # Timeframe mapping
    freq_map = {
        "1m": "1min",
        "3m": "3min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1D",
        "1w": "1W",
    }

    freq = freq_map.get(target_timeframe, "5min")

    # Resample
    resampled = df.resample(freq).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    ).dropna()

    # Convert back to OHLCV objects
    result = []
    for ts, row in resampled.iterrows():
        candle = OHLCV(
            timestamp=ts.to_pydatetime(),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row.get("volume", 0.0) or 0.0,
        )
        result.append(candle)

    return result
