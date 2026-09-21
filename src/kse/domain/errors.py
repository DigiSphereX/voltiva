"""Domain error hierarchy.

Rules from the spec:
- Do NOT hide missing data; never guess.
- Show clear, understandable calculation errors.
"""
from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain/business errors."""

    code = "DOMAIN_ERROR"


class CalculationError(DomainError):
    """A calculation cannot be completed accurately."""

    code = "CALCULATION_ERROR"


class NoTariffFoundError(CalculationError):
    """No effective tariff exists for subscriber type + date (spec §21/§37)."""

    code = "NO_TARIFF_FOUND"

    def __init__(self, subscriber_type: str, effective_date) -> None:
        self.subscriber_type = subscriber_type
        self.effective_date = effective_date
        super().__init__(
            "لا يمكن حساب الفاتورة بدقة لأن جدول التعرفة للفترة المحددة غير موجود. "
            f"(المشترك: {subscriber_type} — التاريخ: {effective_date})"
        )


class DebtUnavailableError(CalculationError):
    """Previous/accumulated debt data is missing (spec §37)."""

    code = "DEBT_UNAVAILABLE"

    def __init__(self, message: str = "لا يمكن التحقق من المبلغ لأن بيانات الدين السابق غير متوفرة.") -> None:
        super().__init__(message)


class VerificationNeededError(DomainError):
    """A special meter scenario needs operator verification (current < previous)."""

    code = "VERIFICATION_NEEDED"


class ReadingInvalidError(DomainError):
    """Readings violate basic validation (non-integer, negative…)."""

    code = "READING_INVALID"


class TariffConflictError(CalculationError):
    """More than one tariff matches; never guess (spec §21)."""

    code = "TARIFF_CONFLICT"

    def __init__(self, schedule_names: list[str]) -> None:
        super().__init__(
            "تم العثور على أكثر من تعرفة واحدة صالحة للفترة المحددة: "
            + "، ".join(schedule_names)
            + ". يرجى تصحيح الجداول قبل الحساب."
        )


class OcrUnavailableError(DomainError):
    """OCR engine is not available on this machine."""

    code = "OCR_UNAVAILABLE"


class ValidationFailedError(DomainError):
    """Aggregate validation errors occurred."""

    code = "VALIDATION_FAILED"

    def __init__(self, issues: list) -> None:
        self.issues = issues
        super().__init__("; ".join(i.message for i in issues))