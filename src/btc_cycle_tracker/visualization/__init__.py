"""Visualization module for BTC Swing Cycle Tracker.

Turns structured analysis results into interactive charts using Plotly.
"""

from .plotly_chart import create_candlestick_chart
from .annotations import add_pivot_annotations, add_leg_annotations

try:
    from .static_chart import create_static_chart
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    create_static_chart = None

__all__ = [
    "create_candlestick_chart",
    "create_static_chart",
    "add_pivot_annotations",
    "add_leg_annotations",
]
