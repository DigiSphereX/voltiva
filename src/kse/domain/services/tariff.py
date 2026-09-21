"""TariffEngine — resolves the effective tariff for a subscriber type + date,
and computes flat or progressive energy costs (spec §10, §20, §21).

No tariff value is hard-coded; this engine is purely data-driven.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from ..enums import ComparisonStatus, TariffMethod
from ..errors import NoTariffFoundError, TariffConflictError
from ..models import Invoice, InvoiceCharge, TariffFee, TariffSchedule, TariffTier
from ..money import CURRENCY_AR, Money, round_money


@dataclass
class TariffBreakdownRow:
    tier_no: int
    label: str
    from_kwh: Decimal
    to_kwh: Decimal | None
    rate: Decimal
    quantity: Decimal
    amount: Money

    def display_range(self) -> str:
        from ..money import fmt_quantity

        top = "∞" if self.to_kwh is None else fmt_quantity(self.to_kwh)
        return f"{fmt_quantity(self.from_kwh)} - {top}"


@dataclass
class TariffBreakdown:
    method: TariffMethod = TariffMethod.FLAT
    schedule: TariffSchedule | None = None
    rows: list[TariffBreakdownRow] = field(default_factory=list)
    energy_cost: Money = field(default_factory=Money.zero)
    rate_display: str = ""
    billing_days: int = 30
    scale: Decimal = Decimal("1")

    def flat_rate(self) -> str:
        if self.rows:
            r = self.rows[0]
            if self.method == TariffMethod.FLAT:
                return f"{Money(r.rate).display()} {CURRENCY_AR}"
        return ""


class TariffEngine:
    """Stateless, data-driven tariff resolution & computation."""

    @staticmethod
    def resolve(
        schedules: list[TariffSchedule],
        subscriber_type,
        effective_date: dt.date,
        service_zone=None,
    ) -> TariffSchedule:
        """Return the single effective schedule for `subscriber_type` on `effective_date`.

        When more than one schedule covers the type/date (smart-meter or investment
        areas next to the classic grid), a `service_zone` narrows the choice;
        otherwise the broadest scope wins.

        Raises:
            NoTariffFoundError : no matching schedule
            TariffConflictError: more than one active schedule matches
        """
        from ..enums import ServiceZone, SubscriberType

        sub = subscriber_type if isinstance(subscriber_type, SubscriberType) else SubscriberType(subscriber_type)
        candidates = [s for s in schedules if _matches(s, sub, effective_date)]

        if service_zone is not None:
            zone = service_zone if isinstance(service_zone, ServiceZone) else ServiceZone(service_zone)
            zoned = [s for s in candidates if s.service_zone == zone]
            if zoned:
                candidates = zoned

        if len(candidates) == 0:
            raise NoTariffFoundError(sub.label_ar, effective_date)
        if len(candidates) > 1:
            raise TariffConflictError([c.name_ar for c in candidates])
        return candidates[0]

    @staticmethod
    def compute(schedule: TariffSchedule, consumption_kwh, billing_days: int = 30) -> TariffBreakdown:
        consumption = Decimal(str(consumption_kwh))
        safe_days = max(int(billing_days), 1)
        scale = Decimal(safe_days) / Decimal("30")

        if schedule.method == TariffMethod.FLAT:
            rate = schedule.tiers[0].rate_per_kwh if schedule.tiers else Decimal("0")
            amount = Money.of(consumption) * rate
            row = TariffBreakdownRow(
                tier_no=1,
                label="تعرفة ثابتة",
                from_kwh=Decimal("0"),
                to_kwh=None,
                rate=rate,
                quantity=consumption,
                amount=amount,
            )
            return TariffBreakdown(
                method=schedule.method,
                schedule=schedule,
                rows=[row],
                energy_cost=amount,
                rate_display=f"{Money(rate).display()} {CURRENCY_AR}/kWh",
                billing_days=safe_days,
                scale=scale,
            )

        # --- Progressive / Tiered ---
        rows: list[TariffBreakdownRow] = []
        remaining = consumption
        total = Money.zero()

        tiers_sorted = sorted(schedule.tiers, key=lambda t: t.from_kwh)

        # Normalize tier bounds: accept both the printed-invoice convention
        # (1-1500 then 1501-3000) and the exclusive convention (0-1500 then 1500-3000).
        prev_to: Decimal | None = None
        for idx, tier in enumerate(tiers_sorted):
            from_eff = tier.from_kwh
            if idx == 0 and from_eff == Decimal("1"):
                from_eff = Decimal("0")
            elif idx > 0 and prev_to is not None and from_eff == prev_to + 1:
                from_eff = prev_to

            # Billing-period scaling: the official tier limits are stated per 30
            # days; a 3-4 month invoice multiplies every threshold by days/30.
            from_eff = from_eff * scale
            upper = tier.to_kwh
            to_eff = (upper * scale) if upper is not None else None

            if remaining <= 0:
                qty = Decimal("0")
            else:
                if consumption <= from_eff:
                    qty = Decimal("0")
                elif to_eff is None or consumption <= to_eff:
                    qty = consumption - from_eff
                else:
                    qty = to_eff - from_eff

            amount = round_money(qty * tier.rate_per_kwh)
            total = total + amount
            rows.append(TariffBreakdownRow(
                tier_no=tier.tier_no,
                label=tier.label(),
                from_kwh=tier.from_kwh,
                to_kwh=tier.to_kwh,
                rate=tier.rate_per_kwh,
                quantity=qty,
                amount=amount,
            ))
            prev_to = tier.to_kwh

        first_rate = schedule.tiers[0].rate_per_kwh if schedule.tiers else Decimal("0")
        return TariffBreakdown(
            method=schedule.method,
            schedule=schedule,
            rows=rows,
            energy_cost=total,
            rate_display=f"من {Money(first_rate).display()} {CURRENCY_AR}/kWh (شرائح متدرجة)",
            billing_days=safe_days,
            scale=scale,
        )


def _matches(s: TariffSchedule, sub_type, d: dt.date) -> bool:
    from ..enums import SubscriberType

    st = sub_type if isinstance(sub_type, SubscriberType) else SubscriberType(sub_type)
    if not s.is_active:
        return False
    if s.subscriber_type != st:
        return False
    if s.effective_from > d:
        return False
    if s.effective_to is not None and d >= s.effective_to:
        return False
    return True


def build_invoice_charges_from_tariff(tariff_schedule: TariffSchedule) -> list[InvoiceCharge]:
    """Convert the schedule's default `fixed_fees` list into `InvoiceCharge` objects."""
    charges: list[InvoiceCharge] = []
    for fee in tariff_schedule.fixed_fees:
        charges.append(InvoiceCharge(
            name=fee.name_ar or fee.name_en,
            name_en=fee.name_en,
            category=fee.category,
            amount=fee.amount,
            reason=fee.reason,
            is_fixed=fee.is_fixed,
            depends_on_consumption=fee.depends_on_consumption,
            taxable=fee.taxable,
            in_current_amount=fee.in_current_amount,
            in_total_due=fee.in_total_due,
            source=tariff_schedule.source,
            tariff_fee_id=fee.id,
        ))
    return charges