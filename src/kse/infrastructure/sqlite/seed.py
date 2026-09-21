"""Seed data — sample/estimated only, never official.
Values follow the reference test case from the spec (readings 13578→17162 ⇒ 3584 kWh ⇒ 35,840 IQD @ flat 10).

⚠️ All seeded tariffs are marked DataSource.ESTIMATED and clearly labelled as
samples for demonstration testing. Real values must be entered from official
sources through Tariff Management before being used in production.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from decimal import Decimal

from ...domain.enums import DataSource, MeterPhase, MeterScenario, SubscriberType, TariffMethod
from ...domain.models import (
    Invoice,
    InvoiceCharge,
    InvoiceReading,
    Meter,
    Subscriber,
    TariffFee,
    TariffSchedule,
    TariffTier,
)
from ...domain.money import Money
from ...domain.services.invoice_calc import InvoiceCalculator
from .repositories import SqliteInvoiceRepository, SqliteSubscriberRepository, SqliteTariffRepository

SAMPLE_RESIDENTIAL_FLAT_10 = "sample_residential_flat_10_v1"
SAMPLE_PROGRESSIVE_2024 = "sample_progressive_2024_v1"

SETTING_KEYS = {
    "language": "ar",
    "theme": "dark",
    "db_path": "",
    "seeded": "1",
}


def build_sample_schedules() -> list[TariffSchedule]:
    flat = TariffSchedule(
        name_ar="مرجع منزلي 2024 (نموذج اختبار)",
        name_en="Residential Reference 2024 (Sample)",
        subscriber_type=SubscriberType.RESIDENTIAL,
        method=TariffMethod.FLAT,
        version="v1/sample",
        effective_from=dt.date(2024, 1, 1),
        effective_to=None,
        is_active=True,
        source=DataSource.ESTIMATED,
        source_date=dt.date(2024, 1, 1),
        source_detail="قيمة مرجعية تقديرية من حالة الاختبار المرفقة (3584 kWh × 10 = 35,840). ليست قيمة رسمية.",
        notes="مثال توضيحي فقط — يجب استبدال الجدول بجدول رسمي من جهة معتمدة.",
    )
    flat.tiers = [TariffTier(tier_no=1, from_kwh=Decimal("0"), to_kwh=None, rate_per_kwh=Decimal("10"))]

    prog = TariffSchedule(
        name_ar="مثال شرائح تجاري 2024 (نموذج اختبار)",
        name_en="Commercial Tiers 2024 (Sample)",
        subscriber_type=SubscriberType.COMMERCIAL,
        method=TariffMethod.PROGRESSIVE,
        version="v1/sample",
        effective_from=dt.date(2024, 1, 1),
        effective_to=None,
        is_active=True,
        source=DataSource.ESTIMATED,
        source_date=dt.date(2024, 1, 1),
        source_detail="أمثلة شرائح افتراضية لأغراض الاختبار فقط.",
        notes="مثال توضيحي فقط — قيم الشرائح ليست رسمية.",
    )
    prog.tiers = [
        TariffTier(tier_no=1, from_kwh=Decimal("0"), to_kwh=Decimal("1500"), rate_per_kwh=Decimal("10")),
        TariffTier(tier_no=2, from_kwh=Decimal("1500"), to_kwh=Decimal("3000"), rate_per_kwh=Decimal("15")),
        TariffTier(tier_no=3, from_kwh=Decimal("3000"), to_kwh=Decimal("4000"), rate_per_kwh=Decimal("20")),
        TariffTier(tier_no=4, from_kwh=Decimal("4000"), to_kwh=None, rate_per_kwh=Decimal("25")),
    ]
    return [flat, prog]


def seed(conn: sqlite3.Connection, overwrite: bool = False) -> None:
    settings_repo = None
    from .repositories import SqliteSettingsRepository

    settings = SqliteSettingsRepository(conn)

    if settings.get("seeded", "") == "1" and not overwrite:
        return

    tariff_repo = SqliteTariffRepository(conn)
    for s in build_sample_schedules():
        if not overwrite and tariff_repo.list_schedules():
            pass
        tariff_repo.save_schedule(s)

    # ---- sample subscriber (the one from the reference invoice) ----
    sub = Subscriber(
        account_no="1201234567",
        subscription_no="1700012101",
        name="مشترك تجريبي (بيانات نموذجية)",
        address="بغداد / الكرخ",
        governorate="بغداد",
        qadaa="الكرخ",
        nahia="المنصور",
        subscriber_type=SubscriberType.RESIDENTIAL,
    )
    sub_repo = SqliteSubscriberRepository(conn)
    sub_repo.save(sub)

    # ---- sample meter ----
    meter = Meter(
        subscriber_id=sub.id,
        meter_no="34001122",
        serial_no="567890",
        phase=MeterPhase.SINGLE,
        multiplier=Decimal("1"),
        installed_at=dt.date(2020, 1, 1),
    )
    from .repositories import SqliteMeterRepository

    SqliteMeterRepository(conn).save(meter)

    # ---- sample invoice matching the reference test case ----
    flat = tariff_repo.list_schedules()
    flat = next((s for s in flat if s.subscriber_type == SubscriberType.RESIDENTIAL), flat[0])

    calc = InvoiceCalculator.calculate(
        subscriber_type=SubscriberType.RESIDENTIAL,
        previous_reading=13578,
        current_reading=17162,
        previous_read_date=dt.date(2024, 2, 1),
        current_read_date=dt.date(2024, 3, 15),
        tariff_schedule=flat,
        previous_debt=Money.zero(),
        official_amount=Money.of(35840),
    )

    reading = InvoiceReading(
        meter_id=meter.id,
        meter_no=meter.meter_no,
        previous_reading=calc.reading.previous_reading,
        current_reading=calc.reading.current_reading,
        previous_date=dt.date(2024, 2, 1),
        current_date=dt.date(2024, 3, 15),
        multiplier=Decimal("1"),
        scenario=MeterScenario.NORMAL,
        consumption_kwh=calc.reading.consumption_kwh,
        adjusted_kwh=calc.reading.adjusted_kwh,
    )

    invoice = Invoice(
        invoice_no="SAMPLE-2024-0001",
        subscriber_id=sub.id,
        account_no=sub.account_no,
        subscription_no=sub.subscription_no,
        subscriber_name=sub.name,
        subscriber_type=SubscriberType.RESIDENTIAL,
        issue_date=dt.date(2024, 3, 15),
        previous_read_date=dt.date(2024, 2, 1),
        current_read_date=dt.date(2024, 3, 15),
        previous_reading=calc.reading.previous_reading,
        current_reading=calc.reading.current_reading,
        consumption_kwh=calc.reading.consumption_kwh,
        adjusted_kwh=calc.reading.adjusted_kwh,
        tariff_schedule_id=flat.id,
        tariff_version=flat.version,
        tariff_name=flat.name_ar,
        energy_cost=calc.energy_cost,
        current_amount=calc.current_amount,
        total_due=calc.total_due,
        official_amount=calc.comparison.official_amount,
        comparison_status=calc.comparison.status.value,
        comparison_diff=calc.comparison.diff,
        due_date=dt.date(2024, 3, 30),
        notes="فاتورة نموذجية مطابقة لحالة الاختبار المرجعية.",
    )
    invoice_repo = SqliteInvoiceRepository(conn)
    invoice_repo.save(invoice, reading, calc.fee_result.charges)

    settings.set("seeded", "1", DataSource.USER_DEFINED)
    conn.commit()