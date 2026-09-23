"""ZigZag-based pivot detection algorithm.

The detector is a classic reversal-threshold ZigZag implemented as a single
pass over the candles:

1. After the last confirmed pivot, track the running extreme of the current
   leg (highest high on an up leg, lowest low on a down leg).
2. Confirm that extreme as a pivot once price retraces from it by at least
   the reversal threshold.
3. Flip direction and continue.

The reversal threshold is ``max(min_move_pct, ATR% × atr_multiplier)`` when
the ATR filter is enabled, so the detector automatically demands bigger
reversals in high-volatility regimes and smaller ones in quiet tape. Because
a pivot is only emitted after a threshold reversal, pivots are true swing
extremes (not merely the first local fractal that passes a filter), they
alternate by construction, and each pivot carries the index of the candle
that confirmed it (``confirmation_candle_index``).
"""

from typing import Optional

from btc_cycle_tracker.models import OHLCV, PivotPoint, PivotType, Config
from btc_cycle_tracker.pivots.detector import BasePivotDetector


class ZigZagDetector(BasePivotDetector):
    """Pivot detector using a reversal-threshold ZigZag.

    Args:
        left_bars: Reserved for interface compatibility / metadata; the
            reversal-threshold algorithm does not require a confirmation
            window (the reversal itself is the confirmation).
        right_bars: See ``left_bars``.
        min_move_pct: Minimum reversal (percent) to confirm a pivot.
        use_atr_filter: Make the reversal threshold volatility-adaptive.
        atr_period: Period for ATR calculation.
        atr_multiplier: ATR multiples required for a reversal (in percent
            terms: threshold = ATR / price × 100 × multiplier).
        min_candles_between: Minimum candle gap between consecutive pivots.
        min_leg_duration_bars: Minimum bars for a valid leg.
    """

    def __init__(
        self,
        left_bars: int = 5,
        right_bars: int = 5,
        min_move_pct: float = 1.0,
        use_atr_filter: bool = True,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        min_candles_between: int = 3,
        min_leg_duration_bars: int = 2,
    ):
        super().__init__(left_bars, right_bars)
        self.min_move_pct = min_move_pct
        self.use_atr_filter = use_atr_filter
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.min_candles_between = min_candles_between
        self.min_leg_duration_bars = min_leg_duration_bars

    # ── Public API ─────────────────────────────────────────────────────

    def detect_pivots(self, data: list[OHLCV], config: Config) -> list[PivotPoint]:
        """Detect alternating swing pivots with a reversal-threshold pass."""
        if len(data) < max(self.left_bars + self.right_bars + 2, 3):
            return []

        atr_values = self._calculate_atr(data) if self.use_atr_filter else None
        gap_required = max(self.min_candles_between + 1, self.min_leg_duration_bars, 1)

        pivots: list[PivotPoint] = []
        # direction of the forming leg: "up" (last pivot = low) / "down" / None (seeding)
        direction: Optional[str] = None
        ext_high_idx, ext_high = 0, data[0].high
        ext_low_idx, ext_low = 0, data[0].low

        for i in range(1, len(data)):
            candle = data[i]
            if candle.high > ext_high:
                ext_high, ext_high_idx = candle.high, i
            if candle.low < ext_low:
                ext_low, ext_low_idx = candle.low, i

            spacing_from = pivots[-1].index if pivots else -(gap_required + 1)

            # A reversal must come from price action AFTER the extreme's own
            # bar — the extreme candle's opposite wick is not a reversal
            # (otherwise every wide-range bar would confirm its own extreme).
            down_retrace = (
                (ext_high - candle.low) / ext_high * 100
                if ext_high > 0 and ext_high_idx < i
                else 0.0
            )
            up_retrace = (
                (candle.high - ext_low) / ext_low * 100
                if ext_low > 0 and ext_low_idx < i
                else 0.0
            )

            if direction is None:
                # Seeding: confirm whichever extreme reverses first (larger
                # relative retrace wins if both trigger on the same candle).
                if max(down_retrace, up_retrace) > 0:
                    thr = self._reversal_threshold(
                        i, atr_values, ext_high if down_retrace >= up_retrace else ext_low
                    )
                    if max(down_retrace, up_retrace) >= thr:
                        if down_retrace >= up_retrace:
                            pivots.append(self._make_pivot(data, PivotType.SWING_HIGH, ext_high_idx, i))
                            direction = "down"
                        else:
                            pivots.append(self._make_pivot(data, PivotType.SWING_LOW, ext_low_idx, i))
                            direction = "up"
                        ext_high, ext_high_idx = candle.high, i
                        ext_low, ext_low_idx = candle.low, i
                continue

            if direction == "up":
                # Forming leg rises from a low; confirm the running high on a
                # sufficient downward retrace.
                if down_retrace > 0:
                    thr = self._reversal_threshold(i, atr_values, ext_high)
                    if down_retrace >= thr and ext_high_idx - spacing_from >= gap_required:
                        pivots.append(self._make_pivot(data, PivotType.SWING_HIGH, ext_high_idx, i))
                        direction = "down"
                        ext_low, ext_low_idx = candle.low, i
            else:
                # Forming leg falls from a high; confirm the running low on a
                # sufficient upward retrace.
                if up_retrace > 0:
                    thr = self._reversal_threshold(i, atr_values, ext_low)
                    if up_retrace >= thr and ext_low_idx - spacing_from >= gap_required:
                        pivots.append(self._make_pivot(data, PivotType.SWING_LOW, ext_low_idx, i))
                        direction = "up"
                        ext_high, ext_high_idx = candle.high, i

        return pivots

    # ── Internals ──────────────────────────────────────────────────────

    def _reversal_threshold(
        self,
        index: int,
        atr_values: Optional[list[Optional[float]]],
        reference_price: float,
    ) -> float:
        """Reversal threshold in percent, optionally ATR-adaptive."""
        threshold = self.min_move_pct
        if self.use_atr_filter and atr_values is not None and index < len(atr_values):
            atr = atr_values[index]
            if atr is not None and reference_price > 0:
                atr_pct = atr / reference_price * 100
                threshold = max(threshold, atr_pct * self.atr_multiplier)
        return threshold

    def _make_pivot(
        self,
        data: list[OHLCV],
        pivot_type: PivotType,
        extreme_index: int,
        confirm_index: int,
    ) -> PivotPoint:
        return PivotPoint(
            index=extreme_index,
            timestamp=data[extreme_index].timestamp,
            price=data[extreme_index].high if pivot_type == PivotType.SWING_HIGH else data[extreme_index].low,
            pivot_type=pivot_type,
            source_candle_index=extreme_index,
            confirmation_candle_index=confirm_index,
            left_bars=self.left_bars,
            right_bars=self.right_bars,
        )

    def _calculate_atr(self, data: list[OHLCV]) -> list[Optional[float]]:
        """Calculate simple ATR values (None until the period warms up)."""
        if len(data) < self.atr_period + 1:
            return [None] * len(data)

        tr_values = []
        for i in range(1, len(data)):
            high_low = data[i].high - data[i].low
            high_close = abs(data[i].high - data[i - 1].close)
            low_close = abs(data[i].low - data[i - 1].close)
            tr_values.append(max(high_low, high_close, low_close))

        atr_values: list[Optional[float]] = []
        for i in range(len(data)):
            if i <= self.atr_period:
                atr_values.append(None)
            else:
                window_tr = tr_values[i - self.atr_period - 1 : i - 1]
                atr_values.append(sum(window_tr) / len(window_tr))
        return atr_values
