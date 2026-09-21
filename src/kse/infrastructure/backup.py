"""Database backup & restore (spec §32)."""
from __future__ import annotations

import datetime as dt
import shutil
import sqlite3
from pathlib import Path


def backup_database(db_path: str | Path, dest: str | Path | None = None) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if dest is None:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = db_path.parent / f"kahraba_backup_{stamp}.db"
    dest = Path(dest)

    # Use the SQLite online backup API for a consistent snapshot.
    src = sqlite3.connect(str(db_path))
    target = sqlite3.connect(str(dest))
    try:
        src.backup(target)
    finally:
        target.close()
        src.close()
    return dest


def restore_database(db_path: str | Path, source_db: str | Path) -> Path:
    """Restore a backup into the live location (replaces live file).

    Safety: refuses to run if source and destination are the same file.
    """
    db_path = Path(db_path)
    source_db = Path(source_db)
    if source_db.resolve() == db_path.resolve():
        raise ValueError("لا يمكن الاستعادة من نفس ملف قاعدة البيانات.")
    if not source_db.exists():
        raise FileNotFoundError("ملف النسخة الاحتياطية غير موجود.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    backup_database(db_path)  # safety blob before overwrite
    src = sqlite3.connect(str(source_db))
    target = sqlite3.connect(str(db_path))
    try:
        src.backup(target)
    finally:
        target.close()
        src.close()
    return db_path