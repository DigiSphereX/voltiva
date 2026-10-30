"""Regenerate the README screenshots (all pages + dialogs, light and dark, English or Arabic).

    python scripts/make_screenshots.py                     # English  -> ScreenShot/<page>.png, <page>-dark.png
    python scripts/make_screenshots.py --lang ar           # Arabic   -> ScreenShot/<page>-ar.png, <page>-ar-dark.png
    python scripts/make_screenshots.py --out some/folder   # another output folder
    python scripts/make_screenshots.py --offscreen         # headless (CI); fonts look slightly different

Uses the NATIVE platform renderer by default (the offscreen plugin distorts fonts). A temporary
database is filled with ~a year of fictional invoices (some paid, some partial) so the dashboard,
analytics charts and tables show realistic content instead of four rows.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

PAGES = ["dashboard", "new_invoice", "invoices", "verify", "review", "analytics",
         "tariffs", "subscribers", "settings"]
SETTLE = float(os.environ.get("VOLTIVA_SHOT_SETTLE", "0.35"))


def enrich(ctx) -> int:
    """Add a year of fictional invoices for the demo subscribers; returns how many were created."""
    from kse.application.services import CalculateInvoiceRequest
    from kse.domain.enums import SubscriberType
    from kse.domain.money import Money

    names = ["David Wilson", "Emily Watson", "Michael Chen", "Sarah Johnson", "Omar Hassan", "Lina Saleh"]
    subs = [ctx.subscribers.find_or_create(f"92000{i:02d}", name=n) for i, n in enumerate(names)]
    created = 0
    for month in range(1, 13):
        for k, sub in enumerate(subs):
            kwh = 180 + (month * 37 + k * 91) % 520 + (140 if month in (7, 8) else 0)   # summer peak
            start, end = dt.date(2024, month, 1), dt.date(2024, month, 28)
            try:
                calc, sched = ctx.invoices.calculate(CalculateInvoiceRequest(
                    subscriber_type=SubscriberType.RESIDENTIAL, previous_reading="0",
                    current_reading=str(kwh), previous_read_date=start, current_read_date=end,
                    previous_debt=Money.of(5000) if (month + k) % 7 == 0 else None))
                inv = ctx.invoices.save_calculation(calc, sched, sub, issue_date=end)
            except Exception as exc:                       # a missing tariff for a date must not abort the run
                print("skip", month, k, exc)
                continue
            created += 1
            if (month + k) % 3 == 0:                       # paid in full
                ctx.repos["invoices"].set_payment(inv.id, inv.total_due, end, "CASH", "")
            elif (month + k) % 5 == 0:                     # partial payment
                ctx.repos["invoices"].set_payment(inv.id, Money.of(inv.total_due.raw / 2), end, "CASH", "")
    ctx.conn.commit()
    return created


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", default="en", choices=["en", "ar"])
    ap.add_argument("--out", default=os.path.join(ROOT, "ScreenShot"))
    ap.add_argument("--offscreen", action="store_true")
    ap.add_argument("--pages", nargs="*", help="only these pages (default: all) - dialogs are skipped")
    args = ap.parse_args()
    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QApplication

    from kse.infrastructure.sqlite.seed import seed
    from kse.presentation import theme
    from kse.presentation.app_context import AppContext
    from kse.presentation.main_window import MainWindow
    from kse.presentation.pages import import_invoice, subscribers, tariffs

    os.makedirs(args.out, exist_ok=True)
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Voltiva")
    app.setStyle("Fusion")
    theme.register_fonts()
    app.setFont(QFont("Cairo", 10))

    ctx = AppContext(os.path.join(tempfile.mkdtemp(), "shots.db"), lang=args.lang)
    seed(ctx.conn, overwrite=True)
    ctx.conn.commit()
    print("fictional invoices added:", enrich(ctx))

    win = MainWindow(ctx)
    win.resize(1280, 800)
    win.show()

    def settle() -> None:
        app.processEvents()
        time.sleep(SETTLE)
        app.processEvents()

    def save(widget, name: str) -> None:
        path = os.path.join(args.out, name)
        widget.grab().save(path)
        print("saved", path, flush=True)

    suffix_lang = "" if args.lang == "en" else "-ar"
    pages = args.pages or PAGES
    for theme_name in ("light", "dark"):
        theme.apply(app, theme_name)
        suffix = suffix_lang + ("-dark" if theme_name == "dark" else "")
        settle()
        for key in pages:
            win.show_page(key)
            settle()
            save(win, f"{key.replace('_', '-')}{suffix}.png")
        if not args.pages:
            for name, make in (("tariff", lambda: tariffs.TariffDialog(ctx, None, win)),
                               ("subscriber", lambda: subscribers.SubscriberDialog(ctx, None, win)),
                               ("import", lambda: import_invoice.ImportInvoiceDialog(ctx, win))):
                dlg = make()
                dlg.show()
                settle()
                save(dlg, f"{name}-dialog{suffix}.png")
                dlg.hide()
    ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
