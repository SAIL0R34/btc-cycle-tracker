"""Pattern recognition and adaptive learning for swing-leg sequences.

Methodology notes (v2)
----------------------
* **Signatures are self-normalising.** Move/duration buckets are derived
  from quartiles of the run's own leg distribution, so a signature encodes
  "small/medium/large *for this market and timeframe*" rather than fixed
  percent thresholds that silently break between a 5m and a 1d chart.
  Signatures carry a ``v2:`` prefix; memory written by the old absolute
  buckets is simply never matched again.
* **Naive baselines.** Zigzag legs alternate by construction, so the
  meaningful null model is *reversion* (predict the next leg opposite to
  the last one) plus the majority-direction baseline. The engine reports
  its own hit rate against both, so "61% accurate" can be read against the
  ~50% null instead of in isolation.
* **Smoothed hit rates.** Persisted hit rates use Laplace smoothing, so a
  2/2 bucket does not parade around as 100%.
* **Deduplicated memory.** Re-running overlapping lookbacks re-evaluates
  the same historical windows; identical outcomes are counted once so the
  adaptive confidence does not inflate on every run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from btc_cycle_tracker.models import (
    Config,
    PatternBacktestRecord,
    PatternInsight,
    PatternLearningSummary,
    PatternSequenceMatch,
    SwingLeg,
)
from btc_cycle_tracker.settings import settings

SIGNATURE_VERSION = "v2"


@dataclass(frozen=True)
class BucketEdges:
    """Quartile-derived cut points for move/duration bucketing."""

    move_q25: float
    move_q50: float
    move_q75: float
    duration_q25: float
    duration_q50: float
    duration_q75: float


def derive_bucket_edges(legs: list[SwingLeg]) -> BucketEdges:
    """Derive bucket edges from the run's own leg distribution.

    Falls back to absolute heuristics when the series is too short for
    meaningful quartiles.
    """
    amplitudes = [abs(leg.percent_change) for leg in legs]
    durations = [float(leg.duration_bars) for leg in legs]
    if len(legs) < 8:
        return BucketEdges(
            move_q25=1.5, move_q50=3.5, move_q75=6.0,
            duration_q25=12, duration_q50=36, duration_q75=96,
        )
    return BucketEdges(
        move_q25=_percentile(amplitudes, 0.25),
        move_q50=_percentile(amplitudes, 0.50),
        move_q75=_percentile(amplitudes, 0.75),
        duration_q25=_percentile(durations, 0.25),
        duration_q50=_percentile(durations, 0.50),
        duration_q75=_percentile(durations, 0.75),
    )


def _bucket_abs_change(abs_change: float, edges: BucketEdges) -> str:
    """Bucket a leg by amplitude relative to the run's distribution."""
    if abs_change < edges.move_q25:
        return "S"
    if abs_change < edges.move_q50:
        return "M"
    if abs_change < edges.move_q75:
        return "L"
    return "X"


def _bucket_duration(duration_bars: int, edges: BucketEdges) -> str:
    """Bucket a leg by duration relative to the run's distribution."""
    if duration_bars < edges.duration_q25:
        return "S"
    if duration_bars < edges.duration_q50:
        return "M"
    if duration_bars < edges.duration_q75:
        return "L"
    return "X"


def build_pattern_signature(legs: list[SwingLeg], edges: BucketEdges | None = None) -> str:
    """Encode a leg sequence into a compact, self-normalising signature."""
    if edges is None:
        edges = derive_bucket_edges(legs)
    directions = "".join("U" if leg.is_up else "D" for leg in legs)
    moves = "".join(_bucket_abs_change(abs(leg.percent_change), edges) for leg in legs)
    durations = "".join(_bucket_duration(leg.duration_bars, edges) for leg in legs)
    return f"{SIGNATURE_VERSION}:{directions}|{moves}|{durations}"


def _sequence_similarity(reference: list[SwingLeg], candidate: list[SwingLeg]) -> float:
    """Measure similarity between two leg sequences."""
    if len(reference) != len(candidate) or not reference:
        return 0.0

    score = 0.0
    for ref_leg, cand_leg in zip(reference, candidate):
        direction_score = 1.0 if ref_leg.direction == cand_leg.direction else 0.0

        ref_abs = abs(ref_leg.percent_change)
        cand_abs = abs(cand_leg.percent_change)
        change_scale = max(ref_abs, cand_abs, 1.0)
        change_score = max(0.0, 1.0 - abs(ref_abs - cand_abs) / change_scale)

        duration_scale = max(ref_leg.duration_bars, cand_leg.duration_bars, 1)
        duration_score = max(
            0.0,
            1.0 - abs(ref_leg.duration_bars - cand_leg.duration_bars) / duration_scale,
        )

        score += (0.45 * direction_score) + (0.35 * change_score) + (0.20 * duration_score)

    return score / len(reference)


def _signed_direction(change_pct: float) -> str:
    """Convert a change percentage into a direction label."""
    if change_pct > 0:
        return "up"
    if change_pct < 0:
        return "down"
    return "flat"


def _percentile(values: list[float], percentile: float) -> float | None:
    """Return an interpolated percentile for a numeric sample."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]

    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _smoothed_rate(correct: int, total: int, prior: float = 1.0) -> float:
    """Laplace-smoothed success rate — a 2/2 bucket is ~0.75, not 1.0."""
    if total <= 0:
        return 0.0
    return (correct + prior) / (total + 2.0 * prior)


def _safe_float_list(values: Any, limit: int = 250) -> list[float]:
    """Coerce persisted values into a bounded float list."""
    if not isinstance(values, list):
        return []
    coerced: list[float] = []
    for value in values[-limit:]:
        try:
            coerced.append(float(value))
        except (TypeError, ValueError):
            continue
    return coerced


def _derive_regime(legs: list[SwingLeg]) -> tuple[str, str]:
    """Classify the local market regime from recent swing-leg behavior."""
    if not legs:
        return "unknown", "Unknown regime"

    window = legs[-min(8, len(legs)) :]
    net_change = sum(leg.percent_change for leg in window)
    avg_abs_change = sum(abs(leg.percent_change) for leg in window) / len(window)
    down_moves = [leg.percent_change for leg in window if leg.percent_change < 0]
    downside_pressure = abs(sum(down_moves))

    if net_change > 3:
        trend_bucket = "uptrend"
        trend_label = "Uptrend"
    elif net_change < -3:
        trend_bucket = "downtrend"
        trend_label = "Downtrend"
    else:
        trend_bucket = "range"
        trend_label = "Range"

    if avg_abs_change >= 4:
        vol_bucket = "high_vol"
        vol_label = "high volatility"
    elif avg_abs_change >= 1.8:
        vol_bucket = "mid_vol"
        vol_label = "medium volatility"
    else:
        vol_bucket = "low_vol"
        vol_label = "low volatility"

    if downside_pressure >= 8:
        pressure_bucket = "deep_pullback"
        pressure_label = "deep pullback pressure"
    elif downside_pressure >= 3:
        pressure_bucket = "normal_pullback"
        pressure_label = "normal pullback pressure"
    else:
        pressure_bucket = "shallow_pullback"
        pressure_label = "shallow pullback pressure"

    return (
        f"{trend_bucket}|{vol_bucket}|{pressure_bucket}",
        f"{trend_label}, {vol_label}, {pressure_label}",
    )


@dataclass
class _MemoryStats:
    """Persisted learning stats for a pattern signature."""

    direction_correct: int = 0
    horizon_correct: int = 0
    total: int = 0
    next_changes: list[float] | None = None
    horizon_changes: list[float] | None = None
    next_durations: list[float] | None = None

    @property
    def direction_hit_rate(self) -> float:
        return _smoothed_rate(self.direction_correct, self.total)

    @property
    def horizon_hit_rate(self) -> float:
        return _smoothed_rate(self.horizon_correct, self.total)

    @property
    def median_next_change_pct(self) -> float | None:
        return median(self.next_changes) if self.next_changes else None

    @property
    def p25_next_change_pct(self) -> float | None:
        return _percentile(self.next_changes or [], 0.25)

    @property
    def p75_next_change_pct(self) -> float | None:
        return _percentile(self.next_changes or [], 0.75)

    @property
    def median_horizon_change_pct(self) -> float | None:
        return median(self.horizon_changes) if self.horizon_changes else None

    @property
    def p25_horizon_change_pct(self) -> float | None:
        return _percentile(self.horizon_changes or [], 0.25)

    @property
    def p75_horizon_change_pct(self) -> float | None:
        return _percentile(self.horizon_changes or [], 0.75)

    @property
    def median_next_duration_bars(self) -> float | None:
        return median(self.next_durations) if self.next_durations else None


def _outcome_key(record: PatternBacktestRecord) -> tuple:
    """Identity of a historical outcome — identical windows re-run later
    produce identical tuples and are only counted once in memory."""
    return (
        record.pattern_signature,
        record.regime_key,
        round(record.realized_next_change_pct, 4),
        round(record.realized_horizon_change_pct, 4),
        record.realized_next_duration_bars,
    )


class PatternLearningStore:
    """Persistent store for pattern-performance history across runs."""

    def __init__(self, output_dir: str):
        self.path = settings.resolve_app_path(output_dir) / "pattern_memory.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def stats_for(self, signature: str) -> _MemoryStats:
        raw = self._data.get(signature, {})
        return self._stats_from_raw(raw)

    def regime_stats_for(self, signature: str, regime_key: str) -> _MemoryStats:
        raw = self._data.get(signature, {})
        regimes = raw.get("regimes", {})
        if not isinstance(regimes, dict):
            regimes = {}
        regime_raw = regimes.get(regime_key, {})
        if not isinstance(regime_raw, dict):
            regime_raw = {}
        return self._stats_from_raw(regime_raw)

    @staticmethod
    def _stats_from_raw(raw: dict[str, Any]) -> _MemoryStats:
        return _MemoryStats(
            direction_correct=int(raw.get("direction_correct", 0)),
            horizon_correct=int(raw.get("horizon_correct", 0)),
            total=int(raw.get("total", 0)),
            next_changes=_safe_float_list(raw.get("next_change_pct")),
            horizon_changes=_safe_float_list(raw.get("horizon_change_pct")),
            next_durations=_safe_float_list(raw.get("next_duration_bars")),
        )

    def update(self, records: list[PatternBacktestRecord]) -> None:
        """Persist new backtest outcomes, counting each unique historical
        window only once (re-runs of overlapping lookbacks don't inflate)."""
        for record in records:
            signature_data = self._data.setdefault(
                record.pattern_signature,
                {"direction_correct": 0, "horizon_correct": 0, "total": 0, "seen": []},
            )
            if self._register_outcome(signature_data, record):
                signature_data["total"] += 1
                if record.was_direction_correct:
                    signature_data["direction_correct"] += 1
                if record.did_horizon_hold:
                    signature_data["horizon_correct"] += 1
                self._append_outcomes(signature_data, record)

            regimes = signature_data.setdefault("regimes", {})
            if not isinstance(regimes, dict):
                regimes = {}
                signature_data["regimes"] = regimes
            regime_data = regimes.setdefault(
                record.regime_key,
                {
                    "label": record.regime_label,
                    "direction_correct": 0,
                    "horizon_correct": 0,
                    "total": 0,
                    "seen": [],
                },
            )
            regime_data["label"] = record.regime_label
            if self._register_outcome(regime_data, record):
                regime_data["total"] += 1
                if record.was_direction_correct:
                    regime_data["direction_correct"] += 1
                if record.did_horizon_hold:
                    regime_data["horizon_correct"] += 1
                self._append_outcomes(regime_data, record)

        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))

    @staticmethod
    def _register_outcome(bucket: dict[str, Any], record: PatternBacktestRecord, limit: int = 1000) -> bool:
        """Return True (and remember) when this exact outcome is new."""
        key = _outcome_key(record)
        seen = bucket.get("seen")
        if not isinstance(seen, list):
            seen = []
            bucket["seen"] = seen
        if key in seen:
            return False
        seen.append(key)
        if len(seen) > limit:
            del seen[: len(seen) - limit]
        return True

    @staticmethod
    def _append_outcomes(
        bucket: dict[str, Any],
        record: PatternBacktestRecord,
        limit: int = 250,
    ) -> None:
        """Append bounded outcome distributions to a memory bucket."""
        bucket.setdefault("next_change_pct", []).append(record.realized_next_change_pct)
        bucket.setdefault("horizon_change_pct", []).append(record.realized_horizon_change_pct)
        bucket.setdefault("next_duration_bars", []).append(record.realized_next_duration_bars)
        for key in ["next_change_pct", "horizon_change_pct", "next_duration_bars"]:
            if isinstance(bucket.get(key), list):
                bucket[key] = bucket[key][-limit:]


class PatternRecognitionEngine:
    """Generate pattern insights and evaluate them through historical walk-forward tests."""

    def __init__(self, config: Config, output_dir: str):
        self.config = config
        self.store = PatternLearningStore(output_dir)

    def analyze(
        self,
        legs: list[SwingLeg],
        symbol: str,
        timeframe: str,
    ) -> tuple[PatternInsight | None, PatternLearningSummary | None, list[PatternBacktestRecord]]:
        """Run current-pattern inference and historical validation."""
        if not self.config.enable_pattern_recognition:
            return None, None, []

        pattern_length = self.config.pattern_length
        forecast_horizon = self.config.pattern_forecast_horizon
        if len(legs) < pattern_length + forecast_horizon + 1:
            return None, None, []

        edges = derive_bucket_edges(legs)
        backtests = self._run_walk_forward_backtest(legs, pattern_length, forecast_horizon, edges)
        if backtests:
            self.store.update(backtests)

        insight = self._current_insight(
            legs=legs,
            symbol=symbol,
            timeframe=timeframe,
            pattern_length=pattern_length,
            forecast_horizon=forecast_horizon,
            edges=edges,
        )
        current_regime_key, current_regime_label = _derive_regime(legs[:-pattern_length])
        learning_summary = self._summarize_learning(
            legs,
            backtests,
            insight.pattern_signature if insight else None,
            current_regime_key,
            current_regime_label,
        )

        return insight, learning_summary, backtests[-12:]

    def _find_matches(
        self,
        history_legs: list[SwingLeg],
        reference_window: list[SwingLeg],
        forecast_horizon: int,
    ) -> list[tuple[int, float]]:
        """Find the closest historical analogs for a reference sequence."""
        matches: list[tuple[int, float]] = []
        pattern_length = len(reference_window)

        for anchor in range(pattern_length, len(history_legs) - forecast_horizon + 1):
            candidate_window = history_legs[anchor - pattern_length : anchor]
            similarity = _sequence_similarity(reference_window, candidate_window)
            if similarity >= 0.55:
                matches.append((anchor, similarity))

        matches.sort(key=lambda item: item[1], reverse=True)
        return matches[: self.config.pattern_max_matches]

    def _build_insight_from_matches(
        self,
        reference_window: list[SwingLeg],
        history_legs: list[SwingLeg],
        matches: list[tuple[int, float]],
        forecast_horizon: int,
        memory_signature: str,
        edges: BucketEdges,
        regime_key: str = "unknown",
    ) -> PatternInsight | None:
        """Aggregate analog matches into a forward-looking insight."""
        if not matches:
            return None

        match_models: list[PatternSequenceMatch] = []
        total_weight = 0.0
        bullish_weight = 0.0
        bearish_weight = 0.0
        weighted_next_change = 0.0
        weighted_horizon_change = 0.0
        weighted_duration = 0.0
        weighted_similarity = 0.0
        next_changes: list[float] = []
        horizon_changes: list[float] = []

        for anchor, similarity in matches:
            next_leg = history_legs[anchor]
            horizon_legs = history_legs[anchor : anchor + forecast_horizon]
            horizon_change = sum(leg.percent_change for leg in horizon_legs)
            horizon_direction = _signed_direction(horizon_change)
            weight = max(similarity, 0.01)

            total_weight += weight
            weighted_similarity += similarity * weight
            weighted_next_change += next_leg.percent_change * weight
            weighted_horizon_change += horizon_change * weight
            weighted_duration += next_leg.duration_bars * weight
            next_changes.append(next_leg.percent_change)
            horizon_changes.append(horizon_change)

            if next_leg.is_up:
                bullish_weight += weight
            elif next_leg.is_down:
                bearish_weight += weight

            match_models.append(
                PatternSequenceMatch(
                    anchor_leg_id=next_leg.leg_id,
                    similarity_score=similarity,
                    match_signature=build_pattern_signature(
                        history_legs[anchor - len(reference_window) : anchor], edges
                    ),
                    next_direction=next_leg.direction,
                    next_change_pct=next_leg.percent_change,
                    next_duration_bars=next_leg.duration_bars,
                    horizon_change_pct=horizon_change,
                    horizon_direction=horizon_direction,
                )
            )

        bullish_probability = bullish_weight / total_weight if total_weight else 0.0
        bearish_probability = bearish_weight / total_weight if total_weight else 0.0
        dominant_bias = "bullish" if bullish_probability > bearish_probability else "bearish"
        if abs(bullish_probability - bearish_probability) < 0.1:
            dominant_bias = "balanced"

        base_confidence = (
            ((max(bullish_probability, bearish_probability) if total_weight else 0.0) + (weighted_similarity / total_weight))
            / 2
        )

        memory = self.store.stats_for(memory_signature)
        regime_memory = self.store.regime_stats_for(memory_signature, regime_key)
        adaptive_weight = min(1.0, memory.total / 25) if memory.total else 0.0
        memory_confidence = (memory.direction_hit_rate + memory.horizon_hit_rate) / 2
        if regime_memory.total >= 5:
            regime_confidence = (regime_memory.direction_hit_rate + regime_memory.horizon_hit_rate) / 2
            memory_confidence = (memory_confidence * 0.6) + (regime_confidence * 0.4)
        adaptive_confidence = (
            (1 - adaptive_weight) * base_confidence
            + adaptive_weight * memory_confidence
        )

        expected_next_change = weighted_next_change / total_weight
        expected_horizon_change = weighted_horizon_change / total_weight
        expected_duration = weighted_duration / total_weight
        next_p25 = _percentile(next_changes, 0.25)
        next_p75 = _percentile(next_changes, 0.75)
        horizon_p25 = _percentile(horizon_changes, 0.25)
        horizon_p75 = _percentile(horizon_changes, 0.75)
        summary = (
            f"Recent legs most closely resemble {len(match_models)} historical sequences. "
            f"The analog set leans {dominant_bias}, with an expected next-leg move of "
            f"{expected_next_change:+.2f}% (typical range {next_p25:+.2f}% to {next_p75:+.2f}%) "
            f"and a {forecast_horizon}-leg follow-through of {expected_horizon_change:+.2f}%."
            if next_p25 is not None and next_p75 is not None
            else (
                f"Recent legs most closely resemble {len(match_models)} historical sequences. "
                f"The analog set leans {dominant_bias}, with an expected next-leg move of "
                f"{expected_next_change:+.2f}% and a {forecast_horizon}-leg follow-through of "
                f"{expected_horizon_change:+.2f}%."
            )
        )

        return PatternInsight(
            pattern_signature=memory_signature,
            pattern_length=len(reference_window),
            forecast_horizon=forecast_horizon,
            matches_used=len(match_models),
            dominant_bias=dominant_bias,
            bullish_probability=bullish_probability,
            bearish_probability=bearish_probability,
            expected_next_change_pct=expected_next_change,
            expected_horizon_change_pct=expected_horizon_change,
            expected_next_duration_bars=expected_duration,
            next_change_p25_pct=next_p25,
            next_change_p75_pct=next_p75,
            horizon_change_p25_pct=horizon_p25,
            horizon_change_p75_pct=horizon_p75,
            base_confidence=base_confidence,
            adaptive_confidence=adaptive_confidence,
            historical_direction_hit_rate=memory.direction_hit_rate,
            historical_horizon_hit_rate=memory.horizon_hit_rate,
            summary=summary,
            matches=match_models,
        )

    def _current_insight(
        self,
        legs: list[SwingLeg],
        symbol: str,
        timeframe: str,
        pattern_length: int,
        forecast_horizon: int,
        edges: BucketEdges,
    ) -> PatternInsight | None:
        """Generate insight for the current trailing pattern."""
        reference_window = legs[-pattern_length:]
        matches = self._find_matches(legs, reference_window, forecast_horizon)
        signature = build_pattern_signature(reference_window, edges)
        regime_key, _ = _derive_regime(legs[:-pattern_length])
        return self._build_insight_from_matches(
            reference_window,
            legs,
            matches,
            forecast_horizon,
            signature,
            edges,
            regime_key,
        )

    def _run_walk_forward_backtest(
        self,
        legs: list[SwingLeg],
        pattern_length: int,
        forecast_horizon: int,
        edges: BucketEdges,
    ) -> list[PatternBacktestRecord]:
        """Evaluate pattern predictions on historical windows only using prior data."""
        records: list[PatternBacktestRecord] = []

        for anchor in range(pattern_length, len(legs) - forecast_horizon):
            history_before_anchor = legs[:anchor]
            reference_window = history_before_anchor[-pattern_length:]
            matches = self._find_matches(history_before_anchor[:-1], reference_window, forecast_horizon)
            signature = build_pattern_signature(reference_window, edges)
            regime_key, _ = _derive_regime(legs[: anchor - pattern_length])
            insight = self._build_insight_from_matches(
                reference_window=reference_window,
                history_legs=history_before_anchor,
                matches=matches,
                forecast_horizon=forecast_horizon,
                memory_signature=signature,
                edges=edges,
                regime_key=regime_key,
            )
            if insight is None:
                continue

            actual_next_leg = legs[anchor]
            realized_horizon_change = sum(leg.percent_change for leg in legs[anchor : anchor + forecast_horizon])
            predicted_direction = (
                "up"
                if insight.bullish_probability > insight.bearish_probability
                else "down"
                if insight.bullish_probability < insight.bearish_probability
                # near-tie: fall back to the expected move's sign
                else ("up" if insight.expected_next_change_pct >= 0 else "down")
            )
            predicted_horizon_direction = _signed_direction(insight.expected_horizon_change_pct)
            actual_horizon_direction = _signed_direction(realized_horizon_change)
            regime_key, regime_label = _derive_regime(legs[: anchor - pattern_length])

            records.append(
                PatternBacktestRecord(
                    anchor_leg_id=actual_next_leg.leg_id,
                    pattern_signature=signature,
                    predicted_direction=predicted_direction,
                    actual_direction=actual_next_leg.direction,
                    predicted_horizon_direction=predicted_horizon_direction,
                    actual_horizon_direction=actual_horizon_direction,
                    predicted_next_change_pct=insight.expected_next_change_pct,
                    confidence_score=insight.base_confidence,
                    adaptive_confidence=insight.adaptive_confidence,
                    was_direction_correct=predicted_direction == actual_next_leg.direction,
                    did_horizon_hold=predicted_horizon_direction == actual_horizon_direction,
                    realized_next_change_pct=actual_next_leg.percent_change,
                    realized_horizon_change_pct=realized_horizon_change,
                    realized_next_duration_bars=actual_next_leg.duration_bars,
                    regime_key=regime_key,
                    regime_label=regime_label,
                )
            )

        return records

    def _summarize_learning(
        self,
        legs: list[SwingLeg],
        backtests: list[PatternBacktestRecord],
        current_signature: str | None,
        current_regime_key: str,
        current_regime_label: str,
    ) -> PatternLearningSummary | None:
        """Summarize the learning state for the UI."""
        if not backtests and not current_signature:
            return None

        total_backtests = len(backtests)
        direction_hit_rate = (
            sum(record.was_direction_correct for record in backtests) / total_backtests
            if total_backtests
            else 0.0
        )
        horizon_hit_rate = (
            sum(record.did_horizon_hold for record in backtests) / total_backtests
            if total_backtests
            else 0.0
        )

        # Naive baselines computed on the same walk-forward anchors. Zigzag
        # legs alternate by construction, so "predict opposite of the last
        # leg" (reversion) is a very strong null — often ~100%. That is the
        # point: it exposes how much of the headline direction accuracy is
        # structural rather than learned. Majority-direction is the second
        # null. (legs are 1-based via leg_id; the previous leg sits at
        # anchor_leg_id - 2 in the 0-based list.)
        reversion_hits = 0
        for record in backtests:
            prev_index = record.anchor_leg_id - 2
            if 0 <= prev_index < len(legs):
                previous_leg = legs[prev_index]
                reversion_prediction = "down" if previous_leg.is_up else "up"
                if reversion_prediction == record.actual_direction:
                    reversion_hits += 1
        reversion_hit_rate = reversion_hits / total_backtests if total_backtests else 0.0

        direction_counts = {"up": 0, "down": 0}
        for record in backtests:
            if record.actual_direction in direction_counts:
                direction_counts[record.actual_direction] += 1
        majority_direction = max(direction_counts, key=direction_counts.get)
        majority_hit_rate = (
            direction_counts[majority_direction] / total_backtests if total_backtests else 0.0
        )
        best_baseline = max(reversion_hit_rate, majority_hit_rate)
        direction_edge = direction_hit_rate - best_baseline

        # Magnitude accuracy: mean absolute error between the expected and
        # realized next-leg percent change (in-run). With alternating legs
        # this — not direction — is where analog matching has to earn its
        # keep.
        magnitude_errors = [
            abs(record.predicted_next_change_pct - record.realized_next_change_pct)
            for record in backtests
            if record.predicted_next_change_pct is not None
        ]
        mean_abs_error = (
            sum(magnitude_errors) / len(magnitude_errors) if magnitude_errors else None
        )

        memory = self.store.stats_for(current_signature) if current_signature else _MemoryStats()
        regime_key = current_regime_key
        regime_label = current_regime_label
        regime_memory = (
            self.store.regime_stats_for(current_signature, regime_key)
            if current_signature
            else _MemoryStats()
        )
        adaptive_weight = min(1.0, memory.total / 25) if memory.total else 0.0
        if memory.total:
            note = (
                f"Confidence blends fresh pattern similarity with persisted hit rates "
                f"({memory.total} unique prior outcomes) and matching regime history. "
                f"Because zigzag legs alternate by construction, the horizon hit rate "
                f"and next-move error are the metrics that carry real signal; "
                f"next-leg direction alone is near-deterministic."
            )
        else:
            note = (
                "No persisted memory for this signature yet; the engine is learning from "
                "this run's backtest only."
            )

        return PatternLearningSummary(
            total_backtests=total_backtests,
            direction_hit_rate=direction_hit_rate,
            horizon_hit_rate=horizon_hit_rate,
            baseline_reversion_hit_rate=reversion_hit_rate,
            baseline_majority_hit_rate=majority_hit_rate,
            direction_edge_vs_baseline=direction_edge,
            mean_abs_error_next_change_pct=mean_abs_error,
            persistent_samples=memory.total,
            persistent_direction_hit_rate=memory.direction_hit_rate,
            persistent_horizon_hit_rate=memory.horizon_hit_rate,
            adaptive_weight=adaptive_weight,
            learning_note=note,
            regime_key=regime_key,
            regime_label=regime_label,
            regime_samples=regime_memory.total,
            regime_direction_hit_rate=regime_memory.direction_hit_rate,
            regime_horizon_hit_rate=regime_memory.horizon_hit_rate,
            median_next_change_pct=memory.median_next_change_pct,
            p25_next_change_pct=memory.p25_next_change_pct,
            p75_next_change_pct=memory.p75_next_change_pct,
            median_horizon_change_pct=memory.median_horizon_change_pct,
            p25_horizon_change_pct=memory.p25_horizon_change_pct,
            p75_horizon_change_pct=memory.p75_horizon_change_pct,
            median_next_duration_bars=memory.median_next_duration_bars,
        )
