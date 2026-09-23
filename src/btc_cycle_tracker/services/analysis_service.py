"""Analysis service for orchestrating pivot detection and analysis."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from btc_cycle_tracker.data.loaders import DataLoader
from btc_cycle_tracker.models import (
    AnalysisMetadata,
    AnalysisResult,
    Config,
    OHLCV,
    PivotPoint,
    PivotType,
    SwingLeg,
)
from btc_cycle_tracker.pivots.detector import PivotDetector
from btc_cycle_tracker.pivots.zigzag import ZigZagDetector
from btc_cycle_tracker.pivots.fractal import FractalDetector
from btc_cycle_tracker.pivots.filters import (
    NoiseFilter,
    ATRFilter,
    PercentChangeFilter,
    ConsecutivePivotFilter,
)
from btc_cycle_tracker.pivots.confirmation import confirm_pivots
from btc_cycle_tracker.analytics.legs import LegBuilder, calculate_leg_metrics
from btc_cycle_tracker.analytics.cross_asset import build_asset_correlation_insight
from btc_cycle_tracker.analytics.decision import (
    WEIGHTS,
    DecisionBrief,
    DecisionInputs,
    run_decision_walk_forward,
    score_decision,
)
from btc_cycle_tracker.analytics.decision_memory import (
    DecisionMemoryStore,
    adaptive_weights,
    build_track_record,
)
from btc_cycle_tracker.analytics.intelligence import build_market_intelligence
from btc_cycle_tracker.analytics.moon_phases import analyze_moon_phase_correlation
from btc_cycle_tracker.analytics.patterns import PatternRecognitionEngine
from btc_cycle_tracker.analytics.stats import calculate_summary_stats
from btc_cycle_tracker.analytics.structures import discover_structures
from btc_cycle_tracker.visualization.plotly_chart import create_candlestick_chart
from btc_cycle_tracker.export.csv_writer import CSVWriter
from btc_cycle_tracker.export.json_writer import JSONWriter
from btc_cycle_tracker.export.filesystem import OutputFilesystem
from btc_cycle_tracker.settings import settings

logger = logging.getLogger("btc_cycle_tracker.services.analysis")


class AnalysisService:
    """Service for running complete swing cycle analysis."""

    def __init__(
        self,
        config: Optional[Config] = None,
        data_loader: Optional[DataLoader] = None,
    ):
        """Initialize the analysis service.

        Args:
            config: Analysis configuration (uses defaults if None)
            data_loader: Data loader instance (creates new if None)
        """
        self.config = config or Config()
        self.data_loader = data_loader or DataLoader()
        self.output_fs = OutputFilesystem(self.config.output_dir)

    async def run_analysis(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        lookback: Optional[str] = None,
    ) -> AnalysisResult:
        """Run a complete analysis.

        Args:
            symbol: Trading symbol (uses config if None)
            timeframe: Timeframe (uses config if None)
            lookback: Lookback period (uses config if None)

        Returns:
            AnalysisResult with all analysis data
        """
        # Use config values if not overridden
        symbol = symbol or self.config.symbol
        timeframe = timeframe or self.config.timeframe.value
        lookback = lookback or self.config.lookback_period

        # Fetch data
        data = await self._fetch_data(symbol, timeframe, lookback)
        data = [
            candle
            if isinstance(candle, OHLCV)
            else OHLCV(
                timestamp=candle.timestamp or datetime.now(),
                open=float(candle.open),
                high=float(candle.high),
                low=float(candle.low),
                close=float(candle.close),
                volume=float(getattr(candle, "volume", 0.0) or 0.0),
            )
            for candle in data
        ]
        if not data:
            raise RuntimeError(
                f"No OHLCV data returned for {symbol} ({timeframe}, {lookback})."
            )

        # Detect pivots
        pivots = await self._detect_pivots(data)

        # Build legs
        legs = LegBuilder.build_legs_from_pivots(pivots, data)

        # The provisional leg still forming after the last confirmed pivot
        forming_leg = LegBuilder.build_forming_leg(pivots, legs, data)

        # Calculate statistics
        summary = calculate_summary_stats(legs, data)
        structure_discoveries = discover_structures(data, pivots, self.config.min_move_pct)
        pattern_insight = None
        pattern_learning = None
        pattern_backtests = []
        moon_phase_insight = None
        gold_correlation_insight = None
        nasdaq_correlation_insight = None
        oil_correlation_insight = None
        if self.config.enable_pattern_recognition:
            pattern_engine = PatternRecognitionEngine(self.config, self.config.output_dir)
            pattern_insight, pattern_learning, pattern_backtests = pattern_engine.analyze(
                legs=legs,
                symbol=symbol,
                timeframe=timeframe,
            )
        if self.config.enable_moon_phase_analysis:
            moon_phase_insight = analyze_moon_phase_correlation(
                data=data,
                pivots=pivots,
                legs=legs,
                config=self.config,
            )
        correlation_errors: dict[str, str] = {}
        if self.config.enable_gold_correlation_analysis:
            try:
                gold_correlation_insight = build_asset_correlation_insight(
                    data=data,
                    asset_name="Gold",
                    asset_symbol="GC=F",
                )
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                gold_correlation_insight = None
                correlation_errors["gold"] = str(exc)
        if self.config.enable_nasdaq_correlation_analysis:
            try:
                nasdaq_correlation_insight = build_asset_correlation_insight(
                    data=data,
                    asset_name="Nasdaq",
                    asset_symbol="^IXIC",
                )
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                nasdaq_correlation_insight = None
                correlation_errors["nasdaq"] = str(exc)
        if self.config.enable_oil_correlation_analysis:
            try:
                oil_correlation_insight = build_asset_correlation_insight(
                    data=data,
                    asset_name="Oil",
                    asset_symbol="CL=F",
                )
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                oil_correlation_insight = None
                correlation_errors["oil"] = str(exc)

        start_date = data[0].timestamp or datetime.now()
        end_date = data[-1].timestamp or datetime.now()

        # Create metadata
        metadata = AnalysisMetadata(
            symbol=symbol,
            timeframe=timeframe,
            pivot_method=self.config.pivot_method.value,
            start_date=start_date,
            end_date=end_date,
            total_candles=len(data),
            total_pivots=len(pivots),
            total_legs=len(legs),
            run_timestamp=datetime.now(),
            config_hash=settings.generate_config_hash(self.config.model_dump()),
        )

        result = AnalysisResult(
            metadata=metadata,
            pivots=pivots,
            legs=legs,
            summary=summary,
            raw_data=data,
            pattern_insight=pattern_insight,
            pattern_learning=pattern_learning,
            pattern_backtests=pattern_backtests,
            moon_phase_insight=moon_phase_insight,
            gold_correlation_insight=gold_correlation_insight,
            nasdaq_correlation_insight=nasdaq_correlation_insight,
            oil_correlation_insight=oil_correlation_insight,
            structure_discoveries=structure_discoveries,
            forming_leg=forming_leg,
            correlation_errors=correlation_errors,
        )

        if self.config.enable_decision_engine:
            result.decision_brief = self._build_decision_brief(result)

        return result

    def _build_decision_brief(self, result: AnalysisResult) -> DecisionBrief:
        """Assemble the decision scorecard from everything the run produced.

        With decision memory enabled the full accountability loop runs in a
        strict order: grade matured past decisions → backfill+grade replay
        checkpoints → learn adaptive weights/calibration from the graded
        history → score with them → log the live decision → attach the
        track record. Every memory interaction is best-effort: a store
        problem must never fail the analysis.
        """
        intelligence = build_market_intelligence(result)
        pattern = result.pattern_insight
        learning = result.pattern_learning
        horizon_edge = 0.0
        if learning:
            # Horizon direction is the genuinely uncertain call; credit the
            # pattern only for beating a coin-flip null on it.
            horizon_edge = max(0.0, learning.horizon_hit_rate - 0.5)
        inputs = DecisionInputs(
            pivots=result.pivots,
            legs=result.legs,
            summary=result.summary,
            structures=result.structure_discoveries,
            forming_leg=result.forming_leg,
            pattern_bias=pattern.dominant_bias if pattern else "unavailable",
            pattern_confidence=pattern.adaptive_confidence if pattern else 0.0,
            pattern_horizon_edge=horizon_edge,
            pattern_matches=pattern.matches_used if pattern else 0,
            correlations={
                name: insight
                for name, insight in (
                    ("gold", result.gold_correlation_insight),
                    ("nasdaq", result.nasdaq_correlation_insight),
                )
                if insight is not None
            },
            intelligence_quality=intelligence.get("quality", {}).get("label", "moderate"),
            intelligence_conflicts=intelligence.get("conflicts", []),
        )

        symbol = result.metadata.symbol
        timeframe = result.metadata.timeframe
        memory = None
        weights = None
        source_stats = None
        calibration = 1.0
        config_hash = result.metadata.config_hash

        if self.config.enable_decision_memory:
            try:
                memory = DecisionMemoryStore(
                    self.config.output_dir, self.config.decision_memory_max_records
                )
                memory.grade_pending(result.raw_data, symbol, timeframe)
            except Exception as exc:  # noqa: BLE001 - memory is best-effort
                logger.warning("Decision memory unavailable: %s", exc)
                memory = None

        if memory is not None:
            walk_forward = run_decision_walk_forward(
                result.raw_data, self.config, memory=memory,
                symbol=symbol, timeframe=timeframe, config_hash=config_hash,
            )
            if self.config.enable_adaptive_decision_weights:
                try:
                    weights, source_stats, calibration = adaptive_weights(
                        memory, symbol, timeframe, WEIGHTS,
                        self.config.decision_learning_min_samples,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Adaptive decision weights failed: %s", exc)
                    weights, source_stats, calibration = None, None, 1.0
        else:
            walk_forward = run_decision_walk_forward(result.raw_data, self.config)

        brief = score_decision(
            inputs,
            weights=weights,
            source_stats=source_stats,
            conviction_calibration=calibration,
        )
        brief.walk_forward = walk_forward

        if memory is not None:
            try:
                memory.log_live_decision(
                    brief, symbol, timeframe, result.raw_data, result.summary, config_hash
                )
                brief.track_record = build_track_record(
                    memory, symbol, timeframe, source_stats or [], calibration
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Decision logging failed: %s", exc)

        return brief

    def run_analysis_sync(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        lookback: Optional[str] = None,
    ) -> AnalysisResult:
        """Run analysis from synchronous contexts like Streamlit callbacks."""
        return asyncio.run(self.run_analysis(symbol, timeframe, lookback))

    async def _fetch_data(
        self,
        symbol: str,
        timeframe: str,
        lookback: str,
    ) -> list[OHLCV]:
        """Fetch OHLCV data.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            lookback: Lookback period

        Returns:
            List of OHLCV candles
        """
        return await self.data_loader.fetch_and_load(
            symbol,
            timeframe,
            lookback,
            use_cache=False,
        )

    async def _detect_pivots(self, data: list[OHLCV]) -> list[PivotPoint]:
        """Detect pivot points using configured method.

        Args:
            data: OHLCV data

        Returns:
            List of pivot points
        """
        # Select detector based on configuration
        if self.config.pivot_method == "zigzag":
            detector = ZigZagDetector(
                left_bars=self.config.left_bars,
                right_bars=self.config.right_bars,
                min_move_pct=self.config.min_move_pct,
            )
        elif self.config.pivot_method == "fractal":
            detector = FractalDetector(
                left_bars=self.config.left_bars,
                right_bars=self.config.right_bars,
                min_move_pct=self.config.min_move_pct,
            )
        else:
            # Default to zigzag
            detector = ZigZagDetector(
                left_bars=self.config.left_bars,
                right_bars=self.config.right_bars,
                min_move_pct=self.config.min_move_pct,
            )

        # Detect pivots
        pivots = detector.detect_pivots(data, self.config)

        # Apply filters
        pivots = self._apply_filters(pivots, data)

        # Confirm pivots
        pivots = confirm_pivots(pivots, data, self.config)

        return pivots

    def _apply_filters(
        self,
        pivots: list[PivotPoint],
        data: list[OHLCV],
    ) -> list[PivotPoint]:
        """Apply configured filters to pivots.

        Args:
            pivots: List of pivot points
            data: OHLCV data

        Returns:
            Filtered list of pivot points
        """
        filters = []

        if self.config.use_atr_filter:
            filters.append(
                ATRFilter(
                    atr_period=self.config.atr_period,
                    atr_multiplier=self.config.atr_multiplier,
                )
            )

        # Apply filters sequentially
        for filter_obj in filters:
            pivots = filter_obj.filter(pivots, data)

        return pivots

    def generate_chart(
        self,
        result: AnalysisResult,
        title: Optional[str] = None,
    ) -> None:
        """Generate and save a chart.

        Args:
            result: AnalysisResult object
            title: Chart title (auto-generated if None)
        """
        if not self.config.save_chart:
            return

        if title is None:
            title = f"{result.metadata.symbol} Swing Cycle Analysis ({result.metadata.timeframe})"

        fig = create_candlestick_chart(
            data=result.raw_data,
            pivots=result.pivots,
            legs=result.legs,
            title=title,
            width=self.config.chart_width,
            height=self.config.chart_height,
            theme="plotly_dark",
        )

        # Save chart
        run_dir = self.output_fs.create_run_directory(
            result.metadata.symbol,
            result.metadata.timeframe,
        )
        chart_path = run_dir / "chart.html"
        fig.write_html(str(chart_path))

    def export_results(
        self,
        result: AnalysisResult,
    ) -> dict[str, str]:
        """Export analysis results to files.

        Args:
            result: AnalysisResult object

        Returns:
            Dictionary of file type to path
        """
        run_dir = self.output_fs.create_run_directory(
            result.metadata.symbol,
            result.metadata.timeframe,
        )

        files = {}

        # Export CSV
        if self.config.save_csv:
            csv_writer = CSVWriter(str(run_dir))
            files.update(csv_writer.write_analysis_result(result, self.config.csv_include_raw_data))

        # Export JSON
        json_writer = JSONWriter(str(run_dir))
        files["json"] = str(json_writer.write_analysis_result(result))

        return files

    def print_summary(self, result: AnalysisResult) -> None:
        """Print a summary of the analysis results.

        Args:
            result: AnalysisResult object
        """
        print("\n" + "=" * 60)
        print("BTC Swing Cycle Tracker - Analysis Summary")
        print("=" * 60)
        print(f"\nSymbol: {result.metadata.symbol}")
        print(f"Timeframe: {result.metadata.timeframe}")
        print(f"Period: {result.metadata.start_date} to {result.metadata.end_date}")
        print(f"Total Candles: {result.metadata.total_candles}")
        print(f"Total Pivots: {result.metadata.total_pivots}")
        print(f"Total Legs: {result.metadata.total_legs}")
        print("\n" + "-" * 40)
        print("Leg Statistics")
        print("-" * 40)
        print(f"Average % Change: {result.summary.avg_percent_change:.2f}%")
        print(f"Average Duration: {result.summary.avg_duration_minutes:.1f} minutes")
        print(f"Min % Change: {result.summary.min_percent_change:.2f}%")
        print(f"Max % Change: {result.summary.max_percent_change:.2f}%")
        print(f"\nUp Legs: {result.summary.up_legs_count} (avg: {result.summary.up_legs_avg_change:.2f}%)")
        print(f"Down Legs: {result.summary.down_legs_count} (avg: {result.summary.down_legs_avg_change:.2f}%)")
        print("=" * 60 + "\n")
