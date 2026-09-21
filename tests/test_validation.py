"""ValidationEngine tests (spec §36)."""
import datetime as dt
from decimal import Decimal

from kse.domain.enums import MeterScenario
from kse.domain.money import Money
from kse.domain.services.validation import ValidationEngine


class TestReadings:
    def test_valid(self):
        r = ValidationEngine.validate_readings(previous="1000", current="1100", scenario=MeterScenario.NORMAL)
        assert not r.has_errors

    def test_decrease_error_when_normal(self):
        r = ValidationEngine.validate_readings(previous="1100", current="1000", scenario=MeterScenario.NORMAL)
        assert r.has_errors

    def test_decrease_allowed_when_replacement(self):
        r = ValidationEngine.validate_readings(previous="9500", current="200", scenario=MeterScenario.REPLACEMENT)
        assert not r.has_errors

    def test_non_numeric(self):
        r = ValidationEngine.validate_readings(previous="abc", current="100", scenario=MeterScenario.NORMAL)
        assert any(i.code == "READING_INVALID" for i in r.issues)

    def test_negative(self):
        r = ValidationEngine.validate_readings(previous="-1", current="100", scenario=MeterScenario.NORMAL)
        assert any(i.code == "READING_NEGATIVE" for i in r.issues)


class TestDates:
    def test_ordering(self):
        r = ValidationEngine.validate_dates(
            previous_date=dt.date(2024, 3, 1), current_date=dt.date(2024, 2, 1), issue_date=None)
        assert any(i.code == "DATE_ORDER" for i in r.issues)

    def test_missing(self):
        r = ValidationEngine.validate_dates(previous_date=None, current_date=None, issue_date=None)
        assert any(i.code == "DATE_MISSING" for i in r.issues)


class TestAccounts:
    def test_valid_account(self):
        r = ValidationEngine.validate_account_numbers("1201234567")
        assert not r.has_errors

    def test_bad_account(self):
        r = ValidationEngine.validate_account_numbers("abc")
        assert any(i.code == "ACCOUNT_FORMAT" for i in r.issues)

    def test_missing_account(self):
        r = ValidationEngine.validate_account_numbers("")
        assert any(i.code == "ACCOUNT_MISSING" for i in r.issues)


class TestFees:
    def test_negative_non_discount_rejected(self):
        from kse.domain.enums import ChargeCategory
        from kse.domain.models import InvoiceCharge

        c = InvoiceCharge(name="bad", category=ChargeCategory.FIXED_FEE, amount=Money.of("-5"))
        r = ValidationEngine.validate_fees([c])
        assert any(i.code == "NEGATIVE_FEE" for i in r.errors)

    def test_discount_positive_ok(self):
        from kse.domain.enums import ChargeCategory
        from kse.domain.models import InvoiceCharge

        c = InvoiceCharge(name="discount", category=ChargeCategory.DISCOUNT, amount=Money.of("5"))
        r = ValidationEngine.validate_fees([c])
        assert not r.has_errors


class TestTariff:
    def test_missing_tiers(self):
        from kse.domain.enums import SubscriberType, TariffMethod
        from kse.domain.models import TariffSchedule

        s = TariffSchedule(name_ar="x", subscriber_type=SubscriberType.RESIDENTIAL,
                           method=TariffMethod.FLAT, effective_from=dt.date(2024, 1, 1),
                           tiers=[])
        r = ValidationEngine.validate_tariff(s)
        assert any(i.code == "TARIFF_NO_TIERS" for i in r.errors)

    def test_overlapping_tiers(self):
        from kse.domain.enums import TariffMethod
        from kse.domain.models import TariffTier
        from conftest import make_schedule

        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        # add a duplicate-overlap tier
        s.tiers.append(TariffTier(tier_no=9, from_kwh=Decimal("100"), to_kwh=Decimal("2000"), rate_per_kwh=Decimal("1")))
        r = ValidationEngine.validate_tariff(s)
        assert any(i.code == "TARIFF_OVERLAP" for i in r.errors)

    def test_gappy_tiers_rejected(self):
        from kse.domain.enums import TariffMethod
        from kse.domain.models import TariffTier
        from conftest import make_schedule

        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        s.tiers.append(TariffTier(tier_no=9, from_kwh=Decimal("2000"), to_kwh=None, rate_per_kwh=Decimal("1")))
        # 2000 is neither 1500 nor 1501 (previous tier ends at 1500) → gap
        r = ValidationEngine.validate_tariff(s)
        assert any(i.code == "TARIFF_OVERLAP" for i in r.errors)

    def test_printed_invoice_convention_accepted(self):
        """i.e. the exact entries from a real قائمة أجور (1-1500, 1501-3000, …)."""
        from kse.domain.enums import TariffMethod
        from kse.domain.models import TariffTier
        from conftest import make_schedule

        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        s.tiers = [
            TariffTier(tier_no=1, from_kwh=Decimal("1"), to_kwh=Decimal("1500"), rate_per_kwh=Decimal("10")),
            TariffTier(tier_no=2, from_kwh=Decimal("1501"), to_kwh=Decimal("3000"), rate_per_kwh=Decimal("35")),
            TariffTier(tier_no=3, from_kwh=Decimal("3001"), to_kwh=Decimal("4000"), rate_per_kwh=Decimal("80")),
            TariffTier(tier_no=4, from_kwh=Decimal("4001"), to_kwh=Decimal("100000"), rate_per_kwh=Decimal("120")),
        ]
        r = ValidationEngine.validate_tariff(s)
        assert not r.has_errors

    def test_first_tier_from_one_accepted(self):
        from kse.domain.enums import TariffMethod
        from kse.domain.models import TariffTier
        from conftest import make_schedule

        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        s.tiers = [
            TariffTier(tier_no=1, from_kwh=Decimal("1"), to_kwh=Decimal("1500"), rate_per_kwh=Decimal("10")),
            TariffTier(tier_no=2, from_kwh=Decimal("1501"), to_kwh=Decimal("3000"), rate_per_kwh=Decimal("15")),
        ]
        r = ValidationEngine.validate_tariff(s)
        assert not r.has_errors

    def test_mixed_conventions_accepted(self):
        from kse.domain.enums import TariffMethod
        from kse.domain.models import TariffTier
        from conftest import make_schedule

        s = make_schedule(method=TariffMethod.PROGRESSIVE)
        s.tiers = [
            TariffTier(tier_no=1, from_kwh=Decimal("1"), to_kwh=Decimal("1500"), rate_per_kwh=Decimal("10")),
            TariffTier(tier_no=2, from_kwh=Decimal("1500"), to_kwh=Decimal("3000"), rate_per_kwh=Decimal("15")),
        ]
        r = ValidationEngine.validate_tariff(s)
        assert not r.has_errors