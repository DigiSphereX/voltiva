from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...domain.enums import SubscriberType
from ...domain.models import Subscriber
from ..widgets import danger_small_button, money_display, small_button, error_text


class SubscriberDialog(QDialog):
    def __init__(self, app, subscriber: Subscriber | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._subscriber = subscriber
        self.setWindowTitle(self.tr("sb_save"))
        self.setMinimumWidth(480)

        self.account_no = QLineEdit(subscriber.account_no if subscriber else "")
        self.account_no.setToolTip(self.tr("tt_sb_account"))
        self.subscription_no = QLineEdit(subscriber.subscription_no if subscriber else "")
        self.subscription_no.setToolTip(self.tr("tt_sb_subscription"))
        self.name = QLineEdit(subscriber.name if subscriber else "")
        self.name.setToolTip(self.tr("tt_sb_name"))
        self.type_combo = QComboBox()
        self.type_combo.setToolTip(self.tr("tt_sb_type"))
        for t in SubscriberType:
            self.type_combo.addItem(app.i18n.enum_label(t), t)
        if subscriber:
            self.type_combo.setCurrentIndex(self.type_combo.findData(subscriber.subscriber_type))
        self.governorate = QLineEdit(subscriber.governorate if subscriber else "")
        self.governorate.setToolTip(self.tr("tt_sb_governorate"))
        self.qadaa = QLineEdit(subscriber.qadaa if subscriber else "")
        self.qadaa.setToolTip(self.tr("tt_sb_qadaa"))
        self.address = QLineEdit(subscriber.address if subscriber else "")
        self.address.setToolTip(self.tr("tt_sb_address"))

        buttons = QDialogButtonBox()
        save_btn = buttons.addButton(self.tr("sb_save"), QDialogButtonBox.ButtonRole.AcceptRole)
        save_btn.setToolTip(self.tr("tt_sb_save"))
        buttons.addButton(self.tr("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        save_btn.clicked.connect(self._save)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow(self.tr("sb_account_no"), self.account_no)
        form.addRow(self.tr("sb_subscription_no"), self.subscription_no)
        form.addRow(self.tr("sb_name"), self.name)
        form.addRow(self.tr("sb_type"), self.type_combo)
        form.addRow(self.tr("sb_governorate"), self.governorate)
        form.addRow(self.tr("sb_qadaa"), self.qadaa)
        form.addRow(self.tr("sb_address"), self.address)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _save(self) -> None:
        sub = self._subscriber or Subscriber()
        sub.account_no = self.account_no.text().strip()
        sub.subscription_no = self.subscription_no.text().strip() or sub.account_no
        sub.name = self.name.text().strip() or self.tr("sb_default_name").format(no=sub.account_no)
        sub.subscriber_type = self.type_combo.currentData()
        sub.governorate = self.governorate.text().strip()
        sub.qadaa = self.qadaa.text().strip()
        sub.address = self.address.text().strip()
        if not sub.account_no:
            QMessageBox.warning(self, self.tr("error"), self.tr("sb_account_required"))
            return
        try:
            self.app.subscribers.save(sub)
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))


class SubscribersPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr

        title = QLabel(self.tr("sb_title"))
        title.setObjectName("PageTitle")

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("sb_search"))
        search_btn = QPushButton(self.tr("il_btn_search"))
        new_btn = QPushButton("+ " + self.tr("sb_title"))
        new_btn.setToolTip(self.tr("tt_sb_new"))

        self.table = QTableWidget()
        self.table.setToolTip(self.tr("tt_sb_table"))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            self.tr("sb_col_account"), self.tr("sb_col_subscription"), self.tr("sb_col_name"),
            self.tr("sb_col_type"), self.tr("sb_col_governorate"), self.tr("sb_col_debt"),
            self.tr("sb_actions"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 132)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(46)

        top = QHBoxLayout()
        top.addWidget(self.search_edit, 1)
        top.addWidget(search_btn, 0)
        top.addWidget(new_btn, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addLayout(top)
        layout.addWidget(self.table)

        search_btn.clicked.connect(self.refresh)
        new_btn.clicked.connect(self._new)
        self.table.itemDoubleClicked.connect(self._edit_selected)

    def refresh(self) -> None:
        query = self.search_edit.text().strip()
        subscribers = self.app.repos["subscribers"].search(query, limit=100) if query else \
            self.app.repos["subscribers"].list_all()
        self.table.setRowCount(len(subscribers))
        for r, s in enumerate(subscribers):
            self.table.setItem(r, 0, QTableWidgetItem(s.account_no))
            self.table.setItem(r, 1, QTableWidgetItem(s.subscription_no))
            self.table.setItem(r, 2, QTableWidgetItem(s.name))
            self.table.setItem(r, 3, QTableWidgetItem(self.app.i18n.enum_label(s.subscriber_type)))
            self.table.setItem(r, 4, QTableWidgetItem(s.governorate))
            self.table.setItem(r, 5, QTableWidgetItem(money_display(s.previous_debt)))
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, s.id)
            self.table.setCellWidget(r, 6, self._actions_cell(s.id))

    def _actions_cell(self, subscriber_id: int) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        edit_btn = small_button(self.tr("edit"))
        delete_btn = danger_small_button(self.tr("delete"))
        edit_btn.clicked.connect(lambda: self._edit_subscriber(subscriber_id))
        delete_btn.clicked.connect(lambda: self._delete_subscriber(subscriber_id))
        layout.addStretch(1)
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)
        layout.addStretch(1)
        return widget

    def _edit_subscriber(self, subscriber_id: int) -> None:
        sub = self.app.repos["subscribers"].get(subscriber_id)
        if sub:
            dialog = SubscriberDialog(self.app, sub, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh()

    def _delete_subscriber(self, subscriber_id: int) -> None:
        answer = QMessageBox.question(
            self, self.tr("delete"), self.tr("delete_generic_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.app.subscribers.delete(subscriber_id)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _edit_selected(self, item: QTableWidgetItem) -> None:
        subscriber_id = item.data(Qt.ItemDataRole.UserRole)
        if subscriber_id is not None:
            sub = self.app.repos["subscribers"].get(subscriber_id)
            if sub:
                dialog = SubscriberDialog(self.app, sub, self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    self.refresh()

    def _new(self) -> None:
        dialog = SubscriberDialog(self.app, None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()