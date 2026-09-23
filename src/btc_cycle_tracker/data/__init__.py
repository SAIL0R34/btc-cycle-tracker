"""Data module for BTC Swing Cycle Tracker.

Handles BTC OHLCV ingestion, normalization, source abstraction, and loading historical data.
"""

from .fetchers import BaseFetcher, CoinbaseFetcher, BinanceFetcher, KrakenFetcher
from .loaders import DataLoader
from .adapters import DataAdapter
from .normalization import normalize_ohlcv

__all__ = [
    "BaseFetcher",
    "CoinbaseFetcher",
    "BinanceFetcher",
    "KrakenFetcher",
    "DataLoader",
    "DataAdapter",
    "normalize_ohlcv",
]
