"""AnalyticsService — consumption & payment statistics (spec §19)."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from ..domain.enums import InvoiceStatus, PaymentStatus
from ..domain.money import Money, round_money
from .interfaces import InvoiceRepository


class AnalyticsService:
    def __init__(self, invoice_repo: InvoiceRepository) -> None:
        self.invoices = invoice_repo

    def dashboard(self) -> dict:
        recent = self.invoices.list_recent(limit=100_000)
        stats = self.compute_stats(recent)
        return stats

    def compute_stats(self, invoices) -> dict:
        total_invoices = len(invoices)
        total_kwh = sum((i.adjusted_kwh for i in invoices), Decimal("0"))
        total_amount = sum((i.total_due.raw for i in invoices), Decimal("0"))
        unpaid = [i for i in invoices if i.payment_status in (PaymentStatus.UNPAID, PaymentStatus.PARTIAL)]
        total_unpaid = sum((i.remaining_balance.raw for i in unpaid), Decimal("0"))
        paid = [i for i in invoices if i.payment_status == PaymentStatus.PAID]
        total_paid = sum((i.paid_amount.raw for i in invoices), Decimal("0"))

        consumptions = [i.adjusted_kwh for i in invoices if i.adjusted_kwh > 0]
        avg_kwh = sum(consumptions, Decimal("0")) / Decimal(len(consumptions)) if consumptions else Decimal("0")
        max_kwh = max(consumptions) if consumptions else Decimal("0")
        min_kwh = min(consumptions) if consumptions else Decimal("0")

        cost_per_kwh = (total_amount / total_kwh) if total_kwh > 0 else Decimal("0")
        avg_invoice = (total_amount / Decimal(total_invoices)) if total_invoices else Decimal("0")
        collection_rate = ((total_paid / total_amount) * 100) if total_amount > 0 else Decimal("0")
        amounts = [i.total_due.raw for i in invoices if i.total_due.raw > 0]
        max_invoice = max(amounts) if amounts else Decimal("0")

        # monthly buckets for charts
        monthly = defaultdict(lambda: {"kwh": Decimal("0"), "amount": Decimal("0"), "paid": Decimal("0"), "count": 0})
        for i in invoices:
            key = i.issue_date.strftime("%Y-%m")
            monthly[key]["kwh"] += i.adjusted_kwh
            monthly[key]["amount"] += i.total_due.raw
            monthly[key]["paid"] += i.paid_amount.raw
            monthly[key]["count"] += 1

        months = sorted(monthly)
        return {
            "total_invoices": total_invoices,
            "total_kwh": total_kwh,
            "total_amount": Money.of(total_amount),
            "unpaid_count": len(unpaid),
            "total_unpaid": Money.of(total_unpaid),
            "paid_count": len(paid),
            "total_paid": Money.of(total_paid),
            "avg_kwh": round_money(avg_kwh),
            "max_kwh": round_money(max_kwh),
            "min_kwh": round_money(min_kwh),
            "cost_per_kwh": round_money(cost_per_kwh),
            "avg_invoice": Money.of(avg_invoice),
            "max_invoice": Money.of(max_invoice),
            "collection_rate": round_money(collection_rate),
            "monthly": {
                m: {
                    "kwh": round_money(monthly[m]["kwh"]),
                    "amount": Money.of(monthly[m]["amount"]),
                    "paid": Money.of(monthly[m]["paid"]),
                    "count": monthly[m]["count"],
                }
                for m in months
            },
        }

    def filter_recent_months(self, invoices, last_n: int = 12) -> list:
        """Return invoices inside the latest `last_n` issue months.

        The filter is month-based rather than day-based so the UI range labels
        match the chart buckets exactly.
        """
        if not last_n:
            return list(invoices)
        months = sorted({i.issue_date.strftime("%Y-%m") for i in invoices})
        keep = set(months[-last_n:])
        return [i for i in invoices if i.issue_date.strftime("%Y-%m") in keep]

    def payment_breakdown(self, invoices) -> dict:
        """Counts and amounts by payment state for compact operational cards."""
        rows = {
            PaymentStatus.PAID: {"count": 0, "amount": Decimal("0")},
            PaymentStatus.PARTIAL: {"count": 0, "amount": Decimal("0")},
            PaymentStatus.UNPAID: {"count": 0, "amount": Decimal("0")},
        }
        for inv in invoices:
            status = inv.payment_status
            if status not in rows:
                continue
            rows[status]["count"] += 1
            rows[status]["amount"] += inv.total_due.raw
        return {
            status.value: {
                "count": data["count"],
                "amount": Money.of(data["amount"]),
            }
            for status, data in rows.items()
        }

    def subscriber_leaders(self, invoices, limit: int = 5) -> list[dict]:
        """Top subscribers by total due; useful for collection and review."""
        grouped: dict[str, dict] = {}
        for inv in invoices:
            key = inv.subscriber_name or inv.account_no or inv.subscription_no or "—"
            row = grouped.setdefault(key, {
                "name": key, "account": inv.account_no, "count": 0,
                "kwh": Decimal("0"), "amount": Decimal("0"), "unpaid": Decimal("0"),
            })
            row["count"] += 1
            row["kwh"] += inv.adjusted_kwh
            row["amount"] += inv.total_due.raw
            if inv.payment_status in (PaymentStatus.UNPAID, PaymentStatus.PARTIAL):
                row["unpaid"] += inv.remaining_balance.raw
        leaders = sorted(grouped.values(), key=lambda r: r["amount"], reverse=True)[:limit]
        return [
            {
                "name": row["name"],
                "account": row["account"],
                "count": row["count"],
                "kwh": round_money(row["kwh"]),
                "amount": Money.of(row["amount"]),
                "unpaid": Money.of(row["unpaid"]),
            }
            for row in leaders
        ]

    def forecast_next_month(self, invoices) -> dict:
        """Simple rolling projection from the latest three complete buckets."""
        stats = self.compute_stats(invoices)
        monthly = stats["monthly"]
        keys = sorted(monthly)[-3:]
        if not keys:
            return {"kwh": Decimal("0"), "amount": Money.zero(), "confidence": "none"}
        kwh = sum((monthly[k]["kwh"] for k in keys), Decimal("0")) / Decimal(len(keys))
        amount = sum((monthly[k]["amount"].raw for k in keys), Decimal("0")) / Decimal(len(keys))
        confidence = "high" if len(keys) >= 3 else ("medium" if len(keys) == 2 else "low")
        return {
            "kwh": round_money(kwh),
            "amount": Money.of(amount),
            "confidence": confidence,
        }

    def monthly_table(self, invoices, last_n: int = 12) -> list[dict]:
        """Rows for the analytics detail table, newest month first."""
        stats = self.compute_stats(self.filter_recent_months(invoices, last_n))
        rows: list[dict] = []
        for key in sorted(stats["monthly"], reverse=True):
            row = stats["monthly"][key]
            avg_rate = (row["amount"].raw / row["kwh"]) if row["kwh"] > 0 else Decimal("0")
            rows.append({
                "month": key,
                "count": row["count"],
                "kwh": row["kwh"],
                "amount": row["amount"],
                "paid": row["paid"],
                "remaining": Money.of(row["amount"].raw - row["paid"].raw),
                "avg_rate": round_money(avg_rate),
            })
        return rows

    def monthly_review(self, limit: int = 100_000) -> dict:
        """Per-month settlement review — recorded official amounts vs computed dues.

        The core anti-fraud view: for every billing month we compare what the
        collector's slip said (official_amount) against what the tariff engine
        computes (total_due). diff > 0 means the collector overcharged.
        """
        invoices = self.invoices.list_recent(limit=limit)
        by_month: dict[str, dict] = {}
        for inv in invoices:
            key = inv.issue_date.strftime("%Y-%m")
            row = by_month.setdefault(key, {
                "month": key, "count": 0, "kwh": Decimal("0"), "computed": Decimal("0"),
                "official": Decimal("0"), "official_count": 0, "paid": Decimal("0"),
            })
            row["count"] += 1
            row["kwh"] += inv.adjusted_kwh
            row["computed"] += inv.total_due.raw
            if inv.official_amount is not None:
                row["official"] += inv.official_amount.raw
                row["official_count"] += 1
            row["paid"] += inv.paid_amount.raw

        months = sorted(by_month, reverse=True)
        rows = []
        totals = {"computed": Decimal("0"), "official": Decimal("0"),
                  "diff": Decimal("0"), "overcharge_months": 0}
        for key in months:
            row = by_month[key]
            computed = round_money(row["computed"])
            official = round_money(row["official"])
            diff = round_money(official - computed)
            if row["official_count"] > 0:
                totals["computed"] += computed
                totals["official"] += official
                total_diff = official - computed
                totals["diff"] += total_diff
                if total_diff > 0:
                    totals["overcharge_months"] += 1
            rows.append({
                "month": key,
                "count": row["count"],
                "kwh": round_money(row["kwh"]),
                "computed": Money.of(computed),
                "official": Money.of(official),
                "official_count": row["official_count"],
                "diff": Money.of(diff),
                "paid": Money.of(round_money(row["paid"])),
            })
        return {
            "rows": rows,
            "totals": {
                "computed": Money.of(totals["computed"]),
                "official": Money.of(totals["official"]),
                "diff": Money.of(totals["diff"]),
                "overcharge_months": totals["overcharge_months"],
            },
        }

    def anomalies(self, invoices, limit: int = 100_000) -> list[dict]:
        """Flag months whose rate/kWh or consumption deviates strongly from the norm."""
        stats = self.compute_stats(invoices)
        monthly = stats["monthly"]
        months = sorted(monthly)
        if len(months) < 2:
            return []
        rates: list[Decimal] = []
        for m in months:
            d = monthly[m]
            if d["kwh"] > 0:
                rates.append(d["amount"].raw / d["kwh"])
        avg_rate = sum(rates) / Decimal(len(rates)) if rates else Decimal("0")
        kwhs = [monthly[m]["kwh"] for m in months]
        avg_kwh = sum(kwhs) / Decimal(len(kwhs)) if kwhs else Decimal("0")

        alerts: list[dict] = []
        for m in months:
            d = monthly[m]
            if avg_rate > 0 and d["kwh"] > 0:
                rate = d["amount"].raw / d["kwh"]
                if rate > avg_rate * Decimal("1.5"):
                    alerts.append({
                        "month": m,
                        "type": "rate",
                        "code": "an_anomaly_rate",
                        "rate": round_money(rate),
                        "avg": round_money(avg_rate),
                    })
            if avg_kwh > 0 and d["kwh"] > avg_kwh * Decimal("2"):
                alerts.append({
                    "month": m,
                    "type": "consumption",
                    "code": "an_anomaly_consumption",
                    "kwh": round_money(d["kwh"]),
                    "avg": round_money(avg_kwh),
                })
        alerts.sort(key=lambda a: a["month"], reverse=True)
        return alerts

    def series_for_months(self, invoices, last_n: int = 12) -> dict:
        """Return ordered monthly series arrays for charts."""
        stats = self.compute_stats(invoices)
        monthly = stats["monthly"]
        keys = sorted(monthly)[-last_n:]
        return {
            "labels": keys,
            "kwh": [float(monthly[k]["kwh"]) for k in keys],
            "amount": [float(monthly[k]["amount"].raw) for k in keys],
            "paid": [float(monthly[k]["paid"].raw) for k in keys],
            "count": [monthly[k]["count"] for k in keys],
        }

    def kwh_trend(self, invoices) -> str:
        """Return a trend code ("insufficient" | "up" | "down" | "flat") for UI localization."""
        stats = self.compute_stats(invoices)
        keys = sorted(stats["monthly"])
        if len(keys) < 2:
            return "insufficient"
        first = stats["monthly"][keys[0]]["kwh"]
        last = stats["monthly"][keys[-1]]["kwh"]
        if last > first * Decimal("1.05"):
            return "up"
        if last < first * Decimal("0.95"):
            return "down"
        return "flat"
