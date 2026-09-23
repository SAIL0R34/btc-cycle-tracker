"""Data loaders for loading OHLCV data from various sources."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from btc_cycle_tracker.data.fetchers import BaseFetcher, get_fetcher
from btc_cycle_tracker.models import OHLCV, Timeframe
from btc_cycle_tracker.settings import settings


class DataLoader:
    """Loader for OHLCV data with caching and fallback support."""

    def __init__(
        self,
        fetcher: Optional[BaseFetcher] = None,
        cache_dir: Optional[str] = None,
    ):
        """Initialize the data loader.

        Args:
            fetcher: Data fetcher instance (uses default if None)
            cache_dir: Cache directory path (uses settings if None)
        """
        self.fetcher = fetcher or get_fetcher(settings.data.default_source)
        self.cache_dir = (
            settings.resolve_app_path(cache_dir) if cache_dir else settings.cache_path
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load_from_cache(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCV]:
        """Load data from cache if available.

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            start: Start datetime
            end: End datetime

        Returns:
            List of OHLCV candles from cache
        """
        normalized_timeframe = self._normalize_timeframe(timeframe)
        cache_file = self._get_cache_file(symbol, normalized_timeframe)
        if not cache_file.exists():
            return []

        try:
            df = pd.read_csv(cache_file, parse_dates=["timestamp"])
            df = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)]
            if df.empty:
                return []

            if not self._cache_covers_range(df, normalized_timeframe, start, end):
                return []

            return [OHLCV(**row) for row in df.to_dict("records")]
        except Exception:
            return []

    def save_to_cache(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        data: list[OHLCV],
    ) -> None:
        """Save data to cache.

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            data: List of OHLCV candles to save
        """
        normalized_timeframe = self._normalize_timeframe(timeframe)
        cache_file = self._get_cache_file(symbol, normalized_timeframe)
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        records = [
            {
                "timestamp": d.timestamp.isoformat(),
                "open": d.open,
                "high": d.high,
                "low": d.low,
                "close": d.close,
                "volume": d.volume,
            }
            for d in data
        ]
        df = pd.DataFrame(records)
        df.to_csv(cache_file, index=False)

    def _get_cache_file(self, symbol: str, timeframe: Timeframe) -> Path:
        """Get the cache file path for a symbol and timeframe.

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe

        Returns:
            Path to cache file
        """
        safe_symbol = symbol.replace("/", "_").replace("-", "_")
        return self.cache_dir / f"{safe_symbol}_{timeframe.value}.csv"

    async def fetch_and_load(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        lookback: str,
        use_cache: bool = True,
    ) -> list[OHLCV]:
        """Fetch data and load into memory.

        Args:
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            lookback: Lookback period (e.g., "30d", "7w")
            use_cache: Whether to use cached data

        Returns:
            List of OHLCV candles
        """
        normalized_timeframe = self._normalize_timeframe(timeframe)
        end = datetime.now()
        start = self._parse_lookback(lookback, end)

        if use_cache:
            cached = self.load_from_cache(symbol, normalized_timeframe, start, end)
            if cached:
                return cached

        data = await self.fetcher.fetch_ohlcv(symbol, normalized_timeframe, start, end)
        if data:
            self.save_to_cache(symbol, normalized_timeframe, data)
        return data

    def _parse_lookback(self, lookback: str, end: datetime) -> datetime:
        """Parse a lookback string to a start datetime.

        Args:
            lookback: Lookback string (e.g., "30d", "7w")
            end: End datetime

        Returns:
            Calculated start datetime
        """
        period = lookback[:-1]
        unit = lookback[-1]

        try:
            days = int(period)
        except ValueError:
            days = 30  # Default

        if unit == "d":
            return end - timedelta(days=days)
        elif unit == "w":
            return end - timedelta(weeks=days)
        elif unit == "m":
            return end - timedelta(days=days * 30)
        elif unit == "y":
            return end - timedelta(days=days * 365)
        else:
            return end - timedelta(days=30)

    def load_from_file(self, filepath: str | Path) -> list[OHLCV]:
        """Load OHLCV data from a CSV file.

        Args:
            filepath: Path to CSV file

        Returns:
            List of OHLCV candles
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        df = pd.read_csv(path, parse_dates=["timestamp"])
        return [OHLCV(**row) for row in df.to_dict("records")]

    def _normalize_timeframe(self, timeframe: Timeframe | str) -> Timeframe:
        """Normalize string timeframes to the Timeframe enum."""
        if isinstance(timeframe, Timeframe):
            return timeframe
        return Timeframe(timeframe)

    def _cache_covers_range(
        self,
        df: pd.DataFrame,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> bool:
        """Require cached data to span the requested interval before using it."""
        if df.empty:
            return False

        interval_seconds = {
            Timeframe.ONE_MINUTE: 60,
            Timeframe.THREE_MINUTE: 180,
            Timeframe.FIVE_MINUTE: 300,
            Timeframe.FIFTEEN_MINUTE: 900,
            Timeframe.THIRTY_MINUTE: 1800,
            Timeframe.ONE_HOUR: 3600,
            Timeframe.FOUR_HOUR: 14400,
            Timeframe.ONE_DAY: 86400,
            Timeframe.ONE_WEEK: 604800,
        }[timeframe]

        tolerance = pd.Timedelta(seconds=interval_seconds * 2)
        min_ts = df["timestamp"].min().to_pydatetime()
        max_ts = df["timestamp"].max().to_pydatetime()
        return min_ts <= start + tolerance and max_ts >= end - tolerance

    def save_to_file(
        self,
        filepath: str | Path,
        data: list[OHLCV],
        include_timestamp: bool = True,
    ) -> None:
        """Save OHLCV data to a CSV file.

        Args:
            filepath: Path to output file
            data: List of OHLCV candles
            include_timestamp: Whether to include timestamp column
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        records = [
            {
                "timestamp": d.timestamp.isoformat() if include_timestamp else None,
                "open": d.open,
                "high": d.high,
                "low": d.low,
                "close": d.close,
                "volume": d.volume,
            }
            for d in data
        ]
        df = pd.DataFrame(records)
        if not include_timestamp:
            df = df.drop(columns=["timestamp"])
        df.to_csv(path, index=False)
