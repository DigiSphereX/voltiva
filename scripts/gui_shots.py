"""Render the current GUI (pages + key dialogs) to PNGs for visual inspection."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from kse.presentation import theme
from kse.presentation.app_context import AppContext
from kse.presentation.main_window import MainWindow
from kse.presentation.pages import import_invoice, subscribers, tariffs

import tempfile

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(OUT, exist_ok=True)


def _grab(widget, name: str) -> None:
    widget.grab().save(os.path.join(OUT, name))
    print("saved", name)


def _dialogs(ctx, win, app, tag: str) -> None:
    for name, dlg in [
        ("tariff", tariffs.TariffDialog(ctx, None, win)),
        ("subscriber", subscribers.SubscriberDialog(ctx, None, win)),
        ("import", import_invoice.ImportInvoiceDialog(ctx, win)),
    ]:
        dlg.show()
        app.processEvents()
        _grab(dlg, f"dialog-{name}-{tag}.png")
        dlg.close()

    nb = tariffs.TariffDialog(ctx, None, win)
    nb.resize(620, 700)
    nb.show()
    app.processEvents()
    nb.grab().save(os.path.join(OUT, f"dialog-tariff-narrow-{tag}.png"))
    print("saved", f"dialog-tariff-narrow-{tag}.png")
    nb.close()


def main() -> int:
    from kse.infrastructure.sqlite.seed import seed

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    theme.register_fonts()
    app.setFont(QFont("Cairo", 10))

    db = os.path.join(tempfile.mkdtemp(), "shot.db")
    ctx = AppContext(db, lang="ar")
    seed(ctx.conn, overwrite=True)
    ctx.conn.commit()

    win = MainWindow(ctx)
    win.resize(1180, 760)
    win.show()

    pages_arg = sys.argv[1:]
    pages = pages_arg or [
        "dashboard", "new_invoice", "invoices", "verify", "review", "analytics",
        "tariffs", "subscribers", "settings"]
    run_dialogs = not pages_arg
    for theme_name in ("dark", "light"):
        theme.apply(app, theme_name)
        app.processEvents()
        for key in pages:
            win.show_page(key)
            app.processEvents()
            win.grab().save(os.path.join(OUT, f"{key}-{theme_name}.png"))
            print("saved", key, theme_name)
        if run_dialogs:
            _dialogs(ctx, win, app, theme_name)

        win.show_page("new_invoice")
        win.resize(900, 560)
        app.processEvents()
        win.grab().save(os.path.join(OUT, f"new_invoice-narrow-{theme_name}.png"))
        print("saved", f"new_invoice-narrow-{theme_name}.png")
        win.resize(1180, 760)
        app.processEvents()

    ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())