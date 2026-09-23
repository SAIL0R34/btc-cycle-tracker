"""Deterministic evidence synthesis for model-facing market intelligence."""

from __future__ import annotations

from statistics import median
from typing import Any

from btc_cycle_tracker.models import AnalysisResult, PivotType


def _round(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def _ratio_regime(recent: float, baseline: float) -> str:
    if baseline <= 0:
        return "unknown"
    ratio = recent / baseline
    if ratio >= 1.25:
        return "expanding"
    if ratio <= 0.80:
        return "compressing"
    return "normal"


def build_market_intelligence(result: AnalysisResult) -> dict[str, Any]:
    """Build a compact, auditable regime brief from an analysis result.

    The output deliberately separates observed structure from probabilistic
    pattern evidence so an LLM can explain agreement and conflict instead of
    blending every signal into an unsupported prediction.
    """
    legs = result.legs
    if not legs:
        return {
            "quality": {"label": "insufficient", "score": 0.0, "reasons": ["No completed swing legs"]},
            "regime": "undetermined",
            "bias": "neutral",
            "conflicts": [],
        }

    recent = legs[-min(8, len(legs)) :]
    recent_changes = [leg.percent_change for leg in recent]
    baseline_legs = legs[: -len(recent)] if len(legs) >= 12 else []
    baseline_source = baseline_legs or legs
    all_amplitudes = [abs(leg.percent_change) for leg in baseline_source]
    recent_amplitudes = [abs(value) for value in recent_changes]
    all_durations = [leg.duration_bars for leg in baseline_source]
    recent_durations = [leg.duration_bars for leg in recent]

    signed_impulse = sum(recent_changes)
    up_magnitude = sum(value for value in recent_changes if value > 0)
    down_magnitude = abs(sum(value for value in recent_changes if value < 0))
    dominance = (up_magnitude - down_magnitude) / max(up_magnitude + down_magnitude, 1e-9)
    empirical_bias = "bullish" if dominance > 0.15 else "bearish" if dominance < -0.15 else "balanced"

    highs = [pivot.price for pivot in result.pivots if pivot.pivot_type == PivotType.SWING_HIGH]
    lows = [pivot.price for pivot in result.pivots if pivot.pivot_type == PivotType.SWING_LOW]
    structure = "mixed"
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            structure = "higher_highs_higher_lows"
        elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            structure = "lower_highs_lower_lows"

    amplitude_recent = median(recent_amplitudes)
    amplitude_baseline = median(all_amplitudes)
    duration_recent = median(recent_durations)
    duration_baseline = median(all_durations)
    if baseline_legs:
        amplitude_regime = _ratio_regime(amplitude_recent, amplitude_baseline)
        duration_regime = _ratio_regime(duration_recent, duration_baseline)
    else:
        amplitude_regime = "insufficient_history"
        duration_regime = "insufficient_history"

    pattern = result.pattern_insight
    pattern_bias = pattern.dominant_bias if pattern else "unavailable"
    conflicts: list[str] = []
    if pattern and pattern_bias in {"bullish", "bearish"} and empirical_bias in {"bullish", "bearish"}:
        if pattern_bias != empirical_bias:
            conflicts.append("Historical pattern bias disagrees with recent swing impulse")
    if structure == "higher_highs_higher_lows" and empirical_bias == "bearish":
        conflicts.append("Recent bearish impulse occurs inside rising pivot structure")
    if structure == "lower_highs_lower_lows" and empirical_bias == "bullish":
        conflicts.append("Recent bullish impulse occurs inside falling pivot structure")
    if structure == "higher_highs_higher_lows" and empirical_bias == "balanced":
        conflicts.append("Recent swing impulse does not confirm rising pivot structure")
    if structure == "lower_highs_lower_lows" and empirical_bias == "balanced":
        conflicts.append("Recent swing impulse does not confirm falling pivot structure")

    sample_score = min(len(legs) / 40.0, 1.0)
    pattern_score = 0.0
    quality_reasons = [f"{len(legs)} completed legs", f"{len(recent)} legs in recent regime window"]
    if pattern:
        match_score = min(pattern.matches_used / 20.0, 1.0)
        pattern_score = max(0.0, min(pattern.adaptive_confidence, 1.0)) * match_score
        quality_reasons.append(f"{pattern.matches_used} historical pattern matches")
    else:
        quality_reasons.append("Pattern evidence unavailable")
    quality_score = 0.65 * sample_score + 0.35 * pattern_score
    if conflicts:
        quality_score *= 0.85
        quality_reasons.append(f"{len(conflicts)} signal conflict(s)")
    quality_label = "high" if quality_score >= 0.75 else "moderate" if quality_score >= 0.45 else "low"

    regime = f"{amplitude_regime}_amplitude_{duration_regime}_duration"
    return {
        "bias": empirical_bias,
        "regime": regime,
        "structure": structure,
        "recent_window": {
            "legs": len(recent),
            "signed_impulse_pct": _round(signed_impulse, 2),
            "directional_dominance": _round(dominance),
            "median_amplitude_pct": _round(amplitude_recent, 2),
            "median_duration_bars": _round(duration_recent, 1),
        },
        "baseline": {
            "legs": len(baseline_legs),
            "median_amplitude_pct": _round(amplitude_baseline, 2),
            "median_duration_bars": _round(duration_baseline, 1),
        },
        "pattern_evidence": {
            "available": pattern is not None,
            "bias": pattern_bias,
            "matches": pattern.matches_used if pattern else 0,
            "adaptive_confidence": _round(pattern.adaptive_confidence) if pattern else None,
        },
        "quality": {
            "label": quality_label,
            "score": _round(quality_score),
            "reasons": quality_reasons,
        },
        "conflicts": conflicts,
    }
