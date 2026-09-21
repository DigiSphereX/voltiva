"""PDF & printing via Qt (QPrinter / QTextDocument) — prints & saves PDFs
with proper RTL Arabic content. No external PDF library required.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from ...domain.models import Invoice, InvoiceCharge, InvoiceReading
from ...domain.money import CURRENCY_AR, Money, fmt_quantity

DISCLAIMER_AR = "حساب تقديري/تحليلي --- ليس مستنداً رسمياً صادراً عن جهة رسمية."


def _esc(text) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _money(m: Money | None, code: str) -> str:
    if m is None:
        return "—"
    return f"{m.display()} {code}"


def build_invoice_html(
    invoice: Invoice,
    reading: InvoiceReading | None,
    charges: list[InvoiceCharge],
    calc_details: list[tuple[str, str]] | None = None,
    lang: str = "ar",
    i18n=None,
    currency: str | None = None,
) -> str:
    """Render a printable invoice as HTML in any UI language.

    ``i18n`` is the presentation I18n instance (provides tr() / enum_label());
    labels fall back to Arabic and ``currency`` to د.ع when not supplied.
    """
    tr = i18n.tr if i18n is not None else (lambda k: k)
    enum_label = i18n.enum_label if i18n is not None else (lambda v: getattr(v, "label_ar", str(v)))
    code = currency or CURRENCY_AR

    app_name = tr("app_name") if i18n is not None else "Voltiva"
    disclaimer = tr("pdf_disclaimer") if i18n is not None else DISCLAIMER_AR
    dir_attr = "rtl" if lang == "ar" else "ltr"
    sub_label = enum_label(invoice.subscriber_type)

    def row(label, value, bold=False, accent=False):
        fw = "font-weight:bold;" if bold else ""
        col = "#c1272d" if accent else "#1f2937"
        return f"<tr><td style='padding:6px;color:#6b7280'>{_esc(label)}</td><td style='padding:6px;{fw}color:{col};text-align:{'left' if lang=='ar' else 'right'}'>{_esc(value)}</td></tr>"

    def header(text):
        return f"<tr><td colspan='2' style='background:#f3f4f6;padding:6px;font-weight:bold'>{_esc(text)}</td></tr>"

    parts = [
        f"<html><head><meta charset='utf-8'></head><body dir='{dir_attr}' style='font-family:\"Segoe UI\",\"Tahoma\";color:#111827'>",
        f"<div style='text-align:center;border-bottom:3px solid #c1272d;padding-bottom:8px'>",
        f"<h2 style='margin:0;color:#c1272d'>{_esc(app_name)}</h2>",
        f"<div style='color:#6b7280'>{_esc(invoice.tariff_name or invoice.invoice_no)} — {_esc(invoice.invoice_no)}</div>",
        "</div>",
        f"<p style='color:#b91c1c;font-size:11px'>{_esc(disclaimer)}</p>",
        "<table width='100%' style='border-collapse:collapse;font-size:13px'>",
        header(tr("pdf_subscriber_header")),
        row(tr("iv_subscriber"), invoice.subscriber_name),
        row(tr("iv_account"), invoice.account_no),
        row(tr("sb_subscription_no"), invoice.subscription_no),
        row(tr("ni_subscriber_type"), sub_label),
        header(tr("pdf_readings_header")),
        row(tr("iv_prev_reading"), f"{fmt_quantity(invoice.previous_reading)} kWh"),
        row(tr("iv_curr_reading"), f"{fmt_quantity(invoice.current_reading)} kWh"),
        row(tr("iv_consumption"), f"{fmt_quantity(invoice.consumption_kwh)} kWh"),
        row(tr("iv_adjusted"), f"{fmt_quantity(invoice.adjusted_kwh)} kWh"),
        row(tr("ni_prev_date"), _esc(invoice.previous_read_date or "")),
        row(tr("ni_curr_date"), _esc(invoice.current_read_date or "")),
        row(tr("issue_date"), _esc(invoice.issue_date)),
        header(tr("pdf_financial_header")),
        row(tr("iv_energy"), _money(invoice.energy_cost, code)),
    ]
    if reading and reading.multiplier and reading.multiplier != 1:
        parts.append(row(tr("iv_multiplier"), str(reading.multiplier)))
    for c in charges:
        parts.append(row(c.name, _money(c.amount, code)))
    parts += [
        row(tr("iv_prev_debt"), _money(invoice.previous_debt, code)),
        row(tr("iv_current_amount"), _money(invoice.current_amount, code), bold=True),
        row(tr("iv_total_due"), _money(invoice.total_due, code), bold=True, accent=True),
    ]
    if invoice.official_amount is not None:
        parts.append(row(tr("iv_official_amt"), _money(invoice.official_amount, code)))
        parts.append(row(tr("iv_diff"), _money(invoice.comparison_diff, code)))
        parts.append(row(tr("iv_status"),
                        tr("status_match") if invoice.comparison_status == "MATCH" else tr("status_mismatch")))

    if calc_details:
        parts.append(header(tr("pdf_chain_header")))
        for label, value in calc_details:
            parts.append(row(label, value))

    parts.append("</table>")
    footer = tr("pdf_footer") if i18n is not None else (
        f"صدر بتاريخ {dt.date.today().isoformat()} — يتضمن بيانات تعرفة: "
        f"{invoice.tariff_name or '—'} (نسخة {invoice.tariff_version or '—'})")
    parts.append(
        f"<p style='margin-top:24px;color:#6b7280;font-size:10px'>"
        f"{_esc(footer.format(date=dt.date.today().isoformat(), tariff=invoice.tariff_name or '—', version=invoice.tariff_version or '—'))}</p>"
    )
    parts.append("</body></html>")
    return "".join(parts)


def render_to_pdf(html: str, path: str | Path, page_lang: str = "ar") -> None:
    from PyQt6.QtCore import QMarginsF, QSizeF
    from PyQt6.QtGui import QFont, QPageLayout, QPageSize, QTextDocument
    from PyQt6.QtPrintSupport import QPrinter

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)

    doc = QTextDocument()
    doc.setDefaultFont(QFont("Segoe UI", 10))
    doc.setHtml(html)
    doc.print(printer)


def print_invoice(html: str, page_lang: str = "ar") -> bool:
    from PyQt6.QtGui import QFont, QPageSize, QTextDocument
    from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    dialog = QPrintDialog(printer)
    if dialog.exec() != QPrintDialog.DialogCode.Accepted:
        return False
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Segoe UI", 10))
    doc.setHtml(html)
    doc.print(printer)
    return True