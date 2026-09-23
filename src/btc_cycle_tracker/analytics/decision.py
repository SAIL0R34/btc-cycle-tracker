"""Auditable investment/divestment decision engine.

Design
------
Every evidence source produces a **signed contribution** in [-1, +1]
(positive = invest tilt) scaled by an evidence weight. The composite score
is the weight-normalised sum expressed on a -100..+100 scale and mapped to
action bands. Every contribution carries its weight and rationale, so the
call can be audited line by line — no black box.

Deliberate methodological choices:

* **Moon phases are excluded** from the decision (display-only; no known
  causal edge).
* **Pattern evidence is scaled by its validated edge** — a bullish analog
  bias only counts when the walk-forward horizon hit rate beats the naive
  null and the next-move error is finite.
* **Chop gate**: when the Kaufman efficiency ratio is very low the
  trend-following contributions are halved (trend signals are noise in
  chop).
* **Quality gate**: low evidence quality (from ``build_market_intelligence``)
  caps the action at ``hold`` and floors conviction.
* **Walk-forward replay**: the same scorecard is re-evaluated at historical
  checkpoints using only the data available at each point, and each replayed
  call is scored against the realised forward move. Replayed decisions use
  structural + regime evidence only (the pattern engine is excluded — it is
  too slow to replay and has its own walk-forward test).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from btc_cycle_tracker.analytics.legs import LegBuilder
from btc_cycle_tracker.analytics.stats import calculate_summary_stats
from btc_cycle_tracker.analytics.structures import discover_structures
from btc_cycle_tracker.models import (
    Config,
    DecisionBandStat,
    DecisionBrief,
    DecisionCheckpoint,
    DecisionContribution,
    DecisionInvalidation,
    DecisionWalkForward,
    OHLCV,
    PivotPoint,
    StructureDiscovery,
    SummaryStatistics,
    SwingLeg,
)
from btc_cycle_tracker.pivots.confirmation import confirm_pivots
from btc_cycle_tracker.pivots.zigzag import ZigZagDetector

ACTION_STRONG_INVEST = "strong_invest"
ACTION_INVEST = "invest"
ACTION_HOLD = "hold"
ACTION_DIVEST = "divest"
ACTION_STRONG_DIVEST = "strong_divest"

_STRONG_BAND = 45.0
_BAND = 18.0

# Evidence weights (they sum to 100).
WEIGHTS = {
    "structure_trend": 22.0,
    "structure_break": 18.0,
    "zone_position": 15.0,
    "pattern_evidence": 15.0,
    "regime_momentum": 15.0,
    "forming_leg": 8.0,
    "cross_asset": 7.0,
}

CHOP_EFFICIENCY_FLOOR = 0.12


def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def action_for_score(score: float, quality: str = "high") -> str:
    """Map a composite score to an action band, respecting the quality gate."""
    if quality == "low":
        # Low evidence quality: never escalate past the inner bands, and
        # demand more agreement before committing either way.
        if score >= _STRONG_BAND:
            return ACTION_INVEST
        if score <= -_STRONG_BAND:
            return ACTION_DIVEST
        if abs(score) < 2 * _BAND:
            return ACTION_HOLD
        return ACTION_INVEST if score > 0 else ACTION_DIVEST
    if score >= _STRONG_BAND:
        return ACTION_STRONG_INVEST
    if score >= _BAND:
        return ACTION_INVEST
    if score <= -_STRONG_BAND:
        return ACTION_STRONG_DIVEST
    if score <= -_BAND:
        return ACTION_DIVEST
    return ACTION_HOLD


def _stance_of(value: float) -> str:
    if value > 0.05:
        return "invest"
    if value < -0.05:
        return "divest"
    return "neutral"


@dataclass
class DecisionInputs:
    """The evidence fields the scorecard consumes (subset of AnalysisResult)."""

    pivots: list[PivotPoint] = field(default_factory=list)
    legs: list[SwingLeg] = field(default_factory=list)
    summary: SummaryStatistics | None = None
    structures: list[StructureDiscovery] = field(default_factory=list)
    forming_leg: SwingLeg | None = None
    pattern_bias: str = "unavailable"          # dominant_bias or "unavailable"
    pattern_confidence: float = 0.0            # adaptive confidence 0..1
    pattern_horizon_edge: float = 0.0          # horizon hit rate minus null
    pattern_matches: int = 0
    correlations: dict = field(default_factory=dict)  # name -> AssetCorrelationInsight
    intelligence_quality: str = "moderate"
    intelligence_conflicts: list[str] = field(default_factory=list)


def _structure_trend(inputs: DecisionInputs) -> tuple[float, str, str]:
    for item in inputs.structures:
        if item.structure_type == "uptrend_structure":
            return 1.0, "Rising swing structure (higher highs and lows)", item.title
        if item.structure_type == "downtrend_structure":
            return -1.0, "Falling swing structure (lower highs and lows)", item.title
        if item.structure_type == "mixed_structure":
            return 0.0, "Swing highs and lows disagree — no structural trend", item.title
    return 0.0, "Not enough confirmed pivots for a structure read", ""


def _structure_break(inputs: DecisionInputs) -> tuple[float, str, str]:
    best = None
    for item in inputs.structures:
        if item.structure_type in {"break_of_structure", "change_of_character"}:
            if best is None or item.end_timestamp > best.end_timestamp:
                best = item
    if best is None:
        return 0.0, "No recent break of structure", ""
    sign = 1.0 if best.direction == "bullish" else -1.0 if best.direction == "bearish" else 0.0
    label = "break of structure" if best.structure_type == "break_of_structure" else "change of character"
    return sign * _clip(best.confidence), f"{best.direction} {label} confirmed", best.title


def _zone_position(inputs: DecisionInputs, last_price: float | None) -> tuple[float, str, str]:
    if last_price is None:
        return 0.0, "No last price available", ""
    zones = [s for s in inputs.structures if s.structure_type in {"support_zone", "resistance_zone"}]
    if not zones:
        return 0.0, "No significant support/resistance zones detected", ""

    best_support = None
    best_support_dist = float("inf")
    best_resistance = None
    best_resistance_dist = float("inf")
    for zone in zones:
        center = float(zone.measurements.get("center_price", (zone.zone_low + zone.zone_high) / 2 if zone.zone_low is not None and zone.zone_high is not None else 0.0))
        dist_pct = abs(center - last_price) / last_price * 100
        if center <= last_price and dist_pct < best_support_dist:
            best_support, best_support_dist = zone, dist_pct
        elif center > last_price and dist_pct < best_resistance_dist:
            best_resistance, best_resistance_dist = zone, dist_pct

    # Inside a zone counts as distance zero to that side.
    support_score = 0.0
    resistance_score = 0.0
    reach = 3.0  # percent distance at which a zone stops mattering
    if best_support is not None and best_support.zone_low is not None:
        if last_price <= best_support.zone_high:
            support_score = 1.0
        else:
            gap = (last_price - best_support.zone_high) / last_price * 100
            support_score = _clip(1.0 - gap / reach, 0.0, 1.0)
    if best_resistance is not None and best_resistance.zone_high is not None:
        if last_price >= best_resistance.zone_low:
            resistance_score = 1.0
        else:
            gap = (best_resistance.zone_low - last_price) / last_price * 100
            resistance_score = _clip(1.0 - gap / reach, 0.0, 1.0)

    net = support_score - resistance_score
    if net > 0:
        zone = best_support
        rationale = "Price is near/at support — better risk location to add than to chase"
    elif net < 0:
        zone = best_resistance
        rationale = "Price is near/at resistance — adding here has poor location"
    else:
        zone = None
        rationale = "Price sits between support and resistance — location is neutral"
    detail = ""
    if zone is not None:
        detail = (
            f"{zone.title} @ {zone.zone_low:.0f}–{zone.zone_high:.0f} "
            f"({zone.measurements.get('touches', '?')} touches)"
        )
    return _clip(net), rationale, detail


def _pattern_evidence(inputs: DecisionInputs) -> tuple[float, str, str]:
    if inputs.pattern_bias not in {"bullish", "bearish"}:
        return 0.0, f"Pattern bias is {inputs.pattern_bias} — no directional evidence", ""
    sign = 1.0 if inputs.pattern_bias == "bullish" else -1.0
    # The analog bias only counts in proportion to its validated edge:
    # horizon hit rate above the naive null, and the adaptive confidence.
    edge = _clip(inputs.pattern_horizon_edge / 0.15, 0.0, 1.0)  # +15pp over null = full credit
    magnitude = inputs.pattern_confidence * edge
    rationale = (
        f"Analog set leans {inputs.pattern_bias} ({inputs.pattern_matches} matches, "
        f"confidence {inputs.pattern_confidence:.0%}, horizon edge {inputs.pattern_horizon_edge:+.0%} vs null)"
    )
    return sign * magnitude, rationale, "scaled by validated walk-forward edge"


def _regime_momentum(inputs: DecisionInputs) -> tuple[float, str, str]:
    summary = inputs.summary
    if summary is None or not inputs.legs:
        return 0.0, "No leg statistics available", ""
    net_norm = _clip(summary.net_change_pct / 10.0)  # ±10% window move saturates
    skew = _clip(summary.up_down_asymmetry)
    value = _clip(0.6 * net_norm + 0.4 * skew)
    rationale = (
        f"Window net {summary.net_change_pct:+.2f}% with magnitude skew {summary.up_down_asymmetry:+.2f}"
    )
    return value, rationale, f"efficiency {summary.efficiency_ratio:.2f}"


def _forming_leg(inputs: DecisionInputs) -> tuple[float, str, str]:
    leg = inputs.forming_leg
    if leg is None:
        return 0.0, "No forming leg right now", ""
    value = _clip((1.0 if leg.is_up else -1.0) * min(1.0, abs(leg.percent_change) / 3.0))
    rationale = f"Unconfirmed {leg.direction} leg {leg.percent_change:+.2f}% since the last pivot"
    return value, rationale, "dashed on the chart — may still extend or fail"


def _cross_asset(inputs: DecisionInputs) -> tuple[float, str, str]:
    usable = []
    for name in ("nasdaq", "gold"):
        corr = inputs.correlations.get(name)
        if corr is None or corr.return_correlation is None:
            continue
        # Relative strength (BTC minus asset, normalized points) is the tilt;
        # a stronger return correlation makes the signal more meaningful.
        tilt = _clip((corr.latest_relative_strength_pct or 0.0) / 10.0)
        weight_factor = 0.5 + 0.5 * abs(corr.return_correlation)
        usable.append((name, tilt * weight_factor, corr))
    if not usable:
        return 0.0, "Cross-asset evidence unavailable (modules off or fetch failed)", ""
    value = _clip(sum(v for _, v, _ in usable) / len(usable))
    detail = ", ".join(
        f"{name}: rel {c.latest_relative_strength_pct:+.1f} · corr {c.return_correlation:+.2f}"
        for name, _, c in usable
    )
    rationale = "BTC relative performance vs correlated macro assets"
    return value, rationale, detail


def score_decision(
    inputs: DecisionInputs,
    weights: dict[str, float] | None = None,
    source_stats: list | None = None,
    conviction_calibration: float = 1.0,
) -> DecisionBrief:
    """Run the scorecard over the evidence and assemble the brief.

    ``weights`` overrides the baseline WEIGHTS (used for adaptive learning);
    ``source_stats`` carries the per-source audit fields (prior weight,
    learned multiplier, sample count) onto the contributions.
    """
    summary = inputs.summary
    last_price = inputs.forming_leg.end_price if inputs.forming_leg else (
        inputs.legs[-1].end_price if inputs.legs else None
    )

    raw: dict[str, tuple[float, str, str]] = {
        "structure_trend": _structure_trend(inputs),
        "structure_break": _structure_break(inputs),
        "zone_position": _zone_position(inputs, last_price),
        "pattern_evidence": _pattern_evidence(inputs),
        "regime_momentum": _regime_momentum(inputs),
        "forming_leg": _forming_leg(inputs),
        "cross_asset": _cross_asset(inputs),
    }

    # Chop gate: trend-following evidence is halved when the window is choppy.
    efficiency = summary.efficiency_ratio if summary else 0.0
    choppiness_gate = efficiency < CHOP_EFFICIENCY_FLOOR
    if choppiness_gate:
        for key in ("structure_trend", "structure_break", "regime_momentum", "forming_leg"):
            value, rationale, detail = raw[key]
            raw[key] = (value * 0.5, rationale + " (halved: choppy window)", detail)

    active_weights = weights if weights else dict(WEIGHTS)
    stat_by_source = {s.source: s for s in (source_stats or [])}

    contributions: list[DecisionContribution] = []
    weighted_sum = 0.0
    total_weight = sum(active_weights.values())
    for source, (value, rationale, detail) in raw.items():
        weight = active_weights.get(source, WEIGHTS.get(source, 0.0))
        score = value * weight  # signed contribution on the ±100 scale
        weighted_sum += score
        stat = stat_by_source.get(source)
        contributions.append(
            DecisionContribution(
                source=source,
                stance=_stance_of(value),
                weight=round(weight, 2),
                score=round(score, 2),
                rationale=rationale,
                detail=detail,
                prior_weight=(WEIGHTS.get(source) if weights else None),
                learned_multiplier=(stat.multiplier if (weights and stat) else None),
                alignment_samples=(stat.samples if (weights and stat) else None),
            )
        )

    composite = _clip(weighted_sum / total_weight * 100.0, -100.0, 100.0)

    # Conviction: evidence agreement × evidence quality, damped by conflicts,
    # then calibrated by the engine's graded track record.
    alignment = abs(weighted_sum) / total_weight  # 0..1
    quality_score = {"high": 1.0, "moderate": 0.6, "low": 0.3}.get(inputs.intelligence_quality, 0.5)
    raw_conviction = _clip(0.5 * alignment + 0.5 * quality_score - 0.12 * len(inputs.intelligence_conflicts), 0.0, 1.0)
    conviction = _clip(raw_conviction * conviction_calibration, 0.0, 1.0)

    quality = inputs.intelligence_quality
    action = action_for_score(composite, quality)

    invalidations = _invalidations(inputs, last_price)

    if not inputs.legs:
        summary_text = "Not enough confirmed swing structure to make a call — holding by default."
    else:
        direction_word = {
            ACTION_STRONG_INVEST: "Strong case to invest/add",
            ACTION_INVEST: "Lean invest/add",
            ACTION_HOLD: "Hold — evidence does not favor either side",
            ACTION_DIVEST: "Lean divest/reduce",
            ACTION_STRONG_DIVEST: "Strong case to divest/reduce",
        }[action]
        summary_text = (
            f"{direction_word} (score {composite:+.0f}, conviction {conviction:.0%}, "
            f"evidence quality {quality})."
            + (f" {len(inputs.intelligence_conflicts)} signal conflict(s) damped conviction." if inputs.intelligence_conflicts else "")
            + (" Evidence is choppy (low efficiency) — trend signals were halved." if choppiness_gate else "")
        )

    return DecisionBrief(
        action=action,
        composite_score=round(composite, 2),
        conviction=round(conviction, 3),
        quality=quality,
        summary=summary_text,
        contributions=contributions,
        invalidations=invalidations,
        conflicts=list(inputs.intelligence_conflicts),
        excluded=["moon_phase: display-only, excluded from the decision (no known causal edge)"],
        last_price=last_price,
        conviction_uncalibrated=(round(raw_conviction, 3) if conviction_calibration != 1.0 else None),
    )


def _invalidations(inputs: DecisionInputs, last_price: float | None) -> list[DecisionInvalidation]:
    """Levels whose break would flip the call, nearest first."""
    if last_price is None:
        return []
    levels: list[tuple[float, str, str, str]] = []  # (price, kind, flips_toward, rationale)
    for item in inputs.structures:
        if item.invalidation_price is None:
            continue
        level = float(item.invalidation_price)
        if abs(level - last_price) / last_price * 100 > 15:
            continue  # too far away to be actionable
        if level < last_price:
            flips = "divest"
            rationale = f"Losing {item.title} level flips structure toward the bears"
        else:
            flips = "invest"
            rationale = f"Clearing {item.title} level flips structure toward the bulls"
        kind = "zone_edge" if item.structure_type.endswith("zone") else "structure_break"
        levels.append((level, kind, flips, rationale))

    # Deduplicate by rounded price, keep nearest few each side.
    seen: set[float] = set()
    unique = []
    for level, kind, flips, rationale in sorted(levels, key=lambda t: abs(t[0] - last_price)):
        key = round(level, 2)
        if key in seen:
            continue
        seen.add(key)
        unique.append(DecisionInvalidation(price=level, kind=kind, flips_toward=flips, rationale=rationale))

    below = [d for d in unique if d.price < last_price][:3]
    above = [d for d in unique if d.price >= last_price][:3]
    return below + above


# ── Walk-forward replay ────────────────────────────────────────────

def _light_pipeline(data: list[OHLCV], config: Config) -> tuple[list[PivotPoint], list[SwingLeg], list[StructureDiscovery], SummaryStatistics]:
    """Pivot/leg/structure/stats pipeline for a data suffix (no pattern engine)."""
    detector = ZigZagDetector(
        left_bars=config.left_bars,
        right_bars=config.right_bars,
        min_move_pct=config.min_move_pct,
        use_atr_filter=config.use_atr_filter,
        atr_period=config.atr_period,
        atr_multiplier=config.atr_multiplier,
    )
    pivots = detector.detect_pivots(data, config)
    if config.use_atr_filter:
        # Match the live pipeline: ATR filter + confirmation + alternation.
        from btc_cycle_tracker.pivots.filters import ATRFilter

        pivots = ATRFilter(
            atr_period=config.atr_period, atr_multiplier=config.atr_multiplier
        ).filter(pivots, data)
    pivots = confirm_pivots(pivots, data, config)
    legs = LegBuilder.build_legs_from_pivots(pivots, data)
    structures = discover_structures(data, pivots, config.min_move_pct)
    summary = calculate_summary_stats(legs, data)
    return pivots, legs, structures, summary


def run_decision_walk_forward(
    data: list[OHLCV],
    config: Config,
    memory=None,
    symbol: str = "",
    timeframe: str = "",
    config_hash: str = "",
) -> DecisionWalkForward | None:
    """Replay the scorecard at historical checkpoints with no lookahead.

    Each checkpoint uses only candles up to that point; the forward return
    is measured over ``horizon_bars`` after it. The pattern engine is
    excluded from replay (slow, and independently walk-forward tested), so
    replayed scores reflect structural + regime evidence only.

    Replay always scores with the FIXED baseline weights — never the
    adaptive ones — so it stays an honest out-of-sample baseline and cannot
    chase its own learning. When ``memory`` is given, each checkpoint is
    also logged (source="replay") and graded immediately against the
    already-known outcome, seeding the track record from day one.
    """
    checkpoints_wanted = config.decision_walk_forward_checkpoints
    if checkpoints_wanted <= 0 or len(data) < 300:
        return None

    horizon = max(24, len(data) // 24)
    warmup = max(config.left_bars + config.right_bars + 60, 150)

    first = warmup
    last = len(data) - horizon
    if last <= first:
        return None

    step = max(1, (last - first) // checkpoints_wanted)
    indices = list(range(first, last + 1, step))[:checkpoints_wanted]

    checkpoints: list[DecisionCheckpoint] = []
    for idx in indices:
        window = data[: idx + 1]
        pivots, legs, structures, summary = _light_pipeline(window, config)
        forming = LegBuilder.build_forming_leg(pivots, legs, window)
        inputs = DecisionInputs(
            pivots=pivots,
            legs=legs,
            summary=summary,
            structures=structures,
            forming_leg=forming,
        )
        brief = score_decision(inputs)  # baseline weights, always
        exit_index = min(idx + horizon, len(data) - 1)
        forward_close = data[exit_index].close
        forward_return = (forward_close / window[-1].close - 1) * 100 if window[-1].close else 0.0
        checkpoints.append(
            DecisionCheckpoint(
                timestamp=window[-1].timestamp,
                close=window[-1].close,
                score=brief.composite_score,
                action=brief.action,
                forward_return_pct=round(forward_return, 3),
            )
        )
        if memory is not None and symbol and timeframe:
            record = memory.log_replay_checkpoint(
                brief=brief,
                symbol=symbol,
                timeframe=timeframe,
                candle_timestamp=window[-1].timestamp,
                exit_timestamp=data[exit_index].timestamp,
                config_hash=config_hash,
            )
            memory.grade_one(record, data)

    # Band statistics: did invest-band calls actually precede up-moves?
    bands: dict[str, list[float]] = {}
    for cp in checkpoints:
        bands.setdefault(cp.action, []).append(cp.forward_return_pct or 0.0)
    band_stats: list[DecisionBandStat] = []
    order = [ACTION_STRONG_INVEST, ACTION_INVEST, ACTION_HOLD, ACTION_DIVEST, ACTION_STRONG_DIVEST]
    for action in order:
        if action not in bands:
            continue
        returns = bands[action]
        invest_side = action in {ACTION_INVEST, ACTION_STRONG_INVEST}
        aligned = [
            (r > 0) if invest_side else (r < 0) if action in {ACTION_DIVEST, ACTION_STRONG_DIVEST} else None
            for r in returns
        ]
        aligned_hits = [a for a in aligned if a is not None]
        band_stats.append(
            DecisionBandStat(
                action=action,
                count=len(returns),
                avg_forward_return_pct=round(sum(returns) / len(returns), 3) if returns else None,
                aligned_rate=round(sum(aligned_hits) / len(aligned_hits), 3) if aligned_hits else None,
            )
        )

    benchmark = (data[-1].close / data[indices[0]].close - 1) * 100 if data[indices[0]].close else None
    invest_avg = next((b.avg_forward_return_pct for b in band_stats if b.action == ACTION_INVEST), None)
    note = (
        f"Replayed {len(checkpoints)} historical checkpoints with a {horizon}-bar forward window. "
        "Scores use structural + regime evidence only (pattern engine excluded from replay). "
        "Read band stats against the naive drift, not against zero."
    )

    return DecisionWalkForward(
        horizon_bars=horizon,
        checkpoints=checkpoints,
        band_stats=band_stats,
        benchmark_return_pct=round(benchmark, 3) if benchmark is not None else None,
        note=note,
    )
