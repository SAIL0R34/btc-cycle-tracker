"""Decision accountability: log briefs, grade them against outcomes, learn.

The loop
-------
1. **Log** every decision (live analysis runs and walk-forward replay
   checkpoints) with the grading horizon *frozen at log time* — the
   outcome window never depends on future config.
2. **Grade** a decision once, one-shot, when later candles cover its
   outcome window: realised forward return, whether an invalidation level
   was breached first, and an ``aligned`` verdict.
3. **Learn**: per-evidence-source alignment rates (Laplace-smoothed toward
   0.5, hard-capped) become multipliers on the scorecard weights, and the
   engine-level alignment calibrates conviction. Prior weight, learned
   multiplier, and sample counts are surfaced everywhere — the learning is
   auditable, not magic.
4. **Acknowledge**: the track record ships with every brief (UI + the AI
   narrative prompt), so each new call explicitly faces its own history.

Honesty guards
--------------
* Grading reads only candles up to each record's frozen due timestamp —
  no lookahead. (Replay backfill grades history with final data; live
  records do not have this caveat — the live/replay split is always shown.)
* The walk-forward replay itself always scores with the *fixed* baseline
  weights, so it remains an honest out-of-sample baseline and cannot chase
  its own tail.
* One-shot grading: the first verdict sticks; re-runs never revise it.
* Records are deduplicated by (source, symbol, timeframe, candle
  timestamp) — replaying the same window twice adds nothing.
"""

from __future__ import annotations

import json
import logging
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from pathlib import Path

from btc_cycle_tracker.models import (
    Config,
    DecisionBandStat,
    DecisionBrief,
    DecisionContribution,
    DecisionGradedItem,
    DecisionInvalidation,
    DecisionRecord,
    DecisionSourceStat,
    DecisionTrackRecord,
    OHLCV,
    SummaryStatistics,
)
from btc_cycle_tracker.settings import settings

logger = logging.getLogger("btc_cycle_tracker.analytics.decision_memory")

TIMEFRAME_DELTA: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}

LEARNING_PRIOR_STRENGTH = 10.0   # shrinkage toward 0.5 (samples needed to move)
MULTIPLIER_CAPS = (0.5, 1.5)
CALIBRATION_RANGE = (0.7, 1.2)
CONTRIB_EPS = 0.05                # |score| above this = the source actually contributed
MAX_RECORDS_DEFAULT = 1000
GRADE_EXIT_GAP_TOLERANCE = 3      # bars late for the exit candle before noting a gap
RECENT_GRADED_SHOWN = 8

_INVEST_ACTIONS = {"invest", "strong_invest"}
_DIVEST_ACTIONS = {"divest", "strong_divest"}


def _to_naive_utc(value: datetime) -> datetime:
    """Normalise tz-aware/naive datetimes so comparisons never raise."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def grading_horizon_bars(num_candles: int) -> int:
    """The grading horizon, matching the walk-forward replay's formula."""
    return max(24, num_candles // 24)


def hold_band_pct(summary: SummaryStatistics | None, horizon: int) -> float:
    """How far price may drift before a HOLD decision counts as wrong."""
    if summary is None or summary.realized_vol_pct_per_bar <= 0:
        return 1.0
    return _clamp(0.5 * summary.realized_vol_pct_per_bar * (horizon ** 0.5), 0.4, 6.0)


class DecisionMemoryStore:
    """JSON-persisted log of decisions and their graded outcomes."""

    def __init__(self, output_dir: str, max_records: int = MAX_RECORDS_DEFAULT):
        self.path: Path = settings.resolve_app_path(output_dir) / "decision_memory.json"
        self.max_records = max(100, max_records)
        self._records: list[DecisionRecord] = self._load()

    # ── Persistence ──────────────────────────────────────────────────

    def _load(self) -> list[DecisionRecord]:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text())
                records = [DecisionRecord.model_validate(r) for r in data.get("records", [])]
                return records[-self.max_records :]
        except Exception as exc:  # noqa: BLE001 - corrupt file shouldn't kill runs
            logger.warning("Ignoring corrupt decision memory (%s): %s", self.path, exc)
        return []

    def _save(self) -> None:
        self._trim()
        payload = {"version": 1, "records": [r.model_dump(mode="json") for r in self._records]}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(self.path)
        except Exception as exc:  # noqa: BLE001 - persistence is best-effort
            logger.warning("Could not persist decision memory: %s", exc)

    def _trim(self) -> None:
        """Bound the log, evicting the oldest *replay* records first —
        live history is irreplaceable, replay is re-seedable."""
        if len(self._records) <= self.max_records:
            return
        overflow = len(self._records) - self.max_records
        replay_indexes = [i for i, r in enumerate(self._records) if r.source == "replay"]
        for i in reversed(replay_indexes[:overflow]):
            del self._records[i]
        del self._records[: len(self._records) - self.max_records]

    # ── Logging ──────────────────────────────────────────────────────

    def log_live_decision(
        self,
        brief: DecisionBrief,
        symbol: str,
        timeframe: str,
        data: list[OHLCV],
        summary: SummaryStatistics | None,
        config_hash: str = "",
    ) -> DecisionRecord:
        """Log (or update) the decision made on the latest candle."""
        if not data:
            raise ValueError("Cannot log a decision without candles")
        candle_ts = _to_naive_utc(data[-1].timestamp)
        horizon = grading_horizon_bars(len(data))
        delta = TIMEFRAME_DELTA.get(timeframe, timedelta(minutes=5))
        record = DecisionRecord(
            decision_id=f"live|{symbol}|{timeframe}|{candle_ts.isoformat()}",
            symbol=symbol,
            timeframe=timeframe,
            source="live",
            logged_at=datetime.now(timezone.utc).replace(tzinfo=None),
            candle_timestamp=candle_ts,
            last_price=brief.last_price or float(data[-1].close),
            action=brief.action,
            composite_score=brief.composite_score,
            conviction=brief.conviction,
            quality=brief.quality,
            contributions=brief.contributions,
            invalidations=brief.invalidations,
            horizon_bars=horizon,
            grade_due_timestamp=candle_ts + horizon * delta,
            hold_band_pct=hold_band_pct(summary, horizon),
            config_hash=config_hash,
        )
        self._upsert(record)
        return record

    def log_replay_checkpoint(
        self,
        brief: DecisionBrief,
        symbol: str,
        timeframe: str,
        candle_timestamp: datetime,
        exit_timestamp: datetime,
        config_hash: str = "",
    ) -> DecisionRecord:
        """Backfill a replayed historical checkpoint (graded immediately)."""
        candle_ts = _to_naive_utc(candle_timestamp)
        record = DecisionRecord(
            decision_id=f"replay|{symbol}|{timeframe}|{candle_ts.isoformat()}",
            symbol=symbol,
            timeframe=timeframe,
            source="replay",
            logged_at=datetime.now(timezone.utc).replace(tzinfo=None),
            candle_timestamp=candle_ts,
            last_price=brief.last_price or 0.0,
            action=brief.action,
            composite_score=brief.composite_score,
            conviction=brief.conviction,
            quality=brief.quality,
            contributions=brief.contributions,
            invalidations=brief.invalidations,
            horizon_bars=0,  # replay exits are clamped; the exit stamp is the truth
            grade_due_timestamp=_to_naive_utc(exit_timestamp),
            config_hash=config_hash,
        )
        self._upsert(record)
        return record

    def _upsert(self, record: DecisionRecord) -> None:
        """Insert, or update decision fields in place (grading fields stick)."""
        for i, existing in enumerate(self._records):
            if existing.decision_id == record.decision_id:
                record.graded_at = existing.graded_at
                record.forward_return_pct = existing.forward_return_pct
                record.outcome_correct = existing.outcome_correct
                record.invalidated = existing.invalidated
                record.invalidation_breach_price = existing.invalidation_breach_price
                record.invalidation_breach_timestamp = existing.invalidation_breach_timestamp
                record.aligned = existing.aligned
                record.grade_note = existing.grade_note
                record.hold_band_pct = existing.hold_band_pct
                record.grade_due_timestamp = existing.grade_due_timestamp
                record.revision_count = existing.revision_count + 1
                self._records[i] = record
                self._save()
                return
        self._records.append(record)
        self._save()

    # ── Grading ──────────────────────────────────────────────────────

    def grade_pending(self, data: list[OHLCV], symbol: str, timeframe: str) -> int:
        """Grade every matured pending record for this pair. Returns graded count."""
        if not data:
            return 0
        timestamps = [_to_naive_utc(c.timestamp) for c in data]
        graded = 0
        for record in self._records:
            if record.symbol != symbol or record.timeframe != timeframe:
                continue
            if record.graded_at is not None:
                continue
            if grade_record(record, data, timestamps):
                graded += 1
        if graded:
            self._save()
        return graded

    @property
    def records(self) -> list[DecisionRecord]:
        return list(self._records)

    def grade_one(self, record: DecisionRecord, data: list[OHLCV]) -> bool:
        """Grade a single (usually just-logged replay) record and persist."""
        graded = grade_record(record, data)
        if graded:
            self._save()
        return graded


def grade_record(
    record: DecisionRecord,
    data: list[OHLCV],
    timestamps: list[datetime] | None = None,
) -> bool:
    """Grade one record in place against candles covering its outcome window.

    One-shot: already-graded records are never revised. Returns True if the
    record was graded by this call.
    """
    if record.graded_at is not None:
        return False
    if not data:
        return False
    if timestamps is None:
        timestamps = [_to_naive_utc(c.timestamp) for c in data]

    due = _to_naive_utc(record.grade_due_timestamp)
    if timestamps[-1] < due:
        return False  # outcome window not covered yet

    # Exit candle: first candle at/after the due timestamp.
    exit_index = bisect_left(timestamps, due)
    exit_index = min(exit_index, len(data) - 1)
    exit_candle = data[exit_index]
    exit_ts = timestamps[exit_index]

    timeframe_delta = TIMEFRAME_DELTA.get(record.timeframe, timedelta(minutes=5))
    note = ""
    if exit_ts - due > GRADE_EXIT_GAP_TOLERANCE * timeframe_delta:
        note = "delayed exit candle (data gap)"

    record.forward_return_pct = (
        round((float(exit_candle.close) / record.last_price - 1) * 100, 4)
        if record.last_price
        else None
    )

    # Invalidation scan over (decision candle, exit candle] — inclusive of
    # the exit candle, exclusive of the anchor (the call was made on its close).
    # Only structure_break levels flip the call; a zone edge being traded
    # into is expected market behaviour (entering a support/resistance area),
    # so zone touches are recorded as an informational note, not a failure.
    invalidated = False
    zone_touched = False
    anchor = _to_naive_utc(record.candle_timestamp)
    start_index = bisect_left(timestamps, anchor)
    for candle, ts in zip(data[start_index : exit_index + 1], timestamps[start_index : exit_index + 1]):
        if ts <= anchor:
            continue
        for inv in record.invalidations:
            level = float(inv.price)
            breached = (
                float(candle.low) <= level
                if level < record.last_price
                else float(candle.high) >= level
            )
            if not breached:
                continue
            if inv.kind == "structure_break":
                invalidated = True
                record.invalidation_breach_price = level
                record.invalidation_breach_timestamp = candle.timestamp
                break
            zone_touched = True
        if invalidated:
            break
    if zone_touched and not invalidated:
        note = (note + "; " if note else "") + "zone level traded into (informational, not a flip)"

    # Outcome by action: direction for invest/divest, staying put for hold.
    if record.forward_return_pct is None:
        outcome_correct = None
    elif record.action in _INVEST_ACTIONS:
        outcome_correct = record.forward_return_pct > 0
    elif record.action in _DIVEST_ACTIONS:
        outcome_correct = record.forward_return_pct < 0
    else:  # hold
        outcome_correct = abs(record.forward_return_pct) <= record.hold_band_pct

    record.outcome_correct = outcome_correct
    record.invalidated = invalidated
    record.aligned = bool(outcome_correct) and not invalidated
    record.grade_note = note
    record.graded_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return True


# ── Learning: adaptive weights + conviction calibration ───────────

def _pair_records(store: DecisionMemoryStore, symbol: str, timeframe: str) -> list[DecisionRecord]:
    return [
        r for r in store.records
        if r.symbol == symbol and r.timeframe == timeframe and r.graded_at is not None
    ]


def adaptive_weights(
    store: DecisionMemoryStore,
    symbol: str,
    timeframe: str,
    baseline_weights: dict[str, float],
    min_samples: int,
) -> tuple[dict[str, float] | None, list[DecisionSourceStat], float]:
    """Learned weight multipliers and conviction calibration.

    Per source, the alignment rate over records where that source actually
    contributed (|score| > eps, non-hold outcomes) is shrunk toward 0.5,
    doubled into a multiplier, and hard-capped. Weights renormalise to Σ100.
    Returns ``(None, stats, 1.0)`` until enough decisions are graded.
    """
    from btc_cycle_tracker.analytics.decision import ACTION_HOLD  # local import avoids cycle

    graded = _pair_records(store, symbol, timeframe)
    directional = [r for r in graded if r.action not in {ACTION_HOLD, "hold"}]

    hits: dict[str, int] = {s: 0 for s in baseline_weights}
    samples: dict[str, int] = {s: 0 for s in baseline_weights}
    live_samples: dict[str, int] = {s: 0 for s in baseline_weights}
    replay_samples: dict[str, int] = {s: 0 for s in baseline_weights}

    for record in directional:
        if record.forward_return_pct is None:
            continue
        fwd = record.forward_return_pct
        for contrib in record.contributions:
            source = contrib.source
            if source not in baseline_weights or abs(contrib.score) <= CONTRIB_EPS:
                continue
            samples[source] += 1
            if record.source == "live":
                live_samples[source] += 1
            else:
                replay_samples[source] += 1
            # Stance-vs-return sign. NOT gated on the invalidation flag: a
            # source can lean the right way and still get stopped out — the
            # invalidation penalty applies once, at decision level.
            if (contrib.score > 0 and fwd > 0) or (contrib.score < 0 and fwd < 0):
                hits[source] += 1

    prior = LEARNING_PRIOR_STRENGTH
    stats: list[DecisionSourceStat] = []
    effective: dict[str, float] = {}
    for source, base_weight in baseline_weights.items():
        rate = (hits[source] + 0.5 * prior) / (samples[source] + prior)
        multiplier = _clamp(2.0 * rate, *MULTIPLIER_CAPS)
        effective[source] = base_weight * multiplier
        stats.append(
            DecisionSourceStat(
                source=source,
                prior_weight=base_weight,
                multiplier=round(multiplier, 3),
                effective_weight=0.0,  # filled after renormalisation
                samples=samples[source],
                hits=hits[source],
                aligned_rate=round(rate, 3),
                live_samples=live_samples[source],
                replay_samples=replay_samples[source],
            )
        )

    total_effective = sum(effective.values())
    if total_effective <= 0:
        return None, stats, 1.0
    for stat in stats:
        stat.effective_weight = round(effective[stat.source] * 100.0 / total_effective, 2)

    # Engine-level alignment calibrates conviction (invalidation penalty
    # included — this is the engine's real track record).
    aligned_total = sum(1 for r in graded if r.aligned)
    engine_rate = (aligned_total + 0.5 * prior) / (len(graded) + prior)
    calibration = _clamp(0.5 + engine_rate, *CALIBRATION_RANGE)

    if len(graded) < min_samples:
        return None, stats, 1.0
    weights = {s: effective[s] * 100.0 / total_effective for s in effective}
    return weights, stats, calibration


def build_track_record(
    store: DecisionMemoryStore,
    symbol: str,
    timeframe: str,
    source_stats: list[DecisionSourceStat],
    calibration_factor: float,
) -> DecisionTrackRecord:
    """Assemble the graded-history summary shown in the UI and AI prompt."""
    pair_all = [
        r for r in store.records if r.symbol == symbol and r.timeframe == timeframe
    ]
    graded = [r for r in pair_all if r.graded_at is not None]
    pending = [r for r in pair_all if r.graded_at is None]

    aligned_total = sum(1 for r in graded if r.aligned)
    returns = [r.forward_return_pct for r in graded if r.forward_return_pct is not None]

    band_stats: list[DecisionBandStat] = []
    order = ["strong_invest", "invest", "hold", "divest", "strong_divest"]
    for action in order:
        rows = [r for r in graded if r.action == action]
        if not rows:
            continue
        action_returns = [r.forward_return_pct for r in rows if r.forward_return_pct is not None]
        invest_side = action in _INVEST_ACTIONS
        divest_side = action in _DIVEST_ACTIONS
        aligned_flags = [
            (r.aligned is True)
            if (invest_side or divest_side)
            else (r.outcome_correct is True)
            for r in rows
        ]
        band_stats.append(
            DecisionBandStat(
                action=action,
                count=len(rows),
                avg_forward_return_pct=(
                    round(sum(action_returns) / len(action_returns), 3) if action_returns else None
                ),
                aligned_rate=round(sum(aligned_flags) / len(aligned_flags), 3) if aligned_flags else None,
            )
        )

    recent = [
        DecisionGradedItem(
            candle_timestamp=r.candle_timestamp,
            action=r.action,
            source=r.source,
            composite_score=r.composite_score,
            forward_return_pct=r.forward_return_pct,
            aligned=r.aligned,
            invalidated=bool(r.invalidated),
        )
        for r in sorted(graded, key=lambda r: r.candle_timestamp)[-RECENT_GRADED_SHOWN:]
    ]

    prior = LEARNING_PRIOR_STRENGTH
    alignment_rate = (aligned_total + 0.5 * prior) / (len(graded) + prior) if graded else None
    live_graded = sum(1 for r in graded if r.source == "live")
    replay_graded = sum(1 for r in graded if r.source == "replay")

    note = (
        f"{len(graded)} graded decisions ({live_graded} live, {replay_graded} replay-seeded), "
        f"{len(pending)} pending outcome windows. Per-source multipliers are shrunk toward "
        f"neutral and capped at ×{MULTIPLIER_CAPS[0]}–×{MULTIPLIER_CAPS[1]}; conviction is "
        f"calibrated ×{calibration_factor:.2f} by the engine alignment rate."
        if graded
        else "No graded decisions yet — the track record fills as decisions mature."
    )

    return DecisionTrackRecord(
        graded_total=len(graded),
        aligned_total=aligned_total,
        alignment_rate=round(alignment_rate, 3) if alignment_rate is not None else None,
        invalidated_total=sum(1 for r in graded if r.invalidated),
        live_graded=live_graded,
        replay_graded=replay_graded,
        pending=len(pending),
        avg_forward_return_pct=round(sum(returns) / len(returns), 3) if returns else None,
        band_stats=band_stats,
        source_stats=source_stats,
        recent_graded=recent,
        calibration_factor=round(calibration_factor, 3),
        note=note,
    )
