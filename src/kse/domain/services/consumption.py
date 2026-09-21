"""ConsumptionCalculator — derives consumption from meter readings (spec §5).

Rules:
- normal            : current − previous            (may be 0)
- multiplier        : (current − previous) × multiplier
- replacement       : new meter; consumption = current + base (pre-replacement usage)
- reset             : consumption = current (pre-reset usage must be added manually → note)
- rollover          : (max_reading − previous) + current    (max_reading configurable)
- current < previous with no explicit scenario → VerificationNeededError (never auto-guess)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..enums import MeterScenario
from ..errors import ReadingInvalidError, VerificationNeededError
from ..money import round_consumption

VERIFICATION_MESSAGE = (
    "القراءة الحالية أقل من القراءة السابقة --- يرجى التحقق من تبديل العداد أو إدخال القراءة."
)


@dataclass
class ConsumptionResult:
    previous_reading: Decimal = Decimal("0")
    current_reading: Decimal = Decimal("0")
    multiplier: Decimal = Decimal("1")
    scenario: MeterScenario = MeterScenario.NORMAL
    consumption_kwh: Decimal = Decimal("0")   # raw difference before multiplier
    adjusted_kwh: Decimal = Decimal("0")      # consumption × multiplier (used for billing)
    needs_verification: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def days(self) -> int | None:
        return None  # filled by application layer when dates are known


class ConsumptionCalculator:
    """Stateless, pure calculator."""

    @staticmethod
    def calculate(
        previous_reading,
        current_reading,
        multiplier: Decimal | int | str = Decimal("1"),
        scenario: MeterScenario = MeterScenario.NORMAL,
        max_reading: Decimal | int | None = None,
        replacement_base: Decimal | int | None = None,
    ) -> ConsumptionResult:
        prev = _as_reading(previous_reading, "previous")
        curr = _as_reading(current_reading, "current")
        mult = _as_multiplier(multiplier)

        notes: list[str] = []
        needs_verification = False

        if scenario in (MeterScenario.REPLACEMENT, MeterScenario.RESET):
            base = Decimal(replacement_base or 0)
            if base > 0:
                raw = base + curr
                notes.append(f"استبدال/إعادة ضبط: استهلاك سابق {base} + قراءة جديدة {curr}")
            else:
                raw = curr
                notes.append(
                    "تم قبول الاستهلاك لأن الحساب بسياق استبدال/إعادة ضبط، "
                    "لكن يجب إضافة الاستهلاك السابق (إن وُجد) يدوياً."
                )
        elif curr < prev:
            if scenario == MeterScenario.ROLLOVER:
                if max_reading is None or max_reading <= 0:
                    raise VerificationNeededError(
                        "لحساب Rollover يجب إدخال سعة العداد القصوى (max_reading)."
                    )
                raw = Decimal(max_reading) - prev + curr
                notes.append(f"Rollover: ({max_reading} - {prev}) + {curr}")
            else:
                needs_verification = True
                notes.append(VERIFICATION_MESSAGE)
                raise VerificationNeededError(VERIFICATION_MESSAGE)
        else:
            raw = curr - prev
            if raw == 0:
                notes.append("الاستهلاك = صفر (القراءتان متساويتان).")

        adjusted = round_consumption(raw * mult)

        result = ConsumptionResult(
            previous_reading=prev,
            current_reading=curr,
            multiplier=mult,
            scenario=scenario,
            consumption_kwh=round_consumption(raw),
            adjusted_kwh=adjusted,
            needs_verification=needs_verification,
            notes=notes,
        )
        return result


def _as_reading(value, name: str) -> Decimal:
    from ..money import Money, latin_digits

    raw_text = str(value).strip()
    if raw_text.startswith("-") or latin_digits(raw_text).startswith("-"):
        raise ReadingInvalidError("لا يمكن أن تكون القراءة سالبة.")
    try:
        d = Money.parse_reading(raw_text)
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise ReadingInvalidError(f"قراءة غير صالحة ({name}): {value} — {exc}") from exc
    if d < 0:
        raise ReadingInvalidError("لا يمكن أن تكون القراءة سالبة.")
    return d


def _as_multiplier(value) -> Decimal:
    from ..money import Money

    try:
        d = Money.parse_reading(str(value))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise ReadingInvalidError(f"معامل قياس غير صالح: {value} — {exc}") from exc
    if d <= 0:
        raise ReadingInvalidError("معامل القياس يجب أن يكون أكبر من الصفر.")
    return d