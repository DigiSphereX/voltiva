from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...domain.enums import SubscriberType
from ...domain.models import Subscriber
from ...domain.money import latin_digits
from .. import theme
from ..widgets import (
    DataTable, PageHeader, action_cell, configure_table, danger_small_button,
    error_text, fit_action_column, form_label, ghost_button, money_display, muted,
    primary_button, small_button,
)

_HEADER_ALIGNS = (
    Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft,
    Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight,
    Qt.AlignmentFlag.AlignHCenter,
)


class SubscriberDialog(QDialog):
    def __init__(self, app, subscriber: Subscriber | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._subscriber = subscriber
        self.setWindowTitle(self.tr("sb_save") if subscriber else self.tr("sb_new"))
        self.setMinimumWidth(520)

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
        save_btn.setObjectName("Primary")
        save_btn.setToolTip(self.tr("tt_sb_save"))
        cancel_btn = buttons.addButton(self.tr("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.setObjectName("Ghost")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        buttons.rejected.connect(self.reject)

        title = QLabel(self.tr("sb_save") if subscriber else self.tr("sb_new"))
        title.setObjectName("CardTitle")

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for label, widget in (
            (self.tr("sb_account_no"), self.account_no),
            (self.tr("sb_subscription_no"), self.subscription_no),
            (self.tr("sb_name"), self.name),
            (self.tr("sb_type"), self.type_combo),
            (self.tr("sb_governorate"), self.governorate),
            (self.tr("sb_qadaa"), self.qadaa),
            (self.tr("sb_address"), self.address),
        ):
            form.addRow(form_label(label, 130), widget)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addLayout(form, 1)
        layout.addWidget(buttons)

    def _save(self) -> None:
        sub = self._subscriber or Subscriber()
        sub.account_no = latin_digits(self.account_no.text().strip())
        sub.subscription_no = latin_digits(self.subscription_no.text().strip()) or sub.account_no
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

        new_btn = primary_button("+ " + self.tr("sb_new"))
        new_btn.setToolTip(self.tr("tt_sb_new"))
        header = PageHeader(self.tr("sb_title"), self.tr("sb_subtitle"), actions=[new_btn])

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("sb_search"))
        self.search_edit.setMinimumWidth(240)
        self.search_edit.setMaximumWidth(520)
        self.search_edit.setClearButtonEnabled(True)
        search_btn = ghost_button(self.tr("il_btn_search"))

        self.table = DataTable()
        self.table.setToolTip(self.tr("tt_sb_table"))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            self.tr("sb_col_account"), self.tr("sb_col_subscription"), self.tr("sb_col_name"),
            self.tr("sb_col_type"), self.tr("sb_col_governorate"), self.tr("sb_col_debt"),
            self.tr("sb_actions"),
        ])
        configure_table(
            self.table, aligns=_HEADER_ALIGNS, stretch=(2,),
            widths={0: 116, 1: 112, 3: 118, 4: 132, 5: 132, 6: 224},
            row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.table.set_empty_text(self.tr("sb_none"))

        self.count_lbl = muted("")
        self.export_excel_btn = small_button(self.tr("sb_btn_export_excel"))
        self.export_excel_btn.setToolTip(self.tr("tt_sb_export_excel"))
        self.export_csv_btn = small_button(self.tr("sb_btn_export_csv"))
        self.export_csv_btn.setToolTip(self.tr("tt_sb_export_csv"))

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self.search_edit, 1)
        top.addWidget(search_btn, 0)
        top.addStretch(1)
        exports = QHBoxLayout()
        exports.setSpacing(8)
        exports.addWidget(self.export_excel_btn)
        exports.addWidget(self.export_csv_btn)
        exports.addStretch(1)
        exports.addWidget(self.count_lbl)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.Metrics.PAGE_MARGIN, 18, theme.Metrics.PAGE_MARGIN, 18)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(exports)

        search_btn.clicked.connect(self.refresh)
        self.search_edit.returnPressed.connect(self.refresh)
        new_btn.clicked.connect(self._new)
        self.export_excel_btn.clicked.connect(lambda: self._export_subscribers("excel"))
        self.export_csv_btn.clicked.connect(lambda: self._export_subscribers("csv"))
        self.table.itemDoubleClicked.connect(self._edit_selected)

    def refresh(self) -> None:
        query = latin_digits(self.search_edit.text().strip())
        subscribers = self.app.repos["subscribers"].search(query, limit=100) if query else \
            self.app.repos["subscribers"].list_all()
        colors = theme.colors()
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        self.table.setUpdatesEnabled(False)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(subscribers))
            for r, s in enumerate(subscribers):
                values = (
                    s.account_no, s.subscription_no, s.name,
                    self.app.i18n.enum_label(s.subscriber_type), s.governorate,
                    money_display(s.previous_debt),
                )
                for c, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(right if c == 5 else left)
                    item.setData(Qt.ItemDataRole.UserRole, s.id)
                    if c == 5 and s.previous_debt.raw > 0:
                        item.setForeground(QColor(colors["danger"]))
                    self.table.setItem(r, c, item)
                actions = self._actions_cell(s.id)
                self.table.setCellWidget(r, 6, actions)
                fit_action_column(self.table, 6, actions)
        finally:
            self.table.setUpdatesEnabled(True)
        self.count_lbl.setText(self.tr("sb_showing", n=str(len(subscribers))))

    def _actions_cell(self, subscriber_id: int) -> QWidget:
        edit_btn = small_button(self.tr("edit"))
        inv_btn = small_button(self.tr("sb_view_invoices"))
        inv_btn.setToolTip(self.tr("tt_sb_view_invoices"))
        delete_btn = danger_small_button(self.tr("delete"))
        edit_btn.clicked.connect(lambda: self._edit_subscriber(subscriber_id))
        inv_btn.clicked.connect(lambda: self._view_invoices(subscriber_id))
        delete_btn.clicked.connect(lambda: self._delete_subscriber(subscriber_id))
        return action_cell(edit_btn, inv_btn, delete_btn)

    def _view_invoices(self, subscriber_id: int) -> None:
        sub = self.app.repos["subscribers"].get(subscriber_id)
        if sub:
            self.app.pending_invoice_filter = {"query": sub.account_no}
            self.app.navigate("invoices")

    def _export_subscribers(self, kind: str) -> None:
        from pathlib import Path
        from ...infrastructure.export.exporters import csv_export_subscribers, excel_export_subscribers
        subscribers = self.app.repos["subscribers"].list_all()
        if not subscribers:
            return
        filters = {"excel": "Excel (*.xlsx)", "csv": "CSV (*.csv)"}
        title = self.tr("sb_btn_export_excel") if kind == "excel" else self.tr("sb_btn_export_csv")
        path, _ = QFileDialog.getSaveFileName(self, title, "subscribers", filters[kind])
        if not path:
            return
        try:
            if kind == "excel":
                excel_export_subscribers(subscribers, path)
            else:
                csv_export_subscribers(subscribers, path)
            QMessageBox.information(
                self, self.tr("success"),
                self.tr("il_export_success", path=Path(path).name))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _edit_subscriber(self, subscriber_id: int) -> None:
        sub = self.app.repos["subscribers"].get(subscriber_id)
        if sub:
            dialog = SubscriberDialog(self.app, sub, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh()

    def _delete_subscriber(self, subscriber_id: int) -> None:
        from ...domain.enums import PaymentStatus
        sub = self.app.repos["subscribers"].get(subscriber_id)
        invoices = self.app.repos["invoices"].search(subscriber_id=subscriber_id, limit=100) if sub else []
        unpaid = sum(1 for i in invoices if i.payment_status != PaymentStatus.PAID)
        if invoices:
            prompt = self.tr("sb_has_invoices_warning", count=len(invoices), unpaid=unpaid)
        else:
            prompt = self.tr("delete_generic_confirm")
        answer = QMessageBox.question(
            self, self.tr("delete"), prompt,
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
