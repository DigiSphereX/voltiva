"""InvoiceCalculator — orchestrates tariff + fees + debt and produces the full
calculation detail (spec §8, §12, §14, §39).

The result contains step-by-step lines so the UI can always answer:
"كيف وصلت إلى هذا الرقم؟" (How did you arrive at this number?)
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional

from ..enums import ChargeCategory, ComparisonStatus, DataSource, SubscriberType, TariffMethod
from ..models import Invoice, InvoiceCharge, InvoiceReading, TariffSchedule, TariffTier
from ..money import CURRENCY_AR, Money, fmt_quantity, round_money
from .consumption import ConsumptionCalculator, ConsumptionResult
from .fees import FeeCalculator, FeeResult
from .tariff import TariffBreakdown, TariffBreakdownRow, TariffEngine, build_invoice_charges_from_tariff
from .debt import DebtCalculator

TrFn = Callable[..., str]

# Arabic fallback messages so domain-level callers (and tests) keep working without an i18n engine.
_CMP_AR = {
    "cmp_diff": "فرق الفاتورة: {amount}",
    "cmp_hint": "السبب المحتمل:",
    "cmp_months": "  • الفاتورة تغطي {days} يوماً ({months} أشهر تقريباً): حدود الشرائح ممددة ×{scale} ونسبة الرسوم قد تكون كاملة لكل الشهر",
    "cmp_debt": "  • الدين السابق: {amount}",
    "cmp_fees": "  • رسوم إضافية بقيمة {amount}",
    "cmp_discount": "  • خصم بقيمة {amount}",
    "cmp_multiplier": "  • معامل العداد: {value}",
    "cmp_cumulative": "  • القراءة قد تكون تراكمية (فرق القراءتين) وليست الاستهلاك الشهري",
    "cmp_estimated": "  • التعرفة المستخدمة تقديرية وقد تختلف عن الرسمية",
    "cmp_rounding": "  • الفرق ضئيل وقد يكون بسبب التقريب",
}


def _ar_tr(key: str, **kwargs) -> str:
    text = _CMP_AR.get(key, key)
    return text.format(**kwargs) if kwargs else text


def _money_ar(m: Money) -> str:
    """Amount label consistent with the running UI style (Arabic-Indic + د.ع vs ISO code).

    Domain callers default to the Arabic style; when called through the UI the
    presentation layer picks the style via widgets.is_arabic_money().
    """
    from ...presentation.widgets import is_arabic_money  # noqa: PLC0415

    if is_arabic_money():
        return m.display_ar()
    from ...presentation.currencies import get_currency_code  # noqa: PLC0415

    return f"{m.display()} {get_currency_code()}"


@dataclass
class CalculationStep:
    label_ar: str
    value_display: str
    raw_value: str = ""
    is_subtotal: bool = False
    is_divider: bool = False
    detail: str = ""
    is_header: bool = False


@dataclass
class InvoiceComparison:
    official_amount: Money = field(default_factory=Money.zero)
    calculated_amount: Money = field(default_factory=Money.zero)
    diff: Money = field(default_factory=Money.zero)
    ratio_pct: float = 0.0
    status: ComparisonStatus = ComparisonStatus.NOT_COMPARED
    possible_causes: list[str] = field(default_factory=list)


@dataclass
class InvoiceCalculation:
    subscriber_type: SubscriberType = SubscriberType.RESIDENTIAL
    reading: ConsumptionResult | None = None
    tariff_breakdown: TariffBreakdown | None = None
    fee_result: FeeResult | None = None
    energy_cost: Money = field(default_factory=Money.zero)
    fixed_fees: Money = field(default_factory=Money.zero)
    additional_fees: Money = field(default_factory=Money.zero)
    discounts: Money = field(default_factory=Money.zero)
    previous_debt: Money = field(default_factory=Money.zero)
    current_amount: Money = field(default_factory=Money.zero)
    total_due: Money = field(default_factory=Money.zero)
    steps: list[CalculationStep] = field(default_factory=list)
    comparison: InvoiceComparison | None = None
    tariff_id: int | None = None
    tariff_version: str = ""
    tariff_source: DataSource = DataSource.UNKNOWN
    consumption_days: int | None = None
    daily_average_kwh: Decimal = Decimal("0")
    monthly_average_kwh: Decimal = Decimal("0")


class InvoiceCalculator:
    @staticmethod
    def calculate(
        *,
        subscriber_type: SubscriberType,
        previous_reading,
        current_reading,
        previous_read_date: dt.date,
        current_read_date: dt.date,
        tariff_schedule: TariffSchedule,
        fees: list[InvoiceCharge] | None = None,
        previous_debt: Money | None = None,
        multiplier: Decimal | int = 1,
        scenario=None,
        max_reading: Decimal | int | None = None,
        replacement_base: Decimal | int | None = None,
        official_amount: Money | None = None,
        tr: Optional[TrFn] = None,
    ) -> InvoiceCalculation:
        from ..enums import MeterScenario
        from ..errors import ReadingInvalidError, VerificationNeededError

        scenario = scenario or MeterScenario.NORMAL

        # --- 1. Consumption ---
        reading = ConsumptionCalculator.calculate(
            previous_reading=previous_reading,
            current_reading=current_reading,
            multiplier=multiplier,
            scenario=scenario,
            max_reading=max_reading,
            replacement_base=replacement_base,
        )

        consumption = reading.adjusted_kwh

        # Billing-period length (official tiers are stated per 30 days; a
        # multi-month invoice stretches the tier limits by days/30).
        days = (current_read_date - previous_read_date).days
        safe_days = max(days, 1)

        # --- 2. Tariff energy cost ---
        tariff = TariffEngine.compute(tariff_schedule, consumption, billing_days=safe_days)

        # --- 3. Fees ---
        all_fees = list(fees or [])
        tariff_fees = build_invoice_charges_from_tariff(tariff_schedule)
        # Deduplicate tariff fees vs explicit by tariff_fee_id
        explicit_ids = {f.tariff_fee_id for f in all_fees if f.tariff_fee_id is not None}
        for tf in tariff_fees:
            if tf.tariff_fee_id not in explicit_ids:
                all_fees.insert(0, tf)

        fee_result = FeeCalculator.compute(all_fees)

        # --- 4. Debt ---
        debt_total = DebtCalculator.resolve_previous_debt(previous_debt or Money.zero())

        # --- 5. Totals ---
        # current_amount = energy + charges flagged for the current period
        # total_due = current_amount + debt + charges flagged ONLY for total
        #   (charges flagged for both are already inside current_amount)
        energy = tariff.energy_cost
        current = energy + fee_result.sum_current_inclusion
        total = current + debt_total + fee_result.sum_total_only

        # --- 6. Time stats ---
        daily_avg = round_money(consumption / Decimal(safe_days))
        monthly_avg = round_money(daily_avg * Decimal("30"))

        # --- 7. Steps ---
        steps = _build_steps(reading, tariff, fee_result, debt_total, energy, current, total, days)

        calc = InvoiceCalculation(
            subscriber_type=subscriber_type,
            reading=reading,
            tariff_breakdown=tariff,
            fee_result=fee_result,
            energy_cost=energy,
            fixed_fees=fee_result.fixed_fees_total,
            additional_fees=fee_result.additional_fees_total,
            discounts=fee_result.discounts_total,
            previous_debt=debt_total,
            current_amount=current,
            total_due=total,
            steps=steps,
            tariff_id=tariff_schedule.id,
            tariff_version=tariff_schedule.version,
            tariff_source=tariff_schedule.source,
            consumption_days=days,
            daily_average_kwh=daily_avg,
            monthly_average_kwh=monthly_avg,
        )

        # --- 8. Official comparison ---
        if official_amount is not None:
            calc.comparison = _compare(total, official_amount, reading, tariff, fee_result, debt_total, days, tr)

        return calc


def _build_steps(
    reading: ConsumptionResult,
    tariff: TariffBreakdown,
    fee_result: FeeResult,
    debt_total: Money,
    energy: Money,
    current: Money,
    total: Money,
    days: int,
) -> list[CalculationStep]:
    from ..enums import MeterScenario

    steps: list[CalculationStep] = []

    steps.append(CalculationStep(
        label_ar="القراءة السابقة",
        value_display=f"{fmt_quantity(reading.previous_reading)} kWh",
        raw_value=str(reading.previous_reading),
    ))
    steps.append(CalculationStep(
        label_ar="القراءة الحالية",
        value_display=f"{fmt_quantity(reading.current_reading)} kWh",
        raw_value=str(reading.current_reading),
    ))
    if reading.scenario != MeterScenario.NORMAL:
        steps.append(CalculationStep(
            label_ar="الحالة",
            value_display=reading.scenario.label_ar,
        ))
    steps.append(CalculationStep(
        label_ar="الاستهلاك",
        value_display=f"{fmt_quantity(reading.consumption_kwh)} kWh",
        raw_value=str(reading.consumption_kwh),
    ))

    if reading.multiplier != Decimal("1"):
        steps.append(CalculationStep(
            label_ar="معامل العداد",
            value_display=str(reading.multiplier),
            raw_value=str(reading.multiplier),
        ))
        steps.append(CalculationStep(
            label_ar="الاستهلاك المعدل",
            value_display=f"{fmt_quantity(reading.adjusted_kwh)} kWh",
            raw_value=str(reading.adjusted_kwh),
        ))

    steps.append(CalculationStep(
        label_ar="المدة الزمنية",
        value_display=f"{days} يوماً",
    ))

    steps.append(CalculationStep(is_divider=True, label_ar="", value_display=""))

    steps.append(CalculationStep(
        label_ar="جدول التعرفة",
        value_display=tariff.schedule.name_ar if tariff.schedule else "—",
        detail=f"المصدر: {tariff.schedule.source.label_ar if tariff.schedule else '—'} | النسخة: {tariff.schedule.version if tariff.schedule else '—'}",
    ))

    # Tier details
    if tariff.method == TariffMethod.FLAT and tariff.rows:
        r = tariff.rows[0]
        steps.append(CalculationStep(
            label_ar="سعر الطاقة",
            value_display=f"{Money(r.rate).display()} {CURRENCY_AR}/kWh",
            raw_value=str(r.rate),
        ))
    else:
        if tariff.scale != Decimal("1"):
            scale_txt = f"{tariff.scale:.2f}".rstrip("0").rstrip(".")
            steps.append(CalculationStep(
                label_ar="حدود الشرائح ممددة",
                value_display=f"×{scale_txt} (الفاتورة تغطي {days} يوماً والافتراضي 30)",
                detail="الشرائح منشورة لكل 30 يوماً؛ تُضرب حدودها بنسبة أيام الدورة / 30",
            ))
        for r in tariff.rows:
            if r.quantity > 0:
                steps.append(CalculationStep(
                    label_ar=f"الشريحة {r.tier_no}",
                    value_display=f"{fmt_quantity(r.quantity)} kWh × {Money(r.rate).display()} = {Money(r.amount).display()} {CURRENCY_AR}",
                ))

    steps.append(CalculationStep(is_divider=True, label_ar="", value_display=""))

    steps.append(CalculationStep(
        label_ar="قيمة الطاقة",
        value_display=f"{energy.display()} {CURRENCY_AR}",
        raw_value=str(energy.raw),
        is_subtotal=True,
    ))

    for c in fee_result.charges:
        val = c.amount.display()
        sign = "-" if c.category == ChargeCategory.DISCOUNT else "+"
        if c.in_current_amount:
            steps.append(CalculationStep(
                label_ar=f"{sign} {c.name}",
                value_display=f"{val} {CURRENCY_AR}",
                raw_value=str(c.amount.raw),
            ))

    if debt_total > Money.zero():
        steps.append(CalculationStep(
            label_ar="+ الدين السابق",
            value_display=f"{debt_total.display()} {CURRENCY_AR}",
            raw_value=str(debt_total.raw),
        ))

    steps.append(CalculationStep(is_divider=True, label_ar="", value_display=""))

    steps.append(CalculationStep(
        label_ar="المجموع المطلوب",
        value_display=f"{total.display()} {CURRENCY_AR}",
        raw_value=str(total.raw),
        is_subtotal=True,
        is_header=True,
    ))

    return steps


def _compare(
    calculated: Money,
    official: Money,
    reading: ConsumptionResult,
    tariff: TariffBreakdown,
    fee_result: FeeResult,
    debt_total: Money,
    days: int,
    tr: Optional[TrFn] = None,
) -> InvoiceComparison:
    tr = tr or _ar_tr
    diff = calculated - official
    diff_abs = Money(abs(diff.raw))
    ratio = (diff_abs.raw / official.raw * 100) if official.raw != 0 else Decimal("0")
    status = ComparisonStatus.MATCH if diff.is_zero else ComparisonStatus.MISMATCH

    causes: list[str] = []
    if not diff.is_zero:
        causes.append(tr("cmp_diff", amount=_money_ar(diff_abs)))
        causes.append(tr("cmp_hint"))

        # Heuristic cause analysis
        fee_total_used = fee_result.fixed_fees_total + fee_result.additional_fees_total
        if days > 30:
            months = (Decimal(days) / Decimal("30")).quantize(Decimal("1"))
            causes.append(tr("cmp_months", days=days, months=months,
                             scale=f"{tariff.scale:.2f}"))
        if debt_total > Money.zero():
            causes.append(tr("cmp_debt", amount=_money_ar(debt_total)))
        if fee_total_used > Money.zero():
            causes.append(tr("cmp_fees", amount=_money_ar(fee_total_used)))
        if fee_result.discounts_total > Money.zero():
            causes.append(tr("cmp_discount", amount=_money_ar(fee_result.discounts_total)))
        if reading.multiplier != Decimal("1"):
            causes.append(tr("cmp_multiplier", value=reading.multiplier))
        if tariff.scale != Decimal("1") and tariff.method != TariffMethod.FLAT:
            causes.append(tr("cmp_cumulative"))

        # When tariff unknown, note possible tariff mismatch
        if tariff.schedule and tariff.schedule.source == DataSource.ESTIMATED:
            causes.append(tr("cmp_estimated"))

        if abs(diff.raw) <= Decimal("10"):
            causes.append(tr("cmp_rounding"))

    return InvoiceComparison(
        official_amount=official,
        calculated_amount=calculated,
        diff=diff,
        ratio_pct=float(ratio),
        status=status,
        possible_causes=causes,
    )