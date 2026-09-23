"""Tests for the decision memory loop: log → grade → adapt → acknowledge."""

import math
from datetime import datetime, timedelta

import pytest

from btc_cycle_tracker.analytics.decision import (
    WEIGHTS,
    run_decision_walk_forward,
    score_decision,
    DecisionInputs,
)
from btc_cycle_tracker.analytics.decision_memory import (
    DecisionMemoryStore,
    adaptive_weights,
    build_track_record,
    grade_record,
    grading_horizon_bars,
    hold_band_pct,
)
from btc_cycle_tracker.models import (
    Config,
    DecisionBrief,
    DecisionInvalidation,
    DecisionRecord,
    OHLCV,
)

START = datetime(2026, 9, 23, 12, 0)


def _candles(direction: float = 1.0, bars: int = 600, start: datetime = START, drift: float = 0.03):
    out = []
    for i in range(bars):
        p = 100 + i * drift * direction + math.sin(i / 22) * 2.2
        out.append(OHLCV(timestamp=start + timedelta(hours=i), open=p, high=p + 0.9, low=p - 0.9, close=p, volume=10))
    return out


def _brief(action="invest", score=30.0, conviction=0.5, price=100.0, invalidations=(), sources=None):
    from btc_cycle_tracker.models import DecisionContribution
    contributions = [
        DecisionContribution(source=s, stance="invest", weight=w, score=w, rationale="test")
        for s, w in (sources or {"structure_trend": 22.0}).items()
    ]
    return DecisionBrief(
        action=action, composite_score=score, conviction=conviction, quality="moderate",
        summary="test brief", contributions=contributions,
        invalidations=[DecisionInvalidation(price=p, kind="structure_break", flips_toward="divest", rationale="test") for p in invalidations],
        last_price=price,
    )


def _live_record(store, data, brief=None, timeframe="1h", invalidations=()):
    brief = brief or _brief(invalidations=invalidations)
    return store.log_live_decision(brief, "BTC-USD", timeframe, data, None)


# ── Logging ────────────────────────────────────────────────────────────

def test_log_decision_dedup_updates_in_place(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles()
    _live_record(store, data, brief=_brief(score=10.0))
    _live_record(store, data, brief=_brief(score=40.0))  # re-run on same candles

    assert len(store.records) == 1
    record = store.records[0]
    assert record.revision_count == 1
    assert record.composite_score == 40.0


def test_horizon_frozen_at_log_time(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles(bars=600)
    record = _live_record(store, data)
    horizon = grading_horizon_bars(600)
    assert record.horizon_bars == horizon
    assert record.grade_due_timestamp == data[-1].timestamp + timedelta(hours=horizon)


# ── Grading ────────────────────────────────────────────────────────────

def test_grade_pending_immature_left_alone(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles()
    record = _live_record(store, data)
    # Fresh store, same (insufficient) data — nothing to grade.
    store.grade_pending(data, "BTC-USD", "1h")
    assert record.graded_at is None
    assert record.forward_return_pct is None


def test_grade_matured_invest_aligned_on_upside(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles()
    record = _live_record(store, data)
    horizon = record.horizon_bars
    # Later run with `horizon` extra rising candles.
    later = _candles(bars=600 + horizon + 5)
    store.grade_pending(later, "BTC-USD", "1h")
    assert record.graded_at is not None
    assert record.forward_return_pct > 0
    assert record.aligned is True


def test_grade_divest_by_sign(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles()
    _live_record(store, data, brief=_brief(action="divest", score=-30.0))
    record = store.records[0]
    later = _candles(bars=600 + record.horizon_bars + 5)  # market rose
    store.grade_pending(later, "BTC-USD", "1h")
    assert record.outcome_correct is False
    assert record.aligned is False


def test_grade_hold_within_band(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles()
    # Freeze a wide band so a small drift stays inside it.
    record = _live_record(store, data, brief=_brief(action="hold", score=0.0))
    record.hold_band_pct = 50.0
    later = _candles(bars=600 + record.horizon_bars + 5, drift=0.001)
    store.grade_pending(later, "BTC-USD", "1h")
    assert record.outcome_correct is True
    assert record.aligned is True


def test_grade_hold_outside_band(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles()
    record = _live_record(store, data, brief=_brief(action="hold", score=0.0))
    record.hold_band_pct = 0.01
    later = _candles(bars=600 + record.horizon_bars + 5, drift=0.3)  # big drift
    store.grade_pending(later, "BTC-USD", "1h")
    assert record.outcome_correct is False


def test_invalidation_breach_before_horizon_counts_against_alignment(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles()
    # Level far below current price, breached by a later crash candle.
    record = _live_record(store, data, brief=_brief(invalidations=(80.0,)))
    horizon = record.horizon_bars

    later_start = data[-1].timestamp + timedelta(hours=1)
    later = _candles(bars=horizon + 5, start=later_start, drift=-2.0)  # crash through 80 well inside the window
    store.grade_pending(data + later, "BTC-USD", "1h")

    assert record.invalidated is True
    assert record.invalidation_breach_price == 80.0
    assert record.aligned is False


def test_invalidation_breach_after_horizon_ignored(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles()
    record = _live_record(store, data, brief=_brief(invalidations=(95.0,)))
    horizon = record.horizon_bars

    # Rising window first (covers the outcome window, no breach)...
    quiet = _candles(bars=horizon + 2, start=data[-1].timestamp + timedelta(hours=1), drift=0.05)
    store.grade_pending(data + quiet, "BTC-USD", "1h")
    assert record.graded_at is not None
    assert record.invalidated is False
    # ...then a crash AFTER grading must not revise anything (one-shot).
    crash = _candles(bars=20, start=quiet[-1].timestamp + timedelta(hours=1), drift=-2.0)
    store.grade_pending(data + quiet + crash, "BTC-USD", "1h")
    assert record.invalidated is False
    assert record.aligned is True  # rose over the window without breaching


def test_grade_is_one_shot(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles()
    record = _live_record(store, data)
    later = _candles(bars=600 + record.horizon_bars + 5)
    store.grade_pending(later, "BTC-USD", "1h")
    first = (record.graded_at, record.forward_return_pct, record.aligned)

    even_later = _candles(bars=600 + record.horizon_bars + 50, drift=-0.5)
    assert grade_record(record, even_later) is False
    assert (record.graded_at, record.forward_return_pct, record.aligned) == first


def test_grade_only_matches_same_symbol_timeframe(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    data = _candles()
    record = _live_record(store, data, timeframe="1h")
    later = _candles(bars=600 + record.horizon_bars + 5)
    store.grade_pending(later, "BTC-USD", "5m")  # different timeframe
    assert record.graded_at is None


# ── Replay backfill ────────────────────────────────────────────────────

def test_replay_backfill_flags_source_and_grades(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    config = Config(timeframe="1h", use_atr_filter=False, decision_walk_forward_checkpoints=4)
    data = _candles(bars=500)

    wf = run_decision_walk_forward(data, config, memory=store, symbol="BTC-USD", timeframe="1h")

    replay_records = [r for r in store.records if r.source == "replay"]
    assert len(replay_records) == len(wf.checkpoints)
    assert all(r.graded_at is not None for r in replay_records)
    assert all(r.forward_return_pct is not None for r in replay_records)


def test_replay_backfill_dedup_across_runs(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    config = Config(timeframe="1h", use_atr_filter=False, decision_walk_forward_checkpoints=4)
    data = _candles(bars=500)

    run_decision_walk_forward(data, config, memory=store, symbol="BTC-USD", timeframe="1h")
    run_decision_walk_forward(data, config, memory=store, symbol="BTC-USD", timeframe="1h")

    assert len(store.records) == 4  # no growth from identical replay


def test_replay_ignores_adaptive_weights(tmp_path):
    # Learned multipliers must never leak into replay scoring.
    store = DecisionMemoryStore(str(tmp_path))
    config = Config(timeframe="1h", use_atr_filter=False, decision_walk_forward_checkpoints=3)
    data = _candles(bars=450)
    pure = run_decision_walk_forward(data, config)
    replayed = run_decision_walk_forward(
        data, config, memory=store, symbol="BTC-USD", timeframe="1h"
    )
    assert [c.score for c in pure.checkpoints] == [c.score for c in replayed.checkpoints]


# ── Adaptive weights + calibration ─────────────────────────────────────

def _graded_directional_record(store, timestamp, score_sign=1.0, fwd=5.0, action="invest", source="live"):
    from btc_cycle_tracker.models import DecisionContribution
    contributions = [
        DecisionContribution(source=s, stance="invest" if score_sign > 0 else "divest",
                             weight=w, score=score_sign * w, rationale="t")
        for s, w in WEIGHTS.items()
    ]
    record = DecisionRecord(
        decision_id=f"{source}|BTC-USD|1h|{timestamp.isoformat()}",
        symbol="BTC-USD", timeframe="1h", source=source,
        logged_at=timestamp, candle_timestamp=timestamp,
        last_price=100.0, action=action, composite_score=score_sign * 30,
        conviction=0.5, contributions=contributions, invalidations=[],
        horizon_bars=24, grade_due_timestamp=timestamp + timedelta(hours=24),
        graded_at=timestamp, forward_return_pct=fwd,
        outcome_correct=(fwd > 0) if action == "invest" else (fwd < 0),
        invalidated=False, aligned=(fwd > 0) if action == "invest" else (fwd < 0),
    )
    store._records.append(record)
    return record


def test_adaptive_weights_caps_shrinkage_renorm(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    base = datetime(2026, 1, 1)
    # 10 perfect invest calls (all sources hit) + 5 wrong ones.
    for i in range(10):
        _graded_directional_record(store, base + timedelta(hours=i), 1.0, fwd=4.0)
    for i in range(5):
        _graded_directional_record(store, base + timedelta(days=1, hours=i), 1.0, fwd=-4.0)

    weights, stats, calibration = adaptive_weights(store, "BTC-USD", "1h", WEIGHTS, min_samples=5)

    assert weights is not None
    by_source = {s.source: s for s in stats}
    good = by_source["structure_trend"]
    assert good.samples == 15 and good.hits == 10
    assert 1.0 < good.multiplier <= 1.5  # above neutral, capped
    zero = by_source["cross_asset"]  # contributed (nonzero score) in fixture
    assert zero.samples == 15
    assert sum(weights.values()) == pytest.approx(100.0, abs=0.01)
    assert 0.7 <= calibration <= 1.2


def test_adaptive_weights_zero_samples_is_neutral(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    weights, stats, _ = adaptive_weights(store, "BTC-USD", "1h", WEIGHTS, min_samples=0)
    by_source = {s.source: s for s in stats}
    assert by_source["structure_trend"].samples == 0
    assert by_source["structure_trend"].multiplier == 1.0  # shrunk to neutral


def test_adaptive_weights_count_only_contributing_sources(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    base = datetime(2026, 1, 1)
    for i in range(6):
        record = _graded_directional_record(store, base + timedelta(hours=i), 1.0, fwd=3.0)
        # Zero out cross_asset: it never contributed.
        record.contributions = [
            c.model_copy(update={"score": 0.0}) if c.source == "cross_asset" else c
            for c in record.contributions
        ]

    _, stats, _ = adaptive_weights(store, "BTC-USD", "1h", WEIGHTS, min_samples=5)
    by_source = {s.source: s for s in stats}
    assert by_source["cross_asset"].samples == 0
    assert by_source["structure_trend"].samples == 6


def test_min_samples_gate(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    _graded_directional_record(store, datetime(2026, 1, 1), 1.0, fwd=4.0)
    weights, _, calibration = adaptive_weights(store, "BTC-USD", "1h", WEIGHTS, min_samples=5)
    assert weights is None
    assert calibration == 1.0


def test_hold_outcome_excluded_from_per_source_learning(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    _graded_directional_record(store, datetime(2026, 1, 1), 1.0, fwd=4.0, action="hold")
    _, stats, _ = adaptive_weights(store, "BTC-USD", "1h", WEIGHTS, min_samples=1)
    assert all(s.samples == 0 for s in stats)


# ── score_decision integration ─────────────────────────────────────────

def _inputs():
    return DecisionInputs(summary=None)  # every source neutral — pure weight test


def test_score_decision_weights_injection_and_calibration():
    from btc_cycle_tracker.models import DecisionSourceStat, StructureDiscovery

    inputs = _inputs()
    default_brief = score_decision(inputs)
    assert default_brief.composite_score == 0.0

    # Double the invest-side structure weight, zero the rest.
    weights = {s: 0.0 for s in WEIGHTS}
    weights["structure_trend"] = 100.0
    # Give structure_trend something to say.
    inputs.structures = [StructureDiscovery(
        discovery_id="u1", structure_type="uptrend_structure", title="Rising",
        status="confirmed", direction="bullish", confidence=0.9,
        start_timestamp=START, end_timestamp=START,
    )]
    stats = [DecisionSourceStat(
        source="structure_trend", prior_weight=WEIGHTS["structure_trend"],
        multiplier=1.3, effective_weight=100.0, samples=20, hits=15,
    )]
    tilted = score_decision(inputs, weights=weights, source_stats=stats)
    assert tilted.composite_score > default_brief.composite_score
    trend = next(c for c in tilted.contributions if c.source == "structure_trend")
    assert trend.prior_weight == WEIGHTS["structure_trend"]
    assert trend.learned_multiplier == 1.3
    assert trend.alignment_samples == 20

    calibrated = score_decision(inputs, weights=weights, source_stats=stats, conviction_calibration=0.5)
    assert calibrated.conviction == pytest.approx(tilted.conviction * 0.5, abs=0.02)
    assert calibrated.conviction_uncalibrated is not None


# ── Track record + store robustness ────────────────────────────────────

def test_build_track_record_aggregates(tmp_path):
    store = DecisionMemoryStore(str(tmp_path))
    base = datetime(2026, 1, 1)
    _graded_directional_record(store, base, 1.0, fwd=4.0)
    _graded_directional_record(store, base + timedelta(hours=1), -1.0, fwd=-3.0, action="divest")
    pending = _live_record(store, _candles())  # ungraded live decision

    tr = build_track_record(store, "BTC-USD", "1h", [], 1.0)
    assert tr.graded_total == 2
    assert tr.aligned_total == 2
    assert tr.pending == 1
    assert tr.live_graded == 2
    assert len(tr.recent_graded) == 2


def test_store_tolerates_corrupt_file(tmp_path):
    bad = tmp_path / "decision_memory.json"
    bad.write_text("{not json at all")
    store = DecisionMemoryStore(str(tmp_path))
    assert store.records == []
    _live_record(store, _candles())
    reloaded = DecisionMemoryStore(str(tmp_path))
    assert len(reloaded.records) == 1


def test_store_bounded_prefers_live_records(tmp_path):
    store = DecisionMemoryStore(str(tmp_path), max_records=100)
    base = datetime(2026, 1, 1)
    for i in range(80):  # replay first, older
        record = _graded_directional_record(store, base + timedelta(minutes=i), source="replay")
    for i in range(80):  # live later, newer
        _graded_directional_record(store, base + timedelta(hours=1, minutes=i), source="live")
    store._save()

    reloaded = DecisionMemoryStore(str(tmp_path), max_records=100)
    sources = [r.source for r in reloaded.records]
    assert len(sources) <= 100
    assert sources.count("live") == 80  # live history fully retained


def test_hold_band_frozen_and_derived_from_vol():
    from btc_cycle_tracker.models import SummaryStatistics
    summary = SummaryStatistics(
        total_legs=10, avg_percent_change=0, avg_duration_minutes=0, avg_duration_bars=0,
        min_percent_change=0, max_percent_change=0, min_duration_minutes=0,
        max_duration_minutes=0, up_legs_count=5, down_legs_count=5,
        realized_vol_pct_per_bar=0.5,
    )
    band = hold_band_pct(summary, horizon=100)
    assert 0.4 <= band <= 6.0
    # sqrt scaling: 4x horizon → 2x band (within clamp)
    assert hold_band_pct(summary, horizon=400) == pytest.approx(min(band * 2, 6.0), abs=0.01)
