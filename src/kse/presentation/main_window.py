from __future__ import annotations

from PyQt6.QtCore import QSettings, QTimer, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from .topbar import TopBar

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
            ("review", "nav_review"),
        ]),
        ("nav_sec_insights", [
            ("analytics", "nav_analytics"),
        ]),
        ("nav_sec_admin", [
            ("tariffs", "nav_tariffs"),
            ("subscribers", "nav_subscribers"),
        ]),
        ("nav_sec_system", [
            ("settings", "nav_settings"),
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
        self.resize(1220, 780)
        self.setMinimumSize(760, 520)
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
        sidebar_layout.setContentsMargins(12, 18, 12, 14)
        sidebar_layout.setSpacing(2)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(6, 0, 6, 14)
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
                divider = QFrame()
                divider.setObjectName("NavDivider")
                divider.setFixedHeight(1)
                sidebar_layout.addSpacing(10)
                sidebar_layout.addWidget(divider)
                sidebar_layout.addSpacing(8)
                self._nav_dividers.append(divider)
            header = QLabel(self.tr(section_key))
            header.setObjectName("SectionHeader")
            self._sec_headers[section_key] = header
            sidebar_layout.addWidget(header)
            for key, label_key in items:
                btn = QPushButton(self.tr(label_key))
                btn.setObjectName("NavBtn")
                btn.setCheckable(True)
                btn.setToolTip(self.tr("tt_" + label_key))
                self._group.addButton(btn)
                self._nav_buttons[key] = btn
                self._nav_label_keys[key] = label_key
                sidebar_layout.addWidget(btn)
        sidebar_layout.addStretch(1)

        self.version_lbl = QLabel(f"{self.tr('app_name')} v{__version__}")
        self.version_lbl.setObjectName("Version")
        sidebar_layout.addWidget(self.version_lbl)

        self.stack = QStackedWidget()
        self._build_pages()

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
        self._install_shortcuts()
        self._start_auto_theme_watch()
        self._apply_rtl()
        self._sync_responsive_chrome()

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
            action.triggered.connect(lambda _=False, k=key: self.show_page(k))
            self.addAction(action)

    def _start_auto_theme_watch(self) -> None:
        self._last_theme = self.app.current_theme()
        self._theme_timer = QTimer(self)
        self._theme_timer.timeout.connect(self._sync_auto_theme)
        self._theme_timer.start(60_000)

    def _sync_auto_theme(self) -> None:
        mode = self.app.current_theme_mode()
        name = self.app.current_theme()
        if mode == "auto" and name != self._last_theme:
            self.app.apply_theme()
            self._last_theme = name
            self.topbar.refresh()
            return
        self._last_theme = name

    def _build_pages(self) -> None:
        self._pages.clear()
        while self.stack.count():
            w = self.stack.currentWidget()
            self.stack.removeWidget(w)
            w.deleteLater()
        builders = {
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
        for key, builder in builders.items():
            page = builder(self.app)
            self._pages[key] = page
            self.stack.addWidget(page)

    def _apply_rtl(self) -> None:
        direction = Qt.LayoutDirection.RightToLeft if self.app.i18n.rtl else Qt.LayoutDirection.LeftToRight
        self.setLayoutDirection(direction)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_responsive_chrome()

    def _sync_responsive_chrome(self) -> None:
        if not hasattr(self, "sidebar"):
            return
        compact = self.width() < 930
        if compact == self._compact_sidebar:
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
        compact_icons = {
            "dashboard": "⌂",
            "new_invoice": "+",
            "invoices": "▤",
            "verify": "✓",
            "review": "≡",
            "analytics": "↗",
            "tariffs": "₮",
            "subscribers": "◇",
            "settings": "⚙",
        }
        for key, btn in self._nav_buttons.items():
            label_key = self._nav_label_keys[key]
            btn.setText(compact_icons.get(key, "•") if compact else self.tr(label_key))
            btn.setToolTip(self.tr(label_key))

    def _on_lang_changed(self) -> None:
        for key, btn in self._nav_buttons.items():
            btn.setText(self.app.tr(self._nav_label_keys[key]))
        self.topbar.refresh()
        for section_key, header in self._sec_headers.items():
            header.setText(self.app.tr(section_key))
        self.brand_sub.setText(self.app.tr("app_tagline"))
        self.brand_name.setText(self.app.tr("app_name"))
        self.version_lbl.setText(f"{self.app.tr('app_name')} v{__version__}")
        self.status_lbl.setText(self.app.tr("ready"))
        self.setWindowTitle(self.app.tr("app_title"))
        self._apply_rtl()
        self._rebuild_pages()
        self._compact_sidebar = not self._compact_sidebar
        self._sync_responsive_chrome()

    def _rebuild_pages(self) -> None:
        current = self._current_key
        if current == "invoice_detail":
            current = "invoices"
        self._build_pages()
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
        if key not in self._pages:
            return
        self._current_key = key
        page = self._pages[key]
        self.stack.setCurrentWidget(page)
        try:
            page.refresh()
        except Exception:
            pass
        self._update_status(key)

    def open_invoice_detail(self, invoice_id: int) -> None:
        page = self._pages["invoice_detail"]
        page.open_invoice(invoice_id)
        self.stack.setCurrentWidget(page)
        self._current_key = "invoice_detail"
        self._update_status("invoice_detail")

    def _update_status(self, key: str) -> None:
        try:
            count = self.app.repos["invoices"].count()
        except Exception:
            count = 0
        label_key = self._nav_label_keys.get(key, "iv_no")
        page_name = self.tr(label_key) if key != "invoice_detail" else self.tr("iv_no")
        self.status_lbl.setText(self.tr("status_context", page=page_name, count=count, db=str(self.app.db_path)))

    def apply_icon(self, path: str) -> None:
        icon = QIcon(path)
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)
