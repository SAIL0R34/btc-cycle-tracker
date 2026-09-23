"""Analytics module for BTC Swing Cycle Tracker.

Converts pivots into legs and cycle metrics, computes percent changes and durations.
"""

from .legs import LegBuilder, calculate_leg_metrics
from .patterns import PatternRecognitionEngine, build_pattern_signature
from .cycles import CycleAnalyzer
from .stats import calculate_summary_stats, calculate_distribution_stats
from .summaries import AnalysisSummary

__all__ = [
    "LegBuilder",
    "calculate_leg_metrics",
    "PatternRecognitionEngine",
    "build_pattern_signature",
    "CycleAnalyzer",
    "calculate_summary_stats",
    "calculate_distribution_stats",
    "AnalysisSummary",
]
