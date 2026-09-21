"""AuditEngine — records every calculation so the chain can always be rebuilt
(spec §28). "لماذا كانت الفاتورة 35,840 دينار؟" — answerable & reproducible.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from .consumption import ConsumptionResult
from ..enums import DataSource, SubscriberType
from ..money import Money, round_consumption, round_money
from .invoice_calc import InvoiceCalculation
from .tariff import TariffBreakdown, TariffEngine


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default, sort_keys=True)


def _json_default(o: Any):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, Money):
        return str(o.raw)
    if isinstance(o, dt.date):
        return o.isoformat()
    if isinstance(o, dt.datetime):
        return o.isoformat()
    if isinstance(o, (SubscriberType, DataSource)):
        return o.value
    return str(o)


@dataclass
class AuditSnapshot:
    """Minimal replay-able inputs for a calculation."""

    subscriber_type: str = "RESIDENTIAL"
    previous_reading: str = "0"
    current_reading: str = "0"
    previous_read_date: str = ""
    current_read_date: str = ""
    multiplier: str = "1"
    scenario: str = "NORMAL"
    max_reading: str | None = None
    replacement_base: str | None = None
    tariff_schedule_id: int | None = None
    tariff_version: str = ""
    tariff_name: str = ""
    tariff_source: str = "UNKNOWN"
    debt: str = "0"
    fees: list[dict[str, Any]] = field(default_factory=list)


class AuditEngine:
    @staticmethod
    def build_snapshot(
        *,
        subscriber_type: SubscriberType,
        previous_reading,
        current_reading,
        previous_read_date: dt.date,
        current_read_date: dt.date,
        multiplier,
        scenario,
        max_reading,
        replacement_base,
        tariff_schedule_id: int | None,
        tariff_version: str,
        tariff_name: str,
        tariff_source: DataSource,
        debt: Money,
        fees,
    ) -> AuditSnapshot:
        fee_dicts = []
        for f in fees or []:
            fee_dicts.append({
                "name": f.name,
                "category": f.category.value,
                "amount": str(f.amount.raw),
                "in_current": bool(f.in_current_amount),
                "in_total": bool(f.in_total_due),
                "taxable": bool(f.taxable),
            })
        return AuditSnapshot(
            subscriber_type=subscriber_type.value,
            previous_reading=str(previous_reading),
            current_reading=str(current_reading),
            previous_read_date=previous_read_date.isoformat() if previous_read_date else "",
            current_read_date=current_read_date.isoformat() if current_read_date else "",
            multiplier=str(multiplier),
            scenario=scenario.value,
            max_reading=str(max_reading) if max_reading is not None else None,
            replacement_base=str(replacement_base) if replacement_base is not None else None,
            tariff_schedule_id=tariff_schedule_id,
            tariff_version=tariff_version,
            tariff_name=tariff_name,
            tariff_source=tariff_source.value if tariff_source else "UNKNOWN",
            debt=str(debt.raw) if debt else "0",
            fees=fee_dicts,
        )

    @staticmethod
    def result_snapshot(calc: InvoiceCalculation) -> dict[str, Any]:
        return {
            "consumption_kwh": str(calc.reading.consumption_kwh) if calc.reading else "0",
            "adjusted_kwh": str(calc.reading.adjusted_kwh) if calc.reading else "0",
            "energy_cost": str(calc.energy_cost.raw),
            "fixed_fees": str(calc.fixed_fees.raw),
            "additional_fees": str(calc.additional_fees.raw),
            "discounts": str(calc.discounts.raw),
            "previous_debt": str(calc.previous_debt.raw),
            "current_amount": str(calc.current_amount.raw),
            "total_due": str(calc.total_due.raw),
            "tariff_id": calc.tariff_id,
            "tariff_version": calc.tariff_version,
        }

    @staticmethod
    def build_record(
        *,
        action: str,
        snapshot: AuditSnapshot,
        calc: InvoiceCalculation,
        description: str = "",
        invoice_id: int | None = None,
        user: str = "local",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Produce a dict ready to persist as one AuditLogs row."""
        steps_flat = [
            {"label": s.label_ar, "value": s.value_display, "detail": s.detail}
            for s in calc.steps
        ]
        details = {
            "snapshot": asdict(snapshot),
            "result": AuditEngine.result_snapshot(calc),
            "steps": steps_flat,
            "rounding": "ROUND_HALF_UP@2",
        }
        return {
            "action": action,
            "entity_type": "INVOICE",
            "entity_id": invoice_id,
            "user": user,
            "description": description,
            "details_json": _dumps(details),
            "invoice_id": invoice_id,
            "tariff_schedule_id": calc.tariff_id,
            "run_id": run_id or str(uuid.uuid4()),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    @staticmethod
    def replay(snapshot: AuditSnapshot, tariff_schedule) -> InvoiceCalculation:
        """Re-run a calculation from a stored snapshot (deterministic)."""
        from ..enums import MeterScenario, SubscriberType
        from .invoice_calc import InvoiceCalculator
        from .fees import FeeCalculator
        from .fees import FeeResult

        scenario = MeterScenario(snapshot.scenario)
        max_r = Decimal(snapshot.max_reading) if snapshot.max_reading else None
        base = Decimal(snapshot.replacement_base) if snapshot.replacement_base is not None else None

        fees = []
        for f in snapshot.fees:
            from ..enums import ChargeCategory
            from ..models import InvoiceCharge

            fees.append(InvoiceCharge(
                name=f.get("name", ""),
                category=ChargeCategory(f.get("category", "FIXED_FEE")),
                amount=Money.of(Decimal(f.get("amount", "0"))),
                in_current_amount=bool(f.get("in_current", True)),
                in_total_due=bool(f.get("in_total", True)),
                taxable=bool(f.get("taxable", False)),
            ))

        return InvoiceCalculator.calculate(
            subscriber_type=SubscriberType(snapshot.subscriber_type),
            previous_reading=snapshot.previous_reading,
            current_reading=snapshot.current_reading,
            previous_read_date=dt.date.fromisoformat(snapshot.previous_read_date) if snapshot.previous_read_date else dt.date.today(),
            current_read_date=dt.date.fromisoformat(snapshot.current_read_date) if snapshot.current_read_date else dt.date.today(),
            tariff_schedule=tariff_schedule,
            fees=fees,
            previous_debt=Money.of(Decimal(snapshot.debt or "0")),
            multiplier=snapshot.multiplier,
            scenario=scenario,
            max_reading=max_r,
            replacement_base=base,
        )