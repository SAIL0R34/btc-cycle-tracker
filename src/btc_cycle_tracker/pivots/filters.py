"""Filters for noise reduction and pivot validation."""

import abc
from typing import Optional

import numpy as np

from btc_cycle_tracker.models import OHLCV, PivotPoint, PivotType, Config


class PivotFilter(abc.ABC):
    """Abstract base class for pivot filters."""

    @abc.abstractmethod
    def filter(self, pivots: list[PivotPoint], data: list[OHLCV]) -> list[PivotPoint]:
        """Filter pivot points.

        Args:
            pivots: List of pivot points
            data: Full data series

        Returns:
            Filtered list of pivot points
        """
        raise NotImplementedError


class NoiseFilter(PivotFilter):
    """Filter that removes pivots within a certain price range of each other."""

    def __init__(self, min_price_diff: float = 0.0):
        """Initialize the noise filter.

        Args:
            min_price_diff: Minimum price difference between pivots
        """
        self.min_price_diff = min_price_diff

    def filter(self, pivots: list[PivotPoint], data: list[OHLCV]) -> list[PivotPoint]:
        """Filter pivots that are too close in price.

        Args:
            pivots: List of pivot points
            data: Full data series

        Returns:
            Filtered list of pivot points
        """
        if len(pivots) <= 1:
            return pivots

        result = [pivots[0]]
        for pivot in pivots[1:]:
            last_pivot = result[-1]
            price_diff = abs(pivot.price - last_pivot.price)
            if price_diff >= self.min_price_diff:
                result.append(pivot)

        return result


class ATRFilter(PivotFilter):
    """Filter that validates pivots against ATR (Average True Range).

    Only keeps pivots where the price movement exceeds the ATR threshold.
    """

    def __init__(self, atr_period: int = 14, atr_multiplier: float = 1.5):
        """Initialize the ATR filter.

        Args:
            atr_period: Period for ATR calculation
            atr_multiplier: Multiplier for ATR threshold
        """
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier

    def filter(self, pivots: list[PivotPoint], data: list[OHLCV]) -> list[PivotPoint]:
        """Filter pivots based on ATR.

        Args:
            pivots: List of pivot points
            data: Full data series

        Returns:
            Filtered list of pivot points
        """
        if len(data) < self.atr_period + 1:
            return pivots

        # Calculate ATR
        atr_values = self._calculate_atr(data)

        if len(pivots) <= 1:
            return pivots

        result = [pivots[0]]
        for pivot in pivots[1:]:
            last_pivot = result[-1]
            price_diff = abs(pivot.price - last_pivot.price)

            # Get ATR at the pivot location
            atr_index = min(pivot.index, len(atr_values) - 1)
            atr = atr_values[atr_index] or 0

            # Only keep if price move exceeds ATR threshold
            if price_diff >= atr * self.atr_multiplier:
                result.append(pivot)

        return result

    def _calculate_atr(self, data: list[OHLCV]) -> list[Optional[float]]:
        """Calculate ATR values.

        Args:
            data: List of OHLCV candles

        Returns:
            List of ATR values
        """
        if len(data) < self.atr_period + 1:
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
            if i <= self.atr_period:
                atr_values.append(None)
            else:
                window_tr = tr_values[i - self.atr_period - 1 : i - 1]
                atr = sum(window_tr) / len(window_tr)
                atr_values.append(atr)

        return atr_values


class PercentChangeFilter(PivotFilter):
    """Filter that validates pivots based on minimum percentage change."""

    def __init__(self, min_pct_change: float = 1.0):
        """Initialize the percent change filter.

        Args:
            min_pct_change: Minimum percentage change required
        """
        self.min_pct_change = min_pct_change

    def filter(self, pivots: list[PivotPoint], data: list[OHLCV]) -> list[PivotPoint]:
        """Filter pivots based on minimum percentage change.

        Args:
            pivots: List of pivot points
            data: Full data series

        Returns:
            Filtered list of pivot points
        """
        if len(pivots) <= 1:
            return pivots

        result = [pivots[0]]
        for pivot in pivots[1:]:
            last_pivot = result[-1]
            if last_pivot.price != 0:
                pct_change = abs(pivot.price - last_pivot.price) / abs(last_pivot.price) * 100
                if pct_change >= self.min_pct_change:
                    result.append(pivot)

        return result


class ConsecutivePivotFilter(PivotFilter):
    """Filter that removes consecutive pivots of the same type."""

    def filter(self, pivots: list[PivotPoint], data: list[OHLCV]) -> list[PivotPoint]:
        """Remove consecutive pivots of the same type.

        Args:
            pivots: List of pivot points
            data: Full data series

        Returns:
            Filtered list of pivot points
        """
        if len(pivots) <= 1:
            return pivots

        result = [pivots[0]]
        for pivot in pivots[1:]:
            last_pivot = result[-1]
            if pivot.pivot_type != last_pivot.pivot_type:
                result.append(pivot)

        return result


def get_filter(filter_name: str, **kwargs) -> PivotFilter:
    """Factory function to get a filter by name.

    Args:
        filter_name: Name of the filter
        **kwargs: Filter parameters

    Returns:
        Filter instance

    Raises:
        ValueError: If filter name is not recognized
    """
    filters = {
        "noise": NoiseFilter,
        "atr": ATRFilter,
        "percent_change": PercentChangeFilter,
        "consecutive": ConsecutivePivotFilter,
    }

    if filter_name not in filters:
        raise ValueError(f"Unknown filter: {filter_name}")

    return filters[filter_name](**kwargs)
