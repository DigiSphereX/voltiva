"""SQLite implementations of the repository ports."""
from __future__ import annotations

import datetime as dt
import sqlite3
from decimal import Decimal
from typing import Any

from ...domain.enums import (
    ChargeCategory,
    DataSource,
    InvoiceStatus,
    MeterPhase,
    MeterScenario,
    MeterType,
    PaymentStatus,
    ServiceZone,
    SubscriberType,
    TariffMethod,
)
from ...domain.models import (
    AuditLogEntry,
    Debt,
    Invoice,
    InvoiceCharge,
    InvoiceReading,
    Meter,
    Payment,
    Setting,
    Subscriber,
    TariffFee,
    TariffSchedule,
    TariffTier,
)
from ...domain.errors import DuplicateInvoiceNumberError, InvoiceStateError, PaymentError
from ...domain.money import Money
from ..sqlite import db as db_module

# ---------------------------------------------------------------- helpers


def _like(query: str) -> str:
    """Contains-pattern for ``LIKE ? ESCAPE '\\'`` with user wildcards neutralised.

    A search for ``50%`` or ``A_1`` used to treat ``%``/``_`` as wildcards and
    return unrelated rows.
    """
    return f"%{_escape_like(query)}%"


def _escape_like(text: str) -> str:
    """Escape LIKE wildcards (use together with ``ESCAPE '\\'``)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")



def _as_date(v) -> dt.date | None:
    if not v:
        return None
    return dt.date.fromisoformat(str(v))


def _as_dt(v) -> dt.datetime | None:
    if not v:
        return None
    return dt.datetime.fromisoformat(str(v))


def _as_dec(v) -> Decimal:
    if v in (None, ""):
        return Decimal("0")
    return Decimal(str(v))


def _row_to_subscriber(r) -> Subscriber:
    if r is None:
        return None
    return Subscriber(
        id=r["id"],
        subscription_no=r["subscription_no"],
        account_no=r["account_no"],
        name=r["name"],
        address=r["address"],
        governorate=r["governorate"],
        qadaa=r["qadaa"],
        nahia=r["nahia"],
        house_no=r["house_no"],
        department=r["department"],
        subscriber_type=SubscriberType(r["subscriber_type"]),
        phase=MeterPhase(r["phase"]),
        status=r["status"],
        previous_debt=Money.from_db(r["previous_debt"]),
        notes=r["notes"],
        created_at=_as_dt(r["created_at"]),
        updated_at=_as_dt(r["updated_at"]),
    )


def _row_to_meter(r) -> Meter:
    if r is None:
        return None
    return Meter(
        id=r["id"],
        subscriber_id=r["subscriber_id"],
        meter_no=r["meter_no"],
        serial_no=r["serial_no"],
        meter_type=MeterType(r["meter_type"]),
        phase=MeterPhase(r["phase"]),
        multiplier=_as_dec(r["multiplier"]),
        status=r["status"],
        installed_at=_as_date(r["installed_at"]),
        removed_at=_as_date(r["removed_at"]),
        notes=r["notes"],
        created_at=_as_dt(r["created_at"]),
    )


def _row_to_tier(r) -> TariffTier:
    return TariffTier(
        id=r["id"],
        tier_no=r["tier_no"],
        from_kwh=_as_dec(r["from_kwh"]),
        to_kwh=_as_dec(r["to_kwh"]) if r["to_kwh"] not in (None, "") else None,
        rate_per_kwh=_as_dec(r["rate_per_kwh"]),
    )


def _row_to_fee(r) -> TariffFee:
    return TariffFee(
        id=r["id"],
        name=r["name"],
        category=ChargeCategory(r["category"]),
        amount=Money.from_db(r["amount"]),
        is_fixed=bool(r["is_fixed"]),
        depends_on_consumption=bool(r["depends_on_consumption"]),
        taxable=bool(r["taxable"]),
        in_current_amount=bool(r["in_current_amount"]),
        in_total_due=bool(r["in_total_due"]),
        reason=r["reason"],
    )


def _row_to_schedule(r, conn: sqlite3.Connection, load_children: bool = True) -> TariffSchedule:
    s = TariffSchedule(
        id=r["id"],
        name=r["name"],
        subscriber_type=SubscriberType(r["subscriber_type"]),
        method=TariffMethod(r["method"]),
        service_zone=ServiceZone(r["service_zone"] or "TRADITIONAL"),
        version=r["version"],
        effective_from=_as_date(r["effective_from"]),
        effective_to=_as_date(r["effective_to"]),
        is_active=bool(r["is_active"]),
        source=DataSource(r["source"]),
        source_date=_as_date(r["source_date"]),
        source_detail=r["source_detail"],
        notes=r["notes"],
        created_at=_as_dt(r["created_at"]),
    )
    if load_children:
        s.tiers = [_row_to_tier(t) for t in conn.execute(
            "SELECT * FROM TariffTiers WHERE schedule_id=? ORDER BY from_kwh", (s.id,))]
        s.fixed_fees = [_row_to_fee(f) for f in conn.execute(
            "SELECT * FROM TariffFees WHERE schedule_id=?", (s.id,))]
    return s


def _rows_to_schedules(rows, conn: sqlite3.Connection) -> list[TariffSchedule]:
    """Build schedules for many rows using 2 queries instead of 2 per schedule.

    ``list_schedules`` runs on every calculation/verification, so the old
    per-row tier/fee queries (N+1) added up quickly as tariffs accumulated.
    """
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    tiers_by: dict[int, list] = {i: [] for i in ids}
    fees_by: dict[int, list] = {i: [] for i in ids}
    for t in conn.execute(
            f"SELECT * FROM TariffTiers WHERE schedule_id IN ({marks}) ORDER BY schedule_id, from_kwh", ids):
        tiers_by[t["schedule_id"]].append(_row_to_tier(t))
    for f in conn.execute(f"SELECT * FROM TariffFees WHERE schedule_id IN ({marks}) ORDER BY id", ids):
        fees_by[f["schedule_id"]].append(_row_to_fee(f))
    out = []
    for r in rows:
        s = _row_to_schedule(r, conn, load_children=False)
        s.tiers = tiers_by[s.id]
        s.fixed_fees = fees_by[s.id]
        out.append(s)
    return out


def _row_to_invoice(r) -> Invoice:
    return Invoice(
        id=r["id"],
        invoice_no=r["invoice_no"],
        subscriber_id=r["subscriber_id"],
        account_no=r["account_no"],
        subscription_no=r["subscription_no"],
        subscriber_name=r["subscriber_name"],
        subscriber_type=SubscriberType(r["subscriber_type"]),
        issue_date=_as_date(r["issue_date"]),
        previous_read_date=_as_date(r["previous_read_date"]),
        current_read_date=_as_date(r["current_read_date"]),
        previous_reading=_as_dec(r["previous_reading"]),
        current_reading=_as_dec(r["current_reading"]),
        consumption_kwh=_as_dec(r["consumption_kwh"]),
        adjusted_kwh=_as_dec(r["adjusted_kwh"]),
        tariff_schedule_id=r["tariff_schedule_id"],
        tariff_version=r["tariff_version"],
        tariff_name=r["tariff_name"],
        energy_cost=Money.from_db(r["energy_cost"]),
        fixed_fees=Money.from_db(r["fixed_fees"]),
        additional_fees=Money.from_db(r["additional_fees"]),
        discounts=Money.from_db(r["discounts"]),
        previous_debt=Money.from_db(r["previous_debt"]),
        current_amount=Money.from_db(r["current_amount"]),
        total_due=Money.from_db(r["total_due"]),
        currency=r["currency"],
        official_amount=Money.from_db(r["official_amount"]) if r["official_amount"] else None,
        comparison_status=r["comparison_status"],
        comparison_diff=Money.from_db(r["comparison_diff"]) if r["comparison_diff"] else None,
        due_date=_as_date(r["due_date"]),
        payment_status=PaymentStatus(r["payment_status"]),
        paid_amount=Money.from_db(r["paid_amount"]),
        remaining_balance=Money.from_db(r["remaining_balance"]),
        notes=r["notes"],
        status=InvoiceStatus(r["status"]),
        audit_run_id=r["audit_run_id"],
        created_at=_as_dt(r["created_at"]),
        updated_at=_as_dt(r["updated_at"]),
    )


def _row_to_reading(r) -> InvoiceReading:
    return InvoiceReading(
        id=r["id"],
        meter_id=r["meter_id"],
        meter_no=r["meter_no"],
        previous_reading=_as_dec(r["previous_reading"]),
        current_reading=_as_dec(r["current_reading"]),
        previous_date=_as_date(r["previous_date"]),
        current_date=_as_date(r["current_date"]),
        multiplier=_as_dec(r["multiplier"]),
        scenario=MeterScenario(r["scenario"]),
        is_estimated=bool(r["is_estimated"]),
        meter_replaced=bool(r["meter_replaced"]),
        rollover_base=_as_dec(r["rollover_base"]) if r["rollover_base"] else None,
        consumption_kwh=_as_dec(r["consumption_kwh"]),
        adjusted_kwh=_as_dec(r["adjusted_kwh"]),
    )


def _row_to_charge(r) -> InvoiceCharge:
    return InvoiceCharge(
        id=r["id"],
        name=r["name"],
        category=ChargeCategory(r["category"]),
        amount=Money.from_db(r["amount"]),
        reason=r["reason"],
        is_fixed=bool(r["is_fixed"]),
        depends_on_consumption=bool(r["depends_on_consumption"]),
        taxable=bool(r["taxable"]),
        in_current_amount=bool(r["in_current_amount"]),
        in_total_due=bool(r["in_total_due"]),
        source=DataSource(r["source"]),
        tariff_fee_id=r["tariff_fee_id"],
    )


# ---------------------------------------------------------------- repositories


class SqliteSubscriberRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get(self, subscriber_id: int) -> Subscriber | None:
        r = self.conn.execute("SELECT * FROM Subscribers WHERE id=?", (subscriber_id,)).fetchone()
        return _row_to_subscriber(r)

    def by_account(self, account_no: str) -> Subscriber | None:
        r = self.conn.execute("SELECT * FROM Subscribers WHERE account_no=? ORDER BY id DESC LIMIT 1", (account_no,)).fetchone()
        return _row_to_subscriber(r)

    def search(self, query: str, limit: int = 50) -> list[Subscriber]:
        q = _like(query)
        rows = self.conn.execute(
            """SELECT * FROM Subscribers
               WHERE name LIKE ? ESCAPE '\\' OR account_no LIKE ? ESCAPE '\\'
                  OR subscription_no LIKE ? ESCAPE '\\'
               ORDER BY name LIMIT ?""",
            (q, q, q, limit),
        ).fetchall()
        return [_row_to_subscriber(r) for r in rows]

    def list_all(self) -> list[Subscriber]:
        rows = self.conn.execute("SELECT * FROM Subscribers ORDER BY name").fetchall()
        return [_row_to_subscriber(r) for r in rows]

    def delete(self, subscriber_id: int) -> None:
        self.conn.execute("DELETE FROM Subscribers WHERE id=?", (subscriber_id,))

    def save(self, s: Subscriber) -> Subscriber:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        if s.id is None:
            cur = self.conn.execute(
                """INSERT INTO Subscribers
                   (subscription_no, account_no, name, address, governorate, qadaa, nahia, house_no,
                    department, subscriber_type, phase, status, previous_debt, notes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s.subscription_no, s.account_no, s.name, s.address, s.governorate, s.qadaa, s.nahia,
                 s.house_no, s.department, s.subscriber_type.value, s.phase.value, s.status,
                 s.previous_debt.to_db(), s.notes, now, now),
            )
            s.id = cur.lastrowid
        else:
            self.conn.execute(
                """UPDATE Subscribers SET
                   subscription_no=?, account_no=?, name=?, address=?, governorate=?, qadaa=?, nahia=?,
                   house_no=?, department=?, subscriber_type=?, phase=?, status=?, previous_debt=?,
                   notes=?, updated_at=? WHERE id=?""",
                (s.subscription_no, s.account_no, s.name, s.address, s.governorate, s.qadaa, s.nahia,
                 s.house_no, s.department, s.subscriber_type.value, s.phase.value, s.status,
                 s.previous_debt.to_db(), s.notes, now, s.id),
            )
        return s


class SqliteMeterRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_for_subscriber(self, subscriber_id: int) -> list[Meter]:
        rows = self.conn.execute("SELECT * FROM Meters WHERE subscriber_id=? ORDER BY id", (subscriber_id,)).fetchall()
        return [_row_to_meter(r) for r in rows]

    def get(self, meter_id: int) -> Meter | None:
        r = self.conn.execute("SELECT * FROM Meters WHERE id=?", (meter_id,)).fetchone()
        return _row_to_meter(r)

    def save(self, m: Meter) -> Meter:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        if m.id is None:
            cur = self.conn.execute(
                """INSERT INTO Meters (subscriber_id, meter_no, serial_no, meter_type, phase, multiplier,
                   status, installed_at, removed_at, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (m.subscriber_id, m.meter_no, m.serial_no, m.meter_type.value, m.phase.value, str(m.multiplier),
                 m.status, m.installed_at.isoformat() if m.installed_at else None,
                 m.removed_at.isoformat() if m.removed_at else None, m.notes, now),
            )
            m.id = cur.lastrowid
        else:
            self.conn.execute(
                """UPDATE Meters SET subscriber_id=?, meter_no=?, serial_no=?, meter_type=?, phase=?,
                   multiplier=?, status=?, installed_at=?, removed_at=?, notes=? WHERE id=?""",
                (m.subscriber_id, m.meter_no, m.serial_no, m.meter_type.value, m.phase.value, str(m.multiplier),
                 m.status, m.installed_at.isoformat() if m.installed_at else None,
                 m.removed_at.isoformat() if m.removed_at else None, m.notes, m.id),
            )
        return m


class SqliteTariffRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_schedules(self, include_inactive: bool = False) -> list[TariffSchedule]:
        sql = "SELECT * FROM TariffSchedules"
        if not include_inactive:
            sql += " WHERE is_active=1"
        sql += " ORDER BY subscriber_type, effective_from DESC, id DESC"
        rows = self.conn.execute(sql).fetchall()
        return _rows_to_schedules(rows, self.conn)

    def get_schedule(self, schedule_id: int) -> TariffSchedule | None:
        r = self.conn.execute("SELECT * FROM TariffSchedules WHERE id=?", (schedule_id,)).fetchone()
        return _row_to_schedule(r, self.conn) if r else None

    def save_schedule(self, s: TariffSchedule) -> TariffSchedule:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        if s.id is None:
            cur = self.conn.execute(
                """INSERT INTO TariffSchedules (name, subscriber_type, method, service_zone, version,
                   effective_from, effective_to, is_active, source, source_date, source_detail, notes, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s.name, s.subscriber_type.value, s.method.value, s.service_zone.value, s.version,
                 s.effective_from.isoformat(), s.effective_to.isoformat() if s.effective_to else None,
                 1 if s.is_active else 0, s.source.value,
                 s.source_date.isoformat() if s.source_date else None, s.source_detail, s.notes, now),
            )
            s.id = cur.lastrowid
            self._save_tiers_and_fees(s)
        else:
            self.conn.execute(
                """UPDATE TariffSchedules SET name=?, subscriber_type=?, method=?, service_zone=?,
                   version=?, effective_from=?, effective_to=?, is_active=?, source=?, source_date=?,
                   source_detail=?, notes=? WHERE id=?""",
                (s.name, s.subscriber_type.value, s.method.value, s.service_zone.value, s.version,
                 s.effective_from.isoformat(), s.effective_to.isoformat() if s.effective_to else None,
                 1 if s.is_active else 0, s.source.value,
                 s.source_date.isoformat() if s.source_date else None, s.source_detail, s.notes, s.id),
            )
            self._replace_tiers_and_fees(s)
        return s

    def delete_schedule(self, schedule_id: int) -> None:
        self.conn.execute("DELETE FROM TariffSchedules WHERE id=?", (schedule_id,))

    def delete_fee(self, fee_id: int) -> None:
        self.conn.execute("DELETE FROM TariffFees WHERE id=?", (fee_id,))

    def _save_tiers_and_fees(self, s: TariffSchedule) -> None:
        for t in s.tiers:
            self._insert_tier(t, s.id)
        for f in s.fixed_fees:
            f.id = None
            self._insert_fee(f, s.id)

    def _replace_tiers_and_fees(self, s: TariffSchedule) -> None:
        self.conn.execute("DELETE FROM TariffTiers WHERE schedule_id=?", (s.id,))
        self.conn.execute("DELETE FROM TariffFees WHERE schedule_id=?", (s.id,))
        for t in s.tiers:
            self._insert_tier(t, s.id)
        for f in s.fixed_fees:
            self._insert_fee(f, s.id)

    def _insert_tier(self, t: TariffTier, schedule_id: int) -> None:
        cur = self.conn.execute(
            "INSERT INTO TariffTiers (schedule_id, tier_no, from_kwh, to_kwh, rate_per_kwh) VALUES (?,?,?,?,?)",
            (schedule_id, t.tier_no, str(t.from_kwh), str(t.to_kwh) if t.to_kwh is not None else None, str(t.rate_per_kwh)),
        )
        t.id = cur.lastrowid

    def _insert_fee(self, f: TariffFee, schedule_id: int) -> None:
        cur = self.conn.execute(
            """INSERT INTO TariffFees (schedule_id, name, category, amount, is_fixed,
               depends_on_consumption, taxable, in_current_amount, in_total_due, reason)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (schedule_id, f.name, f.category.value, f.amount.to_db(),
             1 if f.is_fixed else 0, 1 if f.depends_on_consumption else 0,
             1 if f.taxable else 0, 1 if f.in_current_amount else 0, 1 if f.in_total_due else 0, f.reason),
        )
        f.id = cur.lastrowid


# Sortable invoice-list columns -> SQL expression. Money/quantity columns are stored as exact
# decimal TEXT, so they are cast for ORDERING only (values themselves are never rounded).
_INVOICE_ORDER = {
    "date": "issue_date",
    "no": "invoice_no",
    "name": "subscriber_name COLLATE NOCASE",
    "account": "account_no",
    "kwh": "CAST(adjusted_kwh AS REAL)",
    "total": "CAST(total_due AS REAL)",
    "official": "CAST(NULLIF(official_amount, '') AS REAL)",
    "status": "payment_status",
}


class SqliteInvoiceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._snapshot: tuple | None = None

    # ---- cached read model ------------------------------------------------
    def _version_key(self) -> tuple:
        """Changes whenever ANY row changes: ``total_changes`` covers this connection's own
        writes, ``data_version`` covers commits made by other connections/processes."""
        return (id(self.conn), self.conn.total_changes,
                self.conn.execute("PRAGMA data_version").fetchone()[0])

    def active_snapshot(self) -> list[Invoice]:
        """All ACTIVE invoices, newest first, cached until the data changes.

        Dashboard, analytics and review all need the full list; rebuilding ~9 ``Money``
        values per row on every page switch cost ~35 ms per 1 000 invoices each time.
        The returned list is a copy; the invoices themselves must be treated as read-only.
        """
        key = self._version_key()
        if self._snapshot is None or self._snapshot[0] != key:
            rows = self.conn.execute(
                "SELECT * FROM Invoices WHERE status='ACTIVE' ORDER BY issue_date DESC, id DESC").fetchall()
            self._snapshot = (key, [_row_to_invoice(r) for r in rows])
        return list(self._snapshot[1])

    def invoice_numbers(self, prefix: str = "") -> list[str]:
        """Invoice numbers starting with ``prefix`` - one narrow column instead of full rows."""
        rows = self.conn.execute(
            "SELECT invoice_no FROM Invoices WHERE invoice_no LIKE ? ESCAPE '\\'",
            (_escape_like(prefix) + "%",),
        ).fetchall()
        return [r[0] for r in rows]

    def save(self, invoice: Invoice, reading: InvoiceReading | None, charges: list[InvoiceCharge]) -> Invoice:
        try:
            return self._save(invoice, reading, charges)
        except sqlite3.IntegrityError as exc:
            if "invoice_no" in str(exc):   # UNIQUE index ux_invoices_invoice_no
                raise DuplicateInvoiceNumberError(invoice.invoice_no) from exc
            raise

    def _save(self, invoice: Invoice, reading: InvoiceReading | None, charges: list[InvoiceCharge]) -> Invoice:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        if invoice.id is None:
            cur = self.conn.execute(
                """INSERT INTO Invoices (invoice_no, subscriber_id, account_no, subscription_no, subscriber_name,
                   subscriber_type, issue_date, previous_read_date, current_read_date, previous_reading,
                   current_reading, consumption_kwh, adjusted_kwh, tariff_schedule_id, tariff_version, tariff_name,
                   tariff_source, energy_cost, fixed_fees, additional_fees, discounts, previous_debt, current_amount,
                   total_due, currency, official_amount, comparison_status, comparison_diff, due_date, payment_status,
                   paid_amount, remaining_balance, notes, status, audit_run_id, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (invoice.invoice_no, invoice.subscriber_id, invoice.account_no, invoice.subscription_no,
                 invoice.subscriber_name, invoice.subscriber_type.value, invoice.issue_date.isoformat(),
                 invoice.previous_read_date.isoformat() if invoice.previous_read_date else None,
                 invoice.current_read_date.isoformat() if invoice.current_read_date else None,
                 str(invoice.previous_reading), str(invoice.current_reading), str(invoice.consumption_kwh),
                 str(invoice.adjusted_kwh), invoice.tariff_schedule_id, invoice.tariff_version, invoice.tariff_name,
                 getattr(invoice, "tariff_source", "UNKNOWN"),
                 invoice.energy_cost.to_db(), invoice.fixed_fees.to_db(), invoice.additional_fees.to_db(),
                 invoice.discounts.to_db(), invoice.previous_debt.to_db(), invoice.current_amount.to_db(),
                 invoice.total_due.to_db(), invoice.currency,
                 invoice.official_amount.to_db() if invoice.official_amount is not None else None,
                 invoice.comparison_status, invoice.comparison_diff.to_db() if invoice.comparison_diff is not None else None,
                 invoice.due_date.isoformat() if invoice.due_date else None, invoice.payment_status.value,
                 invoice.paid_amount.to_db(), invoice.remaining_balance.to_db(), invoice.notes,
                 invoice.status.value, invoice.audit_run_id, now, now),
            )
            invoice.id = cur.lastrowid
        else:
            self.conn.execute(
                """UPDATE Invoices SET invoice_no=?, subscriber_id=?, account_no=?, subscription_no=?,
                   subscriber_name=?, subscriber_type=?, issue_date=?, previous_read_date=?, current_read_date=?,
                   previous_reading=?, current_reading=?, consumption_kwh=?, adjusted_kwh=?, tariff_schedule_id=?,
                   tariff_version=?, tariff_name=?, tariff_source=?, energy_cost=?, fixed_fees=?, additional_fees=?,
                   discounts=?, previous_debt=?, current_amount=?, total_due=?, currency=?, official_amount=?,
                   comparison_status=?, comparison_diff=?, due_date=?, payment_status=?, paid_amount=?,
                   remaining_balance=?, notes=?, status=?, audit_run_id=?, updated_at=? WHERE id=?""",
                (invoice.invoice_no, invoice.subscriber_id, invoice.account_no, invoice.subscription_no,
                 invoice.subscriber_name, invoice.subscriber_type.value, invoice.issue_date.isoformat(),
                 invoice.previous_read_date.isoformat() if invoice.previous_read_date else None,
                 invoice.current_read_date.isoformat() if invoice.current_read_date else None,
                 str(invoice.previous_reading), str(invoice.current_reading), str(invoice.consumption_kwh),
                 str(invoice.adjusted_kwh), invoice.tariff_schedule_id, invoice.tariff_version, invoice.tariff_name,
                 getattr(invoice, "tariff_source", "UNKNOWN"),
                 invoice.energy_cost.to_db(), invoice.fixed_fees.to_db(), invoice.additional_fees.to_db(),
                 invoice.discounts.to_db(), invoice.previous_debt.to_db(), invoice.current_amount.to_db(),
                 invoice.total_due.to_db(), invoice.currency,
                 invoice.official_amount.to_db() if invoice.official_amount is not None else None,
                 invoice.comparison_status, invoice.comparison_diff.to_db() if invoice.comparison_diff is not None else None,
                 invoice.due_date.isoformat() if invoice.due_date else None, invoice.payment_status.value,
                 invoice.paid_amount.to_db(), invoice.remaining_balance.to_db(), invoice.notes,
                 invoice.status.value, invoice.audit_run_id, now, invoice.id),
            )

        # readings
        if reading is not None:
            self.conn.execute("DELETE FROM InvoiceReadings WHERE invoice_id=?", (invoice.id,))
            self.conn.execute(
                """INSERT INTO InvoiceReadings (invoice_id, meter_id, meter_no, previous_reading, current_reading,
                   previous_date, current_date, multiplier, scenario, is_estimated, meter_replaced, rollover_base,
                   consumption_kwh, adjusted_kwh) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (invoice.id, reading.meter_id, reading.meter_no or "", str(reading.previous_reading),
                 str(reading.current_reading), reading.previous_date.isoformat(), reading.current_date.isoformat(),
                 str(reading.multiplier), reading.scenario.value, 1 if reading.is_estimated else 0,
                 1 if reading.meter_replaced else 0,
                 str(reading.rollover_base) if reading.rollover_base is not None else None,
                 str(reading.consumption_kwh), str(reading.adjusted_kwh)),
            )

        # charges
        self.conn.execute("DELETE FROM InvoiceCharges WHERE invoice_id=?", (invoice.id,))
        for c in charges:
            self.conn.execute(
                """INSERT INTO InvoiceCharges (invoice_id, name, category, amount, reason, is_fixed,
                   depends_on_consumption, taxable, in_current_amount, in_total_due, source, tariff_fee_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (invoice.id, c.name, c.category.value, c.amount.to_db(), c.reason,
                 1 if c.is_fixed else 0, 1 if c.depends_on_consumption else 0, 1 if c.taxable else 0,
                 1 if c.in_current_amount else 0, 1 if c.in_total_due else 0, c.source.value, c.tariff_fee_id),
            )
        return invoice

    def get(self, invoice_id: int) -> Invoice | None:
        r = self.conn.execute("SELECT * FROM Invoices WHERE id=?", (invoice_id,)).fetchone()
        return _row_to_invoice(r) if r else None

    def by_number(self, invoice_no: str) -> Invoice | None:
        r = self.conn.execute("SELECT * FROM Invoices WHERE invoice_no=? ORDER BY id DESC LIMIT 1", (invoice_no,)).fetchone()
        return _row_to_invoice(r) if r else None

    def list_recent(self, limit: int = 50) -> list[Invoice]:
        rows = self.conn.execute("SELECT * FROM Invoices WHERE status='ACTIVE' ORDER BY issue_date DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [_row_to_invoice(r) for r in rows]

    def search(self, *, query="", subscriber_id=None, payment_status=None, date_from=None, date_to=None,
               status=None, order_by: str = "date", descending: bool = True,
               limit: int = 200, offset: int = 0) -> list[Invoice]:
        sql = "SELECT * FROM Invoices WHERE 1=1"
        params: list[Any] = []
        if query:
            sql += (" AND (invoice_no LIKE ? ESCAPE '\\' OR account_no LIKE ? ESCAPE '\\'"
                    " OR subscription_no LIKE ? ESCAPE '\\' OR subscriber_name LIKE ? ESCAPE '\\')")
            like = _like(query)
            params += [like, like, like, like]
        if status is not None:
            sql += " AND status=?"
            params.append(getattr(status, "value", status))
        if subscriber_id is not None:
            sql += " AND subscriber_id=?"
            params.append(subscriber_id)
        if payment_status is not None:
            sql += " AND payment_status=?"
            params.append(payment_status.value)
        if date_from is not None:
            sql += " AND issue_date>=?"
            params.append(date_from.isoformat())
        if date_to is not None:
            sql += " AND issue_date<=?"
            params.append(date_to.isoformat())
        column = _INVOICE_ORDER.get(order_by, _INVOICE_ORDER["date"])      # whitelist: never user text
        direction = "DESC" if descending else "ASC"
        sql += f" ORDER BY {column} {direction}, id {direction} LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_invoice(r) for r in rows]

    def count(self, **filters) -> int:
        sql = "SELECT COUNT(*) FROM Invoices WHERE 1=1"
        params: list[Any] = []
        if filters.get("payment_status"):
            sql += " AND payment_status=?"
            params.append(filters["payment_status"].value)
        if filters.get("subscriber_id"):
            sql += " AND subscriber_id=?"
            params.append(filters["subscriber_id"])
        if filters.get("date_from") is not None:
            sql += " AND issue_date>=?"
            params.append(filters["date_from"].isoformat())
        if filters.get("date_to") is not None:
            sql += " AND issue_date<=?"
            params.append(filters["date_to"].isoformat())
        if filters.get("query"):          # same predicate as search(query=...)
            sql += (" AND (invoice_no LIKE ? ESCAPE '\\' OR account_no LIKE ? ESCAPE '\\'"
                    " OR subscription_no LIKE ? ESCAPE '\\' OR subscriber_name LIKE ? ESCAPE '\\')")
            like = _like(filters["query"])
            params += [like, like, like, like]
        r = self.conn.execute(sql, params).fetchone()
        return r[0]

    def delete(self, invoice_id: int) -> None:
        self.conn.execute("DELETE FROM Invoices WHERE id=?", (invoice_id,))

    def list_reading(self, invoice_id: int) -> InvoiceReading | None:
        r = self.conn.execute("SELECT * FROM InvoiceReadings WHERE invoice_id=?", (invoice_id,)).fetchone()
        return _row_to_reading(r) if r else None

    def list_charges(self, invoice_id: int) -> list[InvoiceCharge]:
        rows = self.conn.execute("SELECT * FROM InvoiceCharges WHERE invoice_id=? ORDER BY id", (invoice_id,)).fetchall()
        return [_row_to_charge(r) for r in rows]

    def list_payments(self, invoice_id: int) -> list[Payment]:
        rows = self.conn.execute(
            "SELECT * FROM Payments WHERE invoice_id=? ORDER BY paid_at, id", (invoice_id,)).fetchall()
        return [Payment(
            id=r["id"], invoice_id=r["invoice_id"], amount=Money.from_db(r["amount"]),
            paid_at=_as_date(r["paid_at"]), method=r["method"], notes=r["notes"],
            created_at=_as_dt(r["created_at"])) for r in rows]

    def set_status(self, invoice_id: int, status: InvoiceStatus) -> None:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        self.conn.execute("UPDATE Invoices SET status=?, updated_at=? WHERE id=?",
                          (status.value, now, invoice_id))

    def transfer_payments(self, from_id: int, to_id: int) -> None:
        """Move payments (and the paid amount) from a superseded invoice to its replacement."""
        old, new = self.get(from_id), self.get(to_id)
        if old is None or new is None:
            raise ValueError("invoice not found")
        paid = old.paid_amount
        if paid > new.total_due:
            raise InvoiceStateError("overpaid")
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        self.conn.execute("UPDATE Payments SET invoice_id=? WHERE invoice_id=?", (to_id, from_id))
        if paid.raw <= 0:
            return
        status = PaymentStatus.PAID if paid >= new.total_due else PaymentStatus.PARTIAL
        self.conn.execute(
            "UPDATE Invoices SET paid_amount=?, payment_status=?, remaining_balance=?, updated_at=? WHERE id=?",
            (paid.to_db(), status.value, (new.total_due - paid).to_db(), now, to_id))

    def set_payment(self, invoice_id: int, amount, paid_at, method, notes) -> None:
        invoice = self.get(invoice_id)
        if invoice is None:
            raise ValueError("invoice not found")
        paid = Money.of(amount)
        if paid.raw <= 0:
            raise PaymentError("non_positive")
        if invoice.status == InvoiceStatus.CANCELLED:
            raise PaymentError("cancelled")
        if invoice.status != InvoiceStatus.ACTIVE:
            raise PaymentError("inactive")
        if invoice.paid_amount + paid > invoice.total_due:
            raise PaymentError("exceeds")
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        cur = self.conn.execute(
            "INSERT INTO Payments (invoice_id, amount, paid_at, method, notes, created_at) VALUES (?,?,?,?,?,?)",
            (invoice_id, paid.to_db(), paid_at.isoformat(), method, notes, now),
        )
        new_paid = invoice.paid_amount + paid
        status = PaymentStatus.PAID if new_paid >= invoice.total_due else PaymentStatus.PARTIAL
        self.conn.execute(
            "UPDATE Invoices SET paid_amount=?, payment_status=?, remaining_balance=?, updated_at=? WHERE id=?",
            (new_paid.to_db(), status.value, (invoice.total_due - new_paid).to_db(), now, invoice_id),
        )


class SqliteAuditRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def append(self, entry: AuditLogEntry) -> AuditLogEntry:
        cur = self.conn.execute(
            """INSERT INTO AuditLogs (action, entity_type, entity_id, user, description, details_json,
               invoice_id, tariff_schedule_id, run_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (entry.action, entry.entity_type, entry.entity_id, entry.user, entry.description, entry.details_json,
             entry.invoice_id, entry.tariff_schedule_id, entry.run_id, entry.created_at.isoformat()),
        )
        entry.id = cur.lastrowid
        return entry

    def list_for_invoice(self, invoice_id: int, limit: int = 50) -> list[AuditLogEntry]:
        rows = self.conn.execute(
            "SELECT * FROM AuditLogs WHERE invoice_id=? ORDER BY id DESC LIMIT ?",
            (invoice_id, limit),
        ).fetchall()
        return [self._row(r) for r in rows]

    def list_recent(self, limit: int = 100) -> list[AuditLogEntry]:
        rows = self.conn.execute("SELECT * FROM AuditLogs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._row(r) for r in rows]

    def _row(self, r) -> AuditLogEntry:
        return AuditLogEntry(
            id=r["id"],
            action=r["action"],
            entity_type=r["entity_type"],
            entity_id=r["entity_id"],
            user=r["user"],
            description=r["description"],
            details_json=r["details_json"],
            invoice_id=r["invoice_id"],
            tariff_schedule_id=r["tariff_schedule_id"],
            run_id=r["run_id"],
            created_at=_as_dt(r["created_at"]),
        )


class SqlitePaymentRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_for_invoice(self, invoice_id: int) -> list[Payment]:
        rows = self.conn.execute("SELECT * FROM Payments WHERE invoice_id=? ORDER BY paid_at", (invoice_id,)).fetchall()
        return [Payment(
            id=r["id"], invoice_id=r["invoice_id"], amount=Money.from_db(r["amount"]),
            paid_at=_as_date(r["paid_at"]), method=r["method"], notes=r["notes"],
            created_at=_as_dt(r["created_at"]),
        ) for r in rows]


class SqliteDebtRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def active_for_subscriber(self, subscriber_id: int) -> list[Debt]:
        rows = self.conn.execute(
            "SELECT * FROM Debts WHERE subscriber_id=? AND status='ACTIVE' ORDER BY recorded_at",
            (subscriber_id,),
        ).fetchall()
        return [Debt(
            id=r["id"], subscriber_id=r["subscriber_id"], amount=Money.from_db(r["amount"]),
            reason=r["reason"], recorded_at=_as_date(r["recorded_at"]),
            status=r["status"], notes=r["notes"],
        ) for r in rows]


class SqliteSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get(self, key: str, default: str = "") -> str:
        r = self.conn.execute("SELECT value FROM Settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set(self, key: str, value: str, source=DataSource.USER_DEFINED) -> None:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO Settings (key, value, source, updated_at) VALUES (?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, source=excluded.source, updated_at=excluded.updated_at""",
            (key, value, source.value, now),
        )


class SqliteUnitOfWork:
    """Simple unit of work bound to a connection; commit delegates to the connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def clear(self) -> None:
        pass


def build_repositories(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "subscribers": SqliteSubscriberRepository(conn),
        "meters": SqliteMeterRepository(conn),
        "tariffs": SqliteTariffRepository(conn),
        "invoices": SqliteInvoiceRepository(conn),
        "audit": SqliteAuditRepository(conn),
        "payments": SqlitePaymentRepository(conn),
        "debts": SqliteDebtRepository(conn),
        "settings": SqliteSettingsRepository(conn),
        "uow": SqliteUnitOfWork(conn),
    }