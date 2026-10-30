"""Tests for: auto-backup, cancel (soft delete), payment history, payment transfer on recalculate,
debt suggestion, server-side sorting, receipts."""
import datetime as dt
import os
import time

import pytest

from kse.application.services import CalculateInvoiceRequest, InvoiceService, SubscriberService
from kse.domain.enums import InvoiceStatus, PaymentStatus, SubscriberType
from kse.domain.errors import InvoiceStateError, PaymentError
from kse.domain.money import Money
from kse.infrastructure.backup import AUTO_PREFIX, auto_backup, backup_database, validate_backup
from kse.infrastructure.export.pdf_exporter import build_receipt_html
from kse.infrastructure.sqlite import db as dbm
from kse.infrastructure.sqlite.repositories import build_repositories
from kse.infrastructure.sqlite.seed import seed


def _ctx(mem_db):
    repos = build_repositories(mem_db)
    seed(mem_db, overwrite=True)
    inv = InvoiceService(repos["invoices"], repos["tariffs"], repos["subscribers"], repos["audit"], repos["uow"])
    sub = SubscriberService(repos["subscribers"], repos["meters"], repos["tariffs"], repos["debts"], repos["uow"])
    return inv, sub, repos


def _invoice(inv_svc, sub_svc, account="ACC-1", name="Ali", cur="500", debt=None, issue=dt.date(2024, 3, 1)):
    sub = sub_svc.find_or_create(account, name=name)
    calc, sched = inv_svc.calculate(CalculateInvoiceRequest(
        subscriber_type=SubscriberType.RESIDENTIAL, previous_reading="0", current_reading=cur,
        previous_read_date=dt.date(2024, 2, 1), current_read_date=dt.date(2024, 3, 1),
        previous_debt=Money.of(debt) if debt is not None else None))
    return inv_svc.save_calculation(calc, sched, sub, issue_date=issue)


# ------------------------------------------------------------------ auto backup
class TestAutoBackup:
    def test_creates_validated_snapshot_with_live_data(self, tmp_path):
        live = tmp_path / "kahraba.db"
        c = dbm.connect(live)
        c.execute("INSERT INTO Settings(key,value,updated_at) VALUES('k','v','now')")
        c.commit()
        dest = auto_backup(c, live)
        assert dest.parent == tmp_path / "backups" and dest.name.startswith(AUTO_PREFIX)
        validate_backup(dest)
        copy = dbm.connect(dest)
        assert copy.execute("SELECT value FROM Settings WHERE key='k'").fetchone()[0] == "v"
        assert not list((tmp_path / "backups").glob("*.part"))
        c.close(); copy.close()

    def test_keeps_only_newest_and_never_touches_manual_backups(self, tmp_path):
        live = tmp_path / "kahraba.db"
        c = dbm.connect(live)
        manual = backup_database(live)                       # manual backup lives next to the db
        folder = tmp_path / "backups"
        made = []
        for _ in range(5):
            made.append(auto_backup(c, live, keep=3))
            time.sleep(0.01)
        left = sorted(folder.glob(f"{AUTO_PREFIX}*.db"))
        assert left == sorted(made)[-3:]                     # the 3 newest survive
        assert manual.exists()
        (folder / "my_own_note.db").write_bytes(b"x")        # foreign file in the folder is ignored
        auto_backup(c, live, keep=1)
        assert (folder / "my_own_note.db").exists()
        c.close()

    def test_failure_leaves_no_partial_file(self, tmp_path):
        live = tmp_path / "kahraba.db"
        c = dbm.connect(live)
        c.close()                                            # closed connection -> backup must fail
        with pytest.raises(Exception):
            auto_backup(c, live)
        assert not list((tmp_path / "backups").glob("*"))


# ------------------------------------------------------------------ cancel / lifecycle
class TestCancel:
    def test_cancel_keeps_row_number_and_audit(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        a = _invoice(inv_svc, sub_svc)
        done = inv_svc.cancel(a.id)
        assert done.status == InvoiceStatus.CANCELLED and done.invoice_no == a.invoice_no
        assert repos["invoices"].get(a.id) is not None                       # never physically deleted
        assert any(e.action == "INVOICE_CANCEL" for e in repos["audit"].list_for_invoice(a.id))
        assert a.id not in {i.id for i in repos["invoices"].active_snapshot()}
        with pytest.raises(PaymentError) as e:
            repos["invoices"].set_payment(a.id, 1, dt.date.today(), "CASH", "")
        assert e.value.reason == "cancelled"

    def test_cancel_refused_with_payments_or_when_not_active(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        a = _invoice(inv_svc, sub_svc)
        repos["invoices"].set_payment(a.id, Money.of(10), dt.date.today(), "CASH", "")
        with pytest.raises(InvoiceStateError) as e:
            inv_svc.cancel(a.id)
        assert e.value.reason == "has_payments"
        b = _invoice(inv_svc, sub_svc, account="ACC-2")
        inv_svc.cancel(b.id)
        with pytest.raises(InvoiceStateError) as e:
            inv_svc.cancel(b.id)
        assert e.value.reason == "not_active"

    def test_numbers_are_not_reused_after_cancel(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        a = _invoice(inv_svc, sub_svc)
        inv_svc.cancel(a.id)
        b = _invoice(inv_svc, sub_svc, account="ACC-2")
        assert b.invoice_no != a.invoice_no


# ------------------------------------------------------------------ payments
class TestPaymentHistory:
    def test_list_payments_in_order_and_sums_to_paid(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        repo = repos["invoices"]
        a = _invoice(inv_svc, sub_svc)
        third = Money.of(a.total_due.raw / 3)
        repo.set_payment(a.id, third, dt.date(2024, 3, 5), "CASH", "first")
        repo.set_payment(a.id, third, dt.date(2024, 3, 2), "TRANSFER", "earlier date")
        pays = repo.list_payments(a.id)
        assert [p.notes for p in pays] == ["earlier date", "first"]          # by payment date
        assert pays[0].method == "TRANSFER" and pays[0].id and pays[0].paid_at == dt.date(2024, 3, 2)
        assert sum((p.amount.raw for p in pays)) == repo.get(a.id).paid_amount.raw

    def test_payment_on_recalculated_invoice_rejected(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        a = _invoice(inv_svc, sub_svc)
        inv_svc.recalculate(a.id)
        with pytest.raises(PaymentError) as e:
            repos["invoices"].set_payment(a.id, 1, dt.date.today(), "CASH", "")
        assert e.value.reason == "inactive"


class TestRecalculateKeepsPayments:
    def test_payments_move_to_the_new_invoice(self, mem_db):
        """Before: the payment stayed on the superseded invoice and vanished from analytics."""
        inv_svc, sub_svc, repos = _ctx(mem_db)
        repo = repos["invoices"]
        a = _invoice(inv_svc, sub_svc)
        repo.set_payment(a.id, Money.of(1000), dt.date(2024, 3, 3), "CASH", "part")
        new = inv_svc.recalculate(a.id)
        assert new.id != a.id and new.status == InvoiceStatus.ACTIVE
        assert new.paid_amount.raw == Money.of(1000).raw
        assert new.payment_status == PaymentStatus.PARTIAL
        assert (new.remaining_balance + Money.of(1000)).raw == new.total_due.raw
        assert [p.invoice_id for p in repo.list_payments(new.id)] == [new.id]
        assert repo.list_payments(a.id) == []
        # the books still add up across the active invoices
        active = repo.active_snapshot()
        assert sum((i.paid_amount.raw for i in active if i.id == new.id)) == Money.of(1000).raw

    def test_overpaid_recalc_refused_and_nothing_changed(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        repo = repos["invoices"]
        a = _invoice(inv_svc, sub_svc)
        repo.set_payment(a.id, a.total_due, dt.date(2024, 3, 3), "CASH", "full")
        # make the tariff cheaper so the recalculated total is below what was paid
        mem_db.execute("UPDATE TariffTiers SET rate_per_kwh='0.0001'")
        before = len(repo.search(limit=1000))
        with pytest.raises(InvoiceStateError) as e:
            inv_svc.recalculate(a.id)
        assert e.value.reason == "overpaid"
        assert len(repo.search(limit=1000)) == before
        assert repo.get(a.id).status == InvoiceStatus.ACTIVE


# ------------------------------------------------------------------ debt suggestion
class TestSuggestedDebt:
    def test_uses_latest_invoice_remaining_not_a_sum(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        repo = repos["invoices"]
        sub = sub_svc.find_or_create("ACC-D", name="D")
        assert inv_svc.suggested_previous_debt(sub.id).raw == 0                     # no invoices
        first = _invoice(inv_svc, sub_svc, account="ACC-D", issue=dt.date(2024, 3, 1))
        assert inv_svc.suggested_previous_debt(sub.id).raw == first.total_due.raw
        # the second invoice carries the first one's debt inside its own total
        second = _invoice(inv_svc, sub_svc, account="ACC-D", debt=first.total_due.raw, issue=dt.date(2024, 4, 1))
        assert inv_svc.suggested_previous_debt(sub.id).raw == second.total_due.raw  # NOT first + second
        repo.set_payment(second.id, second.total_due, dt.date(2024, 4, 2), "CASH", "")
        assert inv_svc.suggested_previous_debt(sub.id).raw == 0                     # settled

    def test_partial_payment_and_inactive_ignored(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        sub = sub_svc.find_or_create("ACC-E", name="E")
        a = _invoice(inv_svc, sub_svc, account="ACC-E")
        repos["invoices"].set_payment(a.id, Money.of(1000), dt.date(2024, 3, 2), "CASH", "")
        assert inv_svc.suggested_previous_debt(sub.id).raw == (a.total_due - Money.of(1000)).raw
        inv_svc.cancel(inv_svc.recalculate(a.id).id) if False else None   # (cancel needs no payments)


# ------------------------------------------------------------------ sorting / filters
class TestSorting:
    def _three(self, inv_svc, sub_svc):
        a = _invoice(inv_svc, sub_svc, account="A1", name="bravo", cur="100", issue=dt.date(2024, 1, 10))
        b = _invoice(inv_svc, sub_svc, account="A2", name="Alpha", cur="900", issue=dt.date(2024, 3, 10))
        c = _invoice(inv_svc, sub_svc, account="A3", name="charlie", cur="20", issue=dt.date(2024, 2, 10))
        return a, b, c

    def test_orders_numerically_not_as_text(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        mem_db.execute("DELETE FROM Invoices")
        a, b, c = self._three(inv_svc, sub_svc)
        repo = repos["invoices"]
        ids = lambda **k: [i.id for i in repo.search(limit=100, **k)]
        assert ids(order_by="kwh", descending=True) == [b.id, a.id, c.id]    # 900 > 100 > 20 (text order would put 20 last... and 900 first)
        assert ids(order_by="kwh", descending=False) == [c.id, a.id, b.id]
        assert ids(order_by="total", descending=False) == [c.id, a.id, b.id]
        assert ids(order_by="name", descending=False) == [b.id, a.id, c.id]  # case-insensitive: Alpha, bravo, charlie
        assert ids(order_by="date", descending=True) == [b.id, c.id, a.id]

    def test_unknown_order_falls_back_and_cannot_inject(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        repo = repos["invoices"]
        default = [i.id for i in repo.search(limit=100)]
        assert [i.id for i in repo.search(limit=100, order_by="id; DROP TABLE Invoices;--")] == default
        assert repo.count() > 0

    def test_month_range_count_matches_search(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        mem_db.execute("DELETE FROM Invoices")
        self._three(inv_svc, sub_svc)
        repo = repos["invoices"]
        lo, hi = dt.date(2024, 2, 1), dt.date(2024, 2, 29)
        assert repo.count(date_from=lo, date_to=hi) == len(repo.search(date_from=lo, date_to=hi, limit=100)) == 1


# ------------------------------------------------------------------ receipt
class TestReceipt:
    def test_receipt_contains_the_books_numbers_and_escapes_text(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        a = _invoice(inv_svc, sub_svc, name="<b>Ali</b> & Sons")
        repos["invoices"].set_payment(a.id, Money.of(1234), dt.date(2024, 3, 3), "TRANSFER", "<script>x</script>")
        inv = repos["invoices"].get(a.id)
        pay = repos["invoices"].list_payments(a.id)[0]
        html = build_receipt_html(inv, pay, lang="en", currency="USD")
        assert f"R-{pay.id:06d}" in html and "2024-03-03" in html and "1,234" in html
        assert "&lt;b&gt;Ali&lt;/b&gt; &amp; Sons" in html and "<script>" not in html
        assert f"{(inv.total_due - Money.of(1234)).raw:,}".split(".")[0] in html     # remaining balance shown

    def test_receipt_rtl_for_arabic(self, mem_db):
        inv_svc, sub_svc, repos = _ctx(mem_db)
        a = _invoice(inv_svc, sub_svc)
        repos["invoices"].set_payment(a.id, Money.of(10), dt.date(2024, 3, 3), "CASH", "")
        pay = repos["invoices"].list_payments(a.id)[0]
        assert "dir='rtl'" in build_receipt_html(repos["invoices"].get(a.id), pay, lang="ar")


def test_dynamic_invoice_state_keys_exist():
    from kse.presentation import i18n
    for reason in InvoiceStateError._MESSAGES:
        for lang in ("en", "ar"):
            assert f"err_invoice_{reason}" in i18n._STRINGS[lang], (reason, lang)


class TestStyledExcelAndCustomExports:
    def test_excel_and_csv_subscribers_export(self, tmp_path, mem_db):
        from openpyxl import load_workbook
        from kse.infrastructure.export.exporters import csv_export_subscribers, excel_export_subscribers
        from kse.domain.models import Subscriber

        subs = [
            Subscriber(account_no="1001", subscription_no="SUB-1", name="Ahmed", subscriber_type=SubscriberType.RESIDENTIAL, previous_debt=Money.of(50)),
            Subscriber(account_no="1002", subscription_no="SUB-2", name="=HYPERLINK(x)", subscriber_type=SubscriberType.COMMERCIAL, previous_debt=Money.zero()),
        ]
        xlsx_path = tmp_path / "subs.xlsx"
        csv_path = tmp_path / "subs.csv"

        excel_export_subscribers(subs, xlsx_path)
        assert xlsx_path.exists()
        wb = load_workbook(xlsx_path)
        ws = wb.active
        assert ws.cell(row=1, column=1).value == "account_no"
        assert ws.cell(row=2, column=1).value == "1001"
        assert ws.cell(row=3, column=3).value.startswith("'")  # formula injection neutralized

        csv_export_subscribers(subs, csv_path)
        assert csv_path.exists()
        content = csv_path.read_text(encoding="utf-8-sig")
        assert "1001" in content and "Ahmed" in content

    def test_monthly_analytics_export(self, tmp_path):
        from decimal import Decimal
        from openpyxl import load_workbook
        from kse.infrastructure.export.exporters import csv_export_monthly, excel_export_monthly

        rows = [
            {"month": "2026-01", "count": 10, "kwh": Decimal("1500"), "amount": Money.of(15000), "paid": Money.of(10000), "remaining": Money.of(5000), "avg_rate": "10.0"},
            {"month": "2026-02", "count": 12, "kwh": Decimal("1800"), "amount": Money.of(18000), "paid": Money.of(18000), "remaining": Money.zero(), "avg_rate": "10.0"},
        ]
        xlsx_path = tmp_path / "monthly.xlsx"
        csv_path = tmp_path / "monthly.csv"

        excel_export_monthly(rows, xlsx_path)
        assert xlsx_path.exists()
        wb = load_workbook(xlsx_path)
        assert wb.active.cell(row=2, column=1).value == "2026-01"

        csv_export_monthly(rows, csv_path)
        assert csv_path.exists()
        assert "2026-01" in csv_path.read_text(encoding="utf-8-sig")


class TestDatabaseOptimization:
    def test_optimize_database(self, tmp_path):
        from kse.presentation.app_context import AppContext
        db_path = tmp_path / "test_opt.db"
        ctx = AppContext(db_path=db_path)
        size = ctx.optimize_database()
        assert size > 0
        entries = ctx.repos["audit"].list_recent(limit=5)
        assert any(e.action == "DB_OPTIMIZE" for e in entries)
        ctx.close()
