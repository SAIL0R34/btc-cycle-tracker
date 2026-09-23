"""Example: Export to CSV.

This example demonstrates exporting analysis results to CSV.
"""

import asyncio
from btc_cycle_tracker.services.analysis_service import AnalysisService
from btc_cycle_tracker.export.csv_writer import CSVWriter
from btc_cycle_tracker.export.json_writer import JSONWriter

async def main():
    """Export analysis results to CSV and JSON."""
    service = AnalysisService()
    result = await service.run_analysis()

    csv_writer = CSVWriter()
    csv_files = csv_writer.write_analysis_result(result, include_raw_data=True)
    print(f"CSV files: {csv_files}")

    json_writer = JSONWriter()
    json_file = json_writer.write_analysis_result(result)
    print(f"JSON file: {json_file}")

if __name__ == "__main__":
    asyncio.run(main())
