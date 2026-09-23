"""Example: Batch Analysis.

This example demonstrates running analysis for multiple symbols.
"""

import asyncio
from btc_cycle_tracker.services.pipeline_service import PipelineService

async def main():
    """Run batch analysis for multiple symbols."""
    pipeline = PipelineService()
    results = await pipeline.run_batch(
        symbols=["BTC-USD", "ETH-USD", "SOL-USD"],
        timeframe="1h",
        lookback="7d",
    )
    for symbol, (result, files) in results.items():
        print(f"\n{symbol}:")
        print(f"  Pivots: {result.metadata.total_pivots}")
        print(f"  Legs: {result.metadata.total_legs}")

if __name__ == "__main__":
    asyncio.run(main())
