"""Pipeline service for orchestrating the complete analysis workflow."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from btc_cycle_tracker.data.loaders import DataLoader
from btc_cycle_tracker.models import AnalysisResult, Config
from btc_cycle_tracker.services.analysis_service import AnalysisService


class PipelineService:
    """Orchestrates the complete analysis pipeline."""

    def __init__(
        self,
        config: Optional[Config] = None,
        data_loader: Optional[DataLoader] = None,
    ):
        """Initialize the pipeline service.

        Args:
            config: Analysis configuration
            data_loader: Data loader instance
        """
        self.config = config or Config()
        self.analysis_service = AnalysisService(self.config, data_loader)

    async def run(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        lookback: Optional[str] = None,
        run_dir: Optional[str] = None,
    ) -> tuple[AnalysisResult, dict[str, str]]:
        """Run the complete analysis pipeline.

        Args:
            symbol: Trading symbol (uses config if None)
            timeframe: Timeframe (uses config if None)
            lookback: Lookback period (uses config if None)
            run_dir: Custom output directory (auto-generated if None)

        Returns:
            Tuple of (AnalysisResult, exported files dict)
        """
        # Run analysis
        result = await self.analysis_service.run_analysis(symbol, timeframe, lookback)

        # Generate chart
        self.analysis_service.generate_chart(result)

        # Export results
        files = self.analysis_service.export_results(result)

        return result, files

    async def run_batch(
        self,
        symbols: list[str],
        timeframe: Optional[str] = None,
        lookback: Optional[str] = None,
    ) -> dict[str, tuple[AnalysisResult, dict[str, str]]]:
        """Run analysis for multiple symbols.

        Args:
            symbols: List of trading symbols
            timeframe: Timeframe (uses config if None)
            lookback: Lookback period (uses config if None)

        Returns:
            Dictionary mapping symbol to (result, files)
        """
        results = {}
        for symbol in symbols:
            result, files = await self.run(symbol, timeframe, lookback)
            results[symbol] = (result, files)

        return results

    async def run_with_callback(
        self,
        symbol: str,
        timeframe: Optional[str] = None,
        lookback: Optional[str] = None,
        on_step: Optional[callable] = None,
    ) -> tuple[AnalysisResult, dict[str, str]]:
        """Run analysis with callback for each step.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            lookback: Lookback period
            on_step: Callback function(step_name, data)

        Returns:
            Tuple of (AnalysisResult, exported files dict)
        """
        # Fetch data
        data = await self.analysis_service._fetch_data(symbol, timeframe or self.config.timeframe.value, lookback or self.config.lookback_period)
        if on_step:
            on_step("data_fetched", {"count": len(data)})

        # Detect pivots
        pivots = await self.analysis_service._detect_pivots(data)
        if on_step:
            on_step("pivots_detected", {"count": len(pivots)})

        # Build legs
        from btc_cycle_tracker.analytics.legs import LegBuilder
        legs = LegBuilder.build_legs_from_pivots(pivots, data)
        if on_step:
            on_step("legs_built", {"count": len(legs)})

        # Calculate statistics
        from btc_cycle_tracker.analytics.stats import calculate_summary_stats
        summary = calculate_summary_stats(legs)

        # Create result
        result = AnalysisResult(
            metadata=None,  # Will be set below
            pivots=pivots,
            legs=legs,
            summary=summary,
            raw_data=data,
        )

        # Set metadata
        from btc_cycle_tracker.models import AnalysisMetadata
        result.metadata = AnalysisMetadata(
            symbol=symbol,
            timeframe=timeframe or self.config.timeframe.value,
            pivot_method=self.config.pivot_method.value,
            start_date=data[0].timestamp,
            end_date=data[-1].timestamp,
            total_candles=len(data),
            total_pivots=len(pivots),
            total_legs=len(legs),
            run_timestamp=datetime.now(),
            config_hash="",
        )

        # Generate chart
        self.analysis_service.generate_chart(result)
        if on_step:
            on_step("chart_generated", {"path": "chart.html"})

        # Export results
        files = self.analysis_service.export_results(result)
        if on_step:
            on_step("exported", {"files": files})

        return result, files
