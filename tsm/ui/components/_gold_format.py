"""Gold formatting and range choices used by the chart.

Kept free of PySide6 so the labels can be tested without a display stack.
"""

from __future__ import annotations

# Ranges offered above the plot. None means everything.
RANGES: tuple[tuple[str, int | None], ...] = (
    ("1D", 1),
    ("1W", 7),
    ("1M", 30),
    ("3M", 90),
    ("6M", 180),
    ("1Y", 365),
    ("2Y", 730),
    ("All", None),
)


def format_gold_short(copper: int) -> str:
    """Axis label: 2.4kg for kilogold, otherwise plain gold."""
    gold = copper / 10000
    if abs(gold) >= 1000:
        return f"{gold / 1000:.1f}kg"
    if abs(gold) >= 1:
        return f"{gold:,.0f}g"
    return f"{copper}c"


def format_gold_full(copper: int) -> str:
    """Readout label: 2,647g 00s 00c, the same split the tooltip uses."""
    sign = "-" if copper < 0 else ""
    copper = abs(copper)
    return f"{sign}{copper // 10000:,}g {copper // 100 % 100:02d}s {copper % 100:02d}c"
