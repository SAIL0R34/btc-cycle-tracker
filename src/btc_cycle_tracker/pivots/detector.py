"""Base pivot detector interface and common functionality."""

import abc
from typing import Optional

from btc_cycle_tracker.models import OHLCV, PivotPoint, PivotType, Config


class PivotDetector(abc.ABC):
    """Abstract base class for pivot detection algorithms."""

    @abc.abstractmethod
    def detect_pivots(self, data: list[OHLCV], config: Config) -> list[PivotPoint]:
        """Detect pivot points in the given data.

        Args:
            data: List of OHLCV candles
            config: Configuration for pivot detection

        Returns:
            List of detected pivot points
        """
        raise NotImplementedError

    def _validate_pivot(
        self,
        index: int,
        price: float,
        pivot_type: PivotType,
        data: list[OHLCV],
        left_bars: int,
        right_bars: int,
    ) -> bool:
        """Validate that a pivot point meets the criteria.

        Args:
            index: Index of the pivot candle
            price: Pivot price
            pivot_type: Type of pivot (high or low)
            data: Full data series
            left_bars: Number of bars to check on the left
            right_bars: Number of bars to check on the right

        Returns:
            True if the pivot is valid
        """
        # Check we have enough data on both sides
        if index < left_bars or index + right_bars >= len(data):
            return False

        # Check left side
        for i in range(index - left_bars, index):
            if pivot_type == PivotType.SWING_HIGH:
                if data[i].high >= price:
                    return False
            else:  # SWING_LOW
                if data[i].low <= price:
                    return False

        # Check right side
        for i in range(index + 1, index + right_bars + 1):
            if pivot_type == PivotType.SWING_HIGH:
                if data[i].high >= price:
                    return False
            else:  # SWING_LOW
                if data[i].low <= price:
                    return False

        return True

    def _filter_consecutive_pivots(
        self,
        pivots: list[PivotPoint],
        min_distance: int = 1,
    ) -> list[PivotPoint]:
        """Filter out pivots that are too close together.

        Args:
            pivots: List of pivot points
            min_distance: Minimum distance between pivots (in bars)

        Returns:
            Filtered list of pivot points
        """
        if len(pivots) <= 1:
            return pivots

        result = [pivots[0]]
        for pivot in pivots[1:]:
            last_pivot = result[-1]
            if abs(pivot.index - last_pivot.index) >= min_distance:
                result.append(pivot)

        return result

    def _ensure_alternation(
        self,
        pivots: list[PivotPoint],
    ) -> list[PivotPoint]:
        """Ensure pivots alternate between high and low.

        Args:
            pivots: List of pivot points

        Returns:
            List of alternating pivots
        """
        if len(pivots) <= 1:
            return pivots

        result = [pivots[0]]
        expected_type = (
            PivotType.SWING_LOW
            if pivots[0].pivot_type == PivotType.SWING_HIGH
            else PivotType.SWING_HIGH
        )

        for pivot in pivots[1:]:
            if pivot.pivot_type == expected_type:
                result.append(pivot)
                expected_type = (
                    PivotType.SWING_LOW
                    if pivot.pivot_type == PivotType.SWING_HIGH
                    else PivotType.SWING_HIGH
                )

        return result


class BasePivotDetector(PivotDetector):
    """Base implementation with common functionality."""

    def __init__(self, left_bars: int = 5, right_bars: int = 5):
        """Initialize the base detector.

        Args:
            left_bars: Number of bars to check on the left
            right_bars: Number of bars to check on the right
        """
        self.left_bars = left_bars
        self.right_bars = right_bars
