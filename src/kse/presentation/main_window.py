from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings, QSize, QTimer, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from . import theme
from .topbar import TopBar
from .widgets import digits

from .pages.analytics import AnalyticsPage
from .pages.dashboard import DashboardPage
from .pages.invoice_detail import InvoiceDetailPage
from .pages.invoices import InvoicesPage
from .pages.new_invoice import NewInvoicePage
from .pages.review import ReviewPage
from .pages.settings import SettingsPage
from .pages.subscribers import SubscribersPage
from .pages.tariffs import TariffsPage
from .pages.verify import VerifyPage


class MainWindow(QMainWindow):
    NAV_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
        ("nav_sec_ops", [
            ("dashboard", "nav_dashboard"),
            ("new_invoice", "nav_new_invoice"),
            ("invoices", "nav_invoices"),
            ("verify", "nav_verify"),
        ]),
        ("nav_sec_insights", [
            ("review", "nav_review"),
            ("analytics", "nav_analytics"),
        ]),
        ("nav_sec_admin", [
            ("tariffs", "nav_tariffs"),
            ("subscribers", "nav_subscribers"),
        ]),
    ]

    def __init__(self, app_context) -> None:
        super().__init__()
        self.app = app_context
        self.tr = app_context.tr
        self.app.set_navigation_handler(self.show_page)
        self.app.set_invoice_handler(self.open_invoice_detail)
        self.app.set_icon_handler(self.apply_icon)
        self.setWindowTitle(self.tr("app_title"))
        self.setWindowIcon(QIcon(self.app.current_icon_path()))
        self.resize(1280, 820)
        self.setMinimumSize(1080, 660)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_label_keys: dict[str, str] = {}
        self._sec_headers: dict[str, QLabel] = {}
        self._nav_dividers: list[QFrame] = []
        self._pages: dict[str, QWidget] = {}
        self._current_key = "dashboard"
        self._compact_sidebar = False
        self._settings = QSettings("Voltiva", "Voltiva")
        self._build()
        self._restore_window_state()

    def _build(self) -> None:
        central = QWidget()
        col = QVBoxLayout(central)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self.topbar = TopBar(self.app, on_exit=self.close)
        col.addWidget(self.topbar)

        root = QHBoxLayout()
        root.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(224)
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 12)
        sidebar_layout.setSpacing(2)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(6, 0, 6, 12)
        self.logo = QLabel()
        self.logo.setObjectName("BrandLogo")
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.setFixedSize(40, 40)
        self.logo.setPixmap(QIcon(self.app.current_icon_path()).pixmap(40, 40))
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        self.brand_name = QLabel(self.tr("app_name"))
        self.brand_name.setObjectName("BrandName")
        self.brand_sub = QLabel(self.tr("app_tagline"))
        self.brand_sub.setObjectName("BrandSub")
        brand_text.addWidget(self.brand_name)
        brand_text.addWidget(self.brand_sub)
        brand_row.addWidget(self.logo)
        brand_row.addSpacing(10)
        brand_row.addLayout(brand_text)
        brand_row.addStretch(1)
        sidebar_layout.addLayout(brand_row)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for idx, (section_key, items) in enumerate(self.NAV_GROUPS):
            if idx:
                sidebar_layout.addSpacing(10)
            header = QLabel(self.tr(section_key))
            header.setObjectName("SectionHeader")
            header.setFixedHeight(theme.Metrics.NAV_CAPTION_H)
            self._sec_headers[section_key] = header
            sidebar_layout.addWidget(header)
            for key, label_key in items:
                self._add_nav_button(sidebar_layout, key, label_key)

        sidebar_layout.addStretch(1)
        divider = QFrame()
        divider.setObjectName("NavDivider")
        divider.setFixedHeight(1)
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(divider)
        sidebar_layout.addSpacing(8)
        self._nav_dividers.append(divider)
        # Settings is a standalone destination: a header over one item only added noise.
        self._add_nav_button(sidebar_layout, "settings", "nav_settings")

        self.version_lbl = QLabel(f"{self.tr('app_name')} v{__version__}")
        self.version_lbl.setObjectName("Version")
        sidebar_layout.addSpacing(4)
        sidebar_layout.addWidget(self.version_lbl)

        self.stack = QStackedWidget()
        self._build_pages(keep="dashboard")

        self._group.buttonClicked.connect(self._on_nav)
        self._nav_buttons["dashboard"].setChecked(True)
        self.stack.setCurrentWidget(self._pages["dashboard"])

        self.stack.setMinimumSize(0, 0)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.sidebar)
        root.addWidget(self.stack, 1)
        col.addLayout(root, 1)
        self.setCentralWidget(central)

        self.status_lbl = QLabel(self.tr("ready"))
        self.statusBar().addWidget(self.status_lbl)

        self.app.i18n.on_change(self._on_lang_changed)
        self.app.on_refresh(self._rebuild_pages)
        self.app.on_theme(self._on_theme_changed)
        self._install_shortcuts()
        self._start_auto_theme_watch()
        self._apply_rtl()
        self._sync_responsive_chrome()

    def _add_nav_button(self, layout: QVBoxLayout, key: str, label_key: str) -> None:
        btn = QPushButton(self.tr(label_key))
        btn.setObjectName("NavBtn")
        btn.setCheckable(True)
        btn.setFixedHeight(theme.Metrics.NAV_ROW_H)
        btn.setToolTip(self.tr("tt_" + label_key))
        self._group.addButton(btn)
        self._nav_buttons[key] = btn
        self._nav_label_keys[key] = label_key
        layout.addWidget(btn)

    def _restore_window_state(self) -> None:
        geometry = self._settings.value("window_geometry")
        state = self._settings.value("window_state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._settings.setValue("window_geometry", self.saveGeometry())
        self._settings.setValue("window_state", self.saveState())
        try:
            self.app.close()
        finally:
            super().closeEvent(event)

    def _install_shortcuts(self) -> None:
        shortcuts = {
            "dashboard": "Ctrl+1",
            "new_invoice": "Ctrl+N",
            "invoices": "Ctrl+F",
            "verify": "Ctrl+Shift+V",
            "review": "Ctrl+R",
            "analytics": "Ctrl+2",
            "tariffs": "Ctrl+T",
            "subscribers": "Ctrl+U",
            "settings": "Ctrl+,",
        }
        for key, shortcut in shortcuts.items():
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(lambda _=False, k=key: self._open_from_shortcut(k))
            self.addAction(action)

        refresh_action = QAction(self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(lambda: self.show_page(self._current_key))
        self.addAction(refresh_action)

    def _open_from_shortcut(self, key: str) -> None:
        self.show_page(key)
        page = self._pages.get(key)
        if key == "invoices" and page is not None and hasattr(page, "focus_search"):
            page.focus_search()                  # Ctrl+F: ready to type

    def _start_auto_theme_watch(self) -> None:
        self._last_theme = self.app.current_theme()
        self._theme_timer = QTimer(self)
        self._theme_timer.timeout.connect(self._sync_auto_theme)
        self._theme_timer.start(60_000)
        # Qt reports a Windows/macOS scheme flip immediately; the timer stays as a
        # fallback for platforms (and Qt versions) that never emit the signal.
        hints = QApplication.instance().styleHints()
        signal = getattr(hints, "colorSchemeChanged", None)
        if signal is not None:
            signal.connect(self._sync_auto_theme)

    def _sync_auto_theme(self, *_scheme) -> None:
        mode = self.app.current_theme_mode()
        name = self.app.current_theme()
        if mode == "auto" and name != self._last_theme:
            self.app.apply_theme()
            self._last_theme = name
            self.app.notify_theme()
            return
        self._last_theme = name

    def _on_theme_changed(self) -> None:
        """Palette changed (top bar, settings or the OS watcher): repaint everything.

        The old flow only re-applied the style sheet, so the theme button/menu and
        any widget that cached a palette colour kept showing the previous theme.
        """
        self._last_theme = self.app.current_theme()
        self.topbar.refresh()
        self._rebuild_pages()
        self._apply_nav_icons()   # compact icons carry their palette colour

    _PAGE_BUILDERS = {
        "dashboard": DashboardPage,
        "new_invoice": NewInvoicePage,
        "invoices": InvoicesPage,
        "verify": VerifyPage,
        "review": ReviewPage,
        "analytics": AnalyticsPage,
        "tariffs": TariffsPage,
        "subscribers": SubscribersPage,
        "settings": SettingsPage,
        "invoice_detail": InvoiceDetailPage,
    }

    def _build_pages(self, keep: str | None = None) -> None:
        """Drop the current pages and rebuild only ``keep``.

        The other pages are built on first navigation (``_ensure_page``): building
        all ten up front made start-up noticeably slower for no visible gain.
        """
        self._pages.clear()
        while self.stack.count():
            w = self.stack.currentWidget()
            self.stack.removeWidget(w)
            w.deleteLater()
        if keep is not None:
            self._ensure_page(keep)

    def _ensure_page(self, key: str) -> QWidget | None:
        page = self._pages.get(key)
        if page is None:
            builder = self._PAGE_BUILDERS.get(key)
            if builder is None:
                return None
            page = builder(self.app)
            self._pages[key] = page
            self.stack.addWidget(page)
        return page

    def _apply_rtl(self) -> None:
        direction = Qt.LayoutDirection.RightToLeft if self.app.i18n.rtl else Qt.LayoutDirection.LeftToRight
        self.setLayoutDirection(direction)
        self._sync_sidebar_edge()

    def _sync_sidebar_edge(self) -> None:
        """In RTL the sidebar sits on the right, so highlight the inner (LEFT) edge.

        The nav buttons also need their own ``rtl`` property: the QSS text-alignment
        selector is evaluated on the button, not on its parent frame.
        """
        sidebar = getattr(self, "sidebar", None)
        if sidebar is None:
            return
        rtl = bool(self.app.i18n.rtl)
        sidebar.setProperty("rtl", rtl)
        sidebar.style().unpolish(sidebar)       # dynamic-property selectors need a re-polish
        sidebar.style().polish(sidebar)
        for btn in self._nav_buttons.values():
            btn.setProperty("rtl", rtl)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_responsive_chrome()

    # Fallback glyphs, only used if assets/icons has not been generated.
    _COMPACT_FALLBACK = {
        "dashboard": "⌂", "new_invoice": "+", "invoices": "▤", "verify": "✓",
        "review": "≡", "analytics": "↗", "tariffs": "₮", "subscribers": "◇",
        "settings": "⚙",
    }

    def _sync_responsive_chrome(self, force: bool = False) -> None:
        if not hasattr(self, "sidebar"):
            return
        compact = self.width() < 1200
        if compact == self._compact_sidebar and not force:
            self._apply_nav_icons()
            return
        self._compact_sidebar = compact
        self.sidebar.setFixedWidth(72 if compact else 224)
        self.brand_name.setVisible(not compact)
        self.brand_sub.setVisible(not compact)
        self.version_lbl.setVisible(not compact)
        for header in self._sec_headers.values():
            header.setVisible(not compact)
        for divider in self._nav_dividers:
            divider.setVisible(not compact)
        for btn in self._nav_buttons.values():
            btn.setProperty("compact", compact)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._apply_nav_icons()

    def _apply_nav_icons(self) -> None:
        """Compact rows: generated per-theme icons, never font glyphs.

        The glyphs the compact sidebar used to show (⌂ ▤ ≡ …) came from whatever
        fallback font the OS picked, so their size and weight drifted per language.
        """
        for key, btn in self._nav_buttons.items():
            label_key = self._nav_label_keys[key]
            label = self.tr(label_key)
            btn.setToolTip(label if self._compact_sidebar else self.tr("tt_" + label_key))
            btn.setAccessibleName(label)
            if not self._compact_sidebar:
                btn.setIcon(QIcon())
                btn.setText(label)
                continue
            icon = QIcon()
            for suffix, state in (("", QIcon.State.Off), ("-on", QIcon.State.On)):
                path = theme.icon_file(f"nav-{key}{suffix}")
                if path:
                    icon.addFile(path, QSize(theme.Metrics.NAV_ICON, theme.Metrics.NAV_ICON),
                             QIcon.Mode.Normal, state)
            if icon.isNull():
                btn.setIcon(QIcon())
                btn.setText(self._COMPACT_FALLBACK.get(key, "•"))
                continue
            btn.setText("")
            btn.setIcon(icon)
            btn.setIconSize(QSize(theme.Metrics.NAV_ICON, theme.Metrics.NAV_ICON))

    def _on_lang_changed(self) -> None:
        self.topbar.refresh()
        for section_key, header in self._sec_headers.items():
            header.setText(self.app.tr(section_key))
        self.brand_sub.setText(self.app.tr("app_tagline"))
        self.brand_name.setText(self.app.tr("app_name"))
        self.version_lbl.setText(f"{self.app.tr('app_name')} v{__version__}")
        self.status_lbl.setText(self.app.tr("ready"))
        self.setWindowTitle(self.app.tr("app_title"))
        self._apply_rtl()
        self.app.apply_theme()      # RTL layout also flips the field text alignment
        self._rebuild_pages()
        self._sync_responsive_chrome(force=True)

    def _rebuild_pages(self) -> None:
        current = self._current_key
        if current == "invoice_detail":
            current = "invoices"
        self._build_pages(keep=current)
        for key, btn in self._nav_buttons.items():
            btn.setChecked(key == current)
        if current in self._pages:
            self.stack.setCurrentWidget(self._pages[current])
            self._current_key = current
            self.show_page(current)

    def _on_nav(self, button: QPushButton) -> None:
        for key, btn in self._nav_buttons.items():
            if btn is button:
                self.show_page(key)
                return

    def show_page(self, key: str) -> None:
        page = self._ensure_page(key)
        if page is None:
            return
        self._current_key = key
        self.stack.setCurrentWidget(page)
        self._sync_nav_highlight(key)
        try:
            page.refresh()
        except Exception:  # noqa: BLE001 - keep the app alive but tell the user + log it
            import logging
            logging.getLogger("voltiva").exception("refresh failed for page %r", key)
            self.statusBar().showMessage(self.tr("error"), 6000)
        self._update_status(key)

    def _sync_nav_highlight(self, key: str) -> None:
        """Highlight the matching sidebar button (buttons on the dashboard navigate
        programmatically, which used to leave "Dashboard" highlighted). The invoice
        detail page belongs to "Invoices"."""
        target = "invoices" if key == "invoice_detail" else key
        for k, btn in self._nav_buttons.items():
            btn.setChecked(k == target)

    def open_invoice_detail(self, invoice_id: int) -> None:
        page = self._ensure_page("invoice_detail")
        page.open_invoice(invoice_id)
        self.stack.setCurrentWidget(page)
        self._current_key = "invoice_detail"
        self._sync_nav_highlight("invoice_detail")
        self._update_status("invoice_detail")

    def _update_status(self, key: str) -> None:
        try:
            count = self.app.repos["invoices"].count()
        except Exception:
            count = 0
        label_key = self._nav_label_keys.get(key, "iv_no")
        page_name = self.tr(label_key) if key != "invoice_detail" else self.tr("iv_no")
        db_name = Path(str(self.app.db_path)).name
        self.status_lbl.setText(
            self.tr("status_context", page=page_name, count=digits(str(count)), db=db_name))

    def apply_icon(self, path: str) -> None:
        icon = QIcon(path)
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)
