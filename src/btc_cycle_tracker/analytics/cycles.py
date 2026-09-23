"""Cycle analyzer for identifying and analyzing price cycles."""

from typing import Optional

from btc_cycle_tracker.models import PivotPoint, SwingLeg


class CycleAnalyzer:
    """Analyzes swing cycles from pivot and leg data."""

    def __init__(self, min_legs_per_cycle: int = 2):
        """Initialize the cycle analyzer.

        Args:
            min_legs_per_cycle: Minimum legs to consider a complete cycle
        """
        self.min_legs_per_cycle = min_legs_per_cycle

    def identify_cycles(
        self,
        legs: list[SwingLeg],
    ) -> list[list[SwingLeg]]:
        """Identify complete cycles from legs.

        A cycle consists of an up leg followed by a down leg (or vice versa).

        Args:
            legs: List of swing legs

        Returns:
            List of cycles, where each cycle is a list of legs
        """
        if len(legs) < self.min_legs_per_cycle:
            return []

        cycles = []
        current_cycle: list[SwingLeg] = []

        for leg in legs:
            current_cycle.append(leg)

            # Check if we have a complete cycle
            if self._is_complete_cycle(current_cycle):
                cycles.append(current_cycle)
                current_cycle = []

        return cycles

    def _is_complete_cycle(self, legs: list[SwingLeg]) -> bool:
        """Check if a list of legs forms a complete cycle.

        Args:
            legs: List of legs to check

        Returns:
            True if the legs form a complete cycle
        """
        if len(legs) < self.min_legs_per_cycle:
            return False

        # Check for alternation
        for i in range(len(legs) - 1):
            if legs[i].direction == legs[i + 1].direction:
                return False

        return True

    def calculate_cycle_metrics(
        self,
        cycles: list[list[SwingLeg]],
    ) -> list[dict]:
        """Calculate metrics for each cycle.

        Args:
            cycles: List of cycles

        Returns:
            List of cycle metrics dictionaries
        """
        metrics = []
        for i, cycle in enumerate(cycles):
            total_pct_change = sum(leg.percent_change for leg in cycle)
            total_duration = sum(leg.duration_seconds for leg in cycle)

            metrics.append({
                "cycle_index": i,
                "num_legs": len(cycle),
                "total_percent_change": total_pct_change,
                "total_duration_seconds": total_duration,
                "legs": cycle,
            })

        return metrics

    def analyze_cycle_patterns(
        self,
        legs: list[SwingLeg],
    ) -> dict:
        """Analyze cycle patterns in the data.

        Args:
            legs: List of swing legs

        Returns:
            Dictionary of pattern analysis results
        """
        cycles = self.identify_cycles(legs)
        cycle_metrics = self.calculate_cycle_metrics(cycles)

        if not cycle_metrics:
            return {
                "total_cycles": 0,
                "avg_cycle_duration": 0,
                "avg_cycle_percent_change": 0,
                "cycle_duration_std": 0,
                "cycle_change_std": 0,
            }

        durations = [m["total_duration_seconds"] for m in cycle_metrics]
        changes = [m["total_percent_change"] for m in cycle_metrics]

        return {
            "total_cycles": len(cycles),
            "avg_cycle_duration": sum(durations) / len(durations),
            "avg_cycle_percent_change": sum(changes) / len(changes),
            "min_cycle_duration": min(durations),
            "max_cycle_duration": max(durations),
            "min_cycle_change": min(changes),
            "max_cycle_change": max(changes),
        }

    def find_incomplete_cycle(
        self,
        legs: list[SwingLeg],
    ) -> Optional[list[SwingLeg]]:
        """Find an incomplete cycle at the end of the data.

        Args:
            legs: List of swing legs

        Returns:
            Incomplete cycle or None if complete
        """
        if not legs:
            return None

        # Start from the end and work backwards
        incomplete = []
        for leg in reversed(legs):
            incomplete.insert(0, leg)
            if self._is_complete_cycle(incomplete):
                return None  # Complete cycle found

        return incomplete if len(incomplete) >= 1 else None
