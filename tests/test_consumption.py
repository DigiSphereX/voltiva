"""ConsumptionCalculator tests (spec §5, §25)."""
from decimal import Decimal

import pytest

from kse.domain.enums import MeterScenario
from kse.domain.errors import ReadingInvalidError, VerificationNeededError
from kse.domain.services.consumption import ConsumptionCalculator, VERIFICATION_MESSAGE


class TestNormal:
    def test_normal_sample(self):
        r = ConsumptionCalculator.calculate(13578, 17162)
        assert r.consumption_kwh == Decimal("3584")
        assert r.adjusted_kwh == Decimal("3584")

    def test_equal_readings_zero(self):
        r = ConsumptionCalculator.calculate(1000, 1000)
        assert r.consumption_kwh == Decimal("0")
        assert not r.needs_verification

    def test_zero_start(self):
        r = ConsumptionCalculator.calculate(0, 250)
        assert r.consumption_kwh == Decimal("250")

    def test_high_consumption(self):
        r = ConsumptionCalculator.calculate(0, 99999)
        assert r.consumption_kwh == Decimal("99999")

    def test_lower_current_raises_verification(self):
        with pytest.raises(VerificationNeededError) as exc:
            ConsumptionCalculator.calculate(17162, 13578)
        assert VERIFICATION_MESSAGE in str(exc.value)

    def test_readings_negative_invalid(self):
        with pytest.raises(ReadingInvalidError):
            ConsumptionCalculator.calculate(-5, 10)

    def test_reading_not_integer(self):
        with pytest.raises(ReadingInvalidError):
            ConsumptionCalculator.calculate(10, "abc")


class TestMultiplier:
    def test_multiplier_applied(self):
        r = ConsumptionCalculator.calculate(1000, 1100, multiplier=10)
        assert r.consumption_kwh == Decimal("100")
        assert r.adjusted_kwh == Decimal("1000")

    def test_multiplier_less_than_one_invalid(self):
        with pytest.raises(ReadingInvalidError):
            ConsumptionCalculator.calculate(0, 100, multiplier=0)


class TestSpecialScenarios:
    def test_rollover(self):
        r = ConsumptionCalculator.calculate(99990, 500, max_reading=100000, scenario=MeterScenario.ROLLOVER)
        assert r.consumption_kwh == Decimal("510")
        assert r.adjusted_kwh == Decimal("510")

    def test_rollover_requires_max(self):
        with pytest.raises(VerificationNeededError):
            ConsumptionCalculator.calculate(99990, 500, scenario=MeterScenario.ROLLOVER)

    def test_replacement(self):
        r = ConsumptionCalculator.calculate(5000, 300, scenario=MeterScenario.REPLACEMENT)
        assert r.consumption_kwh == Decimal("300")

    def test_replacement_with_base(self):
        r = ConsumptionCalculator.calculate(5000, 300, scenario=MeterScenario.REPLACEMENT, replacement_base=4200)
        assert r.consumption_kwh == Decimal("4500")

    def test_reset(self):
        r = ConsumptionCalculator.calculate(9000, 120, scenario=MeterScenario.RESET)
        assert r.consumption_kwh == Decimal("120")