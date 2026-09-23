"""Data adapters for converting between different data formats."""

from typing import Any

import pandas as pd

from btc_cycle_tracker.models import OHLCV


class DataAdapter:
    """Adapter for converting between different data formats."""

    @staticmethod
    def to_ohlcv(df: pd.DataFrame) -> list[OHLCV]:
        """Convert a pandas DataFrame to OHLCV objects.

        Args:
            df: DataFrame with columns: timestamp, open, high, low, close, volume

        Returns:
            List of OHLCV objects
        """
        records = df.to_dict("records")
        return [OHLCV(**row) for row in records]

    @staticmethod
    def from_ohlcv(ohlcv: list[OHLCV]) -> pd.DataFrame:
        """Convert OHLCV objects to a pandas DataFrame.

        Args:
            ohlcv: List of OHLCV objects

        Returns:
            DataFrame with OHLCV data
        """
        records = [
            {
                "timestamp": d.timestamp,
                "open": d.open,
                "high": d.high,
                "low": d.low,
                "close": d.close,
                "volume": d.volume,
            }
            for d in ohlcv
        ]
        return pd.DataFrame(records)

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to standard format.

        Args:
            df: DataFrame with potentially non-standard column names

        Returns:
            DataFrame with normalized column names
        """
        column_map = {
            "date": "timestamp",
            "datetime": "timestamp",
            "time": "timestamp",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "vol": "volume",
            "amount": "volume",
        }

        df = df.copy()
        df.columns = df.columns.str.lower().str.replace(" ", "_")

        rename_map = {}
        for col in df.columns:
            if col in column_map:
                rename_map[col] = column_map[col]

        return df.rename(columns=rename_map)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> OHLCV:
        """Create an OHLCV object from a dictionary.

        Args:
            data: Dictionary with OHLCV data

        Returns:
            OHLCV object
        """
        return OHLCV(**data)

    @staticmethod
    def to_dict(ohlcv: OHLCV) -> dict[str, Any]:
        """Convert an OHLCV object to a dictionary.

        Args:
            ohlcv: OHLCV object

        Returns:
            Dictionary with OHLCV data
        """
        return ohlcv.model_dump()
