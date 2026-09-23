"""Table components for the Streamlit app."""

from typing import Optional

import pandas as pd
import streamlit as st

from btc_cycle_tracker.models import AnalysisResult


def render_legs_table(
    result: AnalysisResult,
    max_rows: Optional[int] = None,
) -> None:
    """Render the legs data table.

    Args:
        result: AnalysisResult object
        max_rows: Maximum rows to display (None for all)
    """
    st.subheader("Swing Legs")

    data = []
    for i, leg in enumerate(result.legs[:max_rows] if max_rows else result.legs):
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

    df = pd.DataFrame(data)
    st.dataframe(df, width="stretch", hide_index=True)


def render_pivots_table(
    result: AnalysisResult,
    max_rows: Optional[int] = None,
) -> None:
    """Render the pivots data table.

    Args:
        result: AnalysisResult object
        max_rows: Maximum rows to display (None for all)
    """
    st.subheader("Pivot Points")

    data = []
    for pivot in result.pivots[:max_rows] if max_rows else result.pivots:
        data.append({
            "Index": pivot.index,
            "Timestamp": pivot.timestamp.strftime("%Y-%m-%d %H:%M"),
            "Price": f"${pivot.price:.2f}",
            "Type": pivot.pivot_type.replace("_", " ").title(),
        })

    df = pd.DataFrame(data)
    st.dataframe(df, width="stretch", hide_index=True)


def render_summary_table(result: AnalysisResult) -> None:
    """Render the summary statistics table.

    Args:
        result: AnalysisResult object
    """
    st.subheader("Summary Statistics")

    data = {
        "Metric": [
            "Total Legs",
            "Average % Change",
            "Min % Change",
            "Max % Change",
            "Avg Duration (min)",
            "Up Legs Count",
            "Down Legs Count",
            "Up Legs Avg %",
            "Down Legs Avg %",
        ],
        "Value": [
            result.metadata.total_legs,
            f"{result.summary.avg_percent_change:.2f}%",
            f"{result.summary.min_percent_change:.2f}%",
            f"{result.summary.max_percent_change:.2f}%",
            f"{result.summary.avg_duration_minutes:.1f}",
            result.summary.up_legs_count,
            result.summary.down_legs_count,
            f"{result.summary.up_legs_avg_change:.2f}%",
            f"{result.summary.down_legs_avg_change:.2f}%",
        ],
    }

    df = pd.DataFrame(data)
    st.dataframe(df, width="stretch", hide_index=True)
