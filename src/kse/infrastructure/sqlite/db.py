"""SQLite persistence — connection factory, migrations, DDL."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2


def default_data_dir() -> Path:
    base = os.environ.get("KSE_DATA_DIR")
    if base:
        return Path(base)
    home = Path.home()
    return home / ".kahraba_smart"


def default_db_path() -> Path:
    return default_data_dir() / "kahraba.db"


def connect(db_path=None) -> sqlite3.Connection:
    if db_path == ":memory:":
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        run_migrations(conn)
        return conn
    path = Path(db_path or default_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    run_migrations(conn)
    return conn


MIGRATION_1_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS Subscribers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_no  TEXT NOT NULL,
    account_no       TEXT NOT NULL,
    name             TEXT NOT NULL,
    address          TEXT NOT NULL DEFAULT '',
    governorate      TEXT NOT NULL DEFAULT '',
    qadaa            TEXT NOT NULL DEFAULT '',
    nahia            TEXT NOT NULL DEFAULT '',
    house_no         TEXT NOT NULL DEFAULT '',
    department       TEXT NOT NULL DEFAULT '',
    subscriber_type  TEXT NOT NULL DEFAULT 'RESIDENTIAL',
    phase            TEXT NOT NULL DEFAULT 'SINGLE',
    status           TEXT NOT NULL DEFAULT 'ACTIVE',
    previous_debt    TEXT NOT NULL DEFAULT '0',
    notes            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_subscribers_account  ON Subscribers(account_no);
CREATE INDEX IF NOT EXISTS ix_subscribers_type    ON Subscribers(subscriber_type);
CREATE INDEX IF NOT EXISTS ix_subscribers_name    ON Subscribers(name);

CREATE TABLE IF NOT EXISTS Meters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES Subscribers(id) ON DELETE CASCADE,
    meter_no      TEXT NOT NULL,
    serial_no     TEXT NOT NULL DEFAULT '',
    meter_type    TEXT NOT NULL DEFAULT 'ELECTROMECHANICAL',
    phase         TEXT NOT NULL DEFAULT 'SINGLE',
    multiplier    TEXT NOT NULL DEFAULT '1',
    status        TEXT NOT NULL DEFAULT 'ACTIVE',
    installed_at  TEXT,
    removed_at    TEXT,
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_meters_subscriber ON Meters(subscriber_id);
CREATE INDEX IF NOT EXISTS ix_meters_number     ON Meters(meter_no);

CREATE TABLE IF NOT EXISTS TariffSchedules (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar          TEXT NOT NULL,
    name_en          TEXT NOT NULL DEFAULT '',
    subscriber_type  TEXT NOT NULL,
    method           TEXT NOT NULL DEFAULT 'FLAT',
    version          TEXT NOT NULL DEFAULT '1',
    effective_from   TEXT NOT NULL,
    effective_to     TEXT,
    is_active        INTEGER NOT NULL DEFAULT 1,
    source           TEXT NOT NULL DEFAULT 'UNKNOWN',
    source_date      TEXT,
    source_detail    TEXT NOT NULL DEFAULT '',
    notes            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tariff_type_date ON TariffSchedules(subscriber_type, effective_from);

CREATE TABLE IF NOT EXISTS TariffTiers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id  INTEGER NOT NULL REFERENCES TariffSchedules(id) ON DELETE CASCADE,
    tier_no      INTEGER NOT NULL,
    from_kwh     TEXT NOT NULL,
    to_kwh       TEXT,
    rate_per_kwh TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_tiers_schedule ON TariffTiers(schedule_id);

CREATE TABLE IF NOT EXISTS TariffFees (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id       INTEGER NOT NULL REFERENCES TariffSchedules(id) ON DELETE CASCADE,
    name_ar           TEXT NOT NULL,
    name_en           TEXT NOT NULL DEFAULT '',
    category          TEXT NOT NULL DEFAULT 'FIXED_FEE',
    amount            TEXT NOT NULL DEFAULT '0',
    is_fixed          INTEGER NOT NULL DEFAULT 1,
    depends_on_consumption INTEGER NOT NULL DEFAULT 0,
    taxable           INTEGER NOT NULL DEFAULT 0,
    in_current_amount INTEGER NOT NULL DEFAULT 1,
    in_total_due      INTEGER NOT NULL DEFAULT 1,
    reason            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_tarifffees_schedule ON TariffFees(schedule_id);

CREATE TABLE IF NOT EXISTS Invoices (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no         TEXT NOT NULL,
    subscriber_id      INTEGER REFERENCES Subscribers(id) ON DELETE SET NULL,
    account_no         TEXT NOT NULL DEFAULT '',
    subscription_no    TEXT NOT NULL DEFAULT '',
    subscriber_name    TEXT NOT NULL DEFAULT '',
    subscriber_type    TEXT NOT NULL DEFAULT 'RESIDENTIAL',
    issue_date         TEXT NOT NULL,
    previous_read_date TEXT,
    current_read_date  TEXT,
    previous_reading   TEXT NOT NULL DEFAULT '0',
    current_reading    TEXT NOT NULL DEFAULT '0',
    consumption_kwh    TEXT NOT NULL DEFAULT '0',
    adjusted_kwh       TEXT NOT NULL DEFAULT '0',
    tariff_schedule_id INTEGER REFERENCES TariffSchedules(id) ON DELETE SET NULL,
    tariff_version     TEXT NOT NULL DEFAULT '',
    tariff_name        TEXT NOT NULL DEFAULT '',
    tariff_source      TEXT NOT NULL DEFAULT 'UNKNOWN',
    energy_cost        TEXT NOT NULL DEFAULT '0',
    fixed_fees         TEXT NOT NULL DEFAULT '0',
    additional_fees    TEXT NOT NULL DEFAULT '0',
    discounts          TEXT NOT NULL DEFAULT '0',
    previous_debt      TEXT NOT NULL DEFAULT '0',
    current_amount     TEXT NOT NULL DEFAULT '0',
    total_due          TEXT NOT NULL DEFAULT '0',
    currency           TEXT NOT NULL DEFAULT 'IQD',
    official_amount    TEXT,
    comparison_status  TEXT NOT NULL DEFAULT 'NOT_COMPARED',
    comparison_diff    TEXT,
    due_date           TEXT,
    payment_status     TEXT NOT NULL DEFAULT 'UNPAID',
    paid_amount        TEXT NOT NULL DEFAULT '0',
    remaining_balance  TEXT NOT NULL DEFAULT '0',
    notes              TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'ACTIVE',
    audit_run_id       TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_invoices_subscriber   ON Invoices(subscriber_id);
CREATE INDEX IF NOT EXISTS ix_invoices_issue_date   ON Invoices(issue_date);
CREATE INDEX IF NOT EXISTS ix_invoices_invoice_no   ON Invoices(invoice_no);
CREATE INDEX IF NOT EXISTS ix_invoices_pay_status   ON Invoices(payment_status);
CREATE INDEX IF NOT EXISTS ix_invoices_account      ON Invoices(account_no);
CREATE INDEX IF NOT EXISTS ix_invoices_created      ON Invoices(created_at);

CREATE TABLE IF NOT EXISTS InvoiceReadings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id        INTEGER NOT NULL REFERENCES Invoices(id) ON DELETE CASCADE,
    meter_id          INTEGER REFERENCES Meters(id) ON DELETE SET NULL,
    meter_no          TEXT NOT NULL DEFAULT '',
    previous_reading  TEXT NOT NULL,
    current_reading   TEXT NOT NULL,
    previous_date     TEXT NOT NULL,
    current_date      TEXT NOT NULL,
    multiplier        TEXT NOT NULL DEFAULT '1',
    scenario          TEXT NOT NULL DEFAULT 'NORMAL',
    is_estimated      INTEGER NOT NULL DEFAULT 0,
    meter_replaced    INTEGER NOT NULL DEFAULT 0,
    rollover_base     TEXT,
    consumption_kwh   TEXT NOT NULL,
    adjusted_kwh      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_readings_invoice ON InvoiceReadings(invoice_id);

CREATE TABLE IF NOT EXISTS InvoiceCharges (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id          INTEGER NOT NULL REFERENCES Invoices(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    name_en             TEXT NOT NULL DEFAULT '',
    category            TEXT NOT NULL DEFAULT 'FIXED_FEE',
    amount              TEXT NOT NULL DEFAULT '0',
    reason              TEXT NOT NULL DEFAULT '',
    is_fixed            INTEGER NOT NULL DEFAULT 1,
    depends_on_consumption INTEGER NOT NULL DEFAULT 0,
    taxable             INTEGER NOT NULL DEFAULT 0,
    in_current_amount   INTEGER NOT NULL DEFAULT 1,
    in_total_due        INTEGER NOT NULL DEFAULT 1,
    source              TEXT NOT NULL DEFAULT 'USER_DEFINED',
    tariff_fee_id       INTEGER
);
CREATE INDEX IF NOT EXISTS ix_charges_invoice ON InvoiceCharges(invoice_id);

CREATE TABLE IF NOT EXISTS Payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id  INTEGER NOT NULL REFERENCES Invoices(id) ON DELETE CASCADE,
    amount      TEXT NOT NULL,
    paid_at     TEXT NOT NULL,
    method      TEXT NOT NULL DEFAULT 'CASH',
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_payments_invoice ON Payments(invoice_id);

CREATE TABLE IF NOT EXISTS Debts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER REFERENCES Subscribers(id) ON DELETE SET NULL,
    amount        TEXT NOT NULL,
    reason        TEXT NOT NULL DEFAULT '',
    recorded_at   TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'ACTIVE',
    notes         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_debts_subscriber ON Debts(subscriber_id);

CREATE TABLE IF NOT EXISTS Settings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL UNIQUE,
    value      TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'USER_DEFINED',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS AuditLogs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    action             TEXT NOT NULL,
    entity_type        TEXT NOT NULL,
    entity_id          INTEGER,
    user               TEXT NOT NULL DEFAULT 'local',
    description        TEXT NOT NULL DEFAULT '',
    details_json       TEXT NOT NULL,
    invoice_id         INTEGER REFERENCES Invoices(id) ON DELETE SET NULL,
    tariff_schedule_id INTEGER,
    run_id             TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_invoice ON AuditLogs(invoice_id);
CREATE INDEX IF NOT EXISTS ix_audit_entity  ON AuditLogs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_audit_created ON AuditLogs(created_at);
CREATE INDEX IF NOT EXISTS ix_audit_run     ON AuditLogs(run_id);
"""

MIGRATION_2_DDL = """
ALTER TABLE TariffSchedules ADD COLUMN service_zone TEXT NOT NULL DEFAULT 'TRADITIONAL';
"""

MIGRATIONS = [
    (1, MIGRATION_1_DDL),
    (2, MIGRATION_2_DDL),
]


def run_migrations(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    for version, ddl in MIGRATIONS:
        if version not in applied:
            conn.executescript(ddl)
            conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
    conn.commit()


def check_schema(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return row["v"] if row else 0