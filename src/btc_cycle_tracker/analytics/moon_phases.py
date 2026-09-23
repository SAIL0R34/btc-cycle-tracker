"""Moon-phase analytics for correlating BTC swings with lunar cycles."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from math import ceil, floor
from statistics import mean, median

from btc_cycle_tracker.models import (
    Config,
    MoonPhaseEvent,
    MoonPhaseInsight,
    MoonPhasePhaseStats,
    OHLCV,
    PivotPoint,
    SwingLeg,
)

SYNODIC_MONTH_DAYS = 29.53058867
REFERENCE_NEW_MOON = datetime(2000, 1, 6, 18, 14)
MAJOR_PHASES = (
    ("New Moon", "new", 0.00),
    ("First Quarter", "first_quarter", 0.25),
    ("Full Moon", "full", 0.50),
    ("Last Quarter", "last_quarter", 0.75),
)


def _timeframe_hours(timeframe: str) -> float:
    """Map a timeframe code to approximate hours per bar."""
    interval_map = {
        "1m": 1 / 60,
        "3m": 3 / 60,
        "5m": 5 / 60,
        "15m": 15 / 60,
        "30m": 30 / 60,
        "1h": 1,
        "4h": 4,
        "1d": 24,
        "1w": 24 * 7,
    }
    return interval_map.get(timeframe, 5 / 60)


def _estimate_phase_window_hours(data: list[OHLCV], config: Config) -> float:
    """Choose a phase-to-pivot matching window that adapts to timeframe density."""
    if len(data) >= 2:
        diffs = [
            (right.timestamp - left.timestamp).total_seconds() / 3600
            for left, right in zip(data, data[1:])
            if right.timestamp > left.timestamp
        ]
        if diffs:
            bar_hours = median(diffs)
        else:
            bar_hours = _timeframe_hours(config.timeframe.value)
    else:
        bar_hours = _timeframe_hours(config.timeframe.value)

    adaptive_window = bar_hours * max(12, config.left_bars + config.right_bars + 2)
    return max(6.0, min(48.0, adaptive_window))


def generate_major_moon_phase_events(start: datetime, end: datetime) -> list[MoonPhaseEvent]:
    """Generate approximate major moon-phase timestamps over a time range."""
    if end <= start:
        return []

    start_lunation = (start - REFERENCE_NEW_MOON).total_seconds() / 86400 / SYNODIC_MONTH_DAYS
    end_lunation = (end - REFERENCE_NEW_MOON).total_seconds() / 86400 / SYNODIC_MONTH_DAYS

    events: list[MoonPhaseEvent] = []
    for lunation in range(floor(start_lunation) - 1, ceil(end_lunation) + 2):
        for phase_name, phase_code, phase_fraction in MAJOR_PHASES:
            event_time = REFERENCE_NEW_MOON + timedelta(
                days=SYNODIC_MONTH_DAYS * (lunation + phase_fraction)
            )
            if start <= event_time <= end:
                events.append(
                    MoonPhaseEvent(
                        timestamp=event_time,
                        phase_name=phase_name,
                        phase_code=phase_code,
                        phase_fraction=phase_fraction,
                    )
                )

    events.sort(key=lambda event: event.timestamp)
    return events


def _nearest_pivot(event_time: datetime, pivots: list[PivotPoint]) -> PivotPoint | None:
    """Find the pivot closest in time to a moon-phase event."""
    if not pivots:
        return None
    return min(pivots, key=lambda pivot: abs((pivot.timestamp - event_time).total_seconds()))


def _responsive_leg(event_time: datetime, legs: list[SwingLeg]) -> SwingLeg | None:
    """Pick the leg most relevant to the moon-phase timestamp."""
    for leg in legs:
        if leg.start_timestamp <= event_time <= leg.end_timestamp:
            return leg
        if leg.start_timestamp > event_time:
            return leg
    return None


def analyze_moon_phase_correlation(
    data: list[OHLCV],
    pivots: list[PivotPoint],
    legs: list[SwingLeg],
    config: Config,
) -> MoonPhaseInsight | None:
    """Measure how major moon phases line up with pivots and ensuing leg behavior."""
    if not config.enable_moon_phase_analysis or not data:
        return None

    events = generate_major_moon_phase_events(data[0].timestamp, data[-1].timestamp)
    phase_window_hours = _estimate_phase_window_hours(data, config)
    window_seconds = phase_window_hours * 3600

    enriched_events: list[MoonPhaseEvent] = []
    for event in events:
        nearest_pivot = _nearest_pivot(event.timestamp, pivots)
        responsive_leg = _responsive_leg(event.timestamp, legs)

        hours_to_pivot = None
        aligned_within_window = False
        nearest_pivot_timestamp = None
        nearest_pivot_type = None
        nearest_pivot_price = None

        if nearest_pivot is not None:
            delta_seconds = abs((nearest_pivot.timestamp - event.timestamp).total_seconds())
            hours_to_pivot = delta_seconds / 3600
            aligned_within_window = delta_seconds <= window_seconds
            nearest_pivot_timestamp = nearest_pivot.timestamp
            nearest_pivot_type = nearest_pivot.pivot_type.value
            nearest_pivot_price = nearest_pivot.price

        enriched_events.append(
            MoonPhaseEvent(
                timestamp=event.timestamp,
                phase_name=event.phase_name,
                phase_code=event.phase_code,
                phase_fraction=event.phase_fraction,
                nearest_pivot_timestamp=nearest_pivot_timestamp,
                nearest_pivot_type=nearest_pivot_type,
                nearest_pivot_price=nearest_pivot_price,
                hours_to_nearest_pivot=hours_to_pivot,
                aligned_within_window=aligned_within_window,
                next_leg_direction=responsive_leg.direction if responsive_leg else None,
                next_leg_percent_change=(
                    responsive_leg.percent_change if responsive_leg else None
                ),
                next_leg_duration_bars=(
                    responsive_leg.duration_bars if responsive_leg else None
                ),
            )
        )

    if not enriched_events:
        return MoonPhaseInsight(
            phase_window_hours=phase_window_hours,
            total_events=0,
            aligned_events=0,
            alignment_rate=0.0,
            avg_hours_to_pivot=None,
            strongest_phase=None,
            strongest_bias=None,
            strongest_bias_score=0.0,
            summary="No major moon phases were present inside the selected lookback window.",
            events=[],
            phase_stats=[],
        )

    phase_groups: dict[str, list[MoonPhaseEvent]] = defaultdict(list)
    for event in enriched_events:
        phase_groups[event.phase_name].append(event)

    phase_stats: list[MoonPhasePhaseStats] = []
    strongest_phase = None
    strongest_bias = None
    strongest_bias_score = 0.0

    for phase_name, phase_events in phase_groups.items():
        aligned_events = sum(event.aligned_within_window for event in phase_events)
        valid_hours = [
            event.hours_to_nearest_pivot
            for event in phase_events
            if event.hours_to_nearest_pivot is not None
        ]
        pivot_types = [
            event.nearest_pivot_type
            for event in phase_events
            if event.nearest_pivot_type is not None
        ]
        next_directions = [
            event.next_leg_direction
            for event in phase_events
            if event.next_leg_direction is not None
        ]
        next_changes = [
            event.next_leg_percent_change
            for event in phase_events
            if event.next_leg_percent_change is not None
        ]
        next_durations = [
            event.next_leg_duration_bars
            for event in phase_events
            if event.next_leg_duration_bars is not None
        ]

        bullish_count = sum(direction == "up" for direction in next_directions)
        bearish_count = sum(direction == "down" for direction in next_directions)
        total_directional = len(next_directions)
        bullish_rate = bullish_count / total_directional if total_directional else 0.0
        bearish_rate = bearish_count / total_directional if total_directional else 0.0
        bias_gap = abs(bullish_rate - bearish_rate)
        dominant_bias = "balanced"
        if bullish_rate > bearish_rate:
            dominant_bias = "bullish"
        elif bearish_rate > bullish_rate:
            dominant_bias = "bearish"

        bias_score = bias_gap * max(aligned_events / len(phase_events), 0.25)
        if bias_score > strongest_bias_score:
            strongest_phase = phase_name
            strongest_bias = dominant_bias
            strongest_bias_score = bias_score

        phase_stats.append(
            MoonPhasePhaseStats(
                phase_name=phase_name,
                occurrences=len(phase_events),
                aligned_events=aligned_events,
                alignment_rate=aligned_events / len(phase_events),
                avg_hours_to_pivot=mean(valid_hours) if valid_hours else None,
                swing_high_rate=(
                    sum(pivot_type == "swing_high" for pivot_type in pivot_types) / len(pivot_types)
                    if pivot_types
                    else 0.0
                ),
                swing_low_rate=(
                    sum(pivot_type == "swing_low" for pivot_type in pivot_types) / len(pivot_types)
                    if pivot_types
                    else 0.0
                ),
                bullish_next_leg_rate=bullish_rate,
                bearish_next_leg_rate=bearish_rate,
                avg_next_leg_change_pct=mean(next_changes) if next_changes else None,
                avg_next_leg_duration_bars=mean(next_durations) if next_durations else None,
                dominant_bias=dominant_bias,
            )
        )

    phase_stats.sort(key=lambda stat: stat.phase_name)

    aligned_total = sum(event.aligned_within_window for event in enriched_events)
    valid_event_hours = [
        event.hours_to_nearest_pivot
        for event in enriched_events
        if event.hours_to_nearest_pivot is not None
    ]
    alignment_rate = aligned_total / len(enriched_events)
    avg_hours_to_pivot = mean(valid_event_hours) if valid_event_hours else None

    if strongest_phase and strongest_bias and strongest_bias != "balanced":
        summary = (
            f"Major moon phases aligned with pivots on {aligned_total}/{len(enriched_events)} "
            f"events ({alignment_rate * 100:.1f}%) using a {phase_window_hours:.1f}h window. "
            f"The strongest historical phase-pattern bias in this lookback was {strongest_phase.lower()}, "
            f"which leaned {strongest_bias}."
        )
    else:
        summary = (
            f"Major moon phases aligned with pivots on {aligned_total}/{len(enriched_events)} "
            f"events ({alignment_rate * 100:.1f}%) using a {phase_window_hours:.1f}h window. "
            f"No strong directional moon-phase bias stood out in this lookback."
        )

    return MoonPhaseInsight(
        phase_window_hours=phase_window_hours,
        total_events=len(enriched_events),
        aligned_events=aligned_total,
        alignment_rate=alignment_rate,
        avg_hours_to_pivot=avg_hours_to_pivot,
        strongest_phase=strongest_phase,
        strongest_bias=strongest_bias,
        strongest_bias_score=strongest_bias_score,
        summary=summary,
        events=enriched_events,
        phase_stats=phase_stats,
    )
