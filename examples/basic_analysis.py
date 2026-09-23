"""Example: Basic Analysis.

This example demonstrates basic swing cycle analysis.
"""

import asyncio
from btc_cycle_tracker.services.analysis_service import AnalysisService
from btc_cycle_tracker.models import Config

async def main():
    """Run basic analysis."""
    config = Config(symbol="BTC-USD", timeframe="5m", lookback="30d")
    service = AnalysisService(config)
    result = await service.run_analysis()
    service.print_summary(result)

if __name__ == "__main__":
    asyncio.run(main())
