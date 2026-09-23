"""Swing leg generation and metrics calculation."""

from datetime import datetime
from typing import Optional

from btc_cycle_tracker.models import PivotPoint, PivotType, SwingLeg


class LegBuilder:
    """Builds swing legs from pivot points with comprehensive metrics."""

    @staticmethod
    def build_legs(
        pivots: list[PivotPoint],
        data: list,
        start_pivot_id: int = 1,
        min_leg_change_pct: float = 0.0,
    ) -> list[SwingLeg]:
        """Build swing legs from pivot points.

        Args:
            pivots: List of pivot points (should alternate high/low)
            data: Full data series for reference
            start_pivot_id: Starting ID for pivot numbering
            min_leg_change_pct: Minimum percent change for a leg to be included

        Returns:
            List of swing legs with full metrics
        """
        if len(pivots) < 2:
            return []

        legs = []
        leg_id = 1

        for i in range(len(pivots) - 1):
            start_pivot = pivots[i]
            end_pivot = pivots[i + 1]

            leg = LegBuilder._build_leg(
                start=start_pivot,
                end=end_pivot,
                leg_id=leg_id,
                start_pivot_id=start_pivot_id + i,
                data=data,
            )
            if leg is not None:
                # Filter small legs
                if abs(leg.percent_change) >= min_leg_change_pct:
                    legs.append(leg)
                    leg_id += 1

        return legs

    @staticmethod
    def _build_leg(
        start: PivotPoint,
        end: PivotPoint,
        leg_id: int,
        start_pivot_id: int,
        data: list,
    ) -> Optional[SwingLeg]:
        """Build a single swing leg between two pivots.

        Args:
            start: Starting pivot point
            end: Ending pivot point
            leg_id: Unique leg identifier
            start_pivot_id: Starting pivot identifier
            data: Full data series

        Returns:
            Swing leg or None if invalid
        """
        if start.index >= end.index:
            return None

        price_change = end.price - start.price
        if price_change == 0:
            return None

        direction = "up" if price_change > 0 else "down"
        absolute_change = abs(price_change)
        percent_change = price_change / start.price * 100

        # Calculate duration
        duration_seconds = (end.timestamp - start.timestamp).total_seconds()
        duration_minutes = duration_seconds / 60
        duration_bars = end.index - start.index

        # Get start and end timestamps
        start_timestamp = start.timestamp
        end_timestamp = end.timestamp

        return SwingLeg(
            leg_id=leg_id,
            start_pivot_id=start_pivot_id,
            end_pivot_id=start_pivot_id + 1,
            direction=direction,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            start_price=start.price,
            end_price=end.price,
            absolute_change=absolute_change,
            percent_change=percent_change,
            duration_seconds=duration_seconds,
            duration_minutes=duration_minutes,
            duration_bars=duration_bars,
        )

    @staticmethod
    def build_forming_leg(
        pivots: list[PivotPoint],
        legs: list[SwingLeg],
        data: list,
    ) -> Optional[SwingLeg]:
        """Build the provisional leg from the last confirmed pivot to the
        latest close. This leg is still forming — it has no confirming
        reversal yet, so it must not be included in pattern history.
        """
        if not pivots or not data:
            return None

        last_pivot = pivots[-1]
        last_candle = data[-1]
        if last_candle.timestamp <= last_pivot.timestamp:
            return None

        price_change = float(last_candle.close) - last_pivot.price
        if price_change == 0:
            return None

        duration_seconds = (
            last_candle.timestamp - last_pivot.timestamp
        ).total_seconds()
        next_leg_id = (legs[-1].leg_id + 1) if legs else 1

        return SwingLeg(
            leg_id=next_leg_id,
            start_pivot_id=last_pivot.index,
            end_pivot_id=len(data) - 1,
            direction="up" if price_change > 0 else "down",
            start_timestamp=last_pivot.timestamp,
            end_timestamp=last_candle.timestamp,
            start_price=last_pivot.price,
            end_price=float(last_candle.close),
            absolute_change=abs(price_change),
            percent_change=price_change / last_pivot.price * 100,
            duration_seconds=duration_seconds,
            duration_minutes=duration_seconds / 60,
            duration_bars=len(data) - 1 - last_pivot.index,
        )

    @staticmethod
    def build_legs_from_pivots(
        pivots: list[PivotPoint],
        data: list,
        min_leg_change_pct: float = 0.0,
    ) -> list[SwingLeg]:
        """Build legs from pivots, ensuring proper alternation.

        Args:
            pivots: List of pivot points
            data: Full data series
            min_leg_change_pct: Minimum percent change for a leg to be included

        Returns:
            List of swing legs
        """
        # Filter to ensure alternation
        filtered_pivots = LegBuilder._ensure_alternation(pivots)

        return LegBuilder.build_legs(filtered_pivots, data, min_leg_change_pct=min_leg_change_pct)

    @staticmethod
    def _ensure_alternation(pivots: list[PivotPoint]) -> list[PivotPoint]:
        """Ensure pivots alternate between high and low.

        Args:
            pivots: List of pivot points

        Returns:
            List of alternating pivots
        """
        if len(pivots) <= 1:
            return pivots

        result = [pivots[0]]

        for pivot in pivots[1:]:
            last_pivot = result[-1]

            if pivot.pivot_type == last_pivot.pivot_type:
                if LegBuilder._is_more_extreme(pivot, last_pivot):
                    result[-1] = pivot
                continue

            if LegBuilder._forms_valid_reversal(last_pivot, pivot):
                result.append(pivot)

        return result

    @staticmethod
    def _is_more_extreme(candidate: PivotPoint, current: PivotPoint) -> bool:
        """Return True when a same-type pivot extends the current extreme."""
        if candidate.pivot_type == PivotType.SWING_HIGH:
            return candidate.price >= current.price
        return candidate.price <= current.price

    @staticmethod
    def _forms_valid_reversal(previous: PivotPoint, candidate: PivotPoint) -> bool:
        """Require opposite-type pivots to move in the expected reversal direction."""
        if previous.pivot_type == PivotType.SWING_HIGH:
            return candidate.price < previous.price
        return candidate.price > previous.price


def calculate_leg_metrics(legs: list[SwingLeg]) -> dict:
    """Calculate summary metrics for a list of legs.

    Args:
        legs: List of swing legs

    Returns:
        Dictionary of metrics
    """
    if not legs:
        return {
            "total_legs": 0,
            "avg_percent_change": 0.0,
            "avg_duration_minutes": 0.0,
            "avg_duration_bars": 0,
            "min_percent_change": 0.0,
            "max_percent_change": 0.0,
            "min_duration_minutes": 0.0,
            "max_duration_minutes": 0.0,
            "up_legs_count": 0,
            "down_legs_count": 0,
            "up_legs_total_change": 0.0,
            "down_legs_total_change": 0.0,
        }

    percent_changes = [leg.percent_change for leg in legs]
    durations_minutes = [leg.duration_minutes for leg in legs]
    durations_bars = [leg.duration_bars for leg in legs]

    up_legs = [leg for leg in legs if leg.is_up]
    down_legs = [leg for leg in legs if leg.is_down]

    up_legs_total_change = sum(leg.percent_change for leg in up_legs) if up_legs else 0.0
    down_legs_total_change = sum(leg.percent_change for leg in down_legs) if down_legs else 0.0

    return {
        "total_legs": len(legs),
        "avg_percent_change": sum(percent_changes) / len(percent_changes),
        "avg_duration_minutes": sum(durations_minutes) / len(durations_minutes),
        "avg_duration_bars": sum(durations_bars) / len(durations_bars),
        "min_percent_change": min(percent_changes),
        "max_percent_change": max(percent_changes),
        "min_duration_minutes": min(durations_minutes),
        "max_duration_minutes": max(durations_minutes),
        "up_legs_count": len(up_legs),
        "down_legs_count": len(down_legs),
        "up_legs_total_change": up_legs_total_change,
        "down_legs_total_change": down_legs_total_change,
        "up_legs_avg_change": sum(leg.percent_change for leg in up_legs) / len(up_legs) if up_legs else 0.0,
        "down_legs_avg_change": sum(leg.percent_change for leg in down_legs) / len(down_legs) if down_legs else 0.0,
        "up_legs_avg_duration": sum(leg.duration_minutes for leg in up_legs) / len(up_legs) if up_legs else 0.0,
        "down_legs_avg_duration": sum(leg.duration_minutes for leg in down_legs) / len(down_legs) if down_legs else 0.0,
    }
