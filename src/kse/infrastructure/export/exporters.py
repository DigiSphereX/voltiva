"""Export/print of invoices — PDF via Qt, Excel via openpyxl, CSV, JSON.

JSON export is structured so it can be re-imported (round-trip).
"""
from __future__ import annotations

import csv
import io
import json
import re
import datetime as dt
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ...domain.enums import ChargeCategory, DataSource, MeterScenario, PaymentStatus, SubscriberType
from ...domain.models import Invoice, InvoiceCharge, InvoiceReading
from ...domain.money import Money

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_NUMERIC_LIKE = re.compile(r"[+-]?[\d\s.,]+")


def safe_cell(value):
    """Neutralise spreadsheet formula injection (CSV/Excel).

    Subscriber names, notes, etc. are user/OCR-controlled. A value such as
    ``=HYPERLINK(...)`` or ``@SUM(...)`` would execute when the export is opened in
    Excel/LibreOffice. Text that starts with a formula trigger gets a leading
    apostrophe; plain numbers (including negative ones) are left untouched.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES) \
            and not _NUMERIC_LIKE.fullmatch(value):
        return "'" + value
    return value


def _dec(value, field: str) -> Decimal:
    """Parse an imported Decimal, rejecting NaN/Infinity/garbage with a clear error."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid number for '{field}': {value!r}") from None
    if not d.is_finite():
        raise ValueError(f"Invalid number for '{field}': {value!r}")
    return d


def _esc(text: str | None) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def invoice_to_dict(invoice: Invoice, reading: InvoiceReading | None = None,
                    charges: list[InvoiceCharge] | None = None) -> dict:
    data = {
        "schema_version": 1,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "invoice": {
            "invoice_no": invoice.invoice_no,
            "account_no": invoice.account_no,
            "subscription_no": invoice.subscription_no,
            "subscriber_name": invoice.subscriber_name,
            "subscriber_type": invoice.subscriber_type.value,
            "issue_date": invoice.issue_date.isoformat(),
            "previous_read_date": invoice.previous_read_date.isoformat() if invoice.previous_read_date else None,
            "current_read_date": invoice.current_read_date.isoformat() if invoice.current_read_date else None,
            "previous_reading": str(invoice.previous_reading),
            "current_reading": str(invoice.current_reading),
            "consumption_kwh": str(invoice.consumption_kwh),
            "adjusted_kwh": str(invoice.adjusted_kwh),
            "tariff_schedule_id": invoice.tariff_schedule_id,
            "tariff_version": invoice.tariff_version,
            "tariff_name": invoice.tariff_name,
            "energy_cost": str(invoice.energy_cost.raw),
            "fixed_fees": str(invoice.fixed_fees.raw),
            "additional_fees": str(invoice.additional_fees.raw),
            "discounts": str(invoice.discounts.raw),
            "previous_debt": str(invoice.previous_debt.raw),
            "current_amount": str(invoice.current_amount.raw),
            "total_due": str(invoice.total_due.raw),
            "official_amount": str(invoice.official_amount.raw) if invoice.official_amount is not None else None,
            "comparison_status": invoice.comparison_status,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "payment_status": invoice.payment_status.value,
            "paid_amount": str(invoice.paid_amount.raw),
            "remaining_balance": str(invoice.remaining_balance.raw),
            "notes": invoice.notes,
        },
        "reading": None,
        "charges": [],
    }
    if reading is not None:
        data["reading"] = {
            "meter_no": reading.meter_no,
            "previous_reading": str(reading.previous_reading),
            "current_reading": str(reading.current_reading),
            "previous_date": reading.previous_date.isoformat(),
            "current_date": reading.current_date.isoformat(),
            "multiplier": str(reading.multiplier),
            "scenario": reading.scenario.value,
            "is_estimated": reading.is_estimated,
            "meter_replaced": reading.meter_replaced,
            "consumption_kwh": str(reading.consumption_kwh),
            "adjusted_kwh": str(reading.adjusted_kwh),
        }
    for c in charges or []:
        data["charges"].append({
            "name": c.name,
            "category": c.category.value,
            "amount": str(c.amount.raw),
            "reason": c.reason,
            "in_current_amount": c.in_current_amount,
            "in_total_due": c.in_total_due,
            "taxable": c.taxable,
            "source": c.source.value,
        })
    return data


def json_export(invoice: Invoice, reading: InvoiceReading | None, charges: list[InvoiceCharge] | None, path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(invoice_to_dict(invoice, reading, charges), fh, ensure_ascii=False, indent=2)


def json_export_many(entries: list[tuple[Invoice, InvoiceReading | None, list[InvoiceCharge] | None]],
                     path: str | Path) -> None:
    """Export several invoices to ONE file.

    One invoice keeps the original single-object format (re-importable by
    :func:`json_to_invoice`); several invoices are written as
    ``{"schema_version": 1, "invoices": [ {...}, ... ]}``.
    """
    if not entries:
        raise ValueError("no invoices to export")
    if len(entries) == 1:
        json_export(*entries[0], path)
        return
    payload = {
        "schema_version": 1,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "invoices": [invoice_to_dict(i, r, c) for i, r, c in entries],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def json_to_invoices(payload: dict) -> list[tuple[Invoice, InvoiceReading | None, list[InvoiceCharge]]]:
    """Inverse of :func:`json_export_many` (also accepts the single-invoice format)."""
    if "invoices" in payload:
        return [json_to_invoice(p) for p in payload["invoices"]]
    return [json_to_invoice(payload)]


def json_to_invoice(payload: dict) -> tuple[Invoice, InvoiceReading | None, list[InvoiceCharge]]:
    inv = payload["invoice"]
    status_map = {
        "UNPAID": PaymentStatus.UNPAID,
        "PARTIAL": PaymentStatus.PARTIAL,
        "PAID": PaymentStatus.PAID,
    }
    invoice = Invoice(
        invoice_no=str(inv["invoice_no"]),
        account_no=str(inv.get("account_no", "")),
        subscription_no=str(inv.get("subscription_no", "")),
        subscriber_name=str(inv.get("subscriber_name", "")),
        subscriber_type=SubscriberType(inv["subscriber_type"]),
        issue_date=dt.date.fromisoformat(inv["issue_date"]),
        previous_read_date=dt.date.fromisoformat(inv["previous_read_date"]) if inv.get("previous_read_date") else None,
        current_read_date=dt.date.fromisoformat(inv["current_read_date"]) if inv.get("current_read_date") else None,
        previous_reading=_dec(inv["previous_reading"], "previous_reading"),
        current_reading=_dec(inv["current_reading"], "current_reading"),
        consumption_kwh=_dec(inv["consumption_kwh"], "consumption_kwh"),
        adjusted_kwh=_dec(inv["adjusted_kwh"], "adjusted_kwh"),
        tariff_schedule_id=inv.get("tariff_schedule_id"),
        tariff_version=str(inv.get("tariff_version", "")),
        tariff_name=str(inv.get("tariff_name", "")),
        energy_cost=Money.of(_dec(inv["energy_cost"], "energy_cost")),
        fixed_fees=Money.of(_dec(inv.get("fixed_fees", "0"), "fixed_fees")),
        additional_fees=Money.of(_dec(inv.get("additional_fees", "0"), "additional_fees")),
        discounts=Money.of(_dec(inv.get("discounts", "0"), "discounts")),
        previous_debt=Money.of(_dec(inv.get("previous_debt", "0"), "previous_debt")),
        current_amount=Money.of(_dec(inv["current_amount"], "current_amount")),
        total_due=Money.of(_dec(inv["total_due"], "total_due")),
        official_amount=Money.of(_dec(inv["official_amount"], "official_amount")) if inv.get("official_amount") else None,
        comparison_status=str(inv.get("comparison_status", "NOT_COMPARED")),
        due_date=dt.date.fromisoformat(inv["due_date"]) if inv.get("due_date") else None,
        payment_status=status_map.get(inv.get("payment_status", "UNPAID"), PaymentStatus.UNPAID),
        paid_amount=Money.of(_dec(inv.get("paid_amount", "0"), "paid_amount")),
        remaining_balance=Money.of(_dec(inv.get("remaining_balance", "0"), "remaining_balance")),
        notes=str(inv.get("notes", "")),
    )
    reading = None
    if payload.get("reading"):
        rd = payload["reading"]
        reading = InvoiceReading(
            meter_no=str(rd.get("meter_no", "")),
            previous_reading=_dec(rd["previous_reading"], "previous_reading"),
            current_reading=_dec(rd["current_reading"], "current_reading"),
            previous_date=dt.date.fromisoformat(rd["previous_date"]),
            current_date=dt.date.fromisoformat(rd["current_date"]),
            multiplier=_dec(rd.get("multiplier", "1"), "multiplier"),
            scenario=MeterScenario(rd.get("scenario", "NORMAL")),
            is_estimated=bool(rd.get("is_estimated", False)),
            meter_replaced=bool(rd.get("meter_replaced", False)),
            consumption_kwh=_dec(rd.get("consumption_kwh", "0"), "consumption_kwh"),
            adjusted_kwh=_dec(rd.get("adjusted_kwh", "0"), "adjusted_kwh"),
        )
    charges = []
    for c in payload.get("charges", []):
        charges.append(InvoiceCharge(
            name=str(c.get("name", "")),
            category=ChargeCategory(c.get("category", "FIXED_FEE")),
            amount=Money.of(_dec(c.get("amount", "0"), "amount")),
            reason=str(c.get("reason", "")),
            in_current_amount=bool(c.get("in_current_amount", True)),
            in_total_due=bool(c.get("in_total_due", True)),
            taxable=bool(c.get("taxable", False)),
            source=DataSource(c.get("source", "USER_DEFINED")),
        ))
    return invoice, reading, charges


def csv_export(rows: list[dict], path: str | Path) -> None:
    if not rows:
        raise ValueError("no rows to export")
    keys = list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows({k: safe_cell(v) for k, v in row.items()} for row in rows)


def _style_excel_sheet(ws, headers: list[str], rows: list[list]) -> None:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_font = Font(name="Segoe UI", size=10)
    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    ws.row_dimensions[1].height = 26
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align

    for r_idx, row_values in enumerate(rows, start=2):
        ws.row_dimensions[r_idx].height = 20
        is_even = (r_idx % 2 == 0)
        for c_idx, val in enumerate(row_values, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=safe_cell(val))
            cell.font = data_font
            cell.border = thin_border
            if not is_even:
                cell.fill = zebra_fill
            if isinstance(val, (int, float, Decimal)):
                if isinstance(val, float):
                    cell.number_format = "#,##0.00"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    for col_idx, h in enumerate(headers, start=1):
        col_letter = get_column_letter(col_idx)
        max_len = len(str(h))
        for r_idx in range(2, len(rows) + 2):
            v = ws.cell(row=r_idx, column=col_idx).value
            if v is not None:
                max_len = max(max_len, len(str(v)))
        ws.column_dimensions[col_letter].width = max(12, min(max_len + 4, 45))


def excel_export(invoices: list[Invoice], path: str | Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Invoices"
    headers = [
        "invoice_no", "account_no", "subscriber_name", "subscriber_type",
        "issue_date", "consumption_kwh", "adjusted_kwh", "energy_cost",
        "fixed_fees", "additional_fees", "discounts", "previous_debt",
        "current_amount", "total_due", "official_amount", "comparison_status",
        "payment_status", "due_date", "tariff_id", "tariff_version", "notes",
    ]
    rows = []
    for inv in invoices:
        rows.append([
            inv.invoice_no, inv.account_no, inv.subscriber_name, inv.subscriber_type.value,
            inv.issue_date.isoformat(), float(inv.consumption_kwh), float(inv.adjusted_kwh),
            float(inv.energy_cost.raw), float(inv.fixed_fees.raw), float(inv.additional_fees.raw),
            float(inv.discounts.raw), float(inv.previous_debt.raw), float(inv.current_amount.raw),
            float(inv.total_due.raw), float(inv.official_amount.raw) if inv.official_amount else None,
            inv.comparison_status, inv.payment_status.value,
            inv.due_date.isoformat() if inv.due_date else None,
            inv.tariff_schedule_id, inv.tariff_version, inv.notes,
        ])
    _style_excel_sheet(ws, headers, rows)
    wb.save(path)


def excel_export_subscribers(subscribers, path: str | Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Subscribers"
    headers = [
        "account_no", "subscription_no", "name", "subscriber_type",
        "governorate", "qadaa", "address", "previous_debt",
    ]
    rows = []
    for s in subscribers:
        sub_type = s.subscriber_type.value if hasattr(s.subscriber_type, "value") else str(s.subscriber_type)
        debt = float(s.previous_debt.raw) if hasattr(s.previous_debt, "raw") else 0.0
        rows.append([
            s.account_no, s.subscription_no, s.name, sub_type,
            s.governorate, s.qadaa, s.address, debt,
        ])
    _style_excel_sheet(ws, headers, rows)
    wb.save(path)


def csv_export_subscribers(subscribers, path: str | Path) -> None:
    rows = []
    for s in subscribers:
        sub_type = s.subscriber_type.value if hasattr(s.subscriber_type, "value") else str(s.subscriber_type)
        rows.append({
            "account_no": s.account_no,
            "subscription_no": s.subscription_no,
            "name": s.name,
            "subscriber_type": sub_type,
            "governorate": s.governorate,
            "qadaa": s.qadaa,
            "address": s.address,
            "previous_debt": str(s.previous_debt.raw) if hasattr(s.previous_debt, "raw") else "0",
        })
    csv_export(rows, path)


def excel_export_monthly(monthly_rows: list[dict], path: str | Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Monthly Analytics"
    headers = [
        "month", "count", "consumption_kwh", "total_amount",
        "paid_amount", "remaining_balance", "avg_rate_kwh",
    ]
    rows = []
    for r in monthly_rows:
        amount = float(r["amount"].raw) if hasattr(r.get("amount"), "raw") else 0.0
        paid = float(r["paid"].raw) if hasattr(r.get("paid"), "raw") else 0.0
        rem = float(r["remaining"].raw) if hasattr(r.get("remaining"), "raw") else 0.0
        rows.append([
            r.get("month", ""),
            int(r.get("count", 0)),
            float(r.get("kwh", 0)),
            amount,
            paid,
            rem,
            str(r.get("avg_rate", "")),
        ])
    _style_excel_sheet(ws, headers, rows)
    wb.save(path)


def csv_export_monthly(monthly_rows: list[dict], path: str | Path) -> None:
    rows = []
    for r in monthly_rows:
        amount_str = str(r["amount"].raw) if hasattr(r.get("amount"), "raw") else "0"
        paid_str = str(r["paid"].raw) if hasattr(r.get("paid"), "raw") else "0"
        rem_str = str(r["remaining"].raw) if hasattr(r.get("remaining"), "raw") else "0"
        rows.append({
            "month": r.get("month", ""),
            "count": r.get("count", 0),
            "consumption_kwh": str(r.get("kwh", 0)),
            "total_amount": amount_str,
            "paid_amount": paid_str,
            "remaining_balance": rem_str,
            "avg_rate_kwh": str(r.get("avg_rate", "")),
        })
    csv_export(rows, path)


def invoice_calculation_details(calc) -> list[tuple[str, str]]:
    """Return [(label, value), ...] from an InvoiceCalculation for the report."""
    rows = [(s.label, s.value_display) for s in calc.steps]
    return rows