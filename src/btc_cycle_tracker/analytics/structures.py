"""Deterministic discovery of core pivot-based market structures."""

from __future__ import annotations

from btc_cycle_tracker.models import (
    OHLCV,
    PivotPoint,
    PivotType,
    StructureAnchor,
    StructureDiscovery,
)


def _anchor(pivot: PivotPoint, role: str) -> StructureAnchor:
    return StructureAnchor(timestamp=pivot.timestamp, price=pivot.price, role=role)


def _confidence(base: float, touches: int = 0) -> float:
    return min(0.95, round(base + max(0, touches - 2) * 0.06, 3))


def _trend_discovery(pivots: list[PivotPoint]) -> StructureDiscovery | None:
    highs = [p for p in pivots if p.pivot_type == PivotType.SWING_HIGH]
    lows = [p for p in pivots if p.pivot_type == PivotType.SWING_LOW]
    if len(highs) < 2 or len(lows) < 2:
        return None
    h1, h2 = highs[-2:]
    l1, l2 = lows[-2:]
    if h2.price > h1.price and l2.price > l1.price:
        title, direction, kind = "Rising swing structure", "bullish", "uptrend_structure"
        evidence = ["Latest swing high is above the prior high", "Latest swing low is above the prior low"]
        invalidation = l2.price
    elif h2.price < h1.price and l2.price < l1.price:
        title, direction, kind = "Falling swing structure", "bearish", "downtrend_structure"
        evidence = ["Latest swing high is below the prior high", "Latest swing low is below the prior low"]
        invalidation = h2.price
    else:
        title, direction, kind = "Mixed swing structure", "neutral", "mixed_structure"
        evidence = ["Swing highs and lows do not confirm the same direction"]
        invalidation = None
    anchors = [_anchor(h1, "prior_high"), _anchor(h2, "latest_high"), _anchor(l1, "prior_low"), _anchor(l2, "latest_low")]
    return StructureDiscovery(
        discovery_id=f"{kind}-{max(h2.index, l2.index)}", structure_type=kind,
        title=title, status="confirmed", direction=direction, confidence=0.86 if direction != "neutral" else 0.62,
        start_timestamp=min(a.timestamp for a in anchors), end_timestamp=max(a.timestamp for a in anchors),
        anchors=anchors, evidence=evidence, invalidation_price=invalidation,
        measurements={"high_change_pct": round((h2.price / h1.price - 1) * 100, 2), "low_change_pct": round((l2.price / l1.price - 1) * 100, 2)},
    )


def _break_discovery(pivots: list[PivotPoint]) -> StructureDiscovery | None:
    if len(pivots) < 5:
        return None
    highs = [p for p in pivots if p.pivot_type == PivotType.SWING_HIGH]
    lows = [p for p in pivots if p.pivot_type == PivotType.SWING_LOW]
    candidates = []
    if len(highs) >= 2 and highs[-1].price > highs[-2].price:
        prior_falling = len(highs) >= 3 and highs[-2].price < highs[-3].price
        candidates.append((highs[-1], highs[-2], "bullish", "change_of_character" if prior_falling else "break_of_structure"))
    if len(lows) >= 2 and lows[-1].price < lows[-2].price:
        prior_rising = len(lows) >= 3 and lows[-2].price > lows[-3].price
        candidates.append((lows[-1], lows[-2], "bearish", "change_of_character" if prior_rising else "break_of_structure"))
    if not candidates:
        return None
    event, broken, direction, kind = max(candidates, key=lambda item: item[0].timestamp)
    label = "Change of character" if kind == "change_of_character" else "Break of structure"
    move = abs(event.price / broken.price - 1) * 100
    return StructureDiscovery(
        discovery_id=f"{kind}-{event.index}", structure_type=kind, title=f"{direction.title()} {label.lower()}",
        status="confirmed", direction=direction, confidence=min(0.92, 0.72 + move / 20),
        start_timestamp=broken.timestamp, end_timestamp=event.timestamp,
        anchors=[_anchor(broken, "broken_level"), _anchor(event, "confirming_pivot")],
        evidence=[f"Confirmed pivot moved {move:.2f}% beyond the prior same-side pivot"],
        measurements={"break_pct": round(move, 2), "broken_level": round(broken.price, 2)},
        invalidation_price=broken.price,
    )


def _zones(pivots: list[PivotPoint], last_price: float, tolerance_pct: float) -> list[StructureDiscovery]:
    groups: list[list[PivotPoint]] = []
    for pivot in pivots[-30:]:
        for group in groups:
            center = sum(p.price for p in group) / len(group)
            if abs(pivot.price - center) / center * 100 <= tolerance_pct:
                group.append(pivot)
                break
        else:
            groups.append([pivot])
    out = []
    for group in groups:
        if len(group) < 2:
            continue
        prices = [p.price for p in group]
        center = sum(prices) / len(prices)
        low, high = min(prices), max(prices)
        direction = "bullish" if center < last_price else "bearish"
        role = "Support" if direction == "bullish" else "Resistance"
        out.append(StructureDiscovery(
            discovery_id=f"{role.lower()}-{round(center)}", structure_type=f"{role.lower()}_zone",
            title=f"{role} zone", status="active", direction=direction, confidence=_confidence(0.62, len(group)),
            start_timestamp=group[0].timestamp, end_timestamp=group[-1].timestamp,
            anchors=[_anchor(p, "touch") for p in group],
            evidence=[f"{len(group)} confirmed pivot touches within {tolerance_pct:.2f}%"],
            measurements={"touches": len(group), "center_price": round(center, 2)},
            invalidation_price=low if role == "Support" else high, zone_low=low, zone_high=high,
        ))
    return sorted(out, key=lambda d: (d.confidence, d.end_timestamp), reverse=True)[:6]


def _range_discovery(pivots: list[PivotPoint], tolerance_pct: float) -> StructureDiscovery | None:
    recent = pivots[-10:]
    highs = [p for p in recent if p.pivot_type == PivotType.SWING_HIGH]
    lows = [p for p in recent if p.pivot_type == PivotType.SWING_LOW]
    if len(highs) < 2 or len(lows) < 2:
        return None
    high_center = sum(p.price for p in highs) / len(highs)
    low_center = sum(p.price for p in lows) / len(lows)
    high_spread = (max(p.price for p in highs) - min(p.price for p in highs)) / high_center * 100
    low_spread = (max(p.price for p in lows) - min(p.price for p in lows)) / low_center * 100
    if high_spread > tolerance_pct * 2 or low_spread > tolerance_pct * 2:
        return None
    return StructureDiscovery(
        discovery_id=f"range-{recent[-1].index}", structure_type="range", title="Defined trading range",
        status="active", direction="neutral", confidence=_confidence(0.68, min(len(highs), len(lows))),
        start_timestamp=recent[0].timestamp, end_timestamp=recent[-1].timestamp,
        anchors=[*[_anchor(p, "upper_boundary_touch") for p in highs], *[_anchor(p, "lower_boundary_touch") for p in lows]],
        evidence=[f"{len(highs)} upper and {len(lows)} lower boundary touches"],
        measurements={"range_high": round(high_center, 2), "range_low": round(low_center, 2), "range_width_pct": round((high_center / low_center - 1) * 100, 2)},
        invalidation_price=None, zone_low=low_center, zone_high=high_center,
    )


def discover_structures(data: list[OHLCV], pivots: list[PivotPoint], min_move_pct: float = 1.0) -> list[StructureDiscovery]:
    """Return ranked, non-predictive discoveries from confirmed pivots."""
    if not data or not pivots:
        return []
    tolerance = max(0.35, min(2.0, min_move_pct * 0.5))
    discoveries = [item for item in (_trend_discovery(pivots), _break_discovery(pivots), _range_discovery(pivots, tolerance)) if item]
    discoveries.extend(_zones(pivots, data[-1].close, tolerance))
    return sorted(discoveries, key=lambda d: (d.confidence, d.end_timestamp), reverse=True)
