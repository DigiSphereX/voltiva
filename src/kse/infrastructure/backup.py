"""Database backup & restore (spec §32)."""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
from pathlib import Path

from .sqlite.db import SCHEMA_VERSION

# Tables a file must contain to be accepted as a Voltiva backup.
_REQUIRED_TABLES = frozenset({
    "Subscribers", "Meters", "TariffSchedules", "TariffTiers", "Invoices",
    "Payments", "Settings", "schema_migrations",
})


class InvalidBackupError(ValueError):
    """The selected file is not a healthy, compatible Voltiva database."""


def validate_backup(source_db: str | Path) -> None:
    """Refuse anything that is not an intact, non-future Voltiva database.

    Restoring blindly used to overwrite the live database with whatever file the
    user picked (any ``.db``, a corrupt file, or a database from a newer version),
    after the app had already closed its connection.
    """
    source_db = Path(source_db)
    if not source_db.is_file():
        raise FileNotFoundError("The backup file does not exist.")
    try:
        # read-only URI: never creates/modifies the candidate file
        uri = source_db.resolve().as_uri() + "?mode=ro"
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise InvalidBackupError("The file is not a valid SQLite database.") from exc
    try:
        try:
            check = con.execute("PRAGMA integrity_check").fetchone()
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] \
                if "schema_migrations" in tables else None
        except sqlite3.Error as exc:
            raise InvalidBackupError("The file is not a valid SQLite database.") from exc
        if not check or check[0] != "ok":
            raise InvalidBackupError("The backup file is corrupt (integrity check failed).")
        missing = _REQUIRED_TABLES - tables
        if missing:
            raise InvalidBackupError("The file is not a backup produced by this application.")
        if version is not None and version > SCHEMA_VERSION:
            raise InvalidBackupError("The backup is newer than the current application version.")
    finally:
        con.close()


def _copy_db(src_path: Path, dest_path: Path) -> None:
    src = sqlite3.connect(str(src_path))
    target = sqlite3.connect(str(dest_path))
    try:
        src.backup(target)
    finally:
        target.close()
        src.close()


def backup_database(db_path: str | Path, dest: str | Path | None = None) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if dest is None:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dest = db_path.parent / f"voltiva_backup_{stamp}.db"
    dest = Path(dest)
    if dest.exists() and dest.resolve() == db_path.resolve():
        raise ValueError("A backup cannot be written over the live database file itself.")
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Snapshot with the SQLite online-backup API into a temp file, then move it into
    # place atomically so a crash never leaves a truncated "backup" behind.
    tmp = dest.with_name(dest.name + ".part")
    try:
        _copy_db(db_path, tmp)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return dest


AUTO_PREFIX = "voltiva_autobackup_"
# Voltiva 1.1 and earlier wrote auto-backups under the legacy product prefix;
# they are still this application's own generated files, so they keep being
# pruned alongside the new ones.
_LEGACY_AUTO_PREFIX = "kahraba_autobackup_"
DEFAULT_KEEP = 10


def auto_backup(conn: sqlite3.Connection, db_path: str | Path, *, keep: int = DEFAULT_KEEP) -> Path:
    """Snapshot the LIVE connection into ``<data dir>/backups`` and keep the newest ``keep`` copies.

    Uses SQLite's online-backup API (consistent even with WAL), writes to a ``.part`` file,
    verifies it with :func:`validate_backup`, then moves it into place - a failed or
    half-written snapshot never replaces or counts as a good backup. Only files created by this
    function (``voltiva_autobackup_*.db``) are ever pruned; manual backups are never touched.
    """
    folder = Path(db_path).parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{AUTO_PREFIX}{dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
    tmp = dest.with_name(dest.name + ".part")
    try:
        target = sqlite3.connect(str(tmp))
        try:
            conn.backup(target)
        finally:
            target.close()
        validate_backup(tmp)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    managed = sorted(p for p in folder.glob(f"{AUTO_PREFIX}*.db"))
    managed += sorted(p for p in folder.glob(f"{_LEGACY_AUTO_PREFIX}*.db"))
    for path in managed[:-max(1, keep)] if len(managed) > keep else []:
        try:
            path.unlink()
        except OSError:
            pass
    return dest


def restore_database(db_path: str | Path, source_db: str | Path) -> Path:
    """Restore a backup into the live location (replaces live content).

    Safety: refuses same-file restores and anything that fails
    :func:`validate_backup`; keeps a pre-restore snapshot of the live database.
    """
    db_path = Path(db_path)
    source_db = Path(source_db)
    if db_path.exists() and source_db.exists() and source_db.resolve() == db_path.resolve():
        raise ValueError("A database cannot be restored from itself.")
    validate_backup(source_db)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        backup_database(db_path)  # safety copy before overwrite
    _copy_db(source_db, db_path)
    return db_path
