"""Geometry audit: report widgets smaller than their sizeHint (shrunk/clipped)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QLineEdit, QPushButton, QComboBox, QDateEdit, QTableWidget

from kse.presentation import theme
from kse.presentation.app_context import AppContext
from kse.presentation.main_window import MainWindow
from kse.presentation.pages import subscribers, tariffs

import tempfile

ROOT_WIDGETS = (QLineEdit, QPushButton, QComboBox, QDateEdit, QTableWidget)


def audit(widget, label, report):
    for w in widget.findChildren(ROOT_WIDGETS):
        if isinstance(w, QTableWidget):
            continue
        if not w.isVisible():
            continue
        sh = w.sizeHint()
        if w.height() < sh.height() - 2 or w.width() < sh.width() - 8:
            report.append((label, type(w).__name__, w.text()[:22], w.width(), sh.width(), w.height(), sh.height()))
    for t in widget.findChildren(QTableWidget):
        if not t.isVisible():
            continue
        for r in range(t.rowCount()):
            cw = t.cellWidget(r, t.columnCount() - 1)
            if cw is not None and t.rowHeight(r) < cw.sizeHint().height() - 1:
                report.append((label, "cellWidget-row", type(cw).__name__, r, t.rowHeight(r), cw.sizeHint().height()))


def main() -> int:
    from kse.infrastructure.sqlite.seed import seed

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    theme.register_fonts()
    app.setFont(QFont("Cairo", 10))

    db = os.path.join(tempfile.mkdtemp(), "audit.db")
    ctx = AppContext(db, lang="ar")
    seed(ctx.conn, overwrite=True)
    ctx.conn.commit()
    theme.apply(app, "dark")
    win = MainWindow(ctx)
    win.resize(1180, 760)
    win.show()

    report = []
    for key in ["dashboard", "new_invoice", "invoices", "review", "analytics",
                "tariffs", "subscribers", "settings"]:
        win.show_page(key)
        app.processEvents()
        audit(win._pages[key], key, report)

    for name, dlg in [
        ("dialog-tariff", tariffs.TariffDialog(ctx, None, win)),
        ("dialog-subscriber", subscribers.SubscriberDialog(ctx, None, win)),
    ]:
        dlg.show()
        app.processEvents()
        audit(dlg, name, report)
        dlg.close()
        app.processEvents()

    win.resize(900, 560)
    win.show_page("new_invoice")
    app.processEvents()
    audit(win._pages["new_invoice"], "new_invoice-narrow", report)

    if not report:
        print("OK: no shrunk widgets")
    else:
        print("REPORT (label, type, text, w, w_sh, h, h_sh):")
        for row in report:
            print("  ", row)
    ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())