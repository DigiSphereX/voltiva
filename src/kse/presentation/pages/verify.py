from __future__ import annotations

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QScrollArea, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...application.services import CalculateInvoiceRequest
from ...domain.enums import ComparisonStatus, MeterScenario, SubscriberType
from .. import theme
from ..app_context import default_issue_dates
from ..widgets import (
    DataTable, FormRow, MoneyEdit, PageHeader, ReadingEdit, Section, chip_cell,
    configure_table, date_edit, error_label, error_text, money_display,
    primary_button,
)


class VerifyPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr

        header = PageHeader(self.tr("vk_title"))

        self.type_combo = QComboBox()
        for t in SubscriberType:
            self.type_combo.addItem(app.i18n.enum_label(t), t)
        self.scenario_combo = QComboBox()
        for s in MeterScenario:
            self.scenario_combo.addItem(app.i18n.enum_label(s), s)

        prev_date, curr_date = default_issue_dates()
        self.prev_date = date_edit(QDate(prev_date.year, prev_date.month, prev_date.day))
        self.curr_date = date_edit(QDate(curr_date.year, curr_date.month, curr_date.day))
        self.prev_reading = ReadingEdit()
        self.curr_reading = ReadingEdit()
        self.official_amount = MoneyEdit()

        verify_btn = primary_button(self.tr("vk_btn_verify"))
        verify_btn.setToolTip(self.tr("tt_vk_verify"))
        verify_btn.setMinimumWidth(140)

        self.err_lbl = error_label()

        input_card = Section(self.tr("vk_input"))
        for label, widget in (
            (self.tr("ni_subscriber_type"), self.type_combo),
            (self.tr("ni_scenario"), self.scenario_combo),
            (self.tr("ni_prev_reading"), self.prev_reading),
            (self.tr("ni_curr_reading"), self.curr_reading),
            (self.tr("ni_prev_date"), self.prev_date),
            (self.tr("ni_curr_date"), self.curr_date),
            (self.tr("vk_official"), self.official_amount),
        ):
            input_card.add_widget(FormRow(label, widget))
        input_card.add_widget(self.err_lbl)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.addStretch(1)
        actions.addWidget(verify_btn)
        input_card.add_layout(actions)
        input_card.body.addStretch(1)

        self.result_table = DataTable()
        self.result_table.setToolTip(self.tr("tt_vk_table"))
        self.result_table.setColumnCount(2)
        self.result_table.setHorizontalHeaderLabels([self.tr("col_item"), self.tr("col_value")])
        configure_table(self.result_table, widths={1: 190}, stretch=(0,),
                        row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.result_table.set_empty_text(self.tr("vk_empty"))

        result_card = Section(self.tr("vk_results"))
        result_card.body.addWidget(self.result_table, 1)

        body = QHBoxLayout()
        body.setSpacing(theme.Metrics.PAGE_SPACING)
        body.addWidget(input_card, 1)
        body.addWidget(result_card, 1)

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(
            theme.Metrics.PAGE_MARGIN, 18, theme.Metrics.PAGE_MARGIN, 18)
        outer.setSpacing(theme.Metrics.PAGE_SPACING)
        outer.addWidget(header)
        outer.addLayout(body, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(container)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        verify_btn.clicked.connect(self._verify)

    def refresh(self) -> None:
        pass

    def _verify(self) -> None:
        self.err_lbl.setVisible(False)
        self.result_table.clearSpans()
        self.result_table.setRowCount(0)
        try:
            prev_dt = self.prev_date.date().toPyDate()
            curr_dt = self.curr_date.date().toPyDate()
            req = CalculateInvoiceRequest(
                subscriber_type=self.type_combo.currentData(),
                previous_reading=self.prev_reading.reading(),
                current_reading=self.curr_reading.reading(),
                previous_read_date=prev_dt,
                current_read_date=curr_dt,
                scenario=self.scenario_combo.currentData(),
                official_amount=self.official_amount.money(),
            )
            result = self.app.invoices.verify(req)
            if result.report.issues:
                messages = ", ".join(i.localized(self.tr) for i in result.report.issues)
                self.err_lbl.setText(messages)
                self.err_lbl.setVisible(True)
                return
            calc = result.calc
            if calc is None:
                self.err_lbl.setText(self.tr("no_data"))
                self.err_lbl.setVisible(True)
                return

            colors = theme.colors()
            status_color = colors["muted"]
            rows: list[tuple[str, str, str]] = [
                (self.tr("vk_calculated"), money_display(calc.total_due), "amount"),
            ]
            status_text = ""
            if calc.comparison:
                cmp = calc.comparison
                status_text = self.tr("status_" + cmp.status.value.lower())
                status_color = {
                    ComparisonStatus.MATCH: colors["success"],
                    ComparisonStatus.MISMATCH: colors["danger"],
                }.get(cmp.status, colors["muted"])
                rows += [
                    (self.tr("vk_official"), money_display(cmp.official_amount), "amount"),
                    (self.tr("vk_diff"), money_display(cmp.diff), "diff"),
                    (self.tr("vk_ratio"), f"{cmp.ratio_pct:.1f}%", "amount"),
                    (self.tr("vk_status"), status_text, "status"),
                ]
            self.result_table.setRowCount(len(rows))
            for i, (label, value, kind) in enumerate(rows):
                label_item = QTableWidgetItem(label)
                label_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.result_table.setItem(i, 0, label_item)
                if kind == "status":
                    self.result_table.setCellWidget(i, 1, chip_cell(value, status_color))
                    continue
                value_item = QTableWidgetItem(value)
                value_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if kind == "diff":
                    value_item.setForeground(QColor(status_color))
                self.result_table.setItem(i, 1, value_item)
            if calc.comparison:
                for cause in calc.comparison.possible_causes:
                    row = self.result_table.rowCount()
                    self.result_table.insertRow(row)
                    self.result_table.setSpan(row, 0, 1, 2)
                    item = QTableWidgetItem("•  " + cause)
                    item.setForeground(QColor(colors["muted"]))
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self.result_table.setItem(row, 0, item)
        except Exception as exc:
            self.err_lbl.setText(error_text(self.app, exc))
            self.err_lbl.setVisible(True)
