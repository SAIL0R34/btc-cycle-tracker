"""Summary components for the Streamlit app."""

import streamlit as st

from btc_cycle_tracker.models import AnalysisResult


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


def render_period_summary(result: AnalysisResult) -> None:
    """Render period summary section.

    Args:
        result: AnalysisResult object
    """
    st.subheader("Analysis Period")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.write(f"**Start:** {result.metadata.start_date.strftime('%Y-%m-%d %H:%M')}")

    with col2:
        st.write(f"**End:** {result.metadata.end_date.strftime('%Y-%m-%d %H:%M')}")

    with col3:
        duration = result.metadata.end_date - result.metadata.start_date
        st.write(f"**Duration:** {duration.days} days")


def render_statistics_section(result: AnalysisResult) -> None:
    """Render the statistics section.

    Args:
        result: AnalysisResult object
    """
    st.subheader("Statistics")

    col1, col2 = st.columns(2)

    with col1:
        st.write(f"**Total Candles:** {result.metadata.total_candles}")
        st.write(f"**Total Pivots:** {result.metadata.total_pivots}")
        st.write(f"**Total Legs:** {result.metadata.total_legs}")

    with col2:
        st.write(f"**Min % Change:** {result.summary.min_percent_change:.2f}%")
        st.write(f"**Max % Change:** {result.summary.max_percent_change:.2f}%")
        st.write(f"**Avg % Change:** {result.summary.avg_percent_change:.2f}%")


def render_direction_summary(result: AnalysisResult) -> None:
    """Render direction summary section.

    Args:
        result: AnalysisResult object
    """
    st.subheader("Direction Summary")

    col1, col2 = st.columns(2)

    with col1:
        st.write(f"**Up Legs:** {result.summary.up_legs_count}")
        if result.summary.up_legs_count > 0:
            st.write(f"**Avg Up Change:** {result.summary.up_legs_avg_change:.2f}%")

    with col2:
        st.write(f"**Down Legs:** {result.summary.down_legs_count}")
        if result.summary.down_legs_count > 0:
            st.write(f"**Avg Down Change:** {result.summary.down_legs_avg_change:.2f}%")


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
