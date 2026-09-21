"""Offscreen GUI smoke: pages build/refresh, theme switch, review page renders."""
import os
import shutil
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import tempfile
from PyQt6.QtWidgets import QApplication

from kse.presentation.app_context import AppContext
from kse.presentation.main_window import MainWindow
from kse.presentation import theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    theme.register_fonts()

    tmp = os.path.join(tempfile.mkdtemp(), "smoke.db")

    def _cleanup():
        shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)

    try:
        ctx = AppContext(tmp, lang="ar")
        ctx.set_theme_mode("light")
        theme.apply(app, ctx.current_theme())
        win = MainWindow(ctx)
        win.resize(1180, 760)
        win.show()

        for key in ("dashboard", "new_invoice", "invoices", "verify", "review",
                    "analytics", "tariffs", "subscribers", "settings"):
            win.show_page(key)
            assert win.stack.currentWidget() is win._pages[key], key

        # theme switching round-trip (light is pinned explicitly)
        assert ctx.current_theme() == "light"
        ctx.set_theme("dark")
        assert theme.colors()["bg"].lower() == "#0b0f1a"
        win.show_page("review")
        ctx.set_theme("light")
        assert theme.colors()["bg"].lower() == "#f4f7fc"

        # nav label present
        assert win._nav_buttons["review"].text() == "المراجعة الشهرية"
        # i18n format smoke
        assert "910931194807" in ctx.tr("ocr_account_mismatch", account="12345", known="910931194807")

        # OCR account-mismatch warning (dialog logic, DB-backed)
        import datetime as dt
        from types import SimpleNamespace
        from kse.domain.models import Invoice
        from kse.presentation.pages.import_invoice import ImportInvoiceDialog

        inv = Invoice(invoice_no="T1", account_no="910931194807",
                      issue_date=dt.date(2026, 8, 15), total_due=__import__(
                          "kse.domain.money", fromlist=["Money"]).Money.of("10000"))
        ctx.repos["invoices"].save(inv, None, [])
        fake = SimpleNamespace(app=ctx, tr=ctx.tr)
        assert ImportInvoiceDialog._account_mismatch(fake, "910931194807") == ""   # known → silent
        warn = ImportInvoiceDialog._account_mismatch(fake, "810931194807")        # misread → warn
        assert warn and "810931194807" in warn, warn
        assert ImportInvoiceDialog._account_mismatch(fake, "123") == ""           # too short → silent

        win.close()
    finally:
        try:
            ctx.close()
        except Exception:
            pass
    _cleanup()
    print("GUI smoke OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())