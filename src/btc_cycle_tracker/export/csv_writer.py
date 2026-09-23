"""CSV export functionality for pivot and leg data with analysis-friendly schemas."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from btc_cycle_tracker.models import OHLCV, PivotPoint, SwingLeg, AnalysisResult
from btc_cycle_tracker.settings import settings


class CSVWriter:
    """Writes analysis results to CSV files with clean schemas."""

    def __init__(
        self,
        output_dir: str = "outputs",
        decimal_places: int = 2,
        timestamp_format: str = "%Y-%m-%d %H:%M:%S",
    ):
        """Initialize the CSV writer.

        Args:
            output_dir: Output directory for CSV files
            decimal_places: Number of decimal places for numeric values
            timestamp_format: Format string for timestamps
        """
        self.output_dir = settings.resolve_app_path(output_dir)
        self.decimal_places = decimal_places
        self.timestamp_format = timestamp_format

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_pivots(
        self,
        pivots: list[PivotPoint],
        filename: Optional[str] = None,
    ) -> Path:
        """Write pivot points to CSV with analysis-friendly schema.

        Schema:
        - pivot_id: Sequential identifier
        - timestamp: Pivot timestamp
        - pivot_type: swing_high or swing_low
        - price: Pivot price
        - confirmation_timestamp: When pivot was confirmed
        - detection_method: Method used (zigzag, fractal, etc.)
        - confidence: Confidence score (based on bar count)
        - left_bars: Bars checked on left
        - right_bars: Bars checked on right
        - source_candle_index: Index in original data
        - price_level: High or Low price used for pivot
        - pivot_rank: Rank of pivot (1 = most extreme, 2 = second most extreme, etc.)
        - prev_pivot_price: Price of previous pivot (for change calculation)
        - prev_pivot_type: Type of previous pivot

        Args:
            pivots: List of pivot points
            filename: Output filename (auto-generated if None)

        Returns:
            Path to the created file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pivots_{timestamp}.csv"

        filepath = self.output_dir / filename

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "pivot_id",
                "timestamp",
                "pivot_type",
                "price",
                "confirmation_timestamp",
                "detection_method",
                "confidence",
                "left_bars",
                "right_bars",
                "source_candle_index",
                "price_level",
                "pivot_rank",
                "prev_pivot_price",
                "prev_pivot_type",
            ])

            for i, pivot in enumerate(pivots, start=1):
                # Calculate confidence based on bar count and price level
                total_bars = pivot.left_bars + pivot.right_bars
                confidence = min(100, (total_bars / 10) * 50) if total_bars > 0 else 50

                # Determine price level (high for swing_high, low for swing_low)
                price_level = pivot.price

                # Calculate pivot rank (based on extremity within the series)
                pivot_rank = self._calculate_pivot_rank(pivot, pivots)

                # Get previous pivot info
                prev_pivot_price = pivots[i - 2].price if i >= 2 else None
                prev_pivot_type = pivots[i - 2].pivot_type if i >= 2 else None

                writer.writerow([
                    i,
                    pivot.timestamp.strftime(self.timestamp_format),
                    pivot.pivot_type,
                    round(pivot.price, self.decimal_places),
                    pivot.timestamp.strftime(self.timestamp_format),
                    "zigzag",
                    round(confidence, 1),
                    pivot.left_bars,
                    pivot.right_bars,
                    pivot.source_candle_index,
                    round(price_level, self.decimal_places),
                    pivot_rank,
                    round(prev_pivot_price, self.decimal_places) if prev_pivot_price else "",
                    prev_pivot_type,
                ])

        return filepath

    def _calculate_pivot_rank(self, pivot: PivotPoint, all_pivots: list[PivotPoint]) -> int:
        """Calculate the rank of a pivot based on its extremity.

        Args:
            pivot: The pivot to rank
            all_pivots: All pivots in the series

        Returns:
            Rank (1 = most extreme, higher = less extreme)
        """
        if not all_pivots:
            return 1

        if pivot.pivot_type == "swing_high":
            # Higher prices are more extreme
            sorted_pivots = sorted(all_pivots, key=lambda p: p.price, reverse=True)
        else:
            # Lower prices are more extreme
            sorted_pivots = sorted(all_pivots, key=lambda p: p.price)

        try:
            return sorted_pivots.index(pivot) + 1
        except ValueError:
            return 1

    def write_legs(
        self,
        legs: list[SwingLeg],
        filename: Optional[str] = None,
    ) -> Path:
        """Write swing legs to CSV with analysis-friendly schema.

        Schema:
        - leg_id: Sequential identifier
        - start_pivot_id: ID of starting pivot
        - end_pivot_id: ID of ending pivot
        - direction: up or down
        - start_time: Leg start timestamp
        - end_time: Leg end timestamp
        - start_price: Leg start price
        - end_price: Leg end price
        - absolute_change: Absolute price change
        - percent_change: Percentage change
        - duration_minutes: Duration in minutes
        - candle_count: Number of candles in leg
        - start_pivot_type: Type of starting pivot
        - end_pivot_type: Type of ending pivot
        - leg_rank: Rank of leg by percent change
        - is_major_move: Whether this leg exceeds the 2% threshold
        - price_at_leg_start: Price at start of leg (for context)
        - price_at_leg_end: Price at end of leg (for context)

        Args:
            legs: List of swing legs
            filename: Output filename (auto-generated if None)

        Returns:
            Path to the created file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"swing_legs_{timestamp}.csv"

        filepath = self.output_dir / filename

        # Calculate leg ranks
        sorted_legs = sorted(legs, key=lambda l: abs(l.percent_change), reverse=True)
        leg_ranks = {leg.leg_id: i + 1 for i, leg in enumerate(sorted_legs)}

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "leg_id",
                "start_pivot_id",
                "end_pivot_id",
                "direction",
                "start_time",
                "end_time",
                "start_price",
                "end_price",
                "absolute_change",
                "percent_change",
                "duration_minutes",
                "candle_count",
                "start_pivot_type",
                "end_pivot_type",
                "leg_rank",
                "is_major_move",
                "price_at_leg_start",
                "price_at_leg_end",
            ])

            for leg in legs:
                # Determine pivot types based on direction
                start_pivot_type = "swing_high" if leg.direction == "down" else "swing_low"
                end_pivot_type = "swing_low" if leg.direction == "down" else "swing_high"

                writer.writerow([
                    leg.leg_id,
                    leg.start_pivot_id,
                    leg.end_pivot_id,
                    leg.direction,
                    leg.start_timestamp.strftime(self.timestamp_format),
                    leg.end_timestamp.strftime(self.timestamp_format),
                    round(leg.start_price, self.decimal_places),
                    round(leg.end_price, self.decimal_places),
                    round(leg.absolute_change, self.decimal_places),
                    round(leg.percent_change, self.decimal_places),
                    round(leg.duration_minutes, 2),
                    leg.duration_bars,
                    start_pivot_type,
                    end_pivot_type,
                    leg_ranks.get(leg.leg_id, 0),
                    "yes" if abs(leg.percent_change) >= 2.0 else "no",
                    round(leg.start_price, self.decimal_places),
                    round(leg.end_price, self.decimal_places),
                ])

        return filepath

    def write_raw_data(
        self,
        data: list[OHLCV],
        filename: Optional[str] = None,
    ) -> Path:
        """Write raw OHLCV data to CSV.

        Args:
            data: List of OHLCV candles
            filename: Output filename (auto-generated if None)

        Returns:
            Path to the created file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"raw_data_{timestamp}.csv"

        filepath = self.output_dir / filename

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ])

            for candle in data:
                writer.writerow([
                    candle.timestamp.strftime(self.timestamp_format),
                    round(candle.open, self.decimal_places),
                    round(candle.high, self.decimal_places),
                    round(candle.low, self.decimal_places),
                    round(candle.close, self.decimal_places),
                    round(candle.volume, self.decimal_places),
                ])

        return filepath

    def write_analysis_result(
        self,
        result: AnalysisResult,
        include_raw_data: bool = False,
    ) -> dict[str, Path]:
        """Write complete analysis result to CSV files.

        Args:
            result: AnalysisResult object
            include_raw_data: Whether to include raw OHLCV data

        Returns:
            Dictionary mapping file type to file path
        """
        files = {}

        # Write pivots
        files["pivots"] = self.write_pivots(result.pivots)

        # Write legs
        files["legs"] = self.write_legs(result.legs)

        # Write raw data if requested
        if include_raw_data:
            files["raw_data"] = self.write_raw_data(result.raw_data)

        files["summary"] = self.write_summary(result)

        if result.pattern_insight:
            files["pattern_matches"] = self.write_pattern_matches(result)

        if result.pattern_backtests:
            files["pattern_backtests"] = self.write_pattern_backtests(result)

        return files

    def write_summary(
        self,
        result: AnalysisResult,
        filename: Optional[str] = None,
    ) -> Path:
        """Write summary statistics to CSV.

        Args:
            result: AnalysisResult object
            filename: Output filename (auto-generated if None)

        Returns:
            Path to the created file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"summary_{timestamp}.csv"

        filepath = self.output_dir / filename

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value"])
            writer.writerow(["total_legs", result.metadata.total_legs])
            writer.writerow(["avg_percent_change", round(result.summary.avg_percent_change, self.decimal_places)])
            writer.writerow(["median_percent_change", round(result.summary.median_percent_change, self.decimal_places)])
            writer.writerow(["avg_duration_minutes", round(result.summary.avg_duration_minutes, 2)])
            writer.writerow(["min_percent_change", round(result.summary.min_percent_change, self.decimal_places)])
            writer.writerow(["max_percent_change", round(result.summary.max_percent_change, self.decimal_places)])
            writer.writerow(["up_legs_count", result.summary.up_legs_count])
            writer.writerow(["down_legs_count", result.summary.down_legs_count])
            writer.writerow(["up_legs_total_change", round(result.summary.up_legs_total_change, self.decimal_places)])
            writer.writerow(["down_legs_total_change", round(result.summary.down_legs_total_change, self.decimal_places)])
            writer.writerow(["up_legs_avg_change", round(result.summary.up_legs_avg_change or 0, self.decimal_places)])
            writer.writerow(["down_legs_avg_change", round(result.summary.down_legs_avg_change or 0, self.decimal_places)])
            writer.writerow(["up_down_ratio", round(result.summary.up_legs_count / max(result.summary.down_legs_count, 1), 2)])
            writer.writerow(["up_down_asymmetry", round(result.summary.up_down_asymmetry, 2)])
            writer.writerow(["amplitude_duration_correlation", round(result.summary.amplitude_duration_correlation, 2)])

        return filepath

    def write_pattern_matches(
        self,
        result: AnalysisResult,
        filename: Optional[str] = None,
    ) -> Path:
        """Write pattern analog matches to CSV."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pattern_matches_{timestamp}.csv"

        filepath = self.output_dir / filename
        insight = result.pattern_insight

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "pattern_signature",
                "anchor_leg_id",
                "similarity_score",
                "next_direction",
                "next_change_pct",
                "next_duration_bars",
                "horizon_change_pct",
                "horizon_direction",
            ])
            if insight:
                for match in insight.matches:
                    writer.writerow([
                        insight.pattern_signature,
                        match.anchor_leg_id,
                        round(match.similarity_score, 4),
                        match.next_direction,
                        round(match.next_change_pct, self.decimal_places),
                        match.next_duration_bars,
                        round(match.horizon_change_pct, self.decimal_places),
                        match.horizon_direction,
                    ])

        return filepath

    def write_pattern_backtests(
        self,
        result: AnalysisResult,
        filename: Optional[str] = None,
    ) -> Path:
        """Write walk-forward pattern validation records to CSV."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pattern_backtests_{timestamp}.csv"

        filepath = self.output_dir / filename

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "anchor_leg_id",
                "pattern_signature",
                "predicted_direction",
                "actual_direction",
                "predicted_horizon_direction",
                "actual_horizon_direction",
                "confidence_score",
                "adaptive_confidence",
                "was_direction_correct",
                "did_horizon_hold",
                "realized_next_change_pct",
                "realized_horizon_change_pct",
            ])
            for record in result.pattern_backtests:
                writer.writerow([
                    record.anchor_leg_id,
                    record.pattern_signature,
                    record.predicted_direction,
                    record.actual_direction,
                    record.predicted_horizon_direction,
                    record.actual_horizon_direction,
                    round(record.confidence_score, 4),
                    round(record.adaptive_confidence, 4),
                    record.was_direction_correct,
                    record.did_horizon_hold,
                    round(record.realized_next_change_pct, self.decimal_places),
                    round(record.realized_horizon_change_pct, self.decimal_places),
                ])

        return filepath
