"""Cross-asset correlation analytics for BTC versus macro benchmarks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from btc_cycle_tracker.models import (
    AssetCorrelationInsight,
    AssetCorrelationObservation,
    OHLCV,
)


def _to_unix_seconds(value: datetime) -> int:
    """Convert naive or aware datetimes into UTC unix seconds."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return int(value.timestamp())


def fetch_yahoo_daily_close_series(
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.Series:
    """Fetch a daily close series from Yahoo Finance."""
    params = urlencode(
        {
            "period1": _to_unix_seconds(start),
            "period2": _to_unix_seconds(end),
            "interval": "1d",
            "includePrePost": "false",
            "events": "div,splits",
        }
    )
    request = Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}",
        headers={"User-Agent": "btc-swing-cycle-tracker/0.1.0"},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    result = payload.get("chart", {}).get("result", [])
    if not result:
        raise RuntimeError(f"No Yahoo Finance data returned for {symbol}")

    series_payload = result[0]
    timestamps = series_payload.get("timestamp") or []
    closes = (
        series_payload.get("indicators", {})
        .get("quote", [{}])[0]
        .get("close", [])
    )
    records = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        records.append(
            (
                datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None),
                float(close),
            )
        )

    if not records:
        raise RuntimeError(f"No valid close data returned for {symbol}")

    frame = pd.DataFrame(records, columns=["timestamp", "close"]).drop_duplicates("timestamp")
    return frame.set_index("timestamp")["close"].sort_index()


def _btc_daily_close_series(data: list[OHLCV]) -> pd.Series:
    """Collapse BTC candles into a daily close series."""
    frame = pd.DataFrame(
        {
            "timestamp": [candle.timestamp for candle in data],
            "close": [candle.close for candle in data],
        }
    ).drop_duplicates("timestamp")
    frame = frame.set_index("timestamp").sort_index()
    return frame["close"].resample("1D").last().dropna()


def build_asset_correlation_insight(
    data: list[OHLCV],
    asset_name: str,
    asset_symbol: str,
    external_prices: pd.Series | None = None,
) -> AssetCorrelationInsight | None:
    """Build normalized price and rolling-return correlation insight."""
    if len(data) < 2:
        return None

    btc_daily = _btc_daily_close_series(data)
    if btc_daily.empty:
        return None

    if external_prices is None:
        external_prices = fetch_yahoo_daily_close_series(
            asset_symbol,
            btc_daily.index.min().to_pydatetime(),
            btc_daily.index.max().to_pydatetime(),
        )

    asset_daily = external_prices.sort_index().resample("1D").last().dropna()
    joined = pd.concat(
        [btc_daily.rename("btc_close"), asset_daily.rename("asset_close")],
        axis=1,
        join="inner",
    ).dropna()

    if len(joined) < 3:
        return AssetCorrelationInsight(
            asset_name=asset_name,
            asset_symbol=asset_symbol,
            overlap_points=len(joined),
            rolling_window_days=0,
            summary=f"Not enough overlapping daily data to chart BTC versus {asset_name} yet.",
            observations=[],
        )

    normalized = joined / joined.iloc[0] * 100
    returns = joined.pct_change().dropna()
    rolling_window = min(30, max(5, len(returns) // 3))
    rolling_corr = (
        returns["btc_close"].rolling(rolling_window).corr(returns["asset_close"])
        if len(returns) >= rolling_window
        else pd.Series(index=returns.index, dtype=float)
    )

    price_corr = float(joined["btc_close"].corr(joined["asset_close"]))
    return_corr = float(returns["btc_close"].corr(returns["asset_close"])) if len(returns) >= 2 else None
    asset_variance = float(returns["asset_close"].var()) if len(returns) >= 2 else 0.0
    beta = None
    if asset_variance > 0:
        beta = float(returns["btc_close"].cov(returns["asset_close"]) / asset_variance)

    latest_relative_strength = float(
        normalized["btc_close"].iloc[-1] - normalized["asset_close"].iloc[-1]
    )
    latest_rolling = None
    if not rolling_corr.dropna().empty:
        latest_rolling = float(rolling_corr.dropna().iloc[-1])

    observations = [
        AssetCorrelationObservation(
            timestamp=index.to_pydatetime(),
            btc_normalized=float(normalized.loc[index, "btc_close"]),
            asset_normalized=float(normalized.loc[index, "asset_close"]),
            rolling_return_correlation=(
                float(rolling_corr.loc[index])
                if index in rolling_corr.index and not pd.isna(rolling_corr.loc[index])
                else None
            ),
        )
        for index in joined.index
    ]

    corr_label = "tracking closely"
    corr_value = return_corr if return_corr is not None else price_corr
    if corr_value is not None:
        if corr_value >= 0.5:
            corr_label = "moving with"
        elif corr_value <= -0.3:
            corr_label = "moving against"
        else:
            corr_label = "only loosely following"

    summary = (
        f"Across {len(joined)} overlapping daily closes, BTC is {corr_label} {asset_name.lower()}. "
        f"Return correlation is {return_corr:.2f} and relative strength is {latest_relative_strength:+.2f} normalized points."
        if return_corr is not None
        else f"Across {len(joined)} overlapping daily closes, BTC has limited overlap with {asset_name.lower()}."
    )

    return AssetCorrelationInsight(
        asset_name=asset_name,
        asset_symbol=asset_symbol,
        overlap_points=len(joined),
        rolling_window_days=rolling_window,
        price_correlation=price_corr,
        return_correlation=return_corr,
        beta_to_asset=beta,
        latest_rolling_correlation=latest_rolling,
        latest_relative_strength_pct=latest_relative_strength,
        summary=summary,
        observations=observations,
    )
