from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ...infrastructure.sqlite.seed import seed
from ... import __author__, __copyright__, __url__, __version__
from ..currencies import CURRENCIES
from ..widgets import danger_small_button, small_button, error_text


class SettingsPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr

        title = QLabel(self.tr("st_title"))
        title.setObjectName("PageTitle")

        self.lang_combo = QComboBox()
        self.lang_combo.setToolTip(self.tr("tt_st_language"))
        self.lang_combo.addItem(self.tr("st_auto"), "auto")
        for lang in app.i18n.AVAILABLE_LANGS:
            self.lang_combo.addItem(self.tr("lang_" + lang), lang)

        self.theme_combo = QComboBox()
        self.theme_combo.setToolTip(self.tr("tt_st_theme"))
        self.theme_combo.addItem(self.tr("st_auto"), "auto")
        self.theme_combo.addItem(self.tr("st_light"), "light")
        self.theme_combo.addItem(self.tr("st_dark"), "dark")

        self.currency_combo = QComboBox()
        self.currency_combo.setToolTip(self.tr("tt_st_currency"))
        self.currency_combo.addItem(self.tr("st_auto"), "auto")
        for code, name in CURRENCIES.items():
            self.currency_combo.addItem(f"{code} — {name}", code)

        self.digits_combo = QComboBox()
        self.digits_combo.setToolTip(self.tr("tt_st_digits"))
        self.digits_combo.addItem(self.tr("st_auto"), "auto")
        self.digits_combo.addItem(self.tr("st_digits_arabic"), "arabic")
        self.digits_combo.addItem(self.tr("st_digits_western"), "western")

        self.db_path_lbl = QLabel(str(app.db_path))
        self.db_path_lbl.setWordWrap(True)
        self.backup_btn = QPushButton(self.tr("st_backup"))
        self.backup_btn.setToolTip(self.tr("tt_st_backup"))
        self.restore_btn = QPushButton(self.tr("st_restore"))
        self.restore_btn.setToolTip(self.tr("tt_st_restore"))
        self.seed_btn = QPushButton(self.tr("st_seed"))
        self.seed_btn.setToolTip(self.tr("tt_st_seed"))

        self.icon_btn = small_button(self.tr("st_icon_change"))
        self.icon_btn.setToolTip(self.tr("tt_st_icon_change"))
        self.icon_reset_btn = danger_small_button(self.tr("st_icon_reset"))
        self.icon_reset_btn.setToolTip(self.tr("tt_st_icon_reset"))
        icon_row = QHBoxLayout()
        icon_row.addWidget(self.icon_btn)
        icon_row.addWidget(self.icon_reset_btn)
        icon_row.addStretch(1)
        self.icon_path_lbl = QLabel(app.current_icon_path())
        self.icon_path_lbl.setObjectName("Muted")
        self.icon_path_lbl.setWordWrap(True)

        about = QLabel()
        about.setText(
            self.tr("about_text")
            + f"\n\nVersion {__version__}  |  Developed by {__author__}\n"
            + f"{__copyright__}\n"
            + f"{__url__}\n"
            + "Donate: https://www.paypal.com/donate/?hosted_button_id=CFANQH892RPH2")
        about.setObjectName("Muted")
        about.setWordWrap(True)

        form = QFormLayout()
        form.addRow(self.tr("st_language"), self.lang_combo)
        form.addRow(self.tr("st_theme"), self.theme_combo)
        form.addRow(self.tr("st_currency"), self.currency_combo)
        form.addRow(self.tr("st_digits"), self.digits_combo)

        app_icon_lbl = QLabel(self.tr("st_icon"))
        app_icon_lbl.setObjectName("StepTitle")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(app_icon_lbl)
        layout.addLayout(icon_row)
        layout.addWidget(self.icon_path_lbl)
        layout.addWidget(QLabel(self.tr("st_db_path")))
        layout.addWidget(self.db_path_lbl)
        layout.addWidget(self.backup_btn)
        layout.addWidget(self.restore_btn)
        layout.addWidget(self.seed_btn)
        layout.addStretch(1)
        layout.addWidget(about)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self.lang_combo.currentIndexChanged.connect(self._set_language)
        self.theme_combo.currentIndexChanged.connect(self._set_theme)
        self.currency_combo.currentIndexChanged.connect(self._set_currency)
        self.digits_combo.currentIndexChanged.connect(self._set_digits)
        self.backup_btn.clicked.connect(self._backup)
        self.restore_btn.clicked.connect(self._restore)
        self.seed_btn.clicked.connect(self._seed)
        self.icon_btn.clicked.connect(self._change_icon)
        self.icon_reset_btn.clicked.connect(self._reset_icon)

    def refresh(self) -> None:
        self.db_path_lbl.setText(str(self.app.db_path))
        self.icon_path_lbl.setText(self.app.current_icon_path())
        idx = self.lang_combo.findData(self.app.current_language_pref())
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        tidx = self.theme_combo.findData(self.app.current_theme_mode())
        if tidx >= 0:
            self.theme_combo.setCurrentIndex(tidx)
        cidx = self.currency_combo.findData(self.app.current_currency_pref())
        if cidx >= 0:
            self.currency_combo.setCurrentIndex(cidx)
        didx = self.digits_combo.findData(self.app.current_digits_pref())
        if didx >= 0:
            self.digits_combo.setCurrentIndex(didx)

    def _change_icon(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("st_icon"), "",
            f"{self.tr('icon_filter')};;{self.tr('all_files')}")
        if not path:
            return
        try:
            self.app.set_app_icon(path)
            self.icon_path_lbl.setText(path)
            QMessageBox.information(self, self.tr("success"), self.tr("st_icon_changed"))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _reset_icon(self) -> None:
        try:
            self.app.set_app_icon(self.app.DEFAULT_ICON)
            self.icon_path_lbl.setText(self.app.DEFAULT_ICON)
            QMessageBox.information(self, self.tr("success"), self.tr("st_icon_reset"))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _set_language(self) -> None:
        pref = self.lang_combo.currentData()
        if pref and pref != self.app.current_language_pref():
            self.app.set_language_pref(pref)

    def _set_theme(self) -> None:
        mode = self.theme_combo.currentData()
        if mode and mode != self.app.current_theme_mode():
            self.app.set_theme_mode(mode)
            self.app.notify_refresh()

    def _set_currency(self) -> None:
        pref = self.currency_combo.currentData()
        if pref and pref != self.app.current_currency_pref():
            self.app.set_currency_pref(pref)
            self.app.notify_refresh()

    def _set_digits(self) -> None:
        pref = self.digits_combo.currentData()
        if pref and pref != self.app.current_digits_pref():
            self.app.set_digits_pref(pref)

    def _backup(self) -> None:
        try:
            dest = self.app.backup()
            QMessageBox.information(self, self.tr("success"), f"{self.tr('st_backup')}: {dest}")
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tr("st_restore"), "", "SQLite (*.db)")
        if not path:
            return
        try:
            self.app.restore(path)
            self.app.repos["invoices"].list_recent(limit=1)
            QMessageBox.information(self, self.tr("success"), self.tr("st_restore"))
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _seed(self) -> None:
        answer = QMessageBox.question(
            self, self.tr("st_seed"), self.tr("st_seed_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            seed(self.app.conn, overwrite=True)
            self.app.conn.commit()
            self.app.notify_refresh()
            QMessageBox.information(self, self.tr("success"), self.tr("st_seed_done"))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))
