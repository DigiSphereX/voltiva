"""Money & rounding policy tests (spec §9)."""
from decimal import Decimal

import pytest

from kse.domain.money import Money, arabic_digits, fmt_quantity, latin_digits, round_money


class TestMoney:
    def test_sample_35_840(self):
        m = Money.of(35840)
        assert m.raw == Decimal("35840.00")
        assert m.display() == "35,840"
        assert m.display_ar() == "٣٥٬٨٤٠ د.ع"

    def test_rounding_halves_up(self):
        assert round_money("12345.545") == Decimal("12345.55")
        assert round_money("12345.544") == Decimal("12345.54")

    def test_money_arithmetic_deterministic(self):
        a = Money.of("10.005")
        b = Money.of("20")
        assert (b + a).raw == Decimal("30.01")  # 10.005 rounds to 10.01 then added? no:
        # Money.of rounds immediately: Money.of("10.005") -> 10.01 (half-up .005->.01)
        assert Money.of("10.005").raw == Decimal("10.01")

    def test_money_multiplication_by_consumption(self):
        cost = Money.of(10) * Decimal("3584")
        assert cost.raw == Decimal("35840.00")
        assert cost.display() == "35,840"

    def test_negative_is_discount(self):
        assert Money.of("-25").is_negative

    def test_db_roundtrip(self):
        m = Money.of("12345.67")
        assert Money.from_db(m.to_db()) == m

    def test_parse_iqd_input(self):
        assert Money.parse_iqd_input(" 35,840 د.ع ").raw == Decimal("35840.00")
        assert Money.parse_iqd_input("٣٥٬٨٤٠").raw == Decimal("35840.00")
        with pytest.raises(ValueError):
            Money.parse_iqd_input("abc")

    def test_parse_reading_rejects_fraction(self):
        with pytest.raises(ValueError):
            Money.parse_reading("12.5")
        assert Money.parse_reading("12") == Decimal("12")

    def test_fmt_quantity(self):
        assert fmt_quantity(Decimal("3584")) == "3,584"
        assert fmt_quantity(Decimal("3584.5")) == "3,584.5"
        assert fmt_quantity(Decimal("0")) == "0"


class TestDigits:
    def test_arabic_indic(self):
        assert arabic_digits("35,840") == "٣٥٬٨٤٠"

    def test_latin_roundtrip(self):
        assert latin_digits("٣٥٬٨٤٠") == "35,840"