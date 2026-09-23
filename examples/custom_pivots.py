"""Example: Custom Pivot Detection.

This example demonstrates using custom pivot detection parameters.
"""

import asyncio
from btc_cycle_tracker.pivots.zigzag import ZigZagDetector
from btc_cycle_tracker.pivots.fractal import FractalDetector
from btc_cycle_tracker.data.loaders import DataLoader
from btc_cycle_tracker.models import Config

async def main():
    """Run custom pivot detection."""
    loader = DataLoader()
    config = Config()
    data = await loader.fetch_and_load("BTC-USD", "5m", "7d")

    zigzag = ZigZagDetector(left_bars=3, right_bars=3, min_move_pct=0.5)
    zigzag_pivots = zigzag.detect_pivots(data, config)
    print(f"ZigZag: {len(zigzag_pivots)} pivots")

    fractal = FractalDetector(left_bars=2, right_bars=2)
    fractal_pivots = fractal.detect_pivots(data, config)
    print(f"Fractal: {len(fractal_pivots)} pivots")

if __name__ == "__main__":
    asyncio.run(main())
