"""TariffEngine tests — flat, progressive, boundaries, date resolution (spec §10, §21, §26)."""
import datetime as dt
from decimal import Decimal

import pytest

from kse.domain.enums import ServiceZone, SubscriberType, TariffMethod
from kse.domain.errors import NoTariffFoundError, TariffConflictError
from kse.domain.money import Money
from kse.domain.services.tariff import TariffEngine

from conftest import make_schedule, progressive_tiers


class TestFlat:
    def test_flat_rate(self):
        s = make_schedule(rate=Decimal("10"))
        b = TariffEngine.compute(s, 3584)
        assert b.energy_cost == Money.of(35840)
        assert len(b.rows) == 1
        assert b.rows[0].quantity == Decimal("3584")


class TestProgressive:
    def test_spec_example_3584(self):
        """1500×10 + 1500×15 + 584×20 = 15000+22500+11680 = 49180 (spec §10)."""
        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        b = TariffEngine.compute(s, 3584)
        assert b.energy_cost == Money.of(49180)
        qs = [r.quantity for r in b.rows]
        assert qs[0] == Decimal("1500")
        assert qs[1] == Decimal("1500")
        assert qs[2] == Decimal("584")

    def test_under_first_tier(self):
        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        b = TariffEngine.compute(s, 100)
        assert b.energy_cost == Money.of(1000)
        assert b.rows[1].quantity == Decimal("0")

    @pytest.mark.parametrize("consumption,expected", [
        (Decimal("999"), 9990),
        (Decimal("1000"), 10000),
        (Decimal("1001"), 10015),
        (Decimal("1499"), 17485),
        (Decimal("1500"), 17500),
        (Decimal("1501"), 17515),
        (Decimal("1999"), 24985),
        (Decimal("2000"), 25000),
        (Decimal("2001"), 25020),
        (Decimal("2999"), 44980),
        (Decimal("3000"), 45000),
        (Decimal("3001"), 45025),
        (Decimal("3999"), 69975),
        (Decimal("4000"), 70000),
        (Decimal("4001"), 70030),
    ])
    def test_tier_boundaries(self, consumption, expected):
        s = make_schedule(method=TariffMethod.PROGRESSIVE, tiers=progressive_tiers())
        b = TariffEngine.compute(s, consumption)
        assert b.energy_cost.raw == Decimal(expected)
        assert b.energy_cost == Money.of(expected)


class TestResolution:
    def test_resolve_by_date(self):
        s1 = make_schedule(name="Old", effective_from=dt.date(2023, 1, 1), effective_to=dt.date(2024, 1, 1))
        s2 = make_schedule(name="New", effective_from=dt.date(2024, 1, 1))
        resolved = TariffEngine.resolve([s1, s2], SubscriberType.RESIDENTIAL, dt.date(2024, 6, 1))
        assert resolved.name_ar == "New"
        assert TariffEngine.resolve([s1, s2], SubscriberType.RESIDENTIAL, dt.date(2023, 6, 1)).name_ar == "Old"

    def test_inactive_ignored(self):
        s = make_schedule(active=False)
        with pytest.raises(NoTariffFoundError):
            TariffEngine.resolve([s], SubscriberType.RESIDENTIAL, dt.date(2024, 6, 1))

    def test_no_tariff(self):
        with pytest.raises(NoTariffFoundError):
            TariffEngine.resolve([], SubscriberType.RESIDENTIAL, dt.date(2024, 6, 1))

    def test_conflict(self):
        s1 = make_schedule(name="A", effective_from=dt.date(2023, 1, 1))
        s2 = make_schedule(name="B", effective_from=dt.date(2024, 1, 1))
        with pytest.raises(TariffConflictError):
            TariffEngine.resolve([s1, s2], SubscriberType.RESIDENTIAL, dt.date(2024, 6, 1))

    def test_subscriber_type_separation(self):
        res = make_schedule(subscriber_type=SubscriberType.RESIDENTIAL)
        com = make_schedule(subscriber_type=SubscriberType.COMMERCIAL)
        got = TariffEngine.resolve([res, com], SubscriberType.COMMERCIAL, dt.date(2024, 6, 1))
        assert got.subscriber_type == SubscriberType.COMMERCIAL

    def test_resolve_before_from(self):
        s = make_schedule(effective_from=dt.date(2025, 1, 1))
        with pytest.raises(NoTariffFoundError):
            TariffEngine.resolve([s], SubscriberType.RESIDENTIAL, dt.date(2024, 6, 1))


class TestBillingPeriodDays:
    """Scenario: multi-month invoices stretch published slab limits (spec — real-world invoice)."""

    def test_default_scale_one_and_30_days(self):
        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        b = TariffEngine.compute(s, 1500)
        assert b.billing_days == 30
        assert b.scale == Decimal("1")

    def test_days_120_scales_thresholds_fourfold(self):
        """4-month bill: 1500→6000; 5600 kWh stays inside first slab → 5600×10 = 56000."""
        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        b = TariffEngine.compute(s, 5600, billing_days=120)
        assert b.scale == Decimal("4")
        assert b.rows[0].quantity == Decimal("5600")
        assert b.energy_cost == Money.of(56000)

    def test_days_60_crossing_scaled_boundary(self):
        """2-month bill: bounds 3000/6000/8000; 3100 → 3000×10 + 100×15 = 31500."""
        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        b = TariffEngine.compute(s, 3100, billing_days=60)
        assert b.scale == Decimal("2")
        assert b.energy_cost == Money.of(31500)

    def test_days_90_keeps_top_bound_intact(self):
        """3-month bill: 4000→12000; 11000 → 4500×10 + 4500×15 + 2000×20 = 152500."""
        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        b = TariffEngine.compute(s, 11000, billing_days=90)
        assert b.scale == Decimal("3")
        assert b.energy_cost == Money.of(152500)

    def test_flat_ignores_billing_days(self):
        s = make_schedule(rate=Decimal("10"))
        b = TariffEngine.compute(s, 5600, billing_days=120)
        assert b.energy_cost == Money.of(56000)

    def test_single_day_never_zero(self):
        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        b = TariffEngine.compute(s, 100, billing_days=1)
        assert b.scale == Decimal("1") / Decimal("30")
        assert b.energy_cost > Money.zero()


class TestServiceZone:
    """Scenario: smart-meter / investment (service-and-collection) regions price differently."""

    def test_zone_preference_among_siloed_schedules(self):
        from datetime import date
        trad = make_schedule(name="T", service_zone=ServiceZone.TRADITIONAL, effective_from=date(2024, 1, 1))
        smart = make_schedule(name="S", service_zone=ServiceZone.SMART_METER, effective_from=date(2024, 1, 1))
        got = TariffEngine.resolve([trad, smart], SubscriberType.RESIDENTIAL, date(2024, 6, 1),
                                   service_zone=ServiceZone.SMART_METER)
        assert got.name_ar == "S"
        got2 = TariffEngine.resolve([trad, smart], SubscriberType.RESIDENTIAL, date(2024, 6, 1),
                                    service_zone=ServiceZone.TRADITIONAL)
        assert got2.service_zone == ServiceZone.TRADITIONAL

    def test_zone_fallback_when_no_zone_match(self):
        from datetime import date
        s = make_schedule()  # TRADITIONAL default
        got = TariffEngine.resolve([s], SubscriberType.RESIDENTIAL, date(2024, 6, 1),
                                   service_zone=ServiceZone.INVESTMENT)
        assert got.service_zone == ServiceZone.TRADITIONAL

    def test_zone_compute_is_rate_agnostic(self):
        smart = make_schedule(name="S", method=TariffMethod.FLAT, rate=Decimal("35"),
                              service_zone=ServiceZone.SMART_METER)
        b = TariffEngine.compute(smart, 1000)
        assert b.energy_cost == Money.of(35000)