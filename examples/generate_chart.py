"""Example: Generate Chart.

This example demonstrates generating an interactive chart.
"""

import asyncio
from btc_cycle_tracker.services.analysis_service import AnalysisService
from btc_cycle_tracker.visualization.plotly_chart import create_candlestick_chart

async def main():
    """Generate and save a chart."""
    service = AnalysisService()
    result = await service.run_analysis()

    fig = create_candlestick_chart(
        data=result.raw_data,
        pivots=result.pivots,
        legs=result.legs,
        title="BTC Swing Cycle Analysis",
        width=1200,
        height=800,
    )

    fig.write_html("chart.html")
    print("Chart saved to chart.html")

if __name__ == "__main__":
    asyncio.run(main())
