"""Record a (possibly partial) payment on an invoice."""
from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QVBoxLayout, QWidget,
)

from ...domain.money import Money
from ..widgets import (
    MoneyEdit, date_edit, error_label, error_text, form_label, ghost_button,
    money_display, primary_button,
)

METHODS = ("CASH", "CARD", "CHEQUE", "TRANSFER")


class PaymentDialog(QDialog):
    def __init__(self, app, invoice, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._invoice = invoice
        self._remaining = invoice.total_due - invoice.paid_amount
        self.payment_id: int | None = None
        self.setWindowTitle(self.tr("pay_dlg_title"))
        self.setMinimumWidth(420)

        self.remaining_lbl = QLabel(self.tr("pay_remaining", amount=money_display(self._remaining)))
        self.remaining_lbl.setObjectName("Muted")

        self.amount = MoneyEdit()
        self.fill_btn = ghost_button(self.tr("pay_fill_remaining"))
        amount_row = QHBoxLayout()
        amount_row.addWidget(self.amount, 1)
        amount_row.addWidget(self.fill_btn)

        today = dt.date.today()
        self.date_edit = date_edit(QDate(today.year, today.month, today.day))

        self.method = QComboBox()
        for code in METHODS:
            self.method.addItem(self.tr("pay_method_" + code.lower()), code)

        self.notes = QLineEdit()

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for label, widget in (
            (self.tr("pay_amount"), amount_row),
            (self.tr("pay_date"), self.date_edit),
            (self.tr("pay_method"), self.method),
            (self.tr("pay_notes"), self.notes),
        ):
            form.addRow(form_label(label, 108), widget)

        self.err_lbl = error_label()
        ok_btn = primary_button(self.tr("save"))
        cancel_btn = ghost_button(self.tr("cancel"))
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(ok_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(14)
        layout.addWidget(self.remaining_lbl)
        layout.addLayout(form)
        layout.addWidget(self.err_lbl)
        layout.addLayout(buttons)

        ok_btn.setDefault(True)
        self.fill_btn.clicked.connect(self._fill_remaining)
        ok_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)
        self._fill_remaining()          # most payments settle the whole balance

    def _fill_remaining(self) -> None:
        if self._remaining.raw > 0:
            self.amount.set_money(self._remaining)

    def _save(self) -> None:
        self.err_lbl.setVisible(False)
        try:
            amount = self.amount.money() or Money.zero()        # empty -> rejected as "must be > 0"
            qd = self.date_edit.date()
            repo = self.app.repos["invoices"]
            repo.set_payment(self._invoice.id, amount, dt.date(qd.year(), qd.month(), qd.day()),
                             self.method.currentData(), self.notes.text().strip())
            self.app.repos["uow"].commit()
            self.accept()
        except Exception as exc:  # noqa: BLE001 - shown inside the dialog, nothing is saved
            self.err_lbl.setText(error_text(self.app, exc))
            self.err_lbl.setVisible(True)
