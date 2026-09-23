"""Chart components for the Streamlit app."""

from typing import Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from btc_cycle_tracker.models import AnalysisResult, AssetCorrelationInsight, MoonPhaseEvent

_MOON_PHASE_COLORS = {
    "New Moon": "#95a5a6",
    "First Quarter": "#f1c40f",
    "Full Moon": "#ecf0f1",
    "Last Quarter": "#3498db",
}

_MOON_PHASE_LABELS = {
    "New Moon": "New",
    "First Quarter": "1Q",
    "Full Moon": "Full",
    "Last Quarter": "3Q",
}

_ASSET_COLORS = {
    "Gold": "#d4af37",
    "Nasdaq": "#63a4ff",
    "Oil": "#1f1f1f",
}


def _leg_color(start_price: float, end_price: float) -> str:
    """Color legs by their actual plotted slope, not just metadata."""
    try:
        return "#2ecc71" if float(end_price) > float(start_price) else "#e74c3c"
    except (TypeError, ValueError):
        return "#e74c3c"


def add_structure_overlays(fig: go.Figure, result: AnalysisResult) -> go.Figure:
    """Add discoveries to a plain Plotly figure's default x/y axes."""
    for discovery in result.structure_discoveries:
        color = (
            "#2ecc71" if discovery.direction == "bullish"
            else "#e74c3c" if discovery.direction == "bearish"
            else "#60a5fa"
        )
        if discovery.zone_low is not None and discovery.zone_high is not None:
            fig.add_hrect(
                y0=discovery.zone_low,
                y1=discovery.zone_high,
                fillcolor=color,
                opacity=0.10,
                line_width=1,
                line_dash="dot",
                annotation_text=discovery.title,
                annotation_position="top left",
            )
        if (
            discovery.structure_type in {"break_of_structure", "change_of_character"}
            and discovery.anchors
        ):
            event = discovery.anchors[-1]
            fig.add_annotation(
                x=event.timestamp,
                y=event.price,
                text=(
                    "CHoCH"
                    if discovery.structure_type == "change_of_character"
                    else "BOS"
                ),
                showarrow=True,
                arrowcolor=color,
                font=dict(color=color),
            )
    return fig


def create_candlestick_chart(
    result: AnalysisResult,
    title: Optional[str] = None,
    height: int = 600,
    show_all_legs: bool = False,
    major_leg_threshold: float = 2.0,
    moon_phase_events: Optional[list[MoonPhaseEvent]] = None,
) -> go.Figure:
    """Create a candlestick chart with pivots and legs.

    Args:
        result: AnalysisResult object
        title: Chart title (auto-generated if None)
        height: Chart height in pixels
        show_all_legs: Whether to show all legs or only major ones
        major_leg_threshold: Minimum percent change for a leg to be considered major

    Returns:
        Plotly figure object
    """
    if title is None:
        title = f"{result.metadata.symbol} Swing Cycle Analysis"

    fig = go.Figure()

    # Add candlestick
    fig.add_trace(go.Candlestick(
        x=[d.timestamp for d in result.raw_data],
        open=[d.open for d in result.raw_data],
        high=[d.high for d in result.raw_data],
        low=[d.low for d in result.raw_data],
        close=[d.close for d in result.raw_data],
        name="OHLC",
        increasing_line_color="#2ecc71",
        decreasing_line_color="#e74c3c",
        showlegend=False,
    ))

    # Add pivots
    high_pivots = [p for p in result.pivots if p.pivot_type == "swing_high"]
    low_pivots = [p for p in result.pivots if p.pivot_type == "swing_low"]

    if high_pivots:
        fig.add_trace(go.Scatter(
            x=[p.timestamp for p in high_pivots],
            y=[p.price for p in high_pivots],
            mode="markers",
            name="Swing Highs",
            marker=dict(symbol="triangle-down", size=10, color="#f39c12", line=dict(color="black", width=1)),
            showlegend=False,
        ))

    if low_pivots:
        fig.add_trace(go.Scatter(
            x=[p.timestamp for p in low_pivots],
            y=[p.price for p in low_pivots],
            mode="markers",
            name="Swing Lows",
            marker=dict(symbol="triangle-up", size=10, color="#3498db", line=dict(color="black", width=1)),
            showlegend=False,
        ))

    # Add legs (only major legs by default to reduce clutter)
    legs_to_show = result.legs if show_all_legs else [leg for leg in result.legs if abs(leg.percent_change) >= major_leg_threshold]

    for leg in legs_to_show:
        duration_minutes = getattr(leg, "duration_minutes", None)
        if not isinstance(duration_minutes, (int, float)):
            duration_seconds = getattr(leg, "duration_seconds", 0.0)
            duration_minutes = duration_seconds / 60 if isinstance(duration_seconds, (int, float)) else 0.0
        color = _leg_color(leg.start_price, leg.end_price)
        fig.add_trace(go.Scatter(
            x=[leg.start_timestamp, leg.end_timestamp],
            y=[leg.start_price, leg.end_price],
            mode="lines",
            line=dict(color=color, width=2),
            showlegend=False,
            hovertemplate=f"Leg {leg.leg_id}: {leg.percent_change:+.2f}%<br>{duration_minutes:.1f} min<extra></extra>",
        ))

    if moon_phase_events:
        marker_y = max(d.high for d in result.raw_data) * 1.02

        for event in moon_phase_events:
            fig.add_vline(
                x=event.timestamp,
                line_dash="dot",
                line_color=_MOON_PHASE_COLORS.get(event.phase_name, "#bdc3c7"),
                opacity=0.28,
            )

        fig.add_trace(
            go.Scatter(
                x=[event.timestamp for event in moon_phase_events],
                y=[marker_y] * len(moon_phase_events),
                mode="markers+text",
                name="Moon Phases",
                text=[_MOON_PHASE_LABELS.get(event.phase_name, event.phase_name) for event in moon_phase_events],
                textposition="top center",
                marker=dict(
                    size=10,
                    color=[
                        _MOON_PHASE_COLORS.get(event.phase_name, "#bdc3c7")
                        for event in moon_phase_events
                    ],
                    line=dict(color="#2c3e50", width=1),
                ),
                cliponaxis=False,
                showlegend=False,
                hovertemplate=(
                    "Moon Phase: %{customdata[0]}<br>"
                    "Time: %{x|%Y-%m-%d %H:%M}<br>"
                    "Nearest Pivot: %{customdata[1]}<br>"
                    "Next Leg: %{customdata[2]}<extra></extra>"
                ),
                customdata=[
                    [
                        event.phase_name,
                        (
                            f"{event.nearest_pivot_type} ({event.hours_to_nearest_pivot:.1f}h)"
                            if event.nearest_pivot_type and event.hours_to_nearest_pivot is not None
                            else "N/A"
                        ),
                        (
                            f"{event.next_leg_direction} {event.next_leg_percent_change:+.2f}%"
                            if event.next_leg_direction and event.next_leg_percent_change is not None
                            else "N/A"
                        ),
                    ]
                    for event in moon_phase_events
                ],
            )
        )

    fig.update_layout(
        title=title,
        height=height,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(l=50, r=50, t=50, b=50),
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.96)",
            bordercolor="rgba(0, 0, 0, 0.18)",
            font=dict(color="#000000"),
        ),
    )

    return fig


def create_asset_correlation_chart(insight: AssetCorrelationInsight) -> go.Figure:
    """Create a normalized comparison chart plus rolling return correlation."""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.68, 0.32],
        vertical_spacing=0.1,
    )

    asset_color = _ASSET_COLORS.get(insight.asset_name, "#95a5a6")
    x_values = [obs.timestamp for obs in insight.observations]
    btc_values = [obs.btc_normalized for obs in insight.observations]
    asset_values = [obs.asset_normalized for obs in insight.observations]
    rolling_values = [obs.rolling_return_correlation for obs in insight.observations]

    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=btc_values,
            mode="lines",
            name="BTC",
            line=dict(color="#f7931a", width=2.5),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=asset_values,
            mode="lines",
            name=insight.asset_name,
            line=dict(color=asset_color, width=2.2),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=rolling_values,
            mode="lines",
            name=f"Rolling Corr ({insight.rolling_window_days}d)",
            line=dict(color="#2c3e50", width=2),
        ),
        row=2,
        col=1,
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5, row=2, col=1)

    fig.update_layout(
        title=f"BTC vs {insight.asset_name} Correlation",
        height=520,
        margin=dict(l=50, r=30, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )
    fig.update_yaxes(title_text="Normalized Price (Base 100)", row=1, col=1)
    fig.update_yaxes(title_text="Rolling Return Corr", row=2, col=1, range=[-1, 1])
    return fig


def create_leg_distribution_chart(
    result: AnalysisResult,
    num_bins: int = 10,
) -> go.Figure:
    """Create a histogram of leg percentage changes.

    Args:
        result: AnalysisResult object
        num_bins: Number of histogram bins

    Returns:
        Plotly figure object
    """
    percent_changes = [leg.percent_change for leg in result.legs]

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=percent_changes,
        nbinsx=num_bins,
        name="Leg Distribution",
        marker_color="#3498db",
        opacity=0.7,
        hovertemplate="Change: %{x:.2f}%<br>Count: %{y}<extra></extra>",
    ))

    # Add vertical line at zero
    fig.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        title="Leg Percentage Change Distribution",
        xaxis_title="Percent Change (%)",
        yaxis_title="Count",
        bargap=0.1,
        showlegend=False,
        margin=dict(l=50, r=50, t=50, b=50),
    )

    return fig


def create_duration_distribution_chart(
    result: AnalysisResult,
    num_bins: int = 10,
) -> go.Figure:
    """Create a histogram of leg durations.

    Args:
        result: AnalysisResult object
        num_bins: Number of histogram bins

    Returns:
        Plotly figure object
    """
    durations = [leg.duration_seconds / 60 for leg in result.legs]  # Convert to minutes

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=durations,
        nbinsx=num_bins,
        name="Duration Distribution",
        marker_color="#e74c3c",
        opacity=0.7,
        hovertemplate="Duration: %{x:.1f} min<br>Count: %{y}<extra></extra>",
    ))

    fig.update_layout(
        title="Leg Duration Distribution",
        xaxis_title="Duration (minutes)",
        yaxis_title="Count",
        bargap=0.1,
        showlegend=False,
        margin=dict(l=50, r=50, t=50, b=50),
    )

    return fig


def create_summary_stats_chart(
    result: AnalysisResult,
) -> go.Figure:
    """Create a summary statistics chart showing key metrics.

    Args:
        result: AnalysisResult object

    Returns:
        Plotly figure object
    """
    summary = result.summary

    fig = go.Figure()

    # Add bar chart for up vs down legs
    fig.add_trace(go.Bar(
        name="Leg Count",
        x=["Total Legs", "Up Legs", "Down Legs"],
        y=[summary.total_legs, summary.up_legs_count, summary.down_legs_count],
        marker_color=["#95a5a6", "#2ecc71", "#e74c3c"],
    ))

    # Add line chart for average changes
    fig.add_trace(go.Scatter(
        name="Avg Change",
        x=["Avg % Change", "Up Leg Avg", "Down Leg Avg"],
        y=[summary.avg_percent_change, summary.up_legs_avg_change or 0, summary.down_legs_avg_change or 0],
        mode="lines+markers",
        line=dict(color="#3498db", width=2),
        marker=dict(size=10),
    ))

    fig.update_layout(
        title="Summary Statistics",
        yaxis_title="Value",
        barmode="group",
        margin=dict(l=50, r=50, t=50, b=50),
        showlegend=True,
    )

    return fig


def create_pattern_probability_chart(result: AnalysisResult) -> go.Figure:
    """Visualize bullish vs bearish next-leg probabilities."""
    fig = go.Figure()

    insight = result.pattern_insight
    if insight is None:
        fig.update_layout(
            title="Pattern Probabilities",
            annotations=[dict(text="Pattern recognition not available", showarrow=False)],
        )
        return fig

    fig.add_trace(
        go.Bar(
            x=["Bullish", "Bearish"],
            y=[insight.bullish_probability * 100, insight.bearish_probability * 100],
            marker_color=["#2ecc71", "#e74c3c"],
            text=[f"{insight.bullish_probability * 100:.1f}%", f"{insight.bearish_probability * 100:.1f}%"],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Pattern-Derived Next Leg Bias",
        yaxis_title="Probability (%)",
        showlegend=False,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def create_pattern_learning_chart(result: AnalysisResult) -> go.Figure:
    """Chart direction and horizon hit rates for the learning engine."""
    fig = go.Figure()
    learning = result.pattern_learning
    if learning is None:
        fig.update_layout(
            title="Pattern Learning",
            annotations=[dict(text="Not enough data to evaluate patterns", showarrow=False)],
        )
        return fig

    fig.add_trace(
        go.Bar(
            x=[
                "Current Run Direction",
                "Current Run Horizon",
                "Persistent Direction",
                "Persistent Horizon",
            ],
            y=[
                learning.direction_hit_rate * 100,
                learning.horizon_hit_rate * 100,
                learning.persistent_direction_hit_rate * 100,
                learning.persistent_horizon_hit_rate * 100,
            ],
            marker_color=["#3498db", "#9b59b6", "#2ecc71", "#f39c12"],
            text=[
                f"{learning.direction_hit_rate * 100:.1f}%",
                f"{learning.horizon_hit_rate * 100:.1f}%",
                f"{learning.persistent_direction_hit_rate * 100:.1f}%",
                f"{learning.persistent_horizon_hit_rate * 100:.1f}%",
            ],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Pattern Learning Hit Rates",
        yaxis_title="Hit Rate (%)",
        showlegend=False,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig
