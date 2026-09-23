"""Streamlit app components for BTC Swing Cycle Tracker.

Reusable UI components for the Streamlit interface.
"""

from typing import Optional

import streamlit as st
import plotly.graph_objects as go

from btc_cycle_tracker.models import AnalysisResult, PivotPoint, SwingLeg


def render_config_form() -> dict:
    """Render configuration form and return config dict.

    Returns:
        Dictionary with configuration values
    """
    st.header("Analysis Configuration")

    col1, col2 = st.columns(2)

    with col1:
        symbol = st.text_input("Symbol", value="BTC-USD")
        timeframe = st.selectbox(
            "Timeframe",
            options=["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"],
            index=2,
        )
        lookback = st.text_input("Lookback Period", value="30d")

    with col2:
        pivot_method = st.selectbox(
            "Pivot Method",
            options=["zigzag", "fractal"],
            index=0,
        )
        min_move_pct = st.slider("Min Move %", 0.1, 10.0, 1.0, 0.1)
        left_bars = st.slider("Left Bars", 1, 20, 5)
        right_bars = st.slider("Right Bars", 1, 20, 5)

    st.divider()

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "lookback": lookback,
        "pivot_method": pivot_method,
        "min_move_pct": min_move_pct,
        "left_bars": left_bars,
        "right_bars": right_bars,
    }


def render_summary_cards(result: AnalysisResult) -> None:
    """Render summary metric cards.

    Args:
        result: AnalysisResult object
    """
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Pivots", result.metadata.total_pivots)

    with col2:
        st.metric("Total Legs", result.metadata.total_legs)

    with col3:
        st.metric("Avg % Change", f"{result.summary.avg_percent_change:.2f}%")

    with col4:
        st.metric("Avg Duration", f"{result.summary.avg_duration_minutes:.1f} min")


def render_chart(
    result: AnalysisResult,
    title: Optional[str] = None,
    height: int = 600,
) -> None:
    """Render the candlestick chart with pivots and legs.

    Args:
        result: AnalysisResult object
        title: Chart title (auto-generated if None)
        height: Chart height in pixels
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
            marker=dict(symbol="triangle-down", size=10, color="#f39c12"),
        ))

    if low_pivots:
        fig.add_trace(go.Scatter(
            x=[p.timestamp for p in low_pivots],
            y=[p.price for p in low_pivots],
            mode="markers",
            name="Swing Lows",
            marker=dict(symbol="triangle-up", size=10, color="#3498db"),
        ))

    # Add legs
    for leg in result.legs:
        fig.add_trace(go.Scatter(
            x=[leg.start_pivot.timestamp, leg.end_pivot.timestamp],
            y=[leg.start_pivot.price, leg.end_pivot.price],
            mode="lines",
            line=dict(color="#2ecc71" if leg.is_up else "#e74c3c", width=2),
            showlegend=False,
        ))

    fig.update_layout(
        title=title,
        height=height,
        xaxis_rangeslider_visible=False,
    )

    st.plotly_chart(fig, width="stretch")


def render_legs_table(result: AnalysisResult) -> None:
    """Render the legs data table.

    Args:
        result: AnalysisResult object
    """
    st.subheader("Swing Legs")

    data = []
    for i, leg in enumerate(result.legs):
        data.append({
            "Leg": i + 1,
            "Start": leg.start_pivot.timestamp.strftime("%Y-%m-%d %H:%M"),
            "End": leg.end_pivot.timestamp.strftime("%Y-%m-%d %H:%M"),
            "Start Price": f"${leg.start_pivot.price:.2f}",
            "End Price": f"${leg.end_pivot.price:.2f}",
            "Change %": f"{leg.percent_change:+.2f}%",
            "Duration (min)": f"{leg.duration_seconds / 60:.1f}",
            "Direction": leg.direction.upper(),
        })

    st.dataframe(data, width="stretch", hide_index=True)


def render_pivots_table(result: AnalysisResult) -> None:
    """Render the pivots data table.

    Args:
        result: AnalysisResult object
    """
    st.subheader("Pivot Points")

    data = []
    for pivot in result.pivots:
        data.append({
            "Index": pivot.index,
            "Timestamp": pivot.timestamp.strftime("%Y-%m-%d %H:%M"),
            "Price": f"${pivot.price:.2f}",
            "Type": pivot.pivot_type.replace("_", " ").title(),
        })

    st.dataframe(data, width="stretch", hide_index=True)


def render_statistics(result: AnalysisResult) -> None:
    """Render the statistics section.

    Args:
        result: AnalysisResult object
    """
    st.subheader("Statistics")

    col1, col2 = st.columns(2)

    with col1:
        st.write(f"**Period:** {result.metadata.start_date} to {result.metadata.end_date}")
        st.write(f"**Total Candles:** {result.metadata.total_candles}")
        st.write(f"**Total Pivots:** {result.metadata.total_pivots}")
        st.write(f"**Total Legs:** {result.metadata.total_legs}")

    with col2:
        st.write(f"**Min % Change:** {result.summary.min_percent_change:.2f}%")
        st.write(f"**Max % Change:** {result.summary.max_percent_change:.2f}%")
        st.write(f"**Avg % Change:** {result.summary.avg_percent_change:.2f}%")
        st.write(f"**Avg Duration:** {result.summary.avg_duration_minutes:.1f} min")

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.write(f"**Up Legs:** {result.summary.up_legs_count}")
        st.write(f"**Down Legs:** {result.summary.down_legs_count}")

    with col2:
        st.write(f"**Up Legs Avg:** {result.summary.up_legs_avg_change:.2f}%")
        st.write(f"**Down Legs Avg:** {result.summary.down_legs_avg_change:.2f}%")


def render_export_section(result: AnalysisResult) -> None:
    """Render the export section.

    Args:
        result: AnalysisResult object
    """
    st.subheader("Export Results")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Download Legs CSV"):
            from btc_cycle_tracker.export.csv_writer import CSVWriter
            csv_writer = CSVWriter()
            csv_path = csv_writer.write_legs(result.legs)
            with open(csv_path, "rb") as f:
                st.download_button(
                    "Download Legs CSV",
                    f.read(),
                    "legs.csv",
                    "text/csv",
                )

    with col2:
        if st.button("Download Pivots CSV"):
            from btc_cycle_tracker.export.csv_writer import CSVWriter
            csv_writer = CSVWriter()
            csv_path = csv_writer.write_pivots(result.pivots)
            with open(csv_path, "rb") as f:
                st.download_button(
                    "Download Pivots CSV",
                    f.read(),
                    "pivots.csv",
                    "text/csv",
                )
