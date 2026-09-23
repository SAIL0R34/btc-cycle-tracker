"""Static chart creation using matplotlib (optional dependency)."""

from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

from btc_cycle_tracker.models import OHLCV, PivotPoint, SwingLeg


def create_static_chart(
    data: list[OHLCV],
    pivots: Optional[list[PivotPoint]] = None,
    legs: Optional[list[SwingLeg]] = None,
    title: str = "BTC Swing Cycle Analysis",
    width: int = 12,
    height: int = 8,
    save_path: Optional[str] = None,
) -> None:
    """Create a static candlestick chart with matplotlib.

    Args:
        data: List of OHLCV candles
        pivots: List of pivot points (optional)
        legs: List of swing legs (optional)
        title: Chart title
        width: Figure width in inches
        height: Figure height in inches
        save_path: Path to save the figure (optional)
    """
    fig, ax = plt.subplots(figsize=(width, height))

    # Plot candlesticks
    _plot_candlesticks(ax, data)

    # Plot pivots if provided
    if pivots:
        _plot_pivots(ax, pivots, data)

    # Plot legs if provided
    if legs:
        _plot_legs(ax, legs)

    # Format the chart
    ax.set_title(title, fontsize=16, fontweight="bold")
    ax.set_ylabel("Price ($)", fontsize=12)
    ax.set_xlabel("Date", fontsize=12)

    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
    plt.xticks(rotation=45, ha="right")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
    else:
        plt.show()

    plt.close()


def _plot_candlesticks(ax, data: list[OHLCV]) -> None:
    """Plot candlesticks on the given axes.

    Args:
        ax: Matplotlib axes
        data: List of OHLCV candles
    """
    colors = []
    for d in data:
        if d.close >= d.open:
            colors.append("#2ecc71")  # Green for up
        else:
            colors.append("#e74c3c")  # Red for down

    # Plot candlesticks
    for i, d in enumerate(data):
        # Draw wicks
        ax.plot([i, i], [d.low, d.high], color="black", linewidth=1)

        # Draw body
        body_top = max(d.open, d.close)
        body_bottom = min(d.open, d.close)
        ax.add_patch(
            plt.Rectangle(
                (i - 0.2, body_bottom),
                0.4,
                body_top - body_bottom,
                facecolor=colors[i],
                edgecolor="black",
                linewidth=1,
            )
        )

    # Set x-axis limits
    ax.set_xlim(-1, len(data))


def _plot_pivots(ax, pivots: list[PivotPoint], data: list[OHLCV]) -> None:
    """Plot pivot points on the chart.

    Args:
        ax: Matplotlib axes
        pivots: List of pivot points
        data: Full data series for reference
    """
    high_pivots = [p for p in pivots if p.pivot_type == "swing_high"]
    low_pivots = [p for p in pivots if p.pivot_type == "swing_low"]

    # Plot swing highs
    for p in high_pivots:
        if p.index < len(data):
            ax.plot(
                p.index,
                p.price,
                marker="v",
                markersize=10,
                markerfacecolor="#f39c12",
                markeredgecolor="black",
                linestyle="None",
            )

    # Plot swing lows
    for p in low_pivots:
        if p.index < len(data):
            ax.plot(
                p.index,
                p.price,
                marker="^",
                markersize=10,
                markerfacecolor="#3498db",
                markeredgecolor="black",
                linestyle="None",
            )


def _plot_legs(ax, legs: list[SwingLeg]) -> None:
    """Plot swing legs on the chart.

    Args:
        ax: Matplotlib axes
        legs: List of swing legs
    """
    for leg in legs:
        start_idx = leg.start_pivot.index
        end_idx = leg.end_pivot.index

        ax.plot(
            [start_idx, end_idx],
            [leg.start_pivot.price, leg.end_pivot.price],
            color="#2ecc71" if leg.is_up else "#e74c3c",
            linewidth=2,
        )


def format_currency(val, pos):
    """Format currency values for axis labels.

    Args:
        val: Value to format
        pos: Position (required by FuncFormatter)

    Returns:
        Formatted string
    """
    if val >= 1000:
        return f"${val/1000:.1f}k"
    return f"${val:.2f}"
