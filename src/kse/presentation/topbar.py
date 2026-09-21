"""Top bar: native menu bar plus quick selectors for language, currency and theme.

All three selectors default to "Automatic" — resolved from the operating system
(Windows locale → language + currency, system color scheme → dark/light theme).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QActionGroup
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMenuBar, QMessageBox, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from .currencies import CURRENCIES
from .i18n import I18n, LANG_NAMES
from .. import __author__, __url__, __version__


def _theme_icon(name: str) -> str:
    return "🌙" if name == "dark" else "☀️"


class _CurrencyMenu(QMenu):
    """Searchable currency picker (Automatic + code/name search over all currencies)."""

    def __init__(self, app, parent=None) -> None:
        super().__init__(parent)
        self.app = app
        self.setMinimumWidth(280)

        self.auto_action = self.addAction(app.tr("st_auto"))
        self.auto_action.setCheckable(True)
        self.auto_action.setChecked(app.current_currency_pref() == "auto")
        self.addSeparator()

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        self.search = QLineEdit()
        self.search.setObjectName("CurrencySearch")
        self.search.setPlaceholderText(app.tr("tb_currency_search_ph"))
        self.search.setClearButtonEnabled(True)
        self.list_ = QListWidget()
        self.list_.setMaximumHeight(280)
        for code in sorted(CURRENCIES):
            self.list_.addItem(QListWidgetItem(f"{code}  —  {CURRENCIES[code]}"))
        lay.addWidget(self.search)
        lay.addWidget(self.list_)

        from PyQt6.QtWidgets import QWidgetAction
        action = QWidgetAction(self)
        action.setDefaultWidget(container)
        self.addAction(action)

        self.auto_action.triggered.connect(lambda: self._pick_auto())
        self.search.textChanged.connect(self._filter)
        self.list_.itemClicked.connect(self._pick_item)

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self.list_.count()):
            item = self.list_.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    def _pick_auto(self) -> None:
        self.app.set_currency_pref("auto")
        self.close()

    def _pick_item(self, item: QListWidgetItem) -> None:
        code = item.text().split()[0]
        self.app.set_currency_pref(code)
        self.close()


class TopBar(QFrame):
    """Menu bar (File / Help) with language, currency and theme tool buttons."""

    def __init__(self, app, on_exit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._on_exit = on_exit
        self.setObjectName("TopBar")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 12, 6)
        lay.setSpacing(8)

        self.menubar = QMenuBar(self)
        self.menubar.setMinimumWidth(0)
        self.menubar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.menubar, 1)

        self.lang_btn = QToolButton()
        self.lang_btn.setMinimumWidth(42)
        self.lang_btn.setToolTip(self.tr("tb_lang_tip"))
        self.lang_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        lay.addWidget(self.lang_btn)

        self.cur_btn = QToolButton()
        self.cur_btn.setMinimumWidth(54)
        self.cur_btn.setToolTip(self.tr("tb_currency_tip"))
        self.cur_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        lay.addWidget(self.cur_btn)

        self.theme_btn = QToolButton()
        self.theme_btn.setMinimumWidth(42)
        self.theme_btn.setToolTip(self.tr("tb_theme_tip"))
        self.theme_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        lay.addWidget(self.theme_btn)

        self.refresh()

    def _build_menu_bar(self) -> None:
        self.menubar.clear()
        file_menu = self.menubar.addMenu(self.tr("mn_file"))
        for key, label in (("new_invoice", "nav_new_invoice"), ("invoices", "nav_invoices"),
                           ("tariffs", "nav_tariffs"), ("subscribers", "nav_subscribers"),
                           ("settings", "nav_settings")):
            act = file_menu.addAction(self.tr(label))
            act.triggered.connect(lambda _=False, k=key: self.app.navigate(k))
        file_menu.addSeparator()
        exit_act = file_menu.addAction(self.tr("mn_exit"))
        exit_act.triggered.connect(lambda _=False: self._on_exit())
        help_menu = self.menubar.addMenu(self.tr("mn_help"))
        about_act = help_menu.addAction(self.tr("mn_about"))
        about_act.triggered.connect(lambda _=False: self._about())

    def _about(self) -> None:
        text = (
            self.tr("about_text")
            + f"\n\nVersion {__version__}\n"
            + f"Developed by {__author__}\n"
            + f"{__url__}\n"
            + "Donate: https://www.paypal.com/donate/?hosted_button_id=CFANQH892RPH2"
        )
        QMessageBox.about(self, self.tr("app_name"), text)

    def _build_lang_menu(self) -> QMenu:
        menu = QMenu(self)
        group = QActionGroup(self)
        group.setExclusive(True)
        pref = self.app.current_language_pref()
        auto = menu.addAction(self.tr("st_auto"))
        auto.setCheckable(True)
        auto.setChecked(pref == "auto")
        auto.triggered.connect(lambda: self.app.set_language_pref("auto"))
        group.addAction(auto)
        menu.addSeparator()
        for code in I18n.AVAILABLE_LANGS:
            act = menu.addAction(LANG_NAMES[code])
            act.setCheckable(True)
            act.setChecked(pref != "auto" and self.app.effective_language() == code)
            act.triggered.connect(lambda _=False, c=code: self.app.set_language_pref(c))
            group.addAction(act)
        return menu

    def _build_theme_menu(self) -> QMenu:
        menu = QMenu(self)
        group = QActionGroup(self)
        group.setExclusive(True)
        for mode, key in (("auto", "st_auto"), ("light", "st_light"), ("dark", "st_dark")):
            act = menu.addAction(self.tr(key))
            act.setCheckable(True)
            act.setChecked(self.app.current_theme_mode() == mode)
            act.triggered.connect(lambda _=False, m=mode: self.app.set_theme_mode(m))
            group.addAction(act)
        return menu

    def refresh(self) -> None:
        self._build_menu_bar()
        self.lang_btn.setText(self.app.effective_language().upper())
        self.cur_btn.setText(self.app.effective_currency())
        resolved = self.app.current_theme()
        mode_text = self.tr("st_" + self.app.current_theme_mode())
        self.theme_btn.setText(f"{_theme_icon(resolved)} {mode_text}")
        self.theme_btn.setToolTip(self.tr("tb_theme_tip"))
        for old in getattr(self, "_menus", []):
            old.deleteLater()
        self._menus = []
        lang_menu = self._build_lang_menu()
        cur_menu = _CurrencyMenu(self.app, self)
        theme_menu = self._build_theme_menu()
        self.lang_btn.setMenu(lang_menu)
        self.cur_btn.setMenu(cur_menu)
        self.theme_btn.setMenu(theme_menu)
        self._menus = [lang_menu, cur_menu, theme_menu]
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if self.app.i18n.rtl else Qt.LayoutDirection.LeftToRight)
