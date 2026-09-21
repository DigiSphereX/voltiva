"""Domain entities (debt-free POJOs). Dates are `datetime.date`, money is `Money`,
readings are `Decimal`. These models never depend on the UI or the database.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .enums import (
    ChargeCategory,
    DataSource,
    InvoiceStatus,
    MeterPhase,
    MeterScenario,
    MeterType,
    PaymentStatus,
    ServiceZone,
    SubscriberType,
    TariffMethod,
)
from .money import Money


@dataclass
class Subscriber:
    subscription_no: str = ""
    account_no: str = ""
    name: str = ""
    address: str = ""
    governorate: str = ""
    qadaa: str = ""
    nahia: str = ""
    house_no: str = ""
    department: str = ""
    subscriber_type: SubscriberType = SubscriberType.RESIDENTIAL
    phase: MeterPhase = MeterPhase.SINGLE
    status: str = "ACTIVE"
    previous_debt: Money = field(default_factory=Money.zero)
    notes: str = ""
    id: Optional[int] = None
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


@dataclass
class Meter:
    subscriber_id: Optional[int] = None
    meter_no: str = ""
    serial_no: str = ""
    meter_type: MeterType = MeterType.ELECTROMECHANICAL
    phase: MeterPhase = MeterPhase.SINGLE
    multiplier: Decimal = Decimal("1")
    status: str = "ACTIVE"
    installed_at: Optional[dt.date] = None
    removed_at: Optional[dt.date] = None
    notes: str = ""
    id: Optional[int] = None
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


@dataclass
class TariffTier:
    tier_no: int = 1
    from_kwh: Decimal = Decimal("0")
    to_kwh: Optional[Decimal] = None  # None means "upper bound +∞"
    rate_per_kwh: Decimal = Decimal("0")
    id: Optional[int] = None

    def covers(self, consumption: Decimal) -> bool:
        if consumption < self.from_kwh:
            return False
        if self.to_kwh is None:
            return True
        return consumption < self.to_kwh

    def label(self) -> str:
        top = "∞" if self.to_kwh is None else str(self.to_kwh)
        return f"{self.from_kwh} - {top}"


@dataclass
class TariffSchedule:
    name_ar: str = ""
    name_en: str = ""
    subscriber_type: SubscriberType = SubscriberType.RESIDENTIAL
    method: TariffMethod = TariffMethod.FLAT
    service_zone: ServiceZone = ServiceZone.TRADITIONAL
    version: str = "1"
    effective_from: dt.date = field(default_factory=dt.date.today)
    effective_to: Optional[dt.date] = None
    is_active: bool = True
    source: DataSource = DataSource.UNKNOWN
    source_date: Optional[dt.date] = None
    source_detail: str = ""
    notes: str = ""
    tiers: list[TariffTier] = field(default_factory=list)
    fixed_fees: list["TariffFee"] = field(default_factory=list)
    id: Optional[int] = None
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    @property
    def tariff_id(self) -> Optional[int]:
        return self.id


@dataclass
class TariffFee:
    """A default charge attached to a tariff schedule (e.g. meter fees)."""

    name_ar: str = ""
    name_en: str = ""
    category: ChargeCategory = ChargeCategory.FIXED_FEE
    amount: Money = field(default_factory=Money.zero)
    is_fixed: bool = True
    depends_on_consumption: bool = False
    taxable: bool = False
    in_current_amount: bool = True
    in_total_due: bool = True
    reason: str = ""
    id: Optional[int] = None


@dataclass
class InvoiceCharge:
    """A single line item on an invoice."""

    name: str = ""
    name_en: str = ""
    category: ChargeCategory = ChargeCategory.FIXED_FEE
    amount: Money = field(default_factory=Money.zero)
    reason: str = ""
    is_fixed: bool = True
    depends_on_consumption: bool = False
    taxable: bool = False
    in_current_amount: bool = True
    in_total_due: bool = True
    source: DataSource = DataSource.USER_DEFINED
    tariff_fee_id: Optional[int] = None
    id: Optional[int] = None


@dataclass
class InvoiceReading:
    meter_id: Optional[int] = None
    meter_no: str = ""
    previous_reading: Decimal = Decimal("0")
    current_reading: Decimal = Decimal("0")
    previous_date: dt.date = field(default_factory=dt.date.today)
    current_date: dt.date = field(default_factory=dt.date.today)
    multiplier: Decimal = Decimal("1")
    scenario: MeterScenario = MeterScenario.NORMAL
    is_estimated: bool = False
    meter_replaced: bool = False
    rollover_base: Optional[Decimal] = None
    consumption_kwh: Decimal = Decimal("0")
    adjusted_kwh: Decimal = Decimal("0")
    id: Optional[int] = None


@dataclass
class Invoice:
    invoice_no: str = ""
    subscriber_id: Optional[int] = None
    account_no: str = ""
    subscription_no: str = ""
    subscriber_name: str = ""
    subscriber_type: SubscriberType = SubscriberType.RESIDENTIAL
    issue_date: dt.date = field(default_factory=dt.date.today)
    previous_read_date: Optional[dt.date] = None
    current_read_date: Optional[dt.date] = None
    previous_reading: Decimal = Decimal("0")
    current_reading: Decimal = Decimal("0")
    consumption_kwh: Decimal = Decimal("0")
    adjusted_kwh: Decimal = Decimal("0")
    tariff_schedule_id: Optional[int] = None
    tariff_version: str = ""
    tariff_name: str = ""
    tariff_source: str = "UNKNOWN"
    energy_cost: Money = field(default_factory=Money.zero)
    fixed_fees: Money = field(default_factory=Money.zero)
    additional_fees: Money = field(default_factory=Money.zero)
    discounts: Money = field(default_factory=Money.zero)
    previous_debt: Money = field(default_factory=Money.zero)
    current_amount: Money = field(default_factory=Money.zero)
    total_due: Money = field(default_factory=Money.zero)
    currency: str = "IQD"
    official_amount: Optional[Money] = None
    comparison_status: str = "NOT_COMPARED"
    comparison_diff: Optional[Money] = None
    due_date: Optional[dt.date] = None
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    paid_amount: Money = field(default_factory=Money.zero)
    remaining_balance: Money = field(default_factory=Money.zero)
    notes: str = ""
    status: InvoiceStatus = InvoiceStatus.ACTIVE
    reading: Optional[InvoiceReading] = None
    charges: list[InvoiceCharge] = field(default_factory=list)
    audit_run_id: Optional[int] = None
    id: Optional[int] = None
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


@dataclass
class Payment:
    invoice_id: Optional[int] = None
    amount: Money = field(default_factory=Money.zero)
    paid_at: dt.date = field(default_factory=dt.date.today)
    method: str = "CASH"
    notes: str = ""
    id: Optional[int] = None
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


@dataclass
class Debt:
    subscriber_id: Optional[int] = None
    amount: Money = field(default_factory=Money.zero)
    reason: str = ""
    recorded_at: dt.date = field(default_factory=dt.date.today)
    status: str = "ACTIVE"
    notes: str = ""
    id: Optional[int] = None


@dataclass
class Setting:
    key: str = ""
    value: str = ""
    source: DataSource = DataSource.USER_DEFINED
    updated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    id: Optional[int] = None


@dataclass
class AuditLogEntry:
    action: str = "CALCULATE"
    entity_type: str = "INVOICE"
    entity_id: Optional[int] = None
    user: str = "local"
    description: str = ""
    details_json: str = "{}"
    invoice_id: Optional[int] = None
    tariff_schedule_id: Optional[int] = None
    before_json: Optional[str] = None
    after_json: Optional[str] = None
    run_id: Optional[int] = None
    id: Optional[int] = None
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))