"""Tests for service orchestration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from btc_cycle_tracker.models import (
    AnalysisMetadata,
    PivotPoint,
    PivotType,
    SwingLeg,
    SummaryStatistics,
    AnalysisResult,
    Config,
)
from btc_cycle_tracker.services.analysis_service import AnalysisService
from btc_cycle_tracker.services.pipeline_service import PipelineService


class TestAnalysisService:
    """Tests for the analysis service."""

    @pytest.mark.asyncio
    async def test_run_analysis(self):
        """Test complete analysis run."""
        config = Config()
        service = AnalysisService(config)

        # Mock the data loader
        mock_data = [
            MagicMock(timestamp=None, open=100, high=105, low=95, close=102, volume=100),
        ]
        service.data_loader.fetch_and_load = AsyncMock(return_value=mock_data)

        # Mock pivot detection
        service._detect_pivots = AsyncMock(return_value=[])

        result = await service.run_analysis()

        assert result is not None
        assert isinstance(result, AnalysisResult)

    @pytest.mark.asyncio
    async def test_detect_pivots_zigzag(self):
        """Test pivot detection with zigzag method."""
        config = Config(pivot_method="zigzag")
        service = AnalysisService(config)

        mock_data = [
            MagicMock(timestamp=None, open=100, high=105, low=95, close=102, volume=100),
        ]

        # Mock the detector
        with patch("btc_cycle_tracker.services.analysis_service.ZigZagDetector") as mock_detector:
            mock_detector.return_value.detect_pivots.return_value = []
            pivots = await service._detect_pivots(mock_data)

            assert isinstance(pivots, list)


class TestPipelineService:
    """Tests for the pipeline service."""

    @pytest.mark.asyncio
    async def test_run(self):
        """Test complete pipeline run."""
        config = Config()
        pipeline = PipelineService(config)

        # Mock the analysis service
        with patch.object(pipeline.analysis_service, "run_analysis") as mock_run:
            mock_result = MagicMock(spec=AnalysisResult)
            mock_result.metadata = MagicMock()
            mock_result.metadata.symbol = "BTC-USD"
            mock_result.metadata.timeframe = "5m"
            mock_result.metadata.total_pivots = 10
            mock_result.metadata.total_legs = 5
            mock_result.pivots = []
            mock_result.legs = []
            mock_result.summary = MagicMock()
            mock_result.summary.avg_percent_change = 1.0
            mock_result.raw_data = []

            mock_run.return_value = mock_result

            with patch.object(pipeline.analysis_service, "generate_chart"):
                with patch.object(pipeline.analysis_service, "export_results", return_value={}):
                    result, files = await pipeline.run()

                    assert result is not None

    @pytest.mark.asyncio
    async def test_run_batch(self):
        """Test batch analysis run."""
        config = Config()
        pipeline = PipelineService(config)

        with patch.object(pipeline.analysis_service, "run_analysis") as mock_run:
            mock_result = MagicMock(spec=AnalysisResult)
            mock_result.metadata = MagicMock()
            mock_result.metadata.symbol = "BTC-USD"
            mock_result.metadata.timeframe = "5m"
            mock_result.metadata.total_pivots = 10
            mock_result.metadata.total_legs = 5
            mock_result.pivots = []
            mock_result.legs = []
            mock_result.summary = MagicMock()
            mock_result.summary.avg_percent_change = 1.0
            mock_result.raw_data = []

            mock_run.return_value = mock_result

            with patch.object(pipeline.analysis_service, "generate_chart"):
                with patch.object(pipeline.analysis_service, "export_results", return_value={}):
                    results = await pipeline.run_batch(["BTC-USD", "ETH-USD"])

                    assert "BTC-USD" in results
                    assert "ETH-USD" in results
