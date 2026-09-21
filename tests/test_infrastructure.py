"""Infrastructure tests — SQLite round-trip, seed, migrations, exports (spec §22, §31)."""
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest

from kse.domain.enums import ChargeCategory, DataSource, PaymentStatus, SubscriberType, TariffMethod
from kse.domain.models import Invoice, InvoiceCharge, InvoiceReading, Subscriber
from kse.domain.money import Money
from kse.infrastructure.backup import backup_database, restore_database
from kse.infrastructure.export.exporters import (
    csv_export,
    excel_export,
    invoice_to_dict,
    json_export,
    json_to_invoice,
)
from kse.infrastructure.sqlite.db import check_schema, connect
from kse.infrastructure.sqlite.repositories import build_repositories
from kse.infrastructure.sqlite.seed import SAMPLE_RESIDENTIAL_FLAT_10, seed


class TestSchema:
    def test_migrations_run(self, mem_db):
        assert check_schema(mem_db) >= 1

    def test_ddl_creates_tables(self, mem_db):
        tables = {r["name"] for r in mem_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ["Subscribers", "Meters", "Invoices", "InvoiceReadings", "InvoiceCharges",
                  "TariffSchedules", "TariffTiers", "TariffFees", "Payments", "Debts",
                  "Settings", "AuditLogs", "schema_migrations"]:
            assert t in tables


class TestRepositories:
    def test_subscriber_save_load(self, mem_db):
        repos = build_repositories(mem_db)
        s = Subscriber(account_no="1234", subscription_no="abc-12", name="Test")
        repos["subscribers"].save(s)
        mem_db.commit()
        got = repos["subscribers"].get(s.id)
        assert got.name == "Test"
        assert got.account_no == "1234"

    def test_subscriber_delete_orphans_invoices(self, mem_db):
        repos = build_repositories(mem_db)
        s = Subscriber(account_no="7777", subscription_no="sub-7", name="S")
        repos["subscribers"].save(s)
        inv = Invoice(
            invoice_no="INV-2024-0007", subscriber_id=s.id, account_no="7777",
            subscriber_type=SubscriberType.RESIDENTIAL, issue_date=dt.date(2024, 3, 15),
            previous_reading=Decimal("0"), current_reading=Decimal("0"),
            consumption_kwh=Decimal("0"), adjusted_kwh=Decimal("0"),
            current_amount=Money.of(0), total_due=Money.of(0),
        )
        repos["invoices"].save(inv, None, [])
        mem_db.commit()

        repos["subscribers"].delete(s.id)
        mem_db.commit()

        assert repos["subscribers"].get(s.id) is None
        got = repos["invoices"].get(inv.id)
        assert got is not None  # invoice history preserved
        assert got.subscriber_id is None
        assert got.account_no == "7777"

    def test_tariff_with_tiers_roundtrip(self, mem_db):
        from kse.domain.models import TariffSchedule, TariffTier

        repos = build_repositories(mem_db)
        sched = TariffSchedule(
            name_ar="تعرفة", subscriber_type=SubscriberType.RESIDENTIAL, method=TariffMethod.PROGRESSIVE,
            effective_from=dt.date(2024, 1, 1), source=DataSource.ESTIMATED,
            tiers=[
                TariffTier(tier_no=1, from_kwh=Decimal("0"), to_kwh=Decimal("1500"), rate_per_kwh=Decimal("10")),
                TariffTier(tier_no=2, from_kwh=Decimal("1500"), to_kwh=None, rate_per_kwh=Decimal("15")),
            ],
        )
        repos["tariffs"].save_schedule(sched)
        mem_db.commit()
        got = repos["tariffs"].get_schedule(sched.id)
        assert len(got.tiers) == 2
        assert got.tiers[1].to_kwh is None

    def test_invoice_full_roundtrip(self, mem_db):
        repos = build_repositories(mem_db)
        sub = Subscriber(account_no="9999", subscription_no="sub-1", name="S")
        repos["subscribers"].save(sub)

        inv = Invoice(
            invoice_no="INV-2024-0001", subscriber_id=sub.id, account_no="9999",
            subscriber_type=SubscriberType.RESIDENTIAL, issue_date=dt.date(2024, 3, 15),
            previous_reading=Decimal("13578"), current_reading=Decimal("17162"),
            consumption_kwh=Decimal("3584"), adjusted_kwh=Decimal("3584"),
            energy_cost=Money.of(35840), current_amount=Money.of(35840), total_due=Money.of(35840),
        )
        reading = InvoiceReading(
            previous_reading=Decimal("13578"), current_reading=Decimal("17162"),
            previous_date=dt.date(2024, 2, 1), current_date=dt.date(2024, 3, 15),
            consumption_kwh=Decimal("3584"), adjusted_kwh=Decimal("3584"),
        )
        charge = InvoiceCharge(name="رسوم", category=ChargeCategory.FIXED_FEE, amount=Money.of(1000))
        repos["invoices"].save(inv, reading, [charge])
        mem_db.commit()

        got = repos["invoices"].get(inv.id)
        assert got.total_due == Money.of(35840)
        assert got.previous_reading == Decimal("13578")
        got_reading = repos["invoices"].list_reading(inv.id)
        assert got_reading.current_reading == Decimal("17162")
        got_charges = repos["invoices"].list_charges(inv.id)
        assert len(got_charges) == 1
        assert got_charges[0].amount == Money.of(1000)


class TestSeed:
    def test_seed_produces_reference_invoice(self, tmp_path):
        db = tmp_path / "t.db"
        conn = connect(db)
        seed(conn, overwrite=True)
        repos = build_repositories(conn)
        invoices = repos["invoices"].list_recent()
        assert len(invoices) >= 1
        sample = invoices[0]
        assert sample.consumption_kwh == Decimal("3584")
        assert sample.total_due == Money.of(35840)
        assert sample.comparison_status == "MATCH"
        conn.close()


class TestJson:
    def test_export_import_roundtrip(self, tmp_path):
        inv = Invoice(
            invoice_no="INV-001", subscriber_type=SubscriberType.RESIDENTIAL,
            issue_date=dt.date(2024, 3, 15), previous_reading=Decimal("1"), current_reading=Decimal("2"),
            consumption_kwh=Decimal("1"), adjusted_kwh=Decimal("1"),
            energy_cost=Money.of(10), current_amount=Money.of(10), total_due=Money.of(10),
        )
        reading = InvoiceReading(
            previous_reading=Decimal("1"), current_reading=Decimal("2"),
            previous_date=dt.date(2024, 1, 1), current_date=dt.date(2024, 2, 1),
            consumption_kwh=Decimal("1"), adjusted_kwh=Decimal("1"),
        )
        charge = InvoiceCharge(name="x", category=ChargeCategory.ADDITIONAL_FEE, amount=Money.of(5), taxable=True)
        target = tmp_path / "inv.json"
        json_export(inv, reading, [charge], target)

        payload = json.loads(target.read_text(encoding="utf-8"))
        loaded_inv, loaded_reading, loaded_charges = json_to_invoice(payload)
        assert loaded_inv.invoice_no == "INV-001"
        assert loaded_inv.total_due == Money.of(10)
        assert loaded_reading.current_reading == Decimal("2")
        assert loaded_charges[0].taxable is True

    def test_export_dict(self):
        inv = Invoice(total_due=Money.of(1234))
        data = invoice_to_dict(inv)
        assert data["invoice"]["total_due"] == "1234.00"


class TestBackup:
    def test_backup_restore(self, tmp_path):
        db = tmp_path / "live.db"
        conn = connect(db)
        repos = build_repositories(conn)
        repos["subscribers"].save(Subscriber(account_no="111", subscription_no="111", name="A"))
        conn.commit()
        conn.close()

        backup_path = backup_database(db, tmp_path / "backup.db")
        assert backup_path.exists()

        # restore into a second live location
        conn2 = connect(tmp_path / "live2.db")
        conn2.close()
        restore_database(tmp_path / "live2.db", backup_path)
        conn3 = connect(tmp_path / "live2.db")
        got = build_repositories(conn3)["subscribers"].by_account("111")
        assert got is not None
        conn3.close()


class TestExports:
    def test_csv(self, tmp_path):
        rows = [{"a": 1, "b": 2}]
        f = tmp_path / "out.csv"
        csv_export(rows, f)
        assert f.exists()

    def test_excel(self, tmp_path):
        inv = Invoice(invoice_no="X", total_due=Money.of(9))
        f = tmp_path / "out.xlsx"
        excel_export([inv], f)
        assert f.exists()
        assert f.stat().st_size > 0