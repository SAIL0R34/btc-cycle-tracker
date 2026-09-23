"""CLI module for BTC Swing Cycle Tracker."""

import asyncio
from typing import Optional

import typer

from btc_cycle_tracker.models import PivotMethod, Timeframe
from btc_cycle_tracker.services.analysis_service import AnalysisService
from btc_cycle_tracker.services.pipeline_service import PipelineService

app = typer.Typer(
    name="btc-cycle-tracker",
    help="Track BTC price action, detect swing highs and lows, and analyze cycles",
)


@app.command()
def analyze(
    symbol: str = typer.Option("BTC-USD", "--symbol", "-s", help="Trading symbol"),
    timeframe: Timeframe = typer.Option(Timeframe.FIVE_MINUTE, "--timeframe", "-t", help="Candle timeframe"),
    lookback: str = typer.Option("30d", "--lookback", "-l", help="Lookback period (e.g., 30d, 7w, 3m)"),
    pivot_method: PivotMethod = typer.Option(PivotMethod.ZIGZAG, "--pivot-method", "-m", help="Pivot detection method"),
    min_move_pct: float = typer.Option(1.0, "--min-move-pct", help="Minimum percentage move for pivot"),
    left_bars: int = typer.Option(5, "--left-bars", help="Left bars for pivot detection"),
    right_bars: int = typer.Option(5, "--right-bars", help="Right bars for pivot detection"),
    use_atr_filter: bool = typer.Option(True, "--use-atr", help="Use ATR filter"),
    atr_period: int = typer.Option(14, "--atr-period", help="ATR period"),
    atr_multiplier: float = typer.Option(1.5, "--atr-multiplier", help="ATR multiplier"),
    output_dir: str = typer.Option("outputs", "--output-dir", help="Output directory"),
    save_chart: bool = typer.Option(True, "--save-chart", help="Save chart"),
    save_csv: bool = typer.Option(True, "--save-csv", help="Save CSV files"),
    csv_include_raw: bool = typer.Option(False, "--csv-raw", help="Include raw data in CSV"),
) -> None:
    """Run a complete swing cycle analysis."""
    from btc_cycle_tracker.models import Config

    config = Config(
        symbol=symbol,
        timeframe=timeframe,
        lookback_period=lookback,
        pivot_method=pivot_method,
        min_move_pct=min_move_pct,
        left_bars=left_bars,
        right_bars=right_bars,
        use_atr_filter=use_atr_filter,
        atr_period=atr_period,
        atr_multiplier=atr_multiplier,
        output_dir=output_dir,
        save_chart=save_chart,
        save_csv=save_csv,
        csv_include_raw_data=csv_include_raw,
    )

    async def run():
        service = AnalysisService(config)
        result = await service.run_analysis()
        service.print_summary(result)
        files = service.export_results(result)
        service.generate_chart(result)

        print(f"\nOutputs saved to: {output_dir}/")
        for file_type, path in files.items():
            print(f"  - {file_type}: {path}")

    asyncio.run(run())


@app.command()
def chart(
    symbol: str = typer.Option("BTC-USD", "--symbol", "-s", help="Trading symbol"),
    timeframe: Timeframe = typer.Option(Timeframe.FIVE_MINUTE, "--timeframe", "-t", help="Candle timeframe"),
    lookback: str = typer.Option("30d", "--lookback", "-l", help="Lookback period"),
    pivot_method: PivotMethod = typer.Option(PivotMethod.ZIGZAG, "--pivot-method", "-m", help="Pivot detection method"),
    output_dir: str = typer.Option("outputs", "--output-dir", help="Output directory"),
) -> None:
    """Generate a chart for the analysis."""
    from btc_cycle_tracker.models import Config

    config = Config(
        symbol=symbol,
        timeframe=timeframe,
        lookback_period=lookback,
        pivot_method=pivot_method,
        output_dir=output_dir,
        save_chart=True,
        save_csv=False,
    )

    async def run():
        service = AnalysisService(config)
        result = await service.run_analysis()
        service.generate_chart(result)
        print(f"Chart saved to: {output_dir}/")

    asyncio.run(run())


@app.command()
def batch(
    symbols: str = typer.Option("", "--symbols", "-S", help="Comma-separated list of symbols"),
    timeframe: Timeframe = typer.Option(Timeframe.FIVE_MINUTE, "--timeframe", "-t", help="Candle timeframe"),
    lookback: str = typer.Option("30d", "--lookback", "-l", help="Lookback period"),
) -> None:
    """Run analysis for multiple symbols."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]

    async def run():
        pipeline = PipelineService()
        results = await pipeline.run_batch(symbol_list, timeframe.value, lookback)

        for symbol, (result, files) in results.items():
            print(f"\n{symbol}:")
            print(f"  Pivots: {result.metadata.total_pivots}")
            print(f"  Legs: {result.metadata.total_legs}")

    asyncio.run(run())


@app.command()
def version() -> None:
    """Print the version."""
    from btc_cycle_tracker import __version__

    print(f"btc-swing-cycle-tracker v{__version__}")


if __name__ == "__main__":
    app()
