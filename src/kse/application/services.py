"""Application services (use cases). Depend on domain engines + repo ports."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from ..domain.enums import (
    ChargeCategory,
    DataSource,
    InvoiceStatus,
    MeterScenario,
    PaymentStatus,
    ServiceZone,
    SubscriberType,
)
from ..domain.errors import (
    DebtUnavailableError,
    DuplicateInvoiceNumberError,
    InvoiceStateError,
    NoTariffFoundError,
    OcrUnavailableError,
    TariffConflictError,
    ValidationFailedError,
    VerificationNeededError,
)


def _localize_error(tr, exc: Exception) -> str:
    """Localize known domain errors through the i18n callable."""
    if isinstance(exc, ValidationFailedError):
        return "; ".join(i.localized(tr) for i in exc.issues)
    if isinstance(exc, NoTariffFoundError):
        return tr("err_no_tariff", type=exc.subscriber_type, date=str(exc.effective_date))
    if isinstance(exc, TariffConflictError):
        return tr("err_tariff_conflict", names=", ".join(exc.schedule_names))
    if isinstance(exc, DebtUnavailableError):
        return tr("err_debt_unavailable")
    return str(exc)
from ..domain.models import (
    AuditLogEntry,
    Invoice,
    InvoiceCharge,
    InvoiceReading,
    Meter,
    Subscriber,
    TariffSchedule,
)
from ..domain.money import Money, money_label, round_money
from ..domain.services.audit import AuditEngine
from ..domain.services.fees import FeeResult
from ..domain.services.invoice_calc import InvoiceCalculation, InvoiceCalculator
from ..domain.services.tariff import TariffEngine
from ..domain.services.validation import Issue, ValidationEngine, ValidationReport

_SVC_EN = {
    "svc_recalc_note": "Recalculated from invoice {no}",
    "svc_audit_calc": "Invoice {no} calculated — total {amount}",
    "svc_audit_tariff_save": "Tariff {name} saved (version {v})",
    "svc_audit_tariff_del": "Tariff {name} deleted",
    "svc_sub_default_name": "Subscriber {no}",
    "err_debt_unavailable": "The amount cannot be verified because the previous-debt data is unavailable.",
    "err_no_tariff": "The invoice cannot be calculated exactly because the tariff schedule for the period is missing. (Subscriber type: {type} — date: {date})",
    "err_tariff_conflict": "More than one valid tariff was found for the period: {names}. Fix the schedules before calculating.",
}


def _svc_en_tr(key: str, **kwargs) -> str:
    text = _SVC_EN.get(key, key)
    return text.format(**kwargs) if kwargs else text
from .interfaces import (
    AuditRepository,
    InvoiceRepository,
    SubscriberRepository,
    TariffRepository,
)


# ---------------------------------------------------------------- DTOs


@dataclass
class CalculateInvoiceRequest:
    subscriber_type: SubscriberType = SubscriberType.RESIDENTIAL
    service_zone: Optional[ServiceZone] = None
    previous_reading: str = "0"
    current_reading: str = "0"
    previous_read_date: Optional[dt.date] = None
    current_read_date: Optional[dt.date] = None
    meter_multiplier: str = "1"
    scenario: MeterScenario = MeterScenario.NORMAL
    max_reading: Optional[str] = None
    replacement_base: Optional[str] = None
    previous_debt: Optional[Money] = None
    fees: list[InvoiceCharge] = field(default_factory=list)
    official_amount: Optional[Money] = None


@dataclass
class VerifyResult:
    report: ValidationReport = field(default_factory=ValidationReport)
    calc: Optional[InvoiceCalculation] = None
    official: Optional[Money] = None


# ---------------------------------------------------------------- services


class InvoiceService:
    def __init__(self, invoice_repo: InvoiceRepository, tariff_repo: TariffRepository,
                 subscriber_repo: SubscriberRepository, audit_repo: AuditRepository,
                 uow=None, tr=None) -> None:
        self.invoices = invoice_repo
        self.tariffs = tariff_repo
        self.subscribers = subscriber_repo
        self.audit = audit_repo
        self.uow = uow
        self.tr = tr or _svc_en_tr

    # ----- calculation (pure, deterministic) ---------------------------
    def calculate(self, req: CalculateInvoiceRequest) -> tuple[InvoiceCalculation, TariffSchedule]:
        report = ValidationEngine.validate_readings(
            previous=req.previous_reading, current=req.current_reading, scenario=req.scenario)
        date_report = ValidationEngine.validate_dates(
            previous_date=req.previous_read_date, current_date=req.current_read_date, issue_date=None)
        fee_report = ValidationEngine.validate_fees(req.fees)
        combined = ValidationReport(issues=report.issues + date_report.issues + fee_report.issues)
        if combined.has_errors:
            raise ValidationFailedError(combined.errors)

        target_date = req.current_read_date or req.previous_read_date
        if target_date is None:
            target_date = dt.date.today()

        schedule = TariffEngine.resolve(self.tariffs.list_schedules(include_inactive=True),
                                        req.subscriber_type, target_date,
                                        service_zone=req.service_zone)

        calc = InvoiceCalculator.calculate(
            subscriber_type=req.subscriber_type,
            previous_reading=req.previous_reading,
            current_reading=req.current_reading,
            previous_read_date=req.previous_read_date or target_date,
            current_read_date=req.current_read_date or target_date,
            tariff_schedule=schedule,
            fees=req.fees,
            previous_debt=req.previous_debt,
            multiplier=decimal_or_1(req.meter_multiplier),
            scenario=req.scenario,
            max_reading=Decimal(req.max_reading) if req.max_reading else None,
            replacement_base=Decimal(req.replacement_base) if req.replacement_base is not None else None,
            official_amount=req.official_amount,
            tr=self.tr,
        )
        return calc, schedule

    def verify(self, req: CalculateInvoiceRequest) -> VerifyResult:
        """Verification mode: compute & compare, never guessing (spec Â§13)."""
        result = VerifyResult(report=ValidationReport())
        try:
            result.calc, _ = self.calculate(req)
        except ValidationFailedError as exc:
            # Keep the individual issues so the page can localize each one.
            result.report.issues.extend(exc.issues)
            return result
        except VerificationNeededError as exc:
            result.report.issues.append(Issue("VERIFY_READING", "ERROR", str(exc)))
            return result
        except Exception as exc:  # noqa: BLE001
            result.report.issues.append(Issue("VERIFY_CALC", "ERROR", _localize_error(self.tr, exc)))
            return result
        result.official = req.official_amount
        return result

    # ----- persistence --------------------------------------------------
    def next_invoice_no(self, issue_date: Optional[dt.date] = None) -> str:
        year = (issue_date or dt.date.today()).year
        prefix = f"INV-{year}-"
        # Only this year's numbers matter, and only the number column is read (the old code
        # loaded up to 500 full invoices, and missed the highest number beyond that).
        max_no = 0
        for number in self.invoices.invoice_numbers(prefix):
            try:
                max_no = max(max_no, int(number[len(prefix):]))
            except ValueError:
                continue    # e.g. "INV-2026-0007-D2" from a duplicate renumbering
        return f"{prefix}{max_no + 1:04d}"


    def save_calculation(
        self,
        calc: InvoiceCalculation,
        schedule: TariffSchedule,
        subscriber: Subscriber | None,
        *,
        invoice_no: Optional[str] = None,
        issue_date: Optional[dt.date] = None,
        previous_read_date: Optional[dt.date] = None,
        current_read_date: Optional[dt.date] = None,
        notes: str = "",
        official_amount: Optional[Money] = None,
        scenario: MeterScenario = MeterScenario.NORMAL,
        user: str = "local",
        audit: bool = True,
    ) -> Invoice:
        issue_date = issue_date or dt.date.today()
        if isinstance(issue_date, dt.datetime):
            issue_date = issue_date.date()
        auto_number = not invoice_no
        invoice_no = invoice_no or self.next_invoice_no(issue_date)

        invoice = Invoice(
            invoice_no=invoice_no,
            subscriber_id=subscriber.id if subscriber else None,
            account_no=subscriber.account_no if subscriber else "",
            subscription_no=subscriber.subscription_no if subscriber else "",
            subscriber_name=subscriber.name if subscriber else "",
            subscriber_type=schedule.subscriber_type,
            issue_date=issue_date,
            previous_read_date=previous_read_date or calc.previous_read_date or issue_date,
            current_read_date=current_read_date or calc.current_read_date or issue_date,
            previous_reading=calc.reading.previous_reading if calc.reading else Decimal("0"),
            current_reading=calc.reading.current_reading if calc.reading else Decimal("0"),
            consumption_kwh=calc.reading.consumption_kwh if calc.reading else Decimal("0"),
            adjusted_kwh=calc.reading.adjusted_kwh if calc.reading else Decimal("0"),
            tariff_schedule_id=schedule.id,
            tariff_version=schedule.version,
            tariff_name=schedule.name,
            tariff_source=schedule.source.value,
            energy_cost=calc.energy_cost,
            fixed_fees=calc.fixed_fees,
            additional_fees=calc.additional_fees,
            discounts=calc.discounts,
            previous_debt=calc.previous_debt,
            current_amount=calc.current_amount,
            total_due=calc.total_due,
            official_amount=official_amount,
            comparison_status=calc.comparison.status.value if calc.comparison else "NOT_COMPARED",
            comparison_diff=calc.comparison.diff if calc.comparison else None,
            due_date=(issue_date or dt.date.today()) + dt.timedelta(days=15),
            payment_status=PaymentStatus.UNPAID,
            notes=notes,
        )

        reading = InvoiceReading(
            previous_reading=calc.reading.previous_reading if calc.reading else Decimal("0"),
            current_reading=calc.reading.current_reading if calc.reading else Decimal("0"),
            previous_date=invoice.previous_read_date or invoice.issue_date,
            current_date=invoice.current_read_date or invoice.issue_date,
            multiplier=calc.reading.multiplier if calc.reading else Decimal("1"),
            scenario=scenario,
            is_estimated=False,
            meter_replaced=scenario in (MeterScenario.REPLACEMENT, MeterScenario.RESET),
            consumption_kwh=invoice.consumption_kwh,
            adjusted_kwh=invoice.adjusted_kwh,
        )

        charges = list(calc.fee_result.charges) if calc.fee_result else []

        run_id = str(uuid.uuid4())
        invoice.audit_run_id = run_id
        for attempt in range(3):
            try:
                self.invoices.save(invoice, reading, charges)
                break
            except DuplicateInvoiceNumberError:
                # a concurrent writer took the number; an explicit number is the caller's problem
                if not auto_number or attempt == 2:
                    raise
                invoice.invoice_no = self.next_invoice_no(issue_date)
        if audit:
            self._append_audit("CALCULATE", calc, invoice, schedule, user, run_id, scenario)
        self._commit()
        return invoice

    def recalculate(self, invoice_id: int, user: str = "local") -> Invoice:
        """Re-run the saved inputs of an invoice against the CURRENT tariff tables."""
        invoice = self.invoices.get(invoice_id)
        if invoice is None:
            raise ValueError("invoice not found")
        reading = self.invoices.list_reading(invoice_id)
        charges = self.invoices.list_charges(invoice_id)
        if reading is None:
            raise ValueError("invoice has no stored reading; cannot recalculate")

        schedule = TariffEngine.resolve(
            self.tariffs.list_schedules(include_inactive=True),
            invoice.subscriber_type,
            reading.current_date,
        )
        req = CalculateInvoiceRequest(
            subscriber_type=invoice.subscriber_type,
            previous_reading=str(reading.previous_reading),
            current_reading=str(reading.current_reading),
            previous_read_date=reading.previous_date,
            current_read_date=reading.current_date,
            meter_multiplier=str(reading.multiplier),
            scenario=reading.scenario,
            previous_debt=invoice.previous_debt,
            fees=charges,
            official_amount=invoice.official_amount,
        )
        calc, schedule = self.calculate(req)
        if invoice.status != InvoiceStatus.ACTIVE:
            raise InvoiceStateError("not_active")
        if invoice.paid_amount > calc.total_due:
            raise InvoiceStateError("overpaid")      # nothing has been changed yet
        invoice.status = InvoiceStatus.RECALCULATED
        self.invoices.save(invoice, reading, charges)
        new_invoice = self.save_calculation(
            calc, schedule,
            subscriber=(self.subscribers.get(invoice.subscriber_id) if invoice.subscriber_id else None),
            issue_date=invoice.issue_date,
            previous_read_date=reading.previous_date,
            current_read_date=reading.current_date,
            notes=self.tr("svc_recalc_note", no=invoice.invoice_no),
            official_amount=invoice.official_amount,
            scenario=reading.scenario,
            user=user,
        )
        # payments belong to the live invoice; before this they stayed on the superseded one,
        # so analytics (active invoices only) lost them
        if invoice.paid_amount.raw > 0:
            self.invoices.transfer_payments(invoice_id, new_invoice.id)
            if self.uow:
                self.uow.commit()
            new_invoice = self.invoices.get(new_invoice.id)
        return new_invoice

    # ----- lifecycle ----------------------------------------------------
    def cancel(self, invoice_id: int, user: str = "local") -> Invoice:
        """Soft-delete: the invoice stays in the database as CANCELLED.

        Physically deleting rows broke the numbering sequence and erased the audit trail.
        An invoice with recorded payments cannot be cancelled (a refund must be handled first).
        """
        invoice = self.invoices.get(invoice_id)
        if invoice is None:
            raise ValueError("invoice not found")
        if invoice.status != InvoiceStatus.ACTIVE:
            raise InvoiceStateError("not_active")
        if invoice.paid_amount.raw > 0:
            raise InvoiceStateError("has_payments")
        self.invoices.set_status(invoice_id, InvoiceStatus.CANCELLED)
        self.audit.append(AuditLogEntry(
            action="INVOICE_CANCEL", entity_type="INVOICE", entity_id=invoice_id, user=user,
            description=f"Invoice {invoice.invoice_no} cancelled",
            details_json=json.dumps({"invoice_no": invoice.invoice_no}, ensure_ascii=False),
            invoice_id=invoice_id))
        if self.uow:
            self.uow.commit()
        return self.invoices.get(invoice_id)

    def suggested_previous_debt(self, subscriber_id: int) -> Money:
        """Debt to pre-fill on the subscriber's NEXT invoice.

        The newest active invoice already carries every older unpaid amount (its ``total_due``
        includes ``previous_debt``), so its remaining balance is the whole outstanding debt.
        Summing all unpaid invoices would count the same debt several times.
        It is only a suggestion: the user can edit the field.
        """
        latest = self.invoices.search(subscriber_id=subscriber_id, status=InvoiceStatus.ACTIVE, limit=1)
        if not latest:
            # first invoice in the app: the opening balance recorded on the subscriber, if any
            subscriber = self.subscribers.get(subscriber_id)
            opening = subscriber.previous_debt if subscriber is not None else Money.zero()
            return opening if opening.raw > 0 else Money.zero()
        remaining = latest[0].total_due - latest[0].paid_amount
        return remaining if remaining.raw > 0 else Money.zero()

    # ----- audit --------------------------------------------------------
    def _append_audit(self, action: str, calc: InvoiceCalculation, invoice: Invoice,
                      schedule: TariffSchedule, user: str, run_id: str,
                      scenario: MeterScenario = MeterScenario.NORMAL) -> None:
        snapshot = AuditEngine.build_snapshot(
            subscriber_type=invoice.subscriber_type,
            previous_reading=invoice.previous_reading,
            current_reading=invoice.current_reading,
            previous_read_date=invoice.previous_read_date,
            current_read_date=invoice.current_read_date,
            multiplier=str(calc.reading.multiplier) if calc.reading else "1",
            scenario=scenario,
            max_reading=None,
            replacement_base=None,
            tariff_schedule_id=schedule.id,
            tariff_version=schedule.version,
            tariff_name=schedule.name,
            tariff_source=schedule.source,
            debt=calc.previous_debt,
            fees=calc.fee_result.charges if calc.fee_result else [],
        )
        entry_data = AuditEngine.build_record(
            action=action,
            snapshot=snapshot,
            calc=calc,
            description=self.tr("svc_audit_calc", no=invoice.invoice_no,
                                amount=money_label(invoice.total_due)),
            invoice_id=invoice.id,
            user=user,
            run_id=run_id,
        )
        entry = AuditLogEntry(
            action=entry_data["action"],
            entity_type=entry_data["entity_type"],
            entity_id=entry_data["entity_id"],
            user=entry_data["user"],
            description=entry_data["description"],
            details_json=entry_data["details_json"],
            invoice_id=entry_data["invoice_id"],
            tariff_schedule_id=entry_data["tariff_schedule_id"],
            run_id=entry_data["run_id"],
        )
        self.audit.append(entry)

    def _commit(self) -> None:
        if self.uow is not None:
            self.uow.commit()


def decimal_or_1(value) -> Decimal:
    if value in (None, ""):
        return Decimal("1")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("1")


# ================================================================ tariffs


class TariffService:
    def __init__(self, tariff_repo: TariffRepository, audit_repo: AuditRepository, uow=None, tr=None) -> None:
        self.tariffs = tariff_repo
        self.audit = audit_repo
        self.uow = uow
        self.tr = tr or _svc_en_tr

    def list(self, include_inactive: bool = False) -> list[TariffSchedule]:
        return self.tariffs.list_schedules(include_inactive=include_inactive)

    def get(self, schedule_id: int) -> TariffSchedule | None:
        return self.tariffs.get_schedule(schedule_id)

    def validate(self, schedule: TariffSchedule) -> ValidationReport:
        return ValidationEngine.validate_tariff(schedule)

    def save(self, schedule: TariffSchedule, user: str = "local") -> TariffSchedule:
        report = self.validate(schedule)
        if report.has_errors:
            from ..domain.errors import ValidationFailedError

            raise ValidationFailedError(report.errors)
        saved = self.tariffs.save_schedule(schedule)
        self.audit.append(AuditLogEntry(
            action="TARIFF_SAVE", entity_type="TARIFF", entity_id=saved.id,
            description=self.tr("svc_audit_tariff_save", name=saved.name,
                                v=saved.version),
            details_json=json.dumps({"name": saved.name, "version": saved.version},
                                    ensure_ascii=False),
            tariff_schedule_id=saved.id, user=user,
        ))
        if self.uow is not None:
            self.uow.commit()
        return saved

    def delete(self, schedule_id: int) -> None:
        schedule = self.tariffs.get_schedule(schedule_id)
        self.tariffs.delete_schedule(schedule_id)
        if schedule is not None:
            self.audit.append(AuditLogEntry(
                action="TARIFF_DELETE", entity_type="TARIFF", entity_id=schedule_id,
                description=self.tr("svc_audit_tariff_del", name=schedule.name),
                tariff_schedule_id=schedule_id,
            ))
        if self.uow is not None:
            self.uow.commit()


# ================================================================ subscribers


class SubscriberService:
    def __init__(self, subscriber_repo: SubscriberRepository, meter_repo,
                 tariff_repo: TariffRepository, debt_repo, uow=None, tr=None) -> None:
        self.subscribers = subscriber_repo
        self.meters = meter_repo
        self.tariffs = tariff_repo
        self.debts = debt_repo
        self.uow = uow
        self.tr = tr or _svc_en_tr

    def find_or_create(self, account_no: str, subscription_no: str = "", name: str = "",
                       subscriber_type: SubscriberType = SubscriberType.RESIDENTIAL,
                       **kwargs) -> Subscriber:
        sub = self.subscribers.by_account(account_no)
        if sub is None:
            sub = Subscriber(
                account_no=account_no,
                subscription_no=subscription_no or account_no,
                name=name or self.tr("svc_sub_default_name", no=account_no),
                subscriber_type=subscriber_type,
            )
            subs = self.subscribers.save(sub)
            self._commit()
            return subs
        return sub

    def save(self, subscriber: Subscriber) -> Subscriber:
        s = self.subscribers.save(subscriber)
        self._commit()
        return s

    def delete(self, subscriber_id: int) -> None:
        self.subscribers.delete(subscriber_id)
        self._commit()

    def add_meter(self, meter: Meter) -> Meter:
        m = self.meters.save(meter)
        self._commit()
        return m

    def meters_of(self, subscriber_id: int):
        # renamed from ``meters``: the __init__ attribute ``self.meters`` (the repo)
        # shadowed the method, so calling it raised "'...Repository' is not callable"
        return self.meters.list_for_subscriber(subscriber_id)

    def set_debt(self, subscriber_id: int, amount: Money, reason: str = "") -> None:
        from ..domain.models import Debt

        self.debts.active_for_subscriber(subscriber_id)
        # simple approach: update Subscribers.previous_debt
        sub = self.subscribers.get(subscriber_id)
        if sub is not None:
            sub.previous_debt = amount
            self.subscribers.save(sub)
            self._commit()

    def _commit(self) -> None:
        if self.uow is not None:
            self.uow.commit()