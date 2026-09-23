"""Filesystem utilities for managing output directories."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from btc_cycle_tracker.settings import settings


class OutputFilesystem:
    """Manages output directories and file paths."""

    def __init__(self, base_dir: str = "outputs"):
        """Initialize the filesystem manager.

        Args:
            base_dir: Base output directory
        """
        self.base_dir = settings.resolve_app_path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_run_directory(
        self,
        symbol: str,
        timeframe: str,
        timestamp: Optional[datetime] = None,
    ) -> Path:
        """Create a timestamped directory for a run.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe used
            timestamp: Timestamp for directory name (default: now)

        Returns:
            Path to the created directory
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Format: BTC-USD_5m_20240101_120000
        dir_name = f"{symbol}_{timeframe}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        run_dir = self.base_dir / dir_name
        run_dir.mkdir(parents=True, exist_ok=True)

        return run_dir

    def get_latest_run_directory(self, symbol: Optional[str] = None) -> Optional[Path]:
        """Get the most recent run directory.

        Args:
            symbol: Filter by symbol (optional)

        Returns:
            Path to the latest run directory, or None if not found
        """
        if not self.base_dir.exists():
            return None

        # Get all run directories
        run_dirs = []
        for item in self.base_dir.iterdir():
            if item.is_dir():
                if symbol is None or symbol in item.name:
                    run_dirs.append(item)

        if not run_dirs:
            return None

        # Return the most recently modified directory
        return max(run_dirs, key=lambda d: d.stat().st_mtime)

    def get_all_run_directories(self, symbol: Optional[str] = None) -> list[Path]:
        """Get all run directories.

        Args:
            symbol: Filter by symbol (optional)

        Returns:
            List of run directory paths
        """
        if not self.base_dir.exists():
            return []

        run_dirs = []
        for item in self.base_dir.iterdir():
            if item.is_dir():
                if symbol is None or symbol in item.name:
                    run_dirs.append(item)

        return sorted(run_dirs, key=lambda d: d.name, reverse=True)

    def save_chart(
        self,
        chart_data: bytes,
        filename: str,
        run_dir: Optional[Path] = None,
    ) -> Path:
        """Save chart data to a file.

        Args:
            chart_data: Chart image data
            filename: Output filename
            run_dir: Run directory (uses base if None)

        Returns:
            Path to the saved file
        """
        if run_dir is None:
            run_dir = self.base_dir

        filepath = run_dir / filename
        with open(filepath, "wb") as f:
            f.write(chart_data)

        return filepath

    def save_text(
        self,
        content: str,
        filename: str,
        run_dir: Optional[Path] = None,
    ) -> Path:
        """Save text content to a file.

        Args:
            content: Text content to save
            filename: Output filename
            run_dir: Run directory (uses base if None)

        Returns:
            Path to the saved file
        """
        if run_dir is None:
            run_dir = self.base_dir

        filepath = run_dir / filename
        with open(filepath, "w") as f:
            f.write(content)

        return filepath

    def get_file_path(
        self,
        filename: str,
        run_dir: Optional[Path] = None,
    ) -> Path:
        """Get a file path in the output directory.

        Args:
            filename: Filename
            run_dir: Run directory (uses base if None)

        Returns:
            Full path to the file
        """
        if run_dir is None:
            run_dir = self.base_dir

        return run_dir / filename

    def cleanup_old_runs(
        self,
        max_age_days: int = 30,
        symbol: Optional[str] = None,
    ) -> int:
        """Remove run directories older than max_age_days.

        Args:
            max_age_days: Maximum age in days
            symbol: Filter by symbol (optional)

        Returns:
            Number of directories removed
        """
        if not self.base_dir.exists():
            return 0

        cutoff = datetime.now().timestamp() - (max_age_days * 86400)
        removed = 0

        for item in self.base_dir.iterdir():
            if item.is_dir():
                if symbol is None or symbol in item.name:
                    if item.stat().st_mtime < cutoff:
                        import shutil
                        shutil.rmtree(item)
                        removed += 1

        return removed
