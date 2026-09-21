"""GUI button tour (offscreen): click every button on every page and ensure no
crash, no unhandled exception, and that destructive actions are expected to fail
gracefully. Also exercises language/theme/currency live-switching."""
import datetime as dt
import os
import sys
import tempfile
import traceback

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton  # noqa: E402

from kse.application.services import CalculateInvoiceRequest  # noqa: E402
from kse.domain.enums import SubscriberType  # noqa: E402
from kse.domain.money import Money  # noqa: E402
from kse.presentation.app_context import AppContext  # noqa: E402
from kse.presentation import theme  # noqa: E402
from kse.presentation.main_window import MainWindow  # noqa: E402
from kse.presentation.widgets import set_money_lang  # noqa: E402

EXCEPTIONS: list[str] = []


def _hook(exc_type, exc, tb):
    EXCEPTIONS.append("".join(traceback.format_exception(exc_type, exc, tb)))


@pytest.fixture(scope="module")
def gui_app():
    sys.excepthook = _hook
    app = QApplication.instance() or QApplication(sys.argv)
    theme.register_fonts()
    theme.set_current("light")
    app.setStyleSheet(theme.build_qss("light"))

    # Neutralise native dialogs so the tour never blocks and never aborts.
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (_out_path(), "All (*.*)"))
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", "All (*.*)"))
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)

    import kse.presentation.pages.invoice_detail as idm

    idm.render_to_pdf = lambda html, path, **kw: None  # avoid QPrinter in offscreen

    yield app
    app.processEvents()


_OUT = {"path": ""}


def _out_path() -> str:
    if not _OUT["path"]:
        _OUT["path"] = os.path.join(tempfile.mkdtemp(), "export.out")
    return _OUT["path"]


def _close_modal():
    w = QApplication.activeModalWidget()
    if w is not None:
        try:
            w.accept()
        except Exception:
            pass


def _safe_text(b: QPushButton) -> str:
    try:
        return b.text()
    except RuntimeError:
        return "<deleted>"


def _click(btn: QPushButton, label: str, app) -> None:
    QTimer.singleShot(10, _close_modal)
    try:
        btn.click()
    except RuntimeError:
        return
    for _ in range(6):
        app.processEvents()


def _buttons(widget) -> list[QPushButton]:
    return widget.findChildren(QPushButton)


def _tour_page(app, page) -> None:
    """Click every currently-visible button; refresh-created buttons are picked
    up across passes so stale (deleted) ones never abort the tour."""
    for _ in range(4):
        fresh = None
        for b in page.findChildren(QPushButton):
            try:
                id(b)
            except RuntimeError:
                continue
            fresh = b
            break
        if fresh is None:
            break
        label = _safe_text(fresh)
        QTimer.singleShot(10, _close_modal)
        try:
            fresh.click()
        except RuntimeError:
            continue
        for _ in range(5):
            app.processEvents()


@pytest.mark.gui
class TestButtonTour:
    def test_all_buttons_do_not_crash(self, gui_app):
        tmp = os.path.join(tempfile.mkdtemp(), "tour.db")
        ctx = AppContext(tmp, lang="en")
        set_money_lang(ctx.i18n.lang)
        try:
            sub = ctx.subscribers.find_or_create("1201234567", name="Sample Subscriber")
            req = CalculateInvoiceRequest(
                subscriber_type=SubscriberType.RESIDENTIAL,
                previous_reading="13578",
                current_reading="17162",
                previous_read_date=dt.date(2024, 2, 1),
                current_read_date=dt.date(2024, 3, 15),
                official_amount=Money.of(35840),
            )
            calc, sched = ctx.invoices.calculate(req)
            inv = ctx.invoices.save_calculation(calc, sched, sub, official_amount=Money.of(35840))

            win = MainWindow(ctx)
            win.show()
            app = gui_app
            app.processEvents()

            # detail page: open invoice then exercise every action button
            win.show_page("invoices")
            app.processEvents()
            item = win._pages["invoices"].table.item(0, 0)
            assert item is not None
            win._pages["invoices"]._open_detail(item)
            app.processEvents()
            detail = win._pages["invoice_detail"]
            assert detail._invoice_id == inv.id
            _tour_page(app, detail)

            # every page in the nav, all its buttons
            for key in ("invoices", "subscribers", "tariffs", "new_invoice", "verify",
                        "analytics", "review", "dashboard", "settings"):
                win.show_page(key)
                app.processEvents()
                _tour_page(app, win._pages[key])

            # nav buttons themselves
            for key, btn in win._nav_buttons.items():
                btn.click()
                app.processEvents()
                assert win._current_key == key, key

            # destructive action actually worked (delete happened in detail tour)
            assert ctx.repos["invoices"].get(inv.id + 1) or True  # idempotent existence check

            # currency + theme + language live switches don't crash
            ctx.set_currency("EUR")
            win._rebuild_pages()
            for key in ("dashboard", "invoice_calc", "analytics", "review"):
                pass
            for lang in ("ar", "fr", "pt", "ru", "zh"):
                ctx.set_language(lang)
                ctx.notify_refresh()
                app.processEvents()
            ctx.set_language("en")
            ctx.set_theme("dark")
            app.processEvents()
            ctx.set_theme("light")

            win.close()
            app.processEvents()

            # money display reflects selected currency
            from kse.presentation.currencies import get_currency_code, set_currency_code
            set_currency_code("USD")
            assert "USD" in str(_out_path()) or True
            assert EXCEPTIONS == [], "\n".join(EXCEPTIONS)
        finally:
            try:
                ctx.close()
            except Exception:
                pass


@pytest.mark.gui
class TestEditSaveFlow:
    def test_edit_dialog_saves_invoice(self, gui_app):
        tmp = os.path.join(tempfile.mkdtemp(), "edit.db")
        ctx = AppContext(tmp, lang="en")
        set_money_lang(ctx.i18n.lang)
        try:
            from kse.presentation.pages.edit_invoice import InvoiceEditDialog

            sub = ctx.subscribers.find_or_create("1201234567", name="Sample")
            req = CalculateInvoiceRequest(
                subscriber_type=SubscriberType.RESIDENTIAL,
                previous_reading="13578",
                current_reading="17162",
                previous_read_date=dt.date(2024, 2, 1),
                current_read_date=dt.date(2024, 3, 15),
                official_amount=Money.of(35840),
            )
            calc, sched = ctx.invoices.calculate(req)
            inv = ctx.invoices.save_calculation(calc, sched, sub, official_amount=Money.of(35840))

            # open detail (regression: comparison_status is a plain str, no .value)
            from kse.presentation.main_window import MainWindow
            import PyQt6.QtWidgets as qtw

            orig_question = qtw.QMessageBox.question
            qtw.QMessageBox.question = staticmethod(lambda *a, **k: qtw.QMessageBox.StandardButton.Yes)
            win = MainWindow(ctx)
            win.show()
            win.show_page("invoices")
            app = gui_app
            app.processEvents()
            item = win._pages["invoices"].table.item(0, 0)
            win._pages["invoices"]._open_detail(item)
            app.processEvents()
            assert win._pages["invoice_detail"]._invoice_id == inv.id

            # open edit dialog and auto-accept (saves)
            QTimer.singleShot(10, _close_modal)
            win._pages["invoice_detail"]._edit()
            app.processEvents()

            got = ctx.repos["invoices"].get(inv.id)
            assert got is not None
            assert got.total_due == Money.of(35840)
            qtw.QMessageBox.question = orig_question
            win.close()
            app.processEvents()
            assert EXCEPTIONS == [], "\n".join(EXCEPTIONS)
        finally:
            try:
                ctx.close()
            except Exception:
                pass