"""Application-layer contracts (ports). Implementations live in infrastructure."""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from decimal import Decimal

from ..domain.enums import PaymentStatus
from ..domain.models import (
    AuditLogEntry,
    Debt,
    Invoice,
    InvoiceCharge,
    InvoiceReading,
    Meter,
    Payment,
    Setting,
    Subscriber,
    TariffFee,
    TariffSchedule,
    TariffTier,
)


class SubscriberRepository(ABC):
    @abstractmethod
    def get(self, subscriber_id: int) -> Subscriber | None: ...

    @abstractmethod
    def by_account(self, account_no: str) -> Subscriber | None: ...

    @abstractmethod
    def search(self, query: str, limit: int = 50) -> list[Subscriber]: ...

    @abstractmethod
    def save(self, subscriber: Subscriber) -> Subscriber: ...

    @abstractmethod
    def list_all(self) -> list[Subscriber]: ...

    @abstractmethod
    def delete(self, subscriber_id: int) -> None: ...


class MeterRepository(ABC):
    @abstractmethod
    def list_for_subscriber(self, subscriber_id: int) -> list[Meter]: ...

    @abstractmethod
    def get(self, meter_id: int) -> Meter | None: ...

    @abstractmethod
    def save(self, meter: Meter) -> Meter: ...


class TariffRepository(ABC):
    @abstractmethod
    def list_schedules(self, include_inactive: bool = False) -> list[TariffSchedule]: ...

    @abstractmethod
    def get_schedule(self, schedule_id: int) -> TariffSchedule | None: ...

    @abstractmethod
    def save_schedule(self, schedule: TariffSchedule) -> TariffSchedule: ...

    @abstractmethod
    def delete_schedule(self, schedule_id: int) -> None: ...

    @abstractmethod
    def save_fee(self, fee: TariffFee) -> TariffFee: ...

    @abstractmethod
    def delete_fee(self, fee_id: int) -> None: ...


class InvoiceRepository(ABC):
    @abstractmethod
    def save(self, invoice: Invoice, reading: InvoiceReading | None, charges: list[InvoiceCharge]) -> Invoice: ...

    @abstractmethod
    def get(self, invoice_id: int) -> Invoice | None: ...

    @abstractmethod
    def by_number(self, invoice_no: str) -> Invoice | None: ...

    @abstractmethod
    def list_recent(self, limit: int = 50) -> list[Invoice]: ...

    @abstractmethod
    def search(
        self,
        *,
        query: str = "",
        subscriber_id: int | None = None,
        payment_status: PaymentStatus | None = None,
        date_from: dt.date | None = None,
        date_to: dt.date | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Invoice]: ...

    @abstractmethod
    def count(self, **filters) -> int: ...

    @abstractmethod
    def delete(self, invoice_id: int) -> None: ...

    @abstractmethod
    def list_reading(self, invoice_id: int) -> InvoiceReading | None: ...

    @abstractmethod
    def list_charges(self, invoice_id: int) -> list[InvoiceCharge]: ...

    @abstractmethod
    def set_payment(self, invoice_id: int, amount, paid_at, method, notes) -> None: ...


class AuditRepository(ABC):
    @abstractmethod
    def append(self, entry: AuditLogEntry) -> AuditLogEntry: ...

    @abstractmethod
    def list_for_invoice(self, invoice_id: int, limit: int = 50) -> list[AuditLogEntry]: ...

    @abstractmethod
    def list_recent(self, limit: int = 100) -> list[AuditLogEntry]: ...


class PaymentRepository(ABC):
    @abstractmethod
    def list_for_invoice(self, invoice_id: int) -> list[Payment]: ...


class DebtRepository(ABC):
    @abstractmethod
    def active_for_subscriber(self, subscriber_id: int) -> list[Debt]: ...


class SettingsRepository(ABC):
    @abstractmethod
    def get(self, key: str, default: str = "") -> str: ...

    @abstractmethod
    def set(self, key: str, value: str, source) -> None: ...


class UnitOfWork(ABC):
    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...