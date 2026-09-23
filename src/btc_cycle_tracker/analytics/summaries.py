"""Analysis summary generation with comprehensive metrics."""

from btc_cycle_tracker.models import AnalysisResult, SummaryStatistics


class AnalysisSummary:
    """Generates human-readable summaries of analysis results."""

    @staticmethod
    def generate(result: AnalysisResult) -> str:
        """Generate a comprehensive text summary of the analysis.

        Args:
            result: AnalysisResult object

        Returns:
            Formatted summary string
        """
        lines = [
            "=" * 60,
            "BTC Swing Cycle Tracker - Analysis Summary",
            "=" * 60,
            "",
            f"Symbol: {result.metadata.symbol}",
            f"Timeframe: {result.metadata.timeframe}",
            f"Period: {result.metadata.start_date} to {result.metadata.end_date}",
            f"Total Candles: {result.metadata.total_candles}",
            "",
            "-" * 40,
            "Pivot Statistics",
            "-" * 40,
            f"Total Pivots: {result.metadata.total_pivots}",
            "",
            "-" * 40,
            "Leg Statistics",
            "-" * 40,
            f"Total Legs: {result.metadata.total_legs}",
            f"Average % Change: {result.summary.avg_percent_change:.2f}%",
            f"Average Duration: {result.summary.avg_duration_minutes:.1f} minutes",
            f"Min % Change: {result.summary.min_percent_change:.2f}%",
            f"Max % Change: {result.summary.max_percent_change:.2f}%",
            "",
            f"Up Legs: {result.summary.up_legs_count} (avg: {result.summary.up_legs_avg_change:.2f}%)",
            f"Down Legs: {result.summary.down_legs_count} (avg: {result.summary.down_legs_avg_change:.2f}%)",
            "",
            "-" * 40,
            "Detailed Summary",
            "-" * 40,
            f"Total Up Change: {result.summary.up_legs_total_change:.2f}%",
            f"Total Down Change: {result.summary.down_legs_total_change:.2f}%",
            f"Min Duration: {result.summary.min_duration_minutes:.1f} minutes",
            f"Max Duration: {result.summary.max_duration_minutes:.1f} minutes",
            "",
            "=" * 60,
        ]

        return "\n".join(lines)

    @staticmethod
    def generate_short(result: AnalysisResult) -> str:
        """Generate a short summary.

        Args:
            result: AnalysisResult object

        Returns:
            Short summary string
        """
        return (
            f"{result.metadata.symbol} - "
            f"{result.metadata.timeframe} - "
            f"{result.metadata.total_legs} legs | "
            f"{result.summary.avg_percent_change:.2f}% avg change"
        )

    @staticmethod
    def to_dict(result: AnalysisResult) -> dict:
        """Convert analysis result to a dictionary.

        Args:
            result: AnalysisResult object

        Returns:
            Dictionary representation
        """
        return {
            "symbol": result.metadata.symbol,
            "timeframe": result.metadata.timeframe,
            "period_start": result.metadata.start_date.isoformat(),
            "period_end": result.metadata.end_date.isoformat(),
            "total_candles": result.metadata.total_candles,
            "total_pivots": result.metadata.total_pivots,
            "total_legs": result.metadata.total_legs,
            "summary": {
                "avg_percent_change": result.summary.avg_percent_change,
                "avg_duration_minutes": result.summary.avg_duration_minutes,
                "min_percent_change": result.summary.min_percent_change,
                "max_percent_change": result.summary.max_percent_change,
                "up_legs_count": result.summary.up_legs_count,
                "down_legs_count": result.summary.down_legs_count,
                "up_legs_total_change": result.summary.up_legs_total_change,
                "down_legs_total_change": result.summary.down_legs_total_change,
            },
        }

    @staticmethod
    def to_markdown(result: AnalysisResult) -> str:
        """Convert analysis result to a Markdown table.

        Args:
            result: AnalysisResult object

        Returns:
            Markdown formatted string
        """
        lines = [
            "# Swing Cycle Analysis Summary",
            "",
            f"**Symbol:** {result.metadata.symbol}",
            f"**Timeframe:** {result.metadata.timeframe}",
            f"**Period:** {result.metadata.start_date} to {result.metadata.end_date}",
            "",
            "## Key Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Legs | {result.metadata.total_legs} |",
            f"| Avg % Change | {result.summary.avg_percent_change:.2f}% |",
            f"| Min % Change | {result.summary.min_percent_change:.2f}% |",
            f"| Max % Change | {result.summary.max_percent_change:.2f}% |",
            f"| Avg Duration | {result.summary.avg_duration_minutes:.1f} min |",
            "",
            "## Direction Summary",
            "",
            "| Direction | Count | Avg % Change |",
            "|-----------|-------|--------------|",
            f"| Up | {result.summary.up_legs_count} | {result.summary.up_legs_avg_change:.2f}% |",
            f"| Down | {result.summary.down_legs_count} | {result.summary.down_legs_avg_change:.2f}% |",
        ]

        return "\n".join(lines)
