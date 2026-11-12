from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from ..application.analytics import AnalyticsService
from ..application.services import InvoiceService, SubscriberService, TariffService
from ..domain.enums import DataSource
from ..infrastructure.backup import auto_backup, backup_database, restore_database, validate_backup
from ..infrastructure.sqlite.db import connect, default_db_path
from ..infrastructure.sqlite.repositories import build_repositories
from ..infrastructure.sqlite.seed import seed
from . import theme
from .currencies import CURRENCIES, set_currency_code
from .i18n import I18n
from .widgets import set_ui_lang


class AppContext:
    DEFAULT_ICON = str(Path(__file__).resolve().parents[3] / "energy.ico")

    def __init__(self, db_path: str | Path | None = None, *, lang: str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.conn: sqlite3.Connection = connect(self.db_path)
        self._closed = False
        self.repos = build_repositories(self.conn)
        self.i18n = I18n(lang or self.effective_language())
        set_ui_lang(self.i18n.lang)
        self._build_services()
        self._nav_handler = None
        self._invoice_handler = None
        self._icon_handler = None
        self._refresh_listeners: list = []
        self._theme_listeners: list = []
        self.seed_if_empty()
        self._baseline_changes = self.conn.total_changes   # writes made after this point are "this session"
        theme.set_current(self.current_theme())
        set_currency_code(self.effective_currency())

    def set_navigation_handler(self, fn) -> None:
        self._nav_handler = fn

    def _build_services(self) -> None:
        """Bind application services to the current repository set."""
        self.tariffs = TariffService(self.repos["tariffs"], self.repos["audit"], self.repos["uow"],
                                     tr=self.i18n.tr)
        self.invoices = InvoiceService(
            self.repos["invoices"], self.repos["tariffs"], self.repos["subscribers"],
            self.repos["audit"], self.repos["uow"], tr=self.i18n.tr)
        self.subscribers = SubscriberService(
            self.repos["subscribers"], self.repos["meters"], self.repos["tariffs"],
            self.repos["debts"], self.repos["uow"], tr=self.i18n.tr)
        self.analytics = AnalyticsService(self.repos["invoices"])

    def set_invoice_handler(self, fn) -> None:
        self._invoice_handler = fn

    def set_icon_handler(self, fn) -> None:
        self._icon_handler = fn

    def on_refresh(self, fn) -> None:
        """Register a callback invoked when the UI needs a full re-render (e.g. theme change)."""
        self._refresh_listeners.append(fn)

    def notify_refresh(self) -> None:
        for fn in list(self._refresh_listeners):
            fn()

    def on_theme(self, fn) -> None:
        """Register a callback invoked after the active palette changes."""
        self._theme_listeners.append(fn)

    def notify_theme(self) -> None:
        for fn in list(self._theme_listeners):
            fn()

    def current_theme_mode(self) -> str:
        """Persisted appearance: "auto" or any palette name ("light", "dark", ...).

        Migrates the legacy single-value "theme" setting (light/dark) into a mode.
        """
        try:
            stored = self.repos["settings"].get("theme_mode", "")
        except Exception:
            stored = ""
        if stored in theme.THEME_MODES:
            return stored
        try:
            legacy = self.repos["settings"].get("theme", "")
        except Exception:
            legacy = ""
        if legacy in ("dark", "light"):
            return legacy
        return theme.THEME_AUTO

    def current_theme(self) -> str:
        """The resolved, effective palette name (auto follows the OS)."""
        return theme.resolve_theme_name(self.current_theme_mode())

    def set_theme_mode(self, mode: str) -> str:
        """Persist the appearance choice (auto or a palette) and apply it."""
        mode = mode if mode in theme.THEME_MODES else theme.THEME_AUTO
        try:
            self.repos["settings"].set("theme_mode", mode, DataSource.USER_DEFINED)
            self.conn.commit()
        except Exception:
            pass
        name = self.apply_theme()
        self.notify_theme()
        return name

    def set_theme(self, name: str) -> str:
        """Explicit palette choice - stores it as a fixed mode."""
        name = name if name in theme.palette_names() else theme.THEME_LIGHT
        return self.set_theme_mode(name)

    def apply_theme(self) -> str:
        """Apply the resolved theme to the running QApplication (QSS + palette)."""
        from PyQt6.QtWidgets import QApplication

        name = theme.resolve_theme_name(self.current_theme_mode())
        theme.set_current(name)
        app = QApplication.instance()
        if app is not None:
            theme.apply(app, name, rtl=self.i18n.rtl)
        return name

    def set_language(self, lang: str) -> bool:
        """Switch UI language; False when the language is not available."""
        if lang not in I18n.AVAILABLE_LANGS:
            return False
        set_ui_lang(lang)          # before listeners rebuild pages / calendars
        self.i18n.set_lang(lang)
        return True

    def current_currency(self) -> str:
        """The resolved, effective display currency code (auto-resolved from the system when preferred)."""
        return self.effective_currency()

    def current_language_pref(self) -> str:
        """Persisted language preference: "auto" or one of I18n.AVAILABLE_LANGS."""
        try:
            stored = self.repos["settings"].get("lang_pref", "")
        except Exception:
            stored = ""
        if stored in ("auto",) + I18n.AVAILABLE_LANGS:
            return stored
        return I18n.DEFAULT

    def current_currency_pref(self) -> str:
        """Persisted currency preference: "auto" or a currency code (migrates the legacy "currency" key)."""
        try:
            stored = self.repos["settings"].get("currency_pref", "")
        except Exception:
            stored = ""
        if stored in ("auto",) or stored in CURRENCIES:
            return stored
        try:
            legacy = self.repos["settings"].get("currency", "USD")
        except Exception:
            legacy = "USD"
        if legacy in CURRENCIES:
            return legacy
        return "auto"

    def _system_language(self) -> str:
        """Resolve the display language from the Windows/system locale (ar_IQ -> ar)."""
        try:
            from PyQt6.QtCore import QLocale  # noqa: PLC0415
        except Exception:
            return I18n.DEFAULT
        try:
            name = QLocale.system().name().lower()
        except Exception:
            return I18n.DEFAULT
        for sep in ("_", "-"):
            tag = name.split(sep)[0]
            if tag in I18n.AVAILABLE_LANGS:
                return tag
        return I18n.DEFAULT

    def _system_currency(self) -> str:
        """Resolve the currency code from the Windows/system locale (ar_IQ -> IQD, en_US -> USD)."""
        try:
            from PyQt6.QtCore import QLocale  # noqa: PLC0415
        except Exception:
            return "USD"
        try:
            code = QLocale.system().currencySymbol(QLocale.CurrencySymbolFormat.CurrencyIsoCode)
        except Exception:
            code = ""
        code = (code or "").upper()
        return code if code in CURRENCIES else "USD"

    def effective_language(self) -> str:
        pref = self.current_language_pref()
        return pref if pref != "auto" else self._system_language()

    def effective_currency(self) -> str:
        pref = self.current_currency_pref()
        return pref if pref != "auto" else self._system_currency()

    def set_language_pref(self, pref: str) -> str:
        """Persist the language preference ("auto" or a language code) and apply it."""
        pref = pref if pref in ("auto",) + I18n.AVAILABLE_LANGS else "auto"
        try:
            self.repos["settings"].set("lang_pref", pref, DataSource.USER_DEFINED)
            self.conn.commit()
        except Exception:
            pass
        lang = self.effective_language()
        self.set_language(lang)
        return lang

    def set_currency_pref(self, pref: str) -> str:
        """Persist the currency preference ("auto" or a currency code) and apply it."""
        pref = pref if pref == "auto" or pref in CURRENCIES else "auto"
        try:
            self.repos["settings"].set("currency_pref", pref, DataSource.USER_DEFINED)
            self.conn.commit()
        except Exception:
            pass
        code = self.effective_currency()
        set_currency_code(code)
        return code

    def set_currency(self, code: str) -> str:
        """Persist the display currency code and apply it for formatting."""
        if code not in CURRENCIES:
            code = "USD"
        try:
            self.repos["settings"].set("currency", code, DataSource.USER_DEFINED)
            self.conn.commit()
        except Exception:
            pass
        set_currency_code(code)
        return code

    def current_icon_path(self) -> str:
        """Resolve the app icon: user-chosen (settings) or the bundled energy.ico."""
        try:
            stored = self.repos["settings"].get("app_icon", "")
        except Exception:
            stored = ""
        if stored and Path(stored).is_file():
            return stored
        return self.DEFAULT_ICON

    def set_app_icon(self, path: str) -> str:
        """Persist a custom app icon and push it to the UI handler. Returns the active path."""
        path = str(path)
        if not path or not Path(path).is_file():
            raise FileNotFoundError(path)
        try:
            self.repos["settings"].set("app_icon", path, DataSource.USER_DEFINED)
            self.conn.commit()
        except Exception:
            path = self.DEFAULT_ICON
        if self._icon_handler:
            self._icon_handler(path)
        return path

    def navigate(self, key: str) -> None:
        if self._nav_handler:
            self._nav_handler(key)

    def open_invoice_detail(self, invoice_id: int) -> None:
        if self._invoice_handler:
            self._invoice_handler(invoice_id)

    def seed_if_empty(self) -> None:
        try:
            self.repos["settings"].get("seeded", "")
        except Exception:
            return
        if not self.repos["tariffs"].list_schedules(include_inactive=True):
            seed(self.conn)

    def tr(self, key: str, **kwargs) -> str:
        return self.i18n.tr(key, **kwargs)

    def backup(self, dest=None) -> Path:
        return backup_database(self.db_path, dest)

    def restore(self, source: str | Path) -> Path:
        validate_backup(source)  # reject bad files BEFORE touching the live connection
        self.conn.close()
        try:
            restored = restore_database(self.db_path, source)
        finally:
            # even if the restore fails the app must keep a working connection
            self.conn = connect(self.db_path)
            self.repos = build_repositories(self.conn)
            self._build_services()
            self._baseline_changes = self.conn.total_changes
        return restored

    def relink_after_restore(self) -> None:
        self._build_services()

    def auto_backup_enabled(self) -> bool:
        return self.repos["settings"].get("auto_backup", "1") != "0"

    def set_auto_backup(self, enabled: bool) -> None:
        self.repos["settings"].set("auto_backup", "1" if enabled else "0", DataSource.USER_DEFINED)
        self.repos["uow"].commit()

    def _auto_backup_on_exit(self) -> None:
        """One safety copy per session in which data actually changed (never blocks closing)."""
        try:
            if self.auto_backup_enabled() and self.conn.total_changes > self._baseline_changes:
                self.conn.commit()
                auto_backup(self.conn, self.db_path)
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger("voltiva").exception("automatic backup failed")

    def optimize_database(self) -> int:
        """Run VACUUM, ANALYZE, and PRAGMA optimize to compact and optimize database.
        Returns the compacted database file size in bytes.
        """
        self.conn.commit()
        self.conn.execute("PRAGMA optimize")
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.execute("VACUUM")
        self.conn.execute("ANALYZE")
        from ..domain.models import AuditLogEntry
        self.repos["audit"].append(AuditLogEntry(
            action="DB_OPTIMIZE", entity_type="DATABASE", entity_id=0,
            user="local", description="Database vacuumed and query planner analyzed",
            details_json="{}",
        ))
        self.conn.commit()
        if self.db_path.exists():
            return self.db_path.stat().st_size
        return 0

    def close(self) -> None:
        # closeEvent() and the exit hook may both call this; never touch a closed DB.
        if self._closed:
            return
        self._closed = True
        self._auto_backup_on_exit()
        try:
            # Fold the write-ahead log into the database file so the single .db file is
            # complete when the user copies it, and let SQLite refresh its query-planner
            # statistics.
            self.conn.commit()
            self.conn.execute("PRAGMA optimize")
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass


def default_issue_dates() -> tuple[dt.date, dt.date]:
    today = dt.date.today()
    if today.day >= 15:
        prev = today.replace(day=15)
        curr = today
    else:
        first = today.replace(day=1)
        prev = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=15)
        curr = first
    return prev, curr
