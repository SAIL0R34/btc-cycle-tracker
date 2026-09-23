"""In-memory application state shared by the API and the agent tools.

One analysis result is "current" at a time (mirroring how the Streamlit app
worked). A lock serialises pipeline runs so the agent and the UI can't race.
Config changes persist to disk so toggles survive restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from btc_cycle_tracker.models import AnalysisResult, Config
from btc_cycle_tracker.services.analysis_service import AnalysisService
from btc_cycle_tracker.settings import settings

logger = logging.getLogger("btc_cycle_tracker.web.state")


class AppState:
    def __init__(self) -> None:
        self.config_path: Path = settings.resolve_app_path("outputs") / "app_config.json"
        self.config: Config = self._load_persisted_config()
        self.result: Optional[AnalysisResult] = None
        self.last_files: dict[str, str] = {}
        self.last_run_at: Optional[str] = None
        self.run_lock = threading.Lock()

    def _load_persisted_config(self) -> Config:
        """Start from defaults, overlaid with the last persisted config."""
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text())
                if isinstance(data, dict):
                    return Config(**data)
        except Exception as exc:  # noqa: BLE001 - corrupt file shouldn't kill boot
            logger.warning("Ignoring persisted config (%s): %s", self.config_path, exc)
        return Config()

    def _persist_config(self) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(
                json.dumps(self.config.model_dump(mode="json"), indent=2, sort_keys=True)
            )
        except Exception as exc:  # noqa: BLE001 - persistence is best-effort
            logger.warning("Could not persist config: %s", exc)

    # ── Config ────────────────────────────────────────────────────────────
    def update_config(self, fields: dict[str, Any]) -> Config:
        """Apply a partial, validated config update. Raises on bad values."""
        merged = self.config.model_dump()
        unknown = [k for k in fields if k not in merged]
        if unknown:
            raise ValueError(f"Unknown config field(s): {', '.join(unknown)}")
        merged.update(fields)
        self.config = Config(**merged)  # pydantic validates
        self._persist_config()
        return self.config

    # ── Analysis ──────────────────────────────────────────────────────────
    def run_analysis_sync(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        lookback: Optional[str] = None,
    ) -> AnalysisResult:
        """Run the pipeline (blocking). Safe to call from a worker thread."""
        if not self.run_lock.acquire(timeout=1):
            raise RuntimeError("An analysis is already running — try again shortly.")
        try:
            overrides = {}
            if symbol:
                overrides["symbol"] = symbol
            if timeframe:
                overrides["timeframe"] = timeframe
            if lookback:
                overrides["lookback_period"] = lookback
            if overrides:
                self.update_config(overrides)

            service = AnalysisService(self.config)
            result = asyncio.run(service.run_analysis())
            self.result = result
            self.last_run_at = datetime.now(timezone.utc).isoformat()
            return result
        finally:
            self.run_lock.release()

    def export_current(self) -> dict[str, str]:
        """Export the current result via the existing writers."""
        if self.result is None:
            raise RuntimeError("No analysis result to export — run an analysis first.")
        service = AnalysisService(self.config)
        files = service.export_results(self.result)
        self.last_files = files
        return files


STATE = AppState()
