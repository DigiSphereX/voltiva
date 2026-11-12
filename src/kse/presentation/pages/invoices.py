from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...domain.enums import InvoiceStatus, PaymentStatus
from ...domain.money import Money, fmt_quantity, latin_digits
from ...infrastructure.export.exporters import csv_export, excel_export, json_export_many
from .. import theme
from ..filters import month_bounds
from ..widgets import (
    DataTable, PageHeader, chip_cell, configure_table, error_text,
    ghost_button, money_display, muted, primary_button, small_button,
)

_RESULT_LIMIT = 500
# table column -> repository ``order_by`` key (a whitelist on the repository side)
_COLUMN_KEYS = ("no", "name", "account", "date", "kwh", "total", "official", "status")
_DESC_FIRST = {"date", "kwh", "total", "official"}      # newest / biggest first on the first click
_HEADER_ALIGNS = (
    Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft,
    Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
    Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignHCenter,
)


class InvoicesPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._selected_id: int | None = None

        self.add_invoice_btn = primary_button("+ " + self.tr("ni_title"))
        self.add_invoice_btn.setToolTip(self.tr("tt_il_add"))
        header = PageHeader(self.tr("il_title"), self.tr("il_subtitle"),
                            actions=[self.add_invoice_btn])

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.tr("il_search"))
        self.search_edit.setToolTip(self.tr("tt_il_search"))
        self.search_edit.setMinimumWidth(240)
        self.search_edit.setMaximumWidth(520)
        self.search_edit.setClearButtonEnabled(True)
        search_btn = ghost_button(self.tr("il_btn_search"))
        search_btn.setToolTip(self.tr("tt_il_searchbtn"))
        self.status_combo = QComboBox()
        self.status_combo.setToolTip(self.tr("tt_il_status"))
        self.status_combo.setMinimumWidth(170)
        self.status_combo.addItem(self.tr("il_filter_status") + " " + self.tr("status_all"))
        self.status_combo.addItem(self.tr("status_unpaid"), PaymentStatus.UNPAID)
        self.status_combo.addItem(self.tr("status_partial"), PaymentStatus.PARTIAL)
        self.status_combo.addItem(self.tr("status_paid"), PaymentStatus.PAID)

        self.table = DataTable()
        self.table.setToolTip(self.tr("tt_il_table"))
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            self.tr("il_col_no"), self.tr("il_col_name"), self.tr("il_col_account"),
            self.tr("il_col_date"), self.tr("il_col_kwh"),
            self.tr("il_col_total"), self.tr("il_col_official"), self.tr("il_col_status"),
        ])
        configure_table(
            self.table, aligns=_HEADER_ALIGNS, stretch=(1,),
            widths={0: 152, 2: 104, 3: 104, 4: 138, 5: 114, 6: 114, 7: 120},
            row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.table.set_empty_text(self.tr("il_none"))
        self.table.horizontalHeader().setSectionsClickable(True)   # click a header to sort
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSortIndicator(3, Qt.SortOrder.DescendingOrder)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._sort_key, self._sort_desc = "date", True
        self._month: str | None = None                 # "YYYY-MM" filter set from the analytics chart
        self.month_btn = ghost_button("")
        self.month_btn.setObjectName("Small")
        self.month_btn.setVisible(False)
        self.month_btn.clicked.connect(self._clear_month)
        self.count_lbl = muted("")

        self.export_json_btn = small_button(self.tr("il_btn_export_json"))
        self.export_json_btn.setToolTip(self.tr("tt_il_json"))
        self.export_csv_btn = small_button(self.tr("il_btn_export_csv"))
        self.export_csv_btn.setToolTip(self.tr("tt_il_csv"))
        self.export_excel_btn = small_button(self.tr("il_btn_export_excel"))
        self.export_excel_btn.setToolTip(self.tr("tt_il_excel"))

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.status_combo, 0)
        top.addWidget(search_btn, 0)
        top.addWidget(self.month_btn, 0)
        top.addStretch(1)
        exports = QHBoxLayout()
        exports.setSpacing(8)
        exports.addWidget(self.export_json_btn)
        exports.addWidget(self.export_csv_btn)
        exports.addWidget(self.export_excel_btn)
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
        self.search_edit.returnPressed.connect(self.refresh)          # Enter searches
        self.status_combo.currentIndexChanged.connect(lambda _i: self.refresh())   # filter applies at once
        self.export_json_btn.clicked.connect(lambda: self._export("json"))
        self.export_csv_btn.clicked.connect(lambda: self._export("csv"))
        self.export_excel_btn.clicked.connect(lambda: self._export("excel"))
        self.add_invoice_btn.clicked.connect(self._add_invoice)
        self.table.itemDoubleClicked.connect(self._open_detail)

    def focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _on_header_clicked(self, col: int) -> None:
        if not 0 <= col < len(_COLUMN_KEYS):
            return
        key = _COLUMN_KEYS[col]
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key, self._sort_desc = key, key in _DESC_FIRST
        self.table.horizontalHeader().setSortIndicator(
            col, Qt.SortOrder.DescendingOrder if self._sort_desc else Qt.SortOrder.AscendingOrder)
        self.refresh()

    def _clear_month(self) -> None:
        self._month = None
        self.refresh()

    def _take_pending_filter(self) -> None:
        """Another page (analytics or subscribers) asked to show one month or query: reset filters appropriately."""
        pending = getattr(self.app, "pending_invoice_filter", None)
        if not pending:
            return
        self.app.pending_invoice_filter = None
        self._month = pending.get("month")
        query = pending.get("query", "")
        for widget in (self.search_edit, self.status_combo):
            widget.blockSignals(True)
        self.search_edit.setText(query)
        self.status_combo.setCurrentIndex(0)
        for widget in (self.search_edit, self.status_combo):
            widget.blockSignals(False)

    def refresh(self) -> None:
        self._take_pending_filter()
        repo = self.app.repos["invoices"]
        # Typing ١٢٠... on an Arabic keyboard must match the stored ASCII account numbers.
        query = latin_digits(self.search_edit.text().strip())
        payment_status = self.status_combo.currentData()
        date_from, date_to = month_bounds(self._month)
        if self._month and date_from is None:        # malformed key: drop the filter
            self._month = None
        self.month_btn.setVisible(bool(self._month))
        if self._month:
            self.month_btn.setText("✕  " + self.tr("il_month_filter", month=str(self._month)))
            self.month_btn.setToolTip(self.tr("il_clear_filter"))
        invoices = repo.search(query=query, payment_status=payment_status, date_from=date_from, date_to=date_to,
                               order_by=self._sort_key, descending=self._sort_desc, limit=_RESULT_LIMIT)
        c = theme.colors()
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        self.table.setUpdatesEnabled(False)          # one repaint instead of one per cell
        try:
            self.table.clearContents()
            self.table.setRowCount(len(invoices))
            for r, inv in enumerate(invoices):
                live = inv.status == InvoiceStatus.ACTIVE
                if not live:                          # history rows: muted, with their own status chip
                    chip_text = self.tr("status_recalculated" if inv.status == InvoiceStatus.RECALCULATED
                                        else "status_cancelled")
                    chip_color = c["muted"]
                elif inv.payment_status == PaymentStatus.PAID:
                    chip_text, chip_color = self.tr("status_paid"), c["success"]
                elif inv.payment_status == PaymentStatus.PARTIAL:
                    chip_text, chip_color = self.tr("status_partial"), c["warn"]
                else:
                    chip_text, chip_color = self.tr("status_unpaid"), c["danger"]
                cells = [
                    (inv.invoice_no, left),
                    (inv.subscriber_name or "—", left),
                    (inv.account_no, left),
                    (inv.issue_date.strftime("%d/%m/%Y"), left),
                    (fmt_quantity(inv.adjusted_kwh), right),
                    (money_display(inv.total_due), right),
                    (money_display(inv.official_amount) if inv.official_amount else "—", right),
                ]
                for col, (text, align) in enumerate(cells):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(align)
                    item.setData(Qt.ItemDataRole.UserRole, inv.id)
                    if col in (0, 1):                 # pinned / stretched columns can clip: keep full text
                        item.setToolTip(text)
                    if col == 0:
                        font = QFont(item.font())
                        font.setWeight(QFont.Weight.DemiBold)
                        item.setFont(font)
                    if not live:
                        item.setForeground(QColor(c["muted"]))
                    self.table.setItem(r, col, item)
                status_item = QTableWidgetItem("")
                status_item.setData(Qt.ItemDataRole.UserRole, inv.id)
                self.table.setItem(r, 7, status_item)
                self.table.setCellWidget(r, 7, chip_cell(chip_text, chip_color))
        finally:
            self.table.setUpdatesEnabled(True)

        total = repo.count(payment_status=payment_status, query=query, date_from=date_from, date_to=date_to)
        if not invoices:
            self.count_lbl.setText(self.tr("il_none"))
        elif len(invoices) < total:
            self.count_lbl.setText(self.tr("il_showing", shown=str(len(invoices)), total=str(total)))
        else:
            self.count_lbl.setText(self.tr("il_showing_all", total=str(len(invoices))))

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
        title_map = {
            "json": self.tr("il_btn_export_json"),
            "csv": self.tr("il_btn_export_csv"),
            "excel": self.tr("il_btn_export_excel"),
        }
        path, _ = QFileDialog.getSaveFileName(self, title_map.get(kind, self.tr("il_btn_export_json")), "invoices", filters[kind])
        if not path:
            return
        try:
            if kind == "json":
                repo = self.app.repos["invoices"]
                json_export_many(
                    [(inv, repo.list_reading(inv.id), repo.list_charges(inv.id)) for inv in invoices],
                    path)
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
            from pathlib import Path
            QMessageBox.information(
                self, self.tr("success"),
                self.tr("il_export_success", path=Path(path).name))
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