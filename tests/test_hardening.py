"""Regression tests for the security / correctness hardening pass."""
import datetime as dt
import json
import os
import sqlite3

import pytest

from kse.application.services import CalculateInvoiceRequest, InvoiceService, SubscriberService, TariffService
from kse.domain.enums import InvoiceStatus, PaymentStatus, SubscriberType
from kse.domain.errors import PaymentError
from kse.domain.money import Money
from kse.infrastructure.backup import InvalidBackupError, backup_database, restore_database, validate_backup
from kse.infrastructure.export.exporters import _dec, csv_export, safe_cell
from kse.infrastructure.sqlite import db as dbm
from kse.infrastructure.sqlite.repositories import build_repositories
from kse.infrastructure.sqlite.seed import seed

from conftest import make_schedule


def _ctx(mem_db):
    repos = build_repositories(mem_db)
    seed(mem_db, overwrite=True)
    inv = InvoiceService(repos["invoices"], repos["tariffs"], repos["subscribers"], repos["audit"], repos["uow"])
    sub = SubscriberService(repos["subscribers"], repos["meters"], repos["tariffs"], repos["debts"], repos["uow"])
    return inv, sub, repos


def _make_invoice(inv_svc, sub_svc, name="Ali", prev="0", cur="500", account="ACC-1"):
    sub = sub_svc.find_or_create(account, name=name)
    calc, sched = inv_svc.calculate(CalculateInvoiceRequest(
        subscriber_type=SubscriberType.RESIDENTIAL, previous_reading=prev, current_reading=cur,
        previous_read_date=dt.date(2024, 2, 1), current_read_date=dt.date(2024, 3, 1)))
    return inv_svc.save_calculation(calc, sched, sub)


# ------------------------------------------------------------ payments
class TestPayments:
    def test_zero_and_negative_rejected(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        inv = _make_invoice(inv_svc, sub_svc)
        for bad in (0, -5):
            with pytest.raises(PaymentError) as e:
                repos["invoices"].set_payment(inv.id, bad, dt.date.today(), "CASH", "")
            assert e.value.reason == "non_positive"

    def test_overpayment_rejected(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        inv = _make_invoice(inv_svc, sub_svc)
        with pytest.raises(PaymentError) as e:
            repos["invoices"].set_payment(inv.id, inv.total_due + Money.of(1), dt.date.today(), "CASH", "")
        assert e.value.reason == "exceeds"

    def test_paying_remaining_twice_is_impossible(self, mem_db):
        """Old 'mark paid' added total_due on every click -> paid_amount > total_due."""
        inv_svc, sub_svc, repos = _ctx(mem_db)
        inv = _make_invoice(inv_svc, sub_svc)
        repos["invoices"].set_payment(inv.id, inv.total_due, dt.date.today(), "CASH", "")
        got = repos["invoices"].get(inv.id)
        assert got.payment_status == PaymentStatus.PAID
        assert (got.total_due - got.paid_amount).raw == 0
        with pytest.raises(PaymentError):
            repos["invoices"].set_payment(inv.id, got.total_due, dt.date.today(), "CASH", "")

    def test_partial_then_remaining(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        inv = _make_invoice(inv_svc, sub_svc)
        first = Money.of(inv.total_due.raw / 2)
        repos["invoices"].set_payment(inv.id, first, dt.date.today(), "CASH", "")
        mid = repos["invoices"].get(inv.id)
        assert mid.payment_status == PaymentStatus.PARTIAL
        repos["invoices"].set_payment(inv.id, mid.total_due - mid.paid_amount, dt.date.today(), "CASH", "")
        assert repos["invoices"].get(inv.id).payment_status == PaymentStatus.PAID


# ------------------------------------------------------------ queries
class TestQueries:
    def test_like_wildcards_are_literal(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        _make_invoice(inv_svc, sub_svc, name="Ali")
        assert repos["invoices"].search(query="%") == []
        assert repos["invoices"].search(query="_") == []
        assert repos["subscribers"].search("%") == []
        assert len(repos["invoices"].search(query="Ali")) == 1

    def test_status_filter_excludes_recalculated(self, mem_db):
        """Analytics used search() without a status filter -> recalculated invoices counted twice."""
        inv_svc, sub_svc, repos = _ctx(mem_db)
        inv = _make_invoice(inv_svc, sub_svc)
        new = inv_svc.recalculate(inv.id)
        everything = {i.id for i in repos["invoices"].search(limit=1000)}
        active = {i.id for i in repos["invoices"].search(status=InvoiceStatus.ACTIVE, limit=1000)}
        assert inv.id in everything and new.id in everything      # history is still listed...
        assert inv.id not in active and new.id in active          # ...but only the live one is "active"

    def test_invoice_numbers_stay_unique_past_500(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        year = dt.date.today().year
        for n in range(1, 8):
            i = _make_invoice(inv_svc, sub_svc)
        # forge the highest number far beyond the old 500-row window, with an OLD issue date
        mem_db.execute("UPDATE Invoices SET invoice_no=?, issue_date='2001-01-01' WHERE id=?",
                       (f"INV-{year}-0999", i.id))
        assert inv_svc.next_invoice_no() == f"INV-{year}-1000"

    def test_schedules_batch_load_matches_single_load(self, mem_db):
        _, _, repos = _ctx(mem_db)
        s = make_schedule(name="extra")
        repos["tariffs"].save_schedule(s)
        for listed in repos["tariffs"].list_schedules(include_inactive=True):
            single = repos["tariffs"].get_schedule(listed.id)
            assert [t.rate_per_kwh for t in listed.tiers] == [t.rate_per_kwh for t in single.tiers]
            assert len(listed.fixed_fees) == len(single.fixed_fees)


# ------------------------------------------------------------ services
class TestServices:
    def test_tariff_audit_details_is_valid_json_with_quotes(self, mem_db):
        _, _, repos = _ctx(mem_db)
        svc = TariffService(repos["tariffs"], repos["audit"], repos["uow"])
        s = make_schedule(name='Tariff "A" \\ x')
        saved = svc.save(s)
        entry = [e for e in repos["audit"].list_recent(50) if e.action == "TARIFF_SAVE"][0]
        assert json.loads(entry.details_json)["name"] == saved.name

    def test_subscriber_service_meters_of(self, mem_db):
        _, sub_svc, _ = _ctx(mem_db)
        sub = sub_svc.find_or_create("ACC-9", name="X")
        assert sub_svc.meters_of(sub.id) == []


# ------------------------------------------------------------ export
class TestExport:
    @pytest.mark.parametrize("value", ["=HYPERLINK(\"http://x\",\"y\")", "+cmd", "@SUM(A1)", "-2+3", "\t=1"])
    def test_formula_prefixes_neutralised(self, value):
        assert safe_cell(value).startswith("'")

    def test_numbers_and_normal_text_untouched(self, tmp_path):
        assert safe_cell("-1,500") == "-1,500"
        assert safe_cell("+12.5") == "+12.5"
        assert safe_cell("Ali") == "Ali"
        assert safe_cell(5) == 5
        p = tmp_path / "x.csv"
        csv_export([{"name": "=1+1", "total": "-20"}], p)
        text = p.read_text(encoding="utf-8-sig")
        assert "'=1+1" in text and "-20" in text

    @pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "abc", None])
    def test_import_rejects_non_finite_numbers(self, bad):
        with pytest.raises(ValueError):
            _dec(bad, "total_due")

    def test_import_accepts_normal_numbers(self):
        assert str(_dec("12.50", "x")) == "12.50"


# ------------------------------------------------------------ db / backup
class TestDatabaseSafety:
    def test_migrations_are_idempotent_after_interruption(self, tmp_path):
        path = tmp_path / "x.db"
        c = dbm.connect(path)
        c.execute("DELETE FROM schema_migrations WHERE version IN (2, 3)")  # column from v2 already exists
        c.commit()
        c.close()
        c = dbm.connect(path)  # used to crash: duplicate column name
        assert dbm.check_schema(c) == dbm.SCHEMA_VERSION
        c.close()

    def test_restore_rejects_bad_files_and_keeps_live_data(self, tmp_path):
        live = tmp_path / "live.db"
        c = dbm.connect(live)
        c.execute("INSERT INTO Settings(key,value,updated_at) VALUES('k','v','now')")
        c.commit()
        c.close()
        junk = tmp_path / "junk.db"
        junk.write_text("not a database")
        foreign = tmp_path / "foreign.db"
        s = sqlite3.connect(foreign)
        s.execute("create table t(x)")
        s.commit()
        s.close()
        for bad in (junk, foreign):
            with pytest.raises(InvalidBackupError):
                restore_database(live, bad)
        with pytest.raises(ValueError):
            restore_database(live, live)
        c = dbm.connect(live)
        assert c.execute("SELECT value FROM Settings WHERE key='k'").fetchone()[0] == "v"
        c.close()

    def test_future_schema_rejected(self, tmp_path):
        f = tmp_path / "future.db"
        c = dbm.connect(f)
        c.execute("INSERT INTO schema_migrations(version) VALUES (99)")
        c.commit()
        c.close()
        with pytest.raises(InvalidBackupError):
            validate_backup(f)

    def test_backup_roundtrip_and_no_partial_file(self, tmp_path):
        live = tmp_path / "live.db"
        dbm.connect(live).close()
        b = backup_database(live)
        validate_backup(b)
        assert not list(tmp_path.glob("*.part"))
        with pytest.raises(ValueError):
            backup_database(live, live)


# ------------------------------------------------------------ multi-invoice JSON
class TestJsonExportMany:
    def test_all_invoices_written_and_roundtrip(self, mem_db, tmp_path):
        import json as _json
        from kse.infrastructure.export.exporters import json_export_many, json_to_invoices

        inv_svc, sub_svc, repos = _ctx(mem_db)
        a = _make_invoice(inv_svc, sub_svc, cur="300")
        b = _make_invoice(inv_svc, sub_svc, cur="700")
        entries = [(i, repos["invoices"].list_reading(i.id), repos["invoices"].list_charges(i.id)) for i in (a, b)]
        path = tmp_path / "many.json"
        json_export_many(entries, path)
        payload = _json.loads(path.read_text(encoding="utf-8"))
        assert len(payload["invoices"]) == 2               # used to silently write only the first
        back = json_to_invoices(payload)
        assert [x[0].invoice_no for x in back] == [a.invoice_no, b.invoice_no]

    def test_single_invoice_keeps_legacy_format(self, mem_db, tmp_path):
        import json as _json
        from kse.infrastructure.export.exporters import json_export_many, json_to_invoices

        inv_svc, sub_svc, repos = _ctx(mem_db)
        a = _make_invoice(inv_svc, sub_svc)
        path = tmp_path / "one.json"
        json_export_many([(a, repos["invoices"].list_reading(a.id), [])], path)
        payload = _json.loads(path.read_text(encoding="utf-8"))
        assert "invoice" in payload and "invoices" not in payload
        assert len(json_to_invoices(payload)) == 1

    def test_empty_rejected(self, tmp_path):
        from kse.infrastructure.export.exporters import json_export_many
        with pytest.raises(ValueError):
            json_export_many([], tmp_path / "x.json")


# ------------------------------------------------------------ performance layer
class TestSnapshotCache:
    def test_snapshot_reflects_every_kind_of_change(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        repo = repos["invoices"]
        base = len(repo.active_snapshot())
        a = _make_invoice(inv_svc, sub_svc)
        snap = repo.active_snapshot()
        assert len(snap) == base + 1                                   # insert
        repo.set_payment(a.id, a.total_due, dt.date.today(), "CASH", "")
        got = [i for i in repo.active_snapshot() if i.id == a.id][0]
        assert got.payment_status == PaymentStatus.PAID                # update
        inv_svc.recalculate(a.id)
        ids = {i.id for i in repo.active_snapshot()}
        assert a.id not in ids                                         # status change drops it
        mem_db.execute("DELETE FROM Invoices")                         # raw SQL on the same connection
        assert repo.active_snapshot() == []

    def test_snapshot_is_a_copy_and_reused_when_unchanged(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        repo = repos["invoices"]
        _make_invoice(inv_svc, sub_svc)
        s1 = repo.active_snapshot()
        s1.clear()                                   # caller mangling its copy must not poison the cache
        s2 = repo.active_snapshot()
        s3 = repo.active_snapshot()
        assert len(s2) >= 1 and s2[0] is s3[0]       # same objects -> no rebuild

    def test_other_connection_commit_invalidates(self, tmp_path):
        path = tmp_path / "shared.db"
        c1 = dbm.connect(path)
        repo = build_repositories(c1)["invoices"]
        assert repo.active_snapshot() == []
        c2 = dbm.connect(path)                       # a second process/connection
        c2.execute("INSERT INTO Invoices (invoice_no, issue_date, created_at, updated_at) "
                   "VALUES ('X-1', '2025-01-01', '2025-01-01T00:00:00', '2025-01-01T00:00:00')")
        c2.commit()
        assert [i.invoice_no for i in repo.active_snapshot()] == ["X-1"]
        c1.close(); c2.close()

    def test_stats_memo_never_returns_stale_data(self, mem_db):
        from kse.application.analytics import AnalyticsService
        inv_svc, sub_svc, repos = _ctx(mem_db)
        an = AnalyticsService(repos["invoices"])
        _make_invoice(inv_svc, sub_svc)
        first = an.dashboard()["total_invoices"]
        _make_invoice(inv_svc, sub_svc)
        assert an.dashboard()["total_invoices"] == first + 1
        lst = an._active()
        s_a = an.compute_stats(lst)
        assert an.compute_stats(lst) is s_a           # same list -> memo hit
        assert an.compute_stats(lst[:-1])["total_invoices"] == len(lst) - 1   # different list -> recomputed


class TestUniqueInvoiceNumber:
    def test_unique_index_blocks_duplicates(self, mem_db):
        from kse.domain.errors import DuplicateInvoiceNumberError
        inv_svc, sub_svc, repos = _ctx(mem_db)
        a = _make_invoice(inv_svc, sub_svc)
        calc, sched = inv_svc.calculate(CalculateInvoiceRequest(
            subscriber_type=SubscriberType.RESIDENTIAL, previous_reading="0", current_reading="10",
            previous_read_date=dt.date(2024, 2, 1), current_read_date=dt.date(2024, 3, 1)))
        with pytest.raises(DuplicateInvoiceNumberError):
            inv_svc.save_calculation(calc, sched, None, invoice_no=a.invoice_no)

    def test_migration_renumbers_existing_duplicates(self, tmp_path):
        path = tmp_path / "old.db"
        c = dbm.connect(path)
        c.execute("DROP INDEX ux_invoices_invoice_no")
        c.execute("DELETE FROM schema_migrations WHERE version=4")
        for _ in range(3):
            c.execute("INSERT INTO Invoices (invoice_no, issue_date, created_at, updated_at) "
                      "VALUES ('INV-2025-0001', '2025-01-01', '2025-01-01T00:00:00', '2025-01-01T00:00:00')")
        c.execute("INSERT INTO Invoices (invoice_no, issue_date, created_at, updated_at) VALUES ('', '2025-01-01', '2025-01-01T00:00:00', '2025-01-01T00:00:00')")
        c.execute("INSERT INTO Invoices (invoice_no, issue_date, created_at, updated_at) VALUES ('', '2025-01-01', '2025-01-01T00:00:00', '2025-01-01T00:00:00')")
        c.commit(); c.close()
        c = dbm.connect(path)                                   # upgrade must not crash
        nos = [r[0] for r in c.execute("SELECT invoice_no FROM Invoices ORDER BY id")]
        assert nos[0] == "INV-2025-0001"                        # oldest keeps its number
        assert nos[1:3] == ["INV-2025-0001-D2", "INV-2025-0001-D3"]
        assert nos[3:] == ["", ""]                              # empty numbers are not constrained
        assert c.execute("SELECT COUNT(*) FROM AuditLogs WHERE action='MIGRATION_RENUMBER'").fetchone()[0] == 2
        assert dbm.check_schema(c) == dbm.SCHEMA_VERSION
        c.close()

    def test_next_number_ignores_renumbered_suffixes(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        year = dt.date.today().year
        i = _make_invoice(inv_svc, sub_svc)
        mem_db.execute("UPDATE Invoices SET invoice_no=? WHERE id=?", (f"INV-{year}-0007-D2", i.id))
        assert inv_svc.next_invoice_no() == f"INV-{year}-0001"


# ------------------------------------------------------------ analytics accuracy
class TestAnalyticsUsesCurrentCharges:
    def _inv(self, inv_svc, sub_svc, debt):
        sub = sub_svc.find_or_create("ACC-D", name="Debtor")
        calc, sched = inv_svc.calculate(CalculateInvoiceRequest(
            subscriber_type=SubscriberType.RESIDENTIAL, previous_reading="0", current_reading="500",
            previous_read_date=dt.date(2024, 2, 1), current_read_date=dt.date(2024, 3, 1),
            previous_debt=Money.of(debt)))
        return inv_svc.save_calculation(calc, sched, sub, issue_date=dt.date(2024, 3, 1))

    def test_carried_debt_does_not_inflate_unit_cost_or_forecast(self, mem_db):
        from kse.application.analytics import AnalyticsService
        inv_svc, sub_svc, repos = _ctx(mem_db)
        mem_db.execute("DELETE FROM Invoices")                       # ignore the demo invoices
        an = AnalyticsService(repos["invoices"])
        self._inv(inv_svc, sub_svc, 0)
        clean = an.dashboard()
        mem_db.execute("DELETE FROM Invoices")
        self._inv(inv_svc, sub_svc, 100_000)                          # same consumption, big old debt
        with_debt = an.dashboard()
        assert with_debt["total_amount"].raw == clean["total_amount"].raw + Money.of(100_000).raw  # receivable includes it
        assert with_debt["cost_per_kwh"] == clean["cost_per_kwh"]      # price per kWh does not
        invs = an._active()
        assert an.forecast_next_month(invs)["amount"].raw == clean["total_amount"].raw
        assert an.monthly_table(invs, 12)[0]["avg_rate"] == clean["cost_per_kwh"]


class TestCountMatchesSearch:
    def test_count_with_query_and_status(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        a = _make_invoice(inv_svc, sub_svc, name="Zed Zulu")
        _make_invoice(inv_svc, sub_svc, name="Other", account="ACC-2")
        repo = repos["invoices"]
        for q in ("", "Zed", "zulu", "%", "ACC-1"):
            assert repo.count(query=q) == len(repo.search(query=q, limit=1000)), q
        repo.set_payment(a.id, a.total_due, dt.date.today(), "CASH", "")
        assert repo.count(query="Zed", payment_status=PaymentStatus.PAID) == 1
        assert repo.count(query="Zed", payment_status=PaymentStatus.UNPAID) == 0


# ------------------------------------------------------------ month filter / sorting wiring
class TestMonthFilter:
    @pytest.mark.parametrize("key,first,last", [
        ("2024-02", dt.date(2024, 2, 1), dt.date(2024, 2, 29)),     # leap year
        ("2023-02", dt.date(2023, 2, 1), dt.date(2023, 2, 28)),
        ("2024-12", dt.date(2024, 12, 1), dt.date(2024, 12, 31)),   # year rollover
        ("2024-01", dt.date(2024, 1, 1), dt.date(2024, 1, 31)),
    ])
    def test_bounds(self, key, first, last):
        from kse.presentation.filters import month_bounds
        assert month_bounds(key) == (first, last)

    @pytest.mark.parametrize("bad", [None, "", "2024", "2024-13", "2024-00", "abcd-ef", "2024-1-1"])
    def test_invalid_keys_mean_no_filter(self, bad):
        from kse.presentation.filters import month_bounds
        assert month_bounds(bad) == (None, None)

    def test_search_and_count_agree_for_a_month(self, mem_db):
        from kse.presentation.filters import month_bounds
        inv_svc, sub_svc, repos = _ctx(mem_db)
        repo = repos["invoices"]
        mem_db.execute("DELETE FROM Invoices")
        for day in (dt.date(2024, 2, 1), dt.date(2024, 2, 29), dt.date(2024, 3, 1), dt.date(2024, 1, 31)):
            sub = sub_svc.find_or_create("ACC-M", name="M")
            calc, sched = inv_svc.calculate(CalculateInvoiceRequest(
                subscriber_type=SubscriberType.RESIDENTIAL, previous_reading="0", current_reading="100",
                previous_read_date=dt.date(2024, 1, 1), current_read_date=dt.date(2024, 1, 20)))
            inv_svc.save_calculation(calc, sched, sub, issue_date=day)
        lo, hi = month_bounds("2024-02")
        got = repo.search(date_from=lo, date_to=hi, limit=100)
        assert sorted(i.issue_date for i in got) == [dt.date(2024, 2, 1), dt.date(2024, 2, 29)]   # edges included
        assert repo.count(date_from=lo, date_to=hi) == 2

    def test_order_by_is_a_whitelist(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        # hostile value must not reach SQL: falls back to the default order instead of erroring/injecting
        assert repos["invoices"].search(order_by="id; DROP TABLE Invoices;--", limit=5) is not None
        assert mem_db.execute("SELECT COUNT(*) FROM Invoices").fetchone()[0] > 0


class TestDashboardNeverStale:
    def test_payment_and_cancel_show_up_immediately(self, mem_db):
        from kse.application.analytics import AnalyticsService
        inv_svc, sub_svc, repos = _ctx(mem_db)
        an = AnalyticsService(repos["invoices"])
        a = _make_invoice(inv_svc, sub_svc, account="ACC-P")
        before = an.dashboard()
        assert an.dashboard() is before                                  # unchanged data -> cached result
        repos["invoices"].set_payment(a.id, a.total_due, dt.date.today(), "CASH", "")
        after = an.dashboard()
        assert after["total_paid"].raw == before["total_paid"].raw + a.total_due.raw    # payment visible at once
        inv_svc.recalculate(a.id)                                        # old invoice leaves the active set
        again = an.dashboard()
        assert again is not after and again["total_invoices"] == after["total_invoices"]  # replaced, not added
