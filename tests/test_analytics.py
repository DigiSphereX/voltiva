"""AnalyticsService — monthly review & anomaly detection (pure Python, no GUI)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from kse.application.analytics import AnalyticsService
from kse.domain.enums import PaymentStatus
from kse.domain.models import Invoice
from kse.domain.money import Money


class _StubRepo:
    def __init__(self, invoices):
        self._invoices = invoices

    def list_recent(self, limit=50):
        return self._invoices


def _inv(month: str, *, kwh: Decimal, amount: str, official: str | None,
         paid: str = "0", status=PaymentStatus.UNPAID) -> Invoice:
    y, m = month.split("-")
    return Invoice(
        invoice_no="X", account_no="1", subscription_no="", subscriber_name="",
        issue_date=dt.date(int(y), int(m), 15),
        previous_read_date=dt.date(int(y), int(m), 1),
        current_read_date=dt.date(int(y), int(m), 15),
        consumption_kwh=kwh,
        adjusted_kwh=kwh,
        current_amount=Money.of(amount),
        total_due=Money.of(amount),
        official_amount=Money.of(official) if official else None,
        paid_amount=Money.of(paid),
        remaining_balance=Money.of(paid),
        payment_status=status,
    )


def test_monthly_review_aggregates_and_diff():
    svc = AnalyticsService(_StubRepo([
        _inv("2026-01", kwh=Decimal("100"), amount="10000", official="12000"),
        _inv("2026-01", kwh=Decimal("50"), amount="5000", official="5000"),
        _inv("2026-02", kwh=Decimal("60"), amount="6000", official=None),
        _inv("2026-02", kwh=Decimal("40"), amount="4000", official="2500"),
    ]))
    review = svc.monthly_review()
    rows = review["rows"]
    assert len(rows) == 2
    first = rows[0]  # 2026-02 (descending)
    assert first["month"] == "2026-02"
    assert first["count"] == 2
    assert first["official"].raw == Decimal("2500.00")       # only one had official
    assert first["official_count"] == 1
    assert first["computed"].raw == Decimal("10000.00")
    assert first["diff"].raw == Decimal("-7500.00")
    second = rows[1]  # 2026-01
    assert second["official"].raw == Decimal("17000.00")
    assert second["computed"].raw == Decimal("15000.00")
    assert second["diff"].raw == Decimal("2000.00")
    # totals only count months with an official amount
    totals = review["totals"]
    assert totals["official"].raw == Decimal("19500.00")
    assert totals["computed"].raw == Decimal("25000.00")
    assert totals["diff"].raw == Decimal("-5500.00")
    assert totals["overcharge_months"] == 1


def test_monthly_review_empty():
    svc = AnalyticsService(_StubRepo([]))
    review = svc.monthly_review()
    assert review["rows"] == []
    assert review["totals"]["diff"].raw == Decimal("0")


def test_anomalies_flags_rate_spike():
    invoices = [
        _inv("2026-01", kwh=Decimal("100"), amount="1000", official="1000"),   # rate 10
        _inv("2026-02", kwh=Decimal("100"), amount="1000", official="1000"),   # rate 10
        _inv("2026-03", kwh=Decimal("100"), amount="5000", official="5000"),   # rate 50 → spike
    ]
    svc = AnalyticsService(_StubRepo(invoices))
    alerts = svc.anomalies(invoices, limit=100)
    rate_alerts = [a for a in alerts if a["type"] == "rate"]
    assert any("2026-03" in a["month"] for a in rate_alerts)


def test_anomalies_no_false_on_even_data():
    invoices = [
        _inv("2026-01", kwh=Decimal("100"), amount="1000", official="1000"),
        _inv("2026-02", kwh=Decimal("100"), amount="1000", official="1000"),
        _inv("2026-03", kwh=Decimal("110"), amount="1100", official="1100"),
    ]
    svc = AnalyticsService(_StubRepo(invoices))
    assert svc.anomalies(invoices, limit=100) == []