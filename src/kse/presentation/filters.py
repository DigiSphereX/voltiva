"""Qt-free helpers for list filters (unit-testable)."""
from __future__ import annotations

import datetime as dt


def month_bounds(key: str | None) -> tuple[dt.date | None, dt.date | None]:
    """'YYYY-MM' -> (first day, last day) of that month; (None, None) for empty/invalid input."""
    if not key:
        return None, None
    try:
        year_s, month_s = key.split("-")
        year, month = int(year_s), int(month_s)
        first = dt.date(year, month, 1)
    except (ValueError, TypeError):
        return None, None
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt - dt.timedelta(days=1)
