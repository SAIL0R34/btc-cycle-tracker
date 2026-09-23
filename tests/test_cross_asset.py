"""Tests for cross-asset correlation analytics."""

from datetime import datetime, timedelta

import pandas as pd

from btc_cycle_tracker.analytics.cross_asset import build_asset_correlation_insight
from btc_cycle_tracker.app.components.charts import create_asset_correlation_chart
from btc_cycle_tracker.models import OHLCV


def _make_candle(timestamp: datetime, close: float) -> OHLCV:
    return OHLCV(
        timestamp=timestamp,
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        volume=1000,
    )


def test_build_asset_correlation_insight_with_external_series():
    start = datetime(2026, 1, 1)
    data = [_make_candle(start + timedelta(days=day), 100 + (day * 2)) for day in range(20)]
    external = pd.Series(
        [200 + (day * 1.5) for day in range(20)],
        index=pd.date_range(start, periods=20, freq="D"),
    )

    insight = build_asset_correlation_insight(
        data=data,
        asset_name="Gold",
        asset_symbol="GC=F",
        external_prices=external,
    )

    assert insight is not None
    assert insight.asset_name == "Gold"
    assert insight.overlap_points == 20
    assert insight.return_correlation is not None
    assert len(insight.observations) == 20


def test_create_asset_correlation_chart_returns_plotly_figure():
    start = datetime(2026, 1, 1)
    data = [_make_candle(start + timedelta(days=day), 100 + day) for day in range(18)]
    external = pd.Series(
        [300 - (day * 2) for day in range(18)],
        index=pd.date_range(start, periods=18, freq="D"),
    )
    insight = build_asset_correlation_insight(
        data=data,
        asset_name="Nasdaq",
        asset_symbol="^IXIC",
        external_prices=external,
    )

    fig = create_asset_correlation_chart(insight)

    assert fig is not None
    assert len(fig.data) == 3
