"""Annotation utilities for chart visualization."""

from btc_cycle_tracker.models import PivotPoint, SwingLeg


def add_pivot_annotations(
    pivots: list[PivotPoint],
    data: list,
) -> list[dict]:
    """Generate annotation data for pivot points.

    Args:
        pivots: List of pivot points
        data: Full data series for reference

    Returns:
        List of annotation dictionaries
    """
    annotations = []
    for pivot in pivots:
        annotation = {
            "x": pivot.timestamp.isoformat(),
            "y": pivot.price,
            "text": f"{pivot.pivot_type.replace('_', ' ').title()}<br>${pivot.price:.2f}",
            "showarrow": True,
            "arrowhead": 2,
            "arrowsize": 1,
            "arrowwidth": 2,
            "arrowcolor": "black",
            "ax": 0,
            "ay": -40 if pivot.pivot_type == "swing_high" else 40,
            "font": {"size": 10},
            "bgcolor": "white",
            "bordercolor": "black",
            "borderpad": 4,
        }
        annotations.append(annotation)

    return annotations


def add_leg_annotations(
    legs: list[SwingLeg],
) -> list[dict]:
    """Generate annotation data for swing legs.

    Args:
        legs: List of swing legs

    Returns:
        List of annotation dictionaries
    """
    annotations = []
    for leg in legs:
        # Calculate midpoint for annotation
        mid_time = (
            leg.start_pivot.timestamp
            + (leg.end_pivot.timestamp - leg.start_pivot.timestamp) / 2
        )
        mid_price = (leg.start_pivot.price + leg.end_pivot.price) / 2

        pct_change = leg.percent_change
        duration_mins = leg.duration_seconds / 60

        annotation = {
            "x": mid_time.isoformat(),
            "y": mid_price,
            "text": f"{pct_change:+.2f}%<br>{duration_mins:.0f}m",
            "showarrow": False,
            "font": {
                "color": "#2ecc71" if leg.is_up else "#e74c3c",
                "size": 10,
                "weight": "bold",
            },
            "bgcolor": "rgba(255,255,255,0.8)",
            "borderpad": 4,
        }
        annotations.append(annotation)

    return annotations


def add_price_level_annotations(
    price_levels: list[float],
    labels: list[str],
    timestamp: str,
) -> list[dict]:
    """Generate annotation data for price levels.

    Args:
        price_levels: List of price levels
        labels: Labels for each price level
        timestamp: Timestamp for the annotation

    Returns:
        List of annotation dictionaries
    """
    annotations = []
    for price, label in zip(price_levels, labels):
        annotation = {
            "x": timestamp,
            "y": price,
            "text": label,
            "showarrow": True,
            "arrowhead": 0,
            "ax": 10,
            "ay": 0,
            "font": {"size": 10},
            "bgcolor": "rgba(255,255,255,0.8)",
            "bordercolor": "black",
            "borderpad": 4,
        }
        annotations.append(annotation)

    return annotations
