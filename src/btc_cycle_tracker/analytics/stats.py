"""Statistical analysis functions for swing cycle data."""

from typing import Optional

import numpy as np

from btc_cycle_tracker.models import OHLCV, SwingLeg, SummaryStatistics


def amplitude_duration_correlation(legs: list[SwingLeg]) -> float:
    """Pearson correlation between leg *amplitude* (|percent change|) and duration.

    Signed change mixes up- and down-legs into two mirrored clouds, which
    collapses the correlation toward zero; amplitude is the meaningful
    relationship ("do bigger swings take longer?").
    """
    if len(legs) < 3:
        return 0.0
    amplitudes = [abs(leg.percent_change) for leg in legs]
    durations = [leg.duration_bars for leg in legs]
    if len(set(amplitudes)) < 2 or len(set(durations)) < 2:
        return 0.0
    return float(np.corrcoef(amplitudes, durations)[0, 1])


def calculate_summary_stats(
    legs: list[SwingLeg],
    data: Optional[list[OHLCV]] = None,
) -> SummaryStatistics:
    """Calculate summary statistics for swing legs.

    Args:
        legs: List of swing legs
        data: Optional OHLCV series — when present, realized volatility and
            max drawdown are measured from the candle closes instead of
            approximated from legs.

    Returns:
        SummaryStatistics object
    """
    if not legs:
        return SummaryStatistics(
            total_legs=0,
            avg_percent_change=0.0,
            avg_duration_minutes=0.0,
            avg_duration_bars=0,
            min_percent_change=0.0,
            max_percent_change=0.0,
            min_duration_minutes=0.0,
            max_duration_minutes=0.0,
            up_legs_count=0,
            down_legs_count=0,
            up_legs_total_change=0.0,
            down_legs_total_change=0.0,
            up_legs_avg_change=0.0,
            down_legs_avg_change=0.0,
            up_legs_avg_duration=0.0,
            down_legs_avg_duration=0.0,
            median_percent_change=0.0,
            median_duration_minutes=0.0,
            up_down_asymmetry=0.0,
            amplitude_duration_correlation=0.0,
            net_change_pct=0.0,
            efficiency_ratio=0.0,
            realized_vol_pct_per_bar=0.0,
            max_drawdown_pct=0.0,
        )

    percent_changes = [leg.percent_change for leg in legs]
    durations_minutes = [leg.duration_minutes for leg in legs]
    durations_bars = [leg.duration_bars for leg in legs]

    up_legs = [leg for leg in legs if leg.is_up]
    down_legs = [leg for leg in legs if leg.is_down]

    up_legs_total_change = sum(leg.percent_change for leg in up_legs) if up_legs else 0.0
    down_legs_total_change = sum(leg.percent_change for leg in down_legs) if down_legs else 0.0

    # Calculate up/down asymmetry: signed magnitude imbalance in [-1, 1].
    # Positive = up legs carry more average magnitude (bullish drift).
    up_avg_abs = abs(up_legs_total_change) / len(up_legs) if up_legs else 0.0
    down_avg_abs = abs(down_legs_total_change) / len(down_legs) if down_legs else 0.0
    magnitude_asymmetry = (
        (up_avg_abs - down_avg_abs) / (up_avg_abs + down_avg_abs)
        if (up_avg_abs + down_avg_abs) > 0
        else 0.0
    )

    # Amplitude-duration correlation on absolute moves (see helper docstring)
    correlation = amplitude_duration_correlation(legs)

    # ── Regime context metrics ──────────────────────────────────────────
    # Net change over the leg sequence (close-to-close of the whole swing path).
    net_change_pct = (legs[-1].end_price / legs[0].start_price - 1) * 100

    # Kaufman efficiency ratio: |net move| / Σ|leg moves| in [0, 1].
    # 1.0 = perfectly directional trend, →0 = choppy two-sided action.
    total_path = sum(abs(leg.percent_change) for leg in legs)
    efficiency_ratio = abs(net_change_pct) / total_path if total_path > 0 else 0.0

    if data and len(data) >= 3:
        closes = [float(c.close) for c in data]
        log_returns = [
            float(np.log(closes[i] / closes[i - 1])) for i in range(1, len(closes))
        ]
        realized_vol_pct_per_bar = float(np.std(log_returns, ddof=1)) * 100 if len(log_returns) >= 2 else 0.0
        peak = closes[0]
        max_drawdown_pct = 0.0
        for close in closes:
            peak = max(peak, close)
            max_drawdown_pct = max(max_drawdown_pct, (peak - close) / peak * 100)
    else:
        # Leg-based proxies: per-bar vol from leg amplitudes, drawdown from
        # the worst cumulative signed-leg path.
        per_bar_moves = [
            leg.percent_change / max(leg.duration_bars, 1) ** 0.5 for leg in legs
        ]
        realized_vol_pct_per_bar = (
            float(np.std(per_bar_moves, ddof=1)) if len(per_bar_moves) >= 2 else 0.0
        )
        cumulative = 0.0
        run_peak = 0.0
        max_drawdown_pct = 0.0
        for leg in legs:
            cumulative += leg.percent_change
            run_peak = max(run_peak, cumulative)
            max_drawdown_pct = max(max_drawdown_pct, run_peak - cumulative)
        total_path_ref = legs[0].start_price or 1.0
        max_drawdown_pct = max_drawdown_pct / total_path_ref * 100

    return SummaryStatistics(
        total_legs=len(legs),
        avg_percent_change=sum(percent_changes) / len(percent_changes),
        avg_duration_minutes=sum(durations_minutes) / len(durations_minutes),
        avg_duration_bars=int(sum(durations_bars) / len(durations_bars)),
        min_percent_change=min(percent_changes),
        max_percent_change=max(percent_changes),
        min_duration_minutes=min(durations_minutes),
        max_duration_minutes=max(durations_minutes),
        up_legs_count=len(up_legs),
        down_legs_count=len(down_legs),
        up_legs_total_change=up_legs_total_change,
        down_legs_total_change=down_legs_total_change,
        up_legs_avg_change=sum(leg.percent_change for leg in up_legs) / len(up_legs) if up_legs else 0.0,
        down_legs_avg_change=sum(leg.percent_change for leg in down_legs) / len(down_legs) if down_legs else 0.0,
        up_legs_avg_duration=sum(leg.duration_minutes for leg in up_legs) / len(up_legs) if up_legs else 0.0,
        down_legs_avg_duration=sum(leg.duration_minutes for leg in down_legs) / len(down_legs) if down_legs else 0.0,
        median_percent_change=float(np.median(percent_changes)),
        median_duration_minutes=float(np.median(durations_minutes)),
        up_down_asymmetry=magnitude_asymmetry,
        amplitude_duration_correlation=correlation,
        net_change_pct=net_change_pct,
        efficiency_ratio=efficiency_ratio,
        realized_vol_pct_per_bar=realized_vol_pct_per_bar,
        max_drawdown_pct=max_drawdown_pct,
    )


def calculate_distribution_stats(
    legs: list[SwingLeg],
    num_bins: int = 10,
) -> dict:
    """Calculate distribution statistics for leg metrics.

    Args:
        legs: List of swing legs
        num_bins: Number of bins for histogram

    Returns:
        Dictionary of distribution statistics
    """
    if not legs:
        return {}

    percent_changes = [leg.percent_change for leg in legs]
    durations = [leg.duration_minutes for leg in legs]

    # Calculate histogram bins
    pct_hist = _calculate_histogram(percent_changes, num_bins)
    dur_hist = _calculate_histogram(durations, num_bins)

    return {
        "percent_change": {
            "mean": np.mean(percent_changes),
            "std": np.std(percent_changes),
            "min": min(percent_changes),
            "max": max(percent_changes),
            "median": np.median(percent_changes),
            "histogram": pct_hist,
        },
        "duration_minutes": {
            "mean": np.mean(durations),
            "std": np.std(durations),
            "min": min(durations),
            "max": max(durations),
            "median": np.median(durations),
            "histogram": dur_hist,
        },
    }


def _calculate_histogram(
    values: list[float],
    num_bins: int,
) -> list[dict]:
    """Calculate histogram bins for a list of values.

    Args:
        values: List of numeric values
        num_bins: Number of bins

    Returns:
        List of bin dictionaries with count and range
    """
    if not values:
        return []

    min_val = min(values)
    max_val = max(values)
    bin_width = (max_val - min_val) / num_bins if max_val != min_val else 1

    bins = []
    for i in range(num_bins):
        bin_start = min_val + i * bin_width
        bin_end = bin_start + bin_width
        count = sum(1 for v in values if bin_start <= v < bin_end)
        bins.append({
            "bin_start": bin_start,
            "bin_end": bin_end,
            "count": count,
        })

    return bins


def calculate_correlation(
    legs: list[SwingLeg],
    metric1: str,
    metric2: str,
) -> float:
    """Calculate correlation between two leg metrics.

    Args:
        legs: List of swing legs
        metric1: First metric name
        metric2: Second metric name

    Returns:
        Correlation coefficient (-1 to 1)
    """
    if not legs:
        return 0.0

    values1 = [getattr(leg, metric1) for leg in legs]
    values2 = [getattr(leg, metric2) for leg in legs]

    if len(values1) < 2:
        return 0.0

    # Calculate correlation
    mean1 = sum(values1) / len(values1)
    mean2 = sum(values2) / len(values2)

    numerator = sum((v1 - mean1) * (v2 - mean2) for v1, v2 in zip(values1, values2))
    denom1 = sum((v - mean1) ** 2 for v in values1)
    denom2 = sum((v - mean2) ** 2 for v in values2)

    denominator = (denom1 * denom2) ** 0.5

    if denominator == 0:
        return 0.0

    return numerator / denominator


def calculate_up_down_ratio(legs: list[SwingLeg]) -> float:
    """Calculate the ratio of up legs to down legs.

    Args:
        legs: List of swing legs

    Returns:
        Ratio of up legs to down legs
    """
    if not legs:
        return 0.0

    up_count = sum(1 for leg in legs if leg.is_up)
    down_count = sum(1 for leg in legs if leg.is_down)

    if down_count == 0:
        return float("inf") if up_count > 0 else 0.0

    return up_count / down_count


def calculate_max_moves(legs: list[SwingLeg]) -> dict:
    """Calculate the largest up and down moves.

    Args:
        legs: List of swing legs

    Returns:
        Dictionary with max up and down move info
    """
    if not legs:
        return {
            "max_up_move": {"leg_id": None, "percent_change": 0.0},
            "max_down_move": {"leg_id": None, "percent_change": 0.0},
        }

    up_legs = [leg for leg in legs if leg.is_up]
    down_legs = [leg for leg in legs if leg.is_down]

    max_up = max(up_legs, key=lambda x: x.percent_change) if up_legs else None
    max_down = min(down_legs, key=lambda x: x.percent_change) if down_legs else None

    return {
        "max_up_move": {
            "leg_id": max_up.leg_id if max_up else None,
            "percent_change": max_up.percent_change if max_up else 0.0,
            "duration_minutes": max_up.duration_minutes if max_up else 0.0,
        },
        "max_down_move": {
            "leg_id": max_down.leg_id if max_down else None,
            "percent_change": max_down.percent_change if max_down else 0.0,
            "duration_minutes": max_down.duration_minutes if max_down else 0.0,
        },
    }


def calculate_cycle_metrics(legs: list[SwingLeg]) -> dict:
    """Calculate cycle-specific metrics for analysis.

    Args:
        legs: List of swing legs

    Returns:
        Dictionary of cycle metrics
    """
    if not legs:
        return {
            "total_cycles": 0,
            "avg_cycle_percent_change": 0.0,
            "avg_cycle_duration_minutes": 0.0,
            "up_down_asymmetry": 0.0,
            "amplitude_duration_correlation": 0.0,
        }

    # Calculate median values
    percent_changes = [leg.percent_change for leg in legs]
    durations = [leg.duration_minutes for leg in legs]

    # Up/Down asymmetry: ratio of up leg count to total
    up_legs = [leg for leg in legs if leg.is_up]
    down_legs = [leg for leg in legs if leg.is_down]
    up_ratio = len(up_legs) / len(legs) if legs else 0.0
    down_ratio = len(down_legs) / len(legs) if legs else 0.0
    asymmetry = abs(up_ratio - down_ratio)

    # Amplitude-duration relationship (correlation between size and duration)
    if len(legs) >= 2:
        abs_changes = [abs(leg.percent_change) for leg in legs]
        correlation = calculate_correlation(legs, "percent_change", "duration_minutes")
    else:
        correlation = 0.0

    # Rolling cycle comparison (group legs into cycles)
    cycles = []
    current_cycle = []
    for leg in legs:
        current_cycle.append(leg)
        if len(current_cycle) >= 2:
            # Check if we have a complete cycle (up then down, or down then up)
            if current_cycle[-1].direction != current_cycle[-2].direction:
                cycles.append(current_cycle)
                current_cycle = []

    total_cycles = len(cycles)
    avg_cycle_change = 0.0
    avg_cycle_duration = 0.0

    if cycles:
        cycle_changes = [sum(leg.percent_change for leg in cycle) for cycle in cycles]
        cycle_durations = [sum(leg.duration_minutes for leg in cycle) for cycle in cycles]
        avg_cycle_change = sum(cycle_changes) / len(cycle_changes)
        avg_cycle_duration = sum(cycle_durations) / len(cycle_durations)

    return {
        "total_cycles": total_cycles,
        "avg_cycle_percent_change": avg_cycle_change,
        "avg_cycle_duration_minutes": avg_cycle_duration,
        "up_down_asymmetry": asymmetry,
        "amplitude_duration_correlation": correlation,
        "median_percent_change": np.median(percent_changes),
        "median_duration_minutes": np.median(durations),
        "up_ratio": up_ratio,
        "down_ratio": down_ratio,
    }
