"""DebtCalculator — resolves total previous debt from subscriber records (spec §7)."""
from __future__ import annotations

from ..money import Money


class DebtCalculator:
    @staticmethod
    def resolve_previous_debt(subscriber_debt: Money) -> Money:
        if subscriber_debt is None:
            return Money.zero()
        return Money.of(subscriber_debt)