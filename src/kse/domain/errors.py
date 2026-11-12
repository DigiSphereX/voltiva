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
            "The invoice cannot be calculated accurately because no tariff schedule covers "
            f"the selected period. (Subscriber: {subscriber_type} — Date: {effective_date})"
        )


class DebtUnavailableError(CalculationError):
    """Previous/accumulated debt data is missing (spec §37)."""

    code = "DEBT_UNAVAILABLE"

    def __init__(self, message: str = "The amount cannot be verified because previous-debt data is unavailable.") -> None:
        super().__init__(message)


class DuplicateInvoiceNumberError(DomainError):
    """An invoice with this number already exists (UNIQUE invoice_no)."""

    code = "DUPLICATE_INVOICE_NO"

    def __init__(self, invoice_no: str) -> None:
        self.invoice_no = invoice_no
        super().__init__(f"Invoice number {invoice_no!r} already exists.")


class InvoiceStateError(DomainError):
    """An invoice operation is not allowed in its current state.

    ``reason``: ``not_active`` (already cancelled/recalculated), ``has_payments`` (cancel needs a
    refund first) or ``overpaid`` (recalculated total is below what was already paid).
    """

    code = "INVOICE_STATE"
    _MESSAGES = {
        "not_active": "Only an active invoice can be changed this way.",
        "has_payments": "This invoice has recorded payments and cannot be cancelled.",
        "overpaid": "The recalculated total is lower than the amount already paid.",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


class PaymentError(DomainError):
    """A payment cannot be recorded (amount <= 0, over-payment, cancelled invoice).

    ``reason`` is one of ``non_positive`` / ``exceeds`` / ``cancelled`` so the UI
    can show a localized message.
    """

    code = "PAYMENT_ERROR"
    _MESSAGES = {
        "non_positive": "Payment amount must be greater than zero.",
        "exceeds": "Payment exceeds the remaining balance of the invoice.",
        "cancelled": "Cannot record a payment on a cancelled invoice.",
        "inactive": "Cannot record a payment on a superseded (recalculated) invoice.",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


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
            "More than one tariff is valid for the selected period: "
            + ", ".join(schedule_names)
            + ". Please correct the schedules before calculating."
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