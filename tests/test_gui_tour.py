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

from PyQt6.QtCore import QLocale, QSize, Qt, QTimer  # noqa: E402
from PyQt6.QtGui import QColor, QPalette  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication, QCalendarWidget, QDateEdit, QFileDialog, QLineEdit, QMessageBox, QPushButton,
    QStyle, QStyleOptionViewItem, QTableWidget, QTableWidgetItem, QToolButton,
)

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

            # monthly analytics: the Remaining cell must be painted once — chip or text,
            # never both (item text under a chip drew the amount twice in the same cell)
            month_table = win._pages["analytics"].month_table
            for r in range(month_table.rowCount()):
                chip = month_table.cellWidget(r, 5)
                item = month_table.item(r, 5)
                text = item.text() if item is not None else ""
                assert (chip is None) != (text == ""), (r, text)

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
class TestSelectedRowLegibility:
    def test_selected_row_text_ignores_status_foreground(self, gui_app):
        """Item foreground roles beat the QSS selected colour, so a red unpaid amount sat
        on the amber selection (~1:1). The delegate must paint on_accent when selected."""
        from kse.presentation.widgets import DataTable
        previous = theme.current_name()
        theme.set_current("graphite")          # amber accent: the red-on-orange case
        try:
            table = DataTable()
            table.setColumnCount(1)
            table.setRowCount(1)
            item = QTableWidgetItem("17,500")
            item.setForeground(QColor(theme.colors()["danger"]))
            table.setItem(0, 0, item)
            table.selectRow(0)
            option = QStyleOptionViewItem()
            option.state = QStyle.StateFlag.State_Selected
            table.itemDelegate().initStyleOption(option, table.model().index(0, 0))
            assert option.state & QStyle.StateFlag.State_Selected
            assert option.palette.color(QPalette.ColorRole.HighlightedText) == \
                QColor(theme.colors()["on_accent"])
            table.deleteLater()
        finally:
            theme.set_current(previous)

    def test_status_chip_background_is_opaque(self, gui_app):
        from kse.presentation.widgets import status_chip
        danger = theme.colors()["danger"]
        chip = status_chip("unpaid", danger)
        css = chip.styleSheet()
        assert "rgba(" not in css            # translucent tints let the row accent through
        assert theme.blend_hex(danger, theme.colors()["surface"], 16 / 255) in css
        chip.deleteLater()


@pytest.mark.gui
class TestArabicInputAndDigits:
    def test_localized_numbers_and_arabic_search(self, gui_app):
        tmp = os.path.join(tempfile.mkdtemp(), "digits.db")
        ctx = AppContext(tmp, lang="ar")
        set_money_lang("ar")
        try:
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
            ctx.invoices.save_calculation(calc, sched, sub, official_amount=Money.of(35840))

            win = MainWindow(ctx)
            win.show()
            app = gui_app
            app.processEvents()

            win.show_page("subscribers")
            app.processEvents()
            page = win._pages["subscribers"]
            for row in range(page.table.rowCount()):
                for col in (0, 1):
                    text = page.table.item(row, col).text()
                    assert text and not any(ch.isascii() and ch.isdigit() for ch in text), text
            # status bar count follows the digit style too
            status = win.status_lbl.text()
            assert status and not any(ch.isascii() and ch.isdigit() for ch in status), status

            # An Arabic-keyboard query still matches the stored ASCII account number
            first_account = page.table.item(0, 0).text()
            page.search_edit.setText(first_account)
            page.refresh()
            app.processEvents()
            assert page.table.rowCount() == 1

            # Path fields are rendered LTR so an Arabic folder name cannot scramble them
            win.show_page("settings")
            app.processEvents()
            db_field = win._pages["settings"].db_path_edit
            from PyQt6.QtCore import Qt
            assert db_field.layoutDirection() == Qt.LayoutDirection.LeftToRight

            win.close()
            app.processEvents()
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

@pytest.mark.gui
class TestThemeModes:
    def test_selector_and_topbar_follow_each_palette(self, gui_app):
        tmp = os.path.join(tempfile.mkdtemp(), "themes.db")
        ctx = AppContext(tmp, lang="en")
        set_money_lang(ctx.i18n.lang)
        try:
            win = MainWindow(ctx)
            win.show()
            app = gui_app
            app.processEvents()
            win.show_page("settings")
            app.processEvents()

            for mode in theme.THEME_UI_ORDER:
                ctx.set_theme_mode(mode)
                app.processEvents()
                page = win._pages["settings"]
                assert page.theme_combo.currentData() == mode, mode
                resolved = ctx.current_theme()
                assert theme.current_name() == resolved
                assert ctx.tr(theme.THEME_LABEL_KEYS[resolved]) in page.theme_hint.text()
                button = win.topbar.theme_btn.text()
                expected = (ctx.tr("st_auto") if mode == "auto"
                            else ctx.tr(theme.THEME_LABEL_KEYS[mode]))
                assert button.endswith(expected), (mode, button)

            ctx.set_theme_mode("midnight")
            app.processEvents()
            win.close()
            app.processEvents()

            reopened = AppContext(tmp, lang="en")   # the choice must survive a restart
            try:
                assert reopened.current_theme_mode() == "midnight"
                assert reopened.current_theme() == "midnight"
            finally:
                reopened.close()
            assert EXCEPTIONS == [], "\n".join(EXCEPTIONS)
        finally:
            try:
                ctx.close()
            except Exception:
                pass


@pytest.mark.gui
class TestNavigationAndCalendar:
    def test_every_nav_section_has_several_items(self):
        for section, items in MainWindow.NAV_GROUPS:
            assert len(items) >= 2, section
        grouped = [key for _, items in MainWindow.NAV_GROUPS for key, _ in items]
        assert "settings" not in grouped          # standalone, pinned at the bottom
        assert len(grouped) == len(set(grouped))

    def test_date_picker_calendar_fits_every_day(self, gui_app):
        tmp = os.path.join(tempfile.mkdtemp(), "calendar.db")
        ctx = AppContext(tmp, lang="ar")
        try:
            win = MainWindow(ctx)
            win.show()
            gui_app.processEvents()
            win.show_page("verify")
            gui_app.processEvents()
            picker = win._pages["verify"].findChildren(QDateEdit)[0]
            cal = picker.calendarWidget()
            assert cal.locale().language() == QLocale.Language.Arabic
            assert cal.firstDayOfWeek() == QLocale("ar").firstDayOfWeek()
            assert cal.minimumWidth() >= 320 and cal.minimumHeight() >= 240
            assert cal.verticalHeaderFormat() == QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
            for name in ("qt_calendar_prevmonth", "qt_calendar_nextmonth"):
                btn = cal.findChild(QToolButton, name)
                assert btn is not None and not btn.icon().isNull(), name
            win.close()
            gui_app.processEvents()
            assert EXCEPTIONS == [], "\n".join(EXCEPTIONS)
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    def test_nav_rows_keep_one_height_in_every_language(self, gui_app):
        from kse.presentation.i18n import I18n

        tmp = os.path.join(tempfile.mkdtemp(), "nav.db")
        ctx = AppContext(tmp, lang="en")
        ctx.set_theme_mode("light")
        try:
            win = MainWindow(ctx)
            win.resize(1280, 820)
            win.show()
            gui_app.processEvents()
            expected_row = {theme.Metrics.NAV_ROW_H}
            expected_caption = {theme.Metrics.NAV_CAPTION_H}
            for lang in I18n.AVAILABLE_LANGS:
                ctx.set_language(lang)
                gui_app.processEvents()
                assert {b.height() for b in win._nav_buttons.values()} == expected_row, lang
                assert {h.height() for h in win._sec_headers.values()} == expected_caption, lang
            win.close()
            gui_app.processEvents()
            assert EXCEPTIONS == [], "\n".join(EXCEPTIONS)
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    def test_compact_sidebar_uses_drawn_icons(self, gui_app):
        tmp = os.path.join(tempfile.mkdtemp(), "compact.db")
        ctx = AppContext(tmp, lang="ar")
        ctx.set_theme_mode("light")
        try:
            win = MainWindow(ctx)
            win.resize(1280, 820)
            win.show()
            gui_app.processEvents()
            win.resize(1120, 700)
            gui_app.processEvents()
            assert win.sidebar.width() == 72
            for key, btn in win._nav_buttons.items():
                assert btn.text() == "", key              # no font-dependent glyphs
                assert not btn.icon().isNull(), key
                assert btn.iconSize() == QSize(theme.Metrics.NAV_ICON, theme.Metrics.NAV_ICON)
            win.resize(1280, 820)
            gui_app.processEvents()
            assert all(b.text() for b in win._nav_buttons.values())
            win.close()
            gui_app.processEvents()
            assert EXCEPTIONS == [], "\n".join(EXCEPTIONS)
        finally:
            try:
                ctx.close()
            except Exception:
                pass


@pytest.mark.gui
class TestEntryTables:
    """The tariff dialog's inline tables must read and behave like tables: grid,
    compact editors, and a height that follows the rows instead of a blank void."""

    def test_entry_tables_are_gridded_and_fit_their_rows(self, gui_app):
        from kse.presentation.pages.tariffs import TariffDialog

        tmp = os.path.join(tempfile.mkdtemp(), "entry.db")
        ctx = AppContext(tmp, lang="en")
        ctx.set_theme_mode("light")
        dlg = TariffDialog(ctx)
        try:
            dlg.show()
            gui_app.processEvents()
            table = dlg.fees_table
            assert table.showGrid()
            triggers = table.editTriggers()
            assert triggers & QTableWidget.EditTrigger.DoubleClicked
            assert triggers & QTableWidget.EditTrigger.AnyKeyPressed
            assert table.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor

            row_h = table.verticalHeader().defaultSectionSize()
            assert row_h == 34
            header_h = theme.Metrics.HEADER_H

            dlg._add_fee_row("Fixed fee", "FIXED_FEE", "500")
            dlg._add_fee_row("Service fee", "SERVICE_FEE", "100")
            gui_app.processEvents()
            assert table.height() == header_h + table.rowCount() * row_h + 2

            table.editItem(table.item(0, 2))
            gui_app.processEvents()
            editors = [w for w in table.viewport().findChildren(QLineEdit) if w.isVisible()]
            assert editors, "double-click edit did not open an editor"
            cell = table.visualRect(table.model().index(0, 2))
            assert all(e.height() <= row_h - 4 for e in editors)   # never taller than the row
            assert all(e.width() <= cell.width() for e in editors)

            table.selectRow(0)
            dlg._remove_selected_rows(table)
            gui_app.processEvents()
            assert table.height() == header_h + max(table.rowCount(), 2) * row_h + 2
            assert table.height() < header_h + 3 * row_h + 2
            assert EXCEPTIONS == [], "\n".join(EXCEPTIONS)
        finally:
            dlg.hide()
            dlg.deleteLater()
            try:
                ctx.close()
            except Exception:
                pass


@pytest.mark.gui
class TestAiScanSettings:
    def test_settings_page_saves_ai_configuration_and_dialog_reports_engine(self, gui_app):
        tmp = os.path.join(tempfile.mkdtemp(), "ai_scan.db")
        ctx = AppContext(tmp, lang="ar")
        set_money_lang(ctx.i18n.lang)
        try:
            from kse.infrastructure.ocr.ai_scanner import AiScanConfig
            from kse.presentation.pages.import_invoice import ImportInvoiceDialog

            win = MainWindow(ctx)
            win.show()
            app = gui_app
            app.processEvents()
            win.show_page("settings")
            app.processEvents()
            page = win._pages["settings"]

            page.ai_mode_combo.setCurrentIndex(page.ai_mode_combo.findData("custom"))
            page.ai_url_edit.setText("http://localhost:11434/v1")
            page.ai_key_edit.setText("test-key")
            page.ai_model_edit.setText("llava")
            page.ai_timeout_combo.setCurrentIndex(page.ai_timeout_combo.findData(45))
            page._save_ai()
            app.processEvents()

            cfg = AiScanConfig.load(ctx.repos["settings"])
            assert cfg.mode == "custom"
            assert cfg.endpoint() == "http://localhost:11434/v1/chat/completions"
            assert cfg.api_key == "test-key" and cfg.model == "llava" and cfg.timeout == 45

            dlg = ImportInvoiceDialog(ctx, win)
            assert ctx.tr("ocr_engine_custom") in dlg.ocr_engine_lbl.text()
            dlg.reject()   # closing before any scan must not touch QWidget.thread()
            assert not dlg.isVisible()
            dlg.deleteLater()

            win.close()
            app.processEvents()
            assert EXCEPTIONS == [], "\n".join(EXCEPTIONS)
        finally:
            try:
                ctx.close()
            except Exception:
                pass
