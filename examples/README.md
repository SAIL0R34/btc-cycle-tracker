# Example scripts for BTC Swing Cycle Tracker

This directory contains example scripts demonstrating various use cases.

## Examples

### 1. Basic Analysis

```python
from btc_cycle_tracker.services.analysis_service import AnalysisService
from btc_cycle_tracker.models import Config

async def main():
    config = Config(symbol="BTC-USD", timeframe="5m", lookback="30d")
    service = AnalysisService(config)
    result = await service.run_analysis()
    service.print_summary(result)

# Run: python examples/basic_analysis.py
```

### 2. Batch Analysis

```python
from btc_cycle_tracker.services.pipeline_service import PipelineService

async def main():
    pipeline = PipelineService()
    results = await pipeline.run_batch(["BTC-USD", "ETH-USD", "SOL-USD"])
    for symbol, (result, files) in results.items():
        print(f"{symbol}: {result.metadata.total_legs} legs")

# Run: python examples/batch_analysis.py
```

### 3. Custom Pivot Detection

```python
from btc_cycle_tracker.pivots.zigzag import ZigZagDetector
from btc_cycle_tracker.data.loaders import DataLoader

async def main():
    loader = DataLoader()
    data = await loader.fetch_and_load("BTC-USD", "5m", "7d")
    
    detector = ZigZagDetector(left_bars=3, right_bars=3, min_move_pct=0.5)
    pivots = detector.detect_pivots(data, None)
    
    print(f"Detected {len(pivots)} pivots")

# Run: python examples/custom_pivots.py
```

### 4. Export to CSV

```python
from btc_cycle_tracker.services.analysis_service import AnalysisService
from btc_cycle_tracker.export.csv_writer import CSVWriter

async def main():
    service = AnalysisService(Config(symbol="BTC-USD"))
    result = await service.run_analysis()
    
    csv_writer = CSVWriter()
    csv_writer.write_legs(result.legs)
    csv_writer.write_pivots(result.pivots)

# Run: python examples/export_csv.py
```

### 5. Chart Generation

```python
from btc_cycle_tracker.visualization.plotly_chart import create_candlestick_chart
from btc_cycle_tracker.services.analysis_service import AnalysisService

async def main():
    service = AnalysisService(Config(symbol="BTC-USD"))
    result = await service.run_analysis()
    
    fig = create_candlestick_chart(
        data=result.raw_data,
        pivots=result.pivots,
        legs=result.legs,
    )
    fig.write_html("chart.html")

# Run: python examples/generate_chart.py
```

## Running Examples

```bash
# Install dependencies
pip install -e .

# Run an example
python examples/basic_analysis.py
```
