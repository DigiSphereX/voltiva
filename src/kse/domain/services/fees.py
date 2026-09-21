"""FeeCalculator — sums line-item charges on an invoice (spec §7).

Charges may come from:
- the tariff schedule's default fixed_fees
- explicit user-entered ad-hoc charges

Rules:
- No default fees are assumed unless present in the tariff or entered by the user.
- Discount amounts are positive and subtracted in the total.
- Only `in_current_amount` charges contribute to current_amount.
- Only `in_total_due` charges contribute to total_due.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..enums import ChargeCategory, DataSource
from ..models import InvoiceCharge
from ..money import Money


@dataclass
class FeeResult:
    charges: list[InvoiceCharge] = field(default_factory=list)
    fixed_fees_total: Money = field(default_factory=Money.zero)
    additional_fees_total: Money = field(default_factory=Money.zero)
    discounts_total: Money = field(default_factory=Money.zero)

    @property
    def sum_current_inclusion(self) -> Money:
        """Sum of charges that include in_current_amount."""
        total = Money.zero()
        for c in self.charges:
            if c.in_current_amount:
                total = total + _charge_value(c)
        return total

    @property
    def sum_total_inclusion(self) -> Money:
        """Sum of charges that include in_total_due (might differ from current)."""
        total = Money.zero()
        for c in self.charges:
            if c.in_total_due:
                total = total + _charge_value(c)
        return total

    @property
    def sum_total_only(self) -> Money:
        """Charges included in total_due but NOT already inside current_amount."""
        total = Money.zero()
        for c in self.charges:
            if c.in_total_due and not c.in_current_amount:
                total = total + _charge_value(c)
        return total


def _charge_value(c: InvoiceCharge) -> Money:
    if c.category == ChargeCategory.DISCOUNT:
        return -c.amount
    return c.amount


class FeeCalculator:
    @staticmethod
    def compute(charges: list[InvoiceCharge]) -> FeeResult:
        fixed = Money.zero()
        additional = Money.zero()
        discount = Money.zero()
        all_charges: list[InvoiceCharge] = []

        for c in charges:
            all_charges.append(c)
            val = _charge_value(c)
            if c.category == ChargeCategory.DISCOUNT:
                discount = discount + c.amount
            elif c.category in (ChargeCategory.FIXED_FEE, ChargeCategory.PENALTY):
                fixed = fixed + val
            else:
                additional = additional + val

        return FeeResult(
            charges=all_charges,
            fixed_fees_total=fixed,
            additional_fees_total=additional,
            discounts_total=discount,
        )