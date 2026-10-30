from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

from ...infrastructure.sqlite.seed import seed
from ... import __author__, __copyright__, __url__, __version__
from .. import theme
from ..currencies import CURRENCIES
from ..widgets import (
    PageHeader, Section, danger_small_button, error_text, form_label, ghost_button,
    small_button,
)

_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=CFANQH892RPH2"


class _AiPingWorker(QObject):
    """Checks the configured vision endpoint without freezing the settings page."""

    done = pyqtSignal(str)
    fail = pyqtSignal(str)

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg

    def run(self) -> None:
        try:
            from ...infrastructure.ocr.ai_scanner import AiScanner
            self.done.emit(AiScanner.ping(self.cfg))
        except Exception as exc:  # pragma: no cover
            self.fail.emit(str(exc))


def _path_field(path: str) -> QLineEdit:
    """Read-only path display: scrolls and copies, never overflows the card."""
    field = QLineEdit(path)
    field.setObjectName("PathField")
    field.setReadOnly(True)
    field.setToolTip(path)
    # Paths are LTR data: without this the RTL layout scrambles an Arabic folder
    # name together with the drive/backslash segments.
    field.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    field.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    field.setCursorPosition(0)
    return field


class SettingsPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr

        header = PageHeader(self.tr("st_title"), self.tr("st_subtitle"))

        self.lang_combo = QComboBox()
        self.lang_combo.setToolTip(self.tr("tt_st_language"))
        self.lang_combo.addItem(self.tr("st_auto"), "auto")
        for lang in app.i18n.AVAILABLE_LANGS:
            self.lang_combo.addItem(self.tr("lang_" + lang), lang)

        self.theme_combo = QComboBox()
        self.theme_combo.setToolTip(self.tr("tt_st_theme"))
        self.theme_combo.addItem(self.tr("st_auto"), "auto")
        self.theme_combo.insertSeparator(self.theme_combo.count())
        last_kind = ""
        for name in theme.THEME_UI_ORDER:
            if name == theme.THEME_AUTO:
                continue
            kind = theme.palette_kind(name)
            if last_kind and kind != last_kind:
                self.theme_combo.insertSeparator(self.theme_combo.count())
            last_kind = kind
            self.theme_combo.addItem(self.tr(theme.THEME_LABEL_KEYS[name]), name)

        self.theme_hint = QLabel()
        self.theme_hint.setObjectName("Muted")
        theme_row = QWidget()
        theme_row_layout = QVBoxLayout(theme_row)
        theme_row_layout.setContentsMargins(0, 0, 0, 0)
        theme_row_layout.setSpacing(4)
        theme_row_layout.addWidget(self.theme_combo)
        theme_row_layout.addWidget(self.theme_hint)

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

        self.ai_mode_combo = QComboBox()
        self.ai_mode_combo.setToolTip(self.tr("tt_st_ai_mode"))
        for mode, key in (
            ("auto", "st_ai_mode_auto"),
            ("custom", "st_ai_mode_custom"),
            ("local", "st_ai_mode_local"),
        ):
            self.ai_mode_combo.addItem(self.tr(key), mode)

        self.ai_url_edit = QLineEdit()
        self.ai_url_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.ai_url_edit.setToolTip(self.tr("tt_st_ai_url"))
        self.ai_key_edit = QLineEdit()
        self.ai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.ai_key_edit.setPlaceholderText("sk-…")
        self.ai_key_edit.setToolTip(self.tr("tt_st_ai_key"))
        self.ai_model_edit = QLineEdit()
        self.ai_model_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.ai_model_edit.setToolTip(self.tr("tt_st_ai_model"))
        self.ai_timeout_combo = QComboBox()
        self.ai_timeout_combo.setToolTip(self.tr("tt_st_ai_timeout"))
        for seconds in (30, 45, 60, 90, 120, 180, 300):
            self.ai_timeout_combo.addItem(str(seconds), seconds)

        self.ai_hint = QLabel()
        self.ai_hint.setObjectName("Muted")
        self.ai_hint.setWordWrap(True)
        self.ai_privacy = QLabel(self.tr("st_ai_privacy"))
        self.ai_privacy.setObjectName("Muted")
        self.ai_privacy.setWordWrap(True)
        self.ai_save_btn = small_button(self.tr("st_ai_save"))
        self.ai_test_btn = ghost_button(self.tr("st_ai_test"))
        self.ai_key_btn = small_button(self.tr("st_ai_get_key"))
        self.ai_key_btn.setToolTip(self.tr("st_ai_get_key_tip"))
        self.ai_key_btn.clicked.connect(self._open_ai_key_page)

        self.db_path_edit = _path_field(str(app.db_path))
        self.backup_btn = small_button(self.tr("st_backup"))
        self.backup_btn.setToolTip(self.tr("tt_st_backup"))
        self.restore_btn = small_button(self.tr("st_restore"))
        self.restore_btn.setToolTip(self.tr("tt_st_restore"))
        self.seed_btn = danger_small_button(self.tr("st_seed"))
        self.seed_btn.setToolTip(self.tr("tt_st_seed"))
        self.optimize_btn = small_button(self.tr("st_optimize_db"))
        self.optimize_btn.setToolTip(self.tr("tt_st_optimize"))

        self.icon_btn = small_button(self.tr("st_icon_change"))
        self.icon_btn.setToolTip(self.tr("tt_st_icon_change"))
        self.icon_reset_btn = danger_small_button(self.tr("st_icon_reset"))
        self.icon_reset_btn.setToolTip(self.tr("tt_st_icon_reset"))
        icon_row = QHBoxLayout()
        icon_row.setSpacing(8)
        icon_row.addWidget(self.icon_btn)
        icon_row.addWidget(self.icon_reset_btn)
        icon_row.addStretch(1)
        self.icon_path_edit = _path_field(app.current_icon_path())

        about_intro = QLabel(self.tr("about_text"))
        about_intro.setObjectName("Muted")
        about_intro.setWordWrap(True)
        about_meta = QLabel(f"v{__version__}   |   {__author__}\n{__copyright__}")
        about_meta.setObjectName("Muted")
        about_meta.setWordWrap(True)
        github_btn = small_button("GitHub")
        github_btn.setToolTip(__url__)
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(__url__)))
        donate_btn = ghost_button(self.tr("st_donate"))
        donate_btn.setToolTip(_DONATE_URL)
        donate_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(_DONATE_URL)))
        about_links = QHBoxLayout()
        about_links.setSpacing(8)
        about_links.addWidget(github_btn)
        about_links.addWidget(donate_btn)
        about_links.addStretch(1)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for label, widget in (
            (self.tr("st_language"), self.lang_combo),
            (self.tr("st_theme"), theme_row),
            (self.tr("st_currency"), self.currency_combo),
            (self.tr("st_digits"), self.digits_combo),
        ):
            form.addRow(form_label(label, 140), widget)

        appearance = Section(self.tr("st_appearance"))
        appearance.add_layout(form)
        appearance.add_stretch()

        ai_desc = QLabel(self.tr("st_ai_desc"))
        ai_desc.setObjectName("Muted")
        ai_desc.setWordWrap(True)
        ai_form = QFormLayout()
        ai_form.setContentsMargins(0, 0, 0, 0)
        ai_form.setHorizontalSpacing(16)
        ai_form.setVerticalSpacing(10)
        ai_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ai_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for label, widget in (
            (self.tr("st_ai_mode"), self.ai_mode_combo),
            (self.tr("st_ai_url"), self.ai_url_edit),
            (self.tr("st_ai_key"), self.ai_key_edit),
            (self.tr("st_ai_model"), self.ai_model_edit),
            (self.tr("st_ai_timeout"), self.ai_timeout_combo),
        ):
            ai_form.addRow(form_label(label, 140), widget)
        ai_buttons = QHBoxLayout()
        ai_buttons.setSpacing(8)
        ai_buttons.addWidget(self.ai_test_btn)
        ai_buttons.addWidget(self.ai_save_btn)
        ai_buttons.addStretch(1)
        ai_buttons.addWidget(self.ai_key_btn)

        ai_card = Section(self.tr("st_ai_title"))
        ai_card.add_widget(ai_desc)
        ai_card.add_layout(ai_form)
        ai_card.add_widget(self.ai_hint)
        ai_card.add_widget(self.ai_privacy)
        ai_card.add_layout(ai_buttons)
        ai_card.add_stretch()

        icon_card = Section(self.tr("st_icon"))
        icon_card.add_layout(icon_row)
        icon_card.add_widget(self.icon_path_edit)
        icon_card.add_stretch()

        db_card = Section(self.tr("st_db_title"))
        db_caption = QLabel(self.tr("st_db_path"))
        db_caption.setObjectName("FieldLabel")
        db_card.add_widget(db_caption)
        db_card.add_widget(self.db_path_edit)
        db_actions = QGridLayout()
        db_actions.setContentsMargins(0, 6, 0, 0)
        db_actions.setHorizontalSpacing(8)
        db_actions.setVerticalSpacing(8)
        db_actions.addWidget(self.backup_btn, 0, 0, Qt.AlignmentFlag.AlignLeft)
        db_actions.addWidget(self.restore_btn, 0, 1, Qt.AlignmentFlag.AlignLeft)
        db_actions.addWidget(self.optimize_btn, 1, 0, Qt.AlignmentFlag.AlignLeft)
        db_actions.addWidget(self.seed_btn, 1, 1, Qt.AlignmentFlag.AlignLeft)
        db_actions.setColumnStretch(2, 1)
        db_card.add_layout(db_actions)

        about_card = Section(self.tr("st_about"))
        about_card.add_widget(about_intro)
        about_card.add_spacing(6)
        about_card.add_widget(about_meta)
        about_card.add_spacing(8)
        about_card.add_layout(about_links)
        about_card.add_stretch()

        cards = QGridLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setHorizontalSpacing(theme.Metrics.PAGE_SPACING)
        cards.setVerticalSpacing(theme.Metrics.PAGE_SPACING)
        cards.addWidget(appearance, 0, 0)
        cards.addWidget(ai_card, 0, 1)
        cards.addWidget(db_card, 1, 0)
        cards.addWidget(icon_card, 1, 1)
        cards.addWidget(about_card, 2, 0, 1, 2)
        cards.setColumnStretch(0, 1)
        cards.setColumnStretch(1, 1)
        cards.setRowStretch(3, 1)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(
            theme.Metrics.PAGE_MARGIN, 18, theme.Metrics.PAGE_MARGIN, 18)
        layout.setSpacing(theme.Metrics.PAGE_SPACING)
        layout.addWidget(header)
        layout.addLayout(cards)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self.lang_combo.currentIndexChanged.connect(self._set_language)
        self.theme_combo.currentIndexChanged.connect(self._set_theme)
        self.currency_combo.currentIndexChanged.connect(self._set_currency)
        self.digits_combo.currentIndexChanged.connect(self._set_digits)
        self.ai_mode_combo.currentIndexChanged.connect(self._on_ai_mode_changed)
        self.ai_save_btn.clicked.connect(self._save_ai)
        self.ai_test_btn.clicked.connect(self._test_ai)
        self.backup_btn.clicked.connect(self._backup)
        self.restore_btn.clicked.connect(self._restore)
        self.seed_btn.clicked.connect(self._seed)
        self.optimize_btn.clicked.connect(self._optimize_db)
        self.icon_btn.clicked.connect(self._change_icon)
        self.icon_reset_btn.clicked.connect(self._reset_icon)
        self._load_ai()

    def refresh(self) -> None:
        self.db_path_edit.setText(str(self.app.db_path))
        self.db_path_edit.setToolTip(str(self.app.db_path))
        self.icon_path_edit.setText(self.app.current_icon_path())
        self.icon_path_edit.setToolTip(self.app.current_icon_path())
        idx = self.lang_combo.findData(self.app.current_language_pref())
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        tidx = self.theme_combo.findData(self.app.current_theme_mode())
        if tidx >= 0:
            self.theme_combo.setCurrentIndex(tidx)
        resolved = self.app.current_theme()
        self.theme_hint.setText(self.tr(
            "st_theme_active",
            theme=self.tr(theme.THEME_LABEL_KEYS[resolved])))
        cidx = self.currency_combo.findData(self.app.current_currency_pref())
        if cidx >= 0:
            self.currency_combo.setCurrentIndex(cidx)
        didx = self.digits_combo.findData(self.app.current_digits_pref())
        if didx >= 0:
            self.digits_combo.setCurrentIndex(didx)
        self._load_ai()

    # ---- AI scanning ---------------------------------------------------
    def _load_ai(self) -> None:
        from ...infrastructure.ocr.ai_scanner import AiScanConfig

        cfg = AiScanConfig.load(self.app.repos["settings"])
        self._stored_ai_url = cfg.url
        self._loading_ai = True
        try:
            idx = self.ai_mode_combo.findData(cfg.mode)
            if idx >= 0:
                self.ai_mode_combo.setCurrentIndex(idx)
            self.ai_url_edit.setText(cfg.url if cfg.mode == "custom" else "")
            self.ai_key_edit.setText(cfg.api_key)
            self.ai_model_edit.setText(cfg.model)
            tidx = self.ai_timeout_combo.findData(cfg.timeout)
            if tidx < 0:
                self.ai_timeout_combo.addItem(str(cfg.timeout), cfg.timeout)
                tidx = self.ai_timeout_combo.count() - 1
            self.ai_timeout_combo.setCurrentIndex(tidx)
        finally:
            self._loading_ai = False
        self._last_ai_mode = cfg.mode
        self._sync_ai_fields()

    def _on_ai_mode_changed(self) -> None:
        from ...infrastructure.ocr.ai_scanner import MODE_CUSTOM

        if getattr(self, "_loading_ai", False):
            return
        if self._last_ai_mode == MODE_CUSTOM:
            self._stored_ai_url = self.ai_url_edit.text().strip()
        self._last_ai_mode = self.ai_mode_combo.currentData() or "auto"
        self._sync_ai_fields()

    def _ai_config(self):
        from ...infrastructure.ocr.ai_scanner import AiScanConfig, MODE_CUSTOM

        mode = self.ai_mode_combo.currentData() or "auto"
        url = (self.ai_url_edit.text().strip() if mode == MODE_CUSTOM
               else self._stored_ai_url)
        return AiScanConfig(
            mode=mode,
            url=url,
            api_key=self.ai_key_edit.text().strip(),
            model=self.ai_model_edit.text().strip(),
            timeout=int(self.ai_timeout_combo.currentData() or 60),
        )

    def _sync_ai_fields(self) -> None:
        from ...infrastructure.ocr.ai_scanner import (
            AUTO_ENDPOINT, MODE_AUTO, MODE_CUSTOM, MODE_LOCAL,
        )

        mode = self.ai_mode_combo.currentData()
        custom = mode == MODE_CUSTOM
        local = mode == MODE_LOCAL
        self.ai_url_edit.setEnabled(custom)
        self.ai_key_edit.setEnabled(not local)
        self.ai_model_edit.setEnabled(not local)
        self.ai_test_btn.setEnabled(not local)
        if mode == MODE_AUTO:
            self.ai_url_edit.clear()
            self.ai_url_edit.setPlaceholderText(AUTO_ENDPOINT)
            self.ai_model_edit.setPlaceholderText("openai")
            self.ai_hint.setText(self.tr("st_ai_hint_auto"))
        elif custom:
            if not self.ai_url_edit.text().strip():
                self.ai_url_edit.setText(getattr(self, "_stored_ai_url", ""))
            self.ai_url_edit.setPlaceholderText("https://…/v1")
            self.ai_model_edit.setPlaceholderText("gpt-4o-mini / llava")
            self.ai_hint.setText(self.tr("st_ai_hint_custom"))
        elif local:
            self.ai_url_edit.clear()
            self.ai_url_edit.setPlaceholderText("")
            self.ai_model_edit.setPlaceholderText("")
            self.ai_hint.setText(self.tr("st_ai_hint_local"))

    def _open_ai_key_page(self) -> None:
        from ...infrastructure.ocr.ai_scanner import AUTO_KEY_URL

        QDesktopServices.openUrl(QUrl(AUTO_KEY_URL))

    def _save_ai(self) -> None:
        from ...infrastructure.ocr.ai_scanner import MODE_CUSTOM

        cfg = self._ai_config()
        if cfg.mode == MODE_CUSTOM and not cfg.endpoint():
            QMessageBox.warning(self, self.tr("st_ai_title"), self.tr("ocr_ai_need_url"))
            return
        try:
            cfg.save(self.app.repos["settings"])
            self.app.conn.commit()
            if cfg.mode == MODE_CUSTOM:
                self._stored_ai_url = cfg.url
            self._sync_ai_fields()
            QMessageBox.information(self, self.tr("success"), self.tr("st_ai_saved"))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _test_ai(self) -> None:
        from ...infrastructure.ocr.ai_scanner import MODE_AUTO, MODE_CUSTOM, MODE_LOCAL

        cfg = self._ai_config()
        if cfg.mode == MODE_LOCAL:
            return
        if cfg.mode == MODE_CUSTOM and not cfg.endpoint():
            QMessageBox.warning(self, self.tr("st_ai_title"), self.tr("ocr_ai_need_url"))
            return
        if cfg.mode == MODE_AUTO and not cfg.api_key.strip():
            QMessageBox.warning(self, self.tr("st_ai_title"), self.tr("ocr_ai_need_key"))
            return
        self.ai_test_btn.setEnabled(False)
        self.ai_test_btn.setText(self.tr("st_ai_testing"))
        self._ai_thread = QThread(self)
        self._ai_worker = _AiPingWorker(cfg)
        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.done.connect(self._ai_test_ok)
        self._ai_worker.fail.connect(self._ai_test_failed)
        self._ai_worker.done.connect(self._ai_thread.quit)
        self._ai_worker.fail.connect(self._ai_thread.quit)
        self._ai_worker.done.connect(self._ai_worker.deleteLater)
        self._ai_worker.fail.connect(self._ai_worker.deleteLater)
        self._ai_thread.finished.connect(self._ai_test_finished)
        self._ai_thread.start()

    def _ai_test_finished(self) -> None:
        from ...infrastructure.ocr.ai_scanner import MODE_LOCAL

        self.ai_test_btn.setEnabled(self.ai_mode_combo.currentData() != MODE_LOCAL)
        self.ai_test_btn.setText(self.tr("st_ai_test"))

    def _ai_test_ok(self, reply: str) -> None:
        QMessageBox.information(
            self, self.tr("st_ai_title"),
            self.tr("st_ai_test_ok", model=self._ai_config().effective_model(),
                    reply=reply))

    def _ai_test_failed(self, message: str) -> None:
        QMessageBox.warning(
            self, self.tr("st_ai_title"), self.tr("st_ai_test_fail", error=message))

    def _change_icon(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("st_icon"), "",
            f"{self.tr('icon_filter')};;{self.tr('all_files')}")
        if not path:
            return
        try:
            self.app.set_app_icon(path)
            self.icon_path_edit.setText(path)
            self.icon_path_edit.setToolTip(path)
            QMessageBox.information(self, self.tr("success"), self.tr("st_icon_changed"))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _reset_icon(self) -> None:
        try:
            self.app.set_app_icon(self.app.DEFAULT_ICON)
            self.icon_path_edit.setText(self.app.DEFAULT_ICON)
            self.icon_path_edit.setToolTip(self.app.DEFAULT_ICON)
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
            # AppContext notifies every window (top bar + pages) after applying it.
            self.app.set_theme_mode(mode)

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

    def _optimize_db(self) -> None:
        try:
            size_bytes = self.app.optimize_database()
            size_kb = round(size_bytes / 1024, 1)
            QMessageBox.information(
                self, self.tr("success"),
                self.tr("st_optimize_success", size=str(size_kb)))
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))
