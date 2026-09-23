"""Plotly-based interactive chart creation with enhanced visualization."""

from typing import Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from btc_cycle_tracker.models import OHLCV, PivotPoint, SwingLeg
from btc_cycle_tracker.settings import ChartSettings


def _leg_color(start_price: float, end_price: float) -> str:
    """Color legs by the actual price slope being drawn."""
    try:
        return "#2ecc71" if float(end_price) > float(start_price) else "#e74c3c"
    except (TypeError, ValueError):
        return "#e74c3c"


def create_candlestick_chart(
    data: list[OHLCV],
    pivots: Optional[list[PivotPoint]] = None,
    legs: Optional[list[SwingLeg]] = None,
    title: str = "BTC Swing Cycle Analysis",
    width: int = 1200,
    height: int = 800,
    show_volume: bool = True,
    theme: str = "plotly_dark",
    show_labels: bool = True,
) -> go.Figure:
    """Create an interactive candlestick chart with pivots and legs.

    Args:
        data: List of OHLCV candles
        pivots: List of pivot points (optional)
        legs: List of swing legs (optional)
        title: Chart title
        width: Chart width in pixels
        height: Chart height in pixels
        show_volume: Whether to show volume subplot
        theme: Plotly template theme
        show_labels: Whether to show labels on legs

    Returns:
        Plotly figure object
    """
    # Create figure with secondary y-axis
    if show_volume:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.7, 0.3],
        )
    else:
        fig = make_subplots(rows=1, cols=1)

    # Add candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=[d.timestamp for d in data],
            open=[d.open for d in data],
            high=[d.high for d in data],
            low=[d.low for d in data],
            close=[d.close for d in data],
            name="OHLC",
            increasing_line_color="#2ecc71",
            decreasing_line_color="#e74c3c",
            increasing_fillcolor="#2ecc71",
            decreasing_fillcolor="#e74c3c",
        ),
        row=1,
        col=1,
    )

    # Add volume if requested
    if show_volume:
        colors = [
            "#2ecc71" if d.close >= d.open else "#e74c3c"
            for d in data
        ]
        fig.add_trace(
            go.Bar(
                x=[d.timestamp for d in data],
                y=[d.volume for d in data],
                name="Volume",
                marker_color=colors,
                opacity=0.5,
            ),
            row=2,
            col=1,
        )

    # Add pivots if provided
    if pivots:
        high_pivots = [p for p in pivots if p.pivot_type == "swing_high"]
        low_pivots = [p for p in pivots if p.pivot_type == "swing_low"]

        if high_pivots:
            fig.add_trace(
                go.Scatter(
                    x=[p.timestamp for p in high_pivots],
                    y=[p.price for p in high_pivots],
                    mode="markers",
                    name="Swing Highs",
                    marker=dict(
                        symbol="triangle-down",
                        size=14,
                        color="#f39c12",
                        line=dict(color="black", width=1.5),
                        opacity=0.9,
                    ),
                    hovertemplate="High: $%{y:.2f}<br>%{x|%Y-%m-%d %H:%M}<extra></extra>",
                ),
                row=1,
                col=1,
            )

        if low_pivots:
            fig.add_trace(
                go.Scatter(
                    x=[p.timestamp for p in low_pivots],
                    y=[p.price for p in low_pivots],
                    mode="markers",
                    name="Swing Lows",
                    marker=dict(
                        symbol="triangle-up",
                        size=14,
                        color="#3498db",
                        line=dict(color="black", width=1.5),
                        opacity=0.9,
                    ),
                    hovertemplate="Low: $%{y:.2f}<br>%{x|%Y-%m-%d %H:%M}<extra></extra>",
                ),
                row=1,
                col=1,
            )

    # Add legs if provided
    if legs:
        for leg in legs:
            color = _leg_color(leg.start_price, leg.end_price)

            fig.add_trace(
                go.Scatter(
                    x=[leg.start_timestamp, leg.end_timestamp],
                    y=[leg.start_price, leg.end_price],
                    mode="lines",
                    name="Swing Legs",
                    line=dict(
                        color=color,
                        width=2.5,
                        shape="linear",
                    ),
                    showlegend=False,
                    hovertemplate="Leg: $%{y:.2f}<br>%{x|%Y-%m-%d %H:%M}<extra></extra>",
                ),
                row=1,
                col=1,
            )

            # Add leg labels if requested
            if show_labels:
                # Calculate midpoint for annotation
                mid_time = (
                    leg.start_timestamp
                    + (leg.end_timestamp - leg.start_timestamp) / 2
                )
                mid_price = (leg.start_price + leg.end_price) / 2

                pct_change = float(getattr(leg, "percent_change", 0.0))
                duration_mins = getattr(leg, "duration_minutes", None)
                if not isinstance(duration_mins, (int, float)):
                    duration_seconds = getattr(leg, "duration_seconds", 0.0)
                    duration_mins = (
                        duration_seconds / 60
                        if isinstance(duration_seconds, (int, float))
                        else 0.0
                    )

                text = f"{pct_change:+.1f}%<br>{duration_mins:.0f}m"

                fig.add_annotation(
                    x=mid_time,
                    y=mid_price,
                    text=text,
                    showarrow=False,
                    font=dict(
                        color=color,
                        size=11,
                    ),
                    bgcolor="rgba(255,255,255,0.85)",
                    bordercolor=color,
                    borderpad=4,
                    borderwidth=1,
                    row=1,
                    col=1,
                )

    # Update layout
    fig.update_layout(
        title=title,
        width=width,
        height=height,
        template=theme,
        xaxis_rangeslider_visible=False,
        xaxis2_rangeslider_visible=False,
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    # Update y-axes
    fig.update_yaxes(title_text="Price ($)", row=1, col=1, gridcolor="#333")
    if show_volume:
        fig.update_yaxes(title_text="Volume", row=2, col=1, gridcolor="#333")

    # Update x-axis
    fig.update_xaxes(
        row=1,
        col=1,
        gridcolor="#333",
        showgrid=True,
        zeroline=False,
    )

    return fig


def add_pivot_annotations(
    fig: go.Figure,
    pivots: list[PivotPoint],
    data: list[OHLCV],
    row: int = 1,
    col: int = 1,
) -> go.Figure:
    """Add annotations for pivot points.

    Args:
        fig: Plotly figure to annotate
        pivots: List of pivot points
        data: Full data series for reference
        row: Row to add annotations to
        col: Column to add annotations to

    Returns:
        Annotated figure
    """
    for pivot in pivots:
        # Get position for annotation
        idx = pivot.index
        if idx >= len(data):
            continue

        y_pos = pivot.price
        x_pos = pivot.timestamp

        # Add annotation
        fig.add_annotation(
            x=x_pos,
            y=y_pos,
            text=f"{pivot.pivot_type.replace('_', ' ').title()}<br>${y_pos:.2f}",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor="black",
            ax=0,
            ay=-40 if pivot.pivot_type == "swing_high" else 40,
            font=dict(size=10),
            bgcolor="white",
            bordercolor="black",
            borderpad=4,
            row=row,
            col=col,
        )

    return fig


def add_leg_annotations(
    fig: go.Figure,
    legs: list[SwingLeg],
    row: int = 1,
    col: int = 1,
) -> go.Figure:
    """Add annotations for swing legs showing percent change.

    Args:
        fig: Plotly figure to annotate
        legs: List of swing legs
        row: Row to add annotations to
        col: Column to add annotations to

    Returns:
        Annotated figure
    """
    for leg in legs:
        # Calculate midpoint for annotation
        mid_time = (
            leg.start_timestamp
            + (leg.end_timestamp - leg.start_timestamp) / 2
        )
        mid_price = (leg.start_price + leg.end_price) / 2

        pct_change = leg.percent_change
        duration_mins = leg.duration_minutes

        text = f"{pct_change:+.1f}%<br>{duration_mins:.0f}m"

        fig.add_annotation(
            x=mid_time,
            y=mid_price,
            text=text,
            showarrow=False,
            font=dict(
                color=_leg_color(leg.start_price, leg.end_price),
                size=10,
            ),
            bgcolor="rgba(255,255,255,0.8)",
            borderpad=4,
            row=row,
            col=col,
        )

    return fig


def save_chart(
    fig: go.Figure,
    filepath: str,
    format: str = "html",
    width: int = 1200,
    height: int = 800,
) -> None:
    """Save a Plotly figure to a file.

    Args:
        fig: Plotly figure to save
        filepath: Output file path
        format: Output format (html, png, svg)
        width: Image width (for static formats)
        height: Image height (for static formats)
    """
    if format == "html":
        fig.write_html(filepath)
    elif format == "png":
        fig.write_image(filepath, width=width, height=height)
    elif format == "svg":
        fig.write_image(filepath, format="svg")
