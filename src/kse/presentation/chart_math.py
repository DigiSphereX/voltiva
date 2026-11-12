"""Pure-Python geometry/number helpers for the custom charts (no Qt imports).

Kept separate from ``charts.py`` so the maths is unit-testable headlessly and there is
a single source of truth for layout (painting and mouse hit-testing use the same
functions - the old chart hit-tested with a different left margin than it painted
with, so the hover highlight landed on the wrong bar).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

_NICE_STEPS = (1.0, 2.0, 2.5, 5.0, 10.0)


def nice_ticks(max_value: float, target: int = 4, integer: bool = False) -> tuple[list[float], float]:
    """Round axis ticks (0, 250, 500, ...) instead of ``max/3`` (3,584 / 2,389 / 1,195).

    Returns ``(ticks, axis_max)`` where ``axis_max`` is the last tick (>= max_value).
    """
    if not math.isfinite(max_value) or max_value <= 0:
        return [0.0, 1.0], 1.0
    raw = max_value / max(target, 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    residual = raw / magnitude
    step = next(n for n in _NICE_STEPS if residual <= n + 1e-12) * magnitude
    if integer:
        step = max(1.0, math.ceil(step))
    top = math.ceil(max_value / step - 1e-9) * step
    n = int(round(top / step))
    return [i * step for i in range(n + 1)], top


def compact_number(value: float) -> str:
    """1_250_000 -> '1.25M'; small numbers keep full precision."""
    sign = "-" if value < 0 else ""
    v = abs(value)
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= limit:
            text = f"{v / limit:.2f}".rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    if abs(v - round(v)) < 1e-9:
        return f"{sign}{v:,.0f}"
    return f"{sign}{v:,.2f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class Slot:
    """Horizontal slot of one category plus the bar drawn inside it."""

    index: int
    x: float          # slot left
    width: float      # slot width
    bar_x: float      # bar left
    bar_w: float      # bar width


def slot_layout(n: int, plot_left: float, plot_width: float, *, max_bar: float = 64.0,
                fill: float = 0.62, rtl: bool = False) -> list[Slot]:
    """Equal slots; bars are centred in them and capped at ``max_bar`` so two or three
    data points no longer turn into two giant blocks. ``rtl`` mirrors the time axis
    (oldest month on the right)."""
    if n <= 0 or plot_width <= 0:
        return []
    slot_w = plot_width / n
    bar_w = max(4.0, min(max_bar, slot_w * fill))
    out = []
    for i in range(n):
        pos = (n - 1 - i) if rtl else i
        x = plot_left + pos * slot_w
        out.append(Slot(i, x, slot_w, x + (slot_w - bar_w) / 2, bar_w))
    return out


def slot_at(slots: list[Slot], x: float) -> int | None:
    """Index of the slot containing ``x`` (whole slot is the hover target, not just the bar)."""
    for s in slots:
        if s.x <= x < s.x + s.width:
            return s.index
    return None


def label_step(slot_width: float, max_label_width: float, gap: float = 10.0) -> int:
    """Show every k-th x label so labels never overlap (replaces rotate+elide)."""
    if slot_width <= 0:
        return 1
    return max(1, math.ceil((max_label_width + gap) / slot_width))


def visible_label_indices(n: int, step: int) -> list[int]:
    """Every ``step``-th label counting back from the LAST point, so the newest is always shown."""
    if n <= 0:
        return []
    return sorted(range(n - 1, -1, -step))


def donut_spans(values: list[float], gap_deg: float = 2.0) -> list[tuple[float, float]]:
    """(start_deg, span_deg) per value, clockwise from 12 o'clock, with small gaps.

    Zero values get no arc; a single non-zero value gets the full ring (no gap)."""
    total = sum(v for v in values if v > 0)
    if total <= 0:
        return [(0.0, 0.0) for _ in values]
    nonzero = sum(1 for v in values if v > 0)
    gap = gap_deg if nonzero > 1 else 0.0
    out, angle = [], 0.0
    for v in values:
        if v <= 0:
            out.append((angle, 0.0))
            continue
        full = 360.0 * v / total
        out.append((angle + gap / 2, max(full - gap, 0.5)))
        angle += full
    return out
