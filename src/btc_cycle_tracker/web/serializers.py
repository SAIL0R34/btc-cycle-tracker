"""Turn AnalysisResult objects into compact JSON payloads for the frontend."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from btc_cycle_tracker.analytics.intelligence import build_market_intelligence
from btc_cycle_tracker.models import AnalysisResult, Config, OHLCV

MAX_CANDLES_DEFAULT = 6000


def _iso(dt) -> str:
    return dt.isoformat() if dt is not None else ""


def serialize_candles(candles: list[OHLCV], max_candles: int = MAX_CANDLES_DEFAULT) -> list[dict]:
    """Serialize candles, resampling into OHLC buckets when the series is huge
    (a 1m × 30d run is ~43k rows — too heavy to ship and plot raw)."""
    if not candles:
        return []
    if len(candles) <= max_candles:
        return [
            {
                "t": _iso(c.timestamp),
                "o": c.open,
                "h": c.high,
                "l": c.low,
                "c": c.close,
                "v": c.volume,
            }
            for c in candles
        ]

    df = pd.DataFrame(
        {
            "timestamp": [c.timestamp for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
    ).set_index("timestamp")

    # Pick a bucket size that lands under max_candles.
    span = df.index[-1] - df.index[0]
    target_seconds = max(int(span.total_seconds() / max_candles), 60)
    rule = f"{target_seconds}s"
    out = (
        df.resample(rule)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open"])
    )
    return [
        {
            "t": _iso(ts),
            "o": row["open"],
            "h": row["high"],
            "l": row["low"],
            "c": row["close"],
            "v": row["volume"],
        }
        for ts, row in out.iterrows()
    ]


def serialize_result(
    result: AnalysisResult,
    max_candles: int = MAX_CANDLES_DEFAULT,
    include_candles: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "metadata": result.metadata.model_dump(mode="json"),
        "summary": result.summary.model_dump(mode="json"),
        "pivots": [p.model_dump(mode="json") for p in result.pivots],
        "legs": [leg.model_dump(mode="json") for leg in result.legs],
        "pattern_insight": result.pattern_insight.model_dump(mode="json") if result.pattern_insight else None,
        "pattern_learning": result.pattern_learning.model_dump(mode="json") if result.pattern_learning else None,
        "moon_phase_insight": result.moon_phase_insight.model_dump(mode="json") if result.moon_phase_insight else None,
        "correlations": {
            name: insight.model_dump(mode="json")
            for name, insight in (
                ("gold", result.gold_correlation_insight),
                ("nasdaq", result.nasdaq_correlation_insight),
                ("oil", result.oil_correlation_insight),
            )
            if insight is not None
        },
        "structure_discoveries": [d.model_dump(mode="json") for d in result.structure_discoveries],
        "forming_leg": result.forming_leg.model_dump(mode="json") if result.forming_leg else None,
        "decision_brief": result.decision_brief.model_dump(mode="json") if result.decision_brief else None,
        "correlation_errors": result.correlation_errors,
    }
    if include_candles:
        payload["candles"] = serialize_candles(result.raw_data, max_candles)
        payload["candles_resampled"] = len(result.raw_data) > max_candles
    return payload


def build_insight_context(result: Optional[AnalysisResult], config: Config) -> dict[str, Any]:
    """Compact dashboard context for the LLM insight / agent overview —
    the same idea as the Streamlit app's _build_qwen_screen_context."""
    ctx: dict[str, Any] = {
        "config": {
            "symbol": config.symbol,
            "timeframe": config.timeframe.value,
            "lookback": config.lookback_period,
            "pivot_method": config.pivot_method.value,
            "min_move_pct": config.min_move_pct,
            "atr_filter": config.use_atr_filter,
        },
    }
    if result is None:
        ctx["state"] = "no analysis has been run yet"
        return ctx

    meta = result.metadata
    summary = result.summary
    ctx["metadata"] = {
        "symbol": meta.symbol,
        "timeframe": meta.timeframe,
        "window": [_iso(meta.start_date), _iso(meta.end_date)],
        "candles": meta.total_candles,
        "pivots": meta.total_pivots,
        "legs": meta.total_legs,
    }
    ctx["summary"] = {
        "avg_percent_change": summary.avg_percent_change,
        "median_percent_change": summary.median_percent_change,
        "avg_duration_minutes": summary.avg_duration_minutes,
        "up_legs": summary.up_legs_count,
        "down_legs": summary.down_legs_count,
        "up_down_asymmetry": summary.up_down_asymmetry,
        "max_percent_change": summary.max_percent_change,
        "min_percent_change": summary.min_percent_change,
        "net_change_pct": summary.net_change_pct,
        "efficiency_ratio": summary.efficiency_ratio,
        "realized_vol_pct_per_bar": summary.realized_vol_pct_per_bar,
        "max_drawdown_pct": summary.max_drawdown_pct,
    }
    ctx["market_intelligence"] = build_market_intelligence(result)
    ctx["structure_discoveries"] = [
        {
            "type": item.structure_type,
            "title": item.title,
            "status": item.status,
            "direction": item.direction,
            "confidence": item.confidence,
            "evidence": item.evidence,
            "measurements": item.measurements,
            "invalidation_price": item.invalidation_price,
        }
        for item in result.structure_discoveries[:8]
    ]
    if result.legs:
        recent = result.legs[-5:]
        ctx["recent_legs"] = [
            {
                "direction": leg.direction,
                "pct": round(leg.percent_change, 2),
                "minutes": round(leg.duration_minutes, 1),
                "end": _iso(leg.end_timestamp),
            }
            for leg in recent
        ]
        ctx["last_price"] = result.legs[-1].end_price
    if result.forming_leg:
        fl = result.forming_leg
        ctx["forming_leg"] = {
            "direction": fl.direction,
            "pct_so_far": round(fl.percent_change, 2),
            "bars_so_far": fl.duration_bars,
            "from_price": fl.start_price,
            "last_price": fl.end_price,
            "note": "leg still forming after the last confirmed pivot",
        }
        ctx["last_price"] = fl.end_price
    if result.pattern_insight:
        pi = result.pattern_insight
        ctx["pattern"] = {
            "bias": pi.dominant_bias,
            "bullish_probability": pi.bullish_probability,
            "bearish_probability": pi.bearish_probability,
            "expected_next_change_pct": pi.expected_next_change_pct,
            "matches_used": pi.matches_used,
        }
    if result.moon_phase_insight:
        ctx["moon_phase"] = result.moon_phase_insight.model_dump(mode="json")
    if result.decision_brief:
        brief = result.decision_brief
        ctx["decision"] = {
            "action": brief.action,
            "composite_score": brief.composite_score,
            "conviction": brief.conviction,
            "quality": brief.quality,
            "summary": brief.summary,
            "contributions": [
                {"source": c.source, "stance": c.stance, "score": c.score, "rationale": c.rationale}
                for c in brief.contributions
            ],
            "invalidations": [i.model_dump(mode="json") for i in brief.invalidations],
            "conflicts": brief.conflicts,
        }
        if brief.track_record:
            tr = brief.track_record
            ctx["decision"]["track_record"] = {
                "graded_total": tr.graded_total,
                "alignment_rate": tr.alignment_rate,
                "live_graded": tr.live_graded,
                "replay_graded": tr.replay_graded,
                "pending": tr.pending,
                "invalidated_total": tr.invalidated_total,
                "calibration_factor": tr.calibration_factor,
                "source_multipliers": [
                    {"source": s.source, "multiplier": s.multiplier, "samples": s.samples,
                     "live": s.live_samples, "replay": s.replay_samples}
                    for s in tr.source_stats if s.samples
                ],
                "recent_graded": [
                    {"action": g.action, "fwd_pct": g.forward_return_pct,
                     "aligned": g.aligned, "invalidated": g.invalidated, "source": g.source}
                    for g in tr.recent_graded
                ],
                "note": tr.note,
            }
    return ctx
