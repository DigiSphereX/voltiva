"""SQLite persistence — connection factory, migrations, DDL."""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 5


def default_data_dir() -> Path:
    base = os.environ.get("KSE_DATA_DIR")
    if base:
        return Path(base)
    return Path.home() / ".voltiva"


# Voltiva 1.1 and earlier stored the database under the legacy product name.
_LEGACY_DATA_DIR = ".kahraba_smart"
_LEGACY_DB_NAME = "kahraba.db"


def _adopt_legacy_database(dest: Path, legacy: Path) -> None:
    """Carry a legacy 1.1 database over to the new location (one-time).

    Uses SQLite's backup API so a legacy WAL file is folded in correctly; the
    legacy copy itself is left untouched as a safety net. Any error is raised
    loudly rather than silently starting an empty database.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(legacy))
    try:
        target = sqlite3.connect(str(dest))
        try:
            src.backup(target)
        finally:
            target.close()
    finally:
        src.close()


def default_db_path() -> Path:
    path = default_data_dir() / "voltiva.db"
    if not os.environ.get("KSE_DATA_DIR"):
        legacy = Path.home() / _LEGACY_DATA_DIR / _LEGACY_DB_NAME
        if not path.exists() and legacy.is_file():
            _adopt_legacy_database(path, legacy)
    return path


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
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-16000")  # ~16 MB page cache
    conn.execute("PRAGMA trusted_schema=OFF")
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
    name             TEXT NOT NULL DEFAULT '',
    subscriber_type  TEXT NOT NULL,
    method           TEXT NOT NULL DEFAULT 'FLAT',
    service_zone     TEXT NOT NULL DEFAULT 'TRADITIONAL',
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
    name              TEXT NOT NULL DEFAULT '',
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
    name                TEXT NOT NULL DEFAULT '',
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

# Composite / partial indexes that match the app's hottest queries
# (dashboard + analytics filter on status and order by issue_date; payments are
# looked up per invoice; tariff lookups filter by active flag).
MIGRATION_3_DDL = """
CREATE INDEX IF NOT EXISTS ix_invoices_status_date ON Invoices(status, issue_date DESC, id DESC);
CREATE INDEX IF NOT EXISTS ix_invoices_subscriber_date ON Invoices(subscriber_id, issue_date);
CREATE INDEX IF NOT EXISTS ix_payments_paid_at ON Payments(paid_at);
CREATE INDEX IF NOT EXISTS ix_tariff_active ON TariffSchedules(is_active, subscriber_type, effective_from);
"""

def _migration_4_unique_invoice_no(conn: sqlite3.Connection) -> None:
    """Make invoice numbers unique.

    Databases created by older versions may already contain duplicates (the old numbering
    scanned only the latest 500 rows). A UNIQUE index would fail on them, so duplicates are
    renumbered first: the OLDEST invoice keeps its number, later ones become
    ``<no>-D2``, ``<no>-D3`` ... and every change is written to the audit log.
    Empty numbers are excluded from the index.
    """
    dups = [r[0] for r in conn.execute(
        "SELECT invoice_no FROM Invoices WHERE invoice_no <> '' "
        "GROUP BY invoice_no HAVING COUNT(*) > 1")]
    for number in dups:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM Invoices WHERE invoice_no=? ORDER BY id", (number,))]
        for rid in ids[1:]:
            n = 2
            while True:
                candidate = f"{number}-D{n}"
                if not conn.execute("SELECT 1 FROM Invoices WHERE invoice_no=?", (candidate,)).fetchone():
                    break
                n += 1
            conn.execute("UPDATE Invoices SET invoice_no=? WHERE id=?", (candidate, rid))
            conn.execute(
                "INSERT INTO AuditLogs (action, entity_type, entity_id, user, description, details_json,"
                " invoice_id, created_at) VALUES ('MIGRATION_RENUMBER', 'INVOICE', ?, 'migration', ?, ?, ?,"
                " datetime('now'))",
                (rid, f"Duplicate invoice number {number} renumbered to {candidate}",
                 '{"old": "%s", "new": "%s"}' % (number, candidate), rid))
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_invoices_invoice_no "
                 "ON Invoices(invoice_no) WHERE invoice_no <> ''")


MIGRATION_5_SCHEDULES_DDL = """
CREATE TABLE TariffSchedules_new (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL DEFAULT '',
    subscriber_type  TEXT NOT NULL,
    method           TEXT NOT NULL DEFAULT 'FLAT',
    service_zone     TEXT NOT NULL DEFAULT 'TRADITIONAL',
    version          TEXT NOT NULL DEFAULT '1',
    effective_from   TEXT NOT NULL,
    effective_to     TEXT,
    is_active        INTEGER NOT NULL DEFAULT 1,
    source           TEXT NOT NULL DEFAULT 'UNKNOWN',
    source_date      TEXT,
    source_detail    TEXT NOT NULL DEFAULT '',
    notes            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL
)
"""

MIGRATION_5_FEES_DDL = """
CREATE TABLE TariffFees_new (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id       INTEGER NOT NULL REFERENCES TariffSchedules(id) ON DELETE CASCADE,
    name              TEXT NOT NULL DEFAULT '',
    category          TEXT NOT NULL DEFAULT 'FIXED_FEE',
    amount            TEXT NOT NULL DEFAULT '0',
    is_fixed          INTEGER NOT NULL DEFAULT 1,
    depends_on_consumption INTEGER NOT NULL DEFAULT 0,
    taxable           INTEGER NOT NULL DEFAULT 0,
    in_current_amount INTEGER NOT NULL DEFAULT 1,
    in_total_due      INTEGER NOT NULL DEFAULT 1,
    reason            TEXT NOT NULL DEFAULT ''
)
"""

MIGRATION_5_CHARGES_DDL = """
CREATE TABLE InvoiceCharges_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id          INTEGER NOT NULL REFERENCES Invoices(id) ON DELETE CASCADE,
    name                TEXT NOT NULL DEFAULT '',
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
)
"""


def _migration_5_single_name(conn: sqlite3.Connection) -> None:
    """Merge the bilingual tariff-name columns into a single ``name`` column.

    Voltiva 2.0 of the data model is English-only: TariffSchedules and
    TariffFees carried ``name_ar`` + ``name_en``, InvoiceCharges carried
    ``name`` (Arabic) + ``name_en``. SQLite cannot drop a column portably
    across versions, so each table is rebuilt (create new, copy, drop old,
    rename) with foreign keys disabled for the move, as the SQLite
    documentation prescribes. The merged value keeps the English name; a
    legacy Arabic-only name is carried over rather than lost.
    """
    if _column_exists(conn, "TariffSchedules", "name"):
        return                        # fresh database (already the new schema)

    conn.commit()                     # PRAGMA foreign_keys is a no-op inside a transaction
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(MIGRATION_5_SCHEDULES_DDL)
            conn.execute(
                """INSERT INTO TariffSchedules_new
                   (id, name, subscriber_type, method, service_zone, version, effective_from,
                    effective_to, is_active, source, source_date, source_detail, notes, created_at)
                   SELECT id,
                          COALESCE(NULLIF(name_en, ''), NULLIF(name_ar, ''), 'Tariff'),
                          subscriber_type, method,
                          COALESCE(service_zone, 'TRADITIONAL'),
                          version, effective_from, effective_to, is_active, source,
                          source_date, source_detail, notes, created_at
                   FROM TariffSchedules""")
            conn.execute("DROP TABLE TariffSchedules")
            conn.execute("ALTER TABLE TariffSchedules_new RENAME TO TariffSchedules")

            conn.execute(MIGRATION_5_FEES_DDL)
            conn.execute(
                """INSERT INTO TariffFees_new
                   (id, schedule_id, name, category, amount, is_fixed, depends_on_consumption,
                    taxable, in_current_amount, in_total_due, reason)
                   SELECT id, schedule_id,
                          COALESCE(NULLIF(name_en, ''), NULLIF(name_ar, ''), 'Fee'),
                          category, amount, is_fixed, depends_on_consumption,
                          taxable, in_current_amount, in_total_due, reason
                   FROM TariffFees""")
            conn.execute("DROP TABLE TariffFees")
            conn.execute("ALTER TABLE TariffFees_new RENAME TO TariffFees")

            conn.execute(MIGRATION_5_CHARGES_DDL)
            conn.execute(
                """INSERT INTO InvoiceCharges_new
                   (id, invoice_id, name, category, amount, reason, is_fixed,
                    depends_on_consumption, taxable, in_current_amount, in_total_due,
                    source, tariff_fee_id)
                   SELECT id, invoice_id,
                          COALESCE(NULLIF(name_en, ''), NULLIF(name, ''), 'Fee'),
                          category, amount, reason, is_fixed,
                          depends_on_consumption, taxable, in_current_amount, in_total_due,
                          source, tariff_fee_id
                   FROM InvoiceCharges""")
            conn.execute("DROP TABLE InvoiceCharges")
            conn.execute("ALTER TABLE InvoiceCharges_new RENAME TO InvoiceCharges")

            # The indexes were dropped together with the old tables.
            conn.execute("CREATE INDEX IF NOT EXISTS ix_tariff_type_date "
                         "ON TariffSchedules(subscriber_type, effective_from)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_tariff_active "
                         "ON TariffSchedules(is_active, subscriber_type, effective_from)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_tarifffees_schedule "
                         "ON TariffFees(schedule_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_charges_invoice "
                         "ON InvoiceCharges(invoice_id)")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise RuntimeError(f"foreign key check failed after migration 5: {problems}")
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


_migration_5_single_name.plain = True


MIGRATIONS = [
    (1, MIGRATION_1_DDL),
    (2, MIGRATION_2_DDL),
    (3, MIGRATION_3_DDL),
    (4, _migration_4_unique_invoice_no),
    (5, _migration_5_single_name),
]


_ADD_COLUMN_RE = re.compile(r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", re.IGNORECASE)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def _apply_migration(conn: sqlite3.Connection, version: int, ddl: str) -> None:
    """Apply one migration all-or-nothing.

    ``executescript`` silently COMMITs first and is not transactional, so a crash
    between the DDL and the ``schema_migrations`` insert used to leave a
    half-migrated database (e.g. ``duplicate column name`` on the next start).
    Statements are now run one by one inside an explicit transaction, and
    ``ALTER TABLE ... ADD COLUMN`` is skipped when the column already exists.

    Migrations flagged ``plain`` rebuild tables and must toggle
    ``PRAGMA foreign_keys`` (a no-op inside a transaction), so they manage their
    own transaction and run outside one.
    """
    if callable(ddl) and getattr(ddl, "plain", False):
        ddl(conn)
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (version,))
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        if callable(ddl):                      # data migration written in Python
            ddl(conn)
        else:
            for stmt in (s.strip() for s in ddl.split(";") if s.strip()):
                m = _ADD_COLUMN_RE.match(stmt)
                if m and _column_exists(conn, m.group(1), m.group(2)):
                    continue  # already applied by an interrupted earlier run
                conn.execute(stmt)
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (version,))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def run_migrations(conn: sqlite3.Connection) -> None:
    conn.commit()
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    for version, ddl in MIGRATIONS:
        if version not in applied:
            _apply_migration(conn, version, ddl)
    conn.commit()


def check_schema(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return row["v"] if row else 0