"""Demo seed data — fictional English records for demonstration and testing only.

All seeded tariffs are marked DataSource.ESTIMATED and clearly labelled as
samples for demonstration. Real values must be entered from official sources
through Tariff Management before being used in production.

The residential reference invoice mirrors the engine test case (readings
13578 → 17162 ⇒ 3,584 units ⇒ 35,840 at a flat 10 units/kWh rate) so the
sample is self-verifying.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from decimal import Decimal

from ...domain.enums import DataSource, MeterPhase, MeterScenario, SubscriberType, TariffMethod
from ...domain.models import (
    Invoice,
    InvoiceReading,
    Meter,
    Subscriber,
    TariffSchedule,
    TariffTier,
)
from ...domain.money import Money
from ...domain.services.invoice_calc import InvoiceCalculator
from .repositories import SqliteInvoiceRepository, SqliteMeterRepository, SqliteSubscriberRepository, SqliteTariffRepository

SAMPLE_RESIDENTIAL_FLAT_10 = "sample_residential_flat_10_v1"
SAMPLE_PROGRESSIVE_2024 = "sample_progressive_2024_v1"

# Demo records are keyed by these natural keys so reloading replaces only the
# sample set and never touches the operator's real data.
DEMO_ACCOUNT_NOS = ("1201234567", "1201234568", "1201234569", "1201234570")
DEMO_INVOICE_PREFIX = "SAMPLE-"
DEMO_VERSION_SUFFIX = "/demo"

SETTING_KEYS = {
    "language": "ar",
    "theme": "dark",
    "db_path": "",
    "seeded": "1",
}


def build_sample_schedules() -> list[TariffSchedule]:
    flat = TariffSchedule(
        name_ar="مرجع منزلي 2024 (نموذج تجريبي)",
        name_en="Residential Reference 2024 (Demo)",
        subscriber_type=SubscriberType.RESIDENTIAL,
        method=TariffMethod.FLAT,
        version="v1/demo",
        effective_from=dt.date(2024, 1, 1),
        effective_to=None,
        is_active=True,
        source=DataSource.ESTIMATED,
        source_date=dt.date(2024, 1, 1),
        source_detail="Reference demo case: 3,584 units × 10 = 35,840. Not an official rate.",
        notes="Demo data only — replace with official schedules before real use.",
    )
    flat.tiers = [TariffTier(tier_no=1, from_kwh=Decimal("0"), to_kwh=None, rate_per_kwh=Decimal("10"))]

    prog = TariffSchedule(
        name_ar="شرائح تجاري 2024 (نموذج تجريبي)",
        name_en="Commercial Tiers 2024 (Demo)",
        subscriber_type=SubscriberType.COMMERCIAL,
        method=TariffMethod.PROGRESSIVE,
        version="v1/demo",
        effective_from=dt.date(2024, 1, 1),
        effective_to=None,
        is_active=True,
        source=DataSource.ESTIMATED,
        source_date=dt.date(2024, 1, 1),
        source_detail="Fictional tiered example for testing only.",
        notes="Demo data only — tier values are not official.",
    )
    prog.tiers = [
        TariffTier(tier_no=1, from_kwh=Decimal("0"), to_kwh=Decimal("1500"), rate_per_kwh=Decimal("10")),
        TariffTier(tier_no=2, from_kwh=Decimal("1500"), to_kwh=Decimal("3000"), rate_per_kwh=Decimal("15")),
        TariffTier(tier_no=3, from_kwh=Decimal("3000"), to_kwh=Decimal("4000"), rate_per_kwh=Decimal("20")),
        TariffTier(tier_no=4, from_kwh=Decimal("4000"), to_kwh=None, rate_per_kwh=Decimal("25")),
    ]
    return [flat, prog]


def _demo_subscriber(*, account_no: str, subscription_no: str, name: str, address: str,
                     governorate: str, qadaa: str, subscriber_type: SubscriberType) -> Subscriber:
    return Subscriber(
        account_no=account_no,
        subscription_no=subscription_no,
        name=name,
        address=address,
        governorate=governorate,
        qadaa=qadaa,
        subscriber_type=subscriber_type,
    )


def _demo_meter(*, subscriber_id: int, meter_no: str, serial_no: str, phase: MeterPhase,
                installed_at: dt.date) -> Meter:
    return Meter(
        subscriber_id=subscriber_id,
        meter_no=meter_no,
        serial_no=serial_no,
        phase=phase,
        multiplier=Decimal("1"),
        installed_at=installed_at,
    )


def _insert_demo_invoice(invoice_repo: SqliteInvoiceRepository, *, sub: Subscriber, meter: Meter,
                         schedule: TariffSchedule, invoice_no: str, prev: int, curr: int,
                         prev_date: dt.date, curr_date: dt.date, issue_date: dt.date,
                         due_date: dt.date, expected: int) -> None:
    calc = InvoiceCalculator.calculate(
        subscriber_type=sub.subscriber_type,
        previous_reading=prev,
        current_reading=curr,
        previous_read_date=prev_date,
        current_read_date=curr_date,
        tariff_schedule=schedule,
        previous_debt=Money.zero(),
        official_amount=Money.of(expected),
    )

    reading = InvoiceReading(
        meter_id=meter.id,
        meter_no=meter.meter_no,
        previous_reading=calc.reading.previous_reading,
        current_reading=calc.reading.current_reading,
        previous_date=prev_date,
        current_date=curr_date,
        multiplier=Decimal("1"),
        scenario=MeterScenario.NORMAL,
        consumption_kwh=calc.reading.consumption_kwh,
        adjusted_kwh=calc.reading.adjusted_kwh,
    )

    invoice = Invoice(
        invoice_no=invoice_no,
        subscriber_id=sub.id,
        account_no=sub.account_no,
        subscription_no=sub.subscription_no,
        subscriber_name=sub.name,
        subscriber_type=sub.subscriber_type,
        issue_date=issue_date,
        previous_read_date=prev_date,
        current_read_date=curr_date,
        previous_reading=calc.reading.previous_reading,
        current_reading=calc.reading.current_reading,
        consumption_kwh=calc.reading.consumption_kwh,
        adjusted_kwh=calc.reading.adjusted_kwh,
        tariff_schedule_id=schedule.id,
        tariff_version=schedule.version,
        tariff_name=schedule.name_en,
        energy_cost=calc.energy_cost,
        current_amount=calc.current_amount,
        total_due=calc.total_due,
        official_amount=calc.comparison.official_amount,
        comparison_status=calc.comparison.status.value,
        comparison_diff=calc.comparison.diff,
        due_date=due_date,
        notes="Demo invoice — fictional data for demonstration only.",
    )
    invoice_repo.save(invoice, reading, calc.fee_result.charges)


def _clear_demo_records(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM Invoices WHERE invoice_no LIKE ?", (DEMO_INVOICE_PREFIX + "%",))
    placeholders = ",".join("?" * len(DEMO_ACCOUNT_NOS))
    cur.execute(f"DELETE FROM Subscribers WHERE account_no IN ({placeholders})", DEMO_ACCOUNT_NOS)
    cur.execute("DELETE FROM TariffSchedules WHERE version LIKE ?", ("%" + DEMO_VERSION_SUFFIX,))
    conn.commit()


def seed(conn: sqlite3.Connection, overwrite: bool = False) -> None:
    from .repositories import SqliteSettingsRepository

    settings = SqliteSettingsRepository(conn)

    if settings.get("seeded", "") == "1" and not overwrite:
        return

    if overwrite:
        _clear_demo_records(conn)

    tariff_repo = SqliteTariffRepository(conn)
    flat, prog = build_sample_schedules()
    tariff_repo.save_schedule(flat)
    tariff_repo.save_schedule(prog)

    sub_repo = SqliteSubscriberRepository(conn)
    meter_repo = SqliteMeterRepository(conn)
    invoice_repo = SqliteInvoiceRepository(conn)

    sarah = _demo_subscriber(
        account_no="1201234567", subscription_no="1700012101", name="Sarah Johnson",
        address="18 Maple Avenue, Springfield", governorate="Springfield", qadaa="River County",
        subscriber_type=SubscriberType.RESIDENTIAL,
    )
    sub_repo.save(sarah)
    sarah_meter = _demo_meter(
        subscriber_id=sarah.id, meter_no="34001122", serial_no="567890",
        phase=MeterPhase.SINGLE, installed_at=dt.date(2020, 1, 1),
    )
    meter_repo.save(sarah_meter)

    michael = _demo_subscriber(
        account_no="1201234568", subscription_no="1700012102", name="Michael Chen",
        address="7 Birch Street, Lakeside", governorate="Lakeside", qadaa="Valley County",
        subscriber_type=SubscriberType.RESIDENTIAL,
    )
    sub_repo.save(michael)
    michael_meter = _demo_meter(
        subscriber_id=michael.id, meter_no="34001123", serial_no="567891",
        phase=MeterPhase.SINGLE, installed_at=dt.date(2019, 6, 15),
    )
    meter_repo.save(michael_meter)

    emily = _demo_subscriber(
        account_no="1201234569", subscription_no="1700012103", name="Emily Watson",
        address="12 Cedar Lane, Hillcrest", governorate="Hillcrest", qadaa="Park County",
        subscriber_type=SubscriberType.RESIDENTIAL,
    )
    sub_repo.save(emily)
    emily_meter = _demo_meter(
        subscriber_id=emily.id, meter_no="34001124", serial_no="567892",
        phase=MeterPhase.SINGLE, installed_at=dt.date(2021, 3, 1),
    )
    meter_repo.save(emily_meter)

    david = _demo_subscriber(
        account_no="1201234570", subscription_no="1700012104", name="David Wilson",
        address="9 Industrial Park Road, Portside", governorate="Portside", qadaa="Harbor County",
        subscriber_type=SubscriberType.COMMERCIAL,
    )
    sub_repo.save(david)
    david_meter = _demo_meter(
        subscriber_id=david.id, meter_no="34001125", serial_no="567893",
        phase=MeterPhase.THREE, installed_at=dt.date(2018, 11, 20),
    )
    meter_repo.save(david_meter)

    # Reference case: 13578 → 17162 ⇒ 3,584 units ⇒ 35,840 (flat × 10) — matches the engine spec.
    _insert_demo_invoice(
        invoice_repo, sub=sarah, meter=sarah_meter, schedule=flat,
        invoice_no="SAMPLE-2024-0001", prev=13578, curr=17162,
        prev_date=dt.date(2024, 2, 1), curr_date=dt.date(2024, 3, 15),
        issue_date=dt.date(2024, 3, 15), due_date=dt.date(2024, 3, 30), expected=35840,
    )
    _insert_demo_invoice(
        invoice_repo, sub=michael, meter=michael_meter, schedule=flat,
        invoice_no="SAMPLE-2024-0002", prev=28000, curr=29300,
        prev_date=dt.date(2024, 4, 10), curr_date=dt.date(2024, 5, 12),
        issue_date=dt.date(2024, 5, 12), due_date=dt.date(2024, 5, 27), expected=13000,
    )
    _insert_demo_invoice(
        invoice_repo, sub=emily, meter=emily_meter, schedule=flat,
        invoice_no="SAMPLE-2024-0003", prev=600, curr=760,
        prev_date=dt.date(2024, 4, 18), curr_date=dt.date(2024, 5, 20),
        issue_date=dt.date(2024, 5, 20), due_date=dt.date(2024, 6, 4), expected=1600,
    )
    # Tiered commercial case: 2,100 units → 1,500 × 10 + 600 × 15 = 24,000.
    _insert_demo_invoice(
        invoice_repo, sub=david, meter=david_meter, schedule=prog,
        invoice_no="SAMPLE-2024-0004", prev=1200, curr=3300,
        prev_date=dt.date(2024, 4, 5), curr_date=dt.date(2024, 5, 25),
        issue_date=dt.date(2024, 5, 25), due_date=dt.date(2024, 6, 9), expected=24000,
    )

    settings.set("seeded", "1", DataSource.USER_DEFINED)
    conn.commit()