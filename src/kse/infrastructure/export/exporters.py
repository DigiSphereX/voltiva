"""Export/print of invoices — PDF via Qt, Excel via openpyxl, CSV, JSON.

JSON export is structured so it can be re-imported (round-trip).
"""
from __future__ import annotations

import csv
import io
import json
import datetime as dt
from decimal import Decimal
from pathlib import Path

from ...domain.enums import ChargeCategory, DataSource, MeterScenario, PaymentStatus, SubscriberType
from ...domain.models import Invoice, InvoiceCharge, InvoiceReading
from ...domain.money import CURRENCY_AR, Money, arabic_digits, fmt_quantity

DISCLAIMER_AR = "حساب تقديري/تحليلي --- ليس مستنداً رسمياً صادراً عن جهة رسمية."
DISCLAIMER_EN = "Analytical / estimated calculation --- not an official document issued by a power utility provider."


def _fmt_money(m: Money | None) -> str:
    if m is None:
        return ""
    return f"{m.display()} {CURRENCY_AR}"


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
        previous_reading=Decimal(inv["previous_reading"]),
        current_reading=Decimal(inv["current_reading"]),
        consumption_kwh=Decimal(inv["consumption_kwh"]),
        adjusted_kwh=Decimal(inv["adjusted_kwh"]),
        tariff_schedule_id=inv.get("tariff_schedule_id"),
        tariff_version=str(inv.get("tariff_version", "")),
        tariff_name=str(inv.get("tariff_name", "")),
        energy_cost=Money.of(Decimal(inv["energy_cost"])),
        fixed_fees=Money.of(Decimal(inv.get("fixed_fees", "0"))),
        additional_fees=Money.of(Decimal(inv.get("additional_fees", "0"))),
        discounts=Money.of(Decimal(inv.get("discounts", "0"))),
        previous_debt=Money.of(Decimal(inv.get("previous_debt", "0"))),
        current_amount=Money.of(Decimal(inv["current_amount"])),
        total_due=Money.of(Decimal(inv["total_due"])),
        official_amount=Money.of(Decimal(inv["official_amount"])) if inv.get("official_amount") else None,
        comparison_status=str(inv.get("comparison_status", "NOT_COMPARED")),
        due_date=dt.date.fromisoformat(inv["due_date"]) if inv.get("due_date") else None,
        payment_status=status_map.get(inv.get("payment_status", "UNPAID"), PaymentStatus.UNPAID),
        paid_amount=Money.of(Decimal(inv.get("paid_amount", "0"))),
        remaining_balance=Money.of(Decimal(inv.get("remaining_balance", "0"))),
        notes=str(inv.get("notes", "")),
    )
    reading = None
    if payload.get("reading"):
        rd = payload["reading"]
        reading = InvoiceReading(
            meter_no=str(rd.get("meter_no", "")),
            previous_reading=Decimal(rd["previous_reading"]),
            current_reading=Decimal(rd["current_reading"]),
            previous_date=dt.date.fromisoformat(rd["previous_date"]),
            current_date=dt.date.fromisoformat(rd["current_date"]),
            multiplier=Decimal(rd.get("multiplier", "1")),
            scenario=MeterScenario(rd.get("scenario", "NORMAL")),
            is_estimated=bool(rd.get("is_estimated", False)),
            meter_replaced=bool(rd.get("meter_replaced", False)),
            consumption_kwh=Decimal(rd.get("consumption_kwh", "0")),
            adjusted_kwh=Decimal(rd.get("adjusted_kwh", "0")),
        )
    charges = []
    for c in payload.get("charges", []):
        charges.append(InvoiceCharge(
            name=str(c.get("name", "")),
            category=ChargeCategory(c.get("category", "FIXED_FEE")),
            amount=Money.of(Decimal(c.get("amount", "0"))),
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
        writer.writerows(rows)


def excel_export(invoices: list[Invoice], path: str | Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

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
    bold = Font(bold=True)
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = bold
    for r, inv in enumerate(invoices, start=2):
        values = [
            inv.invoice_no, inv.account_no, inv.subscriber_name, inv.subscriber_type.value,
            inv.issue_date.isoformat(), float(inv.consumption_kwh), float(inv.adjusted_kwh),
            float(inv.energy_cost.raw), float(inv.fixed_fees.raw), float(inv.additional_fees.raw),
            float(inv.discounts.raw), float(inv.previous_debt.raw), float(inv.current_amount.raw),
            float(inv.total_due.raw), float(inv.official_amount.raw) if inv.official_amount else None,
            inv.comparison_status, inv.payment_status.value,
            inv.due_date.isoformat() if inv.due_date else None,
            inv.tariff_schedule_id, inv.tariff_version, inv.notes,
        ]
        for col, v in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=v)
            if isinstance(v, float):
                cell.number_format = "#,##0.00"
    for i, _ in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(i)].width = 20
    wb.save(path)


def invoice_calculation_details(calc) -> list[tuple[str, str]]:
    """Return [(label, value), ...] from an InvoiceCalculation for the report."""
    from ...domain.money import fmt_quantity

    rows = [(s.label_ar, s.value_display) for s in calc.steps]
    return rows