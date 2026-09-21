"""Audit trails — replay & determinism (spec §28)."""
import datetime as dt
import json
from decimal import Decimal

from kse.domain.enums import DataSource, SubscriberType
from kse.domain.money import Money
from kse.domain.services.audit import AuditEngine, AuditSnapshot
from kse.domain.services.invoice_calc import InvoiceCalculator

from conftest import make_schedule


def run_and_record():
    s = make_schedule(name="مرجع", rate=Decimal("10"))
    calc = InvoiceCalculator.calculate(
        subscriber_type=SubscriberType.RESIDENTIAL,
        previous_reading=13578,
        current_reading=17162,
        previous_read_date=dt.date(2024, 2, 1),
        current_read_date=dt.date(2024, 3, 15),
        tariff_schedule=s,
        previous_debt=Money.of(2500),
        official_amount=Money.of(38340),
    )
    snapshot = AuditEngine.build_snapshot(
        subscriber_type=SubscriberType.RESIDENTIAL,
        previous_reading=13578,
        current_reading=17162,
        previous_read_date=dt.date(2024, 2, 1),
        current_read_date=dt.date(2024, 3, 15),
        multiplier=1,
        scenario=calc.reading.scenario,
        max_reading=None,
        replacement_base=None,
        tariff_schedule_id=s.id,
        tariff_version=s.version,
        tariff_name=s.name_ar,
        tariff_source=s.source,
        debt=calc.previous_debt,
        fees=calc.fee_result.charges,
    )
    record = AuditEngine.build_record(
        action="CALCULATE", snapshot=snapshot, calc=calc,
        description="مثال", invoice_id=1,
    )
    return snapshot, record, s


class TestAudit:
    def test_record_contains_input_and_result(self):
        _, record, _ = run_and_record()
        details = json.loads(record["details_json"])
        assert details["snapshot"]["previous_reading"] == "13578"
        assert details["result"]["total_due"] == "38340.00"
        assert details["rounding"] == "ROUND_HALF_UP@2"

    def test_replay_is_deterministic(self):
        snapshot, record, s = run_and_record()
        details = json.loads(record["details_json"])
        # rebuild snapshot from stored JSON
        restored = AuditSnapshot(**details["snapshot"])
        replay = AuditEngine.replay(restored, s)
        assert replay.total_due == Money.of(38340)
        assert replay.energy_cost == Money.of(35840)
        # run again identical → deterministic
        replay2 = AuditEngine.replay(restored, s)
        assert replay.total_due == replay2.total_due