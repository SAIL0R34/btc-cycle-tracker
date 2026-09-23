"""Fractal-based pivot detection algorithm.

Fractals identify pivot points by looking for patterns where price reverses
after reaching a local extremum.
"""

from btc_cycle_tracker.models import OHLCV, PivotPoint, PivotType, Config
from btc_cycle_tracker.pivots.detector import BasePivotDetector


class FractalDetector(BasePivotDetector):
    """Pivot detector using fractal patterns.

    A fractal high forms when a candle's high is higher than the highs
    of the N candles before and after it.
    A fractal low forms when a candle's low is lower than the lows
    of the N candles before and after it.
    """

    def __init__(
        self,
        left_bars: int = 2,
        right_bars: int = 2,
        min_move_pct: float = 0.0,
    ):
        """Initialize the fractal detector.

        Args:
            left_bars: Number of bars to check on the left (default 2)
            right_bars: Number of bars to check on the right (default 2)
            min_move_pct: Minimum percentage move (0 = no filter)
        """
        super().__init__(left_bars, right_bars)
        self.min_move_pct = min_move_pct

    def detect_pivots(self, data: list[OHLCV], config: Config) -> list[PivotPoint]:
        """Detect pivots using fractal patterns.

        Args:
            data: List of OHLCV candles
            config: Configuration for pivot detection

        Returns:
            List of detected pivot points
        """
        if len(data) < self.left_bars + self.right_bars + 1:
            return []

        pivots: list[PivotPoint] = []

        # Find all fractals
        for i in range(self.left_bars, len(data) - self.right_bars):
            candle = data[i]

            # Check for fractal high
            if self._is_fractal_high(i, data):
                pivots.append(
                    PivotPoint(
                        index=i,
                        timestamp=candle.timestamp,
                        price=candle.high,
                        pivot_type=PivotType.SWING_HIGH,
                        source_candle_index=i,
                        left_bars=self.left_bars,
                        right_bars=self.right_bars,
                    )
                )

            # Check for fractal low
            if self._is_fractal_low(i, data):
                pivots.append(
                    PivotPoint(
                        index=i,
                        timestamp=candle.timestamp,
                        price=candle.low,
                        pivot_type=PivotType.SWING_LOW,
                        source_candle_index=i,
                        left_bars=self.left_bars,
                        right_bars=self.right_bars,
                    )
                )

        # Filter by minimum move if specified
        if self.min_move_pct > 0:
            pivots = self._filter_by_min_move(pivots, data)

        # Ensure alternation
        pivots = self._ensure_alternation(pivots)

        return pivots

    def _is_fractal_high(self, index: int, data: list[OHLCV]) -> bool:
        """Check if a candle forms a fractal high.

        Args:
            index: Index of the candle
            data: Full data series

        Returns:
            True if the candle forms a fractal high
        """
        if index < self.left_bars or index + self.right_bars >= len(data):
            return False

        price = data[index].high

        # Check left side
        for i in range(index - self.left_bars, index):
            if data[i].high >= price:
                return False

        # Check right side
        for i in range(index + 1, index + self.right_bars + 1):
            if data[i].high >= price:
                return False

        return True

    def _is_fractal_low(self, index: int, data: list[OHLCV]) -> bool:
        """Check if a candle forms a fractal low.

        Args:
            index: Index of the candle
            data: Full data series

        Returns:
            True if the candle forms a fractal low
        """
        if index < self.left_bars or index + self.right_bars >= len(data):
            return False

        price = data[index].low

        # Check left side
        for i in range(index - self.left_bars, index):
            if data[i].low <= price:
                return False

        # Check right side
        for i in range(index + 1, index + self.right_bars + 1):
            if data[i].low <= price:
                return False

        return True

    def _filter_by_min_move(
        self,
        pivots: list[PivotPoint],
        data: list[OHLCV],
    ) -> list[PivotPoint]:
        """Filter pivots by minimum percentage move.

        Args:
            pivots: List of pivot points
            data: Full data series

        Returns:
            Filtered list of pivot points
        """
        if len(pivots) < 2:
            return pivots

        result = [pivots[0]]
        for i in range(1, len(pivots)):
            prev_pivot = result[-1]
            curr_pivot = pivots[i]

            # Get the price to compare against
            if curr_pivot.pivot_type == PivotType.SWING_HIGH:
                compare_price = prev_pivot.price
                pct_change = (curr_pivot.price - compare_price) / compare_price * 100
            else:
                compare_price = prev_pivot.price
                pct_change = (compare_price - curr_pivot.price) / compare_price * 100

            if abs(pct_change) >= self.min_move_pct:
                result.append(curr_pivot)

        return result
