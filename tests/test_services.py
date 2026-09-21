"""Application service orchestration tests."""
import datetime as dt
from decimal import Decimal

import pytest

from kse.application.services import CalculateInvoiceRequest, InvoiceService, SubscriberService, TariffService
from kse.domain.enums import DataSource, PaymentStatus, ServiceZone, SubscriberType
from kse.domain.errors import ValidationFailedError
from kse.domain.money import Money
from kse.infrastructure.sqlite.repositories import build_repositories
from kse.infrastructure.sqlite.seed import seed

from conftest import make_schedule


def make_context(mem_db):
    repos = build_repositories(mem_db)
    tariff_svc = TariffService(repos["tariffs"], repos["audit"], repos["uow"])
    invoice_svc = InvoiceService(repos["invoices"], repos["tariffs"], repos["subscribers"], repos["audit"], repos["uow"])
    sub_svc = SubscriberService(repos["subscribers"], repos["meters"], repos["tariffs"], repos["debts"], repos["uow"])
    seed(mem_db, overwrite=True)  # creates the reference flat schedule + sample subscriber
    return tariff_svc, invoice_svc, sub_svc, repos


class TestInvoiceService:
    def test_calculate_and_save(self, mem_db):
        _, svc, sub_svc, _ = make_context(mem_db)
        sub = sub_svc.find_or_create("1201234567", name="مشترك تجريبي")

        req = CalculateInvoiceRequest(
            subscriber_type=SubscriberType.RESIDENTIAL,
            previous_reading="13578",
            current_reading="17162",
            previous_read_date=dt.date(2024, 2, 1),
            current_read_date=dt.date(2024, 3, 15),
            official_amount=Money.of(35840),
        )
        calc, schedule = svc.calculate(req)
        assert calc.total_due == Money.of(35840)

        invoice = svc.save_calculation(calc, schedule, sub, official_amount=Money.of(35840))
        assert invoice.id is not None
        assert invoice.invoice_no.startswith(f"INV-{invoice.issue_date.year}-")
        # persisted + audited
        got = svc.invoices.get(invoice.id)
        assert got.total_due == Money.of(35840)
        audit = svc.audit.list_for_invoice(invoice.id)
        assert len(audit) == 1
        assert audit[0].action == "CALCULATE"

    def test_calculate_honors_service_zone(self, mem_db):
        """Scenario: smart-meter region tariff preferred over traditional when zone provided."""
        from kse.domain.models import TariffTier

        _, svc, _, repos = make_context(mem_db)
        # add a SMART_METER residential schedule alongside the seeded TRADITIONAL flat one
        smart = make_schedule(name="ذكي", method=repos["tariffs"].list_schedules()[0].method)
        smart.service_zone = ServiceZone.SMART_METER
        smart.name_en = "smart"
        smart.name_ar = "ذكي"
        repos["tariffs"].save_schedule(smart)
        mem_db.commit()

        req = CalculateInvoiceRequest(
            subscriber_type=SubscriberType.RESIDENTIAL,
            service_zone=ServiceZone.SMART_METER,
            previous_reading="13578",
            current_reading="14162",
            previous_read_date=dt.date(2026, 5, 1),
            current_read_date=dt.date(2026, 6, 1),
            official_amount=None,
        )
        calc, schedule = svc.calculate(req)
        assert schedule.service_zone == ServiceZone.SMART_METER
        assert calc.tariff_id == schedule.id

    def test_missing_tariff_raises_clear_error(self, mem_db):
        _, svc, _, _ = make_context(mem_db)
        # commercial has a sample too, use GOVERNMENTAL which has no schedule
        req = CalculateInvoiceRequest(
            subscriber_type=SubscriberType.GOVERNMENTAL,
            previous_reading="0",
            current_reading="100",
            previous_read_date=dt.date(2024, 1, 1),
            current_read_date=dt.date(2024, 2, 1),
        )
        from kse.domain.errors import NoTariffFoundError

        with pytest.raises(NoTariffFoundError):
            svc.calculate(req)

    def test_validation_blocks_bad_readings(self, mem_db):
        _, svc, _, _ = make_context(mem_db)
        req = CalculateInvoiceRequest(
            subscriber_type=SubscriberType.RESIDENTIAL,
            previous_reading="999",
            current_reading="100",
            previous_read_date=dt.date(2024, 1, 1),
            current_read_date=dt.date(2024, 2, 1),
        )
        with pytest.raises(ValidationFailedError):
            svc.calculate(req)

    def test_verify_returns_report(self, mem_db):
        _, svc, _, _ = make_context(mem_db)
        req = CalculateInvoiceRequest(
            subscriber_type=SubscriberType.RESIDENTIAL,
            previous_reading="13578",
            current_reading="17162",
            previous_read_date=dt.date(2024, 2, 1),
            current_read_date=dt.date(2024, 3, 15),
            official_amount=Money.of(35840),
        )
        vr = svc.verify(req)
        assert not vr.report.has_errors
        assert vr.calc.comparison.status.value == "MATCH"

    def test_recalculate_uses_current_tariff(self, mem_db):
        from kse.domain.models import TariffTier

        _, svc, sub_svc, repos = make_context(mem_db)
        sub = sub_svc.find_or_create("1201234567", name="مشترك")
        req = CalculateInvoiceRequest(
            subscriber_type=SubscriberType.RESIDENTIAL,
            previous_reading="13578",
            current_reading="17162",
            previous_read_date=dt.date(2024, 2, 1),
            current_read_date=dt.date(2024, 3, 15),
        )
        calc, sched = svc.calculate(req)
        inv = svc.save_calculation(calc, sched, sub)
        assert inv.total_due == Money.of(35840)

        # change the tariff rate → recalc must use the new rate
        sched.tiers[0].rate_per_kwh = Decimal("12")
        repos["tariffs"].save_schedule(sched)
        repos["uow"].commit()

        recalculated = svc.recalculate(inv.id)
        assert recalculated.total_due == Money.of(3584 * 12)


class TestTariffTierConventions:
    """Billing must be correct for both tier-boundary conventions:
    printed-invoice style (1-1500 then 1501-3000) and exclusive style
    (0-1500 then 1500-3000)."""

    def _schedule(self, tiers):
        from kse.domain.enums import TariffMethod
        from kse.domain.models import TariffTier

        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        s.tiers = [TariffTier(tier_no=i + 1, from_kwh=Decimal(f), to_kwh=Decimal(t),
                              rate_per_kwh=Decimal(r)) for i, (f, t, r) in enumerate(tiers)]
        return s

    def _cost(self, tiers, consumption):
        from kse.domain.services.tariff import TariffEngine

        return TariffEngine.compute(self._schedule(tiers), consumption).energy_cost

    USER_STYLE = [
        ("1", "1500", "10"),
        ("1501", "3000", "35"),
        ("3001", "4000", "80"),
        ("4001", "100000", "120"),
    ]

    def test_user_style_boundaries(self):
        cost = self._cost
        assert cost(self.USER_STYLE, 500) == Money.of(500 * 10)
        assert cost(self.USER_STYLE, 1500) == Money.of(1500 * 10)
        assert cost(self.USER_STYLE, 1501) == Money.of(1500 * 10 + 1 * 35)
        assert cost(self.USER_STYLE, 3000) == Money.of(1500 * 10 + 1500 * 35)
        assert cost(self.USER_STYLE, 4000) == Money.of(1500 * 10 + 1500 * 35 + 1000 * 80)
        assert cost(self.USER_STYLE, 100000) == Money.of(
            1500 * 10 + 1500 * 35 + 1000 * 80 + 96000 * 120)

    def test_exclusive_style_unchanged(self):
        exclusive = [("0", "1500", "10"), ("1500", "3000", "35"),
                     ("3000", "4000", "80"), ("4000", "100000", "120")]
        cost = self._cost
        assert cost(exclusive, 1500) == Money.of(1500 * 10)
        assert cost(exclusive, 1501) == Money.of(1500 * 10 + 1 * 35)
        assert cost(exclusive, 3000) == Money.of(1500 * 10 + 1500 * 35)
        assert cost(exclusive, 100000) == Money.of(
            1500 * 10 + 1500 * 35 + 1000 * 80 + 96000 * 120)

    def test_same_results_between_conventions(self):
        exclusive = [("0", "1500", "10"), ("1500", "3000", "35"),
                     ("3000", "4000", "80"), ("4000", "100000", "120")]
        for consumption in (1, 500, 1499, 1500, 1501, 2500, 2999, 3000, 3001, 4000, 4001, 99999):
            assert self._cost(self.USER_STYLE, consumption) == self._cost(exclusive, consumption)


class TestSubscriberService:
    def test_find_or_create(self, mem_db):
        _, _, svc, _ = make_context(mem_db)
        s1 = svc.find_or_create("1000", name="أول")
        s2 = svc.find_or_create("1000", name="ثاني")
        assert s1.id == s2.id  # identity preserved by account_no

    def test_delete_removes_subscriber(self, mem_db):
        _, _, svc, repos = make_context(mem_db)
        s = svc.find_or_create("2000", name="لحذف")
        assert svc.subscribers.get(s.id) is not None
        svc.delete(s.id)
        assert svc.subscribers.get(s.id) is None
        assert repos["subscribers"].by_account("2000") is None