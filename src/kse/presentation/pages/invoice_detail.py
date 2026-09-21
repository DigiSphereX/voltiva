from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QListWidget, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...domain.money import Money
from ...infrastructure.export.exporters import json_export
from ...infrastructure.export.pdf_exporter import build_invoice_html, render_to_pdf
from ..widgets import FormRow, danger_button, ghost_button, money_display, primary_button, error_text, digits


class InvoiceDetailPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._invoice_id: int | None = None

        self.title = QLabel("")
        self.title.setObjectName("PageTitle")
        back_btn = QPushButton("← " + self.tr("il_title"))
        back_btn.setToolTip(self.tr("tt_iv_back"))
        back_btn.clicked.connect(lambda: self.app.navigate("invoices"))

        self.detail_table = QTableWidget()
        self.detail_table.setToolTip(self.tr("tt_iv_table"))
        self.detail_table.setColumnCount(2)
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.detail_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        charges_lbl = QLabel(self.tr("iv_charges"))
        charges_lbl.setObjectName("StepTitle")
        self.charges_table = QTableWidget()
        self.charges_table.setToolTip(self.tr("tt_iv_charges"))
        self.charges_table.setColumnCount(3)
        self.charges_table.setHorizontalHeaderLabels([
            self.tr("iv_col_name"), self.tr("iv_col_type"), self.tr("iv_col_amount")])
        self.charges_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        audit_lbl = QLabel(self.tr("iv_audit"))
        audit_lbl.setObjectName("StepTitle")
        self.audit_list = QListWidget()
        self.audit_list.setToolTip(self.tr("tt_iv_audit"))

        recalc_btn = ghost_button(self.tr("recalc"))
        edit_btn = QPushButton(self.tr("edit_invoice"))
        mark_paid_btn = primary_button(self.tr("iv_mark_paid"))
        delete_btn = danger_button(self.tr("delete_invoice"))
        pdf_btn = QPushButton(self.tr("il_btn_export_pdf"))
        json_btn = QPushButton(self.tr("il_btn_export_json"))
        recalc_btn.setToolTip(self.tr("tt_iv_recalc"))
        edit_btn.setToolTip(self.tr("tt_iv_edit"))
        mark_paid_btn.setToolTip(self.tr("tt_iv_mark_paid"))
        delete_btn.setToolTip(self.tr("tt_iv_delete"))
        actions = QHBoxLayout()
        actions.addWidget(recalc_btn)
        actions.addWidget(edit_btn)
        actions.addWidget(mark_paid_btn)
        actions.addWidget(delete_btn)
        actions.addWidget(pdf_btn)
        actions.addWidget(json_btn)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(back_btn)
        layout.addWidget(self.title)
        layout.addWidget(self.detail_table)
        layout.addWidget(charges_lbl)
        layout.addWidget(self.charges_table)
        layout.addWidget(audit_lbl)
        layout.addWidget(self.audit_list)
        layout.addLayout(actions)

        recalc_btn.clicked.connect(self._recalculate)
        edit_btn.clicked.connect(self._edit)
        mark_paid_btn.clicked.connect(self._mark_paid)
        delete_btn.clicked.connect(self._delete)
        pdf_btn.clicked.connect(self._export_pdf)
        json_btn.clicked.connect(self._export_json)

    def open_invoice(self, invoice_id: int) -> None:
        self._invoice_id = invoice_id
        invoice = self.app.repos["invoices"].get(invoice_id)
        if invoice is None:
            return
        self.title.setText(f"{invoice.invoice_no} — {invoice.subscriber_name}")
        reading = self.app.repos["invoices"].list_reading(invoice_id)
        charges = self.app.repos["invoices"].list_charges(invoice_id)

        rows = [
            (self.tr("iv_no"), invoice.invoice_no),
            (self.tr("iv_account"), invoice.account_no),
            (self.tr("iv_subscriber"), invoice.subscriber_name),
            (self.tr("iv_date"), str(invoice.issue_date)),
            (self.tr("iv_prev_reading"), f"{digits(invoice.previous_reading)}"),
            (self.tr("iv_curr_reading"), f"{digits(invoice.current_reading)}"),
            (self.tr("iv_consumption"), f"{digits(invoice.consumption_kwh)} {self.tr('unit_kwh')}"),
            (self.tr("iv_adjusted"), f"{digits(invoice.adjusted_kwh)} {self.tr('unit_kwh')}"),
            (self.tr("iv_tariff"), f"{invoice.tariff_name} (v{invoice.tariff_version})"),
            (self.tr("iv_energy"), money_display(invoice.energy_cost)),
            (self.tr("iv_fixed"), money_display(invoice.fixed_fees)),
            (self.tr("iv_additional"), money_display(invoice.additional_fees)),
            (self.tr("iv_discounts"), money_display(invoice.discounts)),
            (self.tr("iv_prev_debt"), money_display(invoice.previous_debt)),
            (self.tr("iv_current_amount"), money_display(invoice.current_amount)),
            (self.tr("iv_total_due"), money_display(invoice.total_due)),
        ]
        if invoice.official_amount is not None:
            rows.append((self.tr("iv_official_amt"), money_display(invoice.official_amount)))
            rows.append((self.tr("iv_diff"), money_display(invoice.comparison_diff)))
            comp = invoice.comparison_status
            value = comp.value if hasattr(comp, "value") else comp
            rows.append((self.tr("iv_status"), self.tr("status_" + str(value).lower())))
        rows.append((self.tr("iv_pay_status"), self.app.i18n.enum_label(invoice.payment_status)))
        if invoice.notes:
            rows.append((self.tr("iv_notes"), invoice.notes))

        self.detail_table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            self.detail_table.setItem(i, 0, QTableWidgetItem(str(label)))
            self.detail_table.setItem(i, 1, QTableWidgetItem(str(value)))

        self.charges_table.setRowCount(len(charges))
        for i, c in enumerate(charges):
            self.charges_table.setItem(i, 0, QTableWidgetItem(c.name))
            self.charges_table.setItem(i, 1, QTableWidgetItem(self.app.i18n.enum_label(c.category)))
            self.charges_table.setItem(i, 2, QTableWidgetItem(money_display(c.amount)))

        self.audit_list.clear()
        for entry in self.app.invoices.audit.list_for_invoice(invoice_id, limit=50):
            self.audit_list.addItem(f"[{entry.action}] {entry.description}")

    def _edit(self) -> None:
        if self._invoice_id is None:
            return
        invoice = self.app.repos["invoices"].get(self._invoice_id)
        if invoice is None:
            return
        from .edit_invoice import InvoiceEditDialog
        dialog = InvoiceEditDialog(self.app, invoice, self)
        if dialog.exec():
            self.open_invoice(self._invoice_id)

    def _delete(self) -> None:
        if self._invoice_id is None:
            return
        from PyQt6.QtWidgets import QMessageBox
        answer = QMessageBox.question(
            self, self.tr("delete_invoice"), self.tr("delete_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.app.repos["invoices"].delete(self._invoice_id)
        self.app.repos["uow"].commit()
        self.app.navigate("invoices")

    def _recalculate(self) -> None:
        if self._invoice_id is None:
            return
        try:
            invoice = self.app.invoices.recalculate(self._invoice_id)
            self.open_invoice(self._invoice_id)
            QMessageBox.information(self, self.tr("success"), self.tr("iv_recalc_done").format(no=invoice.invoice_no))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _mark_paid(self) -> None:
        if self._invoice_id is None:
            return
        invoice = self.app.repos["invoices"].get(self._invoice_id)
        if invoice is None:
            return
        try:
            import datetime as dt
            self.app.repos["invoices"].set_payment(
                self._invoice_id, invoice.total_due, dt.date.today(), "CASH", self.tr("iv_pay_notes_full"))
            self.app.repos["uow"].commit()
            self.open_invoice(self._invoice_id)
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _export_pdf(self) -> None:
        if self._invoice_id is None:
            return
        invoice = self.app.repos["invoices"].get(self._invoice_id)
        if invoice is None:
            return
        try:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export PDF", f"{invoice.invoice_no}.pdf", "PDF (*.pdf)")
            if not path:
                return
            reading = self.app.repos["invoices"].list_reading(self._invoice_id)
            charges = self.app.repos["invoices"].list_charges(self._invoice_id)
            from ..currencies import get_currency_code
            html = build_invoice_html(
                invoice, reading, charges,
                lang=self.app.i18n.lang, i18n=self.app.i18n, currency=get_currency_code())
            render_to_pdf(html, path)
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _export_json(self) -> None:
        if self._invoice_id is None:
            return
        invoice = self.app.repos["invoices"].get(self._invoice_id)
        if invoice is None:
            return
        try:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export JSON", f"{invoice.invoice_no}.json", "JSON (*.json)")
            if not path:
                return
            reading = self.app.repos["invoices"].list_reading(self._invoice_id)
            charges = self.app.repos["invoices"].list_charges(self._invoice_id)
            json_export(invoice, reading, charges, path)
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))