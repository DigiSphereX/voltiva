from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFileDialog, QGridLayout, QHBoxLayout, QLabel, QListWidget, QMessageBox,
    QScrollArea, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...infrastructure.export.exporters import json_export
from ...domain.money import fmt_quantity
from ...infrastructure.export.pdf_exporter import build_invoice_html, build_receipt_html, print_invoice, render_to_pdf
from .. import theme
from ..widgets import (
    DataTable, PageHeader, Section, configure_table, danger_small_button, digits,
    error_text, ghost_button, money_display, primary_button, small_button,
)


class InvoiceDetailPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._invoice_id: int | None = None
        self._payments: list = []

        recalc_btn = small_button(self.tr("recalc"))
        edit_btn = ghost_button(self.tr("edit_invoice"))
        mark_paid_btn = primary_button(self.tr("iv_mark_paid"))
        self.add_payment_btn = ghost_button(self.tr("iv_add_payment"))
        self.receipt_btn = small_button(self.tr("iv_receipt"))
        self.receipt_btn.setEnabled(False)
        delete_btn = danger_small_button(self.tr("cancel_invoice"))
        print_btn = small_button(self.tr("il_btn_print"))
        pdf_btn = small_button(self.tr("il_btn_export_pdf"))
        json_btn = small_button(self.tr("il_btn_export_json"))
        recalc_btn.setToolTip(self.tr("tt_iv_recalc"))
        edit_btn.setToolTip(self.tr("tt_iv_edit"))
        mark_paid_btn.setToolTip(self.tr("tt_iv_mark_paid"))
        delete_btn.setToolTip(self.tr("tt_iv_cancel"))
        print_btn.setToolTip(self.tr("tt_iv_print"))

        self.header = PageHeader("", "", actions=[edit_btn, self.add_payment_btn, mark_paid_btn])
        back_btn = ghost_button("← " + self.tr("il_title"))
        back_btn.setToolTip(self.tr("tt_iv_back"))
        back_btn.clicked.connect(lambda: self.app.navigate("invoices"))
        self.header.layout().insertWidget(0, back_btn, 0, Qt.AlignmentFlag.AlignTop)

        secondary = QHBoxLayout()
        secondary.setSpacing(8)
        secondary.addWidget(recalc_btn)
        secondary.addWidget(print_btn)
        secondary.addWidget(pdf_btn)
        secondary.addWidget(json_btn)
        secondary.addWidget(self.receipt_btn)
        secondary.addStretch(1)
        secondary.addWidget(delete_btn)

        self._details_grid = QGridLayout()
        self._details_grid.setContentsMargins(0, 0, 0, 0)
        self._details_grid.setHorizontalSpacing(14)
        self._details_grid.setVerticalSpacing(9)
        details_card = Section(self.tr("iv_details"))
        details_card.body.addLayout(self._details_grid)

        self.charges_table = DataTable()
        self.charges_table.setToolTip(self.tr("tt_iv_charges"))
        self.charges_table.setColumnCount(3)
        self.charges_table.setHorizontalHeaderLabels([
            self.tr("iv_col_name"), self.tr("iv_col_type"), self.tr("iv_col_amount")])
        configure_table(self.charges_table, widths={1: 176, 2: 156}, stretch=(0,),
                        row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.charges_table.set_empty_text(self.tr("iv_no_charges"))
        charges_card = Section(self.tr("iv_charges"))
        charges_card.body.addWidget(self.charges_table)

        self.payments_table = DataTable()
        self.payments_table.setToolTip(self.tr("iv_payments"))
        self.payments_table.setColumnCount(4)
        self.payments_table.setHorizontalHeaderLabels([
            self.tr("pay_col_date"), self.tr("pay_col_amount"),
            self.tr("pay_col_method"), self.tr("pay_col_notes")])
        configure_table(self.payments_table, widths={0: 116, 1: 148, 2: 128}, stretch=(3,),
                        row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.payments_table.set_empty_text(self.tr("iv_no_payments"))
        payments_card = Section(self.tr("iv_payments"))
        payments_card.body.addWidget(self.payments_table)

        self.audit_list = QListWidget()
        self.audit_list.setObjectName("AuditList")
        self.audit_list.setToolTip(self.tr("tt_iv_audit"))
        self.audit_list.setMaximumHeight(146)
        audit_card = Section(self.tr("iv_audit"))
        audit_card.body.addWidget(self.audit_list)

        mid = QHBoxLayout()
        mid.setSpacing(theme.Metrics.PAGE_SPACING)
        mid.addWidget(charges_card, 1)
        mid.addWidget(payments_card, 1)

        container = QWidget()
        body = QVBoxLayout(container)
        body.setContentsMargins(
            theme.Metrics.PAGE_MARGIN, 18, theme.Metrics.PAGE_MARGIN, 18)
        body.setSpacing(theme.Metrics.PAGE_SPACING)
        body.addWidget(self.header)
        body.addLayout(secondary)
        body.addWidget(details_card)
        body.addLayout(mid)
        body.addWidget(audit_card)
        body.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(container)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        recalc_btn.clicked.connect(self._recalculate)
        edit_btn.clicked.connect(self._edit)
        mark_paid_btn.clicked.connect(self._mark_paid)
        self.add_payment_btn.clicked.connect(self._add_payment)
        self.receipt_btn.clicked.connect(self._export_receipt)
        self.payments_table.itemSelectionChanged.connect(
            lambda: self.receipt_btn.setEnabled(self.payments_table.currentRow() >= 0))
        delete_btn.clicked.connect(self._delete)
        print_btn.clicked.connect(self._print_invoice)
        pdf_btn.clicked.connect(self._export_pdf)
        json_btn.clicked.connect(self._export_json)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self._print_invoice)

    def refresh(self) -> None:
        if self._invoice_id is not None:
            self.open_invoice(self._invoice_id)

    def open_invoice(self, invoice_id: int) -> None:
        self._invoice_id = invoice_id
        invoice = self.app.repos["invoices"].get(invoice_id)
        if invoice is None:
            return
        self.header.set_title(
            f"{invoice.invoice_no} — {invoice.subscriber_name}",
            digits(invoice.issue_date.strftime("%d/%m/%Y")) + " · "
            + self.app.i18n.enum_label(invoice.payment_status))
        charges = self.app.repos["invoices"].list_charges(invoice_id)

        rows = [
            (self.tr("iv_no"), invoice.invoice_no),
            (self.tr("iv_account"), digits(invoice.account_no)),
            (self.tr("iv_subscriber"), invoice.subscriber_name),
            (self.tr("iv_date"), digits(invoice.issue_date.strftime("%d/%m/%Y"))),
            (self.tr("iv_prev_reading"), digits(fmt_quantity(invoice.previous_reading))),
            (self.tr("iv_curr_reading"), digits(fmt_quantity(invoice.current_reading))),
            (self.tr("iv_consumption"), f"{digits(fmt_quantity(invoice.consumption_kwh))} {self.tr('unit_kwh')}"),
            (self.tr("iv_adjusted"), f"{digits(fmt_quantity(invoice.adjusted_kwh))} {self.tr('unit_kwh')}"),
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

        self._fill_details(rows)

        self.charges_table.clearContents()
        self.charges_table.setRowCount(len(charges))
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        for i, c in enumerate(charges):
            for col, text, align in (
                (0, c.name, left),
                (1, self.app.i18n.enum_label(c.category), left),
                (2, money_display(c.amount), right),
            ):
                item = QTableWidgetItem(text)
                item.setTextAlignment(align)
                self.charges_table.setItem(i, col, item)
        self.charges_table.setFixedHeight(
            theme.Metrics.HEADER_H + max(len(charges), 1) * theme.Metrics.ROW_H + 2)

        self._fill_payments(invoice)

        self.audit_list.clear()
        entries = self.app.invoices.audit.list_for_invoice(invoice_id, limit=50)
        for entry in entries:
            self.audit_list.addItem(f"[{entry.action}] {entry.description}")
        if not entries:
            self.audit_list.addItem(self.tr("iv_no_audit"))

    def _fill_details(self, rows: list[tuple[str, str]]) -> None:
        while self._details_grid.count():
            item = self._details_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        total_label = self.tr("iv_total_due")
        for i, (label, value) in enumerate(rows):
            row, pair = divmod(i, 2)
            caption = QLabel(label)
            caption.setObjectName("DetailLabel")
            caption.setMinimumWidth(132)
            text = QLabel(str(value))
            text.setObjectName("DetailTotal" if label == total_label else "DetailValue")
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._details_grid.addWidget(
                caption, row, pair * 2, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeading)
            self._details_grid.addWidget(
                text, row, pair * 2 + 1, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeading)
        self._details_grid.setColumnStretch(0, 0)
        self._details_grid.setColumnStretch(1, 1)
        self._details_grid.setColumnStretch(2, 0)
        self._details_grid.setColumnStretch(3, 1)

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
            self, self.tr("cancel_invoice"), self.tr("cancel_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            # soft delete: the row, its number and its audit trail are kept (the old code erased
            # the row, which also let the number be reused); refused when payments exist
            self.app.invoices.cancel(self._invoice_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))
            return
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
            remaining = invoice.total_due - invoice.paid_amount
            if remaining.raw <= 0:
                QMessageBox.information(self, self.tr("success"), self.tr("iv_already_paid"))
                return
            self.app.repos["invoices"].set_payment(
                self._invoice_id, remaining, dt.date.today(), "CASH", self.tr("iv_pay_notes_full"))
            self.app.repos["uow"].commit()
            self.open_invoice(self._invoice_id)
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _fill_payments(self, invoice) -> None:
        from ...domain.enums import InvoiceStatus
        self._payments = self.app.repos["invoices"].list_payments(invoice.id)
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        self.payments_table.clearContents()
        self.payments_table.setRowCount(len(self._payments))
        for r, pay in enumerate(self._payments):
            method_key = "pay_method_" + str(pay.method).lower()
            method = self.tr(method_key)
            cells = [(digits(pay.paid_at.strftime("%d/%m/%Y")), left),
                     (money_display(pay.amount), right),
                     (method if method != method_key else str(pay.method), left),
                     (pay.notes or "", left)]
            for col, (text, align) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(align)
                self.payments_table.setItem(r, col, item)
        shown = min(max(len(self._payments), 1), 4)
        self.payments_table.setFixedHeight(
            theme.Metrics.HEADER_H + shown * theme.Metrics.ROW_H + 2)
        self.receipt_btn.setEnabled(False)
        # payments only make sense on a live invoice that still has a balance
        open_balance = (invoice.total_due - invoice.paid_amount).raw > 0
        self.add_payment_btn.setEnabled(invoice.status == InvoiceStatus.ACTIVE and open_balance)

    def _add_payment(self) -> None:
        if self._invoice_id is None:
            return
        invoice = self.app.repos["invoices"].get(self._invoice_id)
        if invoice is None:
            return
        from .payment_dialog import PaymentDialog
        if PaymentDialog(self.app, invoice, self).exec():
            self.open_invoice(self._invoice_id)

    def _export_receipt(self) -> None:
        row = self.payments_table.currentRow()
        if self._invoice_id is None or not (0 <= row < len(self._payments)):
            return
        invoice = self.app.repos["invoices"].get(self._invoice_id)
        if invoice is None:
            return
        payment = self._payments[row]
        try:
            suggested = f"R-{payment.id:06d}.pdf" if payment.id else f"{invoice.invoice_no}-receipt.pdf"
            path, _ = QFileDialog.getSaveFileName(self, self.tr("iv_receipt"), suggested, "PDF (*.pdf)")
            if not path:
                return
            from ..currencies import get_currency_code
            html = build_receipt_html(invoice, payment, lang=self.app.i18n.lang, i18n=self.app.i18n,
                                      currency=get_currency_code())
            render_to_pdf(html, path, page_lang=self.app.i18n.lang)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _print_invoice(self) -> None:
        if self._invoice_id is None:
            return
        invoice = self.app.repos["invoices"].get(self._invoice_id)
        if invoice is None:
            return
        try:
            reading = self.app.repos["invoices"].list_reading(self._invoice_id)
            charges = self.app.repos["invoices"].list_charges(self._invoice_id)
            from ..currencies import get_currency_code
            html = build_invoice_html(
                invoice, reading, charges,
                lang=self.app.i18n.lang, i18n=self.app.i18n, currency=get_currency_code())
            print_invoice(html, page_lang=self.app.i18n.lang)
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
                self, self.tr("il_btn_export_pdf"), f"{invoice.invoice_no}.pdf", "PDF (*.pdf)")
            if not path:
                return
            reading = self.app.repos["invoices"].list_reading(self._invoice_id)
            charges = self.app.repos["invoices"].list_charges(self._invoice_id)
            from ..currencies import get_currency_code
            html = build_invoice_html(
                invoice, reading, charges,
                lang=self.app.i18n.lang, i18n=self.app.i18n, currency=get_currency_code())
            render_to_pdf(html, path)
            QMessageBox.information(
                self, self.tr("success"),
                self.tr("il_export_success", path=Path(path).name))
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
                self, self.tr("il_btn_export_json"), f"{invoice.invoice_no}.json", "JSON (*.json)")
            if not path:
                return
            reading = self.app.repos["invoices"].list_reading(self._invoice_id)
            charges = self.app.repos["invoices"].list_charges(self._invoice_id)
            json_export(invoice, reading, charges, path)
            QMessageBox.information(
                self, self.tr("success"),
                self.tr("il_export_success", path=Path(path).name))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))
