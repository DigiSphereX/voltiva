from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QVBoxLayout, QWidget,
)

from ...domain.enums import PaymentStatus
from ...domain.money import Money
from ..widgets import (
    MoneyEdit, date_edit, error_label, error_text, form_label, ghost_button, primary_button,
)


class InvoiceEditDialog(QDialog):
    def __init__(self, app, invoice, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._invoice = invoice
        self.setWindowTitle(self.tr("edit_invoice"))
        self.setMinimumWidth(480)

        hint = QLabel(self.tr("edit_invalidates"))
        hint.setWordWrap(True)
        hint.setObjectName("Muted")

        self.issue_date = date_edit()
        self.issue_date.setToolTip(self.tr("tt_ed_issue_date"))
        self.issue_date.setDate(QDate(invoice.issue_date.year, invoice.issue_date.month, invoice.issue_date.day))
        self.prev_date = date_edit()
        if invoice.previous_read_date:
            self.prev_date.setDate(QDate(invoice.previous_read_date.year, invoice.previous_read_date.month,
                                         invoice.previous_read_date.day))
        self.curr_date = date_edit()
        if invoice.current_read_date:
            self.curr_date.setDate(QDate(invoice.current_read_date.year, invoice.current_read_date.month,
                                         invoice.current_read_date.day))
        self.official_amount = MoneyEdit()
        self.official_amount.set_money(invoice.official_amount)
        self.notes = QLineEdit(invoice.notes)
        self.notes.setToolTip(self.tr("tt_ed_notes"))
        self.payment_status = QComboBox()
        self.payment_status.setToolTip(self.tr("tt_ed_payment"))
        for s in PaymentStatus:
            self.payment_status.addItem(app.i18n.enum_label(s), s)
        self._set_payment(invoice.payment_status)

        self.err_lbl = error_label()

        save_btn = primary_button(self.tr("save_edits"))
        save_btn.setToolTip(self.tr("tt_ed_save"))
        cancel_btn = ghost_button(self.tr("cancel"))
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for label, widget in (
            (self.tr("issue_date"), self.issue_date),
            (self.tr("ni_prev_date"), self.prev_date),
            (self.tr("ni_curr_date"), self.curr_date),
            (self.tr("vk_official"), self.official_amount),
            (self.tr("il_notes"), self.notes),
            (self.tr("payment_status"), self.payment_status),
        ):
            form.addRow(form_label(label, 130), widget)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(14)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.err_lbl)
        layout.addLayout(buttons)

        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)

    def _set_payment(self, status) -> None:
        for i in range(self.payment_status.count()):
            if self.payment_status.itemData(i) == status:
                self.payment_status.setCurrentIndex(i)
                return

    def _save(self) -> None:
        self.err_lbl.setVisible(False)
        try:
            invoice = self._invoice
            invoice.issue_date = self.issue_date.date().toPyDate()
            invoice.previous_read_date = self.prev_date.date().toPyDate()
            invoice.current_read_date = self.curr_date.date().toPyDate()
            invoice.official_amount = self.official_amount.money()
            invoice.notes = self.notes.text().strip()
            status = self.payment_status.currentData()
            paid, due = invoice.paid_amount.raw, invoice.total_due.raw
            expected = (PaymentStatus.PAID if due > 0 and paid >= due
                        else PaymentStatus.UNPAID if paid <= 0
                        else PaymentStatus.PARTIAL)
            if status != expected:
                # Status must follow the money actually recorded (see PaymentDialog).
                self.err_lbl.setText(self.tr("ed_payment_status_mismatch"))
                self.err_lbl.setVisible(True)
                return
            invoice.payment_status = status

            reading = self.app.repos["invoices"].list_reading(invoice.id)
            if reading:
                reading.previous_date = invoice.previous_read_date or invoice.issue_date
                reading.current_date = invoice.current_read_date or invoice.issue_date
            charges = self.app.repos["invoices"].list_charges(invoice.id)
            self.app.repos["invoices"].save(invoice, reading, charges)
            self.app.repos["uow"].commit()
            self.accept()
        except Exception as exc:
            self.err_lbl.setText(error_text(self.app, exc))
            self.err_lbl.setVisible(True)