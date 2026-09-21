from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...domain.enums import PaymentStatus
from ...domain.money import Money
from ...infrastructure.export.exporters import csv_export, excel_export, json_export
from ..widgets import PageHeader, money_display, primary_button, status_chip, error_text


class InvoicesPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._selected_id: int | None = None

        header = PageHeader(self.tr("il_title"),
                            self.tr("il_subtitle"))

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("il_search"))
        self.search_edit.setToolTip(self.tr("tt_il_search"))
        search_btn = primary_button(self.tr("il_btn_search"))
        search_btn.setToolTip(self.tr("tt_il_searchbtn"))
        self.status_combo = QComboBox()
        self.status_combo.setToolTip(self.tr("tt_il_status"))
        self.status_combo.addItem(self.tr("il_filter_status") + " " + self.tr("status_all"))
        self.status_combo.addItem(self.tr("status_unpaid"), PaymentStatus.UNPAID)
        self.status_combo.addItem(self.tr("status_partial"), PaymentStatus.PARTIAL)
        self.status_combo.addItem(self.tr("status_paid"), PaymentStatus.PAID)

        self.table = QTableWidget()
        self.table.setToolTip(self.tr("tt_il_table"))
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            self.tr("il_col_no"), self.tr("il_col_name"), self.tr("il_col_account"),
            self.tr("il_col_date"), self.tr("il_col_kwh"),
            self.tr("il_col_total"), self.tr("il_col_official"), self.tr("il_col_status"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(40)

        self.export_json_btn = QPushButton(self.tr("il_btn_export_json"))
        self.export_json_btn.setToolTip(self.tr("tt_il_json"))
        self.export_csv_btn = QPushButton(self.tr("il_btn_export_csv"))
        self.export_csv_btn.setToolTip(self.tr("tt_il_csv"))
        self.export_excel_btn = QPushButton(self.tr("il_btn_export_excel"))
        self.export_excel_btn.setToolTip(self.tr("tt_il_excel"))
        self.add_invoice_btn = QPushButton("+ " + self.tr("ni_title"))
        self.add_invoice_btn.setToolTip(self.tr("tt_il_add"))

        top = QHBoxLayout()
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.status_combo, 0)
        top.addWidget(search_btn, 0)
        top.addWidget(self.add_invoice_btn, 0)
        exports = QHBoxLayout()
        exports.addWidget(self.export_json_btn)
        exports.addWidget(self.export_csv_btn)
        exports.addWidget(self.export_excel_btn)
        exports.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addLayout(exports)

        search_btn.clicked.connect(self.refresh)
        self.export_json_btn.clicked.connect(lambda: self._export("json"))
        self.export_csv_btn.clicked.connect(lambda: self._export("csv"))
        self.export_excel_btn.clicked.connect(lambda: self._export("excel"))
        self.add_invoice_btn.clicked.connect(self._add_invoice)
        self.table.itemDoubleClicked.connect(self._open_detail)

    def refresh(self) -> None:
        query = self.search_edit.text().strip()
        payment_status = self.status_combo.currentData()
        invoices = self.app.repos["invoices"].search(
            query=query,
            payment_status=payment_status,
            limit=300,
        )
        self.table.setRowCount(len(invoices))
        for r, inv in enumerate(invoices):
            self.table.setItem(r, 0, QTableWidgetItem(inv.invoice_no))
            self.table.setItem(r, 1, QTableWidgetItem(inv.subscriber_name))
            self.table.setItem(r, 2, QTableWidgetItem(inv.account_no))
            self.table.setItem(r, 3, QTableWidgetItem(inv.issue_date.isoformat()))
            self.table.setItem(r, 4, QTableWidgetItem(f"{inv.adjusted_kwh}"))
            self.table.setItem(r, 5, QTableWidgetItem(money_display(inv.total_due)))
            self.table.setItem(r, 6, QTableWidgetItem(
                money_display(inv.official_amount) if inv.official_amount else "—"))
            self.table.setItem(r, 7, QTableWidgetItem(self.app.i18n.enum_label(inv.payment_status)))
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, inv.id)

    def _current_invoice_ids(self) -> list[int]:
        ids: list[int] = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole):
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _export(self, kind: str) -> None:
        invoices = []
        for iid in self._current_invoice_ids():
            inv = self.app.repos["invoices"].get(iid)
            if inv:
                invoices.append(inv)
        if not invoices:
            return
        from PyQt6.QtWidgets import QFileDialog
        filters = {
            "json": "JSON (*.json)",
            "csv": "CSV (*.csv)",
            "excel": "Excel (*.xlsx)",
        }
        path, _ = QFileDialog.getSaveFileName(self, self.tr("il_btn_export_json"), "invoices", filters[kind])
        if not path:
            return
        try:
            if kind == "json":
                for inv in invoices:
                    reading = self.app.repos["invoices"].list_reading(inv.id)
                    charges = self.app.repos["invoices"].list_charges(inv.id)
                    json_export(inv, reading, charges, path)
                    break
            elif kind == "csv":
                rows = []
                for inv in invoices:
                    rows.append({
                        "invoice_no": inv.invoice_no,
                        "account_no": inv.account_no,
                        "subscriber_name": inv.subscriber_name,
                        "issue_date": inv.issue_date.isoformat(),
                        "consumption_kwh": str(inv.adjusted_kwh),
                        "total_due": str(inv.total_due.raw),
                        "payment_status": inv.payment_status.value,
                    })
                csv_export(rows, path)
            else:
                excel_export(invoices, path)
            from PyQt6.QtWidgets import QStatusBar
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _open_detail(self, item: QTableWidgetItem) -> None:
        inv_id = item.data(Qt.ItemDataRole.UserRole)
        if inv_id:
            self.app.open_invoice_detail(inv_id)

    def _add_invoice(self) -> None:
        from .import_invoice import ImportInvoiceDialog
        dialog = ImportInvoiceDialog(self.app, self)
        if dialog.exec():
            self.refresh()