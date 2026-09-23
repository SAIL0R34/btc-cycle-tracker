"""Pivot confirmation logic for validating swing points."""

from btc_cycle_tracker.models import OHLCV, PivotPoint, PivotType, Config


class PivotConfirmation:
    """Handles confirmation of pivot points after initial detection."""

    @staticmethod
    def confirm_pivot(
        pivot: PivotPoint,
        data: list[OHLCV],
        confirmation_bars: int = 3,
    ) -> bool:
        """Confirm that a pivot point is valid.

        A pivot is confirmed if the price moves in the opposite direction
        by a certain amount after the pivot.

        Args:
            pivot: The pivot point to confirm
            data: Full data series
            confirmation_bars: Number of bars to check for confirmation

        Returns:
            True if the pivot is confirmed
        """
        if pivot.index + confirmation_bars >= len(data):
            return False

        # Check if price moved in the expected direction
        if pivot.pivot_type == PivotType.SWING_HIGH:
            # After a swing high, price should move down
            start_price = pivot.price
            end_price = data[pivot.index + confirmation_bars].low
            return end_price < start_price

        else:  # SWING_LOW
            # After a swing low, price should move up
            start_price = pivot.price
            end_price = data[pivot.index + confirmation_bars].high
            return end_price > start_price

    @staticmethod
    def confirm_pivots(
        pivots: list[PivotPoint],
        data: list[OHLCV],
        confirmation_bars: int = 3,
    ) -> list[PivotPoint]:
        """Confirm multiple pivot points.

        Args:
            pivots: List of pivot points
            data: Full data series
            confirmation_bars: Number of bars to check for confirmation

        Returns:
            List of confirmed pivot points
        """
        return [
            pivot
            for pivot in pivots
            if PivotConfirmation.confirm_pivot(pivot, data, confirmation_bars)
        ]

    @staticmethod
    def validate_alternation(
        pivots: list[PivotPoint],
    ) -> list[PivotPoint]:
        """Validate that pivots alternate between high and low.

        Args:
            pivots: List of pivot points

        Returns:
            List of pivots with proper alternation
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

    @staticmethod
    def validate_min_move(
        pivots: list[PivotPoint],
        data: list[OHLCV],
        min_pct_change: float = 1.0,
    ) -> list[PivotPoint]:
        """Validate that pivots have minimum percentage change.

        Args:
            pivots: List of pivot points
            data: Full data series
            min_pct_change: Minimum percentage change required

        Returns:
            List of pivots with sufficient price movement
        """
        if len(pivots) <= 1:
            return pivots

        result = [pivots[0]]
        for pivot in pivots[1:]:
            last_pivot = result[-1]
            if last_pivot.price != 0:
                pct_change = abs(pivot.price - last_pivot.price) / abs(last_pivot.price) * 100
                if pct_change >= min_pct_change:
                    result.append(pivot)

        return result


def confirm_pivots(
    pivots: list[PivotPoint],
    data: list[OHLCV],
    config: Config,
) -> list[PivotPoint]:
    """Confirm pivots using configuration settings.

    Args:
        pivots: List of pivot points
        data: Full data series
        config: Configuration for confirmation

    Returns:
        List of confirmed pivot points
    """
    if not pivots:
        return []

    # Apply confirmation
    confirmed = PivotConfirmation.confirm_pivots(
        pivots,
        data,
        confirmation_bars=3,
    )

    # Validate alternation
    confirmed = PivotConfirmation.validate_alternation(confirmed)

    # Validate minimum move
    confirmed = PivotConfirmation.validate_min_move(
        confirmed,
        data,
        min_pct_change=config.min_move_pct,
    )

    return confirmed
