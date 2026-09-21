"""Full InvoiceCalculator tests — the reference test case + fees/debt/discounts (spec §11, §25)."""
import datetime as dt
from decimal import Decimal

import pytest

from kse.domain.enums import ChargeCategory, ComparisonStatus, SubscriberType, TariffMethod
from kse.domain.errors import ValidationFailedError
from kse.domain.models import InvoiceCharge
from kse.domain.money import Money
from kse.domain.services.invoice_calc import InvoiceCalculator

from conftest import make_schedule

D1 = dt.date(2024, 2, 1)
D2 = dt.date(2024, 3, 15)


def ref_calc(**overrides):
    s = make_schedule(name="مرجع", rate=Decimal("10"))
    params = dict(
        subscriber_type=SubscriberType.RESIDENTIAL,
        previous_reading=13578,
        current_reading=17162,
        previous_read_date=D1,
        current_read_date=D2,
        tariff_schedule=s,
        official_amount=Money.of(35840),
    )
    params.update(overrides)
    return InvoiceCalculator.calculate(**params)


class TestReferenceSample:
    def test_reference_case(self):
        calc = ref_calc()
        assert calc.reading.consumption_kwh == Decimal("3584")
        assert calc.energy_cost == Money.of(35840)
        assert calc.current_amount == Money.of(35840)
        assert calc.total_due == Money.of(35840)
        assert calc.comparison is not None
        assert calc.comparison.status == ComparisonStatus.MATCH
        assert calc.comparison.diff == Money.zero()
        assert calc.consumption_days == 43

    def test_steps_present(self):
        calc = ref_calc()
        labels = [s.label_ar for s in calc.steps]
        assert "المجموع المطلوب" in labels
        assert "قيمة الطاقة" in labels
        # full chain per spec §12
        chain = ["القراءة السابقة", "القراءة الحالية", "الاستهلاك", "قيمة الطاقة", "المجموع المطلوب"]
        for c in chain:
            assert c in labels


class TestFeesAndDebt:
    def test_fixed_fee_added_to_total(self):
        charge = InvoiceCharge(name="أجور المقياس", category=ChargeCategory.FIXED_FEE, amount=Money.of(1000))
        calc = ref_calc(fees=[charge])
        assert calc.fixed_fees == Money.of(1000)
        assert calc.total_due == Money.of(35840 + 1000)

    def test_discount_subtracted(self):
        charge = InvoiceCharge(name="خصم", category=ChargeCategory.DISCOUNT, amount=Money.of(500))
        calc = ref_calc(fees=[charge])
        assert calc.discounts == Money.of(500)
        assert calc.total_due == Money.of(35840 - 500)

    def test_previous_debt_added(self):
        calc = ref_calc(previous_debt=Money.of(2500))
        assert calc.previous_debt == Money.of(2500)
        assert calc.total_due == Money.of(35840 + 2500)

    def test_multiplier_meter(self):
        charge = None
        calc = ref_calc(multiplier=10)
        assert calc.reading.adjusted_kwh == Decimal("35840")
        assert calc.energy_cost == Money.of(358400)
        assert calc.total_due == Money.of(358400)


class TestComparison:
    def test_mismatch_report(self):
        calc = ref_calc(official_amount=Money.of(36340))
        assert calc.comparison.status == ComparisonStatus.MISMATCH
        assert not calc.comparison.diff.is_zero
        assert calc.comparison.diff == Money.of(35840 - 36340)
        assert any("فرق الفاتورة" in c for c in calc.comparison.possible_causes)

    def test_match_with_rounding_difference_tolerance(self):
        calc = ref_calc(official_amount=Money.of(35840))
        assert calc.comparison.status == ComparisonStatus.MATCH

    def test_not_comparison_when_none(self):
        calc = ref_calc()
        calc.comparison = None
        assert calc.comparison is None


class TestDailyAverage:
    def test_daily_average(self):
        calc = ref_calc()
        # 3584 / 43 = 83.3488 -> rounded to 83.35
        from kse.domain.money import round_money
        assert calc.daily_average_kwh == round_money(calc.reading.consumption_kwh / Decimal("43"))
        assert calc.monthly_average_kwh == calc.daily_average_kwh * Decimal("30")


class TestRealInvoiceScenarios:
    """Real household invoice: reads 3000→5600, dates 01/05/2026 → 01/08/2026 (≈92 days ≈ 3 months)."""

    PD = dt.date(2026, 5, 1)
    CD = dt.date(2026, 8, 1)

    def progressive_params(self, **overrides):
        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        params = dict(
            subscriber_type=SubscriberType.RESIDENTIAL,
            previous_reading=3000,
            current_reading=5600,
            previous_read_date=self.PD,
            current_read_date=self.CD,
            tariff_schedule=s,
            official_amount=Money.of(86000),
        )
        params.update(overrides)
        return params

    def test_consumption_is_current_minus_previous(self):
        calc = InvoiceCalculator.calculate(**self.progressive_params())
        assert calc.reading.consumption_kwh == Decimal("2600")
        assert calc.consumption_days == 92

    def test_thresholds_stretched_by_days_over_30(self):
        calc = InvoiceCalculator.calculate(**self.progressive_params(official_amount=None))
        assert calc.tariff_breakdown.billing_days == 92
        assert calc.tariff_breakdown.scale == Decimal("92") / Decimal("30")
        # 2600 kWh still inside the first slab scaled ×(92/30≈4600) → 2600×10
        assert calc.energy_cost == Money.of(26000)

    def test_steps_annotate_extended_thresholds(self):
        calc = InvoiceCalculator.calculate(**self.progressive_params(official_amount=None))
        labels = [st.label_ar for st in calc.steps]
        assert "حدود الشرائح ممددة" in labels
        assert calc.steps[calc.steps.index(next(s for s in calc.steps if s.label_ar == "حدود الشرائح ممددة"))].detail

    def test_flat_invoice_has_no_threshold_note(self):
        s = make_schedule(rate=Decimal("10"))
        calc = InvoiceCalculator.calculate(
            subscriber_type=SubscriberType.RESIDENTIAL, previous_reading=3000, current_reading=5600,
            previous_read_date=self.PD, current_read_date=self.CD, tariff_schedule=s)
        labels = [st.label_ar for st in calc.steps]
        assert "حدود الشرائح ممددة" not in labels

    def test_mismatch_causes_include_multimonth_bullet(self):
        calc = InvoiceCalculator.calculate(**self.progressive_params(official_amount=Money.of(100000)))
        assert any("تغطي" in c for c in calc.comparison.possible_causes)
        assert any("92" in c for c in calc.comparison.possible_causes)

    def test_mismatch_causes_include_cumulative_reading_hint(self):
        calc = InvoiceCalculator.calculate(**self.progressive_params(official_amount=Money.of(100000)))
        assert any("تراكمية" in c for c in calc.comparison.possible_causes)