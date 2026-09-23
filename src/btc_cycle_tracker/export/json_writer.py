"""JSON export functionality for analysis results."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from btc_cycle_tracker.models import OHLCV, PivotPoint, SwingLeg, AnalysisResult
from btc_cycle_tracker.settings import settings


class JSONWriter:
    """Writes analysis results to JSON files."""

    def __init__(
        self,
        output_dir: str = "outputs",
    ):
        """Initialize the JSON writer.

        Args:
            output_dir: Output directory for JSON files
        """
        self.output_dir = settings.resolve_app_path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_pivots(
        self,
        pivots: list[PivotPoint],
        filename: Optional[str] = None,
    ) -> Path:
        """Write pivot points to JSON.

        Args:
            pivots: List of pivot points
            filename: Output filename (auto-generated if None)

        Returns:
            Path to the created file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pivots_{timestamp}.json"

        filepath = self.output_dir / filename

        data = {
            "pivots": [
                {
                    "index": p.index,
                    "timestamp": p.timestamp.isoformat(),
                    "price": p.price,
                    "pivot_type": p.pivot_type,
                    "source_candle_index": p.source_candle_index,
                    "left_bars": p.left_bars,
                    "right_bars": p.right_bars,
                }
                for p in pivots
            ]
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        return filepath

    def write_legs(
        self,
        legs: list[SwingLeg],
        filename: Optional[str] = None,
    ) -> Path:
        """Write swing legs to JSON.

        Args:
            legs: List of swing legs
            filename: Output filename (auto-generated if None)

        Returns:
            Path to the created file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"legs_{timestamp}.json"

        filepath = self.output_dir / filename

        data = {
            "legs": [
                {
                    "start_pivot": {
                        "index": l.start_pivot.index,
                        "timestamp": l.start_pivot.timestamp.isoformat(),
                        "price": l.start_pivot.price,
                        "pivot_type": l.start_pivot.pivot_type,
                    },
                    "end_pivot": {
                        "index": l.end_pivot.index,
                        "timestamp": l.end_pivot.timestamp.isoformat(),
                        "price": l.end_pivot.price,
                        "pivot_type": l.end_pivot.pivot_type,
                    },
                    "percent_change": l.percent_change,
                    "duration_seconds": l.duration_seconds,
                    "duration_bars": l.duration_bars,
                    "direction": l.direction,
                }
                for l in legs
            ]
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        return filepath

    def write_analysis_result(
        self,
        result: AnalysisResult,
        filename: Optional[str] = None,
    ) -> Path:
        """Write complete analysis result to JSON.

        Args:
            result: AnalysisResult object
            filename: Output filename (auto-generated if None)

        Returns:
            Path to the created file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"analysis_{timestamp}.json"

        filepath = self.output_dir / filename

        data = {
            "metadata": {
                "symbol": result.metadata.symbol,
                "timeframe": result.metadata.timeframe,
                "pivot_method": result.metadata.pivot_method,
                "start_date": result.metadata.start_date.isoformat(),
                "end_date": result.metadata.end_date.isoformat(),
                "total_candles": result.metadata.total_candles,
                "total_pivots": result.metadata.total_pivots,
                "total_legs": result.metadata.total_legs,
                "run_timestamp": result.metadata.run_timestamp.isoformat(),
                "config_hash": result.metadata.config_hash,
            },
            "pivots": [
                {
                    "index": p.index,
                    "timestamp": p.timestamp.isoformat(),
                    "price": p.price,
                    "pivot_type": p.pivot_type,
                    "source_candle_index": p.source_candle_index,
                    "left_bars": p.left_bars,
                    "right_bars": p.right_bars,
                }
                for p in result.pivots
            ],
            "legs": [
                {
                    "start_pivot": {
                        "index": l.start_pivot.index,
                        "timestamp": l.start_pivot.timestamp.isoformat(),
                        "price": l.start_pivot.price,
                        "pivot_type": l.start_pivot.pivot_type,
                    },
                    "end_pivot": {
                        "index": l.end_pivot.index,
                        "timestamp": l.end_pivot.timestamp.isoformat(),
                        "price": l.end_pivot.price,
                        "pivot_type": l.end_pivot.pivot_type,
                    },
                    "percent_change": l.percent_change,
                    "duration_seconds": l.duration_seconds,
                    "duration_bars": l.duration_bars,
                    "direction": l.direction,
                }
                for l in result.legs
            ],
            "summary": {
                "total_legs": result.summary.total_legs,
                "avg_percent_change": result.summary.avg_percent_change,
                "avg_duration_minutes": result.summary.avg_duration_minutes,
                "avg_duration_bars": result.summary.avg_duration_bars,
                "min_percent_change": result.summary.min_percent_change,
                "max_percent_change": result.summary.max_percent_change,
                "min_duration_minutes": result.summary.min_duration_minutes,
                "max_duration_minutes": result.summary.max_duration_minutes,
                "up_legs_count": result.summary.up_legs_count,
                "down_legs_count": result.summary.down_legs_count,
                "up_legs_avg_change": result.summary.up_legs_avg_change,
                "down_legs_avg_change": result.summary.down_legs_avg_change,
                "up_legs_avg_duration": result.summary.up_legs_avg_duration,
                "down_legs_avg_duration": result.summary.down_legs_avg_duration,
            },
            "pattern_insight": (
                result.pattern_insight.model_dump(mode="json")
                if result.pattern_insight
                else None
            ),
            "pattern_learning": (
                result.pattern_learning.model_dump(mode="json")
                if result.pattern_learning
                else None
            ),
            "pattern_backtests": [
                record.model_dump(mode="json")
                for record in result.pattern_backtests
            ],
            "moon_phase_insight": (
                result.moon_phase_insight.model_dump(mode="json")
                if result.moon_phase_insight
                else None
            ),
            "gold_correlation_insight": (
                result.gold_correlation_insight.model_dump(mode="json")
                if result.gold_correlation_insight
                else None
            ),
            "nasdaq_correlation_insight": (
                result.nasdaq_correlation_insight.model_dump(mode="json")
                if result.nasdaq_correlation_insight
                else None
            ),
            "oil_correlation_insight": (
                result.oil_correlation_insight.model_dump(mode="json")
                if result.oil_correlation_insight
                else None
            ),
            "structure_discoveries": [
                discovery.model_dump(mode="json")
                for discovery in result.structure_discoveries
            ],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        return filepath

    def write_manifest(
        self,
        output_dir: str,
        symbol: str,
        timeframe: str,
        files: dict[str, str],
    ) -> Path:
        """Write export manifest.

        Args:
            output_dir: Output directory
            symbol: Trading symbol
            timeframe: Timeframe used
            files: Dictionary of file type to path

        Returns:
            Path to the manifest file
        """
        manifest = {
            "output_directory": output_dir,
            "generated_at": datetime.now().isoformat(),
            "symbol": symbol,
            "timeframe": timeframe,
            "files": files,
        }

        filepath = self.output_dir / "manifest.json"
        with open(filepath, "w") as f:
            json.dump(manifest, f, indent=2)

        return filepath
