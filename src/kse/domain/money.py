"""Money type & the single, centralized rounding policy (spec §9).

Determinism requirements:
- Never use float/double for financial values → everything is `decimal.Decimal`.
- One rounding mode in the whole system: `ROUND_HALF_UP` to 2 decimals.
- Clear separation between Raw Value (Decimal, 2dp) and Displayed Value (string).

Display examples (spec):
- raw 35840.00  →  displayed "35,840"   (IQD, grouped)
- raw 12345.67  →  displayed "12,346"   (IQD rounded for screen)
"""
from __future__ import annotations

import decimal
import re
from decimal import Decimal, ROUND_HALF_UP, getcontext

MONEY_SCALE = 2          # internal monetary precision
CONSUMPTION_SCALE = 6    # consumption precision (supports multipliers)
CURRENCY = "IQD"
CURRENCY_AR = "د.ع"

getcontext().prec = 34


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Money):
        return value.raw
    return Decimal(str(value))


def round_money(value) -> Decimal:
    """Central rounding: half-up, MONEY_SCALE decimals."""
    return _to_decimal(value).quantize(Decimal("1e-{0}".format(MONEY_SCALE)), rounding=ROUND_HALF_UP)


def round_consumption(value) -> Decimal:
    return _to_decimal(value).quantize(Decimal("1e-{0}".format(CONSUMPTION_SCALE)), rounding=ROUND_HALF_UP)


def fmt_quantity(d: Decimal | int, max_scale: int = CONSUMPTION_SCALE) -> str:
    """Format a quantity (kWh) with thousands separators; trim trailing zeros."""
    d = _to_decimal(d)
    if d == d.to_integral_value():
        text = f"{d.quantize(Decimal('1')):,}"
    else:
        q = d.quantize(Decimal("1e-{0}".format(max_scale)), rounding=ROUND_HALF_UP)
        text = f"{q:,}".rstrip("0").rstrip(".")
        if text in {"", "-"}:
            text = "0"
    return text


def fmt_ar_number(d: Decimal | int, scale: int = 0) -> str:
    """Format a plain number with grouping, converting ASCII digits to Arabic-Indic digits."""
    if scale == 0:
        raw = f"{_to_decimal(d).quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}"
    else:
        raw = f"{_to_decimal(d).quantize(Decimal('1e-{:d}'.format(scale)), rounding=ROUND_HALF_UP):,}"
    return arabic_digits(raw)


def arabic_digits(text: str) -> str:
    """Convert ASCII digits 0-9 to Arabic-Indic digits, and separators to Arabic ones."""
    mapping = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
    return text.translate(mapping).replace(",", "٬").replace(".", "٫")


def latin_digits(text: str) -> str:
    """Convert Arabic-Indic digits and separators back to ASCII (for parsing user input)."""
    mapping = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    result = text.translate(mapping).replace("٬", ",").replace("٫", ".")
    return result


class Money:
    """Immutable money value (IQD). Raw = Decimal with MONEY_SCALE decimals."""

    __slots__ = ("_raw",)

    def __init__(self, raw) -> None:
        self._raw = round_money(raw)

    # ---- constructors -------------------------------------------------
    @classmethod
    def zero(cls) -> "Money":
        return cls(Decimal("0"))

    @classmethod
    def of(cls, value) -> "Money":
        return cls(_to_decimal(value))

    # ---- properties ----------------------------------------------------
    @property
    def raw(self) -> Decimal:
        return self._raw

    @property
    def is_zero(self) -> bool:
        return self._raw == 0

    @property
    def is_negative(self) -> bool:
        return self._raw < 0

    # ---- arithmetic (all results re-rounded via constructor) ----------
    def __add__(self, other) -> "Money":
        return Money(self._raw + _to_decimal(other))

    def __sub__(self, other) -> "Money":
        return Money(self._raw - _to_decimal(other))

    def __mul__(self, other) -> "Money":
        if isinstance(other, Money):
            raise TypeError("Money cannot be multiplied by Money")
        return Money(self._raw * _to_decimal(other))

    __rmul__ = __mul__

    def __truediv__(self, other) -> "Money":
        if other == 0:
            raise ZeroDivisionError("division by zero")
        return Money(self._raw / _to_decimal(other))

    def __neg__(self) -> "Money":
        return Money(-self._raw)

    def __eq__(self, other) -> bool:
        return isinstance(other, Money) and self._raw == other._raw

    def __lt__(self, other) -> bool:
        return self._raw < _to_decimal(other)

    def __le__(self, other) -> bool:
        return self._raw <= _to_decimal(other)

    def __gt__(self, other) -> bool:
        return self._raw > _to_decimal(other)

    def __ge__(self, other) -> bool:
        return self._raw >= _to_decimal(other)

    def __hash__(self) -> int:
        return hash(self._raw)

    def __repr__(self) -> str:
        return f"Money({self._raw})"

    # ---- display -------------------------------------------------------
    def display(self, decimals: int = 0) -> str:
        """Displayed value: grouped, e.g. 35,840 (default IQD integer view)."""
        q = self._raw.quantize(Decimal("1e-{:d}".format(decimals)), rounding=ROUND_HALF_UP)
        return f"{q:,}"

    def display_ar(self) -> str:
        """Arabic-Indic digits + IQD suffix: '٣٥٬٨٤٠ د.ع'."""
        return f"{arabic_digits(self.display())} {CURRENCY_AR}"

    def display_exact(self) -> str:
        return f"{self._raw:,}"

    def to_db(self) -> str:
        return str(self._raw)

    @classmethod
    def from_db(cls, raw: str | None | Decimal) -> "Money":
        if raw is None or raw == "":
            return cls.zero()
        return cls(_to_decimal(raw))

    # ---- parsing helpers -----------------------------------------------
    @staticmethod
    def _clean_input(text: str, *, integer_only: bool) -> str:
        import re

        cleaned = latin_digits(str(text)).strip()
        if integer_only:
            if re.search(r"[.,]", cleaned):
                raise ValueError("القراءات يجب أن تكون أعداداً صحيحة بدون كسر.")
            cleaned = re.sub(r"[^0-9]", "", cleaned)
        else:
            cleaned = re.sub(r"[^0-9.,]", "", cleaned).replace(",", "")
        return cleaned.strip()

    @staticmethod
    def parse_iqd_input(text: str) -> "Money":
        """Parse user input allowing Arabic-Indic digits, Arabic/ASCII separators."""
        if text is None:
            raise ValueError("no value")
        cleaned = Money._clean_input(text, integer_only=False)
        if cleaned == "":
            raise ValueError("no value")
        try:
            return Money(Decimal(cleaned))
        except (decimal.InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"مبلغ غير صالح: {text}") from exc

    @staticmethod
    def parse_reading(text: str) -> Decimal:
        """Parse a reading entry (integer kWh); Arabic-Indic digits allowed."""
        if text is None:
            raise ValueError("no reading")
        cleaned = Money._clean_input(text, integer_only=True)
        if cleaned == "":
            raise ValueError("no reading")
        try:
            value = Decimal(cleaned)
        except decimal.InvalidOperation as exc:
            raise ValueError(f"قراءة غير صالحة: {text}") from exc
        if value != value.to_integral_value():
            raise ValueError("readings must be whole numbers (kWh)")
        return value