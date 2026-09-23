"""Application settings and configuration management."""

import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DataSettings(BaseModel):
    """Settings for data sources and storage."""

    data_dir: str = "data"
    cache_dir: str = "data/cache"
    default_source: str = "coinbase"  # coinbase, binance, kraken
    supported_sources: list[str] = ["coinbase", "binance", "kraken"]


class ChartSettings(BaseModel):
    """Settings for chart visualization."""

    default_width: int = 1200
    default_height: int = 800
    theme: str = "plotly_dark"
    colors: dict[str, str] = {
        "up": "#2ecc71",
        "down": "#e74c3c",
        "pivot_high": "#f39c12",
        "pivot_low": "#3498db",
        "leg_up": "#2ecc71",
        "leg_down": "#e74c3c",
    }


class OutputSettings(BaseModel):
    """Settings for output files."""

    output_dir: str = "outputs"
    chart_format: str = "html"  # html, png, svg
    csv_decimal_places: int = 2
    csv_timestamp_format: str = "%Y-%m-%d %H:%M:%S"


class Settings(BaseSettings):
    """Application settings loaded from environment and config."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core settings
    debug: bool = False
    log_level: str = "INFO"

    # Data settings
    data: DataSettings = DataSettings()

    # Chart settings
    chart: ChartSettings = ChartSettings()

    # Output settings
    output: OutputSettings = OutputSettings()

    # API keys (optional, loaded from environment)
    coinbase_api_key: str | None = None
    coinbase_api_secret: str | None = None
    binance_api_key: str | None = None
    binance_api_secret: str | None = None

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: Any) -> Any:
        """Handle common environment-style debug values."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "dev", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return value

    @property
    def base_dir(self) -> Path:
        """Get the base directory of the application."""
        return Path(__file__).parent.parent.parent

    def resolve_app_path(self, path: str | Path) -> Path:
        """Resolve app-owned relative paths from the project root."""
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.base_dir / candidate

    @property
    def data_path(self) -> Path:
        """Get the full path to the data directory."""
        return self.resolve_app_path(self.data.data_dir)

    @property
    def cache_path(self) -> Path:
        """Get the full path to the cache directory."""
        return self.resolve_app_path(self.data.cache_dir)

    @property
    def output_path(self) -> Path:
        """Get the full path to the output directory."""
        return self.resolve_app_path(self.output.output_dir)

    def generate_config_hash(self, config: dict[str, Any]) -> str:
        """Generate a hash for configuration to track runs."""
        config_str = str(sorted(config.items()))
        return hashlib.md5(config_str.encode()).hexdigest()[:12]


# Global settings instance
settings = Settings()
