import asyncio
import base64
import html
import json
import math
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import plotly.graph_objects as go
import streamlit as st


from btc_cycle_tracker.export.csv_writer import CSVWriter
from btc_cycle_tracker.analytics.intelligence import build_market_intelligence
from btc_cycle_tracker.data.loaders import DataLoader
from btc_cycle_tracker.models import Config, PivotMethod, Timeframe
from btc_cycle_tracker.services.analysis_service import AnalysisService
from btc_cycle_tracker.settings import settings
from btc_cycle_tracker.app.components.charts import (
    add_structure_overlays,
    create_asset_correlation_chart,
    create_candlestick_chart as create_candlestick_chart_v2,
    create_duration_distribution_chart,
    create_leg_distribution_chart,
    create_pattern_learning_chart,
    create_pattern_probability_chart,
    create_summary_stats_chart,
)


DEFAULT_CONFIG = Config()
ALT_SIGNAL_KEYS = [
    "enable_moon_phase_analysis",
    "enable_gold_correlation_analysis",
    "enable_nasdaq_correlation_analysis",
    "enable_oil_correlation_analysis",
]

DEFAULT_SIDEBAR_STATE = {
    "symbol": DEFAULT_CONFIG.symbol,
    "timeframe": DEFAULT_CONFIG.timeframe.value,
    "lookback": DEFAULT_CONFIG.lookback_period,
    "pivot_method": DEFAULT_CONFIG.pivot_method.value,
    "min_move_pct": DEFAULT_CONFIG.min_move_pct,
    "left_bars": DEFAULT_CONFIG.left_bars,
    "right_bars": DEFAULT_CONFIG.right_bars,
    "use_atr": DEFAULT_CONFIG.use_atr_filter,
    "atr_period": DEFAULT_CONFIG.atr_period,
    "atr_multiplier": DEFAULT_CONFIG.atr_multiplier,
    "enable_pattern_recognition": DEFAULT_CONFIG.enable_pattern_recognition,
    "pattern_length": DEFAULT_CONFIG.pattern_length,
    "pattern_forecast_horizon": DEFAULT_CONFIG.pattern_forecast_horizon,
    "pattern_max_matches": DEFAULT_CONFIG.pattern_max_matches,
    "enable_moon_phase_analysis": DEFAULT_CONFIG.enable_moon_phase_analysis,
    "enable_gold_correlation_analysis": DEFAULT_CONFIG.enable_gold_correlation_analysis,
    "enable_nasdaq_correlation_analysis": DEFAULT_CONFIG.enable_nasdaq_correlation_analysis,
    "enable_oil_correlation_analysis": DEFAULT_CONFIG.enable_oil_correlation_analysis,
    "alt_signals_select_all": False,
    "app_theme": "Auto",
}

COMPARISON_STORE_FILENAME = "period_comparisons.json"
PREDICTION_JOURNAL_FILENAME = "prediction_journal.json"
QWEN_API_BASE_URL = os.environ.get("BTC_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
QWEN_MODEL = os.environ.get("BTC_LLM_MODEL", "auto")
QWEN_API_KEY = os.environ.get("BTC_LLM_API_KEY", "EMPTY")
QWEN_INSIGHT_TIMEOUT_SECONDS = float(os.environ.get("BTC_LLM_TIMEOUT_SECONDS", "120"))


GLOSSARY_ITEMS = [
    ("Swing High", "A local peak where price forms a meaningful high before reversing lower."),
    ("Swing Low", "A local trough where price forms a meaningful low before reversing higher."),
    ("Leg", "One move from a pivot to the next pivot."),
    ("Pivot", "A detected turning point used to build legs."),
    ("Pivot Method", "The rule set the app uses to decide where swing highs and swing lows should be placed."),
    ("ZigZag", "A reversal-based method that marks pivots when price moves far enough in the opposite direction. Good for filtering noise and emphasizing cleaner swing structure."),
    ("Fractal", "A local high/low method that compares a candle to surrounding candles on both sides. Good for finding more classical chart turning points."),
    ("Fixed Window", "A windowed comparison method that looks for highs and lows inside a chosen bar range. It is the most mechanical option and depends heavily on the left/right bar settings."),
    ("ATR Filter", "A volatility filter that suppresses pivots caused by small, noisy moves."),
    ("Pattern Signature", "A shorthand code describing the recent sequence of leg directions, move sizes, and durations."),
    ("UDU / DUD", "Direction codes. `U` means an up leg and `D` means a down leg."),
    ("Move Buckets", "`S` small, `M` medium, `L` large, `X` extra-large absolute percent moves."),
    ("Duration Buckets", "`S` short, `M` medium, `L` long, `X` extra-long leg durations measured in bars."),
    ("Pattern Length", "How many recent legs are encoded into the current pattern signature."),
    ("Forecast Horizon", "How many future legs the pattern engine evaluates after a match."),
    ("Analog Match", "A historical sequence that looks similar to the current pattern."),
    ("Current Bias", "Whether the matched historical patterns lean bullish, bearish, or balanced."),
    ("Expected Next Move", "The average next-leg percent change across the closest historical matches."),
    ("Expected Horizon Move", "The average combined percent change over the selected forecast horizon."),
    ("Base Confidence", "Confidence from the current analog matches alone."),
    ("Adaptive Confidence", "Confidence after blending current matches with persisted hit rates from past runs."),
    ("Direction Hit Rate", "How often the engine correctly predicted the next leg's direction in backtests."),
    ("Horizon Hit Rate", "How often the engine correctly predicted the multi-leg follow-through direction."),
    ("Adaptive Weight", "How much the persisted learning history influences the current confidence score."),
    ("Moon Phase Indicator", "An overlay of major lunar phases so you can compare BTC swings with lunar timing."),
    ("Major Moon Phases", "The app tracks New Moon, First Quarter, Full Moon, and Last Quarter events."),
    ("Phase Alignment Rate", "How often a major moon phase landed near a detected pivot within the adaptive time window."),
    ("Phase Bias", "Whether a given moon phase historically leaned bullish, bearish, or balanced in the next leg."),
    ("Gold Correlation Indicator", "A toggle reserved for comparing BTC swing behavior against gold once that signal is enabled."),
    ("Nasdaq Correlation Indicator", "A toggle for comparing BTC against the Nasdaq's daily regime and rolling correlation."),
    ("Oil Correlation Indicator", "A toggle for comparing BTC against crude oil and its rolling relationship."),
]


def _period_comparison_path(output_dir: str) -> Path:
    """Return the persisted period-comparison snapshot path."""
    return (settings.base_dir / output_dir / COMPARISON_STORE_FILENAME).resolve()


def _load_period_comparison_snapshots(output_dir: str) -> list[dict[str, Any]]:
    """Load saved period-comparison snapshots."""
    store_path = _period_comparison_path(output_dir)
    if not store_path.exists():
        return []

    try:
        payload = json.loads(store_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []

    snapshots = payload.get("snapshots", []) if isinstance(payload, dict) else []
    if not isinstance(snapshots, list):
        return []
    return [snapshot for snapshot in snapshots if isinstance(snapshot, dict)]


def _write_period_comparison_snapshots(
    output_dir: str,
    snapshots: list[dict[str, Any]],
) -> Path:
    """Persist period-comparison snapshots to disk."""
    store_path = _period_comparison_path(output_dir)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": snapshots,
    }
    store_path.write_text(json.dumps(payload, indent=2))
    return store_path


def _prediction_journal_path(output_dir: str) -> Path:
    """Return the persisted prediction journal path."""
    return (settings.base_dir / output_dir / PREDICTION_JOURNAL_FILENAME).resolve()


def _load_prediction_journal(output_dir: str) -> list[dict[str, Any]]:
    """Load saved prediction journal entries."""
    journal_path = _prediction_journal_path(output_dir)
    if not journal_path.exists():
        return []

    try:
        payload = json.loads(journal_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []

    predictions = payload.get("predictions", []) if isinstance(payload, dict) else []
    if not isinstance(predictions, list):
        return []
    return [prediction for prediction in predictions if isinstance(prediction, dict)]


def _write_prediction_journal(
    output_dir: str,
    predictions: list[dict[str, Any]],
) -> Path:
    """Persist prediction journal entries."""
    journal_path = _prediction_journal_path(output_dir)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "predictions": predictions,
    }
    journal_path.write_text(json.dumps(payload, indent=2))
    return journal_path


def _format_compact_dollars(value: float) -> str:
    """Format large dollar values compactly for the sidebar."""
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:,.2f}"


def _format_snapshot_time(raw_timestamp: str) -> str:
    """Render the fetched timestamp in US Eastern time."""
    if not raw_timestamp:
        return "Fetch time unavailable"

    try:
        normalized = raw_timestamp.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        eastern_time = parsed.astimezone(ZoneInfo("America/New_York"))
        return eastern_time.strftime("%Y-%m-%d %I:%M:%S %p %Z")
    except ValueError:
        return raw_timestamp


def _format_chart_as_of(raw_timestamp: datetime | str | None) -> str:
    """Render the latest chart candle timestamp in US Eastern time."""
    if raw_timestamp is None:
        return "Chart time unavailable"

    try:
        if isinstance(raw_timestamp, datetime):
            parsed = raw_timestamp
        else:
            normalized = str(raw_timestamp).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))

        eastern_time = parsed.astimezone(ZoneInfo("America/New_York"))
        return eastern_time.strftime("%Y-%m-%d %I:%M:%S %p %Z")
    except ValueError:
        return str(raw_timestamp)


def _coerce_utc_naive(value: datetime) -> datetime:
    """Normalize aware or naive datetimes into naive UTC datetimes."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@st.cache_data(ttl=3600, show_spinner=False)
def get_historical_btc_market_caps(days: int) -> list[dict[str, float | str]]:
    """Fetch historical BTC market caps from CoinGecko."""
    bounded_days = max(1, min(days, 3650))
    request = Request(
        f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={bounded_days}",
        headers={"User-Agent": "btc-swing-cycle-tracker/0.1.0"},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    market_caps = payload.get("market_caps", [])
    rows = []
    for item in market_caps:
        if len(item) < 2:
            continue
        timestamp_ms, market_cap = item[0], item[1]
        rows.append(
            {
                "timestamp": datetime.fromtimestamp(
                    float(timestamp_ms) / 1000,
                    tz=timezone.utc,
                ).replace(tzinfo=None),
                "market_cap": float(market_cap),
            }
        )
    return rows


def create_market_cap_bar_chart(
    result,
) -> go.Figure | None:
    """Create a historical BTC market cap bar chart from CoinGecko data."""
    if not result.raw_data:
        return None

    start = _coerce_utc_naive(result.metadata.start_date)
    end = _coerce_utc_naive(result.metadata.end_date)
    lookback_value = max(1, (end - start).days + 3)

    try:
        history_rows = get_historical_btc_market_caps(lookback_value)
    except Exception:
        return None

    filtered_rows = [
        row for row in history_rows
        if start <= _coerce_utc_naive(row["timestamp"]) <= end
    ]
    if not filtered_rows:
        return None

    fig = go.Figure(
        data=[
            go.Bar(
                x=[row["timestamp"] for row in filtered_rows],
                y=[row["market_cap"] for row in filtered_rows],
                marker_color="#f7931a",
                opacity=0.78,
                hovertemplate=(
                    "Time: %{x|%Y-%m-%d %H:%M}<br>"
                    "Market Cap: $%{y:,.0f}<extra></extra>"
                ),
                showlegend=False,
                name="Market Cap",
            )
        ]
    )
    fig.update_layout(
        title="BTC Market Cap",
        height=280,
        margin=dict(l=40, r=20, t=52, b=24),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.96)",
            bordercolor="rgba(0, 0, 0, 0.18)",
            font=dict(color="#000000"),
        ),
    )
    fig.update_yaxes(title_text="Market Cap", tickformat="$~s")
    return fig


def create_leg_story_chart(result) -> go.Figure:
    """Show each swing leg as a signed move bar with duration in hover text."""
    fig = go.Figure()
    legs = result.legs
    fig.add_trace(
        go.Bar(
            x=[f"Leg {leg.leg_id}" for leg in legs],
            y=[leg.percent_change for leg in legs],
            marker_color=[
                "#45c981" if leg.percent_change >= 0 else "#ff7768"
                for leg in legs
            ],
            customdata=[
                [
                    leg.direction.title(),
                    leg.duration_minutes,
                    leg.start_timestamp.strftime("%Y-%m-%d %H:%M"),
                    leg.end_timestamp.strftime("%Y-%m-%d %H:%M"),
                ]
                for leg in legs
            ],
            hovertemplate=(
                "%{x}<br>"
                "Direction: %{customdata[0]}<br>"
                "Move: %{y:+.2f}%<br>"
                "Duration: %{customdata[1]:.1f} min<br>"
                "%{customdata[2]} to %{customdata[3]}<extra></extra>"
            ),
            name="Leg Move",
        )
    )
    fig.add_hline(y=0, line_color="rgba(148, 163, 184, 0.55)", line_width=1)
    fig.update_layout(
        title="Swing Leg Moves",
        height=360,
        margin=dict(l=42, r=20, t=52, b=42),
        showlegend=False,
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Move (%)", ticksuffix="%")
    fig.update_xaxes(title_text="Detected Leg")
    return fig


def create_pivot_overview_chart(result) -> go.Figure:
    """Plot pivot prices over time with swing-high/swing-low color coding."""
    pivots = result.pivots
    fig = go.Figure()
    for pivot_type, label, color, symbol in [
        ("swing_high", "Swing High", "#f7931a", "triangle-down"),
        ("swing_low", "Swing Low", "#45c981", "triangle-up"),
    ]:
        rows = [
            pivot
            for pivot in pivots
            if str(pivot.pivot_type) == pivot_type
            or getattr(pivot.pivot_type, "value", "") == pivot_type
        ]
        fig.add_trace(
            go.Scatter(
                x=[pivot.timestamp for pivot in rows],
                y=[pivot.price for pivot in rows],
                mode="markers+lines",
                name=label,
                marker=dict(size=10, color=color, symbol=symbol),
                line=dict(color=color, width=1.4, dash="dot"),
                hovertemplate=f"{label}<br>%{{x|%Y-%m-%d %H:%M}}<br>$%{{y:,.2f}}<extra></extra>",
            )
        )
    fig.update_layout(
        title="Pivot Map",
        height=360,
        margin=dict(l=42, r=20, t=52, b=42),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Pivot Price", tickprefix="$")
    return fig


def create_pattern_matches_chart(insight) -> go.Figure:
    """Visualize analog match similarity and next-leg expectation."""
    fig = go.Figure()
    matches = insight.matches
    fig.add_trace(
        go.Bar(
            x=[f"Leg {match.anchor_leg_id}" for match in matches],
            y=[match.similarity_score * 100 for match in matches],
            marker_color=[
                "#45c981" if match.next_change_pct >= 0 else "#ff7768"
                for match in matches
            ],
            customdata=[
                [
                    match.next_direction.title(),
                    match.next_change_pct,
                    match.horizon_direction.title(),
                    match.horizon_change_pct,
                ]
                for match in matches
            ],
            hovertemplate=(
                "%{x}<br>"
                "Similarity: %{y:.1f}%<br>"
                "Next: %{customdata[0]} %{customdata[1]:+.2f}%<br>"
                "Horizon: %{customdata[2]} %{customdata[3]:+.2f}%<extra></extra>"
            ),
            name="Similarity",
        )
    )
    fig.update_layout(
        title="Closest Historical Analogs",
        height=340,
        margin=dict(l=42, r=20, t=52, b=42),
        showlegend=False,
    )
    fig.update_yaxes(title_text="Similarity (%)", range=[0, 100])
    return fig


def create_learning_outcomes_chart(learning) -> go.Figure:
    """Show learned next-leg and horizon outcome ranges."""
    fig = go.Figure()
    rows = [
        ("Next Leg", learning.p25_next_change_pct, learning.median_next_change_pct, learning.p75_next_change_pct),
        ("Horizon", learning.p25_horizon_change_pct, learning.median_horizon_change_pct, learning.p75_horizon_change_pct),
    ]
    for label, p25, median, p75 in rows:
        if p25 is None or median is None or p75 is None:
            continue
        fig.add_trace(
            go.Box(
                x=[label, label, label],
                y=[p25, median, p75],
                name=label,
                boxpoints="all",
                marker_color="#f7931a" if label == "Next Leg" else "#63a4ff",
                hovertemplate=f"{label}<br>%{{y:+.2f}}%<extra></extra>",
            )
        )
    fig.update_layout(
        title="Learned Outcome Range",
        height=320,
        margin=dict(l=42, r=20, t=52, b=42),
        showlegend=False,
    )
    fig.update_yaxes(title_text="Move (%)", ticksuffix="%")
    return fig


def create_moon_phase_bias_chart(moon) -> go.Figure:
    """Show moon phase alignment and next-leg bias by phase."""
    fig = go.Figure()
    stats = moon.phase_stats
    fig.add_trace(
        go.Bar(
            x=[stat.phase_name for stat in stats],
            y=[stat.alignment_rate * 100 for stat in stats],
            name="Alignment",
            marker_color="#f7931a",
            hovertemplate="%{x}<br>Alignment: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[stat.phase_name for stat in stats],
            y=[
                (stat.bullish_next_leg_rate - stat.bearish_next_leg_rate) * 100
                for stat in stats
            ],
            name="Bull/Bear Tilt",
            mode="lines+markers",
            line=dict(color="#63a4ff", width=2.4),
            yaxis="y2",
            hovertemplate="%{x}<br>Tilt: %{y:+.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title="Moon Phase Alignment And Bias",
        height=340,
        margin=dict(l=42, r=42, t=52, b=42),
        yaxis=dict(title="Alignment (%)", ticksuffix="%"),
        yaxis2=dict(
            title="Bull/Bear Tilt",
            overlaying="y",
            side="right",
            ticksuffix="%",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )
    return fig


def _build_qwen_screen_context(result, config: Config) -> dict[str, Any]:
    """Build the same compact context a user sees on the dashboard."""
    recent_legs = result.legs[-5:]
    latest_candle = result.raw_data[-1] if result.raw_data else None
    live_snapshot = get_live_btc_market_snapshot()
    context: dict[str, Any] = {
        "screen": "BTC Swing Cycle Tracker results dashboard",
        "symbol": result.metadata.symbol,
        "timeframe": result.metadata.timeframe,
        "lookback": config.lookback_period,
        "pivot_method": result.metadata.pivot_method,
        "analysis_window": {
            "start": result.metadata.start_date.isoformat(),
            "end": result.metadata.end_date.isoformat(),
            "latest_chart_time": (
                latest_candle.timestamp.isoformat()
                if latest_candle is not None
                else None
            ),
            "latest_close": float(latest_candle.close) if latest_candle is not None else None,
        },
        "summary": {
            "total_candles": result.metadata.total_candles,
            "total_pivots": result.metadata.total_pivots,
            "total_legs": result.metadata.total_legs,
            "avg_leg_change_pct": result.summary.avg_percent_change,
            "avg_duration_minutes": result.summary.avg_duration_minutes,
            "up_legs": result.summary.up_legs_count,
            "down_legs": result.summary.down_legs_count,
            "up_avg_change_pct": result.summary.up_legs_avg_change,
            "down_avg_change_pct": result.summary.down_legs_avg_change,
            "min_leg_change_pct": result.summary.min_percent_change,
            "max_leg_change_pct": result.summary.max_percent_change,
        },
        "latest_swing_legs": [
            {
                "id": leg.leg_id,
                "direction": leg.direction,
                "start": leg.start_timestamp.isoformat(),
                "end": leg.end_timestamp.isoformat(),
                "start_price": leg.start_price,
                "end_price": leg.end_price,
                "change_pct": leg.percent_change,
                "duration_minutes": leg.duration_minutes,
            }
            for leg in recent_legs
        ],
    }

    if live_snapshot is not None:
        context["sidebar_live_btc"] = {
            "price": live_snapshot.get("price"),
            "volume_24h": live_snapshot.get("volume_24h"),
            "market_cap": live_snapshot.get("market_cap"),
            "as_of": live_snapshot.get("as_of"),
        }

    if result.pattern_insight is not None:
        insight = result.pattern_insight
        context["pattern"] = {
            "signature": insight.pattern_signature,
            "bias": insight.dominant_bias,
            "adaptive_confidence": insight.adaptive_confidence,
            "expected_next_change_pct": insight.expected_next_change_pct,
            "expected_horizon_change_pct": insight.expected_horizon_change_pct,
            "matches_used": insight.matches_used,
            "summary": insight.summary,
        }

    if result.pattern_learning is not None:
        learning = result.pattern_learning
        context["learning"] = {
            "direction_hit_rate": learning.direction_hit_rate,
            "horizon_hit_rate": learning.horizon_hit_rate,
            "persistent_samples": learning.persistent_samples,
            "regime_label": learning.regime_label,
            "regime_samples": learning.regime_samples,
            "note": learning.learning_note,
        }

    if result.moon_phase_insight is not None:
        moon = result.moon_phase_insight
        context["moon_phase"] = {
            "alignment_rate": moon.alignment_rate,
            "avg_hours_to_pivot": moon.avg_hours_to_pivot,
            "strongest_phase": moon.strongest_phase,
            "strongest_bias": moon.strongest_bias,
            "summary": moon.summary,
        }

    correlation_context = []
    for insight in [
        result.gold_correlation_insight,
        result.nasdaq_correlation_insight,
        result.oil_correlation_insight,
    ]:
        if insight is None:
            continue
        correlation_context.append(
            {
                "asset": insight.asset_name,
                "symbol": insight.asset_symbol,
                "return_correlation": insight.return_correlation,
                "latest_rolling_correlation": insight.latest_rolling_correlation,
                "relative_strength_pct": insight.latest_relative_strength_pct,
                "summary": insight.summary,
            }
        )
    if correlation_context:
        context["correlations"] = correlation_context

    context["market_intelligence"] = build_market_intelligence(result)

    return context


def _qwen_context_key(context: dict[str, Any]) -> str:
    """Create a stable cache key for the current visible dashboard context."""
    return json.dumps(context, sort_keys=True, default=str)


@st.cache_data(ttl=90, show_spinner=False)
def get_qwen_realtime_insight(context_key: str) -> str:
    """Ask the configured AI gateway for an operator-friendly dashboard read."""
    context = json.loads(context_key)
    prompt = (
        "You are integrated inside a BTC swing-cycle analysis dashboard. "
        "The user can already see the chart, KPIs, pattern panels, and optional overlays. "
        "Use only the supplied dashboard context. Do not invent prices, dates, or signals. "
        "Treat market_intelligence as the primary evidence brief. Separate observed swing structure "
        "from historical pattern evidence, mention conflicts, and calibrate claims to its quality label. "
        "Preserve structure detector status exactly; confidence is evidence strength rather than outcome probability, "
        "and invalidation_price is only a detector invalidation level. "
        "Be concise, calm, and useful. This is not financial advice. "
        "Return compact markdown with these four headings: "
        "**Current read**, **What matters**, **Watch next**, **Caveats**. "
        "Use 1-2 short bullets under each heading. Prefer plain language over trading jargon."
    )
    body = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "Here is the current dashboard state as JSON:\n\n"
                    f"{json.dumps(context, separators=(',', ':'))}"
                ),
            },
        ],
        "temperature": 0.25,
        "max_tokens": 420,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = Request(
        f"{QWEN_API_BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {QWEN_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=QWEN_INSIGHT_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI gateway returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError("AI gateway is currently unreachable") from exc

    choices = payload.get("choices", [])
    if not choices:
        raise RuntimeError("AI gateway returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not content:
        content = message.get("reasoning", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("AI gateway returned an empty insight.")
    return content.strip()


def render_qwen_insight_panel(result, config: Config) -> None:
    """Render the provider-neutral assistant panel for the current dashboard."""
    context = _build_qwen_screen_context(result, config)
    context_key = _qwen_context_key(context)
    st.header("AI Live Read")
    st.caption(
        "The assistant receives the same dashboard context shown here: setup, summary, recent legs, pattern read, and enabled overlays."
    )

    action_col, status_col = st.columns([1, 3])
    with action_col:
        refresh = st.button("Refresh AI insight", type="primary")
    with status_col:
        st.write("Connected through the automatic AI gateway")

    if refresh:
        get_qwen_realtime_insight.clear()

    try:
        with st.spinner("AI is reading the current chart context..."):
            insight_text = get_qwen_realtime_insight(context_key)
    except Exception as exc:
        st.warning(f"AI insight unavailable: {exc}")
        with st.expander("Dashboard context prepared for the assistant", expanded=False):
            st.json(context)
        return

    st.markdown(insight_text)
    with st.expander("Dashboard context sent to the assistant", expanded=False):
        st.json(context)


def _date_bounds_from_result(result) -> tuple[date, date] | None:
    """Return safe date bounds for the loaded result candles."""
    timestamps = [candle.timestamp for candle in result.raw_data if candle.timestamp]
    if not timestamps:
        return None
    return min(timestamps).date(), max(timestamps).date()


def _datetime_bounds_from_result(result) -> tuple[datetime, datetime] | None:
    """Return safe datetime bounds for the loaded result candles."""
    timestamps = [
        _coerce_utc_naive(candle.timestamp)
        for candle in result.raw_data
        if candle.timestamp
    ]
    if not timestamps:
        return None
    return min(timestamps), max(timestamps)


def _filter_candles_by_window(
    candles: list[Any],
    start_date: date,
    start_time: time,
    end_date: date,
    end_time: time,
) -> list[Any]:
    """Filter candles inclusively by a calendar date/time window."""
    start_dt = datetime.combine(start_date, start_time)
    end_dt = datetime.combine(end_date, end_time)
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    return [
        candle
        for candle in candles
        if candle.timestamp and start_dt <= _coerce_utc_naive(candle.timestamp) <= end_dt
    ]


def _max_drawdown_pct(closes: list[float]) -> float:
    """Calculate max peak-to-trough drawdown for a close series."""
    if not closes:
        return 0.0

    peak = closes[0]
    max_drawdown = 0.0
    for close in closes:
        peak = max(peak, close)
        if peak:
            max_drawdown = min(max_drawdown, ((close - peak) / peak) * 100)
    return max_drawdown


def _calculate_period_metrics(candles: list[Any]) -> dict[str, Any]:
    """Calculate frozen comparison metrics for one selected period."""
    if not candles:
        return {
            "candles": 0,
            "start": None,
            "end": None,
            "start_close": None,
            "end_close": None,
            "total_return_pct": None,
            "high": None,
            "low": None,
            "range_pct": None,
            "max_drawdown_pct": None,
            "avg_candle_return_pct": None,
            "positive_candle_rate": None,
        }

    closes = [float(candle.close) for candle in candles]
    highs = [float(candle.high) for candle in candles]
    lows = [float(candle.low) for candle in candles]
    candle_returns = [
        ((closes[index] - closes[index - 1]) / closes[index - 1]) * 100
        for index in range(1, len(closes))
        if closes[index - 1]
    ]
    positive_returns = [value for value in candle_returns if value > 0]
    start_close = closes[0]
    end_close = closes[-1]
    high = max(highs)
    low = min(lows)

    return {
        "candles": len(candles),
        "start": candles[0].timestamp.isoformat(),
        "end": candles[-1].timestamp.isoformat(),
        "start_close": start_close,
        "end_close": end_close,
        "total_return_pct": ((end_close - start_close) / start_close) * 100 if start_close else 0.0,
        "high": high,
        "low": low,
        "range_pct": ((high - low) / start_close) * 100 if start_close else 0.0,
        "max_drawdown_pct": _max_drawdown_pct(closes),
        "avg_candle_return_pct": (
            sum(candle_returns) / len(candle_returns)
            if candle_returns
            else 0.0
        ),
        "positive_candle_rate": (
            len(positive_returns) / len(candle_returns)
            if candle_returns
            else 0.0
        ),
    }


def _serialize_period_candles(candles: list[Any]) -> list[dict[str, float | str]]:
    """Serialize candles with normalized close values for static review."""
    if not candles:
        return []

    base_close = float(candles[0].close) or 1.0
    return [
        {
            "timestamp": candle.timestamp.isoformat(),
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(candle.volume),
            "normalized_close": (float(candle.close) / base_close) * 100,
            "return_from_start_pct": ((float(candle.close) - base_close) / base_close) * 100,
            "bar_index": index,
            "progress_pct": (index / (len(candles) - 1)) * 100 if len(candles) > 1 else 0,
        }
        for index, candle in enumerate(candles)
    ]


def _resample_series(values: list[float], points: int = 100) -> list[float]:
    """Linearly resample a numeric series to a fixed number of points."""
    if not values:
        return []
    if len(values) == 1:
        return [values[0]] * points
    if points <= 1:
        return [values[0]]

    max_index = len(values) - 1
    resampled = []
    for point in range(points):
        position = (point / (points - 1)) * max_index
        left = int(math.floor(position))
        right = min(left + 1, max_index)
        weight = position - left
        resampled.append(values[left] * (1 - weight) + values[right] * weight)
    return resampled


def _pearson_correlation(series_a: list[float], series_b: list[float]) -> float | None:
    """Calculate Pearson correlation for two equal-length series."""
    if len(series_a) != len(series_b) or len(series_a) < 2:
        return None

    mean_a = sum(series_a) / len(series_a)
    mean_b = sum(series_b) / len(series_b)
    numerator = sum((a - mean_a) * (b - mean_b) for a, b in zip(series_a, series_b))
    denom_a = math.sqrt(sum((a - mean_a) ** 2 for a in series_a))
    denom_b = math.sqrt(sum((b - mean_b) ** 2 for b in series_b))
    denominator = denom_a * denom_b
    if denominator == 0:
        return None
    return numerator / denominator


def _build_period_comparison_snapshot(
    *,
    result,
    period_a_candles: list[Any],
    period_b_candles: list[Any],
    label: str,
    notes: str,
) -> dict[str, Any]:
    """Create a self-contained comparison snapshot."""
    period_a_rows = _serialize_period_candles(period_a_candles)
    period_b_rows = _serialize_period_candles(period_b_candles)
    series_a = _resample_series([float(row["normalized_close"]) for row in period_a_rows])
    series_b = _resample_series([float(row["normalized_close"]) for row in period_b_rows])
    shape_correlation = _pearson_correlation(series_a, series_b)
    metrics_a = _calculate_period_metrics(period_a_candles)
    metrics_b = _calculate_period_metrics(period_b_candles)
    return_delta = None
    drawdown_delta = None
    if metrics_a["total_return_pct"] is not None and metrics_b["total_return_pct"] is not None:
        return_delta = metrics_a["total_return_pct"] - metrics_b["total_return_pct"]
    if metrics_a["max_drawdown_pct"] is not None and metrics_b["max_drawdown_pct"] is not None:
        drawdown_delta = metrics_a["max_drawdown_pct"] - metrics_b["max_drawdown_pct"]

    created_at = datetime.now(timezone.utc).isoformat()
    safe_id = created_at.replace(":", "").replace("+", "Z")
    return {
        "id": f"comparison-{safe_id}",
        "label": label.strip() or f"Comparison saved {created_at}",
        "notes": notes.strip(),
        "created_at": created_at,
        "analysis_context": {
            "symbol": result.metadata.symbol,
            "timeframe": result.metadata.timeframe,
            "pivot_method": result.metadata.pivot_method,
            "lookback_start": result.metadata.start_date.isoformat(),
            "lookback_end": result.metadata.end_date.isoformat(),
            "analysis_run_timestamp": result.metadata.run_timestamp.isoformat(),
            "config_hash": result.metadata.config_hash,
        },
        "metrics": {
            "shape_correlation": shape_correlation,
            "return_delta_pct": return_delta,
            "max_drawdown_delta_pct": drawdown_delta,
        },
        "period_a": {
            "name": "Period A",
            "metrics": metrics_a,
            "candles": period_a_rows,
        },
        "period_b": {
            "name": "Period B",
            "metrics": metrics_b,
            "candles": period_b_rows,
        },
    }


def create_period_comparison_chart(snapshot: dict[str, Any]) -> go.Figure:
    """Create a normalized static chart for a saved or draft comparison."""
    fig = go.Figure()
    for key, label, color in [
        ("period_a", "Period A", "#f7931a"),
        ("period_b", "Period B", "#2c7be5"),
    ]:
        rows = snapshot.get(key, {}).get("candles", [])
        fig.add_trace(
            go.Scatter(
                x=[row["progress_pct"] for row in rows],
                y=[row["normalized_close"] for row in rows],
                mode="lines",
                name=label,
                line=dict(color=color, width=2.7),
                customdata=[
                    [row["timestamp"], row["close"], row["return_from_start_pct"]]
                    for row in rows
                ],
                hovertemplate=(
                    "Progress: %{x:.1f}%<br>"
                    "Normalized: %{y:.2f}<br>"
                    "Close: $%{customdata[1]:,.2f}<br>"
                    "Return: %{customdata[2]:+.2f}%<br>"
                    "Time: %{customdata[0]}<extra></extra>"
                ),
            )
        )

    corr = snapshot.get("metrics", {}).get("shape_correlation")
    title_corr = f" | Shape Corr {corr:+.2f}" if isinstance(corr, (int, float)) else ""
    fig.update_layout(
        title=f"Normalized Period Comparison{title_corr}",
        height=440,
        margin=dict(l=45, r=24, t=58, b=42),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )
    fig.update_xaxes(title_text="Period Progress (%)", range=[0, 100])
    fig.update_yaxes(title_text="Close Indexed To 100")
    return fig


def _format_optional_pct(value: Any, digits: int = 2) -> str:
    """Format optional percentage values for comparison displays."""
    if not isinstance(value, (int, float)):
        return "N/A"
    return f"{value:+.{digits}f}%"


def _format_optional_corr(value: Any) -> str:
    """Format optional correlation values."""
    if not isinstance(value, (int, float)):
        return "N/A"
    return f"{value:+.2f}"


def _ensure_date_input_state(
    key: str,
    default_value: date,
    min_value: date,
    max_value: date,
) -> None:
    """Clamp persisted Streamlit date widget state to the current data bounds."""
    current_value = st.session_state.get(key)
    if not isinstance(current_value, date) or current_value < min_value or current_value > max_value:
        st.session_state[key] = default_value


def _parse_optional_float(raw_value: str) -> float | None:
    """Parse optional numeric text input."""
    value = raw_value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _build_prediction_entry(
    *,
    result,
    direction: str,
    horizon_end: datetime,
    confidence: int,
    expected_move_pct: float | None,
    thesis: str,
    invalidation: str,
) -> dict[str, Any]:
    """Create a static prediction journal entry from the current chart context."""
    latest_candle = result.raw_data[-1]
    pattern = result.pattern_insight
    created_at = datetime.now(timezone.utc).isoformat()
    safe_id = created_at.replace(":", "").replace("+", "Z")
    return {
        "id": f"prediction-{safe_id}",
        "created_at": created_at,
        "status": "open",
        "symbol": result.metadata.symbol,
        "timeframe": result.metadata.timeframe,
        "base_time": latest_candle.timestamp.isoformat(),
        "base_price": float(latest_candle.close),
        "horizon_end": horizon_end.isoformat(),
        "prediction_direction": direction,
        "confidence_pct": confidence,
        "expected_move_pct": expected_move_pct,
        "thesis": thesis.strip(),
        "invalidation": invalidation.strip(),
        "pattern_signature": pattern.pattern_signature if pattern else None,
        "pattern_bias": pattern.dominant_bias if pattern else None,
        "pattern_adaptive_confidence": pattern.adaptive_confidence if pattern else None,
        "resolved_at": None,
        "resolution": None,
        "actual_return_pct": None,
        "actual_direction": None,
        "resolution_notes": "",
    }


def _prediction_auto_outcome(prediction: dict[str, Any], result) -> dict[str, Any] | None:
    """Infer an unresolved prediction outcome from currently loaded candles."""
    try:
        horizon_end = datetime.fromisoformat(str(prediction["horizon_end"]))
        base_price = float(prediction["base_price"])
    except (KeyError, TypeError, ValueError):
        return None

    matching_candles = [
        candle
        for candle in result.raw_data
        if candle.timestamp and _coerce_utc_naive(candle.timestamp) >= _coerce_utc_naive(horizon_end)
    ]
    if not matching_candles or not base_price:
        return None

    outcome_candle = matching_candles[0]
    actual_return = ((float(outcome_candle.close) - base_price) / base_price) * 100
    actual_direction = "up" if actual_return > 0 else "down" if actual_return < 0 else "flat"
    predicted_direction = str(prediction.get("prediction_direction", "")).lower()
    confirmed = (
        (predicted_direction == "bullish" and actual_direction == "up")
        or (predicted_direction == "bearish" and actual_direction == "down")
        or (predicted_direction == "sideways" and abs(actual_return) < 0.5)
    )
    return {
        "outcome_time": outcome_candle.timestamp.isoformat(),
        "outcome_price": float(outcome_candle.close),
        "actual_return_pct": actual_return,
        "actual_direction": actual_direction,
        "suggested_resolution": "confirmed" if confirmed else "denied",
    }


@st.cache_data(ttl=60, show_spinner=False)
def get_live_btc_market_snapshot() -> dict[str, float | str] | None:
    """Fetch a lightweight live BTC snapshot for the sidebar."""
    try:
        ticker_request = Request(
            "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
            headers={"User-Agent": "btc-swing-cycle-tracker/0.1.0"},
        )
        with urlopen(ticker_request, timeout=10) as response:
            ticker_payload = json.loads(response.read().decode("utf-8"))

        market_request = Request(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_market_cap=true&include_24hr_vol=true",
            headers={"User-Agent": "btc-swing-cycle-tracker/0.1.0"},
        )
        with urlopen(market_request, timeout=10) as response:
            market_payload = json.loads(response.read().decode("utf-8"))

        bitcoin = market_payload.get("bitcoin", {})
        return {
            "price": float(ticker_payload["price"]),
            "volume_24h": float(bitcoin["usd_24h_vol"]),
            "market_cap": float(bitcoin["usd_market_cap"]),
            "as_of": ticker_payload.get("time", ""),
        }
    except Exception:
        return None


def render_live_btc_sidebar_card() -> None:
    """Render the live BTC snapshot at the top of the sidebar."""
    refresh_col, spacer_col = st.columns([1, 5])
    with refresh_col:
        if st.button("↻", key="refresh_live_btc_snapshot"):
            get_live_btc_market_snapshot.clear()
            st.rerun()
    with spacer_col:
        st.empty()

    snapshot = get_live_btc_market_snapshot()
    if snapshot is None:
        return

    price_text = _format_compact_dollars(float(snapshot["price"]))
    volume_text = _format_compact_dollars(float(snapshot["volume_24h"]))
    market_cap_text = _format_compact_dollars(float(snapshot["market_cap"]))
    fetched_at_text = _format_snapshot_time(str(snapshot.get("as_of", "")))

    st.markdown(
        f"""
        <div class="btc-live-card">
          <div class="btc-live-label">BTC Live</div>
          <div class="btc-live-price">{price_text}</div>
          <div class="btc-live-meta">24h Vol {volume_text} · Mkt Cap {market_cap_text}</div>
          <div class="btc-live-time">Fetched {fetched_at_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()


@st.cache_data(ttl=60, show_spinner=False)
def get_pre_analysis_preview_data(
    symbol: str,
    timeframe: str,
    lookback: str,
) -> list[dict[str, float | str]]:
    """Fetch lightweight market data for the empty-state preview chart."""
    loader = DataLoader()
    candles = asyncio.run(loader.fetch_and_load(symbol, timeframe, lookback, use_cache=False))
    return [
        {
            "timestamp": candle.timestamp.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in candles
    ]


def create_pre_analysis_preview_chart(
    preview_rows: list[dict[str, float | str]],
    symbol: str,
    timeframe: str,
    lookback: str,
) -> go.Figure:
    """Create a normal candlestick chart for the pre-analysis page state."""
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=[row["timestamp"] for row in preview_rows],
            open=[row["open"] for row in preview_rows],
            high=[row["high"] for row in preview_rows],
            low=[row["low"] for row in preview_rows],
            close=[row["close"] for row in preview_rows],
            name=symbol,
            increasing_line_color="#2ecc71",
            decreasing_line_color="#e74c3c",
            showlegend=False,
        )
    )
    fig.update_layout(
        title=f"{symbol} Price Preview ({timeframe}, {lookback})",
        height=560,
        xaxis_rangeslider_visible=False,
        margin=dict(l=35, r=20, t=58, b=36),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.96)",
            bordercolor="rgba(0, 0, 0, 0.18)",
            font=dict(color="#000000"),
        ),
    )
    fig.update_yaxes(title_text="Price")
    return fig


def render_glossary() -> None:
    """Render a plain-English glossary for analytics terms and acronyms."""
    st.subheader("Glossary")
    for term, definition in GLOSSARY_ITEMS:
        st.write(f"**{term}:** {definition}")


def inject_sidebar_button_styles() -> None:
    """Center sidebar action buttons and their labels."""
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"]:has(.sidebar-action-anchor) div[data-testid="stElementContainer"],
        section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"]:has(.sidebar-action-anchor) div[data-testid="stElementContainer"] {
            width: 100% !important;
        }

        section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"]:has(.sidebar-action-anchor) div[data-testid="stButton"],
        section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"]:has(.sidebar-action-anchor) div[data-testid="stButton"] {
            display: flex;
            justify-content: center;
            width: 100%;
        }

        section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"]:has(.sidebar-action-anchor) div[data-testid="stButton"] > div,
        section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"]:has(.sidebar-action-anchor) div[data-testid="stButton"] > div {
            width: 100%;
            display: flex;
            justify-content: center;
        }

        section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"]:has(.sidebar-action-anchor) div[data-testid="stButton"] > button,
        section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"]:has(.sidebar-action-anchor) div[data-testid="stButton"] > button {
            width: min(12rem, 100%);
            justify-content: center;
            text-align: center;
            margin-left: auto;
            margin-right: auto;
        }

        section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"]:has(.sidebar-action-anchor) div[data-testid="stButton"] button[kind],
        section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"]:has(.sidebar-action-anchor) div[data-testid="stButton"] button[kind] {
            width: min(12rem, 100%);
            justify-content: center;
            text-align: center;
            margin-left: auto;
            margin-right: auto;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_app_styles() -> None:
    """Add shared layout styles for centered summary tiles."""
    st.html(
        """
        <style>
        header[data-testid="stHeader"] {
            background: transparent !important;
        }

        @media (min-width: 901px) {
            header[data-testid="stHeader"] {
                display: none !important;
                height: 0 !important;
                min-height: 0 !important;
            }

            header[data-testid="stHeader"] > div {
                display: none !important;
            }

            section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"],
            section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"] > button {
                visibility: visible !important;
            }

            section[data-testid="stSidebar"] div[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {
                color: #ffffff !important;
            }
        }

        [data-testid="stMainBlockContainer"] {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }

        [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
            gap: 0 !important;
            padding-top: 0 !important;
            margin-top: 0 !important;
        }

        section[data-testid="stSidebar"] {
            border-right: 1px solid rgba(148, 163, 184, 0.14);
        }

        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            letter-spacing: -0.01em;
        }

        section[data-testid="stSidebar"] hr {
            margin: 1rem 0;
            opacity: 0.28;
        }

        section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"] {
            background: #f7931a !important;
            border-color: #f7931a !important;
            color: #141414 !important;
            font-weight: 700 !important;
        }

        section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"]:hover {
            background: #ffad3b !important;
            border-color: #ffad3b !important;
        }

        .btc-live-card {
            padding: 0.7rem 0 0.9rem;
            text-align: left;
        }

        .btc-live-label,
        .workspace-kicker,
        .context-label {
            font-size: 0.72rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            opacity: 0.64;
        }

        .btc-live-price {
            margin-top: 0.16rem;
            font-size: 1.7rem;
            font-weight: 760;
            line-height: 1.05;
            letter-spacing: -0.03em;
        }

        .btc-live-meta {
            margin-top: 0.34rem;
            font-size: 0.82rem;
            opacity: 0.76;
        }

        .btc-live-time {
            margin-top: 0.24rem;
            font-size: 0.72rem;
            opacity: 0.62;
        }

        .hero-parallax-shell {
            position: relative;
            min-height: clamp(230px, 34vh, 360px);
            margin: 0 calc(50% - 50vw) 1.35rem;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            isolation: isolate;
            background: #060b14;
        }

        .hero-parallax-media {
            position: absolute;
            inset: -6%;
            background-size: cover;
            background-position: center center;
            background-repeat: no-repeat;
            transform: scale(1.12);
            transform-origin: center center;
            filter: saturate(1.08) contrast(1.04);
            z-index: 0;
        }

        .hero-parallax-grid {
            position: absolute;
            inset: 0;
            background:
                linear-gradient(rgba(255, 185, 61, 0.07) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255, 185, 61, 0.07) 1px, transparent 1px);
            background-size: 64px 64px;
            mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.32), rgba(0, 0, 0, 0.9));
            z-index: 1;
        }

        .hero-parallax-frost {
            position: absolute;
            inset: 0;
            opacity: 0;
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.28) 0%, rgba(255, 255, 255, 0.12) 34%, rgba(255, 255, 255, 0.2) 100%);
            backdrop-filter: blur(3px) saturate(1.02);
            transition: opacity 220ms ease;
            z-index: 2;
            pointer-events: none;
        }

        .hero-parallax-shell::after {
            content: "";
            position: absolute;
            inset: 0;
            background:
                linear-gradient(90deg, rgba(6, 10, 19, 0.94) 0%, rgba(6, 10, 19, 0.74) 46%, rgba(6, 10, 19, 0.2) 100%),
                linear-gradient(180deg, rgba(6, 10, 19, 0.28) 0%, rgba(6, 10, 19, 0.8) 100%);
            z-index: 3;
        }

        .hero-parallax-content {
            position: relative;
            z-index: 4;
            width: min(1180px, calc(100vw - 4rem));
            margin: 0 auto;
            padding: 2.3rem 0;
            color: #f7f4ea;
            text-align: left;
        }

        @media (min-width: 901px) {
            .hero-parallax-content {
                width: min(980px, calc(100vw - 25rem));
                margin-left: 24rem;
                margin-right: auto;
            }
        }

        .hero-parallax-kicker {
            font-size: 0.8rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: rgba(255, 218, 137, 0.86);
            margin-bottom: 0.85rem;
        }

        .hero-parallax-content h1 {
            margin: 0;
            font-size: clamp(2.2rem, 4vw, 4.2rem);
            line-height: 0.98;
            font-weight: 800;
            letter-spacing: -0.035em;
            text-shadow: 0 16px 42px rgba(0, 0, 0, 0.35);
        }

        .hero-parallax-content p {
            width: min(690px, 92%);
            margin: 0.9rem 0 0;
            font-size: clamp(0.98rem, 1.35vw, 1.12rem);
            line-height: 1.55;
            color: rgba(244, 239, 225, 0.88);
        }

        .hero-parallax-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.6rem;
            justify-content: flex-start;
            margin-top: 1.1rem;
        }

        .hero-parallax-tags span {
            padding: 0.48rem 0.78rem;
            border: 1px solid rgba(255, 220, 143, 0.22);
            background: rgba(12, 18, 28, 0.42);
            border-radius: 8px;
            font-size: 0.86rem;
            color: rgba(255, 244, 213, 0.92);
            backdrop-filter: blur(10px);
        }

        .workspace-status-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.6rem;
            margin-top: 1.2rem;
        }

        .workspace-status {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.48rem 0.68rem;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: rgba(250, 245, 235, 0.9);
            font-size: 0.84rem;
        }

        .workspace-status strong {
            font-weight: 700;
        }

        .context-strip {
            max-width: 1180px;
            margin: 0 auto 1.15rem;
            padding: 0.84rem 0;
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0;
            border-top: 1px solid rgba(148, 163, 184, 0.22);
            border-bottom: 1px solid rgba(148, 163, 184, 0.22);
        }

        .context-item {
            padding: 0 1rem;
            border-right: 1px solid rgba(148, 163, 184, 0.16);
        }

        .context-item:last-child {
            border-right: 0;
        }

        .context-value {
            margin-top: 0.18rem;
            font-size: 0.96rem;
            font-weight: 700;
            letter-spacing: -0.01em;
        }

        .section-note {
            max-width: 1180px;
            margin: 0 auto 1rem;
            font-size: 0.95rem;
            opacity: 0.74;
        }

        .footer-parallax-shell {
            position: relative;
            min-height: clamp(190px, 30vh, 280px);
            margin: 2.2rem calc(50% - 50vw) -1rem;
            overflow: hidden;
            display: flex;
            align-items: flex-end;
            justify-content: center;
            isolation: isolate;
            background: #05080f;
        }

        .footer-parallax-media {
            position: absolute;
            inset: -7%;
            background-size: cover;
            background-position: center center;
            background-repeat: no-repeat;
            transform: scale(1.1);
            transform-origin: center center;
            filter: saturate(1.03) contrast(1.05) brightness(0.84);
            z-index: 0;
        }

        .footer-parallax-frost {
            position: absolute;
            inset: 0;
            opacity: 0;
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.24) 0%, rgba(255, 255, 255, 0.1) 42%, rgba(255, 255, 255, 0.22) 100%);
            backdrop-filter: blur(3px) saturate(1.02);
            transition: opacity 220ms ease;
            z-index: 1;
            pointer-events: none;
        }

        .footer-parallax-shell::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                linear-gradient(180deg, rgba(5, 8, 15, 0.2) 0%, rgba(5, 8, 15, 0.62) 52%, rgba(5, 8, 15, 0.92) 100%);
            z-index: 2;
        }

        .footer-parallax-shell::after {
            content: "";
            position: absolute;
            inset: auto 0 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255, 204, 115, 0.58), transparent);
            z-index: 4;
        }

        .footer-parallax-content {
            position: relative;
            z-index: 3;
            width: min(980px, calc(100vw - 4rem));
            padding: 0 0 2.5rem 0;
            text-align: center;
            color: #f5edda;
        }

        .footer-parallax-eyebrow {
            font-size: 0.78rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: rgba(255, 215, 131, 0.82);
            margin-bottom: 0.65rem;
        }

        .footer-parallax-content h2 {
            margin: 0;
            font-size: clamp(1.55rem, 3.2vw, 2.6rem);
            line-height: 0.96;
            letter-spacing: -0.035em;
            text-shadow: 0 14px 34px rgba(0, 0, 0, 0.36);
        }

        .footer-parallax-content p {
            width: min(640px, 92%);
            margin: 0.85rem auto 0;
            font-size: clamp(0.98rem, 1.5vw, 1.08rem);
            line-height: 1.6;
            color: rgba(244, 239, 225, 0.82);
        }

        html[data-btc-theme="light"] .hero-parallax-frost,
        html[data-btc-theme="light"] .footer-parallax-frost {
            opacity: 1;
        }

        html[data-btc-theme="light"] .hero-parallax-shell::after {
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(255, 255, 255, 0.72) 10%, rgba(255, 255, 255, 0.34) 22%, rgba(250, 251, 253, 0.12) 34%, rgba(244, 247, 252, 0.08) 50%, rgba(243, 247, 251, 0.16) 68%, rgba(247, 249, 253, 0.4) 82%, rgba(252, 253, 254, 0.72) 92%, rgba(255, 255, 255, 0.98) 100%);
        }

        html[data-btc-theme="light"] .footer-parallax-shell::before {
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(255, 255, 255, 0.7) 10%, rgba(252, 252, 253, 0.28) 22%, rgba(246, 248, 251, 0.1) 34%, rgba(242, 246, 251, 0.1) 52%, rgba(241, 245, 250, 0.2) 70%, rgba(246, 248, 252, 0.46) 84%, rgba(251, 252, 254, 0.76) 93%, rgba(255, 255, 255, 0.98) 100%);
        }

        html[data-btc-theme="light"] .hero-parallax-grid {
            opacity: 0.34;
        }

        html[data-btc-theme="light"] .footer-parallax-content {
            color: #142132;
        }

        html[data-btc-theme="light"] .footer-parallax-eyebrow {
            color: rgba(255, 255, 255, 0.98);
        }

        html[data-btc-theme="light"] .footer-parallax-content h2 {
            text-shadow: 0 14px 30px rgba(255, 255, 255, 0.22);
        }

        html[data-btc-theme="light"] .footer-parallax-content p {
            color: rgba(22, 33, 50, 0.82);
        }

        html[data-btc-theme="light"] .hero-parallax-tags span {
            border-color: rgba(255, 255, 255, 0.78);
            background: rgba(255, 255, 255, 0.42);
            color: #223143;
            backdrop-filter: blur(14px);
        }

        .summary-shell {
            max-width: 1120px;
            margin: 0 auto 1.5rem auto;
        }

        .summary-intro {
            text-align: center;
            margin-bottom: 1rem;
        }

        .summary-kicker {
            font-size: 0.74rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            opacity: 0.62;
            margin-bottom: 0.25rem;
        }

        .summary-caption {
            font-size: 0.96rem;
            opacity: 0.78;
            margin: 0;
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.85rem;
            margin-bottom: 0.85rem;
        }

        .summary-tile {
            border: 1px solid rgba(255, 255, 255, 0.08);
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02)),
                rgba(16, 18, 24, 0.72);
            border-radius: 8px;
            padding: 1rem 1rem 0.95rem 1rem;
            min-height: 132px;
            text-align: center;
            color: #f7f4ea;
            display: flex;
            flex-direction: column;
            justify-content: center;
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.14);
        }

        .summary-label {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            opacity: 0.62;
            margin-bottom: 0.45rem;
        }

        .summary-value {
            font-size: clamp(1.35rem, 2.3vw, 2rem);
            font-weight: 700;
            line-height: 1.05;
            margin-bottom: 0.35rem;
        }

        .summary-detail {
            font-size: 0.84rem;
            opacity: 0.72;
        }

        .summary-value.is-positive {
            color: #53d38b;
        }

        .summary-value.is-negative {
            color: #ff7768;
        }

        html[data-btc-theme="light"] .summary-tile {
            color: #243043;
            background: rgba(255, 255, 255, 0.88);
            border-color: rgba(20, 33, 50, 0.1);
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
        }

        html[data-btc-theme="light"] .summary-label,
        html[data-btc-theme="light"] .summary-detail {
            color: rgba(36, 48, 67, 0.72);
        }

        html[data-btc-theme="dark"] body,
        html[data-btc-theme="dark"] .stApp {
            background: #080d16 !important;
            color: #f7f4ea !important;
        }

        html[data-btc-theme="dark"] section[data-testid="stSidebar"] {
            background: #0d1420 !important;
        }

        html[data-btc-theme="dark"] .context-strip {
            border-color: rgba(255, 255, 255, 0.14);
        }

        html[data-btc-theme="dark"] .context-item {
            border-color: rgba(255, 255, 255, 0.1);
        }

        html[data-btc-theme="light"] body,
        html[data-btc-theme="light"] .stApp {
            background: #f8fafc !important;
            color: #243043 !important;
        }

        @media (max-width: 1080px) {
            .summary-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .context-strip {
                grid-template-columns: repeat(3, minmax(0, 1fr));
                row-gap: 0.75rem;
            }

            .context-item:nth-child(3) {
                border-right: 0;
            }
        }

        @media (max-width: 900px) {
            header[data-testid="stHeader"] {
                display: block !important;
                height: 0 !important;
                min-height: 0 !important;
            }

            [data-testid="stToolbar"] {
                display: none !important;
            }

            div[data-testid="collapsedControl"] {
                display: flex !important;
                position: fixed;
                top: 0.85rem;
                left: 0.85rem;
                z-index: 1002;
            }

            section[data-testid="stSidebar"][aria-expanded="false"] div[data-testid="stSidebarCollapseButton"] {
                opacity: 0 !important;
                pointer-events: none !important;
            }
        }

        @media (max-width: 640px) {
            .hero-parallax-shell {
                min-height: 330px;
                margin: 0 calc(50% - 50vw) 1.5rem;
            }

            .hero-parallax-media {
                transform: scale(1.08);
            }

            .hero-parallax-content {
                width: min(92vw, 680px);
                padding: 2rem 0 2.2rem;
            }

            .hero-parallax-kicker {
                margin-left: 3.25rem;
            }

            .context-strip {
                max-width: 92vw;
                grid-template-columns: minmax(0, 1fr);
                gap: 0.65rem;
            }

            .context-item,
            .context-item:nth-child(3) {
                padding: 0;
                border-right: 0;
            }

            .footer-parallax-shell {
                min-height: 260px;
                margin: 2rem calc(50% - 50vw) -0.75rem;
            }

            .footer-parallax-media {
                transform: scale(1.06);
            }

            .footer-parallax-content {
                width: min(90vw, 640px);
                padding-bottom: 2rem;
            }

            .hero-parallax-tags span {
                font-size: 0.78rem;
                padding: 0.52rem 0.78rem;
            }

            .summary-shell {
                max-width: 92vw;
            }

            .summary-grid {
                grid-template-columns: minmax(0, 1fr);
            }

            .summary-tile {
                min-height: 118px;
                margin: 0 auto;
            }
        }
        </style>
        """
    )


def _metric_tone_class(value: float | None) -> str:
    """Map signed values to a CSS tone class."""
    if value is None:
        return ""
    if value > 0:
        return " is-positive"
    if value < 0:
        return " is-negative"
    return ""


def render_summary_tile_section(
    title: str,
    subtitle: str,
    metrics: list[dict[str, str | float | None]],
) -> None:
    """Render a centered, responsive KPI tile section."""
    tile_markup = []
    for metric in metrics:
        tone_class = _metric_tone_class(metric.get("tone"))  # type: ignore[arg-type]
        tile_markup.append(
            f"""
            <div class="summary-tile">
              <div class="summary-label">{html.escape(str(metric["label"]))}</div>
              <div class="summary-value{tone_class}">{html.escape(str(metric["value"]))}</div>
              <div class="summary-detail">{html.escape(str(metric["detail"]))}</div>
            </div>
            """
        )

    st.html(
        f"""
        <section class="summary-shell">
          <div class="summary-intro">
            <div class="summary-kicker">{html.escape(title)}</div>
            <p class="summary-caption">{html.escape(subtitle)}</p>
          </div>
          <div class="summary-grid">
            {''.join(tile_markup)}
          </div>
        </section>
        """
    )


def render_context_strip(items: list[tuple[str, str]]) -> None:
    """Render a compact strip that keeps the active analysis settings visible."""
    item_markup = []
    for label, value in items:
        item_markup.append(
            f"""
            <div class="context-item">
              <div class="context-label">{html.escape(label)}</div>
              <div class="context-value">{html.escape(value)}</div>
            </div>
            """
        )

    st.html(
        f"""
        <section class="context-strip">
          {''.join(item_markup)}
        </section>
        """
    )


@st.cache_data(show_spinner=False)
def load_hero_image_data_uri() -> str | None:
    """Load the local hero image as a data URI for the parallax header."""
    hero_path = Path(__file__).resolve().parent / "assets" / "btc-parallax-hero.jpg"
    if not hero_path.exists():
        return None

    encoded = base64.b64encode(hero_path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def render_parallax_hero() -> None:
    """Render a compact, full-bleed workspace header."""
    hero_image = load_hero_image_data_uri()
    background_css = (
        f"linear-gradient(180deg, rgba(6, 10, 19, 0.2) 0%, rgba(6, 10, 19, 0.58) 56%, rgba(6, 10, 19, 0.9) 100%), url('{hero_image}')"
        if hero_image
        else "radial-gradient(circle at top right, rgba(240, 172, 36, 0.35), transparent 32%), linear-gradient(135deg, #06101d 0%, #13233b 50%, #0a1222 100%)"
    )
    st.html(
        f"""
        <section class="hero-parallax-shell">
          <div class="hero-parallax-media" style="background-image: {background_css};"></div>
          <div class="hero-parallax-grid"></div>
          <div class="hero-parallax-frost"></div>
          <div class="hero-parallax-content">
            <div class="hero-parallax-kicker">BTC MARKET STRUCTURE</div>
            <h1>Cycle workspace</h1>
            <p>Set the market window in the sidebar, run the detector, then read swing structure, analog patterns, and optional macro overlays from top to bottom.</p>
            <div class="hero-parallax-tags">
              <span>1. Configure range</span>
              <span>2. Run analysis</span>
              <span>3. Inspect swings</span>
            </div>
            <div class="workspace-status-row">
              <div class="workspace-status"><strong>Primary view</strong> Price chart</div>
              <div class="workspace-status"><strong>Detail view</strong> Tables and journals</div>
              <div class="workspace-status"><strong>Refresh</strong> Sidebar live BTC</div>
            </div>
          </div>
        </section>
        """
    )


@st.cache_data(show_spinner=False)
def load_footer_image_data_uri() -> str | None:
    """Load the user-provided footer image as a data URI."""
    footer_path = Path(__file__).resolve().parents[3] / "btcblur.jpg"
    if not footer_path.exists():
        return None

    encoded = base64.b64encode(footer_path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def render_parallax_footer() -> None:
    """Render a compact closing context banner."""
    footer_image = load_footer_image_data_uri()
    background_css = (
        f"linear-gradient(180deg, rgba(6, 10, 19, 0.18) 0%, rgba(6, 10, 19, 0.54) 48%, rgba(6, 10, 19, 0.9) 100%), url('{footer_image}')"
        if footer_image
        else "radial-gradient(circle at center, rgba(244, 182, 62, 0.25), transparent 36%), linear-gradient(135deg, #050911 0%, #0d1828 52%, #070c14 100%)"
    )
    st.html(
        f"""
        <section class="footer-parallax-shell">
          <div class="footer-parallax-media" style="background-image: {background_css};"></div>
          <div class="footer-parallax-frost"></div>
          <div class="footer-parallax-content">
            <div class="footer-parallax-eyebrow">Review Checklist</div>
            <h2>Save comparisons and predictions worth revisiting.</h2>
            <p>Use the lower panels for period comparisons, prediction notes, and export snapshots after the chart read is complete.</p>
          </div>
        </section>
        """
    )


def mount_theme_detector(theme_mode: str = "Auto") -> None:
    """Set a light/dark flag for banner styling without any scroll effects."""
    forced_theme = theme_mode.lower() if theme_mode in {"Light", "Dark"} else ""
    st.iframe(src=(
        """
        <script>
        (() => {
          const root = window.parent.document;
          const forcedTheme = __FORCED_THEME__;

          const parseRgb = (raw) => {
            const match = (raw || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
            return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
          };

          const getLuminance = (rgb) => {
            const transform = (channel) => {
              const normalized = channel / 255;
              return normalized <= 0.03928
                ? normalized / 12.92
                : Math.pow((normalized + 0.055) / 1.055, 2.4);
            };
            const [r, g, b] = rgb.map(transform);
            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
          };

          const updateThemeMode = () => {
            const html = root.documentElement;
            if (forcedTheme) {
              html.setAttribute('data-btc-theme', forcedTheme);
              html.setAttribute('data-btc-theme-source', 'manual');
              return;
            }

            html.setAttribute('data-btc-theme-source', 'auto');
            const app = root.querySelector('[data-testid="stAppViewContainer"]');
            const body = root.body;
            const candidates = [app, body, html].filter(Boolean);
            let theme = 'dark';

            for (const node of candidates) {
              const rgb = parseRgb(window.getComputedStyle(node).backgroundColor);
              if (!rgb) {
                continue;
              }
              if (getLuminance(rgb) > 0.72) {
                theme = 'light';
                break;
              }
            }

            html.setAttribute('data-btc-theme', theme);
          };

          updateThemeMode();
          window.addEventListener('resize', updateThemeMode, { passive: true });
          setTimeout(updateThemeMode, 300);
          setTimeout(updateThemeMode, 1200);
        })();
        </script>
        """
    ).replace("__FORCED_THEME__", json.dumps(forced_theme)),
        height=1,
        width=1,
    )


def mount_mobile_sidebar_trigger() -> None:
    """Inject a mobile hamburger that toggles Streamlit's real sidebar."""
    st.iframe(src=
        """
        <script>
        (() => {
          const root = window.parent.document;
          const launcherId = 'btc-mobile-sidebar-launcher';

          const styleLine = (line) => {
            line.style.display = 'block';
            line.style.width = '1.1rem';
            line.style.height = '2px';
            line.style.borderRadius = '999px';
            line.style.background = '#f7f4ea';
          };

          const removeLauncher = () => {
            root.getElementById(launcherId)?.remove();
          };

          const ensureLauncher = () => {
            const sidebar = root.querySelector('section[data-testid="stSidebar"]');
            const sidebarExpanded = sidebar?.getAttribute('aria-expanded') === 'true';
            const sidebarToggle = root.querySelector('div[data-testid="stSidebarCollapseButton"] button');

            if (window.innerWidth > 900) {
              removeLauncher();
              return;
            }

            let launcher = root.getElementById(launcherId);
            if (!launcher) {
              launcher = root.createElement('button');
              launcher.id = launcherId;
              launcher.type = 'button';
              launcher.setAttribute('aria-label', 'Open analysis controls');
              launcher.setAttribute('title', 'Open analysis controls');
              launcher.style.position = 'fixed';
              launcher.style.top = '0.85rem';
              launcher.style.left = '0.85rem';
              launcher.style.zIndex = '1003';
              launcher.style.width = '3rem';
              launcher.style.height = '3rem';
              launcher.style.borderRadius = '999px';
              launcher.style.border = '1px solid rgba(255, 196, 95, 0.28)';
              launcher.style.background = 'rgba(10, 16, 27, 0.92)';
              launcher.style.display = 'flex';
              launcher.style.alignItems = 'center';
              launcher.style.justifyContent = 'center';
              launcher.style.boxShadow = '0 18px 42px rgba(0, 0, 0, 0.28)';
              launcher.style.backdropFilter = 'blur(10px)';
              launcher.style.cursor = 'pointer';

              const icon = root.createElement('span');
              icon.style.display = 'flex';
              icon.style.flexDirection = 'column';
              icon.style.gap = '0.24rem';

              for (let i = 0; i < 3; i += 1) {
                const line = root.createElement('span');
                styleLine(line);
                icon.appendChild(line);
              }

              launcher.appendChild(icon);
              launcher.addEventListener('click', () => {
                root.querySelector('div[data-testid="stSidebarCollapseButton"] button')?.click();
              });
              root.body.appendChild(launcher);
            }

            if (launcher) {
              launcher.style.display = sidebarExpanded || !sidebarToggle ? 'none' : 'flex';
            }
          };

          ensureLauncher();
          window.addEventListener('resize', ensureLauncher, { passive: true });
          new MutationObserver(ensureLauncher).observe(root.body, { attributes: true, childList: true, subtree: true });
          setTimeout(ensureLauncher, 250);
          setTimeout(ensureLauncher, 1200);
        })();
        </script>
        """,
        height=1,
        width=1,
    )


def render_chart_key(show_moon_phase_key: bool) -> None:
    """Render a centered chart key below the main price chart."""
    moon_item = (
        '<span class="chart-key-item"><span class="chart-key-swatch moon">●</span>Moon Phases</span>'
        if show_moon_phase_key
        else ""
    )
    st.html(
        f"""
        <div style="display:flex; justify-content:center; margin:0.45rem 0 1.1rem 0;">
          <div style="display:flex; flex-wrap:wrap; gap:0.9rem 1.15rem; align-items:center; justify-content:center; font-size:0.84rem; opacity:0.82;">
            <span class="chart-key-item"><span style="color:#f39c12; font-weight:700;">▼</span>Swing High</span>
            <span class="chart-key-item"><span style="color:#3498db; font-weight:700;">▲</span>Swing Low</span>
            <span class="chart-key-item"><span style="color:#2ecc71; font-weight:700;">━</span>Up Leg</span>
            <span class="chart-key-item"><span style="color:#e74c3c; font-weight:700;">━</span>Down Leg</span>
            {moon_item}
          </div>
        </div>
        """
    )


def render_saved_period_comparison_reviews(
    output_dir: str,
    *,
    key_prefix: str = "saved-comparisons",
) -> None:
    """Render saved static comparison snapshots."""
    snapshots = _load_period_comparison_snapshots(output_dir)
    st.subheader("Saved Correlation Reviews")
    st.write(f"Snapshot store: `{_period_comparison_path(output_dir)}`")
    if not snapshots:
        st.info("No saved comparison snapshots yet.")
        return

    if st.button("Delete All Saved Comparison Snapshots", key=f"{key_prefix}-delete-all"):
        _write_period_comparison_snapshots(output_dir, [])
        st.success("Deleted saved comparison snapshots.")
        st.rerun()

    for snapshot in snapshots:
        label = snapshot.get("label", "Untitled comparison")
        created_at = _format_snapshot_time(str(snapshot.get("created_at", "")))
        context = snapshot.get("analysis_context", {})
        metrics = snapshot.get("metrics", {})
        with st.expander(f"{label} | {created_at}", expanded=False):
            st.write(
                f"**Context:** {context.get('symbol', 'N/A')} "
                f"{context.get('timeframe', 'N/A')} using {context.get('pivot_method', 'N/A')} pivots"
            )
            st.write(f"**Shape Correlation:** {_format_optional_corr(metrics.get('shape_correlation'))}")
            st.write(f"**Return Delta:** {_format_optional_pct(metrics.get('return_delta_pct'))}")
            st.write(
                f"**Max Drawdown Delta:** {_format_optional_pct(metrics.get('max_drawdown_delta_pct'))}"
            )
            notes = str(snapshot.get("notes", "")).strip()
            if notes:
                st.write(f"**Notes:** {notes}")

            st.plotly_chart(
                create_period_comparison_chart(snapshot),
                width="stretch",
                key=f"{key_prefix}-chart-{snapshot.get('id', label)}",
            )

            rows = []
            for key, label_text in [("period_a", "Period A"), ("period_b", "Period B")]:
                period = snapshot.get(key, {})
                period_metrics = period.get("metrics", {})
                rows.append(
                    {
                        "Period": label_text,
                        "Start": _format_chart_as_of(period_metrics.get("start")),
                        "End": _format_chart_as_of(period_metrics.get("end")),
                        "Candles": period_metrics.get("candles", 0),
                        "Return": _format_optional_pct(period_metrics.get("total_return_pct")),
                        "Range": _format_optional_pct(period_metrics.get("range_pct")),
                        "Max Drawdown": _format_optional_pct(period_metrics.get("max_drawdown_pct")),
                        "Positive Candle Rate": (
                            f"{period_metrics.get('positive_candle_rate') * 100:.1f}%"
                            if isinstance(period_metrics.get("positive_candle_rate"), (int, float))
                            else "N/A"
                        ),
                    }
                )
            st.dataframe(rows, width="stretch", hide_index=True)


def render_period_comparison_workspace(result, output_dir: str) -> None:
    """Render ad hoc period comparison controls and saved static reviews."""
    st.header("Period Comparison Lab")
    st.caption(
        "Compare two windows inside the loaded chart data, then save a static snapshot "
        "when the pattern looks worth reviewing later."
    )

    bounds = _date_bounds_from_result(result)
    datetime_bounds = _datetime_bounds_from_result(result)
    if bounds is None or datetime_bounds is None:
        st.info("No candle data is available for period comparison yet.")
        return

    min_date, max_date = bounds
    min_dt, max_dt = datetime_bounds
    total_seconds = max((max_dt - min_dt).total_seconds(), 1)
    default_span = timedelta(seconds=min(total_seconds / 4, 7 * 24 * 60 * 60))
    default_a_end_dt = max_dt
    default_a_start_dt = max(min_dt, default_a_end_dt - default_span)
    default_b_end_dt = max(min_dt, default_a_start_dt)
    default_b_start_dt = max(min_dt, default_b_end_dt - default_span)
    _ensure_date_input_state("comparison_period_a_start", default_a_start_dt.date(), min_date, max_date)
    _ensure_date_input_state("comparison_period_a_end", default_a_end_dt.date(), min_date, max_date)
    _ensure_date_input_state("comparison_period_b_start", default_b_start_dt.date(), min_date, max_date)
    _ensure_date_input_state("comparison_period_b_end", default_b_end_dt.date(), min_date, max_date)

    st.write(
        f"Loaded comparison range: `{_format_chart_as_of(min_dt)}` to `{_format_chart_as_of(max_dt)}`"
    )
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Period A")
        period_a_start = st.date_input(
            "A Start",
            value=default_a_start_dt.date(),
            min_value=min_date,
            max_value=max_date,
            key="comparison_period_a_start",
        )
        period_a_start_time = st.time_input(
            "A Start Time",
            value=default_a_start_dt.time().replace(microsecond=0),
            key="comparison_period_a_start_time",
        )
        period_a_end = st.date_input(
            "A End",
            value=default_a_end_dt.date(),
            min_value=min_date,
            max_value=max_date,
            key="comparison_period_a_end",
        )
        period_a_end_time = st.time_input(
            "A End Time",
            value=default_a_end_dt.time().replace(microsecond=0),
            key="comparison_period_a_end_time",
        )
    with col_b:
        st.subheader("Period B")
        period_b_start = st.date_input(
            "B Start",
            value=default_b_start_dt.date(),
            min_value=min_date,
            max_value=max_date,
            key="comparison_period_b_start",
        )
        period_b_start_time = st.time_input(
            "B Start Time",
            value=default_b_start_dt.time().replace(microsecond=0),
            key="comparison_period_b_start_time",
        )
        period_b_end = st.date_input(
            "B End",
            value=default_b_end_dt.date(),
            min_value=min_date,
            max_value=max_date,
            key="comparison_period_b_end",
        )
        period_b_end_time = st.time_input(
            "B End Time",
            value=default_b_end_dt.time().replace(microsecond=0),
            key="comparison_period_b_end_time",
        )

    period_a_candles = _filter_candles_by_window(
        result.raw_data,
        period_a_start,
        period_a_start_time,
        period_a_end,
        period_a_end_time,
    )
    period_b_candles = _filter_candles_by_window(
        result.raw_data,
        period_b_start,
        period_b_start_time,
        period_b_end,
        period_b_end_time,
    )

    if len(period_a_candles) < 2 or len(period_b_candles) < 2:
        st.warning("Choose two ranges with at least two candles each.")
    else:
        draft_snapshot = _build_period_comparison_snapshot(
            result=result,
            period_a_candles=period_a_candles,
            period_b_candles=period_b_candles,
            label="Draft comparison",
            notes="",
        )
        metrics = draft_snapshot["metrics"]
        metrics_a = draft_snapshot["period_a"]["metrics"]
        metrics_b = draft_snapshot["period_b"]["metrics"]

        metric_cols = st.columns(4)
        with metric_cols[0]:
            st.metric("Shape Correlation", _format_optional_corr(metrics["shape_correlation"]))
        with metric_cols[1]:
            st.metric("A Return", _format_optional_pct(metrics_a["total_return_pct"]))
        with metric_cols[2]:
            st.metric("B Return", _format_optional_pct(metrics_b["total_return_pct"]))
        with metric_cols[3]:
            st.metric("Return Delta", _format_optional_pct(metrics["return_delta_pct"]))

        st.plotly_chart(
            create_period_comparison_chart(draft_snapshot),
            width="stretch",
            key="draft-period-comparison-chart",
        )
        st.caption(
            "Shape correlation compares the normalized close path, resampled to the same progress scale. "
            "It is useful for pattern similarity, not a trade signal by itself."
        )

        save_col, note_col = st.columns([1, 2])
        with save_col:
            comparison_label = st.text_input(
                "Snapshot Label",
                value=f"{result.metadata.symbol} analog {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                key="comparison_snapshot_label",
            )
        with note_col:
            comparison_notes = st.text_area(
                "Correlation Notes",
                placeholder="What did you see? e.g. compression into breakout, failed rebound, similar drawdown rhythm...",
                key="comparison_snapshot_notes",
                height=94,
            )

        if st.button("Save Static Comparison Snapshot", type="primary"):
            snapshot = _build_period_comparison_snapshot(
                result=result,
                period_a_candles=period_a_candles,
                period_b_candles=period_b_candles,
                label=comparison_label,
                notes=comparison_notes,
            )
            snapshots = _load_period_comparison_snapshots(output_dir)
            snapshots.insert(0, snapshot)
            store_path = _write_period_comparison_snapshots(output_dir, snapshots)
            st.success(f"Saved static comparison to `{store_path}`")

    render_saved_period_comparison_reviews(output_dir, key_prefix="comparison-lab-saved")


def render_prediction_journal(result, output_dir: str) -> None:
    """Render a manual prediction journal with resolution tracking."""
    st.header("Prediction Journal")
    st.caption(
        "Write down the trade/path hypothesis while the chart is fresh, then resolve it later "
        "as confirmed, denied, or unclear. Tiny lab notebook, fewer ghosts in the machine."
    )

    if not result.raw_data:
        st.info("Run an analysis with candle data before adding predictions.")
        return

    latest_candle = result.raw_data[-1]
    latest_time = _coerce_utc_naive(latest_candle.timestamp)
    default_horizon = latest_time + timedelta(hours=24)
    prediction_col, context_col = st.columns([2, 1])

    with prediction_col:
        direction = st.selectbox(
            "Prediction",
            ["Bullish", "Bearish", "Sideways"],
            key="prediction_direction",
        )
        horizon_date = st.date_input(
            "Review / Horizon Date",
            value=default_horizon.date(),
            key="prediction_horizon_date",
        )
        horizon_time = st.time_input(
            "Review / Horizon Time",
            value=default_horizon.time().replace(microsecond=0),
            key="prediction_horizon_time",
        )
        confidence = st.slider(
            "Your Confidence",
            min_value=0,
            max_value=100,
            value=55,
            step=5,
            key="prediction_confidence",
        )
        expected_move_raw = st.text_input(
            "Expected Move % (optional)",
            placeholder="Example: 2.5 or -1.2",
            key="prediction_expected_move_pct",
        )
        thesis = st.text_area(
            "Thesis",
            placeholder="What are you seeing? Pattern, regime, invalidation, timing, emotion check...",
            key="prediction_thesis",
            height=110,
        )
        invalidation = st.text_area(
            "Invalidation / What Would Change Your Mind",
            placeholder="Example: loses prior swing low, no follow-through by NY close, volume divergence fails...",
            key="prediction_invalidation",
            height=90,
        )

    with context_col:
        st.write(f"**Base Time:** {_format_chart_as_of(latest_time)}")
        st.write(f"**Base Price:** ${float(latest_candle.close):,.2f}")
        if result.pattern_insight:
            st.write(f"**Pattern:** `{result.pattern_insight.pattern_signature}`")
            st.write(f"**Engine Bias:** {result.pattern_insight.dominant_bias.title()}")
            st.write(
                f"**Adaptive Confidence:** {result.pattern_insight.adaptive_confidence * 100:.1f}%"
            )
        else:
            st.write("**Pattern:** Not available")

    if st.button("Save Prediction", type="primary"):
        expected_move_pct = _parse_optional_float(expected_move_raw)
        horizon_end = datetime.combine(horizon_date, horizon_time)
        prediction = _build_prediction_entry(
            result=result,
            direction=direction.lower(),
            horizon_end=horizon_end,
            confidence=confidence,
            expected_move_pct=expected_move_pct,
            thesis=thesis,
            invalidation=invalidation,
        )
        predictions = _load_prediction_journal(output_dir)
        predictions.insert(0, prediction)
        journal_path = _write_prediction_journal(output_dir, predictions)
        st.success(f"Saved prediction to `{journal_path}`")

    predictions = _load_prediction_journal(output_dir)
    st.subheader("Prediction Review")
    st.write(f"Journal store: `{_prediction_journal_path(output_dir)}`")
    if not predictions:
        st.info("No saved predictions yet.")
        return

    open_count = sum(1 for item in predictions if item.get("status") == "open")
    resolved_count = len(predictions) - open_count
    st.write(f"Open predictions: **{open_count}** | Resolved: **{resolved_count}**")

    for index, prediction in enumerate(predictions):
        status = str(prediction.get("status", "open")).title()
        label = (
            f"{status} | {prediction.get('prediction_direction', 'unknown').title()} "
            f"from {_format_chart_as_of(str(prediction.get('base_time', '')))}"
        )
        with st.expander(label, expanded=index == 0 and prediction.get("status") == "open"):
            st.write(f"**Symbol / Timeframe:** {prediction.get('symbol')} {prediction.get('timeframe')}")
            st.write(f"**Base Price:** ${float(prediction.get('base_price', 0.0)):,.2f}")
            st.write(f"**Horizon:** {_format_chart_as_of(str(prediction.get('horizon_end', '')))}")
            st.write(f"**Your Confidence:** {prediction.get('confidence_pct', 0)}%")
            if prediction.get("expected_move_pct") is not None:
                st.write(f"**Expected Move:** {_format_optional_pct(prediction.get('expected_move_pct'))}")
            if prediction.get("pattern_signature"):
                st.write(f"**Pattern Signature:** `{prediction.get('pattern_signature')}`")
            if prediction.get("pattern_bias"):
                st.write(f"**Engine Bias At Save:** {str(prediction.get('pattern_bias')).title()}")
            if prediction.get("thesis"):
                st.write(f"**Thesis:** {prediction.get('thesis')}")
            if prediction.get("invalidation"):
                st.write(f"**Invalidation:** {prediction.get('invalidation')}")

            outcome = _prediction_auto_outcome(prediction, result)
            if outcome:
                st.info(
                    "Auto outcome preview: "
                    f"{outcome['actual_direction'].title()} "
                    f"{outcome['actual_return_pct']:+.2f}% by "
                    f"{_format_chart_as_of(outcome['outcome_time'])}. "
                    f"Suggested resolution: {outcome['suggested_resolution']}."
                )
            elif prediction.get("status") == "open":
                st.caption("No auto outcome yet in the currently loaded candle window.")

            if prediction.get("status") == "open":
                notes = st.text_input(
                    "Resolution Notes",
                    key=f"prediction_resolution_notes_{prediction.get('id', index)}",
                )
                col1, col2, col3 = st.columns(3)
                for resolution, column in [
                    ("confirmed", col1),
                    ("denied", col2),
                    ("unclear", col3),
                ]:
                    with column:
                        if st.button(
                            f"Mark {resolution.title()}",
                            key=f"prediction_{resolution}_{prediction.get('id', index)}",
                        ):
                            prediction["status"] = "resolved"
                            prediction["resolution"] = resolution
                            prediction["resolved_at"] = datetime.now(timezone.utc).isoformat()
                            prediction["resolution_notes"] = notes
                            if outcome:
                                prediction["actual_return_pct"] = outcome["actual_return_pct"]
                                prediction["actual_direction"] = outcome["actual_direction"]
                            _write_prediction_journal(output_dir, predictions)
                            st.rerun()
            else:
                st.write(f"**Resolution:** {prediction.get('resolution', 'N/A')}")
                if prediction.get("actual_return_pct") is not None:
                    st.write(f"**Actual Return:** {_format_optional_pct(prediction.get('actual_return_pct'))}")
                if prediction.get("resolution_notes"):
                    st.write(f"**Resolution Notes:** {prediction.get('resolution_notes')}")


def initialize_sidebar_state() -> None:
    """Populate sidebar widget state once."""
    for key, value in DEFAULT_SIDEBAR_STATE.items():
        st.session_state.setdefault(key, value)
    sync_alt_signal_master_state()


def sync_alt_signal_master_state() -> None:
    """Keep the master alternative-signal toggle aligned with individual toggles."""
    st.session_state.alt_signals_select_all = all(
        bool(st.session_state.get(key, False))
        for key in ALT_SIGNAL_KEYS
    )


def apply_alt_signal_master_toggle() -> None:
    """Apply the master alternative-signal toggle to all individual signals."""
    new_value = bool(st.session_state.get("alt_signals_select_all", False))
    for key in ALT_SIGNAL_KEYS:
        st.session_state[key] = new_value


def control_sync_callback(base_key: str):
    """Return the appropriate widget sync callback."""
    if base_key in ALT_SIGNAL_KEYS:
        return sync_alt_signal_master_state
    return None


def render_configuration_controls(
    *,
    show_live_card: bool = False,
    show_title: bool = True,
) -> None:
    """Render the configuration controls."""

    if show_live_card:
        render_live_btc_sidebar_card()

    if show_title:
        st.header("Setup")
        st.caption("Choose the market window and detection sensitivity, then run the analysis.")

    st.subheader("Market Window")
    st.text_input(
        "Symbol",
        key="symbol",
        help="Use the Coinbase-style market pair, for example BTC-USD.",
    )
    st.selectbox(
        "Timeframe",
        options=[tf.value for tf in Timeframe],
        key="timeframe",
        help="Candle interval used for pivots, legs, and pattern matching.",
    )
    st.text_input(
        "Lookback",
        key="lookback",
        help="Window to load, such as 30d, 12w, or 1y.",
    )

    st.subheader("Pivot Detection")
    st.selectbox(
        "Pivot Method",
        options=[m.value for m in PivotMethod],
        key="pivot_method",
        help="Zigzag filters by reversal size; fractal/fixed-window look for local turning points.",
    )

    st.slider(
        "Min Move %",
        0.1,
        10.0,
        key="min_move_pct",
        step=0.1,
        help="Higher values ignore smaller swings and reduce chart noise.",
    )
    st.slider(
        "Left Bars",
        1,
        20,
        key="left_bars",
        help="Candles checked before a local pivot.",
    )
    st.slider(
        "Right Bars",
        1,
        20,
        key="right_bars",
        help="Candles checked after a local pivot.",
    )

    use_atr = st.checkbox(
        "Use ATR Filter",
        key="use_atr",
        help="Require swings to clear a volatility-adjusted threshold.",
    )
    if use_atr:
        st.slider(
            "ATR Period",
            5,
            50,
            key="atr_period",
            help="Candles used to calculate average true range.",
        )
        st.slider(
            "ATR Multiplier",
            1.0,
            3.0,
            key="atr_multiplier",
            step=0.1,
            help="Higher values make the volatility filter stricter.",
        )

    st.divider()
    st.subheader("Pattern Memory")
    st.caption("Compare the latest leg sequence with similar historical sequences.")
    st.checkbox(
        "Enable Pattern Recognition",
        key="enable_pattern_recognition",
        help="Run analog matching and adaptive confidence scoring.",
    )
    st.slider(
        "Pattern Length",
        2,
        6,
        key="pattern_length",
        help="Number of recent legs encoded into the current pattern.",
    )
    st.slider(
        "Forecast Horizon (legs)",
        1,
        6,
        key="pattern_forecast_horizon",
        help="How many future legs the analog engine evaluates.",
    )
    st.slider(
        "Max Analog Matches",
        3,
        20,
        key="pattern_max_matches",
        help="Maximum historical matches used for the current bias.",
    )

    st.divider()
    st.subheader("Overlays")
    st.caption("Optional context layers. Enable only what you want to review.")
    st.checkbox(
        "Moon phases",
        key="enable_moon_phase_analysis",
        on_change=control_sync_callback("enable_moon_phase_analysis"),
    )
    st.checkbox(
        "Gold correlation",
        key="enable_gold_correlation_analysis",
        on_change=control_sync_callback("enable_gold_correlation_analysis"),
    )
    st.checkbox(
        "Nasdaq correlation",
        key="enable_nasdaq_correlation_analysis",
        on_change=control_sync_callback("enable_nasdaq_correlation_analysis"),
    )
    st.checkbox(
        "Oil correlation",
        key="enable_oil_correlation_analysis",
        on_change=control_sync_callback("enable_oil_correlation_analysis"),
    )
    st.checkbox(
        "Select all overlays",
        key="alt_signals_select_all",
        on_change=apply_alt_signal_master_toggle,
    )

    with st.container():
        st.markdown('<div class="sidebar-action-anchor"></div>', unsafe_allow_html=True)
        if st.button("Run analysis", key="run_analysis_button", type="primary"):
            st.session_state.run_analysis = True
        if st.button("Reset to Defaults", key="reset_defaults_button"):
            reset_sidebar_state()
            st.rerun()

    with st.expander("Glossary / Acronyms"):
        for term, definition in GLOSSARY_ITEMS[:13]:
            st.write(f"**{term}:** {definition}")

    st.divider()
    st.selectbox(
        "Theme",
        options=["Auto", "Light", "Dark"],
        key="app_theme",
        help="Auto follows Streamlit's current theme; Light or Dark forces this workspace's custom styling.",
    )


def reset_sidebar_state() -> None:
    """Restore sidebar inputs and clear the current result."""
    for key, value in DEFAULT_SIDEBAR_STATE.items():
        st.session_state[key] = value
    st.session_state.run_analysis = False
    st.session_state.pop("result", None)


def main():
    """Main Streamlit app entry point."""
    st.set_page_config(
        page_title="BTC Swing Cycle Tracker",
        page_icon="📊",
        layout="wide",
    )

    initialize_sidebar_state()
    inject_sidebar_button_styles()
    inject_app_styles()
    mount_theme_detector(st.session_state.get("app_theme", "Auto"))
    mount_mobile_sidebar_trigger()
    render_parallax_hero()

    # Sidebar for configuration
    with st.sidebar:
        render_configuration_controls(show_live_card=True)

    symbol = st.session_state.symbol
    timeframe = st.session_state.timeframe
    lookback = st.session_state.lookback
    pivot_method = st.session_state.pivot_method
    min_move_pct = st.session_state.min_move_pct
    left_bars = st.session_state.left_bars
    right_bars = st.session_state.right_bars
    use_atr = st.session_state.use_atr
    atr_period = st.session_state.atr_period if use_atr else DEFAULT_CONFIG.atr_period
    atr_multiplier = st.session_state.atr_multiplier if use_atr else DEFAULT_CONFIG.atr_multiplier
    enable_pattern_recognition = st.session_state.enable_pattern_recognition
    pattern_length = st.session_state.pattern_length
    pattern_forecast_horizon = st.session_state.pattern_forecast_horizon
    pattern_max_matches = st.session_state.pattern_max_matches
    enable_moon_phase_analysis = st.session_state.enable_moon_phase_analysis
    enable_gold_correlation_analysis = st.session_state.enable_gold_correlation_analysis
    enable_nasdaq_correlation_analysis = st.session_state.enable_nasdaq_correlation_analysis
    enable_oil_correlation_analysis = st.session_state.enable_oil_correlation_analysis

    # Main content
    if not hasattr(st.session_state, "run_analysis") or not st.session_state.run_analysis:
        render_context_strip(
            [
                ("Symbol", symbol),
                ("Timeframe", timeframe),
                ("Lookback", lookback),
                ("Pivot", pivot_method),
                ("Min Move", f"{min_move_pct:.1f}%"),
            ]
        )
        st.info("Review the setup in the sidebar, then click 'Run analysis' to detect swings and build the full workspace.")
        st.header("Price Preview")
        st.markdown(
            '<p class="section-note">This preview uses the selected symbol, timeframe, and lookback before pivot detection is run.</p>',
            unsafe_allow_html=True,
        )
        try:
            preview_rows = get_pre_analysis_preview_data(symbol, timeframe, lookback)
        except Exception as exc:
            preview_rows = []
            st.warning(f"Preview chart unavailable right now: {exc}")

        if preview_rows:
            preview_fig = create_pre_analysis_preview_chart(
                preview_rows=preview_rows,
                symbol=symbol,
                timeframe=timeframe,
                lookback=lookback,
            )
            st.plotly_chart(
                preview_fig,
                width="stretch",
                key="pre-analysis-preview-chart",
            )
            st.markdown(
                f'<p style="text-align:center; opacity:0.8;">Chart as of: {_format_chart_as_of(preview_rows[-1]["timestamp"])}</p>',
                unsafe_allow_html=True,
            )
        render_parallax_footer()
        return

    # Run analysis
    with st.spinner("Running analysis..."):
        config = Config(
            symbol=symbol,
            timeframe=timeframe,
            lookback_period=lookback,
            pivot_method=pivot_method,
            min_move_pct=min_move_pct,
            left_bars=left_bars,
            right_bars=right_bars,
            use_atr_filter=use_atr,
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
            enable_pattern_recognition=enable_pattern_recognition,
            pattern_length=pattern_length,
            pattern_forecast_horizon=pattern_forecast_horizon,
            pattern_max_matches=pattern_max_matches,
            enable_moon_phase_analysis=enable_moon_phase_analysis,
            enable_gold_correlation_analysis=enable_gold_correlation_analysis,
            enable_nasdaq_correlation_analysis=enable_nasdaq_correlation_analysis,
            enable_oil_correlation_analysis=enable_oil_correlation_analysis,
        )

        service = AnalysisService(config)

        try:
            result = service.run_analysis_sync()
            st.session_state.result = result
        except Exception as e:
            st.error(f"Error running analysis: {e}")
            return

    # Display results
    result = st.session_state.result

    # Summary cards
    st.header("Summary")
    render_context_strip(
        [
            ("Symbol", symbol),
            ("Timeframe", timeframe),
            ("Lookback", lookback),
            ("Pivot", pivot_method),
            ("ATR Filter", "On" if use_atr else "Off"),
        ]
    )
    render_summary_tile_section(
        title="Core Snapshot",
        subtitle="Current swing count, average move, and active chart window.",
        metrics=[
            {
                "label": "Total Pivots",
                "value": str(result.metadata.total_pivots),
                "detail": f"{result.metadata.symbol} turning points",
                "tone": None,
            },
            {
                "label": "Total Legs",
                "value": str(result.metadata.total_legs),
                "detail": f"{result.metadata.timeframe} swing legs detected",
                "tone": None,
            },
            {
                "label": "Avg % Change",
                "value": f"{result.summary.avg_percent_change:+.2f}%",
                "detail": "Mean leg move across the selected lookback",
                "tone": result.summary.avg_percent_change,
            },
            {
                "label": "Avg Duration",
                "value": f"{result.summary.avg_duration_minutes:.1f} min",
                "detail": "Average time spent per leg",
                "tone": None,
            },
        ],
    )
    render_summary_tile_section(
        title="Directional Balance",
        subtitle="Bullish and bearish leg counts plus average move by direction.",
        metrics=[
            {
                "label": "Up Legs",
                "value": str(result.summary.up_legs_count),
                "detail": "Completed upward legs",
                "tone": float(result.summary.up_legs_count),
            },
            {
                "label": "Down Legs",
                "value": str(result.summary.down_legs_count),
                "detail": "Completed downward legs",
                "tone": -float(result.summary.down_legs_count),
            },
            {
                "label": "Up Avg %",
                "value": (
                    f"{result.summary.up_legs_avg_change:+.2f}%"
                    if result.summary.up_legs_avg_change is not None
                    else "N/A"
                ),
                "detail": "Average move when BTC swings higher",
                "tone": result.summary.up_legs_avg_change,
            },
            {
                "label": "Down Avg %",
                "value": (
                    f"{result.summary.down_legs_avg_change:+.2f}%"
                    if result.summary.down_legs_avg_change is not None
                    else "N/A"
                ),
                "detail": "Average move when BTC swings lower",
                "tone": result.summary.down_legs_avg_change,
            },
        ],
    )

    # Chart
    st.header("Price Chart")
    st.markdown(
        '<p class="section-note">Start here: confirm the detected pivots, then use lower panels for distributions, analog patterns, and saved reviews.</p>',
        unsafe_allow_html=True,
    )
    
    # Toggle for showing all legs
    show_all_legs = st.checkbox("Show all legs (may be cluttered)", value=False)
    
    fig = create_candlestick_chart_v2(
        result=result,
        title=f"{symbol} Swing Cycle Analysis",
        show_all_legs=show_all_legs,
        moon_phase_events=(
            result.moon_phase_insight.events
            if result.moon_phase_insight is not None
            else None
        ),
    )
    add_structure_overlays(fig, result)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        f"Chart as of: {_format_chart_as_of(result.raw_data[-1].timestamp if result.raw_data else None)}. The sidebar shows live ticker price, so the current candle may still be forming."
    )
    render_chart_key(show_moon_phase_key=result.moon_phase_insight is not None)

    if result.structure_discoveries:
        st.subheader("Structures you may have missed")
        st.caption("Deterministic observations from confirmed pivots; confidence measures detector evidence, not trade probability.")
        columns = st.columns(3)
        for index, discovery in enumerate(result.structure_discoveries[:6]):
            with columns[index % 3]:
                st.markdown(f"**{discovery.title}** · {discovery.confidence * 100:.0f}%")
                st.caption(f"{discovery.status.title()} · {discovery.direction.title()}")
                st.write(discovery.evidence[0] if discovery.evidence else "Confirmed pivot structure")
                if discovery.invalidation_price is not None:
                    st.caption(f"Invalidation: ${discovery.invalidation_price:,.2f}")

    if result.moon_phase_insight is not None:
        st.caption(
            "Moon-phase overlay shows major lunar turning points and the nearest swing response for correlation work."
        )

    market_cap_fig = create_market_cap_bar_chart(result=result)
    if market_cap_fig is not None:
        st.plotly_chart(market_cap_fig, width="stretch")
        st.caption(
            "Historical BTC market cap from CoinGecko, filtered to the same chart window."
        )

    render_qwen_insight_panel(result, config)

    render_period_comparison_workspace(result, config.output_dir)

    # Distribution charts
    st.header("Distributions")
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Leg % Change Distribution")
        dist_fig = create_leg_distribution_chart(result)
        st.plotly_chart(dist_fig, width="stretch")
    
    with col2:
        st.subheader("Leg Duration Distribution")
        dur_fig = create_duration_distribution_chart(result)
        st.plotly_chart(dur_fig, width="stretch")

    # Summary stats chart
    st.header("Summary Statistics")
    summary_fig = create_summary_stats_chart(result)
    st.plotly_chart(summary_fig, width="stretch")

    if result.pattern_insight:
        st.header("Pattern Intelligence")
        insight = result.pattern_insight
        learning = result.pattern_learning

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Current Bias", insight.dominant_bias.title())
        with col2:
            st.metric("Adaptive Confidence", f"{insight.adaptive_confidence * 100:.1f}%")
        with col3:
            st.metric("Expected Next Move", f"{insight.expected_next_change_pct:+.2f}%")
        with col4:
            st.metric(
                "Expected Horizon Move",
                f"{insight.expected_horizon_change_pct:+.2f}%",
            )

        st.caption(insight.summary)

        col1, col2 = st.columns(2)
        with col1:
            pattern_prob_fig = create_pattern_probability_chart(result)
            st.plotly_chart(pattern_prob_fig, width="stretch")
        with col2:
            pattern_learning_fig = create_pattern_learning_chart(result)
            st.plotly_chart(pattern_learning_fig, width="stretch")

        if learning:
            st.info(learning.learning_note)
            st.caption(
                f"Current memory regime: {learning.regime_label} "
                f"({learning.regime_samples} matching samples)."
            )

    if result.moon_phase_insight is not None:
        moon = result.moon_phase_insight
        st.header("Moon Phase Correlation")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Major Phases", moon.total_events)
        with col2:
            st.metric("Alignment Rate", f"{moon.alignment_rate * 100:.1f}%")
        with col3:
            avg_hours = f"{moon.avg_hours_to_pivot:.1f}h" if moon.avg_hours_to_pivot is not None else "N/A"
            st.metric("Avg Hours To Pivot", avg_hours)
        with col4:
            strongest = "N/A"
            if moon.strongest_phase and moon.strongest_bias:
                strongest = f"{moon.strongest_phase} / {moon.strongest_bias.title()}"
            st.metric("Strongest Phase Bias", strongest)

        st.caption(moon.summary)

    correlation_insights = [
        insight
        for insight in [
            result.gold_correlation_insight,
            result.nasdaq_correlation_insight,
            result.oil_correlation_insight,
        ]
        if insight is not None
    ]
    if correlation_insights:
        st.header("Market Correlations")
        for insight in correlation_insights:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                return_corr_text = (
                    f"{insight.return_correlation:+.2f}"
                    if insight.return_correlation is not None
                    else "N/A"
                )
                st.metric(f"{insight.asset_name} Return Corr", return_corr_text)
            with col2:
                rolling_text = (
                    f"{insight.latest_rolling_correlation:+.2f}"
                    if insight.latest_rolling_correlation is not None
                    else "N/A"
                )
                st.metric("Latest Rolling Corr", rolling_text)
            with col3:
                strength_text = (
                    f"{insight.latest_relative_strength_pct:+.2f}"
                    if insight.latest_relative_strength_pct is not None
                    else "N/A"
                )
                st.metric("Relative Strength", strength_text)
            with col4:
                st.metric("Overlap Days", str(insight.overlap_points))

            st.caption(insight.summary)
            st.plotly_chart(
                create_asset_correlation_chart(insight),
                width="stretch",
                key=f"asset-correlation-main-{insight.asset_symbol}",
            )

    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs(
        ["Legs", "Pivots", "Summary", "Pattern Insights", "Pattern Learning", "Predictions", "Moon Phases", "Market Correlations", "Saved Comparisons", "Glossary"]
    )

    with tab1:
        st.subheader("Swing Legs")
        st.plotly_chart(
            create_leg_story_chart(result),
            width="stretch",
            key="legs-story-chart",
        )
        legs_data = []
        for i, leg in enumerate(result.legs):
            legs_data.append({
                "Leg": leg.leg_id,
                "Start Pivot": leg.start_pivot_id,
                "End Pivot": leg.end_pivot_id,
                "Direction": leg.direction.upper(),
                "Start": leg.start_timestamp.strftime("%Y-%m-%d %H:%M"),
                "End": leg.end_timestamp.strftime("%Y-%m-%d %H:%M"),
                "Start Price": f"${leg.start_price:.2f}",
                "End Price": f"${leg.end_price:.2f}",
                "Abs Change": f"${leg.absolute_change:.2f}",
                "Change %": f"{leg.percent_change:+.2f}%",
                "Duration (min)": f"{leg.duration_minutes:.1f}",
                "Candles": leg.duration_bars,
            })

        with st.expander("Detailed leg table", expanded=False):
            st.dataframe(legs_data, width="stretch", hide_index=True)

        # Download legs CSV
        if st.button("Download Legs CSV"):
            csv_writer = CSVWriter()
            csv_path = csv_writer.write_legs(result.legs)
            with open(csv_path, "rb") as f:
                st.download_button(
                    "Download",
                    f.read(),
                    "swing_legs.csv",
                    "text/csv",
                )

    with tab2:
        st.subheader("Pivot Points")
        st.plotly_chart(
            create_pivot_overview_chart(result),
            width="stretch",
            key="pivot-overview-chart",
        )
        pivots_data = []
        for pivot in result.pivots:
            pivots_data.append({
                "ID": pivot.index,
                "Timestamp": pivot.timestamp.strftime("%Y-%m-%d %H:%M"),
                "Price": f"${pivot.price:.2f}",
                "Type": pivot.pivot_type.replace("_", " ").title(),
                "Left Bars": pivot.left_bars,
                "Right Bars": pivot.right_bars,
            })

        with st.expander("Detailed pivot table", expanded=False):
            st.dataframe(pivots_data, width="stretch", hide_index=True)

        # Download pivots CSV
        if st.button("Download Pivots CSV"):
            csv_writer = CSVWriter()
            csv_path = csv_writer.write_pivots(result.pivots)
            with open(csv_path, "rb") as f:
                st.download_button(
                    "Download",
                    f.read(),
                    "pivots.csv",
                    "text/csv",
                )

    with tab3:
        st.subheader("Statistics")
        st.plotly_chart(
            create_summary_stats_chart(result),
            width="stretch",
            key="summary-stats-tab-chart",
        )
        with st.expander("Metric details", expanded=False):
            st.write(f"**Period:** {result.metadata.start_date} to {result.metadata.end_date}")
            st.write(f"**Total Candles:** {result.metadata.total_candles}")
            st.write(f"**Total Pivots:** {result.metadata.total_pivots}")
            st.write(f"**Total Legs:** {result.metadata.total_legs}")
            st.write(f"**Min % Change:** {result.summary.min_percent_change:.2f}%")
            st.write(f"**Max % Change:** {result.summary.max_percent_change:.2f}%")
            st.write(f"**Min Duration:** {result.summary.min_duration_minutes:.1f} min")
            st.write(f"**Max Duration:** {result.summary.max_duration_minutes:.1f} min")
            st.write(f"**Total Up Change:** {result.summary.up_legs_total_change:.2f}%")
            st.write(f"**Total Down Change:** {result.summary.down_legs_total_change:.2f}%")

    with tab4:
        st.subheader("Pattern Insights")
        if result.pattern_insight is None:
            st.info("Not enough leg history yet to infer analog patterns.")
        else:
            insight = result.pattern_insight
            if insight.matches:
                st.plotly_chart(
                    create_pattern_matches_chart(insight),
                    width="stretch",
                    key="pattern-matches-chart",
                )
            st.write(f"**Pattern Signature:** `{insight.pattern_signature}`")
            st.write(f"**Pattern Length:** {insight.pattern_length} legs")
            st.write(f"**Forecast Horizon:** {insight.forecast_horizon} legs")
            st.write(f"**Matches Used:** {insight.matches_used}")
            st.write(f"**Base Confidence:** {insight.base_confidence * 100:.1f}%")
            st.write(
                f"**Historical Direction Hit Rate:** {insight.historical_direction_hit_rate * 100:.1f}%"
            )
            st.write(
                f"**Historical Horizon Hit Rate:** {insight.historical_horizon_hit_rate * 100:.1f}%"
            )

            matches_data = [
                {
                    "Anchor Leg": match.anchor_leg_id,
                    "Similarity": f"{match.similarity_score * 100:.1f}%",
                    "Next Direction": match.next_direction.upper(),
                    "Next Change %": f"{match.next_change_pct:+.2f}%",
                    "Next Duration Bars": match.next_duration_bars,
                    "Horizon Change %": f"{match.horizon_change_pct:+.2f}%",
                    "Horizon Direction": match.horizon_direction.upper(),
                }
                for match in insight.matches
            ]
            with st.expander("Detailed analog matches", expanded=False):
                st.dataframe(matches_data, width="stretch", hide_index=True)

    with tab5:
        st.subheader("Pattern Learning")
        if result.pattern_learning is None:
            st.info("No learning stats available yet.")
        else:
            learning = result.pattern_learning
            st.plotly_chart(
                create_learning_outcomes_chart(learning),
                width="stretch",
                key="learning-outcomes-chart",
            )
            st.write(f"**Backtests Run This Analysis:** {learning.total_backtests}")
            st.write(f"**Current Run Direction Hit Rate:** {learning.direction_hit_rate * 100:.1f}%")
            st.write(f"**Current Run Horizon Hit Rate:** {learning.horizon_hit_rate * 100:.1f}%")
            st.write(f"**Persistent Samples:** {learning.persistent_samples}")
            st.write(
                f"**Persistent Direction Hit Rate:** {learning.persistent_direction_hit_rate * 100:.1f}%"
            )
            st.write(
                f"**Persistent Horizon Hit Rate:** {learning.persistent_horizon_hit_rate * 100:.1f}%"
            )
            st.write(f"**Adaptive Weight:** {learning.adaptive_weight * 100:.1f}%")
            st.write(f"**Current Regime:** {learning.regime_label}")
            st.write(f"**Regime Samples:** {learning.regime_samples}")
            st.write(
                f"**Regime Direction Hit Rate:** {learning.regime_direction_hit_rate * 100:.1f}%"
            )
            st.write(
                f"**Regime Horizon Hit Rate:** {learning.regime_horizon_hit_rate * 100:.1f}%"
            )
            distribution_rows = [
                {
                    "Outcome": "Next Leg %",
                    "P25": _format_optional_pct(learning.p25_next_change_pct),
                    "Median": _format_optional_pct(learning.median_next_change_pct),
                    "P75": _format_optional_pct(learning.p75_next_change_pct),
                },
                {
                    "Outcome": "Horizon %",
                    "P25": _format_optional_pct(learning.p25_horizon_change_pct),
                    "Median": _format_optional_pct(learning.median_horizon_change_pct),
                    "P75": _format_optional_pct(learning.p75_horizon_change_pct),
                },
            ]
            with st.expander("Outcome percentile details", expanded=False):
                st.dataframe(distribution_rows, width="stretch", hide_index=True)
            if learning.median_next_duration_bars is not None:
                st.write(f"**Median Next Duration:** {learning.median_next_duration_bars:.1f} bars")

            if result.pattern_backtests:
                backtest_rows = [
                    {
                        "Anchor Leg": record.anchor_leg_id,
                        "Pattern": record.pattern_signature,
                        "Predicted Dir": record.predicted_direction.upper(),
                        "Actual Dir": record.actual_direction.upper(),
                        "Predicted Horizon": record.predicted_horizon_direction.upper(),
                        "Actual Horizon": record.actual_horizon_direction.upper(),
                        "Adaptive Confidence": f"{record.adaptive_confidence * 100:.1f}%",
                        "Direction Correct": "Yes" if record.was_direction_correct else "No",
                        "Horizon Held": "Yes" if record.did_horizon_hold else "No",
                        "Realized Next %": f"{record.realized_next_change_pct:+.2f}%",
                        "Realized Horizon %": f"{record.realized_horizon_change_pct:+.2f}%",
                    }
                    for record in result.pattern_backtests
                ]
                with st.expander("Backtest records", expanded=False):
                    st.dataframe(backtest_rows, width="stretch", hide_index=True)

    with tab6:
        render_prediction_journal(result, config.output_dir)

    with tab7:
        st.subheader("Moon Phases")
        if result.moon_phase_insight is None:
            st.info("Enable the moon phase indicator in the sidebar and rerun analysis to see lunar correlation stats.")
        else:
            moon = result.moon_phase_insight
            if moon.phase_stats:
                st.plotly_chart(
                    create_moon_phase_bias_chart(moon),
                    width="stretch",
                    key="moon-phase-bias-chart",
                )
            st.write(f"**Adaptive Alignment Window:** {moon.phase_window_hours:.1f} hours")
            st.write(f"**Aligned Events:** {moon.aligned_events} / {moon.total_events}")

            if moon.phase_stats:
                phase_rows = [
                    {
                        "Phase": stat.phase_name,
                        "Occurrences": stat.occurrences,
                        "Aligned": stat.aligned_events,
                        "Alignment Rate": f"{stat.alignment_rate * 100:.1f}%",
                        "Avg Hours To Pivot": (
                            f"{stat.avg_hours_to_pivot:.1f}h"
                            if stat.avg_hours_to_pivot is not None
                            else "N/A"
                        ),
                        "Swing High Rate": f"{stat.swing_high_rate * 100:.1f}%",
                        "Swing Low Rate": f"{stat.swing_low_rate * 100:.1f}%",
                        "Bullish Next Leg": f"{stat.bullish_next_leg_rate * 100:.1f}%",
                        "Bearish Next Leg": f"{stat.bearish_next_leg_rate * 100:.1f}%",
                        "Avg Next Leg %": (
                            f"{stat.avg_next_leg_change_pct:+.2f}%"
                            if stat.avg_next_leg_change_pct is not None
                            else "N/A"
                        ),
                        "Bias": stat.dominant_bias.title(),
                    }
                    for stat in moon.phase_stats
                ]
                with st.expander("Moon phase statistics", expanded=False):
                    st.dataframe(phase_rows, width="stretch", hide_index=True)

            if moon.events:
                event_rows = [
                    {
                        "Timestamp": event.timestamp.strftime("%Y-%m-%d %H:%M"),
                        "Phase": event.phase_name,
                        "Nearest Pivot": (
                            event.nearest_pivot_type.replace("_", " ").title()
                            if event.nearest_pivot_type
                            else "N/A"
                        ),
                        "Hours To Pivot": (
                            f"{event.hours_to_nearest_pivot:.1f}"
                            if event.hours_to_nearest_pivot is not None
                            else "N/A"
                        ),
                        "Aligned": "Yes" if event.aligned_within_window else "No",
                        "Next Leg": event.next_leg_direction.title() if event.next_leg_direction else "N/A",
                        "Next Leg %": (
                            f"{event.next_leg_percent_change:+.2f}%"
                            if event.next_leg_percent_change is not None
                            else "N/A"
                        ),
                    }
                    for event in moon.events
                ]
                with st.expander("Moon phase event log", expanded=False):
                    st.dataframe(event_rows, width="stretch", hide_index=True)

    with tab8:
        st.subheader("Market Correlations")
        if not correlation_insights:
            st.info("Enable the gold or Nasdaq indicator in the sidebar and rerun analysis to chart cross-asset correlation.")
        else:
            for insight in correlation_insights:
                st.write(f"**{insight.asset_name} ({insight.asset_symbol})**")
                st.write(f"**Price Correlation:** {insight.price_correlation:+.2f}" if insight.price_correlation is not None else "**Price Correlation:** N/A")
                st.write(f"**Return Correlation:** {insight.return_correlation:+.2f}" if insight.return_correlation is not None else "**Return Correlation:** N/A")
                st.write(f"**Beta To Asset:** {insight.beta_to_asset:+.2f}" if insight.beta_to_asset is not None else "**Beta To Asset:** N/A")
                st.write(f"**Rolling Window:** {insight.rolling_window_days} days")
                st.plotly_chart(
                    create_asset_correlation_chart(insight),
                    width="stretch",
                    key=f"asset-correlation-tab-{insight.asset_symbol}",
                )

    with tab9:
        render_saved_period_comparison_reviews(config.output_dir, key_prefix="comparison-tab-saved")

    with tab10:
        render_glossary()

    # Export section
    st.header("Export")
    if st.button("Export All Results"):
        files = service.export_results(result)
        st.success(f"Exported {len(files)} files to {config.output_dir}/")

    render_parallax_footer()


if __name__ == "__main__":
    main()
