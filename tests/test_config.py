"""Tests for configuration and settings."""

import pytest

from btc_cycle_tracker.models import Config, PivotMethod, Timeframe
from btc_cycle_tracker.settings import Settings, DataSettings, ChartSettings, OutputSettings


class TestConfig:
    """Tests for configuration."""

    def test_config_defaults(self):
        """Test configuration with defaults."""
        config = Config()

        assert config.symbol == "BTC-USD"
        assert config.timeframe == Timeframe.FIVE_MINUTE
        assert config.pivot_method == PivotMethod.ZIGZAG
        assert config.min_move_pct == 1.0

    def test_config_custom_values(self):
        """Test configuration with custom values."""
        config = Config(
            symbol="ETH-USD",
            timeframe=Timeframe.ONE_HOUR,
            pivot_method=PivotMethod.FRACTAL,
            min_move_pct=2.0,
        )

        assert config.symbol == "ETH-USD"
        assert config.timeframe == Timeframe.ONE_HOUR
        assert config.pivot_method == PivotMethod.FRACTAL
        assert config.min_move_pct == 2.0

    def test_config_lookback_validation(self):
        """Test lookback period validation."""
        with pytest.raises(ValueError):
            Config(lookback_period="30")  # Missing unit

        config = Config(lookback_period="30d")
        assert config.lookback_period == "30d"


class TestSettings:
    """Tests for application settings."""

    def test_settings_creation(self):
        """Test settings instantiation."""
        settings = Settings()

        assert settings.data is not None
        assert settings.chart is not None
        assert settings.output is not None

    def test_data_settings(self):
        """Test data settings."""
        data_settings = DataSettings()

        assert data_settings.data_dir == "data"
        assert data_settings.cache_dir == "data/cache"

    def test_chart_settings(self):
        """Test chart settings."""
        chart_settings = ChartSettings()

        assert chart_settings.default_width == 1200
        assert chart_settings.default_height == 800
        assert "up" in chart_settings.colors
